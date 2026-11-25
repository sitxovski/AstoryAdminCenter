// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Античит: суточный отчёт» (шаг А6.6, 22.11.2026; domains/acdaily.py, /api/acdaily/*). Отчёт считает тот же код
// AstoryServer/Tools/Anticheat/ac_daily_report (без правок): служба сама раз в сутки за вчера, задание или оператор с правом ac.daily_run. Экран
// «за день»: итог по метрикам как в отчёте исходника, флаги вне списка владельца (кандидаты на разбор) и фон владельца (справочно),
// по метрике — источник, формула, статус, заметки, таблицы, последние события и все события (CSV исходника); Markdown исходника — как есть.
// Значения отчёта (ники, логины, IP, виды, подробности) — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (acText), без HTML.
// Помощники — из app.js (h, T, put, mount, shell, badge, errbox, stale, api, pager, dt, fmt, notify, op, confirmWin, can) и acjournal.js
// (acText, acTable, acQs, acDay).
"use strict";

const ADW_WIN = r => r.days === 1 ? r.day_to : r.day_from + "–" + r.day_to;
const ADW_THR = o => Object.keys(o || {}).sort().map(k => k + "=" + o[k]).join(", ");
// ★ ревизия 56 Н-4: сводка хранения adm.AcDaily (служба / вручную: отчётов, объём, самые старые сутки) и сроки процедуры очистки
function ADW_STORE(r) {
  const by = {};
  (r.storage || []).forEach(x => { by[x.kind] = x; });
  const one = k => by[k] ? T("{0} отчётов, {1} МБ, с {2}", fmt(by[k].n), (by[k].bytes / 1048576).toFixed(1), by[k].oldest) : T("нет");
  return h("div", { class: "muted small" }, acText(T("Хранится: служба — {0}; вручную и задания — {1}. Срок: служба {2} суток, вручную {3} суток (очистка — сама служба после ночного прогона).",
    one("sched"), one("manual"), r.keep ? r.keep.sched : "?", r.keep ? r.keep.manual : "?")));
}

async function viewAcDaily(my) {
  const out = h("div"), listBox = h("div"), repBox = h("div");
  mount(shell("#/acdaily", h("h1", null, "Античит: суточный отчёт"), h("div", { class: "note" },
    acText(T("Отчёт считает тот же код, что консольный ac_daily_report (AstoryServer/Tools/Anticheat), без изменений: журналы стойки читаются на сервере, база — логином панели только на чтение. «Вне владельца» и «фон» — по списку ников и логинов владельца исходника (не по номеру учётки). Флаг — повод посмотреть события, а не доказательство."))), out));
  let lst;
  try { lst = await api("/api/acdaily/list"); } catch (e) { put(out, errbox(e)); return; }
  if (stale(my)) return;
  const dayIn = h("input", { type: "date" });

  function listTable(rows) {
    return acTable([["№", r => String(r.id)], ["Сутки", r => ADW_WIN(r)], ["Сформирован (сервер)", r => dt(r.made_local)], ["Кто", r => r.by], ["Путь", r => r.via],
      ["Флагов вне владельца", r => fmt(r.flags_out)], ["Фон владельца", r => fmt(r.flags_bg)], ["С ошибкой", r => fmt(r.errors)], ["Нет данных", r => fmt(r.nodata)],
      ["Журналов", r => fmt(r.log_files)], ["Прогон, с", r => (r.elapsed_ms / 1000).toFixed(1)], ["Пороги", r => r.thr_over && Object.keys(r.thr_over).length ? ADW_THR(r.thr_over) : T("прежние")],
      ["", r => h("button", { type: "button", class: "ghost small", onclick: () => loadReport({ id: r.id }) }, "открыть")]], rows);
  }

  async function loadList() {
    put(listBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/acdaily/list?" + acQs({ day: acDay(dayIn.value) })); } catch (e) { if (!stale(my)) put(listBox, errbox(e)); return; }
    if (stale(my)) return;
    lst = r;
    put(listBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))), h("div", { class: "muted small" }, acText(T("Служба считает отчёт за вчерашние сутки сама в {0} (часы сервера). Вручную — не больше {1} раз в час на пользователя.", r.run_at, r.runs_per_hour))),
      ADW_STORE(r), listTable(r.reports));
  }

  function metricCard(rep, m) {
    const evBox = h("div");
    async function loadEvents(page) {
      put(evBox, h("div", { class: "muted" }, "Загружаю…"));
      let r;
      try { r = await api("/api/acdaily/events?" + acQs({ id: rep.id, metric: m.mid, page: page || 1, size: 100 })); } catch (e) { if (!stale(my)) put(evBox, errbox(e)); return; }
      if (stale(my)) return;
      put(evBox, h("div", { class: "muted small" }, acText(T("Событий {0} · страница {1} из {2}", fmt(r.total), r.page, r.pages))),
        acTable([["Время", e => e[0]], ["Источник", e => e[1]], ["Субъект", e => e[2]], ["Вид", e => e[3]], ["Деталь", e => e[4]], ["Файл", e => e[5]], ["IP", e => e[6]]], r.rows),
        r.pages > 1 ? pager(r.page, r.pages, p => loadEvents(p)) : null);
    }
    const s = m.summary || [];
    return h("details", { class: "card" },
      h("summary", null, h("b", null, acText(m.mid + " — " + m.title)), " ", badge(acText(m.status === "ok" ? s[7] : m.status), m.status === "ошибка" || m.status === "error" ? "bad" : (m.status === "ok" ? "" : "warn"))),
      h("div", { class: "kv" }, h("div", null, "Источник"), h("div", null, acText(m.source)), h("div", null, "Формула / порог"), h("div", null, acText(m.formula))),
      (m.notes || []).map(n => h("div", { class: "muted small" }, acText(n))),
      (m.tables || []).filter(t => t[2] && t[2].length).map(t => h("div", null, h("h3", null, acText(t[0])), acTable(t[1].map((c, i) => [c, r => r[i]]), t[2]))),
      m.last && m.last.length ? h("div", null, h("h3", null, acText(T("Последние события (из {0})", fmt(m.events_total)))),
        acTable([["Время", e => e[0]], ["Источник", e => e[1]], ["Субъект", e => e[2]], ["Вид", e => e[3]], ["Деталь", e => e[4]]], m.last)) : null,
      m.events_total ? h("div", { class: "row" }, h("button", { type: "button", class: "ghost small", onclick: () => loadEvents(1) }, "все события"),
        m.events_total > m.events_kept ? badge(acText(T("сохранены последние {0} из {1}", fmt(m.events_kept), fmt(m.events_total))), "warn") : null) : null,
      evBox);
  }

  async function loadReport(q) {
    put(repBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/acdaily/report?" + acQs(q)); } catch (e) { if (!stale(my)) put(repBox, errbox(e)); return; }
    if (stale(my)) return;
    const mt = r.meta || {};
    const outFlags = [], bg = [];
    r.metrics.forEach(m => {
      const a = (m.flags || []).filter(f => !f[2]);
      if (a.length) outFlags.push([m, a]);
      const b = (m.flags || []).filter(f => f[2]);
      if (b.length) bg.push([m, b.length]);
    });
    const mdBox = h("div");
    async function showMd() {
      let x;
      try { x = await api("/api/acdaily/md?" + acQs({ id: r.id })); } catch (e) { return notify(e.message, true); }
      if (stale(my)) return;
      put(mdBox, h("pre", { class: "mono small scroll" }, acText(x.md)));
    }
    put(repBox,
      h("h2", null, acText(T("Отчёт №{0} за {1}", r.id, ADW_WIN(r)))),
      h("div", { class: "muted small" }, acText(T("Сформирован {0} (часы сервера), {1}, путь {2}, прогон {3} с; журналов {4}, {5} байт; код исходника {6}.",
        dt(r.made_local), r.by, r.via, (r.elapsed_ms / 1000).toFixed(1), fmt(r.log_files), fmt(r.log_bytes), (r.code_md5 || "").slice(0, 8)))),
      r.code_now && r.code_now !== r.code_md5 ? h("div", null, badge(acText(T("сейчас выложен другой код исходника {0}", r.code_now.slice(0, 8))), "warn")) : null,
      h("div", { class: "muted small" }, acText(T("Серверы: {0}; Npc: {1}. Список владельца (regex): {2}", (mt.servers || []).join(", "), (mt.npc || []).join(", "), mt.owner_re))),
      r.thr_over && Object.keys(r.thr_over).length ? h("div", null, badge(acText(T("пороги не прежние: {0}", ADW_THR(r.thr_over))), "warn")) : null,
      mt.otp_missing && mt.otp_missing.length ? h("div", null, badge(acText(T("нет OTP_Report ни в журнале LoginManager, ни в архиве за сутки: {0} — M8 / M12 / M12o без записей входа",
        mt.otp_missing.join(", "))), "warn")) : null,
      r.ip_hidden ? h("div", null, badge(T("IP скрыты (нет права players.view_net)"), "")) : null,
      (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      h("h3", null, "Итог"),
      acTable([["Метрика", m => m.summary[0]], ["Всего", m => m.summary[1]], ["Субъектов", m => m.summary[2]], ["На субъекта (ср. / макс.)", m => m.summary[3]],
        ["Топ-5", m => m.summary[4]], ["Вне владельца", m => m.summary[5]], ["Флагов (вне / фон)", m => m.summary[6]], ["Статус", m => m.summary[7]]], r.metrics),
      h("div", { class: "muted small" }, acText(T("«Вне владельца» — события на никах вне списка владельца; «без ника» — источник ника не даёт (userindex / IP). Флаги «вне» — субъект не из списка владельца или не определён; «фон» — учётки владельца (справочно)."))),
      h("h3", null, "Флаги вне списка владельца (кандидаты на разбор)"),
      outFlags.length ? outFlags.map(([m, a]) => h("div", null, h("b", null, acText(m.mid + " (" + a.length + ")")),
        acTable([["Субъект", f => f[0] || "?"], ["Флаг", f => f[1]]], a))) : h("div", { class: "muted" }, "Нет: на учётках вне списка владельца пороги не превышены."),
      h("h3", null, "Фон владельца (справочно)"),
      bg.length ? acTable([["Метрика", x => x[0].mid], ["Флагов", x => fmt(x[1])], ["По нику", x => (x[0].bg_top || []).map(y => y[0] + ": " + y[1]).join(", ")]], bg)
        : h("div", { class: "muted" }, "Флагов на учётках владельца нет."),
      h("h3", null, "Метрики"),
      r.metrics.map(m => metricCard(r, m)),
      h("div", { class: "row" }, h("button", { type: "button", class: "ghost", onclick: () => showMd() }, "Markdown исходника")), mdBox);
  }

  // ---- прогон вручную (право ac.daily_run)
  const runDate = h("input", { type: "date" }), runDays = h("input", { type: "number", min: 1, max: lst.days_max, value: 1, class: "num" });
  const thrIn = {};
  Object.keys(lst.defaults || {}).sort().forEach(k => { thrIn[k] = h("input", { type: "text", maxlength: 12, class: "mono num", placeholder: String(lst.defaults[k]) }); });
  async function runNow() {
    const thr = {};
    Object.entries(thrIn).forEach(([k, el]) => { if (el.value.trim() !== "") thr[k] = el.value.trim(); });
    const p = { date: acDay(runDate.value), days: runDays.value.trim() || "1", thr };
    if (!p.date) delete p.date;
    let pv;
    try { pv = await op("ac.daily", p, true); } catch (e) { return notify(e.message, true); }
    if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(pv.preview.text)), (pv.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
    try {
      const res = await op("ac.daily", p, false);
      notify(T(res.message || "готово"));
      await loadList();
      if (res.result && res.result.id) loadReport({ id: res.result.id });
    } catch (e) { notify(e.message, true); }
  }
  const runCard = lst.can_run ? h("details", { class: "card" }, h("summary", null, h("b", null, "Посчитать отчёт сейчас")),
    h("div", { class: "muted small" }, acText(T("Без даты — вчерашние сутки по часам сервера. Пустой порог — прежнее значение исходника (подсказка в поле)."))),
    h("div", { class: "row" }, h("span", null, "Последние сутки "), runDate, h("span", null, "Суток в окне "), runDays),
    h("div", { class: "kv" }, Object.keys(thrIn).map(k => [h("div", { class: "mono" }, acText(k)), h("div", null, thrIn[k])])),
    h("div", { class: "row" }, h("button", { type: "button", class: "gold", onclick: () => runNow() }, "Посчитать"))) : null;

  put(out,
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Прогоны"), h("span", null, "Сутки "), dayIn,
      h("button", { type: "button", onclick: () => loadList() }, "Показать"),
      h("button", { type: "button", onclick: () => loadReport({ day: acDay(dayIn.value) }) }, "Отчёт за сутки"),
      h("button", { type: "button", class: "ghost", onclick: () => { location.hash = "#/ac"; } }, "Журнал античита")), listBox),
    runCard,
    h("div", { class: "card" }, repBox));
  loadList();
  if (lst.reports.length) loadReport({ id: lst.reports[0].id }); else put(repBox, h("div", { class: "muted" }, acText(T("Отчётов ещё нет: служба посчитает первый в {0}.", lst.run_at))));
}
