// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Античит: дела» (шаг А6.7, 22.11.2026; domains/cases.py, /api/cases/*, операции case.*).
// Журнал дел AC-NNNN (joylog1.san.*) тем же кодом, что AstoryServer/Tools/Anticheat/ac_case.py: открыть, приложить события журнала ac.* и выдержки журналов
// стойки (маска секретов), выгрузка, решение по лестнице (от ступени 3 — два независимых источника; блок — операция account.block с причиной
// «AC-NNNN …»), исполнение, отзыв, снятие блока (account.unblock), апелляция (пересматривает другое лицо), закрытие, проверка целостности,
// отчёт отката по Serial (только отчёт). Каждое действие — предпросмотр тем же кодом в транзакции с откатом, затем подтверждение; блок и снятие —
// номером дела. Дела служебных учёток (≤ 5000) — только владелец. Доказательства — в каталоге службы на сервере (на ПК — только просмотр).
// Значения из базы (суть, тексты, имена, сводки событий, пути) — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (acText из acjournal.js), без T()
// и без HTML. Общие помощники — из app.js и acjournal.js: h(), T(), put(), mount(), shell(), sel(), badge(), errbox(), stale(), api(), op(),
// confirmWin(), notify(), dt(), fmt(), can(), acText(), acTable(), acAccount(), acChar(), acQs(), acDay().
"use strict";

const CS_STATUS = { open: "открыто", evidence: "доказательства", decision: "решение", executed: "исполнено", appeal: "апелляция", closed: "закрыто" };
const CS_OUTCOME = { sanctioned: "санкция", acquitted: "оправдан", no_action: "без мер", overturned: "решение отменено" };
const CS_KIND = { file: "файл", excerpt: "выдержка", "export": "выгрузка", report: "отчёт" };

function csRole() { return ((S.me && S.me.user) || {}).role; }
function csBadge(st) { return badge(T(CS_STATUS[st] || st), st === "executed" || st === "decision" ? "warn" : st === "closed" ? "" : "ok"); }
function csNo(no) { return h("button", { type: "button", class: "ghost small mono", onclick: () => { location.hash = "#/cases?case=" + encodeURIComponent(no); } }, acText(no)); }
function csIn(ph, len, cls) { return h("input", { type: "text", maxlength: len || 200, placeholder: ph, class: cls || "grow" }); }
function csLines(lines) { return h("pre", { class: "mono small pv" }, acText((lines || []).join("\n"))); }

// Действие дела: предпросмотр (код исходника в транзакции с откатом) → подтверждение (для блока / снятия — номером дела) → запись.
async function csOp(name, params, opts) {
  opts = opts || {};
  let p;
  try { p = await op(name, params, true); } catch (e) { notify(e.message, true); return null; }
  const pv = p.preview || {};
  const confirmIn = opts.confirm ? h("input", { type: "text", maxlength: 12, class: "mono", placeholder: "AC-NNNN" }) : null;
  const body = [h("div", { class: "pv" }, acText(pv.text)), csLines(pv.case_lines),
    (pv.warnings || []).map(w => h("div", { class: "note" }, acText(w))),
    confirmIn ? h("div", { class: "row" }, h("span", null, T("Подтвердите номером дела {0}: ", opts.confirm)), confirmIn) : null,
    h("div", { class: "muted small" }, "Предпросмотр — тот же код в транзакции с откатом. Действие попадёт в журнал дела и в журнал действий панели.")];
  if (!await confirmWin(T("Подтвердите"), body)) return null;
  const params2 = confirmIn ? Object.assign({}, params, { confirm: confirmIn.value.trim() }) : params;
  try {
    const x = await op(name, params2, false);
    notify(x.message || T("готово"));
    return x;
  } catch (e) { notify(e.message, true); return null; }
}

function csLadderTable(L) {
  return acTable([["Ступень", s => String(s.step)], ["Код", s => s.code], ["Название", s => h("span", null, T(s.name))],
    ["Срок, ч", s => s.hours === null ? "—" : String(s.hours)], ["Исполнение", s => s.exec], ["Механизм", s => h("span", { class: "small" }, T(s.mechanism))]], L.ladder);
}

// ---- форма «открыть дело»
// ★ А6.11 (22.11): pre — предзаполнение из жалобы игрока (web/reports.js «Открыть дело»): { title, char, hypothesis }; оператор правит и подтверждает сам
function csOpenForm(L, uid, after, pre) {
  const accIn = csIn("номер или логин", 61, "mono"), charIn = csIn("персонаж (необязательно)", 32), titleIn = csIn("суть дела одной строкой", 200);
  const hypIn = csIn("гипотеза / флаги отчёта (необязательно)", 2000), trIn = h("input", { type: "checkbox" });
  if (uid) accIn.value = uid;
  if (pre) { titleIn.value = (pre.title || "").slice(0, 200); charIn.value = (pre.char || "").slice(0, 32); hypIn.value = (pre.hypothesis || "").slice(0, 2000); }
  return h("div", { class: "card" }, h("h2", null, "Открыть дело"),
    h("div", { class: "row" }, h("span", null, "Учётка "), accIn, h("span", null, "Персонаж "), charIn),
    h("div", { class: "row" }, h("span", null, "Суть "), titleIn),
    h("div", { class: "row" }, h("span", null, "Гипотеза "), hypIn, h("label", null, trIn, " учебное дело")),
    h("div", { class: "row" }, h("button", { type: "button", onclick: async () => {
      const a = accIn.value.trim();
      const p = { title: titleIn.value.trim(), char: charIn.value.trim() || undefined, hypothesis: hypIn.value.trim() || undefined, training: trIn.checked };
      if (/^\d+$/.test(a)) p.uid = +a; else p.login = a;
      const x = await csOp("case.open", p);
      if (x && x.result && x.result.case_no) after(x.result.case_no);
    } }, "Открыть")),
    h("div", { class: "muted small" }, "Дела служебных учёток (номер ≤ 5000) ведёт только владелец."));
}

// ---- карточка дела: поля, действия, история, события, доказательства, блоки
async function csCase(no, L, my, box, evPrefill) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let r;
  try { r = await api("/api/cases/show?" + acQs({ case: no })); } catch (e) { if (!stale(my)) put(box, errbox(e)); return; }
  if (stale(my)) return;
  const c = r.case, reload = () => csCase(c.case_no, L, my, box);
  const P = L.perms || {}, w = L.can_write;
  const svcLock = r.service && csRole() !== "owner";
  const act = h("div");
  const forms = [];
  const run = async (name, params, opts) => { const x = await csOp(name, Object.assign({ case: c.case_no }, params), opts); if (x) reload(); };
  if (!w) forms.push(h("div", { class: "note" }, acText(L.store_note)));
  else if (svcLock) forms.push(h("div", { class: "note" }, "Дело служебной учётки (номер ≤ 5000) — действия только у владельца."));
  else {
    if (P["ac.case"] && c.status !== "closed") {
      const evIn = csIn("события: таблица:номер через запятую, например other:15, move_combat:7158", 4000, "grow mono");
      if (evPrefill) evIn.value = evPrefill;
      const fromIn = h("input", { type: "date" }), toIn = h("input", { type: "date" }), noteIn = csIn("пометка (необязательно)", 400);
      forms.push(h("div", { class: "card" }, h("h3", null, "Приложить события журнала ac.*"),
        h("div", { class: "row" }, evIn), h("div", { class: "row" }, h("span", null, "или все события учётки за окно с "), fromIn, h("span", null, " по "), toIn),
        h("div", { class: "row" }, noteIn, h("button", { type: "button", onclick: () => {
          const ev = evIn.value.split(/[\s,;]+/).map(x => x.trim()).filter(Boolean);
          run("case.attach", { events: ev.length ? ev : undefined, from: acDay(fromIn.value) || undefined, to: acDay(toIn.value) || undefined,
            note: noteIn.value.trim() || undefined });
        } }, "Приложить"))));
      if (P["logs.view"]) {
        const srcIn = csIn("источник (gslog, patch, …)", 40, "mono"), procIn = csIn("копия (GameServer, NpcServer, …)", 80, "mono");
        const kindIn = csIn("вид (Log_SpeedHack) — если есть", 80, "mono"), fileIn = csIn("файл (SpeedHack_20260112.txt)", 80, "mono");
        const ndIn = csIn("подстроки отбора через |, например SpeedHack|GM_x", 600), lbIn = csIn("метка источника, например «GS SpeedHack»", 64);
        forms.push(h("div", { class: "card" }, h("h3", null, "Приложить выдержку журнала стойки"),
          h("div", { class: "muted small" }, "Путь — только из белого списка «Журналов стойки». В выдержку попадают строки с подстроками отбора; секреты, хеши паролей (32-hex) и — без права logs.view_ip — IP маскируются ДО отбора. В реестр пишется sha256 источника и выдержки."),
          h("div", { class: "row" }, srcIn, procIn, kindIn, fileIn), h("div", { class: "row" }, ndIn, lbIn),
          h("div", { class: "row" }, h("button", { type: "button", onclick: () => run("case.attach", {
            log: { source: srcIn.value.trim(), proc: procIn.value.trim(), kind: kindIn.value.trim() || null, name: fileIn.value.trim() },
            needles: ndIn.value.split("|").map(x => x.trim()).filter(Boolean), label: lbIn.value.trim() }) }, "Приложить выдержку"))));
      }
      const fmtSel = sel([["json,csv", "JSON и CSV"], ["json", "JSON"], ["csv", "CSV"]], "json,csv");
      const serIn = csIn("Serial (GUID) через запятую", 2000, "grow mono"), rfIn = h("input", { type: "date" }), rtIn = h("input", { type: "date" });
      forms.push(h("div", { class: "card" }, h("h3", null, "Выгрузка и отчёт отката"),
        h("div", { class: "row" }, h("span", null, "Выгрузить события дела "), fmtSel, h("button", { type: "button", onclick: () => run("case.export", { format: fmtSel.value }) }, "Выгрузить")),
        h("div", { class: "row" }, serIn, h("span", null, " или окно с "), rfIn, h("span", null, " по "), rtIn,
          h("button", { type: "button", class: "ghost", onclick: () => {
            const ss = serIn.value.split(/[\s,;]+/).map(x => x.trim()).filter(Boolean);
            run("case.rollback_report", { serials: ss.length ? ss : undefined, from: acDay(rfIn.value) || undefined, to: acDay(rtIn.value) || undefined });
          } }, "Отчёт отката по Serial")),
        h("div", { class: "muted small" }, "Отчёт отката — ТОЛЬКО отчёт: игровые таблицы не меняются; откат делает владелец на копии базы.")));
    }
    // ★ ревизия 59 Н-2 (решение владельца №3): ступени 0–2 решает и gm (ac.decide_low), со ступени 3 — admin / owner (ac.decide)
    const high = !!P["ac.decide"], lowOk = high || !!P["ac.decide_low"];
    if (lowOk) {
      if (c.status === "evidence") {
        const stepSel = h("select", null, L.ladder.filter(s => high || s.step < L.decide_high).map(s => h("option", { value: String(s.step) }, String(s.step) + " · " + T(s.name))));
        const hrsIn = h("input", { type: "number", min: 1, max: 87600, class: "num", placeholder: "часы" });
        const txIn = csIn("на основании чего", 2000), reIn = csIn("причина латиницей (в BlockList.Reason после номера дела)", 200);
        const ovIn = csRole() === "owner" ? csIn("снять правило двух источников — почему (только владелец)", 400) : null;
        forms.push(h("div", { class: "card" }, h("h3", null, "Решение по лестнице"),
          h("div", { class: "row" }, h("span", null, "Ступень "), stepSel, h("span", null, " срок (ступени 3–4, если не по лестнице) "), hrsIn),
          h("div", { class: "row" }, txIn), h("div", { class: "row" }, reIn), ovIn ? h("div", { class: "row" }, ovIn) : null,
          h("div", { class: "row" }, h("button", { type: "button", onclick: () => {
            const st = +stepSel.value, blk = (L.ladder.find(s => s.step === st) || {}).exec === "block";
            run("case.decide", { step: st, hours: hrsIn.value ? +hrsIn.value : undefined, text: txIn.value.trim(), reason_en: reIn.value.trim() || undefined,
              override_two_sources: ovIn && ovIn.value.trim() ? ovIn.value.trim() : undefined }, blk ? { confirm: c.case_no } : null);
          } }, "Вынести решение")),
          h("div", { class: "muted small" }, acText(T("Со ступени {0} — доказательства из двух независимых источников. Блок (ступени 3–5) — операция account.block с причиной «{1} s<ступень> <часы>h…»; не встал — откатывается, дело не исполняется.", L.two_sources_from_step, c.case_no)))));
      }
      if (c.status === "decision" && (high || (c.ladder_step !== null && c.ladder_step < L.decide_high))) {
        const exIn = csIn("что сделано (нотис, кик, откат владельцем)", 2000), wdIn = csIn("почему отзывается", 2000);
        forms.push(h("div", { class: "card" }, h("h3", null, "Исполнение решения"),
          h("div", { class: "row" }, exIn, h("button", { type: "button", onclick: () => run("case.execute", { text: exIn.value.trim() }) }, "Отметить исполнение")),
          h("div", { class: "row" }, wdIn, h("button", { type: "button", class: "ghost", onclick: () => run("case.withdraw", { text: wdIn.value.trim() }) }, "Отозвать решение"))));
      }
      if (high && (r.blocks || []).some(b => !b.lifted_at)) {
        const ltIn = csIn("пояснение (необязательно)", 2000), allIn = h("input", { type: "checkbox" });
        forms.push(h("div", { class: "card" }, h("h3", null, "Снять блок дела"),
          h("div", { class: "row" }, ltIn, h("label", null, allIn, " снять и чужие блоки учётки"),
            h("button", { type: "button", class: "ok", onclick: () => run("case.lift", { text: ltIn.value.trim() || undefined, all_blocks: allIn.checked }, { confirm: c.case_no }) }, "Снять блок")),
          h("div", { class: "muted small" }, "Снятие — операция account.unblock (как OPBlockDel): строки BlockList → BlockHistory, us_block = 0.")));
      }
      if (high && c.status !== "closed" && c.status !== "appeal") {
        const ocSel = sel([["sanctioned", T("санкция")], ["acquitted", T("оправдан")], ["no_action", T("без мер")]], c.status === "executed" ? "sanctioned" : "no_action");
        const ctIn = csIn("итог словами", 2000), fuIn = csRole() === "owner" ? csIn("закрыть при нарушенной целостности — почему (только владелец)", 400) : null;
        forms.push(h("div", { class: "card" }, h("h3", null, "Закрыть дело"),
          h("div", { class: "row" }, h("span", null, "Итог "), ocSel, ctIn), fuIn ? h("div", { class: "row" }, fuIn) : null,
          h("div", { class: "row" }, h("button", { type: "button", class: "ghost", onclick: () => run("case.close", { outcome: ocSel.value, text: ctIn.value.trim(),
            force_unverified: fuIn && fuIn.value.trim() ? fuIn.value.trim() : undefined }) }, "Закрыть дело"))));
      }
    }
    if (P["ac.appeal"]) {
      if (c.status === "executed" || (c.status === "closed" && c.outcome === "sanctioned")) {
        const apIn = csIn("текст апелляции", 2000), whoIn = csIn("кто подаёт (игрок)", 64), lateIn = csIn("принять после срока — почему", 400);
        forms.push(h("div", { class: "card" }, h("h3", null, "Апелляция"),
          h("div", { class: "row" }, apIn, whoIn), h("div", { class: "row" }, lateIn,
            h("button", { type: "button", onclick: () => run("case.appeal", { text: apIn.value.trim(), who: whoIn.value.trim() || undefined, late: lateIn.value.trim() || undefined }) }, "Принять апелляцию"))));
      }
      if (c.status === "appeal") {
        const rvIn = csIn("основание пересмотра", 2000);
        forms.push(h("div", { class: "card" }, h("h3", null, "Пересмотр апелляции"),
          h("div", { class: "muted small" }, acText(T("Пересматривает другое лицо — не {0}, выносивший решение.", c.decided_by || "—"))),
          h("div", { class: "row" }, rvIn, h("button", { type: "button", onclick: () => run("case.appeal", { text: rvIn.value.trim(), resolve: "upheld" }) }, "Решение в силе"),
            h("button", { type: "button", class: "ghost", onclick: () => run("case.appeal", { text: rvIn.value.trim(), resolve: "overturned" }) }, "Отменить решение"))));
      }
    }
  }
  const verBox = h("div");
  put(act, forms);
  const fields = [["status", "Статус"], ["user_index", "Учётка"], ["login", "Логин"], ["char_name", "Персонаж"], ["hypothesis", "Гипотеза"],
    ["opened_by", "Открыл"], ["opened_at", "Открыто"], ["ladder_step", "Ступень"], ["decision_kind", "Решение"], ["block_hours", "Срок, ч"],
    ["decision_text", "Основание"], ["decided_by", "Решение вынес"], ["decided_at", "Решение вынесено"], ["executed_by", "Исполнил"],
    ["executed_at", "Исполнено"], ["execution_text", "Исполнение"], ["appeal_until", "Апелляция до"], ["appeal_by", "Апелляцию подал"],
    ["appeal_text", "Текст апелляции"], ["appeal_result", "Итог апелляции"], ["appeal_reviewed_by", "Пересматривал"], ["outcome", "Итог"],
    ["closed_by", "Закрыл"], ["closed_at", "Закрыто"], ["close_text", "Итог словами"]];
  put(box,
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, acText(c.case_no + " — " + c.title)), csBadge(c.status),
      c.is_training ? badge(T("учебное"), "") : null, r.service ? badge(T("служебная учётка"), "warn") : null,
      h("button", { type: "button", class: "ghost", onclick: async () => {
        put(verBox, h("div", { class: "muted" }, "Проверяю…"));
        try { const v = await api("/api/cases/verify?" + acQs({ case: c.case_no })); put(verBox, v.cases.map(x => [x.ok ? badge("OK", "") : badge(T("ОШИБКИ"), "bad"), csLines(x.case_lines)])); }
        catch (e) { put(verBox, errbox(e)); }
      } }, "Проверить целостность"), h("button", { type: "button", class: "ghost", onclick: reload }, "Обновить"),
      // ★ А6.12: сообщения учётки дела в журнале чата за период дела (7 суток до открытия — по сегодня)
      can("chat.view") && c.user_index ? h("button", { type: "button", class: "ghost", onclick: () => { location.hash = "#/chat?" + acQs({ account: c.user_index, from: chFrom(c.opened_at, 7) }); } },
        "Сообщения в чате") : null),
      verBox,
      acTable([["Поле", f => h("span", null, f[1])], ["Значение", f => f[0] === "user_index" ? acAccount(c.user_index, c.login) : f[0] === "status" ? csBadge(c.status)
        : f[0] === "outcome" && c.outcome ? h("span", null, T(CS_OUTCOME[c.outcome] || c.outcome)) : acText(c[f[0]])]], fields.filter(f => c[f[0]] !== null && c[f[0]] !== undefined)),
      h("div", { class: "muted small" }, acText(T("Независимые источники: {0}. Хранилище: {1}", (r.sources || []).join(" · ") || "—", r.store || "—")))),
    act,
    h("div", { class: "card" }, h("h3", null, "История"),
      acTable([["Когда", x => dt(x.at)], ["Кто", x => x.actor], ["Действие", x => x.action], ["Статус", x => (x.status_from || "") + (x.status_from !== x.status_to ? " → " + x.status_to : "")],
        ["Подробности", x => h("span", { class: "small" }, acText(x.detail))]], r.log)),
    h("div", { class: "card" }, h("h3", null, "События журнала (снимки строк)"),
      acTable([["Таблица", e => "ac." + e.table_name], ["№", e => String(e.event_id)], ["Когда", e => dt(e.ev_local)], ["Сервер", e => e.server_name],
        ["Персонаж", e => e.char_name], ["IP", e => e.ip], ["Вид", e => e.violation_type], ["Сводка", e => h("span", { class: "small" }, acText(e.summary))],
        ["sha256 снимка", e => h("span", { class: "mono small" }, acText((e.row_sha256 || "").slice(0, 16) + "…"))], ["Приложил", e => e.attached_by]], r.events)),
    h("div", { class: "card" }, h("h3", null, "Доказательства"),
      acTable([["Вид", v => h("span", null, T(CS_KIND[v.kind] || v.kind))], ["Файл", v => h("span", { class: "mono small" }, acText(v.rel_path))], ["Байт", v => fmt(v.size_bytes)],
        ["sha256", v => h("span", { class: "mono small" }, acText(v.sha256))], ["Источник", v => v.source_label],
        ["Путь источника", v => h("span", { class: "mono small" }, acText(v.source_path))], ["Добавил", v => v.added_by], ["Когда", v => dt(v.added_at)]], r.evidence)),
    h("div", { class: "card" }, h("h3", null, "Блоки по делу"),
      acTable([["С", b => dt(b.black_date)], ["По", b => dt(b.close_date)], ["Часы", b => String(b.hours)], ["Причина", b => h("span", { class: "mono small" }, acText(b.reason))],
        ["Наложил", b => b.applied_by], ["Чем", b => h("span", { class: "small" }, acText(b.apply_via))], ["Снят", b => b.lifted_at ? dt(b.lifted_at) + " · " + (b.lifted_by || "") : "—"],
        ["Чем снят", b => h("span", { class: "small" }, acText(b.lift_via))]], r.blocks),
      h("div", { class: "muted small" }, acText(T("BlockList учётки сейчас: {0}", (r.blocklist_now || []).map(b => dt(b.BlackDate) + ".." + dt(b.CloseDate) + " «" + b.Reason + "»").join("; ") || T("пусто"))))));
}

async function viewCases(my, q) {
  q = q || new URLSearchParams();
  const ladBox = h("div"), listBox = h("div"), caseBox = h("div"), openBox = h("div");
  mount(shell("#/cases", h("h1", null, "Античит: дела"), h("div", { class: "note" },
    acText(T("Дела AC-NNNN — тот же код, что ac_case.py: доказательства из журнала античита и журналов стойки с sha256, решение по лестнице санкций (со ступени 3 — два независимых источника), блок — операцией account.block с причиной «AC-NNNN …», апелляцию пересматривает другое лицо."))),
    caseBox, listBox, openBox, ladBox));
  let L;
  try { L = await api("/api/cases/ladder"); } catch (e) { put(listBox, errbox(e)); return; }
  if (stale(my)) return;
  put(ladBox, h("div", { class: "card" }, h("h2", null, "Лестница санкций"), csLadderTable(L),
    h("div", { class: "muted small" }, acText(T("Апелляция — {0} дн., хранение материалов — не меньше {1} дн., файл — до {2} МБ. Код дел: {3} (md5 {4}).", L.appeal_days, L.retention_days, L.max_file_mb, L.source.where, L.source.code_md5))),
    L.store_note ? h("div", { class: "note" }, acText(L.store_note)) : null));
  const stSel = sel([["", T("все статусы")]].concat(Object.entries(CS_STATUS).map(([k, v]) => [k, T(v)])), "");
  const accIn = csIn("номер или логин", 61, "mono"), trSel = sel([["", T("все")], ["0", T("рабочие")], ["1", T("учебные")]], "");
  const uid = q.get("uid"), ev = q.get("ev"), cs = q.get("case");
  if (uid) accIn.value = uid;
  const out = h("div");
  async function load() {
    put(out, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/cases/list?" + acQs({ status: stSel.value, account: accIn.value.trim(), training: trSel.value })); }
    catch (e) { if (!stale(my)) put(out, errbox(e)); return; }
    if (stale(my)) return;
    put(out, acTable([["Дело", c => csNo(c.case_no)], ["Статус", c => csBadge(c.status)], ["Учётка", c => acAccount(c.user_index, c.login)],
      ["Персонаж", c => c.char_name], ["Ступень", c => c.ladder_step === null ? "—" : String(c.ladder_step)],
      ["Итог", c => c.outcome ? h("span", null, T(CS_OUTCOME[c.outcome] || c.outcome)) : acText("—")], ["Событий", c => fmt(c.n_events)], ["Файлов", c => fmt(c.n_evidence)],
      ["Блоков (действует)", c => fmt(c.n_blocks) + " (" + fmt(c.n_blocks_active) + ")"], ["Суть", c => c.title],
      ["", c => c.is_training ? badge(T("учебное"), "") : acText("")], ["Открыто", c => dt(c.opened_at)]], r.rows),
      r.more ? h("div", { class: "muted small" }, "Показаны последние 500 дел — сузьте фильтр.") : null,
      ev && L.can_write && can("ac.case") && r.rows.length ? h("div", { class: "note" }, acText(T("Событие {0}: выберите дело учётки выше — поле событий в карточке дела будет заполнено.", ev))) : null);
    if (ev && r.rows.length === 1 && !cs) csCase(r.rows[0].case_no, L, my, caseBox, ev);
  }
  put(listBox, h("div", { class: "card" }, h("h2", null, "Дела"),
    h("div", { class: "row" }, h("span", null, "Статус "), stSel, h("span", null, "Учётка "), accIn, h("span", null, "Вид "), trSel,
      h("button", { type: "button", onclick: load }, "Показать")), out));
  if (can("ac.case") && L.can_write) put(openBox, csOpenForm(L, uid, no => { location.hash = "#/cases?case=" + encodeURIComponent(no); }));
  if (cs) csCase(cs, L, my, caseBox, ev);
  load();
}
