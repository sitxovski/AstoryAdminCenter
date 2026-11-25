// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Заметки к выпуску» (шаг А7.7, 24.11.2026; решение владельца А7 №7 — черновик заметок для игроков в панели и кнопка
// «Опубликовать»; №2 — тексты EN / RU / AR пишутся руками, канал и роль выбираются; domains/notes.py, /api/notes).
// Записи текущего changelog и неопубликованные записи прежних файлов (реестр, ★ ревизия 82 В-2) с видом, состоянием, пометкой
// «чувствительное» (★ р82 В-1) и отметкой «опубликовано» (по итогу бота в очереди Discord); галочки, заголовок ветки, роль Patch Ping или без
// упоминания, тексты EN / RU / AR (RU можно заполнить из «Что стало» отмеченных НЕчувствительных записей — EN и AR ничем не заполняются),
// предпросмотр как в Discord с длинами (AR — справа налево, ★ р82 М-4); действия — операции notes.*: черновик (notes.draft), скрыть / вернуть
// (notes.hide), отметить «опубликовано вне панели» (notes.mark), опубликовать (notes.publish, с отметкой «тест» — бот не публикует), «итог
// неизвестен» — ветки нет / ветка есть (notes.resolve). Откат — в «Журнале действий». Тексты changelog и оператора — НЕДОВЕРЕННЫЙ текст:
// только текстовыми узлами (acText), без T() и без HTML. Помощники — app.js и acjournal.js.
"use strict";

// вид записи → [подпись, оттенок значка]
const NT_AREA = { client: ["клиент", "ok"], server: ["сервер", "ok"], release: ["выпуск", "ok"], clarify: ["уточнение", "warn"], service: ["служебное", ""] };
// состояние записи → подпись ({0} — номер выпуска)
const NT_STATUS = { released: "в выпуске {0}", unreleased: "ещё не в выпуске", live: "уже действует", pending: "ещё не действует",
  unknown: "статус не указан", service: "игрокам не видно" };
// отметка «опубликовано» записи → [подпись, оттенок]
const NT_PUB = { published: ["опубликовано", "ok"], queued: ["ждёт бота", "warn"], unknown: ["итог неизвестен", "bad"], failed: ["ошибка — записи свободны", ""],
  test: ["только тест", ""], free: ["не опубликовано", ""] };
// состояние публикации в истории → [подпись, оттенок]
const NT_POST = { queued: ["ждёт бота", "warn"], claimed: ["бот взял", "warn"], posted: ["опубликовано", "ok"], failed: ["ошибка — записи свободны", "bad"],
  unknown: ["итог неизвестен", "bad"], cancelled: ["отменено", ""], expired: ["просрочено", "warn"], test: ["тест (не публиковалось)", "ok"],
  deleted: ["удалено из Discord", ""], deleting: ["удаление ждёт бота", "warn"], manual: ["отмечено вне панели", "ok"], revoked: ["отметка снята", ""], hold: ["ждёт", ""] };
// значок по словарю (неизвестное значение — как есть)
const ntBadge = (map, k) => { const x = map[k] || [String(k || "—"), ""]; return badge(T(x[0]), x[1]); };

// строки сообщения Discord так же, как собирают панель (domains/outbox.compose) и бот: роль, затем языки с флагами (EN, AR, RU) → [[язык, строка]]
function ntParts(mention, vals, langs, flags) {
  const parts = mention ? [["", mention]] : [];
  for (const k of langs) { const v = String(vals[k] || "").trim(); if (v) parts.push([k, flags[k] + " " + v]); }
  return parts;
}
// всё сообщение одной строкой (для подсчёта длины)
function ntCompose(mention, vals, langs, flags) { return ntParts(mention, vals, langs, flags).map(p => p[1]).join("\n"); }

// предпросмотр операции (dry) → окно подтверждения → применение с отпечатком expect → обновить экран
async function ntRun(name, params, reload, okText) {
  let p;
  try { p = await op(name, params, true); } catch (e) { return notify(e.message, true); }
  const pre = { whiteSpace: "pre-wrap" };
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv", style: pre }, acText(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note", style: pre }, acText(w)))], okText)) return;
  try { const x = await op(name, Object.assign(p.preview.expect !== undefined ? { expect: p.preview.expect } : {}, params), false);
        notify(T(x.message || "готово")); }
  catch (e) { notify(e.message, true); }
  reload();
}

// окно «причина» (3–200 знаков) → текст или null
async function ntAsk(title, note) {
  const inp = h("input", { type: "text", maxlength: "200", style: { width: "100%" }, placeholder: "причина (3–200 знаков)" });
  if (!await confirmWin(T(title), [h("div", { class: "note" }, note), h("label", null, "Причина", inp)], "Дальше")) return null;
  return inp.value;
}

// экран «Заметки к выпуску»
async function viewNotes(my) {
  const info = h("div", { class: "muted small" }), warnBox = h("div"), listBox = h("div"), postsBox = h("div"), lenBox = h("div", { class: "muted small" }),
    pvBox = h("div", { class: "pv small", style: { whiteSpace: "pre-wrap" } });
  const show = h("select", null, [["open", "не опубликованные"], ["all", "все"]].map(([v, t]) => h("option", { value: v }, T(t))));
  const svc = h("input", { type: "checkbox" });
  const title = h("input", { type: "text", maxlength: "100", style: { width: "100%" }, placeholder: "заголовок ветки форума updates (до 100 знаков)" });
  const role = h("select", null, h("option", { value: "patch" }, "Patch Ping"), h("option", { value: "" }, T("без упоминания")));
  const ttl = h("input", { type: "number", min: "5", max: "1440", style: { width: "7em" } });
  const ta = (ph, dir) => h("textarea", { rows: "8", style: { width: "100%" }, placeholder: ph, dir: dir || null });
  const en = ta("текст EN (обязательно, пишется руками)"), ru = ta("текст RU (можно пусто)"), ar = ta("текст AR (можно пусто, пишется руками)", "rtl");
  const test = h("input", { type: "checkbox" });
  let r = null, can = {}, sel = new Set(), filled = false;
  [title, en, ru, ar, ttl].forEach(x => x.addEventListener("input", () => preview()));
  role.addEventListener("change", () => preview());
  show.addEventListener("change", () => table());
  svc.addEventListener("change", () => table());
  const keysSel = () => (r ? r.entries : []).filter(x => sel.has(x.key)).map(x => x.key);
  const params = () => ({ snap: r && r.snap ? r.snap.id : null, keys: keysSel(), title: title.value, role: role.value, ttl: ttl.value,
    en: en.value, ru: ru.value, ar: ar.value });
  const btn = (label, fn, cls) => h("button", { type: "button", class: cls || "ghost", onclick: fn }, label);
  const draftBtn = btn("Сохранить черновик", () => ntRun("notes.draft", params(), load, "Сохранить"));
  const hideBtn = btn("Скрыть отмеченные", () => hide(keysSel(), true));
  const markBtn = btn("Отметить «опубликовано вне панели»", () => mark());
  const pubBtn = btn("Опубликовать", () => ntRun("notes.publish", Object.assign(params(), { test: test.checked }), load,
    test.checked ? "Поставить тест" : "Опубликовать для всех"), "ok");
  const fillBtn = btn("Заполнить RU из «Что стало» отмеченных", () => fillRu());
  const fillNote = h("div", { class: "note" });

  mount(shell("#/notes", h("div", { class: "row" }, h("h1", null, "Заметки к выпуску"), btn("Обновить", () => load())),
    h("div", { class: "note" }, "Черновик заметок для игроков из текущего changelog. Changelog присылает ПК владельца — панель его не пишет. Публикует бот Oracle на ПК в форум updates (раз в 30 с) — сервер Discord не видит."),
    info, warnBox,
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Записи changelog"), show,
        h("label", { class: "row" }, svc, h("span", null, "показывать служебные")),
        btn("Отметить по умолчанию", () => { sel = new Set(r.entries.filter(x => x.default && open(x)).map(x => x.key)); table(); preview(); }),
        btn("Снять все", () => { sel = new Set(); table(); preview(); }), hideBtn),
      h("div", { class: "muted small" }, "По умолчанию отмечены выпуски, записи клиента, вошедшие в выпуск, и сервера «уже действует». Служебные (админ-центр, инструменты, сборка), «ещё не …» и чувствительные (античит, пороги, номера игроков, стойка) сняты — их можно отметить, но текст чувствительных пишется своими словами."),
      listBox),
    h("div", { class: "card" }, h("h2", null, "Черновик"),
      h("label", null, "Заголовок ветки", title),
      h("div", { class: "row" }, h("label", null, "Роль", role), h("label", null, "Срок годности, мин", ttl)),
      h("label", null, "EN", en), h("div", { class: "row" }, h("span", null, "RU"), fillBtn), fillNote, ru, h("label", null, "AR", ar),
      h("div", { class: "muted small" }, "EN и AR ничем не заполняются: тексты пишутся руками (решение владельца №2). @everyone и @here запрещены. Сообщение — до 2000 знаков вместе с флагами и упоминанием, имя ветки — до 100 и за сутки не повторяется (части — «… (часть 2)»)."),
      h("h2", null, "Как будет в Discord"), lenBox, pvBox,
      h("label", { class: "row" }, test, h("span", null, "тест — бот отметит «тест» и в Discord ничего не опубликует")),
      h("div", { class: "row" }, draftBtn, markBtn, pubBtn)),
    h("div", { class: "card" }, h("h2", null, "Публикации заметок"), postsBox)));
  fillNote.style.display = "none";

  // свободна ли запись для новой публикации (опубликованное, ждущее бота и «итог неизвестен» — заняты; скрытая — нет)
  function open(x) { return (x.pub === "free" || x.pub === "test" || x.pub === "failed") && !x.hidden; }

  // таблица записей с фильтрами
  function table() {
    if (!r || !r.snap) return put(listBox);
    const rows = r.entries.filter(x => (show.value === "all" || open(x)) && (svc.checked || x.visible || sel.has(x.key))).slice().reverse();
    put(listBox, acTable([
      ["", x => { const c = h("input", { type: "checkbox", disabled: !open(x) || !can["notes.draft"] ? true : null });
                  c.checked = sel.has(x.key);
                  c.addEventListener("change", () => { if (c.checked) sel.add(x.key); else sel.delete(x.key); preview(); });
                  return c; }],
      ["Дата", x => h("span", null, acText(x.date), x.old ? h("div", { class: "muted small" }, acText(T("из файла {0}", x.file))) : null)],
      ["Вид", x => h("span", null, ntBadge(NT_AREA, x.area), h("div", { class: "muted small" }, acText(T(NT_STATUS[x.status] || x.status, x.release))),
        x.of_title ? h("div", { class: "muted small" }, acText(T("уточнение к «{0}»", x.of_title))) : null)],
      ["Запись", x => h("details", null, h("summary", null, acText(x.title)), h("div", { class: "small muted" }, acText(x.section)),
        h("div", { class: "small", style: { whiteSpace: "pre-wrap" } }, acText(x.body)))],
      ["Для RU", x => x.sens && x.sens.length
        ? h("div", { class: "small" }, badge(T("чувствительное"), "warn"), h("div", { class: "muted small" }, acText(x.sens.join(", "))),
            h("div", { class: "muted small" }, "в RU не переносится — перепишите своими словами"))
        : h("div", { class: "small", style: { whiteSpace: "pre-wrap", maxWidth: "28em" } }, acText(x.ru),
            x.ru_cut ? h("div", { class: "muted small" }, acText(T("убрано пунктов с внутренними деталями: {0}", x.ru_cut))) : null)],
      ["Публикация", x => h("span", null, x.hidden ? badge(T("скрыто"), "") : ntBadge(NT_PUB, x.pub),
        x.similar ? h("div", null, badge(T("похоже на уже опубликованное"), "warn"), h("div", { class: "muted small" }, acText(x.similar))) : null,
        x.hidden ? h("div", { class: "muted small" }, acText(x.hidden_note)) : null,
        x.hidden && can["notes.draft"] ? btn("Вернуть", () => hide([x.key], false)) : null,
        x.pub_post ? h("div", { class: "muted small" },
          acText(T(x.pub_kind === "manual" ? "отметка №{0}" : "публикация №{0}, очередь №{1}", x.pub_post, x.pub_outbox))) : null)]], rows),
      h("div", { class: "muted small" }, acText(T("отмечено {0} · всего записей {1}, видны игрокам {2}, не опубликовано {3}", sel.size, r.entries.length,
        r.entries.filter(x => x.visible).length, r.entries.filter(x => open(x)).length))));
  }

  // RU из «Что стало» отмеченных записей — без чувствительных (★ р82 В-1)
  async function fillRu() {
    const picked = r.entries.filter(x => sel.has(x.key));
    const skip = picked.filter(x => x.sens && x.sens.length);
    const t = picked.filter(x => !(x.sens && x.sens.length)).map(x => x.ru).filter(Boolean).join("\n");
    if (ru.value.trim() && !await confirmWin(T("Подтвердите"), h("div", { class: "note" }, "Заменить текст RU текстом «Что стало» отмеченных записей?"), "Заменить")) return;
    ru.value = t;
    fillNote.style.display = skip.length ? "" : "none";
    put(fillNote, skip.length ? acText(T("не перенесено записей с чувствительным: {0} ({1}) — перепишите их своими словами", skip.length,
      skip.map(x => x.title.slice(0, 60)).join(" · "))) : null);
    preview();
  }

  // длины и предпросмотр как в Discord: каждая строка языка своим блоком, AR — справа налево (★ р82 М-4)
  function preview() {
    if (!r) return;
    const L = r.limits, vals = { en: en.value, ru: ru.value, ar: ar.value };
    const parts = ntParts(role.value ? "@" + r.roles[role.value] : "", vals, r.langs, r.flags);
    const n = ntCompose(role.value ? "x".repeat(L.mention_max) : "", vals, r.langs, r.flags).length;   // длина строки JS — в единицах UTF-16, как dlen
    const tl = title.value.trim().length;
    const over = [n > L.msg_max ? T("сообщение длиннее {0}", L.msg_max) : null, tl > L.title_max ? T("имя ветки длиннее {0}", L.title_max) : null,
      ["en", "ru", "ar"].filter(k => vals[k].trim().length > L.text_max).map(k => T("текст {0} длиннее {1}", k.toUpperCase(), L.text_max))].flat().filter(Boolean);
    put(lenBox, acText(T("форум updates · ветка: {0} знаков из {1} · сообщение: {2} из {3} (с упоминанием роли) · отмечено записей {4}", tl, L.title_max, n, L.msg_max, sel.size)),
      over.length ? h("div", { class: "err" }, acText(over.join(" · "))) : null);
    put(pvBox, h("div", { class: "small muted" }, acText(T("ветка «{0}»", title.value.trim() || "—"))),
      parts.length ? parts.map(([k, line]) => h("div", { dir: k === "ar" ? "rtl" : "auto" }, acText(line))) : acText(T("(пусто)")));
  }

  // отметка «опубликовано вне панели» с причиной
  async function mark() {
    const note = await ntAsk("Опубликовано вне панели", "Отмеченные записи будут считаться опубликованными без Discord — например, то, что вы уже публиковали руками. Откат — в «Журнале действий».");
    if (note === null) return;
    ntRun("notes.mark", { snap: r && r.snap ? r.snap.id : null, keys: keysSel(), note }, load, "Отметить");
  }

  // скрыть записи из черновика (с причиной) или вернуть
  async function hide(keys, on) {
    if (!keys.length) return notify(T("отметьте хотя бы одну запись changelog"), true);
    const note = on ? await ntAsk("Скрыть из черновика", "Скрытые записи не попадают в черновик и в число неопубликованных. Вернуть — кнопкой «Вернуть» (фильтр «все») или откатом.") : "";
    if (note === null) return;
    ntRun("notes.hide", { keys, hide: on, note }, load, on ? "Скрыть" : "Вернуть");
  }

  // «итог неизвестен»: решение оператора по виду форума
  async function resolve(post, thread) {
    const note = await ntAsk(thread === "none" ? "Ветки в форуме нет" : "Ветка в форуме есть",
      thread === "none" ? "Сначала проверьте форум updates: если ветка на деле есть, следующая публикация даст дубль." : "Записи будут отмечены «опубликовано вне панели».");
    if (note === null) return;
    ntRun("notes.resolve", { post, thread, note }, load, "Записать");
  }

  // загрузить экран
  async function load() {
    put(info, acText(T("Загружаю…")));
    try { r = await api("/api/notes"); } catch (e) { if (!stale(my)) { put(info, errbox(e)); put(listBox); } return; }
    if (stale(my)) return;
    can = r.can || {};
    const s = r.snap;
    put(info, !r.installed ? acText(r.error) : s ? acText(T("changelog {0} · снимок №{1} от ПК {2} UTC (присылал {3} UTC, раз {4}) · {5} знаков · пределы Discord: {6} в час, {7} в сутки",
      s.file, s.id, s.collected, s.seen, s.seen_count, s.chars, r.limits.per_hour, r.limits.per_day))
      : acText(T("Снимка changelog нет")),
      h("div", { class: "muted small" }, "Прислать с ПК: python AstoryAdminCenter\\asda_admin.py notes push (или задание ПК notes.push в «Заданиях»)."));
    put(warnBox, (r.warnings || []).length ? h("div", { class: "card" }, h("h2", null, "Предупреждения"),
      (r.warnings || []).map(w => h("div", { class: "note" }, acText(w)))) : null);
    const entries = r.entries || [];
    const byKey = new Set(entries.filter(x => open(x)).map(x => x.key));
    if (!filled) {
      const d = r.draft;
      if (d && Array.isArray(d.keys)) {
        sel = new Set(d.keys.filter(k => byKey.has(k)));
        title.value = d.title || ""; role.value = d.role === "" ? "" : "patch"; ttl.value = d.ttl || r.limits.ttl_def;
        en.value = d.en || ""; ru.value = d.ru || ""; ar.value = d.ar || "";
      } else {
        sel = new Set(entries.filter(x => x.default && open(x)).map(x => x.key));
        title.value = r.title_hint || ""; ttl.value = r.limits.ttl_def;
      }
      filled = true;
    } else {
      sel = new Set([...sel].filter(k => byKey.has(k)));   // опубликованное, ушедшее в очередь и скрытое — снимается
    }
    draftBtn.style.display = hideBtn.style.display = can["notes.draft"] ? "" : "none";
    markBtn.style.display = pubBtn.style.display = can["community.post"] && s ? "" : "none";
    fillBtn.disabled = !s;
    table();
    preview();
    put(postsBox, acTable([["№", x => acText(x.id)], ["Создано (UTC)", x => h("span", null, acText(x.created), h("div", { class: "muted small" }, acText(x.by)))],
      ["Что", x => h("span", null, acText(x.kind === "manual" ? T("вне панели: {0}", x.note) : x.title),
        x.outbox ? h("div", { class: "muted small" }, acText(T("очередь Discord №{0}", x.outbox))) : null)],
      ["Записей", x => acText(x.entries)],
      ["Статус", x => h("span", null, ntBadge(NT_POST, x.state), x.test ? h("div", { class: "muted small" }, acText(T("проверочная"))) : null,
        x.error ? h("div", { class: "err" }, acText(x.error)) : null,
        x.can_resolve && can["community.post"] ? h("div", null, btn("Ветки нет", () => resolve(x.id, "none")), btn("Ветка есть", () => resolve(x.id, "exists"))) : null)]],
      r.posts || []),
      h("div", { class: "muted small" }, "Записи становятся «опубликованными», когда бот отчитался об успехе. Ошибка публикации освобождает записи сразу — опубликуйте их заново. «Итог неизвестен» держит записи, пока вы не проверите форум и не нажмёте «Ветки нет» или «Ветка есть». Отменить или удалить из Discord (только владелец) — откатом в «Журнале действий». Кто уже прочитал — не вернуть."));
  }
  load();
}
