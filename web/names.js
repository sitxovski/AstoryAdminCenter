// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Очередь имён» (шаг А6.11, часть «имена», 22.11.2026; domains/namereview.py, /api/names/*, операция names.mark).
// Новые и сменённые имена персонажей за период (создание CharEventCreate, смена в игре CharEvent Rename, смена панелью char.rename, сторож A13
// ac.other 55) с проверкой ТЕМ ЖЕ кодом, что смена имени char.rename (правила A13 1–7). Отметка «ок / сменить» пишет только AsdaAdmin
// (adm.NameReview); имя изменилось после отметки — отметка недействительна. «Сменить имя» — существующая операция char.rename (renameChar
// из app.js, право players.rename). Правка словаря запрещённых слов — набором данных А4 («Данные игры»).
// Имена и тексты журнала — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (acText из acjournal.js), без T() и без HTML.
"use strict";

const NM_STATE = { none: "не отмечено", ok: "ок", rename: "сменить", stale: "имя изменилось после отметки", gone: "персонажа нет" };
const NM_EVENT = { create: "создан", rename_game: "смена имени в игре", rename_panel: "смена имени панелью", a13: "сторож A13 сервера" };
const NM_CAT = { player: "игроки", service: "служебные ≤ 5000" };

function nmRule(it) {
  if (it.state === "gone") return h("span", { class: "muted" }, "—");
  if (it.rule === "0") return badge(T("проходит"), "");
  return h("span", null, badge(T("не проходит"), "bad"), " ", acText(it.why));
}
function nmMark(it) {
  const st = h("span", null, badge(T(NM_STATE[it.state] || it.state), it.state === "stale" ? "warn" : it.state === "rename" ? "bad" : ""));
  if (!it.mark) return st;
  return h("span", null, st, h("div", { class: "muted small" }, acText("№" + it.mark.id + " " + it.mark.by + " " + dt(it.mark.at) + (it.mark.note_text ? " · " + it.mark.note_text : "")),
    it.state === "stale" ? h("div", { class: "muted small" }, acText(T("отмечено для имени {0}", it.mark.name))) : null));
}
function nmEvents(it) {
  return h("div", { class: "small" }, it.events.map(e => h("div", null, h("span", null, NM_EVENT[e.kind] || e.kind), " ", acText(dt(e.at) + " " + (e.name || "") +
    (e.kind === "rename_panel" ? " ← " + (e.old || "?") + " · " + (e.by || "") : "") + (e.kind === "a13" ? " · " + T("правило {0}, область {1}", e.rule, e.scope) : "")))),
    it.events_n > it.events.length ? h("div", { class: "muted" }, acText(T("и ещё {0}", it.events_n - it.events.length))) : null);
}

async function nmMarkAsk(it, verdict, reload) {
  const note = h("input", { type: "text", maxlength: 200, class: "grow", placeholder: "пояснение (необязательно)" });
  if (!await confirmWin(T(verdict === "ok" ? "Отметить имя «ок»" : "Отметить имя «сменить»"), [h("div", { class: "pv mono" }, acText(it.name)),
    h("div", { class: "row" }, h("span", null, "Пояснение "), note),
    h("div", { class: "muted small" }, "Пишется только база панели. Имя не меняется: смена — кнопкой «Сменить имя». Если имя потом изменится, отметка станет недействительной.")])) return;
  const params = { uid: it.uid, idx: it.idx, verdict, note: note.value.trim() };
  let p;
  try { p = await op("names.mark", params, true); } catch (e) { return notify(e.message, "bad"); }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, acText(p.preview.text)), (p.preview.warnings || []).map(w => h("div", { class: "note" }, acText(w)))])) return;
  try { const x = await op("names.mark", Object.assign({ expect: p.preview.expect }, params), false); notify(x.message || T("готово")); reload(); }
  catch (e) { notify(e.message, "bad"); }
}

async function nmHistory(it) {
  let r;
  try { r = await api("/api/names/marks?" + acQs({ uid: it.uid, idx: it.idx })); } catch (e) { return notify(e.message, "bad"); }
  await confirmWin(T("Отметки имени {0}/{1}", it.uid, it.idx), [acTable([["№", m => String(m.id)], ["Имя", m => h("span", { class: "mono" }, acText(m.name))],
    ["Отметка", m => h("span", null, NM_STATE[m.verdict] || m.verdict)], ["Проверка тогда", m => m.rule_at_mark], ["Кто", m => m.by], ["Когда", m => dt(m.at)],
    ["Пояснение", m => m.note_text]], r.marks)]);
}

async function viewNames(my) {
  const out = h("div"), info = h("div", { class: "muted small" });
  const fromIn = h("input", { type: "date" }), toIn = h("input", { type: "date" });
  const allIn = h("input", { type: "checkbox" });
  const accIn = h("input", { type: "text", maxlength: 40, placeholder: "номер или логин", class: "mono" });
  const stSel = sel([["all", T("все")], ["bad", T("не проходят правила")], ["open", T("ждут отметки")], ["ok", T("отмечены «ок»")],
    ["rename", T("отмечены «сменить»")], ["stale", T("имя изменилось после отметки")]], "all");
  const svcSel = sel([["sep", T("служебные отдельно")], ["in", T("служебные вместе")]], "sep");
  const sizeSel = sel([[25, "25"], [50, "50"], [100, "100"], [200, "200"]], 50);
  const st = { page: 1 };
  async function load(page) {
    st.page = page || 1;
    put(info, acText(T("Загружаю…")));
    let r;
    try { r = await api("/api/names/queue?" + acQs({ from: acDay(fromIn.value), to: acDay(toIn.value), all: allIn.checked ? "1" : "", account: accIn.value.trim(),
      state: stSel.value, svc: svcSel.value, page: st.page, size: sizeSel.value })); }
    catch (e) { if (!stale(my)) { put(info, errbox(e)); put(out); } return; }
    if (stale(my)) return;
    const c = r.config || {};
    put(info, acText(T("Период {0} — {1} · в очереди {2} · страница {3} из {4}", r.from, r.to, fmt(r.total), r.page, r.pages)),
      h("div", null, acText(T("A13: Mode {0}, набор {1}, слова {2} ({3} ascii), LewdWordList {4}, операторы освобождены: {5}", c.Mode, c.Charset,
        fmt(!!c.CurseWords), r.words.curse_ascii, r.words.lewd, fmt(!!c.ExemptOperators)))));
    const rows = r.rows;
    const reload = () => load(st.page);
    put(out, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      (r.notes || []).map(x => h("div", { class: "muted small" }, acText(x))),
      h("h3", null, "Итоги"),
      acTable([["Категория", x => h("span", null, NM_CAT[x[0]] || x[0])], ["В очереди", x => fmt(x[1].items)], ["Не проходят правила", x => fmt(x[1].bad)],
        ["Ждут отметки", x => fmt(x[1].open)], ["«ок»", x => fmt(x[1].ok)], ["«сменить»", x => fmt(x[1].rename)], ["Имя изменилось", x => fmt(x[1].stale)],
        ["Персонажа нет", x => fmt(x[1].gone)]], Object.entries(r.totals)),
      h("h3", null, "Имена"),
      acTable([["Учётка", x => acAccount(x.uid, x.login)], ["Персонаж", x => x.exists ? acChar(x.uid, x.idx, x.name) : acText(x.uid + "/" + x.idx)],
        ["Имя", x => h("span", { class: "mono" }, acText(x.name), x.oper ? h("span", null, " ", badge(T("оператор"), "")) : null,
          x.cat === "service" ? h("span", null, " ", badge(T("служебная"), "")) : null, x.pos_differs ? h("span", null, " ", badge(T("в CharPos другое"), "warn")) : null)],
        ["Проверка", x => nmRule(x)], ["Отметка", x => nmMark(x)], ["События периода", x => nmEvents(x)],
        ["Действия", x => x.state === "gone" ? acText("—") : h("span", null,
          h("button", { type: "button", class: "small", onclick: () => nmMarkAsk(x, "ok", reload) }, "ок"),
          h("button", { type: "button", class: "small", onclick: () => nmMarkAsk(x, "rename", reload) }, "сменить"),
          r.can_rename ? h("button", { type: "button", class: "small", onclick: () => renameChar(x.uid, x.idx, x.name, reload) }, "Сменить имя") : null,
          h("button", { type: "button", class: "ghost small", onclick: () => nmHistory(x) }, "История"))]], rows),
      r.pages > 1 ? pager(r.page, r.pages, p => load(p)) : null,
      h("div", { class: "row" }, h("button", { type: "button", class: "ghost", onclick: () => { location.hash = r.dict_link; } }, "Словарь запрещённых слов — набором «Данных игры»")));
  }
  mount(shell("#/names", h("h1", null, "Очередь имён"), h("div", { class: "note" },
    acText(T("Новые и сменённые имена персонажей за период. Проверка — та же, что у смены имени: правила A13 (длина, символы, запрещённые слова CurseTable и LewdWordList, занятость). Отметка «ок / сменить» пишется только в базу панели; смена имени — отдельной операцией."))),
    h("div", { class: "card" }, h("div", { class: "row" }, h("span", null, "С "), fromIn, h("span", null, "по "), toIn, h("label", null, allIn, " все текущие имена"),
      h("span", null, "Учётка "), accIn),
      h("div", { class: "row" }, h("span", null, "Показать "), stSel, svcSel, h("span", null, "Строк "), sizeSel, h("button", { type: "button", onclick: () => load(1) }, "Показать")),
      h("div", { class: "muted small" }, "Без дат — последние 30 суток по часам сервера."), info, out)));
  load(1);
}
