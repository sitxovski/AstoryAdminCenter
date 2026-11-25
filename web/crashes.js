// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Сбои клиента» (шаг А7.2, 23.11.2026; решения владельца А7 №1 — сбои расшифровываются только на ПК, ключ LogSeal на сервере
// не лежит, сюда приходит только сводка; №8 — .alog хранятся 60 суток, .acrash без срока; domains/crashes.py, /api/crashes).
//   Группы — место падения: код исключения + первые 3 кадра AsdaReborn-Win64-Shipping.exe (модуль+RVA). Символов нет: PDB хранится только у
//   последней сборки — имена функций даст шаг А7.3. Версия — по времени (releases.log): начало сессии, иначе время падения.
//   Частота — за сутки и за 7 суток; один и тот же пакет считается один раз (SHA-256), одно и то же падение в разных пакетах — тоже.
//   Квота LogDrop — служба считает сама (размеры и даты файлов, без расшифровки). Удаление .alog старше 60 суток — только owner: предпросмотр,
//   слово alogprune, свежий код второго фактора; .acrash не удаляются никогда.
// Всё, что пришло из пакетов и с ПК (логины, тексты ошибок, кадры, имена файлов, версии), — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами
// (acText), без T() и без HTML. Помощники — app.js и acjournal.js.
"use strict";

const CR_STATUS = { ok: ["прочитан", "ok"], unread: ["не прочитан", "bad"], nosummary: ["без сводки", "warn"], notfetched: ["не забран", "warn"] };
const crBadge = k => { const x = CR_STATUS[k] || [String(k || "—"), ""]; return badge(T(x[0]), x[1]); };
const crGb = v => v === null || v === undefined ? "—" : T("{0} ГиБ", (v / 1073741824).toFixed(2));
const crMb = v => v === null || v === undefined ? "—" : T("{0} МБ", (v / 1048576).toFixed(1));

function crLogin(x, canPlayers) {
  if (!x.login) return acText(T("логина нет"));
  if (x.uid === null || x.uid === undefined || !canPlayers) return acText(x.login);
  return acAccount(x.uid, x.login);
}

function crFrames(frames) {
  return h("div", { class: "mono small" }, (frames || []).map(f => h("div", null, acText(f))));
}

function crCases(rows, canPlayers) {
  return acTable([["Падение (UTC)", x => acText(x.crash_utc || x.received_utc)], ["Учётка", x => crLogin(x, canPlayers)],
    ["Итог", x => h("span", null, crBadge(x.status), x.status_note ? h("div", { class: "muted small" }, acText(x.status_note)) : null)],
    ["Код", x => h("span", null, acText(x.code), x.code_name ? h("div", { class: "muted small" }, acText(x.code_name)) : null)],
    ["Адрес", x => h("span", { class: "mono small" }, acText(x.addr), x.access ? h("div", null, acText(x.access)) : null)],
    ["Место", x => acText(x.sig)], ["Версия", x => h("span", null, acText(x.version), h("div", { class: "muted small" }, acText(x.version_note)))],
    ["Символы", x => x.symbols === "pdb" ? badge(T("есть"), "ok") : badge(T("символов нет"), "")],
    ["Пакет", x => h("span", { class: "small" }, acText(x.file), h("div", { class: "muted small mono" }, acText(x.sha)))]], rows || []);
}

async function viewCrashes(my) {
  const warnBox = h("div"), grpBox = h("div"), dayBox = h("div"), caseBox = h("div"), dropBox = h("div"), info = h("div", { class: "muted small" });
  mount(shell("#/crashes", h("div", { class: "row" }, h("h1", null, "Сбои клиента"),
      h("button", { type: "button", class: "ghost", onclick: () => load(true) }, "Обновить")),
    h("div", { class: "note" }, "Сбои расшифровываются только на ПК владельца (ключ LogSeal на сервере не лежит). Сюда приходит только сводка: код, место, версия по времени, учётка. Памяти процесса, хвоста журнала, путей и IP здесь нет."),
    info, warnBox,
    h("div", { class: "card" }, h("h2", null, "Места падения"), grpBox),
    h("div", { class: "card" }, h("h2", null, "По дням (14 суток)"), dayBox),
    h("div", { class: "card" }, h("h2", null, "Хранилище LogDrop"), dropBox),
    h("div", { class: "card" }, h("h2", null, "Все случаи"), caseBox)));

  const prune = async () => {
    let p;
    try { p = await op("crash.alog_prune", {}, true); } catch (e) { return notify(e.message, true); }
    const pv = p.preview || {};
    if (!pv.items_n) return notify(T(pv.text || "нечего удалять"));
    const word = h("input", { type: "text", maxlength: 12, placeholder: T("слово alogprune"), autocomplete: "off" });
    const code = h("input", { type: "text", maxlength: 6, placeholder: T("свежий код второго фактора (не тот, которым входили)"), autocomplete: "one-time-code" });
    if (!await confirmWin(T("Подтвердите удаление"), [h("div", { class: "pv" }, T(pv.text)),
      (pv.first || []).map(x => h("div", { class: "muted small mono" }, acText(x))),
      pv.items_n > (pv.first || []).length ? h("div", { class: "muted small" }, T("и ещё {0}", pv.items_n - (pv.first || []).length)) : null,
      (pv.warnings || []).map(w => h("div", { class: "note" }, T(w))),
      h("div", { class: "row" }, word, code)], T("Удалить"))) return;
    try {
      const x = await op("crash.alog_prune", { confirm: word.value.trim(), totp: code.value.trim(), expect: pv.expect }, false);
      notify(T(x.message)); load(true);
    } catch (e) { notify(e.message, true); }
  };

  async function load(force) {
    put(info, acText(T("Загружаю…")));
    let r;
    try { r = await api("/api/crashes" + (force ? "?force=1" : "")); } catch (e) { if (!stale(my)) { put(info, errbox(e)); put(grpBox); put(caseBox); } return; }
    if (stale(my)) return;
    const s = r.summary || {}, ld = r.logdrop || {}, sy = s.sync, can = r.can || {};
    put(info, sy ? h("span", null, acText(T("Сводка №{0}: собрана {1} UTC на {2} · ПК присылал {3} UTC (раз {4})", sy.id, sy.collected_utc, sy.host, sy.seen_utc, sy.seen_count)),
        " ", sy.stale ? badge(T("сводка старше {0} ч", r.pc_stale_h), "warn") : badge(T("свежая"), "ok"),
        acText(" · " + T("пакетов на сервере {0}, на ПК {1}, повторов {2}", (sy.stats || {}).on_server, (sy.stats || {}).local, (sy.stats || {}).dups)))
      : acText(s.error || T("ПК ещё не присылал сводку")));
    put(warnBox, (r.warnings || []).length ? h("div", { class: "card" }, h("h2", null, "Предупреждения"),
      (r.warnings || []).map(w => h("div", { class: "note" }, acText(w)))) : h("div", { class: "muted small" }, "Предупреждений нет."));
    put(grpBox,
      h("div", { class: "muted small" }, acText(T("Место = код исключения + первые {0} кадра {1}. RVA — у своей сборки: та же ошибка в другой сборке даёт другое место, пока нет символов.", r.sig_frames, r.exe))),
      h("div", { class: "muted small" }, "У падений, которые поднимает сам движок (GPU 0x8000, assert 0x4000, нехватка памяти 0x6000), общий путь отчёта пропускается, а в подпись входит текст ошибки, если он не «Fatal error!»."),
      acTable([["Место", x => h("span", { class: "mono" }, acText(x.sig))],
        ["Код", x => h("span", null, acText(x.code), h("div", { class: "muted small" }, acText(x.code_name)))],
        ["Кадры exe", x => h("span", null, x.skipped ? h("div", { class: "muted small" }, acText(T("после общего пути отчёта движка ({0} кадра пропущено):", x.skipped))) : null,
          crFrames(x.place || []),
          x.exe_frames ? null : h("div", { class: "muted small" }, acText(T("кадров exe нет — первые кадры стека:"))), x.exe_frames ? null : crFrames(x.frames.slice(0, 3)))],
        ["Адрес", x => h("span", { class: "mono small" }, acText(x.addr), x.error ? h("div", { class: "muted small" }, acText(x.error)) : null)],
        ["Всего", x => acText(x.n)], ["За сутки", x => acText(x.n_24h)], ["За 7 суток", x => acText(x.n_7d)],
        ["Учётки (заявлены клиентом)", x => h("span", null, (x.accounts || []).map(a => h("div", null, crLogin(a, can["players.view"]))),
          x.unknown ? h("div", { class: "muted small" }, acText(T("без логина: {0}", x.unknown))) : null)],
        ["Версии (по времени)", x => h("span", null, (x.versions || []).map(v => h("div", null, acText(v.version + " × " + v.n))))],
        ["Первое / последнее (UTC)", x => h("span", null, acText(x.first), h("div", null, acText(x.last)))],
        ["Символы", () => badge(T("символов нет"), "")]], s.groups || []),
      h("div", { class: "muted small" }, "Символов нет: PDB хранится только у последней сборки, поэтому кадры — модуль+RVA без имён функций (шаг А7.3)."),
      h("div", { class: "muted small" }, "Логин заявлен клиентом игрока и проверен приёмником только на существование учётки — это подсказка для диагностики, а не доказательство."));
    const mx = Math.max(1, ...(s.days || []).map(d => d.n));
    put(dayBox, acTable([["День (UTC)", x => acText(x.day)], ["Падений", x => acText(x.n)],
      ["", x => h("div", { class: "bar", style: { width: Math.round(160 * x.n / mx) + "px", height: "8px", background: "var(--accent, #b88a2e)" } })]], s.days || []));
    if (ld.error) put(dropBox, h("div", { class: "err" }, acText(ld.error)));
    else {
      const be = ld.by_ext || {}, old = ld.old_alog || {};
      put(dropBox,
        kv([["Занято", h("span", null, acText(T("{0} из {1} ({2}%)", crGb(ld.used), crGb(ld.quota), ld.pct)), " ",
              ld.warn ? badge(T("выше порога {0}%", ld.warn_pct), "bad") : badge(T("ниже порога {0}%", ld.warn_pct), "ok"))],
            ["Журналы .alog", acText(T("{0} файлов, {1}", (be.alog || {}).n || 0, crGb((be.alog || {}).bytes || 0)))],
            ["Пакеты падений .acrash", acText(T("{0} файлов, {1} — хранятся без срока", (be.acrash || {}).n || 0, crMb((be.acrash || {}).bytes || 0)))],
            ["Самый старый день .alog", acText(old.oldest)],
            [T("Старше {0} суток", ld.keep_days), acText(T("{0} файлов .alog, {1}", old.n || 0, crMb(old.bytes || 0)))],
            ["Снято (UTC)", acText(ld.at)]]),
        h("h3", null, "Рост по полумесяцам"),
        acTable([["Полумесяц", x => acText(x.half)], ["Принято", x => acText(crGb(x.bytes))]], ld.halves || []),
        h("div", { class: "muted small" }, "Срок хранения .alog — 60 суток (решение владельца). Удаление — только кнопкой владельца, автоматической чистки нет: удалённые журналы не восстанавливаются."),
        can["crash.prune"] ? h("div", { class: "row" }, h("button", { type: "button", class: "gold", onclick: prune }, T("Удалить .alog старше {0} суток…", ld.keep_days))) : null);
    }
    put(caseBox, crCases(s.rows, can["players.view"]),
      h("div", { class: "muted small" }, "Логин заявлен клиентом игрока и проверен приёмником только на существование учётки — это подсказка для диагностики, а не доказательство."),
      can["crash.sync"] ? h("div", { class: "muted small" }, "Прислать с ПК: python AstoryAdminCenter\\asda_admin.py crashes sync (или задание ПК crash.sync в «Заданиях»).") : null);
  }
  load(false);
}
