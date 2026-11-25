// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Журналы стойки» (шаг А5.6, 21.11.2026; domains/logs.py, /api/logs*). ТОЛЬКО ЧТЕНИЕ.
// Источник → копия процесса → [вид] → файл; хвост N строк, поиск по подстроке и уровню, «следить» — опрос раз в 5 с с отметкой
// «размер:время» (служба открывает данные, только когда они изменились). Секреты в строках скрыты службой всегда, IP — без права
// logs.view_ip. Строки журналов — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (document.createTextNode), без перевода и без HTML.
// Общие помощники — из app.js: h(), T(), put(), mount(), shell(), sel(), badge(), errbox(), stale(), api(), notify().
"use strict";

const LG_POLL_MS = 5000;
const LG = { timer: null };
const lgText = s => document.createTextNode(String(s === null || s === undefined ? "" : s));
const lgQs = o => Object.entries(o).filter(([, v]) => v !== null && v !== undefined && v !== "").map(([k, v]) => k + "=" + encodeURIComponent(v)).join("&");

function lgStop() { if (LG.timer) { clearTimeout(LG.timer); LG.timer = null; } }

function lgLine(ln) {
  const links = (ln.ln || []).map(l => h("button", { type: "button", class: "ghost small", title: l.k === "account" ? "карточка учётки" : "поиск игрока",
    onclick: () => { lgStop(); location.hash = l.k === "account" ? "#/account/" + l.v : "#/players?q=" + encodeURIComponent(l.v); } },
    lgText(l.k === "account" ? "№" + l.v : l.v)));
  return h("div", { class: "lgline lv-" + ln.lv }, h("span", { class: "mono" }, lgText(ln.t)), links.length ? h("span", { class: "lglinks" }, links) : null);
}

async function viewLogs(my) {
  lgStop();
  const out = h("div"), info = h("div", { class: "muted small" }), pre = h("div", { class: "lgbox" });
  mount(shell("#/logs", h("h1", null, "Журналы стойки"), h("div", { class: "note" },
    lgText(T("Только чтение. Файлы открываются на время чтения с общим доступом и сразу закрываются; при «следить» — только когда изменились размер или время. Секреты в строках скрыты всегда, IP — по праву роли."))), out));
  let cat;
  try { cat = await api("/api/logs"); } catch (e) { put(out, errbox(e)); return; }
  if (stale(my)) return;
  const srcSel = sel(cat.sources.map(s => [s.key, s.title]), cat.sources[0].key);
  const procBox = h("span"), kindBox = h("span"), fileBox = h("span"), srcNote = h("div", { class: "muted small" });
  const nSel = sel([[100, "100"], [200, "200"], [500, "500"], [1000, "1000"], [2000, "2000"]], 200);
  const lvSel = sel([["", T("все уровни")], ["err", T("только ошибки")], ["warn", T("ошибки и предупреждения")], ["info", T("без отладки")]], "");
  const qIn = h("input", { type: "text", maxlength: 200, placeholder: "подстрока (после маскировки)", class: "mono" });
  const follow = h("input", { type: "checkbox" });
  const st = { sig: null, offset: null, head: null };
  const cur = () => cat.sources.find(s => s.key === srcSel.value);
  let procSel = null, kindSel = null, fileSel = null;

  async function loadFiles() {
    lgStop(); follow.checked = false; st.sig = st.offset = st.head = null; put(fileBox); put(pre); put(info);   // ревизия 46 Н-1
    const s = cur();
    const q = { source: s.key, proc: procSel.value, kind: kindSel ? kindSel.value : "" };
    let r;
    try { r = await api("/api/logs/files?" + lgQs(q)); } catch (e) { put(fileBox, errbox(e)); return; }
    if (stale(my)) return;
    if (s.kinds && !kindSel) {
      if (r.missing || !r.kinds.length) { put(kindBox, badge(T("папки {0} нет", r.dir), "warn")); return; }
      kindSel = sel(r.kinds.map(k => [k, k]), r.kinds.includes("Log_Game") ? "Log_Game" : r.kinds[0], () => loadFiles());
      put(kindBox, h("span", null, "Вид "), kindSel);
      return loadFiles();
    }
    if (r.missing) { put(fileBox, badge(T("папки {0} нет", r.dir), "warn"), r.note ? h("div", { class: "muted small" }, lgText(r.note)) : null); return; }
    if (!r.files.length) { put(fileBox, badge(T("в папке {0} файлов журнала нет", r.dir), "")); return; }
    // подписи файлов — текстовыми узлами, без перевода (ревизия 46, мелочь)
    fileSel = h("select", null, r.files.map((f, i) => { const o = h("option", { value: f.name, selected: i === 0 });
      o.append(lgText(f.name + " · " + fmtSize(f.size) + " · " + new Date(f.mtime).toLocaleString())); return o; }));
    fileSel.addEventListener("change", () => { lgStop(); follow.checked = false; st.sig = st.offset = st.head = null; show(); });
    put(fileBox, h("span", null, "Файл "), fileSel, r.more ? h("span", { class: "muted small" }, lgText(T("показаны {0} новых из {1}", r.files.length, r.total))) : null);
    show();
  }
  function fmtSize(b) { return b >= 1048576 ? T("{0} МБ", (b / 1048576).toFixed(1)) : b >= 1024 ? T("{0} КБ", Math.round(b / 1024)) : T("{0} б", b); }

  function render(r, append) {
    const rows = r.lines.map(lgLine);
    if (append) { pre.append(...rows); while (pre.childElementCount > 4000) pre.firstElementChild.remove(); pre.scrollTop = pre.scrollHeight; }
    else { put(pre, rows.length ? rows : h("div", { class: "muted" }, "пусто")); pre.scrollTop = pre.scrollHeight; }
    put(info, lgText(T("{0} · {1} · совпало {2}, показано {3}", r.path, fmtSize(r.size), r.matched === undefined ? "—" : r.matched, r.lines.length)),
      r.truncated ? badge(T("есть более ранние строки"), "") : null, r.masked ? badge(T("скрыто секретов и адресов: {0}", r.masked), "warn") : null,
      r.ip_masked ? badge(T("IP скрыты (нет права logs.view_ip)"), "") : null, r.skipped ? badge(T("пропущено {0} (прирост больше предела опроса)", fmtSize(r.skipped)), "warn") : null,
      r.reset ? badge(T("файл стал короче — хвост заново"), "warn") : null, r.exclusive ? badge(T("пишется без общего доступа — без «следить»"), "warn") : null);
  }

  async function show(poll) {
    if (!fileSel) return;
    const s = cur();
    const base = { source: s.key, proc: procSel.value, kind: kindSel ? kindSel.value : "", file: fileSel.value, lines: nSel.value,
      q: qIn.value.trim(), level: lvSel.value };
    if (poll) {
      if (st.offset === null) return;                       // ревизия 46 Н-1: без своей отметки не опрашивать
      Object.assign(base, { since: st.offset, sig: st.sig, head: st.head });
    } else { st.sig = st.offset = st.head = null; }
    let r;
    try { r = await api("/api/logs/tail?" + lgQs(base)); }
    catch (e) { if (poll) { put(info, errbox(e)); } else { put(pre); put(info, errbox(e)); } return; }
    if (stale(my)) { lgStop(); return; }
    st.sig = r.sig; st.offset = r.offset; st.head = r.head;
    if (!(poll && r.unchanged)) render(r, poll && !r.reset);
  }

  function tick() {
    lgStop();
    if (!follow.checked) return;
    LG.timer = setTimeout(async () => { if (stale(my) || !follow.checked) return lgStop(); await show(true); tick(); }, LG_POLL_MS);
  }
  follow.addEventListener("change", () => {
    if (follow.checked && st.offset === null) { follow.checked = false; notify(T("сначала покажите файл — «следить» продолжает от показанного"), true); return; }
    if (follow.checked && !cur().follow) { follow.checked = false; notify(T("«следить» за этим журналом нельзя: процесс пишет его без общего доступа"), true); return; }
    tick();
  });

  function pickSource() {
    lgStop(); kindSel = null; fileSel = null; put(kindBox); put(fileBox); put(pre); put(info);
    const s = cur();
    procSel = sel(s.procs.map(p => [p, p]), s.procs[0], () => { kindSel = null; put(kindBox); loadFiles(); });
    put(procBox, h("span", null, "Копия "), procSel);
    put(srcNote, lgText(T("Кодировка: UTF-8, иначе {0}. Ротация: {1}. Как пишет процесс: {2}.", s.enc, s.rotation, s.how)),
      s.local_only ? h("div", null, lgText(T("Прогоны restart_stack лежат на машине, где он шёл (ПК): служба видит только свою папку data\\stack_runs."))) : null);
    loadFiles();
  }
  srcSel.addEventListener("change", pickSource);

  put(out, h("div", { class: "card" },
    h("div", { class: "row" }, h("span", null, "Источник "), srcSel, procBox, kindBox),
    srcNote, h("div", { class: "row" }, fileBox),
    h("div", { class: "row" }, h("span", null, "Строк "), nSel, lvSel, qIn,
      h("button", { type: "button", onclick: () => show() }, "Показать"),
      h("label", null, follow, " следить (опрос раз в 5 с)")),
    info, pre,
    h("div", { class: "muted small" }, lgText(T("Пределы: строк ≤ {0}, окно поиска ≤ {1} МБ, один файл — не чаще раза в {2} с, {3} запросов в минуту.",
      cat.limits.lines_max, cat.limits.scan_max / 1048576, cat.limits.min_gap_s, cat.limits.per_min)))));
  pickSource();
}
