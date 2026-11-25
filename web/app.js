// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр Astory — интерфейс панели (без библиотек). 16.11.2026.
// Всё рисуется через h() + textContent (никакого innerHTML с данными — защита от XSS); маршруты — по #хэшу.
// Данные — только через /api/* той же службы; изменяющие запросы несут X-Asda-Csrf.
// ЯЗЫК (владелец 16.11: «переключатель RU / EN»): надписи — словарь web/i18n.js (T(), h() переводит статические строки
// сам); названия из справочников (профессии, карты, навыки, предметы) и сообщения службы приходят на выбранном языке по
// заголовку X-Asda-Lang. Выбор хранится в браузере (localStorage, с запасным вариантом «ru», если хранилище недоступно).
"use strict";

const S = { me: null, csrf: "", groups: null, skin: null, invPlate: 1, lang: "ru", nav: 0, opDoc: null };   // состояние сессии (opDoc — справка последнего предпросмотра, А7.10)
// nav — номер перехода: ответ, пришедший после ухода на другой раздел, ничего не рисует (иначе медленное «Состояние»
// затирало уже открытый раздел — «вкладки не переключаются»). stale(n) — переход n устарел.
const stale = n => n !== S.nav;
try { S.lang = localStorage.getItem("asda.lang") === "en" ? "en" : "ru"; } catch (e) { S.lang = "ru"; }

// ---------- перевод ----------
function T(s, ...args) {
  let out = (S.lang === "en" && typeof I18N_EN !== "undefined" && I18N_EN[s] !== undefined) ? I18N_EN[s] : s;
  args.forEach((a, i) => { out = out.split("{" + i + "}").join(a === null || a === undefined ? "—" : String(a)); });
  return out;
}
function setLang(l) {
  S.lang = l;
  try { localStorage.setItem("asda.lang", l); } catch (e) { /* без хранилища — до перезагрузки */ }
  document.documentElement.lang = l;
  S.groups = null;
  render();
}
function langToggle() {
  return h("div", { class: "lang" },
    h("button", { type: "button", class: "ghost" + (S.lang === "ru" ? " on" : ""), onclick: () => setLang("ru") }, "RU"),
    h("button", { type: "button", class: "ghost" + (S.lang === "en" ? " on" : ""), onclick: () => setLang("en") }, "EN"));
}

// ---------- DOM ----------
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style") Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? "" : ((k === "placeholder" || k === "title") ? T(String(v)) : v));
  }
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    el.append(k instanceof Node ? k : document.createTextNode(typeof k === "string" ? T(k) : String(k)));
  }
  return el;
}
const $app = () => document.getElementById("app");
// Заменить содержимое: массивы раскрываются, null/false пропускаются (иначе массив превратился бы в строку).
function put(el, ...kids) { el.replaceChildren(...kids.flat(Infinity).filter(k => k !== null && k !== undefined && k !== false)); }
function mount(...nodes) { put($app(), ...nodes); }
function fmt(v) {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return T(v ? "да" : "нет");
  if (typeof v === "number") return v.toLocaleString(S.lang === "en" ? "en-US" : "ru-RU");
  return String(v);
}
function dt(v) { return v ? String(v).replace("T", " ").slice(0, 19) : "—"; }
function badge(text, kind) { return h("span", { class: "badge " + (kind || "") }, text); }
function kv(pairs) { return h("div", { class: "kv" }, pairs.map(([k, v]) => [h("div", null, k), h("div", null, v instanceof Node ? v : fmt(v))])); }
function table(cols, rows, onclick) {
  return h("div", { class: "scroll" }, h("table", null,
    h("thead", null, h("tr", null, cols.map(c => h("th", null, c[0])))),
    h("tbody", null, rows.length ? rows.map(r => h("tr", { class: onclick ? "click" : "", onclick: onclick ? () => onclick(r) : null },
      cols.map(c => { const v = c[1](r); return h("td", null, v instanceof Node || Array.isArray(v) ? v : fmt(v)); })))
      : h("tr", null, h("td", { colspan: cols.length, class: "muted" }, "пусто")))));
}
function errbox(e) { return h("div", { class: "err" }, String(e && e.message || e)); }
// Листалка страниц (как в окнах магазинов игры: «⏮ ◀ 1 / 6 ▶ ⏭»)
function pager(page, pages, go) {
  const b = (txt, to, dis) => h("button", { type: "button", class: "ghost", disabled: dis, onclick: () => go(to) }, txt);
  return h("div", { class: "pager" }, b("⏮", 1, page <= 1), b("◀", page - 1, page <= 1),
    h("span", { class: "pg" }, page + " / " + pages), b("▶", page + 1, page >= pages), b("⏭", pages, page >= pages));
}
// Окно-подтверждение в виде всплывающего окна игры. → Promise<bool>
// doc — справка операции (core/opdoc) для блока «Что изменится / Перезапуск / Откат»: объект — показать её, null — без блока, не задан — справка
// предпросмотра, который только что пришёл (takeOpDoc).
function confirmWin(title, body, okText, doc) {
  doc = doc !== undefined ? doc : takeOpDoc();     // ★ А7.10, ревизия 85 М-10
  return new Promise(resolve => {
    const close = (v) => { ov.remove(); resolve(v); };
    const ov = h("div", { class: "modal" }, h("div", { class: "modal-in" }, win(title, "systme", [body, doc ? opDocBlock(doc) : null,
      h("div", { class: "row end" }, h("button", { type: "button", class: "ok", onclick: () => close(true) }, okText || "Выполнить"),
        h("button", { type: "button", onclick: () => close(false) }, "Отмена"))], null, { fn: () => close(false), title: "закрыть" })));
    document.body.append(ov);
    ov.querySelector("button.ok").focus();
  });
}
// ★ А7.10 (24.11): справка операции (core/opdoc.py). Служба прикладывает её к каждому предпросмотру (/api/ops, dry) — op() кладёт её в S.opDoc
// с номером предпросмотра, и окно подтверждения этого предпросмотра показывает блок; поэтому блок есть у ЛЮБОЙ операции без правки её окна.
// ★ ревизия 85 М-10: без таймера — справка принадлежит только окну, открытому сразу за своим предпросмотром: любое другое обращение к службе
// (api), сообщение (notify) или переход (render) её сбрасывает, а окно, которому справка известна, получает её явно (параметр doc).
const docText = s => document.createTextNode(String(s === null || s === undefined || s === "" ? "—" : s));   // текст службы — узлом, без T() и HTML
// Забрать справку последнего предпросмотра (один раз) → справка или null
function takeOpDoc() {
  const d = S.opDoc;
  S.opDoc = null;
  return d ? d.doc : null;
}
// Справка одной операции для окон без предпросмотра (/api/opdoc/one: «о себе», откат из журнала) → справка или null (нет права — без блока)
async function fetchOpDoc(name) {
  try { return (await api("/api/opdoc/one?name=" + encodeURIComponent(name))).doc || null; } catch (e) { return null; }
}
// Блок «Что изменится / Перезапуск / Откат» (окно подтверждения и страница «Справка»): подписи кодов — бейджами, подробности — текстом службы
function opDocBlock(d) {
  if (!d || !d.writes) return null;             // ★ ревизия 85 М-8: без права на операцию подробностей нет
  const tag = (label, kind) => h("span", { class: "badge " + (kind || "") }, docText(label));
  const wk = c => (c === "discord" || c === "telegram" || c === "stack") ? "warn" : (c === "none" ? "ok" : "");
  const rk = d.restart.code === "none" ? "ok" : "warn";
  const uk = { journal: "ok", inverse: "", irreversible: "bad", nothing: "ok" }[d.undo.code] || "";
  const line = (head, tags, text) => h("div", { class: "opdoc-line" }, h("b", null, head), " ", tags, h("div", { class: "muted small" }, docText(text)));
  return h("div", { class: "opdoc" },
    line(T("Что изменится"), d.writes.codes.map((c, i) => tag(d.writes.labels[i], wk(c))), d.writes.info),
    line(T("Перезапуск"), tag(d.restart.label, rk), d.restart.info),
    line(T("Откат"), [tag(d.undo.label, uk), (d.undo.inverse || []).map(n => h("span", { class: "mono small" }, docText(" " + n)))], d.undo.info),
    d.job ? line(T("Задание"), tag(T("в назначенное время"), "warn"), d.job.info) : null);   // ★ ревизия 85 В-6: справка планируемой операции у job.add
}
function notify(text, bad) {
  S.opDoc = null;                               // ★ ревизия 85 М-10: поток предпросмотра закончился сообщением — окна для его справки не будет
  const n = h("div", { class: "toast" + (bad ? " bad" : "") }, text);
  document.body.append(n);
  setTimeout(() => n.remove(), bad ? 7000 : 3500);
}

// ---------- API ----------
async function api(path, body) {
  S.opDoc = null;                               // ★ ревизия 85 М-10: справка предпросмотра — только для окна, открытого сразу за ним
  const opt = { method: body === undefined ? "GET" : "POST", headers: { "X-Asda-Lang": S.lang }, credentials: "same-origin" };
  if (body !== undefined) {
    opt.headers["Content-Type"] = "application/json";
    opt.headers["X-Asda-Csrf"] = path === "/api/login" ? "login" : S.csrf;
    opt.body = JSON.stringify(body);
  }
  const r = await fetch(path, opt);
  let j = null;
  try { j = await r.json(); } catch (e) { throw new Error(T("ответ службы не JSON ({0})", r.status)); }
  // 401: сессия кончилась. Для /api/me — просто отказ (его зовёт render(); перерисовка отсюда давала вечный цикл
  // «render → /api/me → 401 → render» и стирала форму входа — ревизия А0 №1). Для остальных — один переход ко входу.
  if (r.status === 401 && path !== "/api/login") {
    if (path !== "/api/me" && S.me) { S.me = null; setTimeout(render, 0); }
    throw new Error(T("нужно войти"));
  }
  if (!r.ok) throw new Error(j && j.error || T("ошибка {0}", r.status));
  return j;
}
const can = p => S.me && S.me.perms.includes(p);
async function loadSkin() {
  if (S.skin) return;
  try { S.skin = await (await fetch("/skin/skin.json", { credentials: "same-origin" })).json(); } catch (e) { S.skin = {}; }
}

// ---------- иконка предмета ----------
function icon(ic, small) {
  const size = small ? 22 : 32;                    // 32 — родной размер иконки в ячейке Slot_Base клиента
  if (!ic) return h("div", { class: small ? "icon sm" : "noicon" }, small ? "" : "?");
  const el = h("div", { class: "icon" + (small ? " sm" : "") });
  const k = size / ic.size;
  el.style.backgroundImage = "url(/ref/atlas/" + encodeURIComponent(ic.atlas) + ".png)";
  if (ic.whole) { el.style.backgroundSize = size + "px " + size + "px"; }
  else {
    el.style.backgroundSize = (ic.w * k) + "px " + (ic.h * k) + "px";
    el.style.backgroundPosition = (-ic.x * k) + "px " + (-ic.y * k) + "px";
  }
  return el;
}
const iname = it => (S.lang === "en" ? (it.name_en || it.name) : (it.name || it.name_en)) || T("(нет названия)");
function itemLine(code, name, ic) {
  // ★ ревизия 36 К-3: название предмета — данные, не текст интерфейса: узлом текста мимо T() (совпадение с ключом словаря не переведётся)
  return h("span", { class: "itemline" }, icon(ic, true), h("span", null, name ? document.createTextNode(String(name)) : T("(нет названия)")),
    h("span", { class: "muted mono" }, code));
}

// ---------- окно игры ----------
// Каркас окна клиента (окно «Рюкзак»): Win_Mg + полоса заголовка WinMd_* + значок WinIcon_* + шестерёнка Gear_50.
// title — надпись в полосе (белая с обводкой), icon — суффикс WinIcon_* (inven, systme, quest…), tools — узлы справа
// в полосе, onclose — крестик CloseBtn_18.
function win(title, icon, body, tools, onclose) {
  return h("section", { class: "win" },
    h("div", { class: "gear" }),
    h("div", { class: "wt" }, h("i", { class: "wi " + (icon || "systme") }),
      // заголовок и сразу за ним значки/кнопки (владелец 17.11: «кнопки и метки — слева, сразу за названием»)
      h("div", { class: "whead" }, h("span", { class: "wtitle" }, title),
        tools && tools.length ? h("div", { class: "wtools" }, tools) : null)),
    onclose ? h("button", { class: "wclose", type: "button", title: onclose.title || "закрыть", onclick: onclose.fn }) : null,
    h("div", { class: "wb" }, body));
}

// ---------- каркас ----------
// [адрес, подпись, право, значок раздела WinIcon_*]
const NAV = [
  ["#/status", "Состояние", "status.view", "systme"],
  ["#/players", "Игроки", "players.view", "myinfo"],
  ["#/online", "Кто в игре", "players.view", "comm"],                      // ★ А5.2 (21.11): по данным моста P127
  ["#/trace", "След предмета", "players.view", "inven"],
  ["#/dupes", "Поиск дюпов", "players.view", "inven"],
  ["#/shops", "Данные игры: магазины", "shop.view", "inven"],                 // А3 19.11: «Данные игры → Магазины» (web/shops.js)
  ["#/logs", "Журналы стойки", "logs.view", "quest"],                       // ★ А5.6 (21.11): хвост серверных журналов (web/logs.js)
  ["#/ac", "Античит", "ac.view", "systme"],                                // ★ А6.1 (21.11): журнал joylog1.ac.* и сводки (web/acjournal.js)
  ["#/acdaily", "Античит: суточный отчёт", "ac.view", "quest"],           // ★ А6.6 (22.11): отчёт ac_daily_report за день — флаги вне владельца / фон (web/acdaily.js)
  ["#/autoblock", "Античит: автоблок и EAC", "ac.view", "systme"],        // ★ А6.8 (22.11): лестница против patches.ini, история автоблоков, EAC по учётке (web/autoblock.js)
  ["#/cases", "Античит: дела", "ac.view", "quest"],                         // ★ А6.7 (22.11): дела AC-NNNN san.* — код ac_case.py, блок account.block (web/cases.js)
  ["#/names", "Очередь имён", "names.review", "myinfo"],                  // ★ А6.11 (22.11): новые и сменённые имена, правила A13, отметка «ок / сменить» (web/names.js)
  ["#/reports", "Жалобы игроков", "reports.view", "comm"],                // ★ А6.11 (22.11, решение №6): жалобы из бота Discord — очередь, разбор, дело, ответ автору (web/reports.js)
  ["#/chat", "Журнал чата", "chat.view", "comm"],                         // ★ А6.12 (22.11, решение №5): журнал чата P129 и заглушки (web/chat.js)
  ["#/attendance", "Посещаемость", "attendance.view", "quest"],          // ★ А6.10 (23.11, решение владельца 23.11): счёт и дни посещаемости, засчитать / снять прошедший день (web/attendance.js)
  ["#/releases", "Выпуски", "releases.view", "systme"],                  // ★ А7.1 (23.11, решение владельца А7 №6 — только статус): каналы, срок подписи, снимок ПК (web/releases.js)
  ["#/crashes", "Сбои клиента", "crash.view", "systme"],                // ★ А7.2 (23.11, решения владельца А7 №1, №8): места падения, частота, версии, квота LogDrop (web/crashes.js)
  ["#/outbox", "Очередь Discord", "outbox.view", "comm"],              // ★ А7.4 (23.11, решение владельца А7 №2): объявления в Discord — статус, ошибки, повтор, отмена, удаление (web/outbox.js)
  ["#/notes", "Заметки к выпуску", "notes.view", "comm"],             // ★ А7.7 (24.11, решение владельца А7 №7): черновик заметок для игроков из changelog и публикация в форум updates (web/notes.js)
  ["#/community", "Сообщество", "community.view", "comm"],            // ★ А7.6 (24.11, решение владельца А7 №9): заявки, тестеры, предупреждения, баны Discord, команды боту (web/community.js)
  ["#/telegram", "Telegram владельцу", "notify.view", "comm"],         // ★ А7.5 (23.11, решение владельца А7 №3): уведомления владельцу — выключатели, события, проверка, очередь (web/telegram.js)
  ["#/money", "Деньги", "money.view", "premiumstore"],                    // ★ А6.2 (21.11): монетизация gp7, только чтение (web/money.js)
  ["#/econ", "Экономика: золото", "econ.view", "itemexchange"],          // ★ А6.3 (21.11): потоки золота, богатейшие, редкое, снимки (web/econ.js)
  ["#/trade", "Передачи и рынок", "econ.view", "trade"],                   // ★ А6.4 (22.11): кто кому, пары M3, аукцион, лавки (web/trade.js)
  ["#/odds", "Шансы: выпало против заявленного", "econ.view", "itemstrength"],   // ★ А6.5 (22.11): заточка, бустеры, коробки gp7 (web/odds.js)
  ["#/audit", "Журнал действий", "audit.view", "quest"],
  ["#/help", "Справка", "status.view", "quest"],                         // ★ А7.10 (24.11): справка по каждой операции — что меняет, перезапуск, откат, права (web/help.js)
  ["#/users", "Пользователи панели", "users.manage", "comm"],
  ["#/me", "О себе", "self.manage", "title"],
];
// Заголовок раздела (первый h1 содержимого) переезжает в полосу заголовка окна; остальное из его строки
// (кнопка «Обновить», метки) — в правую часть полосы. Карточкам с h2 первой строкой — место под вкладку-заголовок.
function shell(active, ...content) {
  const u = S.me.user;
  const nav = NAV.find(n => n[0] === active) || NAV[0];
  const body = h("div", null, content);
  let title = T(nav[1]), tools = [];
  const h1 = body.querySelector("h1");
  if (h1) {
    title = h1.textContent;
    const row = h1.parentElement;
    h1.remove();
    if (row !== body && row.classList.contains("row") && row.parentElement === body) {
      tools = [...row.childNodes];
      row.remove();
    }
  }
  body.querySelectorAll(".card > h2:first-child").forEach(x => x.parentElement.classList.add("headed"));
  const logout = async () => { try { await api("/api/logout", {}); } catch (e) {} S.me = null; render(); };
  return h("div", { class: "layout" },
    h("nav", { class: "side" }, win(T("Админ-центр"), "systme", [
      NAV.filter(n => can(n[2])).map(n => {
        const locked = S.me.need_totp_setup && n[0] !== "#/me";        // закрыто до включения второго фактора
        return h("a", { href: n[0], class: "navbtn" + (active === n[0] ? " on" : "") + (locked ? " locked" : ""),
          title: locked ? "откроется после включения второго фактора" : null },
          h("i", { class: "wi " + n[3] }), n[1], locked ? h("span", { class: "lock" }, "🔒") : null);
      }),
      h("div", { class: "who" }, u.login + " · " + T(S.me.role_title), h("br"), h("a", { onclick: logout }, "выйти"), langToggle())],
      null, { fn: () => { if (confirm(T("Выйти из панели?"))) logout(); }, title: "выйти" })),
    h("main", { class: "main" }, win(title, nav[3], body, tools)));
}

// ---------- вход ----------
// Код второго фактора вводится сразу вместе с паролем (ревизия 16.11 вечер В2: отдельный шаг «нужен код» выдавал,
// что пароль верен). Снаружи VPN войти можно только со включённым вторым фактором.
function viewLogin(msg) {
  const login = h("input", { autocomplete: "username" });
  const pw = h("input", { type: "password", autocomplete: "current-password" });
  const code = h("input", { inputmode: "numeric", autocomplete: "one-time-code", maxlength: 6, placeholder: "6 цифр, если второй фактор включён" });
  const err = h("div", { class: "err" }, msg || "");
  const go = async (ev) => {
    ev.preventDefault();
    err.textContent = "";
    try {
      const r = await api("/api/login", { login: login.value, password: pw.value, totp_code: code.value.trim() });
      S.csrf = r.csrf;
      await loadMe();
      if (!location.hash || location.hash === "#/") location.hash = S.me.need_totp_setup ? "#/me" : "#/status";
      render();
    } catch (e) { err.textContent = e.message; }
  };
  mount(h("div", { class: "login" }, win(T("Админ-центр Astory"), "systme", h("form", { onsubmit: go },
    h("label", null, "Логин"), login, h("label", null, "Пароль"), pw,
    h("label", null, "Код из приложения-аутентификатора"), code,
    h("div", { class: "muted small" }, "Вход не из VPN — только со включённым вторым фактором."),
    err, h("div", { class: "row" }, langToggle(), h("div", { class: "grow" }), h("button", { type: "submit", class: "gold" }, "Войти"))))));
  login.focus();
}
async function loadMe() {
  try { S.me = await api("/api/me"); S.csrf = S.me.csrf; } catch (e) { S.me = null; }
}

// ---------- Состояние ----------
async function viewStatus(force) {
  const my = S.nav;
  mount(shell("#/status", h("h1", null, "Состояние"), h("div", { class: "muted" }, "Снимаю состояние сервера…")));
  let s;
  try { s = await api("/api/status" + (force ? "?force=1" : "")); } catch (e) { return stale(my) ? null : mount(shell("#/status", h("h1", null, "Состояние"), errbox(e))); }
  if (stale(my)) return;
  const m = s.machine;
  const sum = s.summary;
  const gb = b => T("{0} ГБ", (b / 1073741824).toFixed(1));
  const pl = s.players;
  mount(shell("#/status",
    h("div", { class: "row" }, h("h1", { class: "grow" }, "Состояние"),
      h("span", { class: "muted small" }, T("снимок {0}", s.at)), h("button", { class: "ghost", onclick: () => viewStatus(true) }, "Обновить")),
    s.host_error ? h("div", { class: "err" }, s.host_error) : null,
    h("div", { class: "grid2" },
      h("div", { class: "card" }, h("h2", null, "Стойка"),
        kv([["Процессов работает", T("{0} из {1}", sum.running, sum.total)], ["Порты в порядке", T("{0} из {1}", sum.ports_ok, sum.total)],
            ["GameServer запущен", dt(pl.gs_start)]])),
      m ? h("div", { class: "card" }, h("h2", null, T("Машина {0}", m.host)),
        kv([["Загрузка ЦП", m.cpu + " %"], ["Память свободна", T("{0} из {1}", gb(m.memfree), gb(m.memtotal))],
            ["Включена с", m.boot], ...(m.disks || []).map(d => [T("Диск {0}", d.dev), T("{0} свободно из {1}", gb(d.free), gb(d.size))])])) : null,
      h("div", { class: "card" }, h("h2", null, "Игроки"),
        kv([["В игре (по БД)", pl.online_db], ["Входов за сутки", pl.logins_24h ? pl.logins_24h.n : null],
            ["Разных учёток за сутки", pl.logins_24h ? pl.logins_24h.u : null]]),
        h("div", { class: "muted small" }, "«В игре» — признак в БД; после аварийной остановки сервера он залипает. Строки старше старта GameServer — подозрительны."),
        pl.error ? h("div", { class: "err" }, pl.error) : null),
      // ★ А6.11 ревизия 67 С-2: база панели AsdaAdmin — размер против потолка SQL Express и доля скриншотов жалоб
      s.admin_db ? h("div", { class: "card" }, h("h2", null, "База панели"),
        s.admin_db.error ? h("div", { class: "err" }, s.admin_db.error) : [
          kv([["Размер AsdaAdmin", T("{0} МБ из {1} ГБ", s.admin_db.db_mb, s.admin_db.limit_gb)],
              ["Скриншоты жалоб", T("{0} МБ ({1} %), файлов {2}, удалено по сроку {3}", s.admin_db.shots_mb, s.admin_db.shots_share, s.admin_db.shots_n, s.admin_db.shots_purged)]]),
          s.admin_db.warn ? h("div", { class: "err" }, T("База панели больше {0} ГБ — до потолка SQL Express {1} ГБ мало места: запись журнала действий остановится.", s.admin_db.warn_gb, s.admin_db.limit_gb)) : null,
          h("div", { class: "muted small" }, T("Байты скриншотов закрытых жалоб удаляются через {0} суток после закрытия (задача службы раз в сутки).", s.admin_db.retention_days))]) : null),
    h("div", { class: "card" }, h("h2", null, "Процессы"),
      table([["", r => r.ports_ok ? badge("работает", "ok") : r.running ? badge("порты?", "warn") : badge("нет", "bad")],
             ["Процесс", r => T(r.title)], ["PID", r => r.pids.join(", ")], ["Запущен", r => r.start],
             ["Память", r => r.mem ? T("{0} МБ", (r.mem / 1048576).toFixed(0)) : "—"],
             ["Порты (слушает / нужно)", r => (r.listening.join(", ") || "—") + " / " + r.ports.join(", ")]], s.stack)),
    maintCard(),
    eventsCard(),
    can("jobs.view") ? jobsCard() : null,
    can("db.view") ? dbCard() : null,
    can("db.view") ? bakCard() : null,
    pl.online_list && pl.online_list.length ? h("div", { class: "card" }, h("h2", null, "В игре по БД"),
      table([["Персонаж", r => r.Charname], ["Ур.", r => r.Lvl], ["Карта", r => r.Poridx], ["Канал", r => r.Channel],
             ["Последняя запись", r => dt(r.LastDate)],
             ["", r => pl.gs_start && dt(r.LastDate) < pl.gs_start ? badge("до старта GS", "warn") : ""]],
        pl.online_list, r => { location.hash = "#/char/" + r.Userindex + "/" + r.Charidx; })) : null));
}

// ---------- А5.3: режим обслуживания (вход только служебным учёткам 1…5000; SQL L09 + LoginPatch L09) ----------
// Состояние — /api/maint (SQL-часть, режим, счётчики, DLL по журналу патчей, кто в игре по мосту). Включение — объявление в игру
// ДО включения (или явно «без объявления»), подтверждение, свежий код второго фактора; уже вошедших отключает только явная галочка.
// По расписанию — карточка «Задания и стойка» (операции maint.on / maint.off). Все тексты — только текстовыми узлами (без innerHTML).
function maintCard() {
  const out = h("div", { class: "muted" }, "Загружаю…");
  const yn = (v, yes, no) => v === null || v === undefined ? badge(T("не прочитано"), "warn") : v ? badge(T(yes), "ok") : badge(T(no), "bad");
  const load = async (force) => {
    let r;
    try { r = await api("/api/maint" + (force ? "?force=1" : "")); } catch (e) { return put(out, errbox(e)); }
    const q = r.sql, d = r.dll, p = r.players;
    // ★ ревизия 43 (мелочь 4): режим считается только при таблице И врезке; таблица без врезки — режим не действует, что бы ни стояло в Mode
    const mode = !q.read || !q.table || !q.gate ? null : q.mode === 1;
    const modeCell = !q.read || !q.table ? "—" : q.gate === null ? badge(T("не прочитано"), "warn")
      : !q.gate ? badge(T("не действует (врезки нет)"), "warn") : mode ? badge(T("ВКЛЮЧЁН"), "bad") : badge(T("выключен"), "ok");
    put(out,
      q.read ? null : h("div", { class: "err" }, T("состояние входа не прочитано: {0}", q.error)),
      kv([["SQL L09 (таблица и врезка в UPUserLogin)", q.read ? h("span", null, yn(q.table, "таблица есть", "таблицы нет"), " ",
              yn(q.gate, "врезка есть", "врезки нет")) : badge(T("не прочитано"), "warn")],
          ["Режим обслуживания", modeCell],
          ["Сменён", q.changed_at ? T("{0}, {1}", dt(q.changed_at), q.changed_by || "—") : "—"],
          ["Причина", q.reason || "—"],
          ["Отказано входов / допущено служебных", q.table ? T("{0} / {1}", q.refused, q.admitted) : "—"],
          ["Отказано входов в мир с выбора персонажа", q.table ? q.world_refused : "—"],
          ["DLL L09 (текст отказа)", !d.read || d.active === null ? h("span", null, badge(T("не прочитано"), "warn"), " ", d.error || "")
              : d.active ? badge(T("действует: «Идут профилактические работы на сервере»"), "ok")
              : badge(T("не действует: игрок увидит «ошибка входа 28»"), "warn")],
          // ★ ревизия 43б Н-4: «закрыт» — только когда сходится всё (сервер: maint.world_state); Н-3 — сбои гейта отдельной строкой
          ["Вход в мир с выбора персонажа", !r.world ? "—" : r.world.closed === true ? badge(T("закрыт (гейт L09)"), "ok")
              : h("span", null, badge(T(r.world.closed === false ? "НЕ закрыт" : "неизвестно"), "warn"), " ", r.world.text)],
          ["Сбои гейта входа в мир", !r.world || !r.world.note ? (d.read && d.active ? T("нет") : "—")
              : h("span", null, badge(T(d.gate_fail_now ? "сейчас НЕ работает" : "были"), d.gate_fail_now ? "bad" : "warn"), " ", r.world.note)],
          ["LoginPatch.dll на стойке", d.read ? T("{0}{1}, LoginManager с {2}", d.dll_md5, d.dll_known ? T(" (сборка L09)") : "", d.lm_start || "—") : "—"],
          ["В игре по мосту вне 1…5000 / служебных", p.bridge_read ? T("{0} / {1}", p.players.length, p.operators.length)
              : h("span", null, badge(T("не прочитано"), "warn"), " ", p.bridge_error || "")],
          ["Вошли по БД вне 1…5000", p.db_read ? p.db_logged : "—"],
          ["CharGmInfo у учёток вне 1…5000 (не пускаются)", p.db_read ? (p.gm_outside.join(", ") || T("нет")) : "—"]]),
      h("div", { class: "muted small" }, T("Вход только служебным учёткам 1…5000. Кто уже на игровом сервере — играет дальше, пока его не отключат; вход в мир с выбора персонажа закрывает только DLL L09 (её гейт при сбое запроса пропускает вход — это видно строкой «Сбои гейта входа в мир»).")),
      r.ready && can("server.maintenance") ? maintForm(mode, () => load(true)) : null,
      !r.ready && q.read ? h("div", { class: "note" }, T("SQL-часть L09 не применена — включить режим нельзя (применение — по слову владельца).")) : null);
  };
  load(false);
  return h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { class: "grow" }, "Режим обслуживания"),
    h("button", { type: "button", class: "ghost", onclick: () => load(true) }, "Обновить")), out);
}
function maintForm(on, reload) {
  const name = on ? "maint.off" : "maint.on";
  const text = h("input", { type: "text", maxlength: 95, placeholder: "текст объявления в игру (до 95 символов)", class: "grow" });
  const silent = h("input", { type: "checkbox", class: "chk" });
  const kick = h("input", { type: "checkbox", class: "chk" });
  const partial = h("input", { type: "checkbox", class: "chk" });
  const reason = h("input", { type: "text", maxlength: 200, placeholder: "причина (для журнала)" });
  const conf = h("input", { type: "checkbox", class: "chk" });
  const code = h("input", { type: "text", maxlength: 6, placeholder: "свежий код второго фактора (не тот, которым входили)", autocomplete: "one-time-code" });
  const err = h("div", { class: "err" });
  const params = () => {
    const x = { confirm: conf.checked ? "maint" : "", announce: text.value.trim(), reason: reason.value.trim() };
    if (!on && silent.checked) x.silent = "silent";
    if (!on && kick.checked) x.kick = "players";
    if (!on && partial.checked) x.partial = "partial";
    return x;
  };
  const go = async (ev) => {
    ev.preventDefault();
    err.textContent = "";
    let p;
    try { p = await op(name, params(), true); } catch (e) { err.textContent = e.message; return; }
    if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
      (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
    const x = Object.assign(params(), on ? {} : { totp: code.value.trim() });
    try { const res = await op(name, x, false); notify(T(res.message)); code.value = ""; reload(); } catch (e) { err.textContent = e.message; }
  };
  return h("form", { class: "row card", onsubmit: go }, text,
    on ? null : h("label", { class: "row chkl" }, silent, "без объявления"),
    on ? null : h("label", { class: "row chkl" }, kick, "отключить игроков вне 1…5000"),
    on ? null : h("label", { class: "row chkl" }, partial, "включить, даже если объявление дошло не до всех узлов"),
    reason, h("label", { class: "row chkl" }, conf, on ? "подтверждаю выключение" : "подтверждаю: вход только служебным учёткам"),
    on ? null : code, h("button", { type: "submit", class: on ? "" : "gold" }, on ? "Выключить режим" : "Включить режим"), err);
}

// ---------- А5.4: события опыта/добычи (6038/6040), счастливые часы, рейтинги (6020), ежедневные задания доски ----------
// Состояние — /api/events?daily=1 (Event.dat всех NpcServer, GameServerEvent.txt ×3 GS, предупреждения, журнал сброса ежедневных).
// Событие / выключение / рейтинги — мостом v84 от персонажа служебной учётки ≤ 5000 с GM-флагом в игре (сток требует оператора);
// сейчас или заданием службы (job.add). Счастливые часы правятся набором изменений (область «Счастливые часы») — здесь только показ.
// Все тексты — только текстовыми узлами (без innerHTML).
const EV_PHASE = { active: ["идёт", "ok"], ahead: ["впереди", "warn"], past: ["прошло — повторится через год", "bad"],
  never: ["не сработает никогда", "bad"] };
function eventsCard() {
  const out = h("div", { class: "muted" }, "Загружаю…");
  const load = async () => {
    let r;
    try { r = await api("/api/events?daily=1"); } catch (e) { return put(out, errbox(e)); }
    const lk = r.lucky || {};
    const d = r.daily;
    put(out,
      kv([["Время сервера", T("{0} (UTC {1})", r.server_now, r.server_utc)],
          ["Event.dat NpcServer", Object.keys(r.npc).map(n => T("{0}: {1}", n, r.npc[n].read ? (r.npc[n].md5 || "").slice(0, 8) : T("не прочитан"))).join(" · ")],
          ["Счастливые часы (GameServerEvent.txt)", Object.keys(lk).map(g => T("{0}: строк {1}, до {2}", g, lk[g].rows, lk[g].last || "—")).join(" · ")],
          ["Счастливые часы сейчас", lk.GameServer && lk.GameServer.now ? T("+{0} ({1}:00–{2}:00)", lk.GameServer.now[5], lk.GameServer.now[3], lk.GameServer.now[4]) : T("нет")],
          // ★ А5.10: P128 (DLL v85+) — значок события (монеты / опыт) видят все игроки; ниже — только оператор (сток)
          // ★ ревизия 49 Н-1: по факту установки P128 (журнал патчей), узел без пульса — «не прочитано»
          ["Значок события у игроков", Object.keys(r.badge_text || {}).map(g => T("{0}: {1}", g, T(r.badge_text[g]))).join(" · ")]]),
      r.windows.length ? table([["Тип", w => T(w.type_name)], ["Окно (без года)", w => w.window],
          ["", w => badge(T((EV_PHASE[w.phase] || [w.phase])[0]), (EV_PHASE[w.phase] || [])[1])],
          ["Карт", w => w.maps.length], ["Копии", w => w.copies.join(", ")]], r.windows)
        : h("div", { class: "muted" }, "Событий в Event.dat нет."),
      (r.warnings || []).map(w => h("div", { class: "note" }, T(w))),
      can("server.events") ? eventForm(r, load) : null,
      can("server.ranks") ? rankForm(r, load) : null,
      d ? kv([["Ежедневные задания доски: граница суток", d.boundary],
              ["Суточный сброс", d.done ? T("сделан ({0}, {1})", d.done.source, d.done.at) : T("НЕ сделан")],
              ["Строк к сбросу", d.pending_rows],
              ["Задача ОС ASDA_LimitationDailyReset", d.task ? T("{0}, итог {1}, следующий {2}", d.task.last, d.task.result, d.task.next) : T("не прочитано")]]) : null,
      d && can("server.daily") ? dailyForm(r, load) : null,
      h("div", { class: "muted small" }, T("Счастливые часы правятся набором изменений: раздел «Данные», область «Счастливые часы» (действуют после рестарта стойки).")));
  };
  load();
  return h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { class: "grow" }, "События и сбросы"),
    h("button", { type: "button", class: "ghost", onclick: load }, "Обновить")), out);
}
// общая отправка: сейчас (операция) или заданием службы (job.add) — предпросмотр, окно подтверждения, применение
async function evRun(name, params, at, two, code, err, reload) {
  err.textContent = "";
  // второй фактор: у event.set и daily.reset (у задания — всегда, сейчас — у внеочередного сброса и события); код не пишется в журнал
  const tot = two || code ? code : "";
  const body = at ? { op: name, at: new Date(at).toISOString(), repeat: "", params, totp: tot }
    : Object.assign({}, params, tot ? { totp: tot } : {});
  const opName = at ? "job.add" : name;
  let p;
  try { p = await op(opName, body, true); } catch (e) { err.textContent = e.message; return; }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
  try { const x = await op(opName, body, false); notify(T(x.message)); reload(); } catch (e) { err.textContent = e.message; }
}
// ★ 25.11.2026 (владелец: «варианты непонятны — упростить, переименовать, выбор даты по ограничениям»): форма события — подписанные строки,
//   выбор даты и времени календарём ПО ЧАСАМ СЕРВЕРА с теми же пределами, что проверяет служба: окно события — не в прошлом, в пределах одного
//   года (сервер хранит окно без года); запуск задания — не раньше чем через минуту и не позже чем через 31 день (core/jobs.MIN_AHEAD_S /
//   MAX_AHEAD_DAYS); выключение заданием — только если конец окна не дальше 31 дня. Служба проверяет всё это сама — здесь только подсказка.
const EV_MIN = 60 * 1000, EV_DAY = 24 * 3600 * 1000, JOB_MAX_DAYS = 31;
const srvMs = s => Date.parse(String(s).replace(" ", "T").slice(0, 16) + ":00Z");    // «ГГГГ-ММ-ДД чч:мм» сервера → мс (арифметика как UTC)
const srvStr = ms => new Date(ms).toISOString().slice(0, 16);                         // → значение datetime-local
function srvClock(r) {
  const base = srvMs(r.server_now), off = base - srvMs(r.server_utc), t0 = Date.now();
  return { now: () => base + (Date.now() - t0), toUtcIso: ms => new Date(ms - off).toISOString(), show: ms => srvStr(ms).replace("T", " ") };
}
// поле «Когда выполнить»: сейчас или заданием службы в пределах [через минуту; через 31 день] по часам сервера
function whenPicker(clk) {
  const sel = h("select", null, [["now", T("сейчас")], ["job", T("запланировать (время сервера)")]].map(([v, t]) => h("option", { value: v }, t)));
  const at = h("input", { type: "datetime-local", step: 60, hidden: true });
  const hint = h("span", { class: "muted small", hidden: true });
  const lim = () => {
    const n = clk.now(), lo = Math.ceil((n + EV_MIN) / EV_MIN) * EV_MIN + EV_MIN, hi = Math.floor((n + JOB_MAX_DAYS * EV_DAY) / EV_MIN) * EV_MIN;
    at.min = srvStr(lo); at.max = srvStr(hi);
    if (!at.value || srvMs(at.value) < lo) at.value = srvStr(lo + 4 * EV_MIN);
    hint.textContent = T("от {0} до {1}", clk.show(lo), clk.show(hi));
    return [lo, hi];
  };
  sel.addEventListener("change", () => { const j = sel.value === "job"; at.hidden = hint.hidden = !j; if (j) lim(); });
  at.addEventListener("focus", lim);
  return {
    el: h("div", { class: "row" }, sel, at, hint),
    // "" — сейчас; иначе ISO UTC для job.add; ошибка — исключение с понятным текстом
    value() {
      if (sel.value !== "job") return "";
      const [lo, hi] = lim(), v = srvMs(at.value);
      if (!at.value || isNaN(v)) throw new Error(T("выберите дату и время запуска"));
      if (v < lo - EV_MIN || v > hi) throw new Error(T("время запуска — не раньше чем через минуту и не позже чем через {0} дн.", JOB_MAX_DAYS));
      return clk.toUtcIso(v);
    },
    isJob: () => sel.value === "job",
    onChange: f => sel.addEventListener("change", f),
  };
}
// строка формы «подпись — поле» в сетке kv edit; hide(true) прячет обе ячейки
function evRow(label, ...ctrl) {
  const a = h("div", null, label), b = h("div", { class: "row" }, ctrl);
  const row = { cells: [a, b], hide: v => { a.hidden = b.hidden = v; } };
  // подсказка при наведении (владелец 25.11: «что это значит — подсказку по наведению»)
  row.tip = t => { a.title = b.title = T(t); a.style.cursor = b.style.cursor = "help"; if (!label) b.classList.add("hasTip"); return row; };
  return row;
}
function eventForm(r, reload) {
  const clk = srvClock(r);
  const mode = h("select", null, [["set", T("включить событие")], ["off", T("выключить событие")]].map(([v, t]) => h("option", { value: v }, t)));
  const typ = h("select", null, [["1", T("опыт")], ["0", T("добыча и золото (шанс выпадения)")]].map(([v, t]) => h("option", { value: v }, t)));
  const val = h("input", { type: "number", min: 0, max: 10, step: 0.1, value: "2", style: { width: "90px" } });
  const start = h("input", { type: "datetime-local", step: 60 });
  const end = h("input", { type: "datetime-local", step: 60 });
  const chan = h("select", null, [["-1", T("все каналы")], ["3", T("только подземелья (Indun)")]].map(([v, t]) => h("option", { value: v }, t)));
  const map = h("select", null, [h("option", { value: "-1" }, T("все карты"))].concat((r.maps || []).map((n, i) => h("option", { value: String(i) }, i + " " + n))));
  const repl = h("input", { type: "checkbox", class: "chk" });
  const strongOk = h("input", { type: "checkbox", class: "chk" });
  const auto = h("input", { type: "checkbox", class: "chk", checked: true });
  const conf = h("input", { type: "checkbox", class: "chk" });
  const code = h("input", { type: "text", maxlength: 6, inputmode: "numeric", placeholder: T("6 цифр, новый код (не тот, что при входе)"), autocomplete: "one-time-code", style: { width: "260px" } });
  const valHint = h("span", { class: "muted small" });
  const winHint = h("span", { class: "muted small" });
  const autoHint = h("span", { class: "muted small" });
  const when = whenPicker(clk);
  const btn = h("button", { type: "submit", class: "gold" });
  const err = h("div", { class: "err" });
  // пределы окна: начало — не раньше текущей минуты сервера и не дальше года вперёд; конец — позже начала, до 31.12 того же года
  const limits = () => {
    const n = Math.floor(clk.now() / EV_MIN) * EV_MIN;
    start.min = srvStr(n); start.max = srvStr(n + 364 * EV_DAY);
    if (!start.value || srvMs(start.value) < n) start.value = srvStr(n + 5 * EV_MIN);
    const s = srvMs(start.value), y = start.value.slice(0, 4);
    end.min = srvStr(s + EV_MIN); end.max = y + "-12-31T23:59";
    if (!end.value || srvMs(end.value) <= s || end.value.slice(0, 4) !== y) end.value = srvStr(Math.min(s + 3 * EV_DAY, srvMs(end.max)));
    winHint.textContent = T("сейчас на сервере {0}; окно — в пределах одного года, конец не позже {1}", clk.show(clk.now()), end.max.replace("T", " "));
    const far = srvMs(end.value) > clk.now() + JOB_MAX_DAYS * EV_DAY;
    auto.disabled = far;
    if (far) auto.checked = false;
    autoHint.textContent = far ? T("конец дальше 31 дня — автоматически не выключится, выключите сами") : "";
  };
  const valCheck = () => {
    const v = parseFloat(String(val.value).replace(",", "."));
    const strong = !isNaN(v) && (v > 2 || v < 1);
    rStrong.hide(!(mode.value === "set" && strong));
    valHint.textContent = isNaN(v) ? "" : (v === 1 ? T("×1 — без изменений") : T("×{0} от обычного; 2 — вдвое больше; от 0 до 10", v));
  };
  const rMode = evRow("Действие", mode).tip("Включить — записать новое событие на сервер. Выключить — снять уже записанное событие выбранного типа на выбранных картах.");
  const rType = evRow("Что", typ).tip("Опыт — больше опыта за монстров. Добыча и золото — выше шанс выпадения предметов и золота (сумма золота за раз не меняется).");
  const rVal = evRow("Во сколько раз", val, valHint).tip("Во сколько раз больше обычного: 2 — вдвое, 1.5 — в полтора раза. От 0 до 10, не больше двух знаков после точки. Обычный диапазон — от 1 до 2.");
  const rStart = evRow("Начало (время сервера)", start).tip("Когда событие начнётся, по часам сервера. Не раньше текущей минуты.");
  const rEnd = evRow("Конец (время сервера)", end, winHint).tip("Когда событие закончится, по часам сервера. Сервер хранит даты без года, поэтому окно должно уложиться в один год (не позже 31 декабря).");
  const rChan = evRow("Каналы", chan).tip("Все каналы — поле, второй канал и подземелья. Только подземелья — только сервер Indun.");
  const rMap = evRow("Карты", map).tip("Все карты сразу или одна выбранная карта.");
  const rRepl = evRow("", h("label", { class: "row chkl" }, repl, "если на этих картах уже есть такое событие — заменить его")).tip("У каждой карты может быть только одно событие каждого типа (опыт или добыча). Если на выбранных картах такое событие уже идёт или назначено, без этой отметки служба откажет. С отметкой новое событие заменит старое.");
  const rStrong = evRow("", h("label", { class: "row chkl" }, strongOk, "да, множитель больше 2 или меньше 1 (только владелец)")).tip("Множитель выше 2 (например 3) или ниже 1 (например 0.5 — меньше обычного) — сильная правка баланса. Её может сделать только владелец, и эта отметка — второе подтверждение.");
  const rAuto = evRow("", h("label", { class: "row chkl" }, auto, "выключить автоматически после конца"), autoHint).tip("Через 2 минуты после конца служба сама выключит событие. Без этого окно останется записанным на сервере и сработает снова в те же даты через год. Работает, только если конец не дальше 31 дня.");
  const rConf = evRow("", h("label", { class: "row chkl" }, conf, "понимаю: это действует на всех игроков")).tip("Обязательная отметка: событие меняет опыт или добычу сразу для всех игроков на выбранных картах.");
  const rWhen = evRow("Когда выполнить", when.el).tip("Сейчас — сразу. Запланировать — служба выполнит команду в выбранное время по часам сервера: не раньше чем через минуту и не позже чем через 31 день.");
  const rCode = evRow("Код второго фактора", code).tip("6 цифр из приложения-аутентификатора. Нужен новый код: тот, которым вы входили, повторно не принимается.");
  const sync = () => {
    const on = mode.value === "set";
    [rVal, rStart, rEnd, rRepl, rAuto].forEach(x => x.hide(!on));
    rCode.hide(!(on || when.isJob()));
    btn.textContent = T(when.isJob() ? "Запланировать" : (on ? "Включить событие" : "Выключить событие"));
    valCheck();
    if (on) limits();
  };
  mode.addEventListener("change", sync);
  when.onChange(sync);
  val.addEventListener("input", valCheck);
  start.addEventListener("change", limits);
  end.addEventListener("change", limits);
  start.addEventListener("focus", limits);
  const go = (ev) => {
    ev.preventDefault();
    err.textContent = "";
    const set = mode.value === "set";
    let at;
    try { at = when.value(); } catch (e) { err.textContent = e.message; return; }
    if (set && start.value && end.value && srvMs(end.value) <= srvMs(start.value)) { err.textContent = T("конец должен быть позже начала"); return; }
    const params = { type: typ.value, chan: chan.value, map: map.value, confirm: conf.checked ? "event" : "" };
    if (set) Object.assign(params, { value: String(val.value).trim(), start: start.value.replace("T", " "), end: end.value.replace("T", " "),
      auto_off: auto.checked ? "1" : "0", replace: repl.checked ? "replace" : "", rate_ok: strongOk.checked ? "rate" : "" });
    evRun(set ? "event.set" : "event.off", params, at, set, code.value.trim(), err, reload);
  };
  sync();
  return h("form", { class: "card", onsubmit: go }, h("h2", null, "Событие: больше опыта или добычи"),
    h("div", { class: "kv edit" }, [rMode, rType, rVal, rStart, rEnd, rChan, rMap, rRepl, rStrong, rAuto, rConf, rWhen, rCode].map(x => x.cells)),
    h("div", { class: "row" }, btn, err),
    h("div", { class: "muted small" }, T("Команду выполняет сервер от персонажа служебной учётки (номер 1…5000) с GM-флагом — он должен быть в игре.")));
}
function rankForm(r, reload) {
  const what = h("select", null, [["0", T("всё: условия званий, звания 65…69, топ славы")], ["1", T("рейтинговые звания 65…69")],
    ["2", T("место в топе славы")], ["3", T("условия званий у игроков в игре")]].map(([v, t]) => h("option", { value: v }, t)));
  const conf = h("input", { type: "checkbox", class: "chk" });   // ★ ревизия 44 Н-3: слово rank (массовая операция)
  const when = whenPicker(srvClock(r));
  const err = h("div", { class: "err" });
  const go = (ev) => {
    ev.preventDefault(); err.textContent = "";
    let at;
    try { at = when.value(); } catch (e) { err.textContent = e.message; return; }
    evRun("rank.recalc", { what: what.value, confirm: conf.checked ? "rank" : "" }, at, false, "", err, reload);
  };
  return h("form", { class: "row card", onsubmit: go }, h("span", null, T("Пересчитать рейтинги (6020)")), what,
    h("label", { class: "row chkl" }, conf, "подтверждаю пересчёт всем игрокам"), when.el,
    h("button", { type: "submit" }, "Пересчитать"), err);
}
function dailyForm(r, reload) {
  const mode = h("select", null, [["catchup", T("догнать суточный сброс")], ["force", T("внеочередной сброс всем")]].map(([v, t]) => h("option", { value: v }, t)));
  const conf = h("input", { type: "checkbox", class: "chk" });
  const when = whenPicker(srvClock(r));
  const code = h("input", { type: "text", maxlength: 6, placeholder: T("свежий код второго фактора (не тот, которым входили)"), autocomplete: "one-time-code" });
  const err = h("div", { class: "err" });
  const go = (ev) => {
    ev.preventDefault(); err.textContent = "";
    let at;
    try { at = when.value(); } catch (e) { err.textContent = e.message; return; }
    const force = mode.value === "force";
    evRun("daily.reset", { mode: mode.value, confirm: conf.checked ? "daily" : "" }, at, force || !!at, code.value.trim(), err, reload);
  };
  return h("form", { class: "row card", onsubmit: go }, h("span", null, T("Ежедневные задания доски")), mode,
    h("label", { class: "row chkl" }, conf, "подтверждаю сброс всем"), when.el, code, h("button", { type: "submit" }, "Сбросить"), err);
}

// ---------- А5.1: задания планировщика (adm.job) и управление стойкой ----------
// Рестарт / остановка / запуск стойки — только restart_stack.py с ПК владельца (объявление Discord EN/AR/RU, 3 минуты с отсчётом
// в игре); из панели они ставятся заданием (исполнитель — консоль ПК, asda_admin.py jobs run-due), с подтверждением и свежим кодом
// второго фактора. Объявление в игру (мост) — задание службы.
const JOB_ST = { pending: ["ждёт", "warn"], running: ["идёт", "warn"], done: ["готово", "ok"], failed: ["сбой", "bad"],
  refused: ["отказ", "bad"], cancelled: ["отменено", ""], missed: ["пропущено", "bad"] };
function jobsCard() {
  const out = h("div");
  const allBox = h("input", { type: "checkbox", class: "chk" });
  const load = async () => {
    put(out, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/jobs" + (allBox.checked ? "?all=1" : "")); } catch (e) { return put(out, errbox(e)); }
    const act = async (name, params, okMsg) => {
      let p;
      try { p = await op(name, params, true); } catch (e) { return notify(e.message, true); }
      if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
        (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
      try { const x = await op(name, params, false); notify(T(x.message || okMsg)); load(); } catch (e) { notify(e.message, true); }
    };
    put(out, r.items.length ? table([["№", j => j.id], ["", j => badge(T((JOB_ST[j.status] || [j.status])[0]), (JOB_ST[j.status] || [])[1])],
        ["Операция", j => j.op], ["Запуск (UTC)", j => dt(j.run_at) + (j.repeat_mode ? " · " + j.repeat_mode : "")],
        ["Исполнитель", j => j.runner === "pc" ? T("консоль ПК") : T("служба")], ["Автор", j => j.created_by],
        ["Итог", j => T(j.result || "")],
        ["", j => j.status === "pending" && can("jobs.manage") ? h("button", { type: "button", class: "ghost",
          onclick: () => act("job.cancel", { id: j.id }, "отменено") }, "Отменить") : ""]], r.items)
      : h("div", { class: "muted" }, "Заданий нет."),
      can("jobs.manage") && r.schedulable.length ? jobForm(r.schedulable, load) : null);
  };
  allBox.addEventListener("change", load);
  load();
  return h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { class: "grow" }, "Задания и стойка"),
    h("label", { class: "row chkl" }, allBox, "и законченные")), out);
}
// ---------- А5.7: бэкапы БД (COPY_ONLY + CHECKSUM + RESTORE VERIFYONLY; восстановление — только на стенд LocalDB ПК консолью) ----------
// Состояние — /api/dbbackup (базы списка, последний бэкап любого инструмента по msdb, бэкапы панели, место на томе папки, предупреждения).
// Кнопка ставит задание службы на «сейчас» (db.backup), перепроверка — db.verify; по расписанию — карточка «Задания и стойка».
// Кнопки восстановления на живой сервер нет и не будет. Все тексты — только текстовыми узлами (без innerHTML).
const DBB_ST = { running: ["идёт", "warn"], done: ["готов", "ok"], failed: ["не удался", "bad"], deleted: ["удалён", ""] };
function dbCard() {
  const out = h("div", { class: "muted" }, "Загружаю…");
  const mb = b => b === null || b === undefined ? "—" : T("{0} МБ", (b / 1048576).toFixed(1));
  const age = x => x && x.age_h !== null && x.age_h !== undefined ? T("{0} ч назад", x.age_h) : "";
  const act = async (name, params, reload) => {
    let p;
    try { p = await op(name, params, true); } catch (e) { return notify(e.message, true); }
    if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
      (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
    try { const x = await op(name, params, false); notify(T(x.message)); reload(); } catch (e) { notify(e.message, true); }
  };
  const load = async () => {
    let r;
    try { r = await api("/api/dbbackup"); } catch (e) { return put(out, errbox(e)); }
    if (!r.read) return put(out, h("div", { class: "err" }, r.error || T("не прочитано")));
    const sel = h("select", null, [h("option", { value: "all" }, T("все базы"))].concat(r.dbs.map(d => h("option", { value: d.db }, d.db))));
    put(out,
      kv([["Папка бэкапов на сервере", r.folder || "—"],
          ["Свободно на томе папки", r.free_bytes === null || r.free_bytes === undefined ? badge(T("не прочитано"), "warn")
            : T("{0} из {1} ({2})", mb(r.free_bytes), mb(r.total_bytes), r.volume || "—")],
          // ★ ревизия 47 С-3: автоуборка — только по возрасту; недельные и месячные копии и последние проверенные — всегда
          ["Хранение", T("{0} дн., недельные — {1} нед., месячные — {2} мес., последние {3} проверенных — всегда", r.policy.keep_days,
            r.policy.long_weeks, r.policy.long_months, r.policy.keep_min)],
          ["Бэкапов панели на диске", T("{0} файлов, {1}", r.panel_files, mb(r.panel_bytes))],
          ["Предупреждать, если бэкапу больше", T("{0} ч", r.policy.warn_hours)]]),
      (r.warnings || []).map(w => h("div", { class: "note" }, w)),
      table([["База", d => d.db], ["Модель", d => d.recovery || "—"], ["Данные / журнал", d => mb(d.data_bytes) + " / " + mb(d.log_bytes)],
             ["Проверенный бэкап панели", d => d.panel_verified ? h("span", null, T("№{0}, {1} UTC", d.panel_verified.id, (d.panel_verified.finished_utc || "").slice(0, 16)),
                " ", badge(age(d.panel_verified), d.panel_verified.age_h > r.policy.warn_hours ? "bad" : "ok"), " ", mb(d.panel_verified.bytes),
                d.panel_verified.stand_ok === null || d.panel_verified.stand_ok === undefined ? "" : badge(T(d.panel_verified.stand_ok ? "стенд: восстановлен" : "стенд: НЕ прошёл"),
                  d.panel_verified.stand_ok ? "ok" : "bad")) : badge(T("нет"), "warn")],
             ["Последний бэкап любым инструментом (msdb)", d => d.any ? h("span", null, T("{0} UTC", (d.any.finish_utc || "").slice(0, 16)), " ",
                h("span", { class: "muted small" }, d.any.device + (d.any.copy_only ? " · COPY_ONLY" : ""))) : T("нет")],
             ["", d => d.warnings.length ? d.warnings.map(w => h("div", { class: "note" }, w)) : badge(T("в порядке"), "ok")]], r.dbs),
      can("db.backup") ? h("div", { class: "row" }, sel,
        h("button", { type: "button", class: "gold", onclick: () => act("db.backup", { dbs: sel.value }, load) }, "Сделать бэкап сейчас"),
        h("span", { class: "muted small" }, T("COPY_ONLY + CHECKSUM + RESTORE VERIFYONLY заданием службы; по расписанию — «Задания и стойка», операция «Бэкапы БД»."))) : null,
      r.rows.length ? table([["№", x => x.id], ["База", x => x.db], ["", x => badge(T((DBB_ST[x.status] || [x.status])[0]), (DBB_ST[x.status] || [])[1])],
          ["Проверен", x => x.verified === null || x.verified === undefined ? "—" : x.verified ? badge(T("да"), "ok") : badge(T("НЕТ"), "bad")],
          ["Время (UTC)", x => (x.finished_at || x.started_at || "").slice(0, 16)], ["Размер", x => mb(x.backup_bytes)],
          ["md5", x => x.md5 ? x.md5.slice(0, 8) + "…" : "—"], ["Автор", x => x.by_login], ["Итог", x => x.message || ""],
          ["", x => x.status === "done" && can("db.backup") ? h("button", { type: "button", class: "ghost",
            onclick: () => act("db.verify", { id: x.id }, load) }, "Перепроверить") : ""]], r.rows) : h("div", { class: "muted" }, "Бэкапов панели ещё нет."),
      h("div", { class: "muted small" }, T("Восстановление — только на стенд LocalDB ПК владельца консолью: python asda_admin.py db stand --id N (скачивание по SSH со сверкой md5, RESTORE … WITH MOVE, DBCC CHECKDB, строки таблиц). На живой сервер панель не восстанавливает.")));
  };
  load();
  return h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { class: "grow" }, "Бэкапы БД"),
    h("button", { type: "button", class: "ghost", onclick: load }, "Обновить")), out);
}
// ---------- А5.8: служебные копии *_bak_* (каталог adm.bakdrop_obj: можно убрать / нужна откату / неизвестно) ----------
// Список — /api/bakdrop (подписанная adm.BakState: размер, даты, происхождение, ссылки, свежий бэкап базы, журнал удалений).
// Удаление — db.bakdrop: только владелец, только копии «можно убрать» без ссылок, свежий проверенный бэкап базы, слово bakdrop и свежий код
// второго фактора; одна транзакция на базу. Отмены нет — восстановление только на стенд LocalDB консолью. Без innerHTML.
const BAK_V = { drop: ["можно убрать", "ok"], rollback: ["нужна откату", "warn"], unknown: ["неизвестно", "bad"] };
function bakCard() {
  const out = h("div", { class: "muted" }, "Загружаю…");
  const showAll = h("input", { type: "checkbox", class: "chk" });
  const drop = async (dbname, names, reload) => {
    let p;
    try { p = await op("db.bakdrop", { db: dbname, names }, true); } catch (e) { return notify(e.message, true); }
    const word = h("input", { type: "text", maxlength: 10, placeholder: T("слово bakdrop"), autocomplete: "off" });
    const code = h("input", { type: "text", maxlength: 6, placeholder: T("свежий код второго фактора (не тот, которым входили)"), autocomplete: "one-time-code" });
    if (!await confirmWin(T("Подтвердите удаление"), [h("div", { class: "pv" }, T(p.preview.text)),
      (p.preview.items || []).map(x => h("div", { class: "muted small" }, x.name + " — " + T(x.evidence || ""))),
      (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w))),
      h("div", { class: "row" }, word, code)], T("Удалить"))) return;
    try {
      const x = await op("db.bakdrop", { db: dbname, names, confirm: word.value.trim(), totp: code.value.trim(), expect: p.preview.expect }, false);
      notify(T(x.message)); reload();
    } catch (e) { notify(e.message, true); }
  };
  const load = async (force) => {
    let r;
    // ★ ревизия 48 (мелочь 9): служба держит список в памяти 60 с; «Обновить» — заново, но не чаще раза в 15 с
    try { r = await api("/api/bakdrop" + (force === true ? "?force=1" : "")); } catch (e) { return put(out, errbox(e)); }
    if (!r.read) return put(out, h("div", { class: "err" }, r.error || T("не прочитано")));
    const rows = r.items.filter(x => x.present || showAll.checked);
    const picked = new Map();
    const byDb = {};
    rows.forEach(x => { (byDb[x.db] = byDb[x.db] || []).push(x); });
    const btn = (dbname) => can("db.bakdrop") && (byDb[dbname] || []).some(x => x.droppable)
      ? h("button", { type: "button", class: "gold", onclick: () => {
          const names = [...picked.entries()].filter(([k, v]) => v.checked && k.startsWith(dbname + "|")).map(([k]) => k.split("|")[1]);
          if (!names.length) return notify(T("не выбраны копии для удаления"), true);
          drop(dbname, names, load);
        } }, T("Удалить выбранные ({0})", dbname)) : null;
    put(out,
      // ★ ревизия 48 С-1: базы, где ссылки на копии не прочитаны, — удаление отказывает, пока это так
      (r.unread || []).map(w => h("div", { class: "note" }, T("ссылки не прочитаны в базе {0}: {1} — удаление закрыто", w.db, T(w.why)))),
      kv([["Свежий бэкап для уборки — не старше", T("{0} ч", r.fresh_hours)],
          ["Можно убрать / нужна откату / неизвестно", T("{0} / {1} / {2}", r.counts.drop || 0, r.counts.rollback || 0, r.counts.unknown || 0)]]),
      Object.keys(byDb).sort().map(dbname => {
        const f = (r.dbs[dbname] || {}).fresh;
        return h("div", null, h("h3", null, dbname),
          h("div", { class: "muted small" }, f ? T("свежий проверенный бэкап: №{0}, {1} UTC ({2} ч назад)", f.id, (f.finished_utc || "").slice(0, 16), f.age_h)
            : ((r.dbs[dbname] || {}).error || T("свежего проверенного бэкапа нет — сначала «Сделать бэкап сейчас» в карточке «Бэкапы БД»"))),
          table([["", x => {
                    if (!x.droppable || !can("db.bakdrop")) return "";
                    const c = h("input", { type: "checkbox", class: "chk" }); picked.set(x.db + "|" + x.sch + "." + x.name, c); return c; }],
                 ["Объект", x => x.sch + "." + x.name], ["Вид", x => x.type || "—"],
                 ["", x => badge(T((BAK_V[x.verdict] || [x.verdict])[0]), (BAK_V[x.verdict] || [])[1])],
                 ["Строк", x => x.rows_n === null || x.rows_n === undefined ? "—" : String(x.rows_n)],
                 ["КБ", x => x.kb === null || x.kb === undefined ? "—" : String(x.kb)],
                 ["Создан (UTC)", x => x.present ? (x.created_utc || "").slice(0, 16) : badge(T("нет на сервере"), "")],
                 ["Происхождение", x => h("div", null, T(x.origin || "—"), x.needed_by ? h("div", { class: "note" }, T("нужна откату: {0}", T(x.needed_by))) : null,
                   x.ref_file ? h("div", { class: "muted small" }, x.ref_file) : null)],
                 ["Почему", x => h("div", null, T(x.evidence || ""), x.blocked && x.verdict === "drop" ? h("div", { class: "note" },
                   x.refs_n ? T("на неё ссылаются: {0}", x.refs || "?") : T(x.blocked)) : null)]],
                byDb[dbname]),
          h("div", { class: "row" }, btn(dbname)));
      }),
      r.log.length ? [h("h3", null, "Журнал удалений"), table([["№", x => x.id], ["Объект", x => x.db + "." + x.sch + "." + x.name],
          ["Строк", x => x.rows_n === null || x.rows_n === undefined ? "—" : String(x.rows_n)], ["Бэкап", x => "№" + x.backup_id],
          ["Время (UTC)", x => (x.dropped_at || "").slice(0, 16)], ["Автор", x => x.by_login]], r.log)] : null,
      h("div", { class: "muted small" }, T("Отмены нет: удалённую копию возвращают восстановлением бэкапа на стенд LocalDB ПК (python asda_admin.py db stand --id N --keep) и ручным переносом; снимок столбцов или текст процедуры и число строк — в журнале удалений, бэкап из журнала удалений автоуборка не трогает. Копии «нужна откату» и «неизвестно» панель не удаляет никогда.")));
  };
  showAll.addEventListener("change", () => load(false));
  // список строится поиском ссылок по тексту всех модулей баз (на сервере ~10 с) — только по кнопке, не при каждом открытии «Состояния»
  put(out, h("button", { type: "button", class: "ghost", onclick: () => { put(out, h("div", { class: "muted" }, "Загружаю…")); load(); } },
    "Показать служебные копии"));
  return h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { class: "grow" }, "Служебные копии"),
    h("label", { class: "row chkl" }, showAll, "и отсутствующие на сервере"),
    h("button", { type: "button", class: "ghost", onclick: () => load(true) }, "Обновить")), out);
}
function jobForm(ops, reload) {
  const sel = h("select", null, ops.map(o => h("option", { value: o.op }, T(o.title))));
  const at = h("input", { type: "datetime-local" });
  const rep = h("select", null, [["", T("разово")], ["daily", T("каждый день")], ["weekly", T("каждую неделю")]].map(([v, t]) => h("option", { value: v }, t)));
  const text = h("input", { type: "text", maxlength: 95, placeholder: T("текст объявления (до 95 символов)"), class: "grow" });
  const conf = h("input", { type: "checkbox", class: "chk" });
  const code = h("input", { type: "text", maxlength: 6, placeholder: T("свежий код второго фактора (не тот, которым входили)"), autocomplete: "one-time-code" });
  const err = h("div", { class: "err" });
  // ★ А5.3: режим обслуживания по расписанию — текст объявления, «без объявления», «отключить игроков», подтверждение, второй фактор (вкл.)
  const silent = h("input", { type: "checkbox", class: "chk" });
  const kick = h("input", { type: "checkbox", class: "chk" });
  const confText = h("span", null);
  const cur = () => ops.find(o => o.op === sel.value) || ops[0];
  const isMaint = o => o.op.startsWith("maint.");
  const sync = () => {
    const o = cur();
    text.hidden = o.stack || o.op === "db.backup";      // ★ А5.7: у бэкапа БД текста нет (базы — все)
    conf.parentNode && (conf.parentNode.hidden = !(o.stack || o.confirm));
    code.hidden = !o.two;
    silent.parentNode && (silent.parentNode.hidden = o.op !== "maint.on");
    kick.parentNode && (kick.parentNode.hidden = o.op !== "maint.on");
    put(confText, T(isMaint(o) ? "подтверждаю (режим обслуживания)" : "подтверждаю (стойка: объявление Discord, 3 минуты)"));
  };
  sel.addEventListener("change", sync);
  const go = async (ev) => {
    ev.preventDefault();
    err.textContent = "";
    const o = cur();
    if (!at.value) { err.textContent = T("укажите время запуска"); return; }
    let params;
    if (o.stack) params = conf.checked ? { confirm: o.confirm } : {};
    else if (isMaint(o)) {
      params = { confirm: conf.checked ? o.confirm : "", announce: text.value.trim() };
      if (o.op === "maint.on" && silent.checked) params.silent = "silent";
      if (o.op === "maint.on" && kick.checked) params.kick = "players";
    } else if (o.op === "db.backup") params = { dbs: "all" };
    else params = { text: text.value.trim() };
    const body = { op: o.op, at: new Date(at.value).toISOString(), repeat: rep.value, params, totp: o.two ? code.value.trim() : "" };
    let p;
    try { p = await op("job.add", body, true); } catch (e) { err.textContent = e.message; return; }
    if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
      (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
    try { const x = await op("job.add", body, false); notify(T(x.message)); code.value = ""; reload(); } catch (e) { err.textContent = e.message; }
  };
  const f = h("form", { class: "row card", onsubmit: go }, sel, at, rep, text,
    h("label", { class: "row chkl" }, silent, "без объявления"), h("label", { class: "row chkl" }, kick, "отключить игроков вне 1…5000"),
    h("label", { class: "row chkl" }, conf, confText), code,
    h("button", { type: "submit" }, "Поставить"), err);
  setTimeout(sync, 0);
  return f;
}

// ---------- А5.2: кто в игре по данным моста P127 (по картам, поиск, переход к карточке, живые действия) ----------
// Источник — adm.bridge_presence (такт игрока в GameServer), не Us_member.Flag (флаг залипает после остановки). Действия: сообщение,
// отключить, перенести к персонажу (аналог стоковых 6012 / 6014 — char.move режим «char»), объявление всем (сразу или заданием),
// для персонажа служебной учётки ≤ 5000 — вызвать / вернуть группу монстров (6045 / 6046, мост v83).
async function viewOnline(q) {
  const my = S.nav;
  mount(shell("#/online", h("h1", null, "Кто в игре"), h("div", { class: "muted" }, "Загружаю…")));
  let r;
  try { r = await api("/api/bridge"); } catch (e) { return stale(my) ? null : mount(shell("#/online", h("h1", null, "Кто в игре"), errbox(e))); }
  if (stale(my)) return;
  const inp = h("input", { placeholder: T("имя персонажа, номер учётки или карта"), value: q || "", class: "grow" });
  const out = h("div");
  const nodes = r.nodes || [];
  const nodeOf = n => nodes.find(x => x.node === n) || {};
  const draw = () => {
    const v = inp.value.trim().toLowerCase();
    history.replaceState(null, "", "#/online" + (v ? "?q=" + encodeURIComponent(v) : ""));
    const rows = (r.presence || []).filter(p => !v || String(p.charname || "").toLowerCase().includes(v) || String(p.Userindex) === v
      || String(p.map) === v || String(p.map_name || "").toLowerCase().includes(v));
    const byMap = {};
    rows.forEach(p => { (byMap[p.map] = byMap[p.map] || []).push(p); });
    const maps = Object.keys(byMap).sort((a, b) => byMap[b].length - byMap[a].length);
    put(out, h("div", { class: "muted small" }, T("В игре по мосту: {0} · карт: {1}", rows.length, maps.length)),
      maps.length ? maps.map(m => h("div", { class: "card" }, h("h2", null, T("Карта {0} — {1} ({2})", m, byMap[m][0].map_name || "?", byMap[m].length)),
        table([["Персонаж", p => p.charname], ["Учётка", p => p.Userindex + "/" + p.Charidx], ["Клетка", p => p.x + "," + p.z],
               ["Узел", p => p.node + (nodeOf(p.node).ver ? " v" + nodeOf(p.node).ver : "")], ["С", p => dt(p.since)],
               ["", p => onlineActions(p, nodeOf(p.node), r.presence, () => viewOnline(inp.value))]], byMap[m],
          p => { location.hash = "#/char/" + p.Userindex + "/" + p.Charidx; })))
        : h("div", { class: "muted" }, "Никого нет в игре (по данным моста)."));
  };
  inp.addEventListener("input", draw);
  mount(shell("#/online",
    h("div", { class: "row" }, h("h1", { class: "grow" }, "Кто в игре"), h("button", { class: "ghost", onclick: () => viewOnline(inp.value) }, "Обновить")),
    h("div", { class: "row card" }, inp,
      can("server.announce") ? h("button", { type: "button", class: "ghost", onclick: announceAll }, "Объявление всем") : null),
    h("div", { class: "card" }, h("h2", null, "Узлы моста"),
      table([["Узел", n => n.node], ["", n => n.fresh ? badge("пульс", "ok") : badge("нет пульса", "bad")],
             ["Режим", n => +n.mode === 1 ? T("исполнять") : T("только слушать")], ["Версия", n => "v" + n.ver], ["В игре", n => n.present],
             ["Пульс", n => dt(n.heartbeat)]], nodes)),
    out));
  draw();
}
function onlineActions(p, node, all, reload) {
  const stop = ev => ev.stopPropagation();
  const b = (label, fn) => h("button", { type: "button", class: "ghost small", onclick: ev => { stop(ev); fn(); } }, label);
  return h("span", { class: "row", onclick: stop },
    can("server.announce") ? b("Сообщение", () => noticeAccount(p.Userindex)) : null,
    can("players.kick") ? b("Отключить", () => runSimple("live.kick", { uid: +p.Userindex }, reload)) : null,
    can("players.move") && S.me.user && (S.me.user.role === "owner" || S.me.user.role === "admin")
      ? b("Перенести к…", () => moveToChar(p, all, reload)) : null,
    can("server.monsters") && +p.Userindex <= 5000 && +node.ver >= 83 ? b("Монстры…", () => mobsWin(p, reload)) : null);   // учётки владельца — служба отказывает не-владельцу (ревизия 42 Н-4)
}
async function runSimple(name, params, reload) {
  let p;
  try { p = await op(name, params, true); } catch (e) { return notify(e.message, "bad"); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
  try { const x = await op(name, Object.assign(p.preview.expect !== undefined ? { expect: p.preview.expect } : {}, params), false);
        notify(T(x.message || "готово")); if (reload) reload(); }
  catch (e) { notify(e.message, "bad"); }
}
async function moveToChar(p, all, reload) {
  // «к персонажу» (6012 — позвать цель к другому, 6014 — переместиться самому к цели): кого переносим → к кому
  const others = (all || []).filter(o => !(o.Userindex === p.Userindex && o.Charidx === p.Charidx));
  if (!others.length) return notify(T("в игре больше никого — переносить не к кому"), "bad");
  const dir = h("select", null, [["to", T("перенести {0} к выбранному", p.charname)], ["from", T("перенести выбранного к {0}", p.charname)]]
    .map(([v, t]) => h("option", { value: v }, t)));
  const who = h("select", null, others.map((o, i) => h("option", { value: String(i) }, o.charname + " (" + T("карта {0}", o.map) + ")")));
  if (!await confirmWin(T("Перенести к персонажу"), [h("div", { class: "row" }, dir), h("div", { class: "row" }, h("span", null, T("Персонаж")), who),
    h("div", { class: "muted small" }, "Как стоковые «позвать» (6012) и «переместиться к игроку» (6014): клетка и карта берутся у другого персонажа по данным моста. Переносимый в игре — переносит сервер сразу (мост), не в игре — меняется позиция для входа.")])) return;
  const o = others[+who.value];
  const [a, t] = dir.value === "to" ? [p, o] : [o, p];
  runSimple("char.move", { uid: +a.Userindex, idx: +a.Charidx, mode: "char", to_uid: +t.Userindex, to_idx: +t.Charidx }, reload);
}
async function mobsWin(p, reload) {
  // ★ ревизия 42 В-1 / С-1: группы карты — из .svr NpcServer узла (справка); номера по умолчанию нет; обычные мобы и группа 0 —
  //   отдельная галочка (confirm = mobs0); честные тексты: бесконечный респавн событийных до 6046, 6046 убивает живых мобов группы
  let gi = null, gerr = "";
  try { gi = await api("/api/mobgroups?node=" + encodeURIComponent(p.node) + "&map=" + encodeURIComponent(p.map)); } catch (e) { gerr = e.message; }
  const kind = h("select", null, [["live.mob_pop", T("вызвать группу (6045)")], ["live.mob_return", T("убрать (вернуть) группу (6046) — живые мобы группы умрут")]]
    .map(([v, t]) => h("option", { value: v }, t)));
  const grp = h("input", { type: "number", min: 0, max: 65535, step: 1, class: "num", placeholder: T("номер") });
  const mode = h("select", null, [["0", T("точка — ровно у персонажа")], ["1", T("на своих точках роуминга (не у персонажа)")]].map(([v, t]) => h("option", { value: v }, t)));
  const zero = h("input", { type: "checkbox", class: "chk" });
  const list = gi ? table([["Группа", g => g.group], ["Мобов", g => g.total], ["Событийных", g => g.event],
      ["", g => g.total > g.event || g.group === 0 ? badge("обычные мобы карты", "warn") : badge("событийная", "ok")]],
    gi.groups.filter(g => g.event || g.group === 0), g => { grp.value = g.group; })
    : h("div", { class: "err" }, T("справка групп не прочитана: {0}", gerr));
  if (!await confirmWin(T("Монстры"), [h("div", { class: "row" }, kind), h("div", { class: "row" }, h("span", null, T("Группа")), grp, mode),
    h("div", { class: "muted small" }, gi ? T("Вызываемые группы карты {0} ({1}, {2}) — щелчок подставит номер:", p.map, gi.file, gi.npc) : ""),
    h("div", { class: "scrollbox" }, list),   // ★ 25.11.2026: длинный список групп — в окне с прокруткой, кнопки окна видны сразу
    h("label", { class: "row chkl" }, zero, "группа 0 или обычные мобы: подтверждаю — их точка появления уйдёт к персонажу до рестарта стойки"),
    h("div", { class: "note" }, "6045: монстры группы появятся у персонажа по таймеру возрождения; событийные будут возрождаться снова и снова, пока не дадите 6046 или не перезапустите стойку; точка появления группы останется сдвинутой до рестарта NpcServer. 6046: живые мобы группы умрут, точку 6046 не возвращает. Ответа у сервера нет. Только служебная учётка с GM-флагом. Не откатывается.")])) return;
  if (grp.value.trim() === "") return notify(T("укажите номер группы"), "bad");
  const params = { uid: +p.Userindex, idx: +p.Charidx, group: +grp.value, confirm: zero.checked ? "mobs0" : "mobs" };
  if (kind.value === "live.mob_pop") params.mode = +mode.value;
  runSimple(kind.value, params, reload);
}
async function announceAll() {
  const inp = h("input", { maxlength: 95, class: "wide", placeholder: T("текст (до 95 символов)") });
  const at = h("input", { type: "datetime-local" });
  // ★ А7.4 (решение владельца А7 №2): «и в Discord» — только флажком; тексты EN / RU / AR оператора, канал и роль — из белого списка
  //   (тот же, что domains/outbox.py и бот); публикует бот Oracle на ПК через очередь adm.Outbox. Без права community.post флажка нет.
  const dOn = h("input", { type: "checkbox", class: "chk" });
  const dBox = h("div", { style: { display: "none" } });
  const opt = (pairs) => pairs.map(([v, t]) => h("option", { value: v }, T(t)));
  const dch = h("select", null, opt([["announcements", "#announcements — новости"], ["updates", "форум updates — новая ветка"], ["test-info", "#test-info — тестерам"]]));
  const drole = h("select", null, opt([["", "без упоминания"], ["news", "News Ping"], ["patch", "Patch Ping"], ["playtest", "Playtest Ping"]]));
  const ta = (ph, rtl) => h("textarea", { rows: 3, maxlength: 1800, class: "wide", placeholder: T(ph), dir: rtl ? "rtl" : "ltr" });
  const den = ta("текст EN (обязательно)"), dru = ta("текст RU (можно пусто)"), dar = ta("текст AR (можно пусто)", true);
  const dttl = h("input", { type: "number", min: 5, max: 1440, step: 1, value: 60, class: "num" });
  put(dBox, h("div", { class: "row" }, h("span", null, T("Канал")), dch, h("span", null, T("Роль")), drole),
    den, dru, dar, h("div", { class: "row" }, h("span", null, T("Срок годности, мин")), dttl),
    h("div", { class: "muted small" }, "@everyone и @here запрещены. Публикует бот Oracle на ПК владельца в течение 30 с, если он запущен. Позже срока годности бот не публикует. Для форума updates имя ветки — текст объявления в игру."));
  dOn.addEventListener("change", () => { dBox.style.display = dOn.checked ? "" : "none"; });
  const dRow = can("community.post") ? [h("label", { class: "row chkl" }, dOn, T("и в Discord")), dBox] : [];
  if (!await confirmWin(T("Объявление всем"), [h("div", { class: "row" }, inp), h("div", { class: "row" }, h("span", null, T("Когда (пусто — сейчас)")), at),
    h("div", { class: "muted small" }, "Сейчас — мостом на все GameServer в режиме исполнения. Со временем — задание планировщика (исполняет служба), видно на странице «Состояние»."),
    ...dRow])) return;
  const params = { text: inp.value.trim() };
  if (dOn.checked) params.discord = { channel: dch.value, role: drole.value, en: den.value, ru: dru.value, ar: dar.value, ttl: dttl.value };
  if (at.value) announceRun("job.add", { op: "live.announce", at: new Date(at.value).toISOString(), params });
  else announceRun("live.announce", params);
}
// ★ А7.4: как runSimple, но многострочный предпросмотр (текст сообщения Discord — как его увидят в канале) — до постановки в очередь
async function announceRun(name, params) {
  let p;
  try { p = await op(name, params, true); } catch (e) { return notify(e.message, "bad"); }
  const pre = { whiteSpace: "pre-wrap" };
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv", style: pre }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note", style: pre }, T(w)))])) return;
  try { const x = await op(name, Object.assign(p.preview.expect !== undefined ? { expect: p.preview.expect } : {}, params), false);
        notify(T(x.message || "готово")); }
  catch (e) { notify(e.message, "bad"); }
}

// ---------- Игроки: список всех (по 20 на страницу) + поиск ----------
// Владелец 16.11: «при открытии раздела уже должен быть список игроков, с листалкой по 20». Поиск — над списком.
function viewPlayers(q, page, online) {
  page = parseInt(page || "1", 10) || 1;
  const inp = h("input", { placeholder: can("players.view_net") ? "логин, номер учётки, имя персонажа, IP, MAC, Discord ID или @handle" : "логин, номер учётки, имя персонажа, Discord ID или @handle", value: q || "", class: "grow" });
  const onlineBox = h("input", { type: "checkbox", class: "chk", checked: online === "1" });
  const out = h("div");
  const accCols = (extra) => [["Учётка", a => a.Userindex], ["Логин", a => a.Us_id],
    ["", a => [a.online ? badge("в игре по БД", "warn") : null, blockBadge(a.block), a.service ? badge("служебная") : null]],
    ["Создана", a => dt(a.us_rdate)], ...(extra || []),
    ["Персонажи", a => a.chars.map(c => c.Charname + " (" + c.Lvl + ")").join(", ")]];
  const showList = async (pg) => {
    const on = onlineBox.checked ? "1" : "";
    history.replaceState(null, "", "#/players?page=" + pg + (on ? "&online=1" : ""));
    put(out, h("div", { class: "muted" }, "Загружаю…"));
    try {
      const r = await api("/api/players/list?page=" + pg + (on ? "&online=1" : ""));
      put(out, h("div", { class: "row" }, h("span", { class: "muted small grow" }, T("Учёток: {0} · страница {1} из {2}", fmt(r.total), r.page, r.pages)),
          pager(r.page, r.pages, showList)),
        table(accCols(), r.items, a => { location.hash = "#/account/" + a.Userindex; }),
        h("div", { class: "row end" }, pager(r.page, r.pages, showList)));
    } catch (e) { put(out, errbox(e)); }
  };
  const go = async (ev) => {
    if (ev) ev.preventDefault();
    const v = inp.value.trim();
    if (!v) return showList(1);
    history.replaceState(null, "", "#/players?q=" + encodeURIComponent(v));
    put(out, h("div", { class: "muted" }, "Ищу…"));
    try {
      const r = await api("/api/players/search?q=" + encodeURIComponent(v));
      put(out, h("div", { class: "row" }, h("span", { class: "muted small grow" }, T("Найдено: {0}", r.items.length)),
          h("button", { type: "button", class: "ghost", onclick: () => { inp.value = ""; showList(1); } }, "Все игроки")),
        r.items.length ? table(accCols([["Совпало", a => T(a.match)]]), r.items, a => { location.hash = "#/account/" + a.Userindex; })
          : h("div", { class: "muted" }, "Ничего не найдено."));
    } catch (e) { put(out, errbox(e)); }
  };
  onlineBox.addEventListener("change", () => { inp.value = ""; showList(1); });
  mount(shell("#/players", h("h1", null, "Игроки"),
    h("form", { class: "row card", onsubmit: go }, inp, h("button", { type: "submit" }, "Найти"),
      h("label", { class: "row chkl" }, onlineBox, "только в игре"),
      can("players.create") ? h("button", { type: "button", class: "ghost", onclick: createAccount }, "Создать учётку") : null,
      can("accounts.create_service") ? h("button", { type: "button", class: "ghost", onclick: createServiceAccount }, "Создать служебную") : null,
      h("button", { type: "button", class: "ghost", onclick: () => discordBans(out) }, "Баны Discord")),
    out));
  inp.focus();
  if (q) go(); else showList(page);
}

// ---------- блок учётки (А1: как ac0_block_user.sql / OPBlockDel; domains/accounts.py) ----------
function blockPanel(uid, a, blocks, rerender) {
  const hours = h("select", null, [[1, T("1 час")], [24, T("1 день")], [72, T("3 дня")], [168, T("7 дней")], [720, T("30 дней")], [-1, T("навсегда")]]
    .map(([v, t]) => h("option", { value: String(v), selected: v === 24 }, t)));
  const reason = h("input", { type: "text", maxlength: 300, placeholder: T("причина (латиницей)"), class: "grow" });
  const err = h("div", { class: "err" });
  const run = async (name, params) => {
    err.textContent = "";
    let p;
    try { p = await op(name, params, true); } catch (e) { err.textContent = e.message; return; }
    if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
      (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w))),
      h("div", { class: "muted small" }, "Действие попадёт в журнал, его можно откатить.")])) return;
    try { const x = await op(name, Object.assign({ expect: p.preview.expect }, params), false); notify(x.message || T("готово")); rerender(); }
    catch (e) { err.textContent = e.message; }
  };
  const blocked = (blocks && blocks.length) || a.us_block;
  return h("div", { class: "card" },
    h("form", { class: "row", onsubmit: (e) => { e.preventDefault(); run("account.block", { uid: +uid, hours: +hours.value, reason: reason.value.trim() }); } },
      h("span", null, T("Заблокировать на")), hours, reason, h("button", { type: "submit" }, "Заблокировать"),
      blocked && can("players.unblock") ? h("button", { type: "button", class: "ok", onclick: () => run("account.unblock", { uid: +uid }) }, "Снять блок") : null),
    h("div", { class: "muted small" }, "Срок истекает сам: при следующем входе сервер снимает блок, у которого вышло время. Игрок в игре доиграет до выхода."),
    err);
}

// ---------- снять залипший «в игре» (domains/online.py: только доказанно мёртвые признаки) ----------
async function clearOnline(uid, rerender) {
  const params = { uid: +uid };
  let p;
  try { p = await op("account.clear_online", params, true); } catch (e) { return notify(e.message, "bad"); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w))),
    h("div", { class: "muted small" }, "Снимается только то, что точно не живая сессия: персонаж вошёл раньше старта GameServer, учётка — раньше старта LoginManager. Действие попадёт в журнал, его можно откатить.")])) return;
  try { const x = await op("account.clear_online", Object.assign({ expect: p.preview.expect }, params), false); notify(x.message || T("готово")); rerender(); }
  catch (e) { notify(e.message, "bad"); }
}

// ---------- пароль игровой учётки (domains/password.py: как UP_AC_SetPassword, P52) ----------
async function setPassword(uid, login, rerender) {
  const p1 = h("input", { type: "password", maxlength: 50, autocomplete: "new-password", class: "grow" });
  const p2 = h("input", { type: "password", maxlength: 50, autocomplete: "new-password", class: "grow" });
  if (!await confirmWin(T("Сменить пароль"), [h("div", { class: "muted" }, login || ""),
    h("div", { class: "row" }, h("span", null, T("Новый пароль")), p1), h("div", { class: "row" }, h("span", null, T("Ещё раз")), p2),
    h("div", { class: "muted small" }, "Как в клиенте: до 50 знаков, только латиница, цифры и печатные знаки ASCII; ведущие пробелы клиент отбрасывает. Замок неудач снимается. Пароль в журнал не пишется; отменить смену нельзя — только задать новый.")])) return;
  const params = { uid: +uid, password: p1.value };
  try {                                     // перепроверка 14 М: пароль затирается при любом выходе (отказ, отмена, ошибка)
    if (p1.value !== p2.value) return notify(T("пароли не совпадают"), "bad");
    let p;
    try { p = await op("account.set_password", params, true); } catch (e) { return notify(e.message, "bad"); }
    if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
      (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
    try { const x = await op("account.set_password", Object.assign({ expect: p.preview.expect }, params), false); notify(x.message || T("готово")); rerender(); }
    catch (e) { notify(e.message, "bad"); }
  } finally { p1.value = p2.value = ""; params.password = ""; }
}
// ---------- создать игровую учётку (domains/accountnew.py: как UP_AC_CreateAccount, P52) ----------
async function createAccount() {
  const lg = h("input", { type: "text", maxlength: 32, autocomplete: "off", class: "grow" });
  const p1 = h("input", { type: "password", maxlength: 50, autocomplete: "new-password", class: "grow" });
  const p2 = h("input", { type: "password", maxlength: 50, autocomplete: "new-password", class: "grow" });
  if (!await confirmWin(T("Создать учётку"), [h("div", { class: "row" }, h("span", null, T("Логин")), lg),
    h("div", { class: "row" }, h("span", null, T("Пароль")), p1), h("div", { class: "row" }, h("span", null, T("Ещё раз")), p2),
    h("div", { class: "muted small" }, "Логин — до 32 знаков: латиница, цифры и _ . @ -; занятость проверяется без учёта регистра. Пароль — как в клиенте: до 50 знаков, печатные знаки ASCII. Удалить учётку панель не может — только заблокировать.")])) return;
  const params = { login: lg.value.trim(), password: p1.value };
  try {
    if (p1.value !== p2.value) return notify(T("пароли не совпадают"), "bad");
    let p;
    try { p = await op("account.create", params, true); } catch (e) { return notify(e.message, "bad"); }
    if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
      (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
    try {
      const x = await op("account.create", Object.assign({ expect: p.preview.expect }, params), false);
      notify(x.message || T("готово"));
      if (x.result && x.result.uid) location.hash = "#/account/" + x.result.uid;
    } catch (e) { notify(e.message, "bad"); }
  } finally { p1.value = p2.value = ""; params.password = ""; }
}
async function pwUnlock(uid, rerender) {
  const params = { uid: +uid };
  let p;
  try { p = await op("account.pw_unlock", params, true); } catch (e) { return notify(e.message, "bad"); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    h("div", { class: "muted small" }, "Сервер запирает вход после 10 неудач подряд на 15 минут. Действие попадёт в журнал, его можно откатить, пока не было новых входов.")])) return;
  try { const x = await op("account.pw_unlock", Object.assign({ expect: p.preview.expect }, params), false); notify(x.message || T("готово")); rerender(); }
  catch (e) { notify(e.message, "bad"); }
}

// ---------- 19.11 «Учётки»: закрыть, GM-флаг, служебная учётка, бан Discord (accountclose.py, gmflag.py, accountnew.py) ----------
// Предпросмотр → подтверждение → запись; если игрок был в игре и мост его вывел («кик + запись») — новый предпросмотр на подтверждение.
async function accountRun(name, params, note, okText) {
  let p;
  try { p = await op(name, params, true); } catch (e) { notify(e.message, true); return null; }
  const ask = (pv) => confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(pv.text)),
    (pv.warnings || []).map(w => h("div", { class: "note" }, T(w))), note ? h("div", { class: "muted small" }, note) : null], okText);
  if (!await ask(p.preview)) return null;
  try {
    let x = await op(name, Object.assign({ expect: p.preview.expect }, params), false);
    if (x.dry && x.kicked) {
      notify(T(x.message || "игрок отключён"));
      if (!await ask(x.preview)) return null;
      x = await op(name, Object.assign({ expect: x.preview.expect }, params), false);
    }
    notify(T(x.message || "готово"));
    return x;
  } catch (e) { notify(e.message, true); return null; }
}
async function closeAccount(uid, login, rerender) {
  const reason = h("input", { type: "text", maxlength: 280, placeholder: T("причина (латиницей, необязательно)"), class: "grow" });
  const pwBox = h("input", { type: "checkbox", class: "chk" });
  const kickBox = h("input", { type: "checkbox", class: "chk", checked: true });
  if (!await confirmWin(T("Закрыть учётку"), [h("div", { class: "muted" }, login || ""),
    h("div", { class: "row" }, h("span", null, T("Причина")), reason),
    h("label", { class: "row chkl" }, pwBox, h("span", null, T("сменить пароль на случайный (никто его не узнает)"))),
    h("label", { class: "row chkl" }, kickBox, h("span", null, T("игрок в игре — отключить с сервера (мост)"))),
    h("div", { class: "muted small" }, "Закрыть = блок навсегда; строки учётки не удаляются. Откат журналом снимает блок и возвращает прежний пароль, если его меняли.")], "Далее")) return;
  if (await accountRun("account.close", { uid: +uid, reason: reason.value.trim(), password_reset: pwBox.checked, kick: kickBox.checked },
    "Действие попадёт в журнал, его можно откатить.", "Закрыть учётку")) rerender();
}
async function gmFlag(uid, grant, rerender) {
  const kickBox = h("input", { type: "checkbox", class: "chk" });
  if (!await confirmWin(T(grant ? "Выдать GM-флаг" : "Снять GM-флаг"), [
    h("div", { class: "muted small" }, grant ? "Только служебные учётки (номер ≤ 5000). Флаг действует со следующей загрузки персонажа."
      : "Снять можно у любой учётки. Флаг перестаёт действовать со следующей загрузки персонажа."),
    h("label", { class: "row chkl" }, kickBox, h("span", null, T("игрок в игре — отключить с сервера (мост), чтобы флаг подействовал сразу")))], "Далее")) return;
  if (await accountRun(grant ? "account.gm_grant" : "account.gm_revoke", { uid: +uid, kick: kickBox.checked },
    "Действие попадёт в журнал, его можно откатить.")) rerender();
}
// бан в Discord, а вход не заблокирован — блок навсегда одной кнопкой (оператор; сама панель не блокирует)
async function discordBlock(uid, rerender) {
  if (await accountRun("account.block", { uid: +uid, hours: -1, reason: "banned in Discord registry (BANNED_PLAYERS.md)" },
    "Блок навсегда (30 лет), как в реестре банов Discord. Действие попадёт в журнал, его можно откатить.", "Заблокировать")) rerender();
}
async function createServiceAccount() {
  const lg = h("input", { type: "text", maxlength: 32, autocomplete: "off", class: "grow" });
  const p1 = h("input", { type: "password", maxlength: 50, autocomplete: "new-password", class: "grow" });
  const p2 = h("input", { type: "password", maxlength: 50, autocomplete: "new-password", class: "grow" });
  if (!await confirmWin(T("Создать служебную учётку"), [h("div", { class: "row" }, h("span", null, T("Логин")), lg),
    h("div", { class: "row" }, h("span", null, T("Пароль")), p1), h("div", { class: "row" }, h("span", null, T("Ещё раз")), p2),
    h("div", { class: "muted small" }, "Номер — наименьший свободный после занятых служебных (≤ 5000). GM-флаг — отдельной кнопкой в карточке. Удалить учётку панель не может — только закрыть.")])) return;
  const params = { login: lg.value.trim(), password: p1.value };
  try {
    if (p1.value !== p2.value) return notify(T("пароли не совпадают"), "bad");
    const x = await accountRun("account.create_service", params, null, "Создать");
    if (x && x.result && x.result.uid) location.hash = "#/account/" + x.result.uid;
  } finally { p1.value = p2.value = ""; params.password = ""; }
}
async function discordBans(out) {
  put(out, h("div", { class: "muted" }, "Загружаю…"));
  let r;
  try { r = await api("/api/players/discord_bans"); } catch (e) { return put(out, errbox(e)); }
  if (!r.items) return put(out, h("div", { class: "muted" }, "Копии реестра банов Discord нет (её кладёт выкладка)."));
  const bad = r.items.filter(x => x.mismatch).length;
  put(out, h("div", { class: "muted small" }, T("Реестр банов Discord: {0} учёток, из них вход в игру открыт у {1}.", r.items.length, bad)),
    table([["Учётка", x => x.Userindex], ["Логин (реестр)", x => x.login], ["Логин (игра)", x => x.exists ? x.Us_id : T("нет в игре")],
      ["Блок входа", x => x.block ? blockBadge(x.block, true) : "—"],
      ["", x => x.mismatch ? [badge("в Discord бан, вход открыт", "warn"), can("players.block")
        ? h("button", { type: "button", onclick: (ev) => { ev.stopPropagation(); discordBlock(x.Userindex, () => discordBans(out)); } }, "Заблокировать") : null] : null]],
      r.items, x => { if (x.exists) location.hash = "#/account/" + x.Userindex; }));
}
// gp7: покупки и подарки страницами (только просмотр)
function gp7View(uid, r) {
  const box = h("div");
  const load = async (kind, page) => {
    put(box, h("div", { class: "muted" }, "Загружаю…"));
    let d;
    try { d = await api("/api/players/gp7/" + uid + "?kind=" + kind + "&page=" + page); } catch (e) { return put(box, errbox(e)); }
    const go = pg => load(kind, pg);
    const switcher = h("div", { class: "row" }, h("button", { type: "button", class: kind === "purchases" ? "ok" : "ghost", onclick: () => load("purchases", 1) }, "Покупки"),
      h("button", { type: "button", class: kind === "gifts" ? "ok" : "ghost", onclick: () => load("gifts", 1) }, "Подарки"),
      h("span", { class: "muted small grow" }, kind === "purchases" ? T("Всего: {0} · потрачено (успешные): {1}", fmt(d.total), fmt(d.spent)) : T("Всего: {0}", fmt(d.total))),
      pager(d.page, d.pages, go));
    put(box, switcher, kind === "purchases"
      ? table([["№", p => p.id], ["Когда", p => dt(p.created_at)], ["Предмет", p => itemLine(p.item_code, p.name, null)],
               ["Цена", p => p.amount], ["Было → стало", p => fmt(p.balance_before) + " → " + fmt(p.balance_after)],
               ["", p => p.success ? badge("ок", "ok") : badge("отказ", "bad")]], d.items)
      : table([["Заказ", g => g.order_id], ["Когда", g => dt(g.created_at)], ["", g => g.sent ? badge("отправил") : badge("получил", "ok")],
               ["От", g => g.sender_name], ["Кому", g => g.recipient_name], ["Предметы", g => g.items.map(i => (i.name || i.code)).join(", ")],
               ["Цена", g => g.amount], ["Сост.", g => g.state], ["Тест", g => g.test_mode], ["Расчёт", g => dt(g.settled_at)]], d.items));
  };
  load("purchases", 1);
  return [r.gp7.user ? kv([["Логин сайта", r.gp7.user.username], ["Роль сайта", r.gp7.user.role],
      ["Баланс", r.gp7.balance ? r.gp7.balance.balance : null], ["Подарочный", r.gp7.balance ? r.gp7.balance.present : null],
      ["Обновлён", r.gp7.balance ? dt(r.gp7.balance.updated_at) : null]])
    : h("div", { class: "muted" }, "У учётки нет записи в базе сайта (AsdaStoryLogin)."),
    h("div", { class: "muted small" }, "Только просмотр: на сервере gp7 включён тестовый баланс (testFixedBalance), правка баланса не делается."), box];
}
function eacView(e) {
  if (!e) return h("div", { class: "muted" }, "нет данных");
  return [h("div", { class: "card" }, kv([["KICK от EAC получено", e.kicks.received], ["KICK выполнено", e.kicks.done],
      ["KICK не выполнено (оператор)", e.kicks.operator], ["Последний KICK", dt(e.kicks.last)]]),
    h("div", { class: "muted small" }, "Живое состояние сессии EAC и AsdaId (в памяти EacServer) панель пока не видит — сводка по журналам ac.* базы. Подробности — «Лента журналов», группа «античит».")),
    (e.errors || []).map(x => h("div", { class: "err" }, x)),
    h("h2", null, "По журналам"), table([["Журнал", t => T(t.title)], ["Таблица", t => t.table], ["Событий", t => t.n], ["Последнее", t => dt(t.last)]], e.tables),
    h("h2", null, "Последние события"), table([["Когда", x => dt(x.ev_local)], ["Журнал", x => x.table], ["Персонаж", x => x.char_name], ["Событие", x => x.kind]], e.recent)];
}

// ---------- восстановить удалённого персонажа (domains/charrestore.py → Joy1.adm.CharRestore) ----------
async function restoreChar(uid, d, rerender) {
  const nm = h("input", { type: "text", maxlength: 19, value: d.Charname || "", class: "grow" });
  const sl = h("select", null, h("option", { value: "" }, T("сам выбрать")), [10, 11, 12].map(s => h("option", { value: String(s) }, String(s))));
  if (!await confirmWin(T("Восстановить персонажа"), [h("div", { class: "row" }, h("span", null, T("Имя")), nm),
    h("div", { class: "row" }, h("span", null, T("Слот")), sl),
    h("div", { class: "muted small" }, "Прежний слот, если свободен, иначе первый свободный. Имя можно оставить или сменить (если прежнее уже занято — обязательно). Игрок — не в игре, на учётке меньше трёх персонажей. Восстановление нельзя откатить: убрать персонажа снова — удалением в игре.")])) return;
  const params = { uid: +uid, idx: d.Charidx, edate: d.ekey, name: nm.value.trim(), slot: sl.value };
  let p;
  try { p = await op("char.restore", params, true); } catch (e) { return notify(e.message, "bad"); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
  try { const x = await op("char.restore", Object.assign({ expect: p.preview.expect }, params), false); notify(x.message || T("готово")); rerender(); }
  catch (e) { notify(e.message, "bad"); }
}

// ---------- карточка учётки ----------
async function viewAccount(uid, tab) {
  tab = tab || "chars";
  const my = S.nav;
  mount(shell("#/players", h("h1", null, T("Учётка {0}", uid)), h("div", { class: "muted" }, "Загружаю…")));
  let r;
  try { r = await api("/api/players/account/" + uid); } catch (e) { return stale(my) ? null : mount(shell("#/players", h("h1", null, T("Учётка {0}", uid)), errbox(e))); }
  if (stale(my)) return;
  const a = r.account;
  const tabs = [["chars", "Персонажи"], ["warehouse", "Склады"], ["blocks", "Блокировки"], ["gp7", "Премиум-валюта"],
                ["soul", "Соулмейт"], ["deleted", "Удалённые"], ["feed", "Лента журналов"]];
  if (r.net) tabs.splice(4, 0, ["net", "Входы и связи"], ["eac", "Античит"]);
  const body = h("div");
  const V = {
    chars: () => table([["Слот", c => c.Charidx], ["Имя", c => c.Charname], ["Ур.", c => c.Lvl], ["Профессия", c => c.job],
      ["Золото", c => c.gold], ["Клан", c => c.clan], ["Карта", c => c.map ? c.map + " (" + c.Poridx + ")" : c.Poridx],
      ["Последняя запись", c => dt(c.LastDate)], ["", c => c.online ? badge("в игре по БД", "warn") : ""]],
      r.chars, c => { location.hash = "#/char/" + uid + "/" + c.Charidx; }),
    warehouse: () => bagList(r.warehouse, "Склады всех персонажей учётки (у каждого персонажа свой склад; чей — «Слот персонажа» в подробностях предмета). Двигать предметы — в карточке персонажа, вкладка «Инвентарь»."),
    blocks: () => [can("players.block") ? blockPanel(uid, a, r.blocks, () => viewAccount(uid, "blocks")) : null,
      can("ac.view") ? h("div", { class: "row" }, h("button", { type: "button", class: "ghost", onclick: () => { location.hash = "#/cases?uid=" + uid; } }, "Дела античита учётки"),
        h("span", { class: "muted small" }, "блок по делу — с причиной AC-NNNN, снятие по делу — там же")) : null,
      a.block && a.block.state === "expired" ? h("div", { class: "note" }, "Срок блока вышел: вход игрока пройдёт, а сервер при этом перенесёт строки в историю и снимет признак блока. До следующего входа строки остаются здесь.") : null,
      h("h2", null, "Действующие"), table(blockCols(), r.blocks), h("h2", null, "История"), table(blockCols(), r.block_history)],
    gp7: () => gp7View(uid, r),
    eac: () => eacView(r.net && r.net.eac),
    net: () => [h("h2", null, "Последние входы"),
      table([["Когда", l => dt(l.Login)], ["Выход", l => dt(l.Logout)], ["Слот", l => l.Charidx], ["IP", l => l.IpAddress],
             ["MAC", l => l.Mac], ["Сост.", l => l.State]], r.net.logins),
      h("h2", null, "Связанные учётки (общий IP или MAC)"),
      h("div", { class: "muted small" }, "Глубина 1 (дальше — по клику). MAC виртуальных адаптеров (Hyper-V, VMware, VirtualBox…) и локально назначенные не в счёт. «IP (общая сеть)» — сессии шли одновременно или на адресе больше 5 учёток: это разные машины за одним NAT."),
      table([["Учётка", l => l.Userindex], ["Логин", l => l.Us_id], ["Связь", l => l.degree === "ip_net" ? badge(l.degree_title) : badge(l.degree_title, "warn")],
             ["Последний вход", l => dt(l.last)]], r.net.linked, l => { location.hash = "#/account/" + l.Userindex; })],
    // ★ 25.11.2026: у каждой стороны пары — номер, логин и персонажи (щелчок по строке — карточка второй учётки)
    soul: () => table([["№", s => s.Smidx],
      ["Эта учётка", s => smSide(s.Userindex, s.a_login, s.a_chars)], ["", () => "↔"],
      ["Соулмейт", s => smSide(s.Ouserindex, s.b_login, s.b_chars)], ["Ур.", s => s.SmLvl],
      ["Опыт", s => s.SmExp], ["Дружба", s => s.FriendShip], ["Сост.", s => s.State], ["С", s => dt(s.Regdate)]], r.soulmate,
      s => { const o = String(s.Userindex) === String(uid) ? s.Ouserindex : s.Userindex; location.hash = "#/account/" + o; }),
    deleted: () => table([["Удалён", d => dt(d.Edate)], ["Слот", d => d.Charidx], ["Имя", d => d.Charname], ["Ур.", d => d.Lvl],
      ["Профессия", d => d.job],
      ["", d => d.restored_to ? badge(T("восстановлен в слот {0}", d.restored_to))
        : can("players.restore") ? h("button", { type: "button", onclick: (ev) => { ev.stopPropagation(); restoreChar(uid, d, () => viewAccount(uid, "deleted")); } }, "Восстановить") : null]],
      r.deleted),
    feed: () => feedView(uid, null),
  };
  const show = (k) => {
    history.replaceState(null, "", "#/account/" + uid + "/" + k);
    put(tabsEl, tabs.map(([id, t]) => h("a", { class: id === k ? "on" : "", onclick: () => show(id) }, t)));
    try { put(body, V[k]()); } catch (e) { put(body, errbox(e)); }
  };
  const tabsEl = h("div", { class: "tabs" });
  mount(shell("#/players",
    h("div", { class: "row" }, h("h1", { class: "grow" }, T("Учётка {0}", a.Userindex) + " · " + (a.Us_id || "?")),
      blockBadge(a.block, true), r.service ? badge("служебная (оператор)") : null,
      can("players.clear_online") && (a.Flag !== 0 || a.UserNum !== -1 || r.chars.some(c => c.online || c.stuck_state))
        ? h("button", { type: "button", onclick: () => clearOnline(uid, () => viewAccount(uid, tab)) }, "Снять залипший «в игре»") : null,
      can("players.password") ? h("button", { type: "button", onclick: () => setPassword(uid, a.Us_id, () => viewAccount(uid, tab)) }, "Сменить пароль") : null,
      can("players.password") && (a.us_pwfail || a.us_pwfail_at)
        ? h("button", { type: "button", onclick: () => pwUnlock(uid, () => viewAccount(uid, tab)) }, "Снять замок пароля") : null,
      r.closed ? badge("закрыта", "bad") : can("accounts.close") && (!r.service || S.me.user.role === "owner")   /* ★ ревизия 59 М-2: роль — в S.me.user (/api/me) */
        ? h("button", { type: "button", onclick: () => closeAccount(uid, a.Us_id, () => viewAccount(uid, tab)) }, "Закрыть учётку") : null,
      can("accounts.gm_flag") && r.service
        ? h("button", { type: "button", onclick: () => gmFlag(uid, !r.gm.length, () => viewAccount(uid, tab)) }, r.gm.length ? "Снять GM-флаг" : "Выдать GM-флаг") : null,
      can("chat.view") ? h("button", { type: "button", class: "ghost", onclick: () => { location.hash = "#/chat?account=" + uid; } }, "Чат учётки") : null),   /* ★ А6.12 */
    r.discord && r.discord.mismatch ? h("div", { class: "note" }, T("Учётка в реестре банов Discord, но вход в игру не заблокирован."), " ",
      can("players.block") ? h("button", { type: "button", onclick: () => discordBlock(uid, () => viewAccount(uid, tab)) }, "Заблокировать навсегда") : null) : null,
    r.gm_warning ? h("div", { class: "err" }, "У игровой учётки (номер > 5000) есть строка CharGmInfo: GM-команд она не даёт, но обходит EAC-кик (P73), автоблок (P69), правила имени (P68) и даёт невидимость (P81).",
      can("accounts.gm_flag") ? [" ", h("button", { type: "button", onclick: () => gmFlag(uid, false, () => viewAccount(uid, tab)) }, "Снять GM-флаг")] : null) : null,
    h("div", { class: "card" }, kv([["Логин", a.Us_id], ["Создана", dt(a.us_rdate)], ["Пароль задан", a.has_password ? dt(a.us_pwset) : T("нет")],
      ["Неудач входа подряд", a.pw_locked_until ? [String(a.us_pwfail), " ", badge(T("заперт до {0}", dt(a.pw_locked_until)))] : a.us_pwfail],
      ["Флаг «в игре»", a.Flag], ["Номер в сессии", a.UserNum],
      ["Операторские строки", r.gm.length ? r.gm.map(g => T("слот {0} (флаг {1})", g.Charidx, g.GMFlag)).join(", ") : T("нет")],
      ["Discord", discordLine(r.discord)]])),
    tabsEl, body));
  show(tabs.some(t => t[0] === tab) ? tab : "chars");
}
function discordLine(d) {
  if (!d) return null;
  if (d.error) return T(d.error);
  const parts = [];
  if (d.handle) parts.push("@" + d.handle + " (" + d.discord_id + ")");
  else parts.push(T("нет привязки"));
  if (d.list_banned) parts.push(badge(T("бан в списке бота {0}", d.list_banned), "bad"));
  if (d.banned_registry) parts.push(badge("в реестре банов", "bad"));
  if (!d.registry_known) parts.push(badge("реестра банов нет"));
  return h("span", null, parts.map((x, i) => [i ? " " : null, x]));
}
function blockCols() {
  return [["№", b => b.Cou], ["Степень", b => b.grade], ["С", b => dt(b.BlackDate)],
          ["По", b => [dt(b.CloseDate), b.expired ? " " : null, b.expired ? badge("истёк") : null]], ["Причина", b => b.Reason]];
}
// Блок как его видит сервер при входе (domains/players.block_state): действует / истёк (снимется при входе) / нет.
function blockBadge(b, long) {
  if (!b || b.state === "none") return long ? badge("не заблокирована", "ok") : null;
  if (b.state === "expired") return badge(long ? "блок истёк — снимется при входе" : "блок истёк");
  return badge(long ? (b.until ? T("заблокирована до {0}", dt(b.until)) : "заблокирована") : "блок", "bad");
}

// ---------- сумка списком (склады учётки): сетка иконок + подробности ----------
function bagList(items, caption) {
  const info = h("div", { class: "card" }, h("div", { class: "muted" }, "Нажмите на предмет — здесь появятся подробности."));
  let sel = null;
  const grid = h("div", { class: "bag" }, items.map(it => {
    const s = slotCell(it);
    s.addEventListener("click", () => { if (sel) sel.classList.remove("sel"); sel = s; s.classList.add("sel"); put(info, itemDetails(it)); });
    return s;
  }));
  return [caption ? h("div", { class: "muted small" }, caption) : null, items.length ? grid : h("div", { class: "muted" }, "пусто"), h("div", { style: { height: "10px" } }), info];
}
function slotCell(it, cls) {
  const s = h("div", { class: "slot" + (cls ? " " + cls : ""), title: it ? iname(it) + (it.Upcount ? " +" + it.Upcount : "") : null },
    it ? icon(it.icon) : null,
    it && it.Amount > 1 ? h("span", { class: "qty" }, it.Amount) : null, it && it.Upcount ? h("span", { class: "up" }, "+" + it.Upcount) : null);
  return s;
}
function itemDetails(it) {
  const other = S.lang === "en" ? it.name : it.name_en;
  return [h("div", { class: "itemline" }, icon(it.icon), h("div", null, h("b", null, iname(it)),
      h("div", { class: "muted small" }, other && other !== iname(it) ? other : ""))),
    kv([["Код", String(it.Code)], ["Сумка / ячейка", (T(PLATE_TITLES[it.Plate] || "") || it.Plate) + " · " + it.Posx], ["Слот персонажа", it.Charidx],
        ["Количество / заряды", it.Amount], ["Прочность", it.Durability],
        ["Вес", it.Weight], ["Улучшение", T("{0} (накоплено {1}, предел {2})", it.Upcount, fmt(it.AcuUpcnt), fmt(it.MaxupCnt))],
        ["Урон улучшения", it.Updamage], ["Очистка", it.Refine], ["Владелец (привязка)", it.Owner],
        ["Получен", dt(it.GainDate)], ["Срок до", dt(it.Fdate)], ["Rdate", dt(it.Rdate)],
        ["Опции", it.options.length ? it.options.map(o => "№" + o.slot + ": " + o.id + " = " + o.value).join("; ") : T("нет")],
        ["Камни", it.sockets.length ? h("div", null, it.sockets.map(s => h("div", null, itemLine(s.code, s.name || s.ru, s.icon)))) : T("нет")],
        ["Серийный номер", h("a", { class: "mono", href: "#/trace/" + it.Uuid }, it.Uuid)]])];
}
const PLATE_TITLES = { 1: "Снаряжение", 2: "Расходники", 3: "Надето", 5: "Склад" };

// ---------- ОКНО ИНВЕНТАРЯ как в игре (владелец 16.11: «сделай как настоящее окно инвентаря в игре; двигать
// предметы, надевать/снимать снаряжение»). Доска экипировки — картинка из разметки окна INVEN_WIN (tools/build_skin.py,
// /skin/inven_board.png), предметы — на позициях EQUIP_SET0…10 (skin.json → inven_board.slots); ниже — вкладки сумок и
// сетка ячеек Slot_Base (10 в ряд, сколько ячеек в сумке у сервера). Перетаскивание: внутри сумки — переставить/обменять,
// из сумки на доску — надеть, с доски в сумку — снять; двойной щелчок — надеть/снять. Каждое действие — операция
// items.move: предпросмотр → подтверждение → запись (только когда игрок не в игре) → журнал с откатом.
function invView(r, uid, idx, rerender) {
  const board = (S.skin && S.skin.inven_board) || { w: 219, h: 200, slots: {} };
  const cells = {};
  r.bags.forEach(b => b.items.forEach(it => { cells[it.Plate + ":" + it.Posx] = it; }));
  const edit = can("players.items_edit") && r.editable;
  const props = can("players.items_props") && r.editable;     // золото и свойства — отдельное право (перепроверка А1 В6)
  const give = can("players.items_give") && r.editable;      // выдать / изъять предмет (18.11)
  const info = h("div", { class: "card inv-info" }, h("div", { class: "muted" }, "Нажмите на предмет — здесь появятся подробности."));
  let selEl = null;
  const select = (el, it) => {
    if (selEl) selEl.classList.remove("sel");
    selEl = el; el.classList.add("sel");
    const editBtn = props && it.Code >= 20551 && [1, 2, 3, 5].includes(it.Plate)
      ? h("button", { type: "button", class: "gold", onclick: () => itemEditor(info, uid, idx, it, rerender) }, "Изменить свойства") : null;
    const takeBtn = give && it.Code !== 20551 && [1, 2, 5].includes(it.Plate)          // 18.11: изъять (domains/itemgive.py)
      ? h("button", { type: "button", onclick: () => takeItem(uid, idx, it, rerender) }, "Изъять") : null;
    put(info, itemDetails(it), editBtn || takeBtn ? h("div", { class: "row end" }, editBtn, takeBtn) : null);
  };
  const move = async (src, dst) => {
    const params = { uid: +uid, idx: +idx, src: { plate: src.plate, posx: src.posx }, dst, uuid: src.uuid };
    let pv;
    try { pv = await op("items.move", params, true); } catch (e) { return notify(e.message, true); }
    const p = pv.preview;
    const ok = await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.text)),
      p.warnings.map(w => h("div", { class: "note" }, T(w))),
      h("div", { class: "muted small" }, "Запись — только пока игрок не в игре; действие попадёт в журнал, его можно откатить.")]);
    if (!ok) return;
    try { const x = await op("items.move", Object.assign({ expect: p.expect }, params), false); notify(T(x.message || "готово")); rerender(); }
    catch (e) { notify(e.message, true); }
  };
  const makeCell = (plate, posx, cls) => {
    const it = cells[plate + ":" + posx];
    if (plate === 2 && r.gold_posx === posx && !it) {     // ячейка золота: занята, но золото не перекладывается (ревизия R8)
      const g = h("div", { class: "slot gold", title: T("золото") + ": " + fmt(r.gold || 0) }, h("i", { class: "goldico big" }));
      return g;
    }
    const el = slotCell(it, cls);
    el.dataset.plate = plate; el.dataset.posx = posx;
    if (it) {
      el.addEventListener("click", () => select(el, it));
      if (edit) {
        el.draggable = true;
        el.addEventListener("dragstart", (ev) => { S.drag = { plate, posx, uuid: it.Uuid }; ev.dataTransfer.effectAllowed = "move"; ev.dataTransfer.setData("text/plain", it.Uuid); });
        el.addEventListener("dragend", () => { setTimeout(() => { S.drag = null; }, 0); });   // отменённое перетаскивание
        if (plate !== 5) el.addEventListener("dblclick", () => move({ plate, posx, uuid: it.Uuid },
          plate === 3 ? { plate: 0 } : { plate: 3 }).catch(() => {}));
      }
    }
    if (edit) {
      el.addEventListener("dragover", (ev) => { if (S.drag) { ev.preventDefault(); el.classList.add("over"); } });
      el.addEventListener("dragleave", () => el.classList.remove("over"));
      el.addEventListener("drop", (ev) => {
        ev.preventDefault(); el.classList.remove("over");
        const d = S.drag; S.drag = null;
        if (!d || (d.plate === plate && d.posx === posx)) return;
        move(d, { plate, posx });
      });
    }
    return el;
  };
  // доска экипировки
  const boardEl = h("div", { class: "inv-board" });
  boardEl.style.width = board.w + "px"; boardEl.style.height = board.h + "px";
  for (let n = 0; n < 11; n++) {
    const pos = board.slots[String(n)] || [0, 0];
    const c = makeCell(3, n, "eslot");
    c.style.left = pos[0] + "px"; c.style.top = pos[1] + "px";
    if (!cells["3:" + n]) c.title = T(r.slot_names[n] || "");
    boardEl.append(c);
  }
  const arrow = h("button", { type: "button", class: "inv-arrow", title: "подробности предмета",
    onclick: () => info.classList.toggle("hidden") });
  boardEl.append(arrow);
  // вкладки сумок и сетка
  const tabsEl = h("div", { class: "tabs inv-tabs" });
  const grid = h("div", { class: "inv-grid" });
  const showPlate = (plate) => {
    S.invPlate = plate;
    put(tabsEl, [1, 2, 5].map(p => {
      const a = h("a", { class: p === plate ? "on" : "", onclick: () => showPlate(p) }, T(PLATE_TITLES[p]));
      if (edit) {   // бросок на вкладку: снять в эту сумку (первая свободная ячейка)
        a.addEventListener("dragover", (ev) => { if (S.drag && S.drag.plate === 3) ev.preventDefault(); });
        a.addEventListener("drop", (ev) => { ev.preventDefault(); const d = S.drag; S.drag = null; if (d) move(d, { plate: p }); });
      }
      return a;
    }));
    const cap = (r.caps && r.caps[plate]) || 0;
    put(grid, cap ? Array.from({ length: cap }, (_, x) => makeCell(plate, x)) : h("div", { class: "muted" }, "у персонажа нет ячеек в этой сумке"));
  };
  showPlate([1, 2, 5].includes(S.invPlate) ? S.invPlate : 1);
  const goldBox = h("div", { class: "inv-gold" });
  const showGold = () => put(goldBox, h("span", null, fmt(r.gold || 0)), h("i", { class: "goldico" }),
    props ? h("button", { type: "button", class: "icobtn pencil", title: "изменить золото", onclick: editGold }) : null);
  // владелец 16.11: «карандаш у золота → поле с текущей суммой, галочка — сохранить, крестик — отмена»
  const editGold = () => {
    const inp = h("input", { class: "goldin", inputmode: "numeric", value: String(r.gold || 0) });
    const save = async () => {
      const amount = inp.value.replace(/[\s,]/g, "");
      if (!/^\d{1,10}$/.test(amount)) return notify(T("золото — целое число от 0 до 2 147 483 647"), true);
      let pv;
      try { pv = await op("gold.set", { uid: +uid, idx: +idx, amount }, true); } catch (e) { return notify(e.message, true); }
      if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(pv.preview.text)),
        (pv.preview.warnings || []).map(w => h("div", { class: "note" }, T(w))),
        h("div", { class: "muted small" }, "Запись — только пока игрок не в игре; действие попадёт в журнал, его можно откатить.")])) return;
      try { const x = await op("gold.set", { uid: +uid, idx: +idx, amount, expect: pv.preview.expect }, false); notify(x.message); rerender(); } catch (e) { notify(e.message, true); }
    };
    inp.addEventListener("keydown", (ev) => { if (ev.key === "Enter") save(); if (ev.key === "Escape") showGold(); });
    put(goldBox, inp, h("i", { class: "goldico" }),
      h("button", { type: "button", class: "icobtn ok", title: "сохранить", onclick: save }),
      h("button", { type: "button", class: "icobtn cancel", title: "отмена", onclick: showGold }));
    inp.focus(); inp.select();
  };
  showGold();
  return h("div", { class: "inv" },
    h("div", { class: "inv-left" },
      edit ? h("div", { class: "muted small" }, "Перетащите предмет: внутри сумки — переставить, на доску — надеть, с доски — снять. Двойной щелчок — надеть / снять.")
        : h("div", { class: "note" }, can("players.items_edit") ? T("Правка закрыта: {0}", T(r.edit_block || "")) : T("Только просмотр: нет права «двигать предметы».")),
      boardEl, tabsEl, h("div", { class: "inv-panel" }, grid,
        goldBox),
      give ? h("div", { class: "row" }, h("button", { type: "button", class: "gold", onclick: () => giveItem(uid, idx, rerender) }, "Выдать предмет")) : null),
    info);
}

// ---------- правка свойств экземпляра предмета (владелец 16.11: «улучшение, характеристики, эффекты, доп. свойства —
// в выпадающих списках только то, что допустимо для этого предмета»). Варианты присылает служба (/api/items/editinfo):
// они взяты из живых таблиц сервера и повторяют его правила (domains/itemedit.py). Сохранение — операция items.edit.
function upgradeValue(growth, t, base, up) {          // = srvtables.upgrade_value (GameServer.c:99018-99035)
  const i16 = v => { v &= 0xFFFF; return v >= 0x8000 ? v - 0x10000 : v; };
  let v = i16(base); const g = growth[t];
  for (let i = 6; i < Math.min(up, 20); i++) {
    if (!g) break;
    if (g[0] === 1) v = i16(v + g[1]);
    else if (g[0] === 2) { const d = Math.trunc(g[1] * v / 100); v = i16(v + (d > 0 ? d : 1)); }
  }
  return v;
}
// Перепроверка А1 К1: в КАЖДОМ списке первым идёт «как есть: …» (выбран по умолчанию), и на службу уходит ТОЛЬКО то, что
// изменили. Нестандартное текущее значение (вне правил сервера) так не сотрётся при правке соседнего поля.
const KEEP = "__keep";
const optText = (fmtStr) => String(fmtStr).replace(/\s*[+-]?%d%{0,2}/, "").trim();
async function itemEditor(box, uid, idx, it, rerender) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let d;
  try { d = await api("/api/items/editinfo?uid=" + uid + "&idx=" + idx + "&uuid=" + encodeURIComponent(it.Uuid)); }
  catch (e) { return put(box, errbox(e), h("div", { class: "row end" }, h("button", { type: "button", onclick: () => put(box, itemDetails(it)) }, "Назад"))); }
  const sel = (opts, cur, onch) => {
    const s = h("select", null, opts.map(([v, t]) => h("option", { value: String(v), selected: String(v) === String(cur) }, t)));
    if (onch) s.addEventListener("change", onch);
    return s;
  };
  // выше max_normal шанс OverUpgrade нулевой — заточить можно только 100%-м свитком (тип 91; перепроверка 5 В1)
  const upOpts = Array.from({ length: d.upcount_max + 1 }, (_, i) =>
    [i, "+" + i + (i > d.upgrade.max_normal ? " " + T("(только 100%-м свитком)") : "")]);
  if (d.upcount > d.upcount_max) upOpts.push([d.upcount, "+" + d.upcount + " " + T("(как есть)")]);
  const upSel = sel(upOpts, d.upcount);
  const curUp = () => +upSel.value;
  // «+N%» заточки (Updamage): сумма шагов удачных заточек; шаг за ступень — из свитков сервера (+ усилитель).
  // Без выбора: при смене ступени прежний процент за ступень сохраняется (как itemedit.auto_updamage). Точную сумму
  // (ближайшую набираемую шагами свитков) считает служба — её показывает подтверждение.
  const avg = d.upcount > 0 ? Math.round(d.updamage / d.upcount * 10) / 10 : 0;
  const keepTxt = d.upcount > 0 && d.updamage > 0 ? T("как есть: {0} % за ступень", avg)
    : d.upcount > 0 ? T("как есть: 0 % (ступень без прибавки — выберите шаг)")      // перепроверка 5 В2
    : T("по умолчанию: {0} % за ступень", d.upgrade.default_step);
  const stepSel = sel([[KEEP, keepTxt]]
    .concat(d.upgrade.steps.map(s => [s, T("{0} % за ступень", s) + (d.upgrade.base_steps.indexOf(s) < 0 ? " " + T("(с усилителем)") : "")])), KEEP);
  const upTotal = () => {
    const up = curUp();
    if (up <= 0) return 0;
    if (stepSel.value !== KEEP) return up * +stepSel.value;
    if (up === d.upcount) return d.updamage;
    return d.upcount > 0 && d.updamage > 0 ? Math.floor(d.updamage * up / d.upcount + 0.5) : up * d.upgrade.default_step;
  };
  const totalEl = h("b");
  const showTotal = () => { totalEl.textContent = "≈ +" + upTotal() + "%"; };
  upSel.addEventListener("change", showTotal); stepSel.addEventListener("change", showTotal);
  showTotal();
  const durIn = h("input", { type: "number", min: 0, max: d.durability_max, value: d.durability, class: "num" });
  const ownSel = sel([[0, T("не привязан")], [1, T("привязан")]].concat(d.owner > 1 ? [[d.owner, String(d.owner)]] : []), d.owner);
  const optLabel = (fmtStr, v) => String(fmtStr).replace("%d", v).replace("%%", "%");
  const pairEls = {};
  const pairRow = (k, title) => {
    const pi = d.pairs[k];
    const cur = pi.cur;
    const keepTxt = T("как есть: {0}", cur ? cur.label : T("нет"));
    const typeSel = sel([[KEEP, keepTxt], ["", T("нет")]].concat(pi.types.map(t => [t.type, T("{0} (шанс {1} %)", optText(t.name) || t.type, t.chance)])), KEEP);
    const valSel = h("select");
    const fill = () => {
      const t = pi.types.find(x => String(x.type) === typeSel.value);
      const up = curUp();
      const curVal = cur && String(cur.type) === typeSel.value ? (k === 4 ? cur.base : cur.value) : null;
      put(valSel, t ? t.values.map(v => h("option", { value: String(v.value), selected: String(v.value) === String(curVal) },
        k === 4 ? (T("на +6: {0}", v.value) + " → " + optLabel(t.name, upgradeValue(d.growth, t.type, v.value, up)) + " " + T("(шанс {0} %)", v.chance))
                : v.label + " " + T("(шанс {0} %)", v.chance))) : []);
      valSel.style.display = t ? "" : "none";
      typeSel.disabled = (k === 4 && up < 6 && !cur) || (!pi.types.length && !cur);
    };
    typeSel.addEventListener("change", fill); upSel.addEventListener("change", fill);
    fill();
    pairEls[k] = { typeSel, valSel };
    return [h("div", null, title), h("div", { class: "row" }, typeSel, valSel,
      !pi.types.length ? h("span", { class: "muted small" }, "у предмета нет группы этих опций") : null,
      k === 4 ? h("span", { class: "muted small" }, "с +6; значение растёт с каждой ступенью, как у сервера") : null)];
  };
  const cellEls = d.cells.map(c => c.enabled || c.cur
    ? sel([[KEEP, T("как есть: {0}", c.cur ? c.cur_name : T("пусто"))], ["", T("пусто")]].concat(
        c.enabled ? c.options.map(o => [o.code, T("{0} (ур. {1})", o.name, o.lvl)]) : []), KEEP)
    : h("span", { class: "muted small" }, c.socket === 0 ? T("гнёзд нет") : T("нет гнезда")));
  const err = h("div", { class: "err" });
  const save = async () => {
    err.textContent = "";
    const set = {};
    if (+upSel.value !== d.upcount) set.upcount = +upSel.value;
    if (stepSel.value !== KEEP) set.upstep = +stepSel.value;          // сумму считает служба (ближайшую набираемую)
    if (durIn.value !== "" && +durIn.value !== d.durability) set.durability = +durIn.value;
    if (+ownSel.value !== d.owner) set.owner = +ownSel.value;
    const pairs = {};
    for (const k of [1, 2, 4, 5]) {
      const e = pairEls[k];
      if (e.typeSel.value === KEEP || e.typeSel.disabled) continue;
      pairs[k] = e.typeSel.value === "" ? null : { type: +e.typeSel.value, value: +e.valSel.value };
    }
    if (Object.keys(pairs).length) set.pairs = pairs;
    const cells = {};
    d.cells.forEach((c, i) => { const el = cellEls[i]; if (el.tagName === "SELECT" && el.value !== KEEP) cells[i] = el.value === "" ? null : +el.value; });
    if (Object.keys(cells).length) set.cells = cells;
    if (!Object.keys(set).length) { err.textContent = T("ничего не меняется"); return; }
    const params = { uid: +uid, idx: +idx, uuid: d.uuid, set };
    let p;
    try { p = await op("items.edit", params, true); } catch (e) { err.textContent = e.message; return; }
    if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
      (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w))),
      h("div", { class: "muted small" }, "Запись — только пока игрок не в игре; действие попадёт в журнал, его можно откатить.")])) return;
    try { const x = await op("items.edit", Object.assign({ expect: p.preview.expect }, params), false); notify(x.message || T("готово")); rerender(); } catch (e) { err.textContent = e.message; }
  };
  put(box, h("div", { class: "itemline" }, icon(it.icon), h("div", null, h("b", null, d.name), h("div", { class: "muted small" }, T("Код {0} · уровень персонажа {1}", d.code, d.lvl_char)))),
    !d.editable ? h("div", { class: "note" }, T("Правка закрыта: {0}", T(d.edit_block || ""))) : null,
    h("div", { class: "kv edit" },
      h("div", null, "Ступень заточки"), h("div", { class: "row" }, upSel, h("span", { class: "muted small" }, T("до +{0} (порог {1} + шаги сверх порога)", d.upcount_max, d.upgrade.t44))),
      h("div", null, "Прибавка заточки"), h("div", { class: "row" }, stepSel, totalEl, h("span", { class: "muted small" }, T("это «+N%» на иконке и сила предмета в игре"))),
      h("div", null, "Прочность"), h("div", { class: "row" }, durIn, h("span", { class: "muted small" }, T("из {0}", d.durability_max))),
      h("div", null, "Привязка"), ownSel,
      pairRow(1, T("Опция 1 (создание)")), pairRow(2, T("Опция 2 (создание)")),
      h("div", null, T("Опция 3")), h("div", { class: "muted small" }, d.pair3 ? d.pair3.label + " — " + T("сервер эту пару не заполняет, только показ") : T("нет (сервер эту пару не заполняет)")),
      pairRow(4, T("Опция заточки")), pairRow(5, T("Опция высшей переработки")),
      d.cells.map((c, i) => [h("div", null, T("Гнездо {0}", i + 1) + (i === 0 ? "" : " " + T("(особые самоцветы)"))), cellEls[i]])),
    h("div", { class: "muted small" }, "Ступень меняется вместе со счётчиками заточки и прибавкой «+N%», как требует сервер; снятый самоцвет пропадает (в игре сервер вернул бы его в сумку)."),
    err,
    h("div", { class: "row end" }, h("button", { type: "button", class: "ok", disabled: !d.editable, onclick: save }, "Сохранить"),
      h("button", { type: "button", onclick: () => put(box, itemDetails(it)) }, "Отмена")));
}

// ---------- карточка персонажа ----------
// ---------- выдать предмет (domains/itemgive.py; решения владельца 18.11: сумки и склад; у брони и оружия опции выбирает
// оператор, камень — как в таблице предмета, кнопка «Случайно» — бросок как у сервера при добыче). Варианты присылает служба
// (/api/items/giveinfo, /api/items/giveroll) из живых таблиц сервера.
async function giveItem(uid, idx, rerender) {
  const q = h("input", { placeholder: T("код или часть названия"), class: "wide" });
  const found = h("div", { class: "picklist" });
  const form = h("div");
  const err = h("div", { class: "err" });
  let d = null, els = {};
  const showForm = () => {
    if (!d) return put(form);
    const qty = h("input", { type: "number", min: 1, max: d.stack ? 1000000 : 60, step: 1, value: 1, class: "num" });
    const to = h("select", null, h("option", { value: "bag" }, T(d.plate === 1 ? "сумка 1 (снаряжение)" : "сумка 2 (расходники)")),
      h("option", { value: "ware" }, T("склад")));
    els = { qty, to };
    const rows = [[T("Количество"), qty], [T("Куда"), to]];
    if (d.pairs) {
      const pair = (k) => {
        const pi = d.pairs[k] || [];
        const typeSel = h("select", null, [h("option", { value: "" }, T("нет"))].concat(pi.map(t =>
          h("option", { value: String(t.type) }, T("{0} (шанс {1} %)", optText(t.name) || t.type, t.chance)))));
        const valSel = h("select");
        const fill = (want) => {
          const t = pi.find(x => String(x.type) === typeSel.value);
          put(valSel, t ? t.values.map(v => h("option", { value: String(v.value), selected: String(v.value) === String(want) },
            v.label + " " + T("(шанс {0} %)", v.chance))) : []);
          valSel.style.display = t ? "" : "none";
        };
        typeSel.addEventListener("change", () => fill());
        typeSel.disabled = !pi.length;
        fill();
        els["p" + k] = { typeSel, valSel, fill };
        return [T("Опция {0}", k), h("div", { class: "row" }, typeSel, valSel,
          !pi.length ? h("span", { class: "muted small" }, "у предмета нет группы этих опций") : null)];
      };
      const stone = h("select", null, d.stones.map(s => h("option", { value: String(s.code) },
        (s.code ? s.name + " [" + s.code + "]" : T("пусто")) + " " + T("(шанс {0} %)", s.chance))));
      const up = h("select", null, d.upcounts.map(u => h("option", { value: String(u.value) }, "+" + u.value + " " + T("(шанс {0} %)", u.chance))));
      stone.disabled = d.stones.length < 2; up.disabled = d.upcounts.length < 2;
      els.stone = stone; els.up = up;
      const roll = async () => {
        let r;
        try { r = await api("/api/items/giveroll?code=" + d.code); } catch (e) { err.textContent = e.message; return; }
        for (const k of [1, 2]) {
          const e = els["p" + k], v = r.pairs[k] || r.pairs[String(k)];
          e.typeSel.value = v ? String(v.type) : ""; e.fill(v ? v.value : null);
        }
        stone.value = String(r.stone); up.value = String(r.upcount);
      };
      rows.push(pair(1), pair(2), [T("Самоцвет в гнезде"), stone], [T("Ступень"), up],
        ["", h("button", { type: "button", onclick: roll }, "Случайно")]);
    }
    put(form, h("div", { class: "itemline" }, h("b", null, d.name), h("span", { class: "muted mono" }, d.code)),
      kv(rows), d.charge ? h("div", { class: "note" }, T("заряды складываются в уже лежащий предмет того же вида (патч P100)")) : null,
      d.timed ? h("div", { class: "note" }, T("предмет со сроком: срок пойдёт с первого использования (как у сервера)")) : null);
  };
  const pick = async (code) => {
    err.textContent = "";
    try { d = await api("/api/items/giveinfo?code=" + code); } catch (e) { d = null; err.textContent = e.message; }
    showForm();
  };
  const search = async () => {
    const t = q.value.trim();
    if (!t) return put(found);
    let r;
    try { r = await api("/api/items/search?q=" + encodeURIComponent(t)); } catch (e) { err.textContent = e.message; return; }
    put(found, r.items.slice(0, 30).map(it => h("div", { class: "pick", onclick: () => pick(it.code) }, itemLine(it.code, it.name, it.icon))));
  };
  let tm = null;
  q.addEventListener("input", () => { clearTimeout(tm); tm = setTimeout(search, 300); });
  q.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { const n = +q.value.trim(); if (n) pick(n); } });
  if (!await confirmWin(T("Выдать предмет"), [h("div", { class: "row" }, q), found, form, err,
    h("div", { class: "muted small" }, "Предмет создаётся так же, как его создаёт сервер (сумка, стопка, вес, прочность — по таблицам сервера). Игрок — не в игре. Действие попадёт в журнал, его можно откатить.")], "Далее")) return;
  if (!d) return notify(T("предмет не выбран"), true);
  const params = { uid: +uid, idx: +idx, code: d.code, qty: els.qty.value, to: els.to.value };
  if (d.pairs) {
    const pairs = {};
    for (const k of [1, 2]) { const e = els["p" + k]; if (e.typeSel.value !== "") pairs[k] = { type: +e.typeSel.value, value: +e.valSel.value }; }
    params.opts = { pairs, stone: +els.stone.value, upcount: +els.up.value };
  }
  let p;
  try { p = await op("items.give", params, true); } catch (e) { return notify(e.message, true); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
  try { const x = await op("items.give", Object.assign({ expect: p.preview.expect }, params), false); notify(T(x.message || "готово")); rerender(); }
  catch (e) { notify(e.message, true); }
}

// ---------- изъять предмет (вся строка или часть стопки / зарядов; надетое — сначала снять) ----------
async function takeItem(uid, idx, it, rerender) {
  const qty = h("input", { type: "number", min: 1, max: Math.max(1, it.Amount || 1), step: 1, value: Math.max(1, it.Amount || 1), class: "num" });
  const body = [h("div", { class: "itemline" }, icon(it.icon), h("b", null, iname(it)), h("span", { class: "muted mono" }, it.Code))];
  // перепроверка 18 К6: часть — только у стопки (сумка 2 / склад, не колчан) и у зарядов спецпредмета (коды Function)
  const partial = (it.Amount || 0) > 1 && (it.Code < 7001 || (it.Code > 20551 && it.Plate !== 1));
  if (partial) body.push(h("div", { class: "row" }, h("span", null, T("Сколько (из {0})", it.Amount)), qty));
  if (!await confirmWin(T("Изъять предмет"), body, "Далее")) return;
  const params = { uid: +uid, idx: +idx, plate: it.Plate, posx: it.Posx, uuid: it.Uuid };
  if (partial && +qty.value < it.Amount) params.qty = +qty.value;
  let p;
  try { p = await op("items.take", params, true); } catch (e) { return notify(e.message, true); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
  try { const x = await op("items.take", Object.assign({ expect: p.preview.expect }, params), false); notify(T(x.message || "готово")); rerender(); }
  catch (e) { notify(e.message, true); }
}

async function viewChar(uid, idx, tab) {
  tab = tab || "sum";
  const my = S.nav;
  mount(shell("#/players", h("h1", null, T("Персонаж {0}", uid + "/" + idx)), h("div", { class: "muted" }, "Загружаю…")));
  let r;
  try { await loadSkin(); r = await api("/api/players/char/" + uid + "/" + idx); } catch (e) { return stale(my) ? null : mount(shell("#/players", h("h1", null, "Персонаж"), errbox(e))); }
  if (stale(my)) return;
  const c = r.char, p = r.pos || {};
  const tabs = [["sum", "Сводка"], ["bags", "Инвентарь"], ["post", "Почта и аукцион"], ["skills", "Навыки"], ["pets", "Питомцы"],
                ["friends", "Друзья"], ["feed", "Лента журналов"]];
  const body = h("div");
  const stat = (n, b, pnt) => fmt(b) + (pnt ? " (+" + pnt + ")" : "");
  const V = {
    sum: () => h("div", { class: "grid2" },
      h("div", { class: "card" }, h("h2", null, "Развитие"), kv([["Уровень", c.Lvl], ["Опыт (накопительный)", c.Expe],
        ["Профессия", c.job + " (" + c.Job + ")"], ["Подкласс", c.subjob ? c.subjob + " (" + c.Subjob + ")" : c.Subjob],
        ["Смен профессии", c.JobCount], ["Очки навыков", c.SkillPoint], ["Золото", r.gold], ["Вес", fmt(c.Weight) + " / " + fmt(c.MaxWeight & 0xFFFF)],
        ["Очки активности", c.ActPoint], ["Очки пожертвований", c.DonationPoint], ["Звания (строк)", r.counts.fame],
        ["Задания (эпизоды / квесты)", r.counts.episodes + " / " + r.counts.quests]])),
      h("div", { class: "card" }, h("h2", null, "Характеристики"), kv([["ОЗ", fmt(c.Hp) + " / " + fmt(c.MaxHp)], ["ОМ", fmt(c.Mp) + " / " + fmt(c.MaxMp)],
        ["Сила", stat("", c.Strength, c.StrengthP)], ["Ловкость", stat("", c.Agility, c.AgilityP)], ["Здоровье", stat("", c.Health, c.HealthP)],
        ["Магия", stat("", c.Spell, c.SpellP)], ["Дух", stat("", c.Mentality, c.MentalityP)], ["Удача", stat("", c.Fortune, c.FortuneP)],
        ["Физ. атака", c.MinAttack + "–" + c.MaxAttack], ["Маг. атака", c.MinMagicAtt + "–" + c.MaxMagicAtt],
        ["Защита", c.MinDefense1 + "–" + c.MaxDefense1], ["Маг. защита", c.MagicDefense], ["Крит / уклонение", c.Critical + " / " + c.Evasion]])),
      h("div", { class: "card" }, h("h2", null, "Где"), kv([["Карта", (p.map || "?") + " (" + fmt(p.Poridx) + ")"], ["Клетка", fmt(p.Posx) + ", " + fmt(p.Posy)],
        ["Канал", p.Channel], ["В игре по БД", p.online ? badge("да", "warn") : T("нет")], ["Последняя запись", dt(p.LastDate)],
        ["Отряд", p.Partyidx], ["Состояние", T("{0} / душа {1}", p.State, fmt(p.SoulState))]])),
      h("div", { class: "card" }, h("h2", null, "Клан и прочее"), kv([["Клан", r.clan ? T("{0} (ур. {1})", r.clan.Cname, fmt(r.clan.Lvl)) : T("нет")],
        ["Ранг в клане", r.clan ? r.clan.Grade : null], ["Глава клана", r.clan ? r.clan.Captain : null],
        ["Оператор", r.gm ? T("да (флаг {0})", r.gm.GMFlag) : T("нет")], ["О себе", r.intro]]))),
    bags: () => invView(r, uid, idx, () => viewChar(uid, idx, "bags")),
    post: () => [h("h2", null, "Элитный почтовый ящик"),
      table([["Заказ", x => x.Orderidx], ["Вид", x => h("span", { title: "iType " + x.iType }, T(x.type || String(x.iType)))], ["Предмет", x => itemLine(x.Code, x.name, x.icon)],
             ["Шт.", x => x.Amount], ["Куплен", x => dt(x.bought)], ["Цена", x => x.price], ["Откуда", x => [x.shop ? T(x.shop) : "", x.panel ? [" ", badge("выдано панелью")] : null]]], r.postbox),
      h("div", { class: "muted small" }, "Номер предмета появляется, когда игрок забирает его из ящика (журнал CashBuy* с тем же номером заказа)."),
      h("h2", null, "Лоты аукциона"), lotTable(r.lots, false),
      h("div", { class: "muted small" }, "Истёкший лот владелец может снять сам; через 14 суток реле снимает его и (патч ac0z, 19.11) возвращает предмет в сумку, если игрок не в игре и есть место."),
      (r.locks || []).length ? [h("h3", null, "В замке аукциона (на время выставления, Plate 11/12)"),
        table([["Сумка", x => plateName(x.Plate)], ["Ячейка", x => x.Posx], ["Предмет", x => itemLine(x.Code, x.name, x.icon)], ["Шт.", x => x.Amount],
               ["Номер", x => h("a", { class: "mono small", href: "#/trace/" + x.Uuid }, x.Uuid)]], r.locks)] : null,
      h("h3", null, "Журнал лотов"),
      table([["Когда", x => dt(x.Edate)], ["Событие", x => T(x.State)], ["Предмет", x => itemLine(x.Code, x.name, null)], ["Было → стало", x => x.Amount != null ? fmt(x.Amount) + " → " + fmt(x.Ramount) : ""],
             ["Цена", x => x.Gm], ["Номер", x => x.Serial ? h("a", { class: "mono small", href: "#/trace/" + x.Serial }, x.Serial) : ""]], r.lot_log || [])],
    skills: () => table([["Код", s => s.Skillidx], ["Навык", s => s.name], ["Ур.", s => s.Lvl]], r.skills),
    pets: () => table([["№", x => x.PetUnique], ["Вид", x => x.kind + " (" + x.Petindex + ")"], ["Имя", x => x.PetName], ["Ур.", x => x.PetLvl + " / " + x.PetMaxLvl],
      ["Опыт", x => x.PetExp], ["Сытость", x => x.FullNess], ["Активен", x => !!x.Active], ["Срок", x => dt(x.Edate)]], r.pets),
    friends: () => table([["Имя", f => f.Charname], ["Учётка/слот", f => f.Fuserindex + "/" + f.Fcharidx]], r.friends,
      f => { location.hash = "#/char/" + f.Fuserindex + "/" + f.Fcharidx; }),
    feed: () => feedView(uid, idx),
  };
  const tabsEl = h("div", { class: "tabs" });
  const show = (k) => {
    history.replaceState(null, "", "#/char/" + uid + "/" + idx + "/" + k);
    put(tabsEl, tabs.map(([id, t]) => h("a", { class: id === k ? "on" : "", onclick: () => show(id) }, t)));
    try { put(body, V[k]()); } catch (e) { put(body, errbox(e)); }
  };
  mount(shell("#/players",
    h("div", { class: "row" }, h("h1", { class: "grow" }, T("{0} · ур. {1} · {2}", c.Charname, c.Lvl, c.job)),
      p.online ? badge("в игре по БД", "warn") : null, r.block && r.block.state === "active" ? badge("учётка заблокирована", "bad") : r.block && r.block.state === "expired" ? badge("блок истёк") : null,
      can("players.rename") ? h("button", { type: "button", onclick: () => renameChar(uid, idx, c.Charname, () => viewChar(uid, idx, tab)) }, "Сменить имя") : null,
      can("players.move") ? h("button", { type: "button", onclick: () => moveChar(uid, idx, () => viewChar(uid, idx, tab)) }, "Перенести") : null,
      can("players.progress") && !(r.max_level && c.Lvl >= r.max_level)
        ? h("button", { type: "button", onclick: () => levelUpChar(uid, idx, c.Lvl, r.max_level, () => viewChar(uid, idx, tab)) }, "Поднять уровень") : null,
      h("button", { type: "button", onclick: () => titlesChar(uid, idx, () => viewChar(uid, idx, tab)) }, "Звания"),
      h("button", { type: "button", onclick: () => skillsChar(uid, idx, () => viewChar(uid, idx, tab)) }, "Навыки"),
      h("button", { type: "button", onclick: () => petsChar(uid, idx, () => viewChar(uid, idx, tab)) }, "Питомцы"),
      h("button", { type: "button", onclick: () => questsChar(uid, idx, () => viewChar(uid, idx, tab)) }, "Задания"),
      h("button", { type: "button", onclick: () => charRestWin(uid, idx, () => viewChar(uid, idx, tab)) }, "Внешность, баффы, лагерь, ремесло"),
      can("players.copy") ? h("button", { type: "button", onclick: () => copyChar(uid, idx, c.Charname, () => viewChar(uid, idx, tab)) }, "Копия на служебную учётку") : null,
      h("button", { type: "button", onclick: () => soulmateChar(uid, idx, () => viewChar(uid, idx, tab)) }, "Соулмейт"),
      h("button", { type: "button", onclick: () => friendsChar(uid, idx, () => viewChar(uid, idx, tab)) }, "Друзья"),
      r.clan ? h("button", { type: "button", onclick: () => clanWin(r.clan.Clanidx, () => viewChar(uid, idx, tab)) }, "Клан") : null,
      can("players.items_give") ? h("button", { type: "button", onclick: () => postItem(uid, idx, () => viewChar(uid, idx, tab)) }, "Подарок / почта") : null,
      can("players.progress") ? h("button", { type: "button", onclick: () => expChar(uid, idx, () => viewChar(uid, idx, tab)) }, "Опыт, %") : null,
      can("server.announce") ? h("button", { type: "button", onclick: () => noticeAccount(uid) }, "Сообщение игроку") : null,
      can("players.progress") && (r.job_targets || []).length
        ? h("button", { type: "button", onclick: () => jobChangeChar(uid, idx, r.job_targets, () => viewChar(uid, idx, tab)) }, "Сменить профессию") : null),
    h("div", { class: "muted" }, T("Учётка") + " ", h("a", { href: "#/account/" + uid }, uid + " · " + (r.login || "?")), " · " + T("слот {0}", idx)),
    tabsEl, body));
  show(tabs.some(t => t[0] === tab) ? tab : "sum");
}

// ---------- смена имени (domains/rename.py: как UPCharRename + правило A13; друзья не теряются) ----------
async function renameChar(uid, idx, cur, rerender) {
  const inp = h("input", { type: "text", maxlength: 19, value: cur || "", class: "grow" });
  if (!await confirmWin(T("Сменить имя"), [h("div", { class: "row" }, h("span", null, T("Новое имя")), inp),
    h("div", { class: "muted small" }, "Как в игре: латиница и цифры, до 19 знаков, без запрещённых слов; имя должно быть свободно (и среди удалённых персонажей). Операторам можно ещё «_» (не в конце). Персонаж — не в клане и без лотов на аукционе. Игрок — не в игре.")])) return;
  const params = { uid: +uid, idx: +idx, name: inp.value.trim() };
  let p;
  try { p = await op("char.rename", params, true); } catch (e) { return notify(e.message, "bad"); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w))),
    h("div", { class: "muted small" }, "Действие попадёт в журнал, его можно откатить.")])) return;
  try { const x = await op("char.rename", Object.assign({ expect: p.preview.expect }, params), false); notify(x.message || T("готово")); rerender(); }
  catch (e) { notify(e.message, "bad"); }
}

// ---------- перенести персонажа (domains/charmove.py: только Poridx/Cporidx/Posx/Posy; точки сервера) ----------
async function moveChar(uid, idx, rerender) {
  const modes = [["village", "своя точка возрождения"], ["town:3", "Альпия (город)"], ["town:0", "Силарис (город)"],
    ["town:7", "Пламения (город)"], ["new", "как новый персонаж (старт Альпии)"]];
  if (S.me && S.me.user && (S.me.user.role === "owner" || S.me.user.role === "admin")) modes.push(["custom", "своя точка"]);   // перепроверка 17 М4
  const mode = h("select", null, modes.map(([v, t]) => h("option", { value: v }, T(t))));
  const mp = h("input", { type: "number", min: 0, max: 22, step: 1, class: "num", value: 3 });
  const x = h("input", { type: "number", min: 1, max: 511, step: 1, class: "num", value: 125 });
  const y = h("input", { type: "number", min: 1, max: 511, step: 1, class: "num", value: 390 });
  const cust = h("div", { class: "row", style: { display: "none" } }, h("span", null, T("Карта")), mp, h("span", null, "X"), x, h("span", null, "Y"), y);
  mode.addEventListener("change", () => { cust.style.display = mode.value === "custom" ? "" : "none"; });
  if (!await confirmWin(T("Перенести персонажа"), [h("div", { class: "row" }, h("span", null, T("Куда")), mode), cust,
    h("div", { class: "muted small" }, "Меняется только позиция (карта и клетка), как её читает вход в игру. Игрок — не в игре. Точки городов — те, что использует сервер; своя точка (владелец, администратор) — карта, которую сервер поднимает, кроме подземелий 10/11. Действие попадёт в журнал, его можно откатить.")])) return;
  const [m, town] = mode.value.split(":");
  const params = { uid: +uid, idx: +idx, mode: m };
  if (m === "town") params.map = +town;
  if (m === "custom") Object.assign(params, { map: mp.value, x: x.value, y: y.value });
  let p;
  try { p = await op("char.move", params, true); } catch (e) { return notify(e.message, "bad"); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
  try { const x2 = await op("char.move", Object.assign({ expect: p.preview.expect }, params), false); notify(x2.message || T("готово")); rerender(); }
  catch (e) { notify(e.message, "bad"); }
}

// ★ ревизия 25 М-4: путь правки — по предпросмотру (мост P127): живьём — сервером сразу, журналом не откатывается
function pathNote(p, offline) {
  if (p && p.preview && p.preview.live)
    return h("div", { class: "muted small" }, "Игрок в игре: правку делает сервер сразу (как событие игры). Действие попадёт в журнал; откат журналом невозможен — исправьте новым действием.");
  return h("div", { class: "muted small" }, offline || "Игрок — не в игре. Действие попадёт в журнал, его можно откатить.");
}

// ---------- поднять уровень (domains/progress.py: как повышение у сервера; понижения у сервера нет) ----------
async function levelUpChar(uid, idx, cur, top, rerender) {
  top = top || 100;
  const inp = h("input", { type: "number", min: (cur || 0) + 1, max: top, step: 1, value: Math.min(top, (cur || 0) + 1), class: "num" });
  if (!await confirmWin(T("Поднять уровень"), [h("div", { class: "row" }, h("span", null, T("Уровень {0} →", cur)), inp),
    h("div", { class: "muted small" }, "Игрок не в игре: как повышение в игре — опыт начала уровня, +2 очка навыков за уровень (если есть профессия), характеристики класса по таблице сервера; HP/MP и атаку сервер пересчитает при входе; HP/MP не станут полными, звания «за уровень» придут при следующем настоящем повышении. Игрок в игре: сервер поднимет уровень сам, событиями по одному уровню (баннер — на последнем уровне, кувшин души не наполняется — ключи P75 сервера). Понижения у сервера нет.")])) return;
  const params = { uid: +uid, idx: +idx, level: inp.value.trim() };
  let p;
  try { p = await op("char.level_up", params, true); } catch (e) { return notify(e.message, "bad"); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w))),
    pathNote(p, "Действие попадёт в журнал, его можно откатить.")])) return;
  try { const x = await op("char.level_up", Object.assign({ expect: p.preview.expect }, params), false); notify(x.message || T("готово")); rerender(); }
  catch (e) { notify(e.message, "bad"); }
}

// ---------- подарок из витрины / премиум-почта в элитный почтовый ящик (domains/gifts.py; вкладка «Подарки» старой утилиты).
// Игрок забирает сам — отправлять можно при запущенном сервере и игроку в игре; откат — пока не забрано и получатели не в игре.
async function postItem(uid, idx, rerender) {
  const kind = h("select", null, h("option", { value: "gift" }, T("подарок из витрины магазина")), h("option", { value: "mail" }, T("премиум-почта (любой предмет)")));
  const q = h("input", { placeholder: T("код или часть названия"), class: "wide" });
  const found = h("div", { class: "picklist" });
  const info = h("div");
  const err = h("div", { class: "err" });
  const qty = h("input", { type: "number", min: 1, max: 60, step: 1, value: 1, class: "num" });
  const to = h("select", null, h("option", { value: "char" }, T("этому персонажу")), h("option", { value: "account" }, T("всем персонажам учётки")),
    h("option", { value: "all" }, T("всем игрокам")));
  let d = null;
  const pick = async (code) => {
    err.textContent = "";
    try { d = await api("/api/gifts/info?kind=" + kind.value + "&code=" + code); } catch (e) { d = null; put(info); err.textContent = e.message; return; }
    put(info, h("div", { class: "itemline" }, h("b", null, d.name), h("span", { class: "muted mono" }, d.delivery)),
      d.price != null ? h("div", { class: "muted small" }, T("цена в магазине: {0} (игрок ничего не платит)", d.price)) : null,
      (d.contents || []).map(c => h("div", { class: "muted small" }, T("в коробке: {0} × {1}", c.name + " (" + c.code + ")", c.n))),
      (d.notes || []).map(n => h("div", { class: "note" }, T(n))));
  };
  const search = async () => {
    const t = q.value.trim();
    if (!t) return put(found);
    let r;
    try { r = await api((kind.value === "gift" ? "/api/gifts/catalog?q=" : "/api/items/search?q=") + encodeURIComponent(t)); } catch (e) { err.textContent = e.message; return; }
    put(found, r.items.slice(0, 30).map(it => h("div", { class: "pick", onclick: () => pick(it.code) }, itemLine(it.code, it.name, it.icon),
      it.places ? h("span", { class: "muted small" }, " " + it.places.map(p => p.shop + ": " + p.path + (p.hidden ? " (" + T("скрыто") + ")" : "")).join("; ")) : null)));
  };
  let tm = null;
  q.addEventListener("input", () => { clearTimeout(tm); tm = setTimeout(search, 300); });
  q.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { const n = +q.value.trim(); if (n) pick(n); } });
  kind.addEventListener("change", () => { d = null; put(info); put(found); search(); });
  if (!await confirmWin(T("Подарок / премиум-почта"), [h("div", { class: "row" }, h("span", null, T("Что")), kind), h("div", { class: "row" }, q), found, info,
    kv([[T("Количество"), qty], [T("Кому"), to]]), err,
    h("div", { class: "muted small" }, "В элитный почтовый ящик — так же, как кладёт покупка в магазине. Игрок забирает сам, сервер можно не выключать. Пока не забрано, действие можно откатить в журнале (когда получатели не в игре).")], "Далее")) return;
  if (!d) return notify(T("предмет не выбран"), true);
  const params = { kind: kind.value, code: d.code, qty: qty.value, to: to.value, uid: +uid, idx: +idx };
  let p;
  try { p = await op("items.post", params, true); } catch (e) { return notify(e.message, true); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
  try { const x = await op("items.post", Object.assign({ expect: p.preview.expect }, params), false); notify(T(x.message || "готово")); rerender(); }
  catch (e) { notify(e.message, true); }
}

// ---------- звания, слава, очки чести (domains/titles.py; как сервер: выдача — AddFameBit, снятие — SubFameBit) ----------
async function titlesChar(uid, idx, rerender) {
  let d;
  try { d = await api("/api/titles/char/" + uid + "/" + idx); } catch (e) { return notify(e.message, true); }
  const edit = can("players.titles"), honor = can("players.honor");
  const run = async (name, params) => {
    let p;
    try { p = await op(name, params, true); } catch (e) { return notify(e.message, true); }
    if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
      (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w))),
      p.preview.live ? h("div", { class: "muted small" }, "Игрок в игре: правку делает сервер сразу. Откат — обратной правкой, пока игрок в игре; иначе — новым действием.") : pathNote(p)])) return false;
    try { const x = await op(name, Object.assign({ expect: p.preview.expect }, params), false); notify(T(x.message || "готово")); return true; }
    catch (e) { notify(e.message, true); return false; }
  };
  const filt = h("select", null, h("option", { value: "got" }, T("полученные")), h("option", { value: "can" }, T("можно выдать")),
    h("option", { value: "all" }, T("все")));
  const q = h("input", { placeholder: T("название или номер"), class: "wide" });
  const list = h("div", { class: "picklist", style: { maxHeight: "360px" } });
  const show = () => {
    const t = q.value.trim().toLowerCase();
    const rows = d.titles.filter(x => (filt.value === "all" || (filt.value === "got" ? x.got : (!x.got && x.enabled && !x.rating && (!x.class || x.class === d.class))))
      && (!t || String(x.id) === t || (x.name || "").toLowerCase().includes(t)));
    put(list, rows.map(x => h("div", { class: "row" },
      h("span", { class: "mono" }, x.id), h("b", null, x.name || "—"), h("span", { class: "muted small" }, T("слава {0}", x.points)),
      x.got ? badge(T("получено"), "ok") : null, x.worn ? badge(T("надето")) : null, x.found && !x.got ? badge(T("найдено")) : null,
      !x.enabled ? badge(T("выключено")) : null,
      x.rating ? h("span", { class: "muted small" }, x.holder ? T("рейтинговое; держатель {0}", x.holder.join("/")) : T("рейтинговое")) : null,
      edit && !x.rating && x.got ? h("button", { type: "button", onclick: async () => { if (await run("title.revoke", { uid: +uid, idx: +idx, title: x.id })) { await reload(); } } }, "Снять") : null,
      edit && !x.rating && !x.got && x.enabled && (!x.class || x.class === d.class)
        ? h("button", { type: "button", onclick: async () => { if (await run("title.grant", { uid: +uid, idx: +idx, title: x.id })) { await reload(); } } }, "Выдать") : null)));
  };
  const head = h("div");
  const showHead = () => put(head, kv([
    [T("Слава"), h("span", null, fmt(d.fame), d.fame_sum != null && d.fame_sum !== d.fame ? " " + T("(по званиям {0})", d.fame_sum) : "",
      edit && d.fame_sum != null && d.fame_sum !== d.fame ? h("button", { type: "button", onclick: async () => { if (await run("fame.recalc", { uid: +uid, idx: +idx })) await reload(); } }, "Пересчитать славу") : null)],
    [T("Очки чести"), d.camp ? h("span", null, fmt(d.camp.CampPoint), honor ? h("button", { type: "button", onclick: async () => {
      const inp = h("input", { type: "number", min: 0, step: 1, value: d.camp.CampPoint, class: "num" });
      if (!await confirmWin(T("Очки чести"), [h("div", { class: "row" }, h("span", null, T("Очки чести")), inp),
        h("div", { class: "muted small" }, "Очки войны фракций (метка «Honor point» окна персонажа). Ступень чести сервер пересчитает при входе.")])) return;
      if (await run("honor.set", { uid: +uid, idx: +idx, value: inp.value.trim() })) await reload();
    } }, "Изменить") : null) : T("фракция не выбрана")]]));
  const reload = async () => { try { d = await api("/api/titles/char/" + uid + "/" + idx); } catch (e) { return notify(e.message, true); } showHead(); show(); };
  filt.addEventListener("change", show); q.addEventListener("input", show);
  showHead(); show();
  await confirmWin(T("Звания"), [head, h("div", { class: "row" }, filt, q), list,
    h("div", { class: "muted small" }, "Выдача и снятие — как у сервера: строка звания, маска, слава, бит «найдено», наборы. Рейтинговые 65–69 меняет только пересчёт рейтинга сервера.")], "Закрыть");
  rerender();
}

// ---------- навыки (domains/skills.py) и питомцы (domains/pets.py) — как сервер; персонаж не в игре; всё в журнал с откатом ----------
async function runOp(name, params) {
  let p;
  try { p = await op(name, params, true); } catch (e) { notify(e.message, true); return false; }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w))),
    h("div", { class: "muted small" }, "Игрок — не в игре. Действие попадёт в журнал, его можно откатить.")])) return false;
  try { const x = await op(name, Object.assign({ expect: p.preview.expect }, params), false); notify(T(x.message || "готово")); return true; }
  catch (e) { notify(e.message, true); return false; }
}
async function skillsChar(uid, idx, rerender) {
  let d;
  const load = async () => { try { d = await api("/api/skills/char/" + uid + "/" + idx); return true; } catch (e) { notify(e.message, true); return false; } };
  if (!await load()) return;
  const edit = can("players.skills");
  const base = { uid: +uid, idx: +idx };
  const head = h("div"), list = h("div", { class: "picklist", style: { maxHeight: "300px" } }), add = h("div", { class: "picklist", style: { maxHeight: "200px" } });
  const q = h("input", { placeholder: T("название или номер"), class: "wide" });
  const after = async (ok) => { if (ok && await load()) show(); };
  const show = () => {
    put(head, kv([[T("Очки навыков"), h("span", null, fmt(d.skill_point), can("players.progress") ? h("button", { type: "button", onclick: async () => {
        const inp = h("input", { type: "number", min: 0, max: 32767, step: 1, value: d.skill_point, class: "num" });
        if (!await confirmWin(T("Очки навыков"), [h("div", { class: "row" }, h("span", null, T("Очки навыков")), inp)])) return;
        after(await runOp("skill.points", Object.assign({ value: inp.value.trim() }, base)));
      } }, "Изменить") : null)],
      [T("Деревья"), h("span", null, Object.keys(d.trees).map(t => h("span", { class: "row" }, T("дерево {0}: {1}", t, d.trees[t]),
        edit ? h("button", { type: "button", onclick: async () => after(await runOp("skill.reset_tree", Object.assign({ tree: +t }, base))) }, "Сбросить дерево") : null)),
        edit ? h("button", { type: "button", onclick: async () => after(await runOp("skill.reset_all", base)) }, "Сбросить все навыки") : null)]]));
    put(list, d.learned.map(s => h("div", { class: "row" }, h("span", { class: "mono" }, s.id), h("b", null, s.name),
      h("span", { class: "muted small" }, T("уровень {0} из {1}, дерево {2}", s.lvl, s.max, s.tree)), !s.fits ? badge(T("не для профессии")) : null,
      edit ? h("button", { type: "button", onclick: async () => after(await runOp("skill.remove", Object.assign({ skill: s.id }, base))) }, "Снять") : null)));
    const t = q.value.trim().toLowerCase();
    put(add, edit ? d.available.filter(s => !t || String(s.id) === t || (s.name || "").toLowerCase().includes(t)).slice(0, 60).map(s =>
      h("div", { class: "row" }, h("span", { class: "mono" }, s.id), h("b", null, s.name), h("span", { class: "muted small" }, T("дерево {0}", s.tree)),
        h("button", { type: "button", onclick: async () => after(await runOp("skill.grant", Object.assign({ skill: s.id }, base))) }, "Выдать"))) : []);
  };
  q.addEventListener("input", show);
  show();
  await confirmWin(T("Навыки"), [head, h("h3", null, T("Изученные")), list, edit ? [h("h3", null, T("Выдать навык (уровнем 0)")), q, add] : null,
    h("div", { class: "muted small" }, "Навык выдаётся уровнем 0, как у сервера. Сброс — как свиток сброса; полный сброс исправлен: навыки без требования дерева (4-я профессия, 734, 757) остаются уровнем 0.")], "Закрыть");
  rerender();
}
// ---------- задания и эпизоды (domains/quests.py: выдать как NPC, снять, завершить с наградой, снять «выполнено») ----------
const rewardText = r => [r.exp ? T("опыт {0}", r.exp) : null, r.gold ? T("золото {0}", r.gold) : null,
  ...(r.items || []).map(i => i[2] + " × " + i[1]), r.sp ? T("очки навыков {0}", r.sp) : null].filter(Boolean).join(", ") || T("пусто");
async function pickReward(rewards) {
  if (!rewards || rewards.length < 2) return rewards && rewards.length ? rewards[0].id : null;
  const s = sel(rewards.map(r => [String(r.id), "№" + r.id + ": " + rewardText(r)]), String(rewards[0].id));
  if (!await confirmWin(T("Вариант награды"), [s, h("div", { class: "muted small" }, "Как выбор награды игроком при сдаче.")])) return undefined;
  return +s.value;
}
async function questsChar(uid, idx, rerender) {
  let d;
  const load = async () => { try { d = await api("/api/quests/char/" + uid + "/" + idx); return true; } catch (e) { notify(e.message, true); return false; } };
  if (!await load()) return;
  const edit = can("players.quests"), fin = can("players.items_give");
  const base = { uid: +uid, idx: +idx };
  const head = h("div"), taken = h("div"), done = h("div", { class: "picklist", style: { maxHeight: "220px" } }), add = h("div", { class: "picklist", style: { maxHeight: "200px" } });
  const qd = h("input", { placeholder: T("название или номер"), class: "wide" }), qa = h("input", { placeholder: T("название или номер"), class: "wide" });
  const qn = h("input", { type: "number", min: 0, max: 1279, step: 1, class: "num", placeholder: T("номер") });
  const after = async (ok) => { if (ok && await load()) show(); };
  const complete = async (quest, rewards) => {
    const r = await pickReward(rewards);
    if (r === undefined) return;
    after(await runOp("quest.complete", Object.assign({ quest: quest }, base, r ? { reward: r } : {})));
  };
  const hit = (t, x) => !t || String(x.quest) === t || (x.name || "").toLowerCase().includes(t);
  const show = () => {
    put(head, [kv([[T("Свободно мест в журнале"), String(d.free) + " / 12"], [T("Выполнено заданий"), String(d.done.length)]]),
      (d.warnings || []).map(w => h("div", { class: "note" }, T(w)))]);
    put(taken, d.taken.length ? d.taken.map(x => h("div", { class: "row" }, h("span", { class: "mono" }, x.posx), h("span", { class: "mono" }, x.quest),
      h("b", null, x.board ? T("доска {0}", x.code) : x.name),
      h("span", { class: "muted small" }, T("шаг {0} (сдача на шаге {1})", x.step, (x.steps || []).join(", ") || "—")),
      x.goals.length ? h("span", { class: "muted small" }, x.goals.map(g => (g[2] || g[0]) + " × " + g[1]).join(", ")) : null,
      x.job ? badge(T("смена профессии")) : null,
      edit ? h("button", { type: "button", onclick: async () => after(await runOp("quest.drop", Object.assign({ posx: x.posx }, base))) }, "Снять") : null,
      fin && !x.board ? h("button", { type: "button", onclick: () => complete(x.quest, x.rewards) }, "Завершить") : null))
      : h("div", { class: "muted" }, T("журнал пуст")));
    const td = qd.value.trim().toLowerCase();
    put(done, d.done.filter(x => hit(td, x)).slice(0, 200).map(x => h("div", { class: "row" }, h("span", { class: "mono" }, x.quest), h("span", null, x.name),
      x.job ? badge(T("смена профессии")) : null, x.repeatable ? badge(T("повторяемое")) : null,
      edit && !x.job ? h("button", { type: "button", onclick: async () => after(await runOp("quest.uncomplete", Object.assign({ quest: x.quest }, base))) }, "Снять отметку") : null)));
    const ta = qa.value.trim().toLowerCase();
    put(add, edit ? d.available.filter(x => hit(ta, x)).slice(0, 80).map(x => h("div", { class: "row" }, h("span", { class: "mono" }, x.quest), h("b", null, x.name),
      h("button", { type: "button", onclick: async () => after(await runOp("quest.give", Object.assign({ quest: x.quest }, base))) }, "Выдать"))) : []);
  };
  qd.addEventListener("input", show);
  qa.addEventListener("input", show);
  show();
  await confirmWin(T("Задания"), [head, h("h3", null, T("Журнал")), taken, h("h3", null, T("Выполненные")), qd, done,
    edit ? [h("h3", null, T("Выдать задание (как NPC)")), qa, add] : null,
    fin ? [h("h3", null, T("Завершить задание по номеру")), h("div", { class: "row" }, qn, h("button", { type: "button", onclick: async () => {
      if (qn.value === "") return;
      let r;
      try { r = await api("/api/quests/rewards/" + (+qn.value)); } catch (e) { return notify(e.message, true); }
      complete(+qn.value, r.rewards);
    } }, "Завершить"))] : null,
    h("div", { class: "muted small" }, "Выдать можно только то, что выдал бы NPC (уровень, профессия, предшествующие задания). Завершение ставит «выполнено» и выдаёт награду ячейки сдачи. Эпизоды смены профессии — строго: выдача только следующей ступени, завершение — только уже достигнутой, «выполнено» не снимается.")], "Закрыть");
  rerender();
}
async function petsChar(uid, idx, rerender) {
  let d;
  const load = async () => { try { d = await api("/api/pets/char/" + uid + "/" + idx); return true; } catch (e) { notify(e.message, true); return false; } };
  if (!await load()) return;
  const edit = can("players.pets");
  const list = h("div");
  const after = async (ok) => { if (ok && await load()) show(); };
  const show = () => put(list, d.pets.length ? d.pets.map(x => h("div", { class: "row" }, h("span", { class: "mono" }, x.PetUnique), h("b", null, x.PetName),
    h("span", { class: "muted small" }, T("{0}, уровень {1} из {2}, опыт {3}, сытость {4}", x.breed, x.PetLvl, x.PetMaxLvl, x.PetExp, x.FullNess)),
    x.Active ? badge(T("призван")) : null,
    edit ? [h("button", { type: "button", onclick: async () => {
      const inp = h("input", { value: x.PetName, maxlength: 14, class: "wide" });
      if (!await confirmWin(T("Кличка питомца"), [inp, h("div", { class: "muted small" }, "От 1 до 14 знаков: латиница, цифры, «-» и «_».")])) return;
      after(await runOp("pet.rename", { uid: +uid, idx: +idx, pet: x.PetUnique, name: inp.value.trim() }));
    } }, "Кличка"), h("button", { type: "button", onclick: async () => {
      const inp = h("input", { type: "number", min: 1, max: x.PetMaxLvl, step: 1, value: x.PetLvl, class: "num" });
      if (!await confirmWin(T("Уровень питомца"), [inp, h("div", { class: "muted small" }, T("от 1 до потолка питомца {0}", x.PetMaxLvl))])) return;
      after(await runOp("pet.level", { uid: +uid, idx: +idx, pet: x.PetUnique, level: +inp.value }));
    } }, "Уровень"), h("button", { type: "button", onclick: async () => after(await runOp("pet.delete", { uid: +uid, idx: +idx, pet: x.PetUnique })) }, "Удалить")] : null))
    : h("div", { class: "muted" }, T("питомцев нет")));
  show();
  await confirmWin(T("Питомцы"), [list], "Закрыть");
  rerender();
}

// ---------- внешность, баффы наборов, лагерь, ремесло, рыбалка, обучение, посещаемость (domains/charrest.py) — как сервер; не в игре ----------
async function charRestWin(uid, idx, rerender) {
  let d;
  const load = async () => { try { d = await api("/api/charrest/char/" + uid + "/" + idx); return true; } catch (e) { notify(e.message, true); return false; } };
  if (!await load()) return;
  const base = { uid: +uid, idx: +idx };
  const body = h("div");
  const after = async (ok) => { if (ok && await load()) show(); };
  const go = (name, extra) => async () => after(await runOp(name, Object.assign({}, base, extra || {})));
  const army = v => T(d.army_names[String(v)] || String(v));
  const show = () => {
    const a = d.appearance, parts = [];
    (d.errors || []).forEach(e => parts.push(h("div", { class: "note" }, T(e))));
    // внешность
    parts.push(h("h3", null, T("Внешность")));
    if (a) {
      const pair = sel(d.hair.map(x => [x.style + ":" + x.color, T("стиль {0}, цвет {1} (ур. {2}, цена {3})", x.style, x.color, x.level, x.price)]), a.HairStyle + ":" + a.HairColor);
      if (![...pair.options].some(o => o.value === a.HairStyle + ":" + a.HairColor)) pair.prepend(h("option", { value: a.HairStyle + ":" + a.HairColor, selected: true }, T("стиль {0}, цвет {1} (сейчас)", a.HairStyle, a.HairColor)));
      const face = sel(d.faces.concat(d.faces.includes(a.FaceType) ? [] : [a.FaceType]).map(f => [String(f), T("лицо {0}", f)]), String(a.FaceType));
      parts.push(kv([[T("Сейчас"), T("причёска {0}, цвет {1}, лицо {2}", a.HairStyle, a.HairColor, a.FaceType)]]),
        can("players.appearance") ? h("div", { class: "row" }, pair, face, h("button", { type: "button", onclick: async () => {
          const [hs, hc] = pair.value.split(":");
          after(await runOp("appearance.set", Object.assign({ hair: +hs, color: +hc, face: +face.value }, base)));
        } }, "Изменить")) : null,
        h("div", { class: "muted small" }, "Причёски — из таблицы парикмахерской сервера для пола персонажа (только продаваемые); лица — как в окне создания персонажа своего пола."));
    } else parts.push(h("div", { class: "muted" }, T("строки внешности нет")));
    // баффы наборов
    parts.push(h("h3", null, T("Бафф набора")));
    parts.push(d.plus.length ? d.plus.map(b => h("div", { class: "row" }, h("b", null, T("тип {0}", b.iType)), h("span", { class: "muted small" }, T("с {0} до {1}, {2} мин", b.StartTime, b.EndTime, b.BuffPeriod)),
      b.active ? badge(T("действует"), "ok") : badge(T("истёк")),
      can("players.plus") ? h("button", { type: "button", onclick: go("plus.remove") }, "Снять") : null)) : h("div", { class: "muted" }, T("бафа нет")));
    if (can("players.plus")) {
      const tp = sel(d.plus_types.map(t => [String(t.type), T("тип {0}: {1} мин", t.type, t.minutes)]), String((d.plus_types[0] || {}).type || 1));
      const mins = numIn(1440, 1, 525600);
      parts.push(h("div", { class: "row" }, tp, h("button", { type: "button", onclick: async () => after(await runOp("plus.set", Object.assign({ type: +tp.value }, base))) }, "Выдать"),
        d.plus.some(b => b.active) ? [mins, h("button", { type: "button", onclick: async () => after(await runOp("plus.extend", Object.assign({ minutes: +mins.value }, base))) }, "Продлить, мин")] : null));
    }
    // лагерь
    parts.push(h("h3", null, T("Лагерь (война фракций)")));
    const c = d.camp;
    parts.push(kv([[T("Армия персонажа"), c ? army(c.Campidx) : T("не выбрана")], [T("Очки чести"), c ? c.CampPoint : null],
      [T("Штраф (тики сервера)"), c ? h("span", null, fmt(c.CampPenaltyTime), c.CampPenaltyTime && can("players.camp") ? h("button", { type: "button", onclick: go("camp.penalty_clear") }, "Снять штраф") : null) : null],
      [T("Место в рейтинге чести"), d.rank ? T("{0} (Per {1})", d.rank.Ranking, d.rank.Per) : T("нет в рейтинге")],
      [T("Армии персонажей учётки"), d.account_camp.length ? d.account_camp.map(x => x.idx + ": " + army(x.Campidx)).join(", ") : T("нет")]]));
    if (can("players.camp")) {
      const ar = sel([["-1", army(-1)], ["0", army(0)], ["1", army(1)], ["2", army(2)]], String(c ? c.Campidx : -1));
      parts.push(h("div", { class: "row" }, ar, h("button", { type: "button", onclick: async () => after(await runOp("camp.set_army", Object.assign({ army: +ar.value }, base))) }, "Сменить армию всей учётки"),
        h("button", { type: "button", onclick: async () => after(await runOp("camp.rank_rebuild", {})) }, "Пересчитать рейтинг чести")),
        h("div", { class: "muted small" }, "Армия меняется у всех персонажей учётки (как у сервера), только когда вся учётка не в игре; счётчики армий сервера не трогаются. Рейтинг чести служба пересчитывает и сама раз в сутки (06:10)."));
    }
    // ремесло
    parts.push(h("h3", null, T("Ремесло")));
    const cr = d.craft;
    parts.push(cr ? kv([[T("Уровень / опыт"), T("{0} / {1}", cr.level, cr.exp)], [T("Изученные рецепты (биты)"), cr.recipe_bits.length ? String(cr.recipe_bits.length) + ": " + cr.recipe_bits.join(", ") : T("нет")],
      [T("Ежедневные задания ремесла"), d.craft_daily.length ? d.craft_daily.map(q => T("{0}: тип {1}, счётчик {2}, флаг {3}", q.Quest_Index, q.Quest_Type, q.Quest_Count, q.Quest_Flag)).join("; ") : T("нет")]])
      : h("div", { class: "muted" }, T("строки ремесла нет — её создаёт сервер при входе")));
    if (cr && can("players.craft")) {
      const lv = sel(d.craft_levels.map(x => [String(x.level), T("уровень {0} (опыт {1}…{2})", x.level, x.lo, x.hi)]), String(cr.level));
      const ex = h("input", { type: "number", min: 0, max: 65535, step: 1, class: "num", placeholder: T("опыт") });
      parts.push(h("div", { class: "row" }, lv, ex, h("button", { type: "button", onclick: async () => after(await runOp("craft.set_level",
        Object.assign({ level: +lv.value }, ex.value.trim() === "" ? {} : { exp: +ex.value }, base))) }, "Изменить"),
        h("button", { type: "button", onclick: go("craft.daily_reset") }, "Суточный сброс заданий")),
        h("div", { class: "muted small" }, "Опыт — в границах уровня по таблице сервера (пусто — начало уровня). Рецепты — только показ: соответствие битов номерам рецептов не сверено."));
    }
    // рыбалка
    parts.push(h("h3", null, T("Рыбалка")));
    parts.push(h("div", { class: "row" }, h("span", null, T("Навык рыбалки: {0}", fmt(d.fish || 0))), can("players.craft") ? h("button", { type: "button", onclick: async () => {
      const v = await askNum("Навык рыбалки", "Навык", d.fish || 0, 0, 2147483647);
      if (v !== null) after(await runOp("fish.set_skill", Object.assign({ value: v }, base)));
    } }, "Изменить") : null));
    parts.push(d.fish_books.length ? d.fish_books.map(b => h("div", { class: "row" }, h("b", null, T("книга {0}", b.book)),
      h("span", { class: "muted small" }, b.fish.map(f => f[0] + " × " + f[1]).join(", ")), b.complete ? badge(T("завершена")) : null,
      can("players.craft") ? h("button", { type: "button", onclick: go("fishbook.delete", { book: b.book }) }, "Удалить") : null)) : h("div", { class: "muted" }, T("книг рыб нет")));
    // обучение
    parts.push(h("h3", null, T("Обучение")));
    const boxes = d.tutorial.map(s => h("input", { type: "checkbox", checked: s.done, disabled: !can("players.tutorial") }));
    parts.push(h("div", { class: "picklist", style: { maxHeight: "200px" } }, d.tutorial.map((s, i) => h("label", { class: "row" }, boxes[i],
      h("span", null, T("шаг {0}", s.step)), h("span", { class: "muted small" }, T("опыт {0}", s.exp))))));
    if (can("players.tutorial")) parts.push(h("div", { class: "row" }, h("button", { type: "button", onclick: async () =>
      after(await runOp("tutorial.set", Object.assign({ steps: d.tutorial.filter((s, i) => boxes[i].checked).map(s => s.step) }, base))) }, "Сохранить отметки обучения")),
      h("div", { class: "muted small" }, "Снятая отметка — шаг можно пройти снова, и сервер снова даст за него опыт."));
    // посещаемость
    parts.push(h("h3", null, T("Посещаемость")));
    const at = d.attendance;
    parts.push(kv([[T("Отметок"), at.count ? at.count.ACount : 0], [T("Дни"), at.days.length ? at.days.map(x => x.slice(0, 10)).join(", ") : T("нет")]]),
      h("div", { class: "muted small" }, "Здесь только показ. Засчитать или снять прошедший день — раздел «Посещаемость» (сегодняшний день не правится: снятая отметка дала бы вторую награду)."),
      can("attendance.view") ? h("div", { class: "row" }, h("button", { type: "button", class: "ghost", onclick: ev => { const m = ev.target.closest(".modal"); if (m) m.remove(); location.hash = "#/attendance?uid=" + base.uid + "&idx=" + base.idx; } }, "Посещаемость персонажа")) : null);   /* ★ А6.10 */
    put(body, parts);
  };
  show();
  await confirmWin(T("Внешность, баффы, лагерь, ремесло — {0}", d.name), [body], "Закрыть");
  rerender();
}
// ---------- копия персонажа на служебную учётку (domains/charcopy.py, adm.CharCopy) ----------
async function copyChar(uid, idx, cur, rerender) {
  let t;
  try { t = await api("/api/charcopy/targets"); } catch (e) { return notify(e.message, true); }
  const ok = t.targets.filter(x => x.free.length);
  if (!ok.length) return notify(T("у служебных учёток (до 5000) нет свободных слотов — сначала освободите слот"), true);
  const to = sel(ok.map(x => [String(x.uid), T("учётка {0}: свободны слоты {1}", x.uid, x.free.join(", "))]), String(ok[0].uid));
  const slot = h("select");
  const fill = () => { const x = ok.find(y => String(y.uid) === to.value); put(slot, x.free.map(s => h("option", { value: s }, String(s)))); };
  to.addEventListener("change", fill); fill();
  const name = h("input", { type: "text", maxlength: 19, value: "", class: "grow", placeholder: T("новое имя") });
  if (!await confirmWin(T("Копия персонажа {0}", cur), [kv([[T("Куда"), to], [T("Слот"), slot], [T("Имя копии"), name]]),
    h("div", { class: "muted small" }, "Копия — на служебную учётку (номер до 5000); обе учётки не в игре. Копируется персонаж целиком (предметы с новыми номерами), без друзей, клана, соулмейта, почты, аукциона и посещаемости. Откат в журнале — удаление копии.")], "Далее")) return;
  if (await runOp("char.copy", { uid: +uid, idx: +idx, to: +to.value, slot: +slot.value, name: name.value.trim() })) rerender();
}

// сторона пары соулмейтов: «№ логин» и персонажи учётки строкой ниже
function smSide(uid, login, chars) {
  return h("div", null, h("b", null, String(uid) + (login ? " " + login : "")),
    h("div", { class: "muted small" }, chars && chars.length ? chars.join(", ") : T("персонажей нет")));
}
// ---------- соулмейт (domains/soulmate.py), друзья (friends.py), клан (clan.py) — как сервер; учётки не в игре; всё в журнал с откатом ----------
const numIn = (v, lo, hi) => h("input", { type: "number", min: lo, max: hi, step: 1, value: v, class: "num" });
// список выбора [[значение, подпись]] (18.11: общий; раньше был только внутри окна свойств предмета — pickReward звал необъявленный sel)
function sel(opts, cur, onch) {
  const s = h("select", null, opts.map(([v, t]) => h("option", { value: String(v), selected: String(v) === String(cur) }, t)));
  if (onch) s.addEventListener("change", onch);
  return s;
}
async function askNum(title, label, v, lo, hi, note) {
  const inp = numIn(v, lo, hi);
  if (!await confirmWin(T(title), [h("div", { class: "row" }, h("span", null, T(label)), inp), note ? h("div", { class: "muted small" }, note) : null])) return null;
  return inp.value.trim() === "" ? null : +inp.value;
}
async function soulmateChar(uid, idx, rerender) {
  let d;
  const load = async () => { try { d = await api("/api/soulmate/char/" + uid + "/" + idx); return true; } catch (e) { notify(e.message, true); return false; } };
  if (!await load()) return;
  const edit = can("players.soulmate");
  const body = h("div");
  const after = async (ok) => { if (ok && await load()) show(); };
  const charsOf = u => (d.chars[String(u)] || []).map(c => h("div", { class: "row" }, h("span", { class: "mono" }, u + "/" + c.idx), h("span", null, c.name),
    h("span", { class: "muted small" }, T("ур. {0}", c.lvl)), c.share ? badge(T("отдан партнёру (Share)")) : null, c.online ? badge("в игре", "warn") : null));
  const show = () => {
    const a = d.active;
    put(body, a ? [kv([[T("Пара"), String(a.Smidx)], [T("Партнёр"), h("a", { href: "#/account/" + a.Ouserindex }, String(a.Ouserindex))],
      [T("Уровень связи"), String(a.SmLvl)], [T("Опыт связи"), String(a.SmExp)], [T("Дружба пары"), String(a.FriendShip)],
      [T("Затухание с"), a.FinalDate || "—"], [T("Связана"), a.Regdate]]),
      edit ? h("div", { class: "row" },
        h("button", { type: "button", onclick: async () => after(await runOp("soulmate.break", { uid: +uid })) }, "Разорвать"),
        h("button", { type: "button", onclick: async () => {
          const top = d.levels.length ? d.levels[d.levels.length - 1][0] : 30;
          const v = await askNum("Уровень связи", "Уровень", a.SmLvl, 1, top, T("Опыт ставится на начало уровня по SoulMateExpTable сервера (1 … {0}).", top));
          if (v !== null) after(await runOp("soulmate.level", { uid: +uid, level: v }));
        } }, "Уровень"),
        h("button", { type: "button", onclick: async () => {
          const v = await askNum("Дружба пары", "Дружба", a.FriendShip, 0, 255, T("0 … 255; отметка затухания сбрасывается."));
          if (v !== null) after(await runOp("soulmate.friendship", { uid: +uid, value: v }));
        } }, "Дружба")) : null,
      h("h3", null, T("Персонажи учёток")), charsOf(uid), charsOf(a.Ouserindex)]
      : [h("div", { class: "muted" }, T("активной связи нет")), h("h3", null, T("Персонажи учётки")), charsOf(uid),
        edit ? h("div", { class: "row" }, h("button", { type: "button", onclick: async () => {
          const v = await askNum("Связать учётки", "Номер второй учётки", "", 1, 2147483647, T("Как согласие обоих: прежняя пара из истории восстанавливается с уровнем и опытом, иначе — новая пара уровня 1."));
          if (v !== null) after(await runOp("soulmate.link", { uid: +uid, uid2: v }));
        } }, "Связать с учёткой")) : null],
      h("h3", null, T("История")), d.history.length ? d.history.map(x => h("div", { class: "row" }, h("span", { class: "mono" }, x.Smidx),
        h("a", { href: "#/account/" + x.Ouserindex }, String(x.Ouserindex)), h("span", { class: "muted small" }, T("уровень {0}, опыт {1}, дружба {2}, с {3}", x.SmLvl, x.SmExp, x.FriendShip, x.Regdate)),
        edit && !a ? h("button", { type: "button", onclick: async () => after(await runOp("soulmate.link", { uid: +uid, uid2: x.Ouserindex })) }, "Связать снова") : null))
        : h("div", { class: "muted" }, T("пусто")),
      d.crystals.length ? h("div", { class: "note" }, T("кристаллов опыта Друга у учётки: {0} — при разрыве удаляются, как у сервера", d.crystals.length)) : null,
      edit ? h("div", { class: "row" }, h("button", { type: "button", class: "ghost", onclick: async () => after(await runOp("soulmate.share_fix", { uid: +uid })) }, "Сверка Share учётки")) : null);
  };
  show();
  await confirmWin(T("Соулмейт"), [body, h("div", { class: "muted small" }, "Связь — на учётку. Обе учётки пары должны быть не в игре: уровень, опыт и дружбу сервер пишет из памяти и перезаписал бы правку.")], "Закрыть");
  rerender();
}
async function friendsChar(uid, idx, rerender) {
  let d;
  const load = async () => { try { d = await api("/api/friends/char/" + uid + "/" + idx); return true; } catch (e) { notify(e.message, true); return false; } };
  if (!await load()) return;
  const edit = can("players.friends");
  const base = { uid: +uid, idx: +idx };
  const list = h("div", { class: "picklist", style: { maxHeight: "320px" } }), orphan = h("div");
  const fu = numIn("", 1, 2147483647), fi = numIn("", 0, 255);
  const after = async (ok) => { if (ok && await load()) show(); };
  const show = () => {
    put(list, d.friends.length ? d.friends.map(x => h("div", { class: "row" }, h("a", { href: "#/char/" + x.Fuserindex + "/" + x.Fcharidx }, x.Fuserindex + "/" + x.Fcharidx),
      h("b", null, x.Charname), x.stale ? badge(T("устаревшее имя, сейчас: {0}", x.cur || "—"), "warn") : null,
      x.mutual ? null : badge(T("односторонняя")), x.online ? badge("в игре", "warn") : null, x.Lvl !== null ? h("span", { class: "muted small" }, T("ур. {0}", x.Lvl)) : null,
      edit ? h("button", { type: "button", onclick: async () => after(await runOp("friend.delete", Object.assign({ fuid: x.Fuserindex, fidx: x.Fcharidx }, base))) }, "Удалить") : null))
      : h("div", { class: "muted" }, T("друзей нет")));
    put(orphan, d.one_sided_to_me.length ? [h("h3", null, T("Числят в друзьях без взаимной строки")), d.one_sided_to_me.map(x => h("div", { class: "row" },
      h("span", { class: "mono" }, x.Userindex + "/" + x.Charidx), h("span", null, x.Charname || "—"),
      edit ? h("button", { type: "button", onclick: async () => after(await runOp("friend.add", Object.assign({ fuid: x.Userindex, fidx: x.Charidx }, base))) }, "Сделать взаимной") : null))] : []);
  };
  show();
  await confirmWin(T("Друзья"), [h("div", { class: "muted small" }, T("в списке {0} из {1}", d.friends.length, d.limit)), list, orphan,
    edit ? [h("h3", null, T("Добавить друга")), h("div", { class: "row" }, h("span", null, T("Учётка")), fu, h("span", null, T("слот")), fi,
      h("button", { type: "button", onclick: async () => { if (fu.value === "" || fi.value === "") return; after(await runOp("friend.add", Object.assign({ fuid: +fu.value, fidx: +fi.value }, base))); } }, "Добавить")),
      h("div", { class: "row" }, h("button", { type: "button", class: "ghost", onclick: async () => after(await runOp("friend.names", base)) }, "Обновить устаревшие имена"))] : null,
    h("div", { class: "muted small" }, "Как в игре: дружба — в обе стороны, не больше 50 у каждого. Владелец списка — не в игре; друг может быть в игре (у него строка обновится при следующем открытии окна друзей).")], "Закрыть");
  rerender();
}
const MARK_COLS = ["MarkFlag", "Markidx", "MarkColor", "MarkBorder", "MarkBdColor", "MarkBgColor"];
async function clanWin(cid, rerender) {
  let d;
  const load = async () => { try { d = await api("/api/clan/" + cid); return true; } catch (e) { notify(e.message, true); return false; } };
  if (!await load()) return;
  const edit = can("players.clan");
  const body = h("div");
  const author = h("input", { maxlength: 20, class: "wide", placeholder: T("автор") }), text = h("textarea", { rows: 3, maxlength: 500, class: "wide", placeholder: T("текст объявления") });
  const q = h("input", { placeholder: T("номер или часть имени клана"), class: "wide" }), found = h("div");
  const after = async (ok) => { if (ok && await load()) show(); };
  const act = (name, extra) => async () => after(await runOp(name, Object.assign({ clan: +cid }, extra || {})));
  const show = () => {
    author.value = author.value || d.Captain || "";
    put(body, kv([[T("Клан"), d.Cname + " (" + d.Clanidx + ")"], [T("Глава"), h("a", { href: "#/char/" + d.Capuserindex + "/" + d.CapCharidx }, d.Captain)],
      [T("Членов"), d.JoinCnt + " / " + d.Maxcnt], [T("Уровень"), d.Lvl], [T("Эмблема"), MARK_COLS.map(k => d[k]).join(" / ")],
      [T("Сейчас в игре"), String(d.online)], [T("MVP лагеря"), d.mvp.length ? d.mvp.join(", ") : "—"],
      [T("Очки лагеря"), d.camp.length ? d.camp.map(c => c.CampType + ": " + [c.EnterPoint0, c.EnterPoint1, c.EnterPoint2].join("/")).join("; ") : "—"]]),
      d.online && edit ? h("div", { class: "note" }, T("в игре членов клана: {0} — исключить, сменить главу, распустить и сбросить эмблему можно, только когда все не в игре", d.online)) : null,
      h("h3", null, T("Состав")), table([["Персонаж", m => h("a", { href: "#/char/" + m.Userindex + "/" + m.Charidx }, m.Charname)], ["Учётка/слот", m => m.Userindex + "/" + m.Charidx],
        ["Ступень", m => m.Grade], ["Ур.", m => m.Lvl], ["В игре", m => !!m.online],
        ["", m => edit ? [m.Grade < 10 && !(m.Userindex === d.Capuserindex && m.Charidx === d.CapCharidx)
          ? h("button", { type: "button", onclick: act("clan.captain", { uid: m.Userindex, idx: m.Charidx }) }, "Сделать главой") : null,
          !(m.Userindex === d.Capuserindex && m.Charidx === d.CapCharidx) ? h("button", { type: "button", onclick: act("clan.kick", { uid: m.Userindex, idx: m.Charidx }) }, "Исключить") : null] : null]], d.members),
      edit ? h("div", { class: "row" }, MARK_COLS.some(k => d[k]) ? h("button", { type: "button", onclick: act("clan.mark_reset") }, "Сбросить эмблему") : null,
        h("button", { type: "button", onclick: act("clan.disband") }, "Распустить клан")) : null,
      h("h3", null, T("Объявления ({0} из {1})", d.notices.length, d.notice_max)),
      d.notices.length ? d.notices.map(n => h("div", { class: "row" }, h("span", { class: "mono" }, n.idx), h("b", null, n.Charname), h("span", { class: "muted small" }, n.Edate),
        h("span", { class: "grow" }, n.Notice), edit ? h("button", { type: "button", onclick: act("clan.notice_delete", { notice: n.idx }) }, "Удалить") : null))
        : h("div", { class: "muted" }, T("объявлений нет")),
      edit ? [h("div", { class: "row" }, h("span", null, T("Автор")), author), text,
        h("div", { class: "row" }, h("button", { type: "button", onclick: async () => after(await runOp("clan.notice_add", { clan: +cid, author: author.value.trim(), text: text.value.trim() })) }, "Добавить объявление"))] : null);
  };
  const search = async () => {
    let r;
    try { r = await api("/api/clan/search?q=" + encodeURIComponent(q.value.trim())); } catch (e) { return notify(e.message, true); }
    put(found, r.items.map(c => h("div", { class: "row" }, h("span", { class: "mono" }, c.Clanidx), h("b", null, c.Cname), h("span", { class: "muted small" }, T("глава {0}, членов {1} / {2}", c.Captain, c.JoinCnt, c.Maxcnt)),
      h("button", { type: "button", onclick: () => clanWin(c.Clanidx, () => {}) }, "Открыть"))));
  };
  show();
  await confirmWin(T("Клан"), [body, h("h3", null, T("Другой клан")), h("div", { class: "row" }, q, h("button", { type: "button", onclick: search }, "Найти")), found,
    h("div", { class: "muted small" }, "Сервер держит клан в памяти: исключение, смена главы, роспуск и эмблема — только когда все члены не в игре (сервер перечитает клан при входе первого). Объявления — можно при членах в игре. Роспуск удаляет и объявления (исправление дефекта оригинала) и снимает MVP лагеря.")], "Закрыть");
  rerender();
}

// ---------- сообщение одному игроку живьём (domains/live.py live.notice, мост P127 v81: 3113 только ему) ----------
async function noticeAccount(uid) {
  const inp = h("input", { maxlength: 95, class: "wide", placeholder: T("текст (до 95 символов)") });
  if (!await confirmWin(T("Сообщение игроку"), [h("div", { class: "row" }, inp),
    h("div", { class: "muted small" }, "Уйдёт сразу, если игрок в игре на сервере с мостом v81 (серверное уведомление в центре экрана). Не в игре — отказ. В журнал попадёт, откатить нельзя.")])) return;
  const params = { uid: +uid, text: inp.value.trim() };
  let p;
  try { p = await op("live.notice", params, true); } catch (e) { return notify(e.message, "bad"); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text))])) return;
  try { const x = await op("live.notice", params, false); notify(T(x.message || "готово")); }
  catch (e) { notify(e.message, "bad"); }
}

// ---------- опыт уровня, % (domains/progress.py char.exp_set; вкладка «Опыт» старой утилиты: обычно 99 % — до повышения один шаг) ----------
async function expChar(uid, idx, rerender) {
  const inp = h("input", { type: "number", min: 0, max: 99, step: 1, value: 99, class: "num" });
  if (!await confirmWin(T("Опыт уровня"), [h("div", { class: "row" }, h("span", null, T("Опыт текущего уровня, %")), inp),
    h("div", { class: "muted small" }, "Уровень не меняется: опыт ставится внутри текущего уровня по таблице опыта сервера. Игрок в игре — живьём только прибавка (уменьшение — отключением игрока и записью).")])) return;
  const params = { uid: +uid, idx: +idx, percent: inp.value.trim() };
  let p;
  try { p = await op("char.exp_set", params, true); } catch (e) { return notify(e.message, "bad"); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w))), pathNote(p)])) return;
  try { const x = await op("char.exp_set", Object.assign({ expect: p.preview.expect }, params), false); notify(x.message || T("готово")); rerender(); }
  catch (e) { notify(e.message, "bad"); }
}

// ---------- смена профессии (domains/jobchange.py: по ступеням, как награда квеста; навыки — только недостающие) ----------
const JOB_LABEL = { 1: "боец 1", 2: "боец 2", 3: "боец 3", 12: "лучник 1", 13: "лучник 2", 14: "лучник 3", 23: "маг 1", 24: "маг 2", 25: "маг 3" };
const jobLabel = t => T(JOB_LABEL[t.job] || String(t.job)) + (t.subjob ? " · " + T("подкласс {0}", t.subjob) : "");
async function jobChangeChar(uid, idx, targets, rerender) {
  const selT = h("select", null, targets.map((t, i) => h("option", { value: String(i) }, jobLabel(t))));
  if (!await confirmWin(T("Сменить профессию"), [h("div", { class: "row" }, h("span", null, T("Новая профессия")), selT),
    h("div", { class: "muted small" }, "Как награда квеста, по ступеням: очки навыков — только при первой смене, навыки новой профессии — по требованиям сервера (уже изученные не трогаются), звание за 3-ю ступень. 4-я профессия выдаёт навыки, только если в основные деревья ветки вложено 60 очков.")])) return;
  const t = targets[+selT.value];
  const params = { uid: +uid, idx: +idx, target: t.subjob ? { job: t.job, subjob: t.subjob } : { job: t.job } };
  let p;
  try { p = await op("char.job_change", params, true); } catch (e) { return notify(e.message, "bad"); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w))),
    h("div", { class: "muted small" }, "Действие попадёт в журнал, его можно откатить.")])) return;
  try { const x = await op("char.job_change", Object.assign({ expect: p.preview.expect }, params), false); notify(x.message || T("готово")); rerender(); }
  catch (e) { notify(e.message, "bad"); }
}

// ---------- лента журналов ----------
function feedView(uid, idx) {
  const box = h("div");
  const days = h("select", null, [[1, "сутки"], [7, "неделя"], [30, "30 дней"], [90, "90 дней"], [365, "год"], [3650, "всё"]]
    .map(([v, t]) => h("option", { value: v, selected: v === 30 }, t)));
  const grp = h("select", null, h("option", { value: "" }, "все разделы"));
  const load = async () => {
    put(box, h("div", { class: "muted" }, "Собираю ленту по всем журналам…"));
    try {
      if (!S.groups) S.groups = (await api("/api/feed/groups")).groups;
      if (grp.options.length === 1) S.groups.forEach(g => grp.append(h("option", { value: g }, T(g))));
      const r = await api("/api/players/feed/" + uid + "?days=" + days.value + (idx !== null ? "&idx=" + idx : "") + (grp.value ? "&groups=" + encodeURIComponent(grp.value) : ""));
      put(box,
        h("div", { class: "muted small" }, T("Записей: {0}", r.total) + (r.total > r.items.length ? " " + T("(показаны {0} последних)", r.items.length) : "") + " · " + T("таблиц с записями: {0}", r.summary.length) + " · " + T("с {0}", dt(r.since))),
        r.errors.length ? h("div", { class: "err" }, r.errors.map(e => e.table + ": " + e.error).join("\n")) : null,
        table([["Когда", x => dt(x.at)], ["Раздел", x => T(x.group)], ["Таблица", x => h("span", { class: "mono" }, x.table)],
               ["Предмет", x => x.item ? itemLine(x.item.code, S.lang === "en" ? (x.item.en || x.item.ru) : x.item.ru, x.item.icon) : ""],
               ["Поля", x => h("details", null, h("summary", null, "показать"), h("div", { class: "mono small" },
                 Object.entries(x.fields).map(([k, v]) => h("div", null, k + " = " + (v === null ? "NULL" : v)))))]], r.items));
    } catch (e) { put(box, errbox(e)); }
  };
  days.addEventListener("change", load); grp.addEventListener("change", load);
  setTimeout(load, 0);
  return [h("div", { class: "row" }, "Период", days, "Раздел", grp), h("div", { style: { height: "8px" } }), box];
}

// ---------- след предмета v2 (domains/feed.py trace: все журналы и все столбцы-номера, цепочка через обмен, «где сейчас») ----------
const plateName = p => T({ 1: "сумка 1 (снаряжение)", 2: "сумка 2 (расходники)", 3: "надето", 5: "склад", 11: "замок аукциона (сумка 1)", 12: "замок аукциона (сумка 2)" }[p] || ("сумка " + p));
const fieldsCell = f => h("details", null, h("summary", null, "показать"), h("div", { class: "mono small" },
  Object.entries(f).map(([k, v]) => h("div", null, k + " = " + (v === null ? "NULL" : v)))));
function viewTrace(serial) {
  const inp = h("input", { placeholder: "серийный номер предмета (GUID)", value: serial || "", class: "grow mono" });
  const out = h("div");
  const go = async (ev) => {
    if (ev) ev.preventDefault();
    const v = inp.value.trim();
    if (!v) return;
    history.replaceState(null, "", "#/trace/" + v);
    put(out, h("div", { class: "muted" }, "Ищу по всем журналам…"));
    let r;
    try { r = await api("/api/items/trace?serial=" + encodeURIComponent(v)); } catch (e) { return put(out, errbox(e)); }
    const n = r.now, sm = r.summary;
    const toChar = x => { location.hash = "#/char/" + x.Userindex + "/" + x.Charidx; };
    const giveOk = can("players.items_give");
    put(out,
      h("div", { class: "card" }, kv([
        ["Номер", h("span", { class: "mono" }, r.serial)],
        ["Цепочка номеров", r.chain.length > 1 ? h("span", null, r.chain.map((c, i) => [i ? " → " : "", h("a", { class: "mono", href: "#/trace/" + c }, c)]),
          h("div", { class: "muted small" }, "неполный обмен даёт получателю новый номер (TradeitemTo: Serial — новый, Tserial — исходный); след идёт по этим связям")) : T("один номер")],
        ["Появился", sm.born ? h("span", null, dt(sm.born.at) + " · ", h("span", { class: "mono" }, sm.born.table), sm.born.birth ? "" : " " + T("(первое событие — не появление)")) : T("событий нет")],
        ["Последнее событие", sm.last ? h("span", null, dt(sm.last.at) + " · ", h("span", { class: "mono" }, sm.last.table), sm.last.death ? [" ", badge(T(sm.last.death), "warn")] : "") : "—"],
        ["Жив сейчас", sm.alive ? badge("да", "ok") : badge("нет", "bad")],
        (sm.explain || []).length ? ["Почему нет следа появления", h("div", null, sm.explain.map(x => h("div", { class: "note" }, x)))] : null,
      ].filter(Boolean))),
      h("h2", null, "Где сейчас"),
      n.item.length ? table([["Учётка/слот", x => x.Userindex + "/" + x.Charidx], ["Предмет", x => itemLine(x.Code, x.name, null)],
        ["Сумка", x => x.lock ? [plateName(x.Plate), " ", badge("в замке аукциона", "warn")] : plateName(x.Plate)], ["Ячейка", x => x.Posx],
        ["Шт.", x => x.Amount], ["+", x => x.Upcount], ["Номер", x => h("span", { class: "mono small" }, x.Uuid)]], n.item, toChar)
        : h("div", { class: "muted" }, "В сумках (Joy1.Item) предмета нет."),
      n.lots.length ? [h("h3", null, "Лот аукциона (Exitem)"), lotTable(n.lots, true)] : null,
      n.socket.length || n.lot_socket.length || n.deleted_socket.length ? [h("h3", null, "Вставлен в оправу (совел, Uc1–4)"),
        table([["Где", x => x._w], ["Учётка/слот", x => x.Userindex + "/" + x.Charidx], ["Оправа", x => itemLine(x.Code, x.name, null)],
          ["Гнездо", x => (x.slot || []).join(", ")], ["Номер оправы", x => h("a", { class: "mono small", href: "#/trace/" + (x.Uuid || x.Eid) }, x.Uuid || x.Eid)]],
          [].concat(n.socket.map(x => Object.assign({ _w: T("сумки") }, x)), n.lot_socket.map(x => Object.assign({ _w: T("лот аукциона") }, x)),
            n.deleted_socket.map(x => Object.assign({ _w: T("удалённый персонаж") }, x))))] : null,
      (n.deleted_lots || []).length ? [h("h3", null, "Лот удалённого персонажа (Del_ExItem)"), table([["Удалён", x => dt(x.Edate)], ["Учётка/слот", x => x.Userindex + "/" + x.Charidx],
        ["Предмет", x => itemLine(x.Code, x.name, null)], ["Шт.", x => x.Amount], ["Гнездо", x => (x.slot || []).length ? T("совел в гнезде {0}", x.slot.join(", ")) : ""]], n.deleted_lots)] : null,
      n.deleted.length ? [h("h3", null, "В корзине удалённых персонажей (Del_item)"), table([["Удалён", x => dt(x.Edate)], ["Учётка/слот", x => x.Userindex + "/" + x.Charidx],
        ["Предмет", x => itemLine(x.Code, x.name, null)], ["Сумка", x => plateName(x.Plate)], ["Шт.", x => x.Amount]], n.deleted)] : null,
      n.taken.length ? [h("h3", null, "Изъят панелью (снимок adm.ItemTaken)"), table([["Запись", x => x.LedgerId], ["Когда", x => dt(x.At)], ["Кто", x => x.Operator],
        ["Учётка/слот", x => x.Userindex + "/" + x.Charidx], ["Предмет", x => itemLine(x.Code, x.name, null)],
        ["Откат", x => x.UndoneBy ? badge(T("возвращён ({0})", x.UndoneBy), "ok") : badge("не возвращён", "warn")]], n.taken)] : null,
      n.ledger.length ? [h("h3", null, "Журнал предметов панели (adm.ItemLedger)"), table([["№", x => x.Id], ["Когда", x => dt(x.At)], ["Вид", x => x.Kind],
        ["Кто", x => x.Operator], ["Учётка/слот", x => x.Userindex + "/" + x.Charidx], ["Было → стало", x => fmt(x.AmountBefore) + " → " + fmt(x.AmountAfter)],
        ["Источник", x => x.Source || ""], ["Откачено", x => x.UndoneBy ? badge(T("№{0}", x.UndoneBy)) : ""]], n.ledger)] : null,
      n.copies.length ? [h("h3", null, "Копия персонажа (adm.CharCopyItemMap)"), table([["Копия №", x => x.CopyId], ["Было", x => h("a", { class: "mono small", href: "#/trace/" + x.OldUuid }, x.OldUuid)],
        ["Стало", x => h("a", { class: "mono small", href: "#/trace/" + x.NewUuid }, x.NewUuid)]], n.copies)] : null,
      h("h2", null, T("История · {0}", r.events.length)),
      r.errors.length ? h("div", { class: "err" }, r.errors.map(e => e.table + ": " + e.error).join("\n")) : null,
      table([["Когда", x => dt(x.at)], ["Раздел", x => T(x.group)], ["Таблица", x => h("span", { class: "mono" }, x.table)],
             ["Кто", x => fmt(x.fields.Userindex ?? x.fields.user_index) + "/" + fmt(x.fields.Charidx ?? x.fields.char_slot)],
             ["Событие", x => [x.birth ? badge("появление", "ok") : null, x.death ? badge(T(x.death), "warn") : null,
               x.link ? h("span", { class: "muted small" }, Object.entries(x.link).map(([k, v]) => k + " " + v.slice(0, 8) + "…").join(" · ")) : null,
               (x.hit || []).length && (x.hit[0] !== r.serial || x.hit.length > 1) ? h("span", { class: "muted small" }, " " + x.hit.map(z => z.slice(0, 8)).join(", ")) : null]],
             ["", x => x.recoverable && giveOk ? h("button", { type: "button", class: "ghost", onclick: () => recoverWin(String(x.fields.Serial || r.serial).toUpperCase(), x, () => go()) }, "Вернуть") : ""],
             ["Поля", x => fieldsCell(x.fields)]], r.events));
  };
  mount(shell("#/trace", h("h1", null, "След предмета"),
    h("form", { class: "row card", onsubmit: go }, inp, h("button", { type: "submit" }, "Найти")),
    h("div", { class: "muted small" }, "Серийный номер есть в подробностях предмета в сумке. Поиск — по всем журналам joylog1 и всем столбцам-номерам (Serial, Uuid, Tserial, Fserial), с переходом по цепочке неполного обмена; «где сейчас» — сумки, замок аукциона, лот, оправа совела, корзина удалённых, изъятое и журнал панели."),
    out));
  if (serial) go();
}

// лоты аукциона: номер → след, истёк ли, когда реле снимет (с ac0z — вернёт владельцу)
function lotTable(lots, withOwner) {
  return table([withOwner ? ["Учётка/слот", x => x.Userindex + "/" + x.Charidx] : null, ["Лот", x => x.idx + (x.Gidx ? " · " + T("группа {0}", x.Gidx) : "")],
    ["Предмет", x => itemLine(x.Code, x.name, x.icon)], ["Шт.", x => x.Amount], ["+", x => x.Upcount], ["Цена", x => x.Sprice],
    ["Выставлен", x => dt(x.Gaindate)], ["Продажа до", x => [dt(x.Fdate), x.expired ? [" ", badge("истёк", "warn")] : null]],
    // ★ ревизия 27 М-4: срок реле прошёл, а лот на месте — реле уже не повторит до рестарта (ac0z ответил «нельзя» или не успело)
    ["Реле снимет", x => x.relay_overdue ? badge(T(x.relay_overdue), "warn") : x.relay_due ? h("span", { title: "ItemDeleteTime 14 суток; если реле перезапускали после истечения — от конца продажи" }, dt(x.relay_due) + (x.relay_due_late && x.relay_due_late !== x.relay_due ? " … " + dt(x.relay_due_late) : "")) : "—"],
    ["Номер", x => x.Eid ? h("a", { class: "mono small", href: "#/trace/" + x.Eid }, x.Eid) : "—"]].filter(Boolean), lots);
}

// ---------- вернуть удалённое по журналу (domains/itemrecover.py → adm.ItemRecover; тот же номер, защита от дюпа) ----------
async function recoverWin(serial, ev, rerender) {
  const sell = /SellNPC/.test(ev.table);
  const gold = h("input", { type: "checkbox", checked: true });
  const params = { serial, table: ev.table, at: ev.key };
  const step = async (pr) => {
    let p;
    try { p = await op("items.recover", pr, true); } catch (e) { notify(e.message, true); return null; }
    const pv = p.preview;
    if (!await confirmWin(T("Вернуть предмет"), [h("div", { class: "pv" }, T(pv.text)),
      h("h3", null, "Не восстановится (в журнале этого нет)"), h("ul", null, (pv.lost || []).map(x => h("li", null, x))),
      (pv.warnings || []).filter(w => !/^(не восстановится|will not be restored)/.test(w)).map(w => h("div", { class: "note" }, T(w))),
      pathNote(p, "Игрок — не в игре. Тот же номер предмета; если он уже где-то есть — отказ (дюп). Действие попадёт в журнал, его можно откатить.")], "Вернуть")) return null;
    return pv;
  };
  if (sell && !await confirmWin(T("Вернуть проданное NPC"), [h("label", { class: "row" }, gold, h("span", null, T("списать золото продажи (сколько игрок получил)"))),
    h("div", { class: "muted small" }, "Решение владельца: при возврате проданного золото продажи списывается; если золота не хватает — отказ.")], "Далее")) return;
  if (sell) params.charge_gold = gold.checked;
  let pv = await step(params);
  if (!pv) return;
  try {
    let x = await op("items.recover", Object.assign({ expect: pv.expect }, params), false);
    if (x.dry && x.kicked) {                     // «кик + запись», шаг 2: игрок выведен — новый предпросмотр на подтверждение
      notify(T(x.message || "игрок отключён"));
      pv = x.preview;
      if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(pv.text)), h("ul", null, (pv.lost || []).map(z => h("li", null, z))),
        (pv.warnings || []).map(w => h("div", { class: "note" }, T(w)))], "Вернуть")) return;
      x = await op("items.recover", Object.assign({ expect: pv.expect }, params), false);
    }
    notify(T(x.message || "готово")); rerender();
  } catch (e) { notify(e.message, true); }
}

// ---------- поиск дюпов (domains/dupes.py; только чтение) ----------
function viewDupes() {
  const out = h("div");
  const load = async (full) => {
    put(out, h("div", { class: "muted" }, full ? "Собираю по всем журналам (до минуты)…" : "Проверяю базу предметов…"));
    let r;
    try { r = await api("/api/items/dupes" + (full ? "?full=1" : "")); } catch (e) { return put(out, errbox(e)); }
    const trace = u => h("a", { class: "mono small", href: "#/trace/" + u }, u);
    const kindBadge = k => ({ suspect: badge("подозрение", "bad"), stack: badge("стопка — штатно", "ok"), restored: badge("восстановлен панелью", "ok"), known: badge("известный", "warn") }[k]);
    put(out,
      h("h2", null, T("Одинаковый номер в нескольких местах · {0}", r.same_uuid.length)),
      r.same_uuid.length ? r.same_uuid.map(g => h("div", { class: "card" }, h("div", { class: "row" }, kindBadge(g.kind), trace(g.uuid), itemLine(g.code, g.name, null)),
        h("div", { class: "muted small" }, g.note),
        table([["Где", x => x.src], ["Учётка/слот", x => x.Userindex + "/" + x.Charidx], ["Сумка", x => plateName(x.Plate)], ["Ячейка / лот", x => x.Posx],
          ["Шт.", x => x.Amount], ["Дата", x => dt(x.d)]], g.rows, x => { location.hash = "#/char/" + x.Userindex + "/" + x.Charidx; })))
        : h("div", { class: "muted" }, "нет"),
      h("h2", null, T("Невозможные количества · {0}", r.amounts.rows.length)),
      h("div", { class: "muted small" }, T("Заряды выше таблицы у кодов P100 в пределах потолка {0} — законные слияния, не считаются: {1}.", r.amounts.cap, r.amounts.p100_merged)),
      table([["Учётка/слот", x => x.Userindex + "/" + x.Charidx], ["Предмет", x => itemLine(x.Code, x.name, null)], ["Сумка", x => plateName(x.Plate)],
        ["Ячейка", x => x.Posx], ["Шт.", x => x.Amount], ["Почему", x => x.why], ["Номер", x => trace(x.Uuid)]], r.amounts.rows,
        x => { location.hash = "#/char/" + x.Userindex + "/" + x.Charidx; }),
      r.no_birth ? [
        h("h2", null, T("Без следа появления · {0} из {1}", r.no_birth_total, r.items)),
        h("div", { class: "muted small" }, T("Не дюп сам по себе: журналы ведутся с {0}, стартовый набор, совел из оправы и копии панели появление не пишут.", dt(r.since).slice(0, 10))),
        Object.entries(r.no_birth).map(([cat, rows]) => h("details", null, h("summary", null, T(cat) + " · " + rows.length),
          table([["Учётка/слот", x => x.Userindex + "/" + x.Charidx], ["Предмет", x => itemLine(x.Code, x.name, null)], ["Сумка", x => plateName(x.Plate)],
            ["Получен", x => dt(x.GainDate)], ["Номер", x => trace(x.Uuid)]], rows.slice(0, 300)))),
        h("h2", null, T("Последнее событие — уничтожение, а строка жива · {0}", r.dead_alive.length)),
        table([["Учётка/слот", x => x.Userindex + "/" + x.Charidx], ["Предмет", x => itemLine(x.Code, x.name, null)], ["Последнее", x => dt(x.last_at) + " · " + x.last_table],
          ["", x => x.partial ? badge(x.note, "ok") : badge(x.note, "bad")], ["Номер", x => trace(x.Uuid)]], r.dead_alive),
        r.errors.length ? h("div", { class: "err" }, r.errors.map(e => e.table + ": " + e.error).join("\n")) : null] : null);
  };
  mount(shell("#/dupes", h("div", { class: "row" }, h("h1", { class: "grow" }, "Поиск дюпов"),
      h("button", { type: "button", onclick: () => load(false) }, "Быстро (база предметов)"),
      h("button", { type: "button", onclick: () => load(true) }, "Полностью (с журналами)")),
    h("div", { class: "muted small" }, "Только чтение. Правила — по тому, как номер живёт у сервера: у стопки одинаковый номер у двух владельцев штатен (неполный лот, отмена лота); у снаряжения, совела и одиночного — подозрение. «Исправить» — изъятием в карточке персонажа и следом предмета."),
    out));
  load(false);
}

// ---------- журнал действий ----------
async function viewAudit() {
  const out = h("div");
  const fAct = h("input", { placeholder: "действие (начало), напр. users." });
  const fLog = h("input", { placeholder: "кто (логин)" });
  const load = async (ev) => {
    if (ev) ev.preventDefault();
    put(out, h("div", { class: "muted" }, "Загружаю…"));
    try {
      const r = await api("/api/audit?action=" + encodeURIComponent(fAct.value) + "&login=" + encodeURIComponent(fLog.value));
      put(out, table([["№", x => x.id], ["Когда", x => dt(x.at)], ["Кто", x => x.login], ["Откуда", x => x.via + " " + x.ip],
        ["Действие", x => h("span", { class: "mono" }, x.action)], ["Цель", x => x.target],
        ["Итог", x => x.result === "ok" ? badge("ок", "ok") : x.result === "refused" ? badge("отказ", "warn") : badge("сбой", "bad")],
        ["Сообщение", x => x.message],
        ["", x => x.undone_by ? badge(T("откачено №{0}", x.undone_by)) : x.undo_of ? badge(T("откат №{0}", x.undo_of))
          : x.undo_note ? h("span", { class: "muted small" }, document.createTextNode(String(x.undo_note)))   // ★ ревизия 79 В-1: откатывать нечего — причина
          : (can("audit.undo") && x.reversible) ? h("button", { class: "ghost", onclick: async (e) => {
              e.stopPropagation();
              // ★ ревизия 63 С-1: откат операции со вторым фактором (корректировка баланса gp7 и т. п.) — окно с текстом записи и свежим кодом
              // ★ ревизия 85 М-9: всегда окно с текстом записи и справкой исходной операции (строка «Откат» — что вернётся и что нет)
              let body = {};
              const doc = await fetchOpDoc(x.action);
              const code = x.two_factor ? h("input", { type: "text", maxlength: 6, placeholder: T("свежий код второго фактора (не тот, которым входили)"), autocomplete: "one-time-code" }) : null;
              if (!await confirmWin(T("Откатить запись №{0} ({1})?", x.id, x.action), [h("div", { class: "pv" }, document.createTextNode(String(x.message || ""))),
                x.two_factor ? [h("div", { class: "muted small" }, T("Откат этого действия — со свежим кодом второго фактора.")), h("div", { class: "row" }, code)] : null,
                h("div", { class: "muted small" }, T("Справка исходного действия — откат возвращает то, что сказано в строке «Откат»."))], T("Откатить"), doc)) return;
              if (x.two_factor) {
                body = { totp: code.value.trim() };
              }
              try { const u = await api("/api/audit/" + x.id + "/undo", body); notify(u.message || T("откачено")); load(); } catch (er) { notify(er.message, true); }
            } }, "откатить") : ""],
        ["Детали", x => (x.params || x.before_json || x.after_json) ? h("details", null, h("summary", null, "показать"),
          h("div", { class: "mono small" }, x.params ? T("параметры: {0}", x.params) : "", h("br"), x.before_json ? T("было: {0}", x.before_json) : "", h("br"),
            x.after_json ? T("стало: {0}", x.after_json) : "")) : ""]], r.items));
    } catch (e) { put(out, errbox(e)); }
  };
  mount(shell("#/audit", h("h1", null, "Журнал действий"),
    h("form", { class: "row card", onsubmit: load }, fAct, fLog, h("button", { type: "submit" }, "Показать")), out));
  load();
}

// ---------- пользователи панели ----------
// Выполнить операцию (dry — только предпросмотр). ★ А7.10: справку предпросмотра кладёт в S.opDoc для окна подтверждения (takeOpDoc).
async function op(name, params, dry) {
  const r = await api("/api/ops/" + name, { params, dry: !!dry });
  S.opDoc = r && r.dry && r.doc ? { doc: r.doc, seq: (S.opDocSeq = (S.opDocSeq || 0) + 1) } : null;
  return r;
}
// ★ ревизия 85 В-7: каждое действие над пользователем панели — предпросмотр → окно подтверждения со справкой → выполнение (как у остальных
// операций); смена роли — не по выбору в списке, а после подтверждения (отказ — список возвращается к прежней роли).
async function usersRun(name, params, text, extra) {
  try { await op(name, params, true); } catch (e) { notify(e.message, true); return null; }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, text), extra || null])) return null;
  try { const x = await op(name, params, false); if (x && x.message) notify(T(x.message)); return x; } catch (e) { notify(e.message, true); return null; }
}
// Раздел «Пользователи панели»
async function viewUsers() {
  const out = h("div");
  const load = async () => {
    put(out, h("div", { class: "muted" }, "Загружаю…"));
    try {
      const r = await api("/api/users");
      const title = id => T((r.roles.find(x => x.id === id) || { title: id }).title);
      const after = x => { load(); return x; };
      put(out, table([["Логин", u => u.login], ["Роль", u => {
          const sel = h("select", null, r.roles.map(x => h("option", { value: x.id, selected: x.id === u.role }, x.title)));
          sel.addEventListener("change", async () => {
            const to = sel.value;
            sel.value = u.role;                           // до подтверждения — прежняя роль
            after(await usersRun("users.set_role", { login: u.login, role: to }, T("сменить роль {0}: {1} → {2} (сессии пользователя отзываются)", u.login, title(u.role), title(to))));
          });
          return sel; }],
        ["Второй фактор", u => u.totp_on ? badge("включён", "ok") : badge("нет", u.role === "owner" || u.role === "admin" ? "warn" : "")],
        ["Состояние", u => u.disabled ? badge("отключён", "bad") : u.locked_until ? badge(T("замок до {0}", dt(u.locked_until)), "warn") : badge("активен", "ok")],
        ["Сессий", u => u.sessions], ["Последний вход", u => dt(u.last_login_at) + (u.last_login_ip ? " · " + u.last_login_ip : "")],
        ["", u => h("div", { class: "row" },
          h("button", { class: "ghost", onclick: async () => after(await usersRun("users.set_disabled", { login: u.login, disabled: !u.disabled },
            u.disabled ? T("включить пользователя {0}", u.login) : T("отключить пользователя {0} (все его сессии отзываются)", u.login))) }, u.disabled ? "включить" : "отключить"),
          h("button", { class: "ghost", onclick: async () => {
            const pw = h("input", { type: "password", autocomplete: "new-password", placeholder: T("новый временный пароль (не короче 10)") });
            if (!await confirmWin(T("Сбросить пароль {0}", u.login), [h("div", { class: "row" }, pw)], T("Дальше"), null) || !pw.value) return;
            after(await usersRun("users.reset_password", { login: u.login, password: pw.value }, T("новый временный пароль для {0} (сессии отзываются)", u.login)));
          } }, "сбросить пароль"),
          u.totp_on ? h("button", { class: "ghost", onclick: async () => after(await usersRun("users.reset_totp", { login: u.login },
            T("снять второй фактор у {0} (сессии отзываются)", u.login))) }, "снять 2FA") : null)]],
        r.items));
    } catch (e) { put(out, errbox(e)); }
  };
  const login = h("input", { placeholder: "логин" }), pw = h("input", { type: "password", placeholder: "временный пароль", autocomplete: "new-password" });
  const role = h("select", null, ["gm", "support", "admin", "owner"].map(x => h("option", { value: x }, x)));
  const err = h("div", { class: "err" });
  const add = async (ev) => {
    ev.preventDefault(); err.textContent = "";
    const prm = { login: login.value, password: pw.value, role: role.value };
    try { await op("users.create", prm, true); } catch (e) { err.textContent = e.message; return; }
    if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T("создать пользователя {0} с ролью {1}", prm.login, prm.role))])) return;
    try { const r = await op("users.create", prm, false); notify(T(r.message)); login.value = pw.value = ""; load(); }
    catch (e) { err.textContent = e.message; }
  };
  mount(shell("#/users", h("h1", null, "Пользователи панели"),
    h("form", { class: "card row", onsubmit: add }, login, pw, role, h("button", { type: "submit" }, "Создать"), err),
    h("div", { class: "muted small" }, "Владелец и администратор обязаны включить второй фактор при первом входе. Смена роли и отключение отзывают сессии пользователя."),
    out));
  load();
}

// QR-код (строки '0'/'1' от службы, core/qr.py) → SVG; модуль 4 px, поле 4 модуля (как требует стандарт).
function qrSvg(rows) {
  const NS = "http://www.w3.org/2000/svg", n = rows.length, q = 4, size = (n + 2 * q) * 4;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 " + (n + 2 * q) + " " + (n + 2 * q));
  svg.setAttribute("width", size); svg.setAttribute("height", size); svg.setAttribute("class", "qr");
  svg.setAttribute("shape-rendering", "crispEdges");
  const bg = document.createElementNS(NS, "rect");
  bg.setAttribute("width", n + 2 * q); bg.setAttribute("height", n + 2 * q); bg.setAttribute("fill", "#fff");
  svg.append(bg);
  let d = "";
  rows.forEach((r, y) => { for (let x = 0; x < n; x++) if (r[x] === "1") d += "M" + (x + q) + " " + (y + q) + "h1v1h-1z"; });
  const p = document.createElementNS(NS, "path");
  p.setAttribute("d", d); p.setAttribute("fill", "#000");
  svg.append(p);
  return svg;
}

// ---------- о себе ----------
function viewMe() {
  const u = S.me.user;
  const totpBox = h("div");
  const renderTotp = () => {
    if (S.me.user.totp_on) return put(totpBox, badge("второй фактор включён", "ok"));
    const code = h("input", { inputmode: "numeric", maxlength: 6, placeholder: "6 цифр из приложения", autocomplete: "one-time-code" });
    const info = h("div");
    const err = h("div", { class: "err" });
    const step2 = h("div", { class: "row", style: { display: "none" } }, code, h("button", { type: "button", class: "ok", onclick: async () => {
        err.textContent = "";
        try {
          await api("/api/self/totp/enable", { totp_code: code.value.trim() }); await loadMe();
          location.hash = "#/status"; render();
        } catch (e) { err.textContent = e.message; } } }, "Включить"));
    put(totpBox,
      S.me.need_totp_setup ? h("div", { class: "note big" }, T("Для роли «{0}» второй фактор обязателен. Пока он не включён, остальные разделы закрыты. Это займёт минуту:", T(S.me.role_title))) : null,
      h("ol", null,
        h("li", null, "Поставьте на телефон приложение-аутентификатор: Google Authenticator, Microsoft Authenticator, Aegis, 1Password и т.п."),
        h("li", null, "Нажмите «Показать QR-код» и отсканируйте его в приложении. Если камера недоступна, введите ключ вручную, тип «по времени»."),
        h("li", null, "Введите 6 цифр, которые покажет приложение, и нажмите «Включить».")),
      h("div", { class: "row" }, h("button", { type: "button", class: "gold", onclick: async () => {
        err.textContent = "";
        try {
          const r = await api("/api/self/totp/begin", {});
          put(info, h("div", { class: "totp" }, qrSvg(r.qr),
            h("div", null, h("div", { class: "muted" }, "Ключ для ручного ввода:"),
              h("div", { class: "mono key" }, r.secret.replace(/(.{4})/g, "$1 ").trim()),
              h("div", { class: "muted small" }, T("Учётная запись: {0}", u.login + " · Astory")))));
          step2.style.display = ""; code.focus();
        } catch (e) { err.textContent = e.message; } } }, "Показать QR-код")),
      info, step2, err, totpDoc);
  };
  const totpDoc = h("div");                       // ★ ревизия 85 В-7: справка self.totp_enable в карточке (свой маршрут /api/self/totp/*)
  fetchOpDoc("self.totp_enable").then(d => put(totpDoc, opDocBlock(d)));
  renderTotp();
  const o = h("input", { type: "password", autocomplete: "current-password" }), n1 = h("input", { type: "password", autocomplete: "new-password" }), n2 = h("input", { type: "password", autocomplete: "new-password" });
  const perr = h("div", { class: "err" });
  const chpw = async (ev) => {
    ev.preventDefault(); perr.textContent = "";
    if (n1.value !== n2.value) { perr.textContent = T("новые пароли не совпали"); return; }
    // ★ ревизия 85 В-7: self.* идут своими маршрутами /api/self/* (сессия «только второй фактор», отзыв прочих сессий) — справка в своём окне
    if (!await confirmWin(T("Сменить свой пароль?"), [h("div", { class: "pv" }, T("пароль панели {0} будет заменён, прочие ваши сессии закроются", u.login))],
      T("Сменить"), await fetchOpDoc("self.password"))) return;
    try { await api("/api/self/password", { old_password: o.value, new_password: n1.value }); o.value = n1.value = n2.value = ""; perr.textContent = T("Пароль изменён."); }
    catch (e) { perr.textContent = e.message; }
  };
  const flash = S.flash; S.flash = "";
  const totpCard = h("div", { class: "card" }, h("h2", null, "Второй фактор"), totpBox);
  const infoCard = h("div", { class: "card" }, kv([["Логин", u.login], ["Роль", T(S.me.role_title)], ["Создан", dt(u.created_at)], ["Пароль сменён", dt(u.pw_changed_at)],
      ["Права", S.me.perms.join(", ")], ["Справочники предметов", S.me.ref && S.me.ref.built ? T("{0} · {1} предметов", S.me.ref.built, fmt(S.me.ref.items)) : T("не собраны")]]));
  mount(shell("#/me", h("h1", null, "О себе"),
    flash ? h("div", { class: "note big" }, flash) : null,
    S.me.need_totp_setup ? [totpCard, infoCard] : [infoCard, totpCard],
    h("form", { class: "card form", onsubmit: chpw }, h("h2", null, "Сменить пароль"),
      h("label", null, "Текущий"), o, h("label", null, "Новый (не короче 10)"), n1, h("label", null, "Ещё раз"), n2,
      h("div", { style: { height: "10px" } }), h("button", { type: "submit" }, "Сменить"), perr)));
}

// ---------- маршрутизатор ----------
async function render() {
  const my = ++S.nav;
  S.opDoc = null;                               // ★ ревизия 85 М-10: переход — справка прежнего предпросмотра никому не принадлежит
  document.documentElement.lang = S.lang;
  if (!S.me) await loadMe();
  if (stale(my)) return;
  if (!S.me) return viewLogin();
  const hs = location.hash || "#/status";
  if (S.me.need_totp_setup && !hs.startsWith("#/me")) {
    // не молча: владелец 16.11 «вошёл, но не может переключать вкладки» — разделы закрыты до включения второго фактора
    const n = NAV.find(x => hs.startsWith(x[0]));
    S.flash = T("Раздел «{0}» откроется после включения второго фактора — он ниже, это займёт минуту.", T(n ? n[1] : "…"));
    location.hash = "#/me"; return;
  }
  const [path, qs] = hs.slice(1).split("?");
  const parts = path.split("/").filter(Boolean);
  const q = new URLSearchParams(qs || "");
  switch (parts[0]) {
    case "players": return viewPlayers(q.get("q"), q.get("page"), q.get("online"));
    case "online": return viewOnline(q.get("q"));
    case "account": return viewAccount(parts[1], parts[2]);
    case "char": return viewChar(parts[1], parts[2], parts[3]);
    case "trace": return viewTrace(parts[1]);
    case "dupes": return viewDupes();
    case "shops": return viewShops(parts[1], parts[2]);
    case "logs": return viewLogs(my);
    case "ac": return viewAc(my);
    case "acdaily": return viewAcDaily(my);
    case "autoblock": return viewAutoblock(my);
    case "cases": return viewCases(my, q);
    case "names": return viewNames(my);
    case "reports": return viewReports(my, q);
    case "chat": return viewChat(my, q);
    case "attendance": return viewAttendance(my, q);
    case "releases": return viewReleases(my);
    case "crashes": return viewCrashes(my);
    case "outbox": return viewOutbox(my);
    case "community": return viewCommunity(my);
    case "notes": return viewNotes(my);
    case "telegram": return viewTelegram(my);
    case "money": return viewMoney(my);
    case "econ": return viewEcon(my);
    case "trade": return viewTrade(my);
    case "odds": return viewOdds(my);
    case "audit": return viewAudit();
    case "help": return viewHelp(my);
    case "users": return viewUsers();
    case "me": return viewMe();
    default: return viewStatus();
  }
}
window.addEventListener("hashchange", render);
document.addEventListener("DOMContentLoaded", render);
