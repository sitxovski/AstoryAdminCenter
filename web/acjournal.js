// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Античит» (шаг А6.1, 21.11.2026; domains/acjournal.py, /api/ac/*). ТОЛЬКО ЧТЕНИЕ.
// Журнал joylog1.ac.* — все 8 таблиц одной лентой по времени: вид текстом, номер и патч по каталогу KindText (AcJournal.cpp,
// ac-journal-p53.md §9); служебные строки (сервер о себе) скрыты, переключатель «служебные» их показывает. Фильтры: учётка (номер или
// логин), персонаж, IP (только с правом players.view_net), таблица, вид, сервер, даты. Сводка: виды за сутки, топ нарушителей за
// 7 суток (ac.v_top_offenders + нарушения без служебных), учётки за сутки (ac.v_account_daily). Переход — в карточку учётки / персонажа.
// Значения из базы (виды, имена, серверы, подробности) — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (acText), без перевода T()
// и без HTML. Общие помощники — из app.js: h(), T(), put(), mount(), shell(), sel(), badge(), errbox(), stale(), api(), pager(), dt().
"use strict";

const acText = s => document.createTextNode(String(s === null || s === undefined || s === "" ? "—" : s));
const acQs = o => Object.entries(o).filter(([, v]) => v !== null && v !== undefined && v !== "").map(([k, v]) => k + "=" + encodeURIComponent(v)).join("&");
const acDay = v => (v || "").replace(/-/g, "");                    // <input type=date> ГГГГ-ММ-ДД → ГГГГММДД (служба принимает только так)
const acNum = v => (v === null || v === undefined) ? "?" : String(v);

// таблица с ячейками-узлами: значение столбца — Node или текст данных (текстовым узлом, без перевода)
function acTable(cols, rows) {
  return h("div", { class: "scroll" }, h("table", null,
    h("thead", null, h("tr", null, cols.map(c => h("th", null, c[0])))),
    h("tbody", null, rows.length ? rows.map(r => h("tr", null, cols.map(c => { const v = c[1](r); return h("td", null, v instanceof Node ? v : acText(v)); })))
      : h("tr", null, h("td", { colspan: cols.length, class: "muted" }, "пусто")))));
}

function acAccount(uid, login) {
  if (uid === null || uid === undefined) return acText("—");
  return h("button", { type: "button", class: "ghost small", title: "карточка учётки", onclick: () => { location.hash = "#/account/" + uid; } },
    acText("№" + uid + (login ? " " + login : "")));
}

function acChar(uid, slot, name) {
  if (!name) return acText("—");
  if (uid === null || uid === undefined || slot === null || slot === undefined) return acText(name);
  return h("button", { type: "button", class: "ghost small", title: "карточка персонажа", onclick: () => { location.hash = "#/char/" + uid + "/" + slot; } },
    acText(name));
}

function acKind(r) {
  return h("span", null, acText(r.kind_text), r.service ? h("span", null, " ", badge(T("служебная"), "")) : null,
    r.hint ? h("div", { class: "muted small" }, acText(r.hint)) : null);
}

function acExtra(x) {
  const parts = Object.entries(x || {}).filter(([, v]) => v !== null && v !== undefined && v !== "").map(([k, v]) => k + "=" + v);
  return h("span", { class: "mono small" }, acText(parts.join(" · ")));
}

async function viewAc(my) {
  const out = h("div"), sumBox = h("div"), feedBox = h("div"), info = h("div", { class: "muted small" });
  mount(shell("#/ac", h("h1", null, "Античит"), h("div", { class: "note" },
    acText(T("Только чтение. Журнал античита joylog1.ac.* — все 8 таблиц одной лентой. Вид — текстом из базы, номер и патч — по каталогу видов серверных патчей. Служебные строки (сервер о себе без учётки: старт и итоги журнала, мост EAC, выключение патча при старте) по умолчанию скрыты."))), out));
  let cat;
  try { cat = await api("/api/ac/catalog"); } catch (e) { put(out, errbox(e)); return; }
  if (stale(my)) return;

  // ---- сводка
  const dayIn = h("input", { type: "date" });
  async function loadSummary() {
    put(sumBox, h("div", { class: "muted" }, "Загружаю…"));
    let s;
    try { s = await api("/api/ac/summary?" + acQs({ day: acDay(dayIn.value) })); } catch (e) { if (!stale(my)) put(sumBox, errbox(e)); return; }
    if (stale(my)) return;
    put(sumBox,
      h("div", { class: "muted small" }, acText(T("Сутки {0}: событий {1}, из них служебных {2}.", s.day, s.kinds_total, s.kinds_service))),
      (s.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      h("h2", null, "Виды за сутки"),
      acTable([["Событий", k => fmt(k.n)], ["Учёток", k => fmt(k.users)], ["Таблица", k => "ac." + k.table], ["№", k => acNum(k.num)],
        ["Патч", k => k.patch || "?"], ["Вид", k => acKind(k)], ["Первое", k => dt(k.first)], ["Последнее", k => dt(k.last)]], s.kinds),
      h("h2", null, "Топ нарушителей за 7 суток"),
      h("div", { class: "muted small" }, acText(T("«Нарушений» — без служебных строк; «всего» — как считает представление ac.v_top_offenders (все строки журнала учётки)."))),
      acTable([["Учётка", r => acAccount(r.user_index, r.login)], ["Нарушений", r => fmt(r.violations)], ["Всего", r => fmt(r.total)],
        ["Кики", r => fmt(r.kicks)], ["Автоблоки", r => fmt(r.autoblocks)], ["Ход и бой", r => fmt(r.move_combat)], ["Прочее", r => fmt(r.other)],
        ["Пакеты", r => fmt(r.packet_validator)], ["Блок сейчас", r => fmt(r.us_block_now)], ["Персонаж", r => r.char_names],
        ["Последнее", r => dt(r.last_local)]], s.top),
      h("h2", null, "Учётки за сутки"),
      acTable([["Учётка", r => acAccount(r.user_index, r.login)], ["Всего", r => fmt(r.total)], ["Кики", r => fmt(r.kicks)],
        ["Автоблоки", r => fmt(r.autoblocks)], ["Ход и бой", r => fmt(r.move_combat)], ["Прочее", r => fmt(r.other)],
        ["Подавлено повторов", r => fmt(r.suppressed_repeats)], ["Первое", r => dt(r.first_local)], ["Последнее", r => dt(r.last_local)]], s.daily));
  }

  // ---- лента
  const accIn = h("input", { type: "text", maxlength: 40, placeholder: "номер или логин", class: "mono" });
  const charIn = h("input", { type: "text", maxlength: 32, placeholder: "имя персонажа" });
  const ipIn = h("input", { type: "text", maxlength: 15, placeholder: cat.can_ip ? "IP" : "IP — нет права players.view_net", class: "mono", disabled: !cat.can_ip });
  const tblSel = sel([["", T("все таблицы")]].concat(cat.tables.map(t => [t.name, "ac." + t.name + " — " + t.title])), "");
  const kindBox = h("span");
  let kindSel = sel([["", T("все виды")]], "");
  const srvSel = h("select", null, h("option", { value: "" }, T("все серверы")), cat.servers.map(s => { const o = h("option", { value: s }); o.append(acText(s)); return o; }));
  const fromIn = h("input", { type: "date" }), toIn = h("input", { type: "date" });
  const svc = h("input", { type: "checkbox" });
  const sizeSel = sel([[25, "25"], [50, "50"], [100, "100"], [200, "200"]], 50);
  const st = { page: 1 };

  function fillKinds() {
    const ts = cat.tables.filter(t => !tblSel.value || t.name === tblSel.value);
    kindSel = h("select", null, h("option", { value: "" }, T("все виды")), ts.map(t => t.kinds.map(k => {
      const o = h("option", { value: t.name + ":" + k.kind_raw });
      o.append(acText((ts.length > 1 ? t.name + " " : "") + k.n + " · " + (k.patch || "?") + " · " + k.kind + (k.service ? " · " + T("служебная") : "")));
      return o;
    })));
    put(kindBox, kindSel);
  }
  tblSel.addEventListener("change", fillKinds);

  async function loadFeed(page) {
    st.page = page || 1;
    put(info, acText(T("Загружаю…")));
    const q = { account: accIn.value.trim(), char: charIn.value.trim(), ip: cat.can_ip ? ipIn.value.trim() : "", table: tblSel.value,
      kind: kindSel.value, server: srvSel.value, from: acDay(fromIn.value), to: acDay(toIn.value), service: svc.checked ? "1" : "",
      page: st.page, size: sizeSel.value };
    let r;
    try { r = await api("/api/ac/events?" + acQs(q)); } catch (e) { if (!stale(my)) { put(info, errbox(e)); put(feedBox); } return; }
    if (stale(my)) return;
    put(info, acText(T("Событий {0} · страница {1} из {2}", fmt(r.total), r.page, r.pages)),
      r.service ? null : badge(T("служебные скрыты"), ""), r.ip_hidden ? badge(T("IP скрыты (нет права players.view_net)"), "") : null,
      r.service_auto ? badge(T("выбран служебный вид — служебные строки показаны"), "") : null,
      r.pages_capped ? badge(T("листается до {0} строк — сузьте фильтр или даты", r.depth_max), "warn") : null);
    put(feedBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      acTable([["Когда", e => dt(e.ev_local)], ["Таблица", e => "ac." + e.table], ["№", e => acNum(e.n)], ["Патч", e => e.patch || "?"],
        ["Сервер", e => e.server], ["Учётка", e => acAccount(e.uid, e.login)], ["Персонаж", e => acChar(e.uid, e.slot, e.char)],
        ["IP", e => r.ip_hidden ? "•••" : e.ip], ["Опкод", e => e.opcode], ["Вид", e => acKind(e)], ["Подробности", e => acExtra(e.extra)],
        // ★ А6.7 (22.11): событие — в дело учётки (раздел «Античит: дела», поле событий карточки дела заполняется)
        ["Дело", e => e.uid !== null && e.uid !== undefined && can("ac.case") ? h("button", { type: "button", class: "ghost small", title: "приложить к делу учётки",
          onclick: () => { location.hash = "#/cases?uid=" + e.uid + "&ev=" + encodeURIComponent(e.table + ":" + e.event_id); } }, "к делу") : acText("")]], r.rows),
      r.pages > 1 ? pager(r.page, r.pages, p => loadFeed(p)) : null);
  }

  put(out,
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Сводка"), h("span", null, "Сутки "), dayIn,
      h("button", { type: "button", onclick: () => loadSummary() }, "Показать"),
      h("button", { type: "button", class: "ghost", onclick: () => { location.hash = "#/acdaily"; } }, "Суточный отчёт")), sumBox),
    h("div", { class: "card" }, h("h2", null, "Лента журнала"),
      h("div", { class: "row" }, h("span", null, "Учётка "), accIn, h("span", null, "Персонаж "), charIn, h("span", null, "IP "), ipIn),
      h("div", { class: "row" }, h("span", null, "Таблица "), tblSel, h("span", null, "Вид "), kindBox, h("span", null, "Сервер "), srvSel),
      h("div", { class: "row" }, h("span", null, "С "), fromIn, h("span", null, "по "), toIn, h("label", null, svc, " служебные строки"),
        h("span", null, "Строк "), sizeSel, h("button", { type: "button", onclick: () => loadFeed(1) }, "Показать")),
      info, feedBox,
      h("div", { class: "muted small" }, acText(T("Каталог видов: {0} (md5 {1}). «?» в номере — текста нет в каталоге (старая сборка патча или вид без текста).", cat.source, cat.md5)))));
  fillKinds();
  loadSummary();
  loadFeed(1);
}
