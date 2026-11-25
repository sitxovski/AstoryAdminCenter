// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Античит: автоблок и EAC» (шаг А6.8, часть «чтение», 22.11.2026; domains/autoblock.py, /api/autoblock/*). ТОЛЬКО ЧТЕНИЕ.
// Сверка лестницы санкций ac_case_config.json с patches.ini P48 / P69 всех копий GameServer — тем же кодом, что ac_case.py ladder --check;
// паритет копий, режим секций по журналу патчей, счётчики автоблоков. История автоблоков: кики и автоблоки P48, ступени P69, BlockList /
// BlockHistory с причиной, сроком, происхождением и снятием. EAC по учётке — процесс и порты, мост P73, KICK-события; ★ А6.8 (вторая часть,
// 22.11): «EAC сейчас» — точка статуса службы AsdaEacServer 127.0.0.1 (только на сервере; IP канала EAC и игры — только с players.view_net,
// без права служба их не отдаёт). Тексты EacServer (пояснения событий, «почему не KICK») — данные службы: текстовыми узлами, как есть.
// Правка автоблока — набором patch.set «Настроек патчей» (#/shops/patches).
// Значения из базы и ini (имена, причины, тексты журнала) — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (acText из acjournal.js), без T() и
// без HTML. Общие помощники — из app.js и acjournal.js: h(), T(), put(), mount(), shell(), badge(), errbox(), stale(), api(), dt(), fmt(),
// acText(), acTable(), acAccount(), acChar(), acQs(), acDay().
"use strict";

const AB_MODES = { active: "действует", journal: "журнал (Mode=0)", off: "выключен", pending_on: "включится после рестарта",
  pending_off: "выключится после рестарта", self_off: "сам выключился при запуске", failed: "не встал", nolog: "нет в журнале патчей",
  unread: "не прочитано", absent: "нет секции", general: "общие" };
const AB_ORIGIN = { p48: "автоблок P48 (кики)", p69: "автоблок P69 (целостность пакетов)", gm6094: "GM-блок 6094 (Log_SpeedHack)",
  hack: "UPHackBlock (2271 / GM 6094) — пары ни в журнале античита, ни в Log_SpeedHack нет",
  user: "UPUserBlock (Login Block)", "case": "дело античита (AC-…)", panel: "блок панели (account.block)", manual: "причина оператора (скрипт или вручную)" };
const AB_STATE = { active: "действует", expired: "срок истёк — снимется при входе", lifted: "снят" };
// ★ ревизия 58 Н-1: BlockHistory времени снятия не хранит — «по сроку» только там, где это установлено (дело — san.case_block)
const AB_LIFT = { panel: "снят панелью", case_term: "снят по сроку (дело, san.case_block)", case_early: "снят досрочно по делу (san.case_block)",
  unknown: "срок прошёл — снят по сроку или досрочно (BlockHistory времени снятия не хранит)", early: "снят досрочно не панелью" };
const AB_CKIND = { kicks: "киков (окно WindowHours)", observe: "наблюдение (Mode=0, «был бы блок»)", live: "боевой (Mode=1)" };
const AB_CAT = { player: "игроки", service: "служебные ≤ 5000", none: "без учётки", all: "все учётки" };
// ★ А6.8: виды событий учётки точки статуса EAC (Core.cpp Ev), причины §5, причины FailOpen (Core.cpp FailOpenWhy)
const AB_EAC_EV = { reg_ok: "EAC-сессия зарегистрирована", reg_reject: "регистрация EAC отклонена", reg_limit: "REG сверх предела учётки",
  reg_error: "ошибка RegisterClient", auth: "аутентифицирована (RemoteAuthComplete)", auth_timeout: "нет RemoteAuthComplete в срок",
  eac_lost: "EAC-сессия потеряна", evicted: "вытеснена новой EAC-сессией", violation: "нарушение EAC (ClientActionRequired)",
  decision: "решение без KICK", kick: "KICK отправлен в P73", kick_wait: "KICK ждёт подключения P73", protected: "игровая сессия защищена",
  unprotected: "защита игровой сессии потеряна", login: "вход в игру (LOGIN)", logout: "выход из игры (LOGOUT)", rebind: "вход соулмейтом (REBIND)",
  orphan_drop: "сессия снята: P73 не вернулся",
  connect_grace: "Epic Connect у клиента не проходит — решение отложено", connect_grace_end: "поблажка «Epic Connect не проходит» снята" };
const AB_EAC_REASON = { no_session: "1 — нет EAC-сессии за BindTimeout", eac_action: "2 — EAC потребовал удалить", channel_lost: "3 — канал 15901 потерян дольше Grace",
  reg_rejected: "4 — регистрация отклонена или не аутентифицирована", evicted: "5 — вытеснен новой EAC-сессией", not_bound: "6 — игра не привязана к EAC-сессии" };
const AB_EAC_FO = { "нет сессии AntiCheatServer (BeginSession не было или не удалась)": "нет сессии AntiCheatServer (BeginSession не было или не удалась)",
  "окно после старта": "окно после старта службы", "Epic недоступен": "Epic недоступен", "AsdaId деградировал (доля 503)": "AsdaId деградировал (доля 503)" };

function abLabel(map, k) { return h("span", null, map[k] || "?"); }
function abCheck(c) {
  if (c.unread) return badge(T("не прочитано"), "warn");
  return c.ok ? badge("OK", "") : badge(T("РАСХОЖДЕНИЕ"), "bad");
}
function abWho(w) {
  if (!w) return acText("—");
  if (w.gm) return h("span", null, h("span", null, "GM"), " ", acText(w.gm + " " + dt(w.at) + " · " + w.proc + "\\" + w.file));
  if (w.source === "san.case_block") return h("span", null, acText(w.login + " " + dt(w.at) + (w.via_text ? " · " + w.via_text : "")), " ", h("span", { class: "muted small" }, "(дело)"));
  return h("span", null, h("a", { href: "#/audit", class: "mono small" }, acText("№" + w.audit_id)), " ", acText(w.login), " ", acText(dt(w.at)));
}
function abSecRow(s) { return Object.entries(s || {}).map(([k, v]) => k + "=" + v).join(" · "); }
// Подпись из словаря или (нет в словаре) — текст службы как есть.
function abKnown(map, k) { return map[k] ? h("span", null, map[k]) : acText(k || "—"); }
// ★ А6.8: «EAC сейчас» — ответ точки статуса службы EAC (r.live домена autoblock.eac_live).
function abLive(lv) {
  if (lv.state !== "ok") return h("div", { class: "note" }, acText(lv.note || "—"));
  const sv = lv.server || {}, a = lv.account, net = !!lv.can_net;
  const m1 = sv.mode === 1;   // ★ р61 М-5: Mode=1 — только журнал, KICK не отправляется
  const out = [kv([["Режим EAC", m1 ? h("span", null, acText("Mode=1 · "), h("span", null, "только журнал: KICK не отправляется")) : acText("Mode=" + sv.mode)], ["FailOpen", sv.fail_open ? abKnown(AB_EAC_FO, sv.fail_open) : h("span", null, "нет")],
    ["Сессия EOS", fmt(!!sv.eos_session)], ["Каналов 15901 / аутентифицировано", acText(fmt((sv.eac || {}).registered) + " / " + fmt((sv.eac || {}).authenticated))],
    ["Игровых сессий / защищено", acText(fmt((sv.games || {}).sessions) + " / " + fmt((sv.games || {}).protected))],
    ["Снимок", acText(T("{0} мс назад · прочитано {1} (время сервера)", sv.age_ms, dt(lv.read_at)))]]),
    h("div", { class: "muted small" }, "Все времена блока — по часам сервера.")];
  if (!lv.found || !a) {
    out.push(h("div", { class: "muted" }, "Учётки нет в таблицах EacServer: не в игре и без EAC-сессии."));
    return out;
  }
  const e = a.eac;
  out.push(kv([["EAC-сессия", a.connected ? badge(T("подключена"), "") : badge(T("нет"), "warn")],
    ["Аутентификация", e ? (e.authenticated ? badge("Authenticated (RemoteAuthComplete)", "") : badge(T("не аутентифицирована"), "bad")) : acText("—")],
    ["Зарегистрирована", acText(e ? dt(e.registered_at) : "—")], ["Последний PING", e ? acText(T("{0} мс назад", e.last_ping_ago_ms)) : acText("—")],
    ["BIND в памяти", acText(e ? fmt(e.binds) : "—")], ["IP канала EAC", net && e && e.net ? acText(e.net.ip) : h("span", { class: "muted" }, net ? "—" : "только с правом сетевых данных")],
    ["Отказ регистрации", acText(a.reject_at ? dt(a.reject_at) : "—")], ["REG за окно", acText(fmt(a.reg_in_window))]]));
  out.push(h("h3", null, "Игровые сессии (P73)"),
    acTable([["Сервер", x => x.server], ["pid", x => String(x.pid)], ["userNum", x => String(x.user_num)], ["Учётка персонажа", x => String(x.uid)],
      ["EAC-учётка", x => String(x.eac_uid)], ["Вход", x => dt(x.login_at)],
      ["Защита", x => x.protected ? badge(T("защищена"), "") : badge(T("не защищена"), x.orphan ? "warn" : "bad")],
      ["bind", x => h("span", null, x.bind_zero ? "нулевой" : x.bound ? "сопоставлен" : "не сопоставлен")],
      ["Срок", x => x.deadline_at ? (m1 ? h("span", null, acText(dt(x.deadline_at) + " · "), h("span", null, "в Mode=1 кика не будет")) : dt(x.deadline_at)) : "—"], ["Решение", x => x.decided ? abKnown(AB_EAC_REASON, x.decided_code) : acText("—")],
      ["Почему без KICK", x => x.decided_why || "—"], ["Последний KICK", x => x.last_kick_at ? dt(x.last_kick_at) : "—"],
      ["IP игры", x => net && x.net ? x.net.ip : "—"]], a.games || []),
    h("h3", null, "Последние события EAC"),
    acTable([["Когда", x => dt(x.at)], ["Событие", x => abKnown(AB_EAC_EV, x.kind)], ["Причина", x => x.reason_code ? abKnown(AB_EAC_REASON, x.reason_code) : acText("—")],
      ["EOS", x => x.eos || "—"], ["Пояснение службы EAC", x => x.text]], (a.events || []).slice().reverse()));
  return out;
}

async function viewAutoblock(my) {
  const lad = h("div"), hist = h("div"), eacBox = h("div");
  mount(shell("#/autoblock", h("h1", null, "Античит: автоблок и EAC"), h("div", { class: "note" },
    acText(T("Только чтение. Сверка лестницы санкций с patches.ini — тем же кодом, что ac_case.py ladder --check; история автоблоков по журналу античита и блокам учёток; EAC по учётке — по тому, что уже есть. Правка автоблока — только набором изменений «Настроек патчей» и рестартом стойки."))),
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Лестница санкций и patches.ini"),
      h("button", { type: "button", class: "ghost", onclick: () => { location.hash = "#/shops/patches"; } }, "Правка — в «Настройках патчей»")), lad),
    h("div", { class: "card" }, h("h2", null, "История автоблоков"), hist),
    h("div", { class: "card" }, h("h2", null, "EAC по учётке"), eacBox)));

  // ---- лестница
  (async () => {
    put(lad, h("div", { class: "muted" }, "Загружаю…"));
    let L;
    try { L = await api("/api/autoblock/ladder"); } catch (e) { if (!stale(my)) put(lad, errbox(e)); return; }
    if (stale(my)) return;
    const copies = L.copies.map(c => c.folder);
    put(lad,
      h("div", { class: "row" }, L.mismatches ? badge(T("расхождений: {0}", L.mismatches), "bad") : badge(T("расхождений нет"), ""),
        L.unread_checks ? badge(T("не прочитано проверок: {0}", L.unread_checks), "warn") : null,
        h("span", { class: "muted small" }, acText(T("прочитано {0} UTC · код {1} ({2}), конфиг {3}", dt(L.read_at), L.source.code_md5.slice(0, 8),
          L.source.where === "ext" ? T("копия выкладки") : T("исходник ПК"), L.source.config_md5.slice(0, 8))))),
      (L.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      (L.notes || []).map(x => h("div", { class: "muted small" }, acText(x))),
      h("h3", null, "Ступени (ac_case_config.json)"),
      acTable([["Ступень", r => String(r.step)], ["Код", r => r.code], ["Название", r => r.name], ["Срок, ч", r => r.hours === null ? "—" : String(r.hours)],
        ["Исполнение", r => r.exec], ["Механизм", r => r.mechanism]], L.ladder),
      h("div", { class: "muted small" }, acText(T("Апелляция {0} суток, хранение материалов не меньше {1} суток, два независимых источника — со ступени {2}.",
        L.appeal_days, L.retention_days, L.two_sources_from_step))),
      h("h3", null, "Сверка с patches.ini"),
      acTable([["Копия", r => r.server], ["Ступень", r => String(r.step)], ["Ключ", r => r.key], ["В ini", r => r.ini === null || r.ini === undefined ? "—" : r.ini],
        ["В лестнице", r => String(r.ladder)], ["Итог", r => abCheck(r)]], L.check),
      h("h3", null, "Паритет копий"),
      acTable([["Пара", r => r.pair.join(" ↔ ")], ["md5", r => r.md5.map(x => x.slice(0, 8)).join(" / ")],
        ["Итог", r => r.same ? badge(T("совпадает"), "") : badge(T("паритет нарушен"), "bad")]], L.parity),
      L.diverge.length ? acTable([["Секция", r => r.section], ["Ключ", r => r.key], ["Значения", r => Object.entries(r.values).map(([k, v]) => k + "=" + v).join(" · ")]], L.diverge)
        : h("div", { class: "muted small" }, "Значения секций P48 / P69 / P73 во всех прочитанных копиях одинаковы."),
      h("h3", null, "Состояние патчей по ini"),
      (L.states || []).map(x => h("div", { class: x.journal_only && x.section === "P69_IntegrityAutoBlock" ? "note" : "muted small" },
        acText(x.why + " · " + x.copies.join(", ")))),
      h("h3", null, "Режим секций по журналу патчей"),
      acTable([["Секция", r => r[0]]].concat(copies.map(f => [f, r => abLabel(AB_MODES, (r[1] || {})[f])])), Object.entries(L.modes)),
      h("h3", null, "Ключи секций в копиях"),
      acTable([["Копия", r => r.folder], ["md5", r => r.md5 ? r.md5.slice(0, 8) : "—"], ["Изменён", r => r.mtime],
        ["P48", r => h("span", { class: "mono small" }, acText(abSecRow((r.sections || {}).P48_KickAutoBlock)))],
        ["P69", r => h("span", { class: "mono small" }, acText(abSecRow((r.sections || {}).P69_IntegrityAutoBlock)))],
        ["P73", r => h("span", { class: "mono small" }, acText(abSecRow((r.sections || {}).P73_EacBridge)))]], L.copies),
      h("h3", null, "Счётчики автоблоков"),
      acTable([["Секция", r => r[0]], ["Файл", r => r[1].file], ["Счёт", r => h("span", null, acText("[" + r[1].section + "] "), AB_CKIND[r[1].kind] || "?")],
        ["Учёток в счёте", r => r[1].read ? fmt(r[1].accounts) : T("файла нет")],
        ["Счёт сгорел (окно)", r => r[1].kind === "kicks" && r[1].read ? acText(fmt(r[1].expired) + " / " + fmt(r[1].accounts) + " · " + r[1].window_hours + " ч") : acText("—")],
        ["Изменён", r => r[1].mtime]],
        [].concat(...Object.entries(L.counters).map(([s, xs]) => xs.map(x => [s, x])))));
  })();

  // ---- история
  const fromIn = h("input", { type: "date" }), toIn = h("input", { type: "date" });
  const accIn = h("input", { type: "text", maxlength: 40, placeholder: "номер или логин", class: "mono" });
  const svcSel = sel([["sep", T("служебные отдельно")], ["in", T("служебные в общем итоге")]], "sep");
  const hOut = h("div");
  async function loadHist() {
    put(hOut, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/autoblock/history?" + acQs({ from: acDay(fromIn.value), to: acDay(toIn.value), account: accIn.value.trim(), svc: svcSel.value })); }
    catch (e) { if (!stale(my)) put(hOut, errbox(e)); return; }
    if (stale(my)) return;
    const cats = r.svc === "sep" ? ["player", "service"] : ["player"];
    const sum = (o, c) => r.svc === "sep" ? o[c] : (o.player + o.service + o.none);
    const cnt = (c, f) => r.blocks.filter(b => (r.svc !== "sep" || b.cat === c) && f(b)).length;
    const blocks = r.svc === "sep" ? cats.map(c => [c, r.blocks.filter(b => b.cat === c)]) : [["all", r.blocks]];
    const capped = Object.entries(r.capped || {}).filter(([, v]) => v).map(([k]) => k);
    put(hOut,
      h("div", { class: "muted small" }, acText(T("Период {0} — {1}. Пара «блок ↔ событие журнала» — та же учётка в пределах {2} мин.", r.from, r.to, r.match_min))),
      capped.length ? badge(T("обрезано по пределу строк: {0}", capped.join(", ")), "warn") : null,
      (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      (r.notes || []).map(x => h("div", { class: "muted small" }, acText(x))),
      h("h3", null, "Итоги"),
      acTable([["Категория", c => r.svc === "sep" ? abLabel(AB_CAT, c) : h("span", null, "все учётки")], ["Киков", c => fmt(sum(r.sums.kicks, c))],
        ["Засчитано", c => fmt(sum(r.sums.counted, c))], ["Автоблоков P48", c => fmt(sum(r.sums.autoblocks, c))],
        ["Блоков учёток", c => fmt(cnt(c, () => true))], ["Действуют", c => fmt(cnt(c, b => b.state === "active"))],
        ["Из них автоблоков", c => fmt(cnt(c, b => b.origin === "p48" || b.origin === "p69"))]], cats),
      h("h3", null, "Кики не засчитаны — почему"),
      acTable([["Причина (журнал P48)", x => x.reason_db || "—"], ["Киков", x => fmt(x.n)]], r.not_counted),
      blocks.map(([c, bs]) => [h("h3", null, T("Блоки учёток — {0}", T(AB_CAT[c]))),
        acTable([["Учётка", b => acAccount(b.uid, b.login)], ["Причина", b => b.reason], ["Происхождение", b => abLabel(AB_ORIGIN, b.origin)],
          ["Начало", b => dt(b.black)], ["Конец", b => b.perm ? h("span", null, "бессрочно") : dt(b.close)], ["Срок, ч", b => b.hours === null ? "—" : String(b.hours)],
          ["Состояние", b => abLabel(AB_STATE, b.state)], ["Снятие", b => b.lift ? abLabel(AB_LIFT, b.lift) : acText("—")],
          ["Кто снял", b => abWho(b.lift_by)], ["Кто поставил", b => abWho(b.block_by)], ["us_block сейчас", b => fmt(b.us_block_now)]], bs)]),
      h("h3", null, "Засчитанные кики и автоблоки P48"),
      acTable([["Когда", k => dt(k.ev_local)], ["Сервер", k => k.server], ["Учётка", k => acAccount(k.uid, k.login)], ["Персонаж", k => acChar(k.uid, k.slot, k.char)],
        ["Вид", k => k.kind], ["Тип", k => (k.disc_type === null ? "?" : String(k.disc_type)) + " " + (k.disc_type_name || "")],
        ["Счёт", k => (k.kick_count === null ? "?" : k.kick_count) + " / " + (k.kick_threshold === null ? "?" : k.kick_threshold)],
        ["Блок, ч", k => k.block_hours === null ? "—" : String(k.block_hours)], ["2271 отправлен", k => k.autoblock ? fmt(!!k.block_sent) : "—"],
        ["Причина", k => k.reason_text]], r.kicks),
      h("h3", null, "Ступени P69 (ac.other вид 62)"),
      acTable([["Когда", k => dt(k.ev_local)], ["Сервер", k => k.server], ["Учётка", k => acAccount(k.uid, k.login)], ["Ступень", k => String(k.stage)],
        ["Нарушений", k => fmt(k.count)], ["Часы", k => String(k.hours)], ["2271 отправлен", k => fmt(!!k.sent)], ["Подробности", k => k.detail_text]], r.p69),
      h("div", { class: "row" }, h("button", { type: "button", class: "ghost", onclick: () => { location.hash = r.ac_link; } }, "Лента «Античит»")));
  }
  put(hist, h("div", { class: "row" }, h("span", null, "С "), fromIn, h("span", null, "по "), toIn, h("span", null, "Учётка "), accIn, svcSel,
    h("button", { type: "button", onclick: () => loadHist() }, "Показать")), h("div", { class: "muted small" }, "Без дат — последние 30 суток по часам сервера."), hOut);
  loadHist();

  // ---- EAC по учётке
  const uidIn = h("input", { type: "number", min: 1, step: 1, class: "num", placeholder: "номер учётки" });
  const eOut = h("div");
  async function loadEac() {
    if (!uidIn.value) return put(eOut, h("div", { class: "muted" }, "Введите номер учётки."));
    put(eOut, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/autoblock/eac?" + acQs({ uid: uidIn.value })); } catch (e) { if (!stale(my)) put(eOut, errbox(e)); return; }
    if (stale(my)) return;
    const s = r.service, k = (r.summary || {}).kicks || {};
    put(eOut,
      (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      kv([["Учётка", acAccount(r.uid, r.login)], ["Категория", abLabel(AB_CAT, r.cat)],
        ["Блок сейчас", h("span", null, r.block ? (r.block.state === "active" ? T("действует") : r.block.state === "expired" ? T("истёк") : T("нет")) : "?")],
        ["AsdaEacServer", s ? h("span", null, s.running ? T("работает") : T("не запущен"), " · ", T("порты"), " ", acText((s.listening || []).join(", ") || "—"),
          " / ", acText((s.ports || []).join(", ")), " · ", T("старт"), " ", acText(s.start || "—")) : acText("—")],
        ["KICK от сайдкара получено / выполнено / оператору", h("span", null, acText(fmt(k.received) + " / " + fmt(k.done) + " / " + fmt(k.operator)))],
        ["Последний KICK", h("span", null, acText(dt(k.last)))],
        ["Счётчик P48", r.counters.P48 ? h("span", { class: "mono small" }, acText(r.counters.P48.count + " · " + r.counters.P48.first + " → " + (r.counters.P48.window_end || "—")),
          r.counters.P48.expired ? h("span", null, " ", badge(T("окно истекло — счёт сгорит на следующем кике"), "")) : null) : acText("—")],
        ["Счётчик P69: наблюдение (Mode=0)", h("span", { class: "mono small" }, acText(((r.counters.P69 || {}).observe) ? r.counters.P69.observe.count + " · " + r.counters.P69.observe.stage + " · " + r.counters.P69.observe.last : "—"))],
        ["Счётчик P69: боевой (Mode=1)", h("span", { class: "mono small" }, acText(((r.counters.P69 || {}).live) ? r.counters.P69.live.count + " · " + r.counters.P69.live.stage + " · " + r.counters.P69.live.last : "—"))]]),
      h("h3", null, "EAC сейчас (точка статуса службы EAC)"),
      abLive(r.live || {}),
      h("h3", null, "Мост P73 в копиях"),
      acTable([["Копия", x => x[0]], ["Enabled", x => x[1].enabled], ["Mode", x => x[1].mode], ["По журналу патчей", x => abLabel(AB_MODES, x[1].mode_log)]], Object.entries(r.p73)),
      h("h3", null, "Журнал античита учётки"),
      acTable([["Таблица", x => x.table], ["Событий", x => fmt(x.n)], ["Последнее", x => dt(x.last)]], (r.summary || {}).tables || []),
      acTable([["Когда", x => dt(x.ev_local)], ["Таблица", x => x.table], ["Персонаж", x => x.char_name], ["Вид", x => x.kind]], (r.summary || {}).recent || []),
      h("div", { class: "row" }, h("button", { type: "button", class: "ghost", onclick: () => { location.hash = r.account_link; } }, "Карточка учётки"),
        h("button", { type: "button", class: "ghost", onclick: () => { location.hash = r.ac_link; } }, "Лента «Античит»")));
  }
  put(eacBox, h("div", { class: "row" }, h("span", null, "Учётка "), uidIn, h("button", { type: "button", onclick: () => loadEac() }, "Показать")), eOut);
}
