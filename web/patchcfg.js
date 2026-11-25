// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Данные игры → Настройки патчей» (шаг А5.5, 21.11.2026; domains/patchcfg.py, область cs_kinds/patchcfg.py).
// ini наших серверных DLL (AsdaPatch ×3 GameServer, AddonNPC ×3 NpcServer, LoginPatch, DBPatch, SrvDbPatch ×5) во ВСЕХ копиях: описание секции
// из реестра INDEX.md, режим по журналу патчей последнего запуска (действует / журнал / выключен / не встал / ждёт рестарта), значения ключей
// по копиям, тип и предел по исходнику. Правка — только позицией набора изменений (patch.set / config.set): проверка, сильная правка —
// второе подтверждение владельца, выкладка — рестартом стойки с объявлением. Стоковые конфиги стойки — на чтение (секреты без содержимого).
// Общие помощники — из app.js, shops.js и skilldata.js: h(), T(), put(), mount(), shell(), table(), kv(), sel(), badge(), can(), notify(),
// errbox(), stale(), api(), sdText(), sdAddAll(), shopsTabs(). Данные стойки — только текстовыми узлами (HTML из данных не вставляется).
"use strict";

const PC_MODE = { active: ["действует", "ok"], journal: ["журнал (Mode=0)", "warn"], off: ["выключен", ""],
  self_off: ["в ini включён, установка сама выключила", "warn"], pending_on: ["включён после старта — ждёт рестарта", "warn"],
  pending_off: ["выключен после старта — ждёт рестарта", "warn"], failed: ["НЕ ВСТАЛ ([MISMATCH] / [ОШИБКА])", "bad"],
  nolog: ["нет в журнале запуска", ""], absent: ["секции нет в файле", "bad"], unread: ["не прочитано", "bad"], general: ["—", ""] };

function pcModes(sec) {
  const groups = {};
  Object.entries(sec.modes).forEach(([g, m]) => { (groups[m] = groups[m] || []).push(g); });
  return h("span", null, Object.entries(groups).map(([m, gs]) => badge(T("{0}: {1}", T((PC_MODE[m] || [m])[0]), gs.join(", ")), (PC_MODE[m] || [])[1])));
}

// ★ ревизия 45: тип и предел ключа — с недопустимыми значениями, «выключает патч» и длиной буфера строки
function pcType(r) {
  let t = r.type + (r.lo !== null || r.hi !== null ? " " + (r.lo ?? "") + "…" + (r.hi ?? "") : "");
  if ((r.excl || []).length) t += " " + T("кроме {0}", r.excl.join(", "));
  if ((r.off_when || []).length) t += " · " + T("выключает патч: {0}", r.off_when.map(o => o[0] + " " + o[1]).join(", "));
  if (r.maxlen) t += " · " + T("до {0} знаков", r.maxlen);
  return t;
}

function pcSection(box, target, dll, sec, trm) {
  const scope = dll.family === "GSP" || dll.family === "NPCP"
    ? sel([["all", T("все копии")], ["field", T("поле + Ch2")], ["indun", T("только Indun")]], "all") : null;
  const rows = sec.keys.map(k => Object.assign({}, k, {
    inp: k.edit && !k.secret ? h("input", { type: "text", maxlength: k.maxlen || 511, class: "mono", value: "" }) : null }));
  const collect = () => rows.filter(r => r.inp && r.inp.value.trim() !== "").map(r => ["patch.set",
    { dll: dll.dll, section: sec.name, key: r.key, value: r.inp.value.trim(), scope: scope ? scope.value : "all" }]);
  const btn = can("patchcfg.edit") ? h("button", { type: "button", onclick: () => sdAddAll(target, T("Настройки патча {0}", sec.name), collect()) },
    "Добавить в набор") : null;
  const idx = (sec.index || []).map(x => h("div", { class: "muted small" }, sdText(x.text), x.docs.length ? h("span", { class: "mono small" }, sdText(" · " + x.docs.join(", "))) : null));
  const deps = [];
  if (Object.keys(sec.needs || {}).length) deps.push(T("вызывает код / читает ключи: {0}",
    Object.entries(sec.needs).map(([p, s]) => p + " (" + s.slice(0, 3).join(", ") + (s.length > 3 ? ", …" : "") + ")").join("; ")));
  if ((sec.hard_users || []).length) deps.push(T("от него зависят (выключение — отказ): {0}", sec.hard_users.join(", ")));
  if (sec.panel) deps.push(T("нужен панели (мост P127) — панелью не выключается"));
  if (sec.strong) deps.push(T("патч защиты / античита — любая правка требует второго подтверждения владельца"));
  const copies = dll.copies.map(c => c.folder);
  put(box, h("div", { class: "card" },
    h("h2", null, sdText(dll.dll + " [" + sec.name + "]")), idx.length ? idx : h("div", { class: "muted small" }, "в реестре INDEX.md строки нет"),
    (sec.docs || []).length ? h("div", { class: "mono small" }, sdText(T("документ: {0}", sec.docs.join(", ")))) : null,
    h("div", { class: "row" }, pcModes(sec)), deps.map(d => h("div", { class: "note" }, sdText(d))),
    sec.comment ? h("details", null, h("summary", null, "комментарий шаблона (Config.cpp)"), h("pre", { class: "mono small" }, sdText(sec.comment))) : null,
    table([["Ключ", r => sdText(r.key)], ["Тип", r => sdText(pcType(r))],
      ["Умолчание", r => sdText(r.def)],
      ...copies.map(g => [g, r => h("span", { class: r.diverge ? "bad mono" : "mono" }, sdText(r.values[g] === null || r.values[g] === undefined ? "—" : r.values[g]))]),
      ["Станет", r => r.inp || sdText(r.secret ? T("секрет — скрыто") : T("только просмотр: {0}", (trm || {})[r.view_only] || r.view_only || "—"))]], rows),
    scope ? h("div", { class: "row" }, h("span", null, "Копии"), scope) : null, btn,
    h("div", { class: "muted small" }, T("Ключ читается DLL только при старте процесса — действует после рестарта стойки (выкладка набора). Пары «поле — Ch2» правятся вместе (паритет)."))));
}

async function viewPatchCfg(my) {
  const out = h("div");
  mount(shell("#/shops", h("h1", null, "Настройки патчей"), shopsTabs("#/shops/patches"), h("div", { class: "note" },
    sdText(T("ini серверных DLL во всех копиях и режим по журналу патчей последнего запуска. Живые файлы панель не пишет: правка — позицией набора изменений и рестартом стойки с объявлением. Конфиги стойки — внизу, на чтение."))), out));
  let sets = [];
  try { sets = (await api("/api/shops/sets")).items.filter(x => x.status === "draft" || x.status === "checked"); } catch (e) { sets = []; }
  if (stale(my)) return;
  const target = sel([["", T("новый набор")]].concat(sets.map(x => [x.id, "№" + x.id + " " + x.title])), sets.length ? sets[0].id : "");
  const card = h("div");
  let r;
  try { r = await api("/api/patchcfg"); } catch (e) { put(out, errbox(e)); return; }
  if (stale(my)) return;
  const dllSel = sel(r.dlls.map(d => [d.dll, d.dll + " — " + d.ini]), r.dlls[0].dll);
  const q = h("input", { type: "search", placeholder: "поиск секции или ключа" });
  const only = h("input", { type: "checkbox", class: "chk" });
  const list = h("div");
  const draw = () => {
    const d = r.dlls.find(x => x.dll === dllSel.value);
    const s = q.value.trim().toLowerCase();
    const secs = d.sections.filter(x => (!s || x.name.toLowerCase().includes(s) || x.keys.some(k => k.key.toLowerCase().includes(s)))
      && (!only.checked || Object.values(x.modes).some(m => m !== "active" && m !== "general") || x.keys.some(k => k.diverge)));
    put(list,
      table([["Копия", c => sdText(c.folder)], ["ini", c => sdText(c.read ? (c.md5 || "").slice(0, 8) + " · " + (c.enc || "") : T("не прочитан"))],
        ["Version", c => sdText(String(c.version ?? "—"))], ["MasterEnable", c => sdText(String(c.master ?? "—"))],
        ["Последний запуск", c => sdText(c.run ? T("{0}, PID {1}, итог {2}", c.run.start || "—", c.run.pid || "—", (c.run.total || []).join(" / ")) : T(c.log === "unread" ? "журнал не прочитан" : "запуска в журнале нет"))]], d.copies),
      h("div", { class: "muted small" }, sdText(T("Секций {0} (Version исходника {1})", d.sections.length, d.version_src))),
      // ★ ревизия 45 (мелочь): код читает секцию, которой нет в шаблоне ini — значение всегда умолчание кода, панелью не правится
      (d.outside || []).map(o => h("div", { class: "note" }, sdText(T("код читает секцию [{0}] вне шаблона ini ({1}) — в ini её нет, действует умолчание кода, панелью не правится",
        o.section, (o.where || []).join(", "))))),
      table([["Секция", x => sdText(x.name)], ["Режим", x => pcModes(x)], ["Расходятся", x => sdText(x.keys.filter(k => k.diverge).map(k => k.key).join(", ") || "—")],
        ["Описание", x => sdText(x.index && x.index[0] ? x.index[0].text.slice(0, 160) : "—")]], secs, x => pcSection(card, target, d, x, r.tr)));
  };
  dllSel.addEventListener("change", draw);
  q.addEventListener("input", draw);
  only.addEventListener("change", draw);
  const cfgBox = h("div");
  const loadCfg = async () => {
    put(cfgBox, h("div", { class: "muted" }, "Загружаю…"));
    let c;
    try { c = await api("/api/patchcfg?configs=1"); } catch (e) { put(cfgBox, errbox(e)); return; }
    const firstEdit = c.configs.find(x => x.edit && x.read && x.text);
    put(cfgBox, table([["Копия", x => sdText(x.folder)], ["Файл", x => sdText(x.file)],
      ["Правка", x => badge(T(x.edit ? "набором изменений" : x.secret ? "секрет — содержимое скрыто" : "только просмотр"), x.edit ? "ok" : x.secret ? "bad" : "")],
      ["Что читается", x => sdText(x.what)], ["Почему", x => sdText(x.why || "—")],
      ["Содержимое", x => x.text === null || x.text === undefined ? sdText(x.read ? T("{0} б, {1}", x.size ?? "—", x.mtime || "—") : T("не прочитан"))
        : h("details", null, h("summary", null, sdText((x.md5 || "").slice(0, 8))), h("pre", { class: "mono small" }, sdText(x.text)))]], c.configs),
      firstEdit ? pcCfgEdit(target, firstEdit) : null);
  };
  put(out, h("div", { class: "card" }, h("div", { class: "row" }, h("span", null, sdText(T("Набор"))), target,
      can("patchcfg.edit") ? null : h("span", { class: "muted small" }, sdText(T("правка — с правом «patchcfg.edit»")))),
    h("div", { class: "row" }, dllSel, q, h("label", { class: "row chkl" }, only, "только не «действует» и расхождения"),
      h("button", { type: "button", class: "ghost", onclick: async () => { try { r = await api("/api/patchcfg?force=1"); draw(); } catch (e) { notify(e.message, true); } } }, "Обновить")),
    (r.warnings || []).map(w => h("div", { class: "note" }, sdText(w))), list), card,
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { class: "grow" }, "Конфиги стойки"),
      h("button", { type: "button", class: "ghost", onclick: loadCfg }, "Показать")), cfgBox,
      h("div", { class: "muted small" }, T("Правится наборами только белый список (ini\\Collection.ini: время сбора); адреса, порты, потоки и подключения к базе — только просмотр."))));
  draw();
}

// ★ ревизия 45 (мелочь): позиция config.set из окна «Конфиги стойки» — ключи белого списка (ini\Collection.ini CollectionTypeAniTimeNN,
// одно значение на все NpcServer). Ключи и текущие значения — из текста файла первой копии; проверка значений — на сервере (cs_kinds/patchcfg).
function pcCfgEdit(target, x) {
  const keys = [];
  let sec = "";
  (x.text || "").split(/\r?\n/).forEach(ln => {
    const s = ln.trim();
    const m = /^\[([^\]]+)\]$/.exec(s);
    if (m) { sec = m[1]; return; }
    const k = /^(CollectionTypeAniTime\d\d)\s*=\s*(\S*)/i.exec(s);
    if (k && sec.toUpperCase() === "COLLECTION_INFO") keys.push({ key: k[1], now: k[2], inp: h("input", { type: "number", min: 100, max: 65535, class: "mono", value: "" }) });
  });
  if (!keys.length) return null;
  const collect = () => keys.filter(k => k.inp.value.trim() !== "").map(k => ["config.set",
    { file: x.file, section: "COLLECTION_INFO", key: k.key, value: k.inp.value.trim() }]);
  return h("div", { class: "card" }, h("h3", null, sdText(T("Правка {0} (все NpcServer)", x.file))),
    table([["Ключ", k => sdText(k.key)], [T("Сейчас ({0})", x.folder), k => sdText(k.now)], ["Станет, мс", k => k.inp]], keys),
    can("patchcfg.edit") ? h("button", { type: "button", onclick: () => sdAddAll(target, T("Конфиг {0}", x.file), collect()) }, "Добавить в набор") : null);
}
