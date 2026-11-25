// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Экономика: золото» (шаг А6.3, 21.11.2026; domains/econ.py, /api/econ/*). Чтение игровых баз; кнопка «Снять снимок»
// (операция econ.snapshot) пишет только базу панели AsdaAdmin.
// Золото — Joy1.Item.Code = 20551 (склада золота нет). Журналы JoyLog1: Amount = было, Ramount = стало, дельта = Ramount − Amount (реверс
// процедур Joy1, отчёт impl_a6_econ §А6.3); у «…To» обмена и лавки баланс — Tuserindex. ★ ревизия 52: учтены и перенос опций (−Gm),
// создание персонажа (+1), ItemEvent 10551 и правки золота самой панелью (adm.audit). «Снимок − журналы» = неучтённое: известные пути
// без журнала — подбор и дроп с монстров, выдача GM-командой, награда ограниченных заданий, восстановление и копия персонажа панелью и пр. Служебные учётки ≤ 5000 по умолчанию — отдельной строкой (переключатель «в общем итоге»).
// Значения из базы (имена, логины, State журналов, названия предметов) — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (acText, itemLine),
// без перевода T() и без HTML. Общие помощники — h(), T(), put(), mount(), shell(), sel(), badge(), errbox(), stale(), api(), op(), dt(),
// fmt(), can(), notify(), confirmWin() (app.js) и acText(), acQs(), acDay(), acTable(), acAccount(), acChar() (acjournal.js).
"use strict";

const EC_CAT = { player: "игроки (> 5000)", service: "служебные ≤ 5000" };
const EC_SRC = {
  MoneyBuy: "покупка у NPC", MoneySell: "продажа NPC", MoneyCraft: "ремесло", MoneyExchangeBuy: "биржа: покупка",
  MoneyExchangeFee: "биржа: сбор за выставление", MoneyReward: "награда (эпизод)", MoneyTelePort: "телепорт", MoneyUse: "клан: создание и рост",
  MoneyWasteBasket: "корзина (выброс предметов)", MoneyCampReward: "награда лагеря", TradeGoldFrom: "обмен: отдал", TradeGoldTo: "обмен: получил",
  TradeShellGoldFrom: "обмен ракушек: отдал", TradeShellGoldTo: "обмен ракушек: получил", PersonalStoreGoldFrom: "лавка: продавец получил",
  PersonalStoreGoldTo: "лавка: покупатель заплатил", CampShopUseGold: "лавка лагеря", TradeItemFrom: "обмен всей кучкой: отдал",
  TradeitemTo: "обмен: получил без своей кучки", ItemEvent: "события предметов (ItemEvent)", AdminitemLog: "оператор (AdminitemLog)",
  ItemRefine: "алхимия (ItemRefine)", TransferOption: "перенос опций (TransferOption.Gm)", OpGameMoneyAdd: "выдача события клана (ItemEvent 10551)",
  CharEventCreate: "создание персонажа (+1)", panel: "правки панели (adm.audit)"
};
const EC_UNLOGGED = { pick: "подбор золота и дроп с монстров", gm: "выдача золота GM-командой", limitation: "награда ограниченных заданий",
  csused: "списание при покупке за использованное", panel_char: "восстановление и копия персонажа панелью", delete: "удаление персонажа" };
const EC_PANEL = { "char.restore": "восстановлен панелью — сумма не записана", "char.copy": "копия панели — сумма не записана",
  "char.copy.undo": "копия удалена панелью — сумма не записана" };
const EC_WHY = { nowriter: "писателя нет ни в одной базе — знак не снят, не считается", dup: "дубль MoneyReward (та же процедура, Amount = дельта) — не считается",
  off: "строка журнала в процедуре закомментирована (золото с моба и подбор) — не считается" };

const ecSgn = v => (v > 0 ? "+" : "") + fmt(v);
const ecCat = c => T(EC_CAT[c] || c);
const ecSrc = k => T(EC_SRC[k] || k);
const EC_FLOW = [["Строк", x => fmt(x.n)], ["Поступило", x => fmt(x.inflow)], ["Списано", x => fmt(x.outflow)], ["Итог", x => ecSgn(x.delta)]];

// строки категорий с пометкой «не в общем итоге» + общий итог
function ecCatRows(cats, total, svc, cols) {
  const rows = ["player", "service"].map(c => Object.assign({ cat: c, out: c === "service" && svc !== "in" }, cats[c]));
  rows.push(Object.assign({ grand: true }, total));
  return acTable([["Учётки", r => r.grand ? h("b", null, T("общий итог")) : h("span", null, ecCat(r.cat), r.out ? h("span", null, " ", badge(T("не в общем итоге"), "warn")) : null)]].concat(cols), rows);
}

function ecPair(p) {
  return acTable([["Учётки", r => r.grand ? h("b", null, T("общий итог")) : ecCat(r.cat)], ["Изменение снимков", r => ecSgn(r.snap)], ["Журналы", r => ecSgn(r.journal)],
    ["Неучтённое", r => h("b", null, ecSgn(r.unaccounted))]], [Object.assign({ cat: "player" }, p.cats.player), Object.assign({ cat: "service" }, p.cats.service),
    Object.assign({ grand: true }, p.total)]);
}

async function viewEcon(my) {
  const out = h("div");
  mount(shell("#/econ", h("h1", null, "Экономика: золото"), h("div", { class: "note" },
    acText(T("Золото персонажа — Joy1.Item, код 20551 (склада золота нет). Потоки — по журналам JoyLog1: было → стало, знак снят с процедур Joy1. Без журнала золото меняют подбор и дроп с монстров, выдача GM-командой, награда ограниченных заданий, восстановление и копия персонажа панелью и др., поэтому «снимок − журналы» = неучтённое. Служебные учётки ≤ 5000 по умолчанию — отдельной строкой, не в общем итоге."))), out));
  const svcIn = h("input", { type: "checkbox" });
  const svc = () => svcIn.checked ? "in" : "sep";
  const sumBox = h("div"), flowBox = h("div"), richBox = h("div"), rareBox = h("div"), unBox = h("div");

  // ---- сводка
  async function loadSummary() {
    put(sumBox, h("div", { class: "muted" }, "Загружаю…"));
    let s;
    try { s = await api("/api/econ/summary?" + acQs({ svc: svc() })); } catch (e) { if (!stale(my)) put(sumBox, errbox(e)); return; }
    if (stale(my)) return;
    put(sumBox, (s.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      h("h2", null, "Золото на руках сейчас"),
      s.held ? ecCatRows(s.held.cats, s.held.total, s.svc, [["Персонажей", r => fmt(r.chars)], ["Золото", r => fmt(r.sum)]]) : null,
      s.held ? h("div", { class: "muted small" }, acText(T("Прочитано {0} (часы сервера).", dt(s.held.at)))) : null,
      h("h2", null, "Снимки и неучтённое"),
      h("div", { class: "muted small" }, acText(s.last ? T("Снимков {0}, последний №{1} — {2} (сервер), всего {3}.", fmt(s.snapshots), s.last.id, dt(s.last.taken_local), fmt(s.last.total))
        : T("Снимков пока нет: служба снимает его сама раз в сутки (00:05 по часам сервера), можно снять кнопкой ниже."))),
      s.pair ? [h("div", { class: "muted small" }, acText(T("Между снимками №{0} и №{1}:", s.pair.from_id, s.pair.to_id))), ecPair(s.pair)] : null,
      h("h2", null, "Источники золота (журналы JoyLog1, всё время)"),
      acTable([["Источник", x => ecSrc(x.key)], ["Таблица", x => h("span", { class: "mono small" }, acText(x.table + (x.gold_only ? " (Code 20551)" : "")))],
        ["Знак", x => acText(x.sign)], ["Владелец строки", x => h("span", { class: "mono small" }, acText(x.owner))], ["Писатель (Joy1)", x => h("span", { class: "small" }, acText(x.proc))],
        ["Строк", x => x.read ? fmt(x.total.n) : badge(T("не прочитан"), "bad")], ["Итог", x => x.read ? ecSgn(x.total.delta) : acText("—")],
        ["Против знака", x => x.read && x.against ? badge(fmt(x.against), "bad") : acText("—")],
        ["Первая — последняя (сервер)", x => x.read && x.first ? acText(dt(x.first) + " — " + dt(x.last)) : acText("—")]], s.sources || []),
      h("div", { class: "muted small" }, acText(T("Правки панели без суммы (восстановление, копия персонажа): {0}.", fmt((s.sources || []).filter(x => x.key === "panel").map(x => x.unknown || 0)[0] || 0)))),
      h("h2", null, "Известные пути без журнала (уходят в неучтённое)"),
      acTable([["Путь", x => T(EC_UNLOGGED[x.key] || x.key)], ["Где", x => h("span", { class: "mono small" }, acText(x.proc))]], s.unlogged || []),
      h("h2", null, "Не считаются"),
      acTable([["Таблица", x => h("span", { class: "mono small" }, acText(x.table))], ["Причина", x => T(EC_WHY[x.why] || x.why)], ["Писатель", x => acText(x.proc)],
        ["Строк", x => x.rows === null ? badge(T("не прочитан"), "bad") : (x.rows && x.why === "nowriter" ? badge(fmt(x.rows), "warn") : fmt(x.rows))]], s.skipped || []),
      (s.other || []).length ? [h("div", { class: "note" }, acText(T("Таблицы вне каталога со строками золота (Code 20551): знак не снят — не считаются, нужен реверс писателя."))),
        acTable([["Таблица", x => h("span", { class: "mono small" }, acText(x.table))], ["Строк", x => fmt(x.rows)]], s.other)] : null);
  }

  // ---- потоки
  const fFrom = h("input", { type: "date" }), fTo = h("input", { type: "date" });
  const fSrc = sel([["", T("все источники")]].concat(Object.entries(EC_SRC).map(([k, v]) => [k, T(v)])), "");
  async function loadFlows() {
    put(flowBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/econ/flows?" + acQs({ from: acDay(fFrom.value), to: acDay(fTo.value), source: fSrc.value, svc: svc() })); }
    catch (e) { if (!stale(my)) put(flowBox, errbox(e)); return; }
    if (stale(my)) return;
    const srcs = (r.sources || []).filter(x => x.read && x.total.n);
    put(flowBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      r.period ? h("div", { class: "muted small" }, acText(T("Период {0} — {1} (сутки по часам сервера).", r.period.from, r.period.to))) : null,
      ecCatRows(r.cats, r.total, r.svc, EC_FLOW),
      h("h3", null, "По дням"),
      acTable([["День", d => d.day]].concat(EC_FLOW.map(([t, f]) => [t, d => f(d.total)])), r.days || []),
      h("h3", null, "По источникам"),
      acTable([["Источник", x => ecSrc(x.key)], ["Игроки: итог", x => ecSgn(x.cats.player.delta)], ["Служебные: итог", x => ecSgn(x.cats.service.delta)]]
        .concat(EC_FLOW.map(([t, f]) => [t, x => f(x.total)])).concat([["Против знака", x => x.against ? badge(fmt(x.against), "bad") : acText("—")]]), srcs),
      srcs.filter(x => x.subs && x.subs.length).map(x => [h("h3", null, h("span", null, ecSrc(x.key), " — ", T("по State"))),
        acTable([["State", y => acText(y.sub)]].concat(EC_FLOW.map(([t, f]) => [t, y => f(y.total)])), x.subs)]),
      (r.skipped || []).some(x => x.rows) ? h("div", { class: "note" }, acText(T("За период есть строки в несчитающихся таблицах: {0}.",
        r.skipped.filter(x => x.rows).map(x => x.table + " " + x.rows).join(", ")))) : null);
  }

  // ---- богатейшие
  const rN = h("input", { type: "number", min: 1, max: 200, value: 50, class: "mono" });
  async function loadRich() {
    put(richBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/econ/richest?" + acQs({ n: rN.value, svc: svc() })); } catch (e) { if (!stale(my)) put(richBox, errbox(e)); return; }
    if (stale(my)) return;
    const cols = [["Персонаж", x => acChar(x.uid, x.idx, x.char)], ["Учётка", x => acAccount(x.uid, x.login)], ["Ур.", x => fmt(x.lvl)], ["Кат.", x => ecCat(x.cat)], ["Золото", x => fmt(x.gold)]];
    put(richBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      r.cats ? ecCatRows(r.cats, r.total, r.svc, [["Персонажей с золотом", x => fmt(x.chars)], ["Золото", x => fmt(x.sum)], ["Наибольшее", x => fmt(x.max)]]) : null,
      r.svc === "in" ? acTable(cols, r.all) : [h("h3", null, "Игроки"), acTable(cols, r.players), h("h3", null, "Служебные ≤ 5000"), acTable(cols, r.service)]);
  }

  // ---- редкое на руках
  const kN = h("input", { type: "number", min: 1, max: 200, value: 50, class: "mono" });
  async function loadRare() {
    put(rareBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/econ/rare?" + acQs({ n: kN.value, svc: svc() })); } catch (e) { if (!stale(my)) put(rareBox, errbox(e)); return; }
    if (stale(my)) return;
    put(rareBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      h("div", { class: "muted small" }, acText(T("Таблица редкого {0} (P11/P59): кодов {1}, сейчас на руках {2}.", r.table || "—", fmt(r.rare_codes), fmt(r.present)))),
      h("div", { class: "muted small" }, acText(T("«Записей» — Item, Exitem, ItemPostBox, gifts по переключателю служебных; «Всего (held_counts)» — все учётки, а ещё снятое панелью (ItemTaken) и висящие подарки gp7, поэтому может быть больше."))),
      r.capped ? badge(T("показаны первые по числу записей — увеличьте «строк»"), "warn") : null,
      r.p59 && !r.p59.rows ? h("div", { class: "muted small" }, acText(T("Событий P59 за {0} суток нет (журнал редкого дропа пуст или P59 не выложен).", r.p59.days))) : null,
      acTable([["Предмет", x => itemLine(x.code, x.name, x.icon)], ["Записей", x => fmt(x.total.rows)], ["Штук (Amount)", x => fmt(x.total.amount)],
        ["Персонажей", x => fmt(x.total.chars)], ["У служебных", x => fmt(x.cats.service.rows)],
        ["Где", x => acText(Object.entries(Object.assign({}, x.cats.player.where)).concat(Object.entries(x.cats.service.where)).map(([k, v]) => k + " " + v).join(", "))],
        ["Всего (held_counts)", x => x.held ? fmt(x.held.rows) : acText("—")],
        ["P59: выпало / подобрано", x => x.p59 ? acText(x.p59.drop + " / " + x.p59.pickup) : acText("—")]], r.rows || []));
  }

  // ---- снимки и неучтённое
  async function loadUn(id) {
    put(unBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/econ/unaccounted?" + acQs({ id: id || "", svc: svc() })); } catch (e) { if (!stale(my)) put(unBox, errbox(e)); return; }
    if (stale(my)) return;
    put(unBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      (r.pairs || []).length ? null : h("div", { class: "muted" }, acText(T("Нужно два снимка: неучтённое считается между соседними снимками."))),
      acTable([["Снимки", p => acText("№" + p.from_id + " → №" + p.to_id)], ["С (сервер)", p => dt(p.from)], ["По (сервер)", p => dt(p.to)],
        ["Изменение снимков", p => ecSgn(p.total.snap)], ["Журналы", p => ecSgn(p.total.journal)], ["Неучтённое", p => h("b", null, ecSgn(p.total.unaccounted))],
        ["", p => h("button", { type: "button", class: "ghost small", onclick: () => loadUn(p.to_id) }, p.to_id === r.detail_of ? "по персонажам ✓" : "по персонажам")]], r.pairs || []),
      r.detail_of ? h("h3", null, h("span", null, T("Неучтённое по персонажам до снимка №{0}", r.detail_of))) : null,
      r.detail_of ? acTable([["Персонаж", x => acChar(x.uid, x.idx, x.char)], ["Учётка", x => acAccount(x.uid, x.login)], ["Кат.", x => ecCat(x.cat)],
        ["Было", x => fmt(x.before)], ["Стало", x => fmt(x.after)], ["Изменение", x => ecSgn(x.snap)], ["Журналы", x => ecSgn(x.journal)],
        ["Неучтённое", x => h("span", null, h("b", null, ecSgn(x.unaccounted)), x.gone ? h("span", null, " ", badge(T("персонажа нет в Charinfo"), "warn")) : null,
          (x.panel || []).map(a => h("span", null, " ", badge(T(EC_PANEL[a] || a), "warn"))))]], r.chars || []) : null,
      h("h3", null, "Снимки"),
      acTable([["№", s => s.id], ["Снят (сервер)", s => dt(s.taken_local)], ["Всего", s => fmt(s.total)], ["Игроки", s => fmt(s.players)], ["Служебные", s => fmt(s.service)],
        ["Персонажей", s => fmt(s.chars_players + s.chars_service)], ["Кто", s => acText(s.by)], ["Путь", s => acText(s.via)]], r.snapshots || []));
  }

  async function snapNow() {
    let p;
    try { p = await op("econ.snapshot", {}, true); } catch (e) { return notify(e.message, true); }
    if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)), (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w)))])) return;
    try { const res = await op("econ.snapshot", {}, false); notify(T(res.message || "готово")); loadSummary(); loadUn(); } catch (e) { notify(e.message, true); }
  }

  svcIn.addEventListener("change", () => { loadSummary(); loadFlows(); loadRich(); loadRare(); loadUn(); });
  put(out,
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Сводка"), h("label", null, svcIn, " служебные ≤ 5000 в общем итоге"),
      h("button", { type: "button", onclick: () => loadSummary() }, "Обновить"),
      can("econ.snapshot") ? h("button", { type: "button", class: "gold", onclick: () => snapNow() }, "Снять снимок сейчас") : null), sumBox),
    h("div", { class: "card" }, h("h2", null, "Потоки по дням и источникам"),
      h("div", { class: "row" }, h("span", null, "С "), fFrom, h("span", null, "по "), fTo, h("span", null, "Источник "), fSrc,
        h("button", { type: "button", onclick: () => loadFlows() }, "Показать")), flowBox),
    h("div", { class: "card" }, h("h2", null, "Снимок − журналы = неучтённое"), unBox),
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Богатейшие"), h("span", null, "Строк "), rN,
      h("button", { type: "button", onclick: () => loadRich() }, "Показать")), richBox),
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Редкое на руках"), h("span", null, "Строк "), kN,
      h("button", { type: "button", onclick: () => loadRare() }, "Показать")), rareBox));
  loadSummary();
  loadFlows();
  loadUn();
  loadRich();
  loadRare();
}
