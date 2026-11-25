// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Передачи и рынок» (шаг А6.4, 22.11.2026; domains/trade.py, /api/trade/*). ТОЛЬКО ЧТЕНИЕ игровых баз.
// Кто кому: обмен (Trade*: Userindex отдал → Tuserindex получил), лавка (PersonalStore*: вещь продавец Userindex → покупатель Tuserindex,
// золото — обратно), аукцион (ExchangeEvent «Purchase»: вещь продавец → покупатель, цена лота — продавцу), подарок gp7 (выданный, state C).
// Зеркала «…To» и «Sold out» не считаются (правило M3 AstoryServer/Tools/Anticheat/ac_metrics_db). Пары — правило M3 без изменений (≥ N записей или
// золото в одну сторону при нуле обратно), цепочки по времени, серийник с цепочкой (порог M4). Сеть (IP, MAC, связь пары) — только с правом
// players.view_net. Открытые лавки живут только в памяти GameServer — показать нельзя. Служебные ≤ 5000 — отдельно (галочка «в общем списке»).
// Значения из базы и журналов (имена, логины, серийники, строки Log_SelfStore) — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (acText,
// itemLine, acChar, acAccount), без T() и без HTML. Общие помощники — h(), T(), put(), mount(), shell(), sel(), badge(), errbox(), stale(),
// api(), pager(), dt(), fmt() (app.js) и acText(), acQs(), acDay(), acTable(), acAccount(), acChar() (acjournal.js).
"use strict";

const TR_CAT = { player: "игроки (> 5000)", service: "служебные ≤ 5000" };
const TR_GROUP = { trade: "обмен", store: "лавка", auction: "аукцион", gift: "подарок gp7" };
const TR_WHAT = { gold: "золото", item: "вещи" };
const TR_LINK = { mac_ip: "MAC+IP", mac: "MAC", ip_apart: "IP (не пересекались)", ip_net: "IP (общая сеть)" };
const TR_STATE = { "Purchase at the Exchange": "покупка", "Sold out at the Exchange": "продано (зеркало покупки)",
  "Registration Cancel": "снят продавцом", "Time Out-Delete": "персонажа нет — лот удалён по сроку без возврата",
  "Time Out-Return": "возвращён продавцу по сроку" };
const TR_TAG = { OPEN: "открыта", RETURN: "закрыта (вещи вернулись)", BUY: "покупка отправлена в базу", INSERT: "база подтвердила",
  error: "ошибка сервера" };
const TR_SRC = { TradeGoldFrom: "обмен: золото", TradeShellGoldFrom: "обмен ракушек: золото", TradeItemFrom: "обмен: стопка",
  TradeGear: "обмен: снаряжение", TradeFunctional: "обмен: расходник", TradeSowel: "обмен: совел", TradeNoStack: "обмен: вещь без стопки",
  PersonalStoreitemFrom: "лавка: стопка", PersonalStoreFunctional: "лавка: расходник", PersonalStoreGear: "лавка: снаряжение",
  PersonalStoreSowel: "лавка: совел", PersonalStoreNostack: "лавка: вещь без стопки", PersonalStoreGoldFrom: "лавка: оплата продавцу",
  ExchangeItem: "аукцион: вещь покупателю", ExchangeGold: "аукцион: цена продавцу", GP7GiftLog: "подарок gp7 (выдан)" };

const trCat = c => T(TR_CAT[c] || c);
const trGroups = g => acText(Object.entries(g || {}).map(([k, v]) => T(TR_GROUP[k] || k) + " " + v).join(", "));
const trUser = (r, u) => acAccount(u, (r.logins || {})[String(u)]);
const trSpan = (a, b) => acText(dt(a) + " — " + dt(b));
const trQty = x => x.what === "gold" ? h("span", null, T("золото"), " ", acText(fmt(x.qty)))
  : h("span", null, x.code !== null && x.code !== undefined ? itemLine(x.code, x.name, x.icon) : acText("—"), " × ", acText(fmt(x.qty)));

function trFlags(p) {
  return h("span", null, (p.flags || []).map(f => f.type === "deals" ? badge(T("{0} записей за период", fmt(f.value)), "warn")
    : f.type === "oneway" ? badge(T("золото {0}: №{1} → №{2}, обратно нет", fmt(f.value), f.from, f.to), "bad")
      : h("span", { class: "badge warn" }, acText(f.raw))));
}

async function viewTrade(my) {
  const out = h("div");
  mount(shell("#/trade", h("h1", null, "Передачи и рынок"), h("div", { class: "note" },
    acText(T("Кто кому по журналам JoyLog1: обмен — Userindex отдал, Tuserindex получил; лавка — вещь от продавца (Userindex) покупателю (Tuserindex), золото обратно; аукцион — вещь от продавца покупателю, цена лота продавцу; подарок gp7 — выданный. Зеркала «…To» не считаются (правило M3). Сеть — только с правом сетевых данных. Служебные учётки ≤ 5000 по умолчанию — отдельно."))), out));
  const svcIn = h("input", { type: "checkbox" });
  const svc = () => svcIn.checked ? "in" : "sep";
  const fFrom = h("input", { type: "date" }), fTo = h("input", { type: "date" });
  const fAcc = h("input", { type: "text", placeholder: "номер или логин", class: "mono", maxlength: 40 });
  const fGrp = sel([["", T("все виды")]].concat(Object.entries(TR_GROUP).map(([k, v]) => [k, T(v)])), "");
  const fPair = h("input", { type: "text", placeholder: "75204-75216", class: "mono", maxlength: 21 });
  const gBox = h("div"), tBox = h("div"), mBox = h("div"), sBox = h("div");
  const base = () => ({ from: acDay(fFrom.value), to: acDay(fTo.value), svc: svc() });

  // ---- граф «кто кому»
  async function loadGraph() {
    put(gBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/trade/graph?" + acQs(Object.assign(base(), { account: fAcc.value.trim(), group: fGrp.value }))); }
    catch (e) { if (!stale(my)) put(gBox, errbox(e)); return; }
    if (stale(my)) return;
    const pairCols = [["Пара", p => h("span", null, trUser(r, p.a), " ↔ ", trUser(r, p.b), p.self ? h("span", null, " ", badge(T("персонажи одной учётки"), "")) : null)],
      ["Кат.", p => trCat(p.cat)], ["Записей", p => fmt(p.deals)], ["Золото a→b", p => fmt(p.gold_ab)], ["Золото b→a", p => fmt(p.gold_ba)],
      ["Вещи a→b", p => fmt(p.items_ab)], ["Вещи b→a", p => fmt(p.items_ba)], ["Виды", p => trGroups(p.groups)], ["Флаги M3", p => trFlags(p)]]
      .concat(r.net_hidden ? [] : [["Связь по входам", p => p.link ? badge(T(TR_LINK[p.link] || p.link), "warn") : acText("—")]])
      .concat([["Первая — последняя (сервер)", p => trSpan(p.first, p.last)],
        ["", p => h("button", { type: "button", class: "ghost small", onclick: () => { fPair.value = p.a + "-" + p.b; loadTransfers(1); } }, "передачи")]]);
    const chainCols = [["Цепочка", c => h("span", null, c.nodes.map((u, i) => [i ? " → " : "", trUser(r, u)]))], ["Шагов", c => fmt(c.hops.length)],
      ["Золото", c => fmt(c.gold)], ["Вещей", c => fmt(c.items)], ["Виды", c => acText(c.hops.map(x => T(TR_GROUP[x.group] || x.group)).join(" · "))],
      ["С — по (сервер)", c => trSpan(c.hops[0].t, c.hops[c.hops.length - 1].t)]];
    const t = r.totals || { cats: { player: {}, service: {} }, total: {} };
    put(gBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      r.period ? h("div", { class: "muted small" }, acText(T("Период {0} — {1} (сутки по часам сервера).", r.period.from, r.period.to))) : null,
      r.thr ? h("div", { class: "muted small" }, acText(T("Правило M3 (ac_metrics_db, без изменений): пара ≥ {0} записей или золото ≥ {1} в одну сторону при нуле обратно; серийник — ≥ {2} передач.", fmt(r.thr.m3_pair_deals), fmt(r.thr.m3_gold_oneway), fmt(r.thr.m4_chain)))) : null,
      r.capped ? badge(T("у источника больше строк, чем читается за раз — сузьте период"), "warn") : null,
      acTable([["Учётки", x => x.grand ? h("b", null, T("общий итог")) : h("span", null, trCat(x.cat), x.out ? h("span", null, " ", badge(T("не в общем итоге"), "warn")) : null)],
        ["Пар", x => fmt(x.pairs)], ["Записей", x => fmt(x.deals)], ["С флагом M3", x => x.flagged ? badge(fmt(x.flagged), "bad") : acText("0")]],
      [Object.assign({ cat: "player" }, t.cats.player), Object.assign({ cat: "service", out: r.svc !== "in" }, t.cats.service), Object.assign({ grand: true }, t.total)]),
      h("h3", null, "Пары учёток"),
      acTable(pairCols, r.pairs || []),
      r.svc !== "in" ? [h("h3", null, "Пары со служебной стороной (не в общем итоге)"), acTable(pairCols, r.service_pairs || [])] : null,
      h("h3", null, "Цепочки передач"),
      h("div", { class: "muted small" }, acText(T("A → B, затем B → C не раньше и так далее (до 5 шагов); показаны только наибольшие."))),
      r.chains_capped ? badge(T("перебор цепочек остановлен на пределе — показаны найденные"), "warn") : null,
      acTable(chainCols, r.chains || []),
      r.svc !== "in" ? [h("h3", null, "Цепочки со служебной учёткой"), acTable(chainCols, r.service_chains || [])] : null,
      h("h3", null, "Серийники с цепочкой"),
      acTable([["Серийник", x => h("span", { class: "mono small" }, acText(x.serial))], ["Предмет", x => itemLine(x.code, x.name, null)], ["Передач", x => fmt(x.n)],
        ["Путь", x => h("span", null, x.path.map((e, i) => [i ? " → " : "", trUser(r, e.fu), " ▸ ", trUser(r, e.tu)]))]], r.serials || []),
      h("h3", null, "Один IP или MAC — разные учётки"),
      r.net_hidden ? h("div", { class: "note" }, acText(T("Сеть (IP, MAC, связь пары) — только с правом сетевых данных (players.view_net)."))) : null,
      r.net ? [h("div", { class: "muted small" }, acText(T("Входы LogInfo за период; адреса стойки, частные и виртуальные не учитываются; на адресе больше {0} учёток — «общая сеть».", r.net.crowd))),
        ["ip", "mac"].map(k => acTable([[k === "ip" ? "IP" : "MAC", g => h("span", { class: "mono small" }, acText(g.value), g.crowd ? h("span", null, " ", badge(T("общая сеть"), "")) : null)],
          ["Учёток", g => fmt(g.n)], ["Учётки (входов)", g => h("span", null, g.accounts.map((a, i) => [i ? ", " : "", trUser(r, a.uid), acText(" (" + a.sessions + ")")]))]],
        r.net[k] || []))] : null,
      h("h3", null, "Источники за период"),
      acTable([["Источник", x => T(TR_SRC[x.key] || x.key)], ["Таблица", x => h("span", { class: "mono small" }, acText(x.table))], ["Вид", x => T(TR_GROUP[x.group] || x.group)],
        ["Что", x => T(TR_WHAT[x.what] || x.what)], ["Писатель", x => h("span", { class: "small" }, acText(x.proc))],
        ["Строк", x => x.rows === null ? badge(T("не прочитан"), "bad") : h("span", null, acText(fmt(x.rows)), x.capped ? h("span", null, " ", badge(T("обрезано"), "warn")) : null)]], r.sources || []),
      h("h3", null, "Зеркала (не считаются)"),
      acTable([["Таблица", x => h("span", { class: "mono small" }, acText(x.table + (x.sold ? " · Sold out" : "")))], ["Пара к", x => h("span", { class: "mono small" }, acText(x.of))],
        ["Строк", x => x.rows === null ? badge(T("не прочитан"), "bad") : fmt(x.rows)]], r.mirrors || []),
      r.box && r.box.postbox ? h("div", { class: "muted small" }, acText(T("Ящик ItemPostBox сейчас (отправитель не хранится): {0}; из них заказов подарков gp7 — {1}; отложенные Joy1.gifts — {2} строк (писателя в процедурах Joy1 нет).",
        r.box.postbox.map(x => "iType " + x.itype + " — " + x.rows).join(", ") || "—", acNum(r.box.gift_orders), acNum(r.box.gifts_rows)))) : null,
      r.gifts ? h("div", { class: "muted small" }, acText(T("Подарки gp7 за период: {0}; тестовых {1}; получатель не найден {2}. Передачей считается только выданный (C).",
        Object.entries(r.gifts.states).map(([k, v]) => k + " " + v).join(", ") || "—", r.gifts.test, r.gifts.unresolved))) : null);
  }

  // ---- передачи построчно
  async function loadTransfers(page) {
    put(tBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/trade/transfers?" + acQs(Object.assign(base(), { account: fAcc.value.trim(), group: fGrp.value, pair: fPair.value.trim(), page: page || 1 }))); }
    catch (e) { if (!stale(my)) put(tBox, errbox(e)); return; }
    if (stale(my)) return;
    const trCols = [["Когда (сервер)", x => dt(x.t)], ["Вид", x => T(TR_GROUP[x.group] || x.group)], ["Источник", x => T(TR_SRC[x.src] || x.src)],
      ["Отдал", x => h("span", null, acChar(x.fu, x.fi, x.fn), " ", trUser(r, x.fu))], ["Получил", x => h("span", null, acChar(x.tu, x.ti, x.tn), " ", trUser(r, x.tu))],
      ["Что", x => trQty(x)], ["Серийник", x => h("span", { class: "mono small" }, acText(x.serial))],
      ["Кат.", x => h("span", null, trCat(x.cat), x.test ? h("span", null, " ", badge(T("тест"), "")) : null)]];
    put(tBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      h("div", { class: "muted small" }, acText(T("Передач {0} за {1} — {2}.", fmt(r.total), r.period.from, r.period.to))),
      acTable(trCols, r.rows || []),
      r.pages > 1 ? pager(r.page, r.pages, p => loadTransfers(p)) : null,
      r.svc !== "in" ? [h("h3", null, "Передачи со служебной стороной (не в общем списке)"),
        h("div", { class: "muted small" }, acText(T("Всего {0}, показаны последние {1}.", fmt(r.service_total), fmt((r.service_rows || []).length)))),
        acTable(trCols, r.service_rows || [])] : null);
  }

  // ---- рынок
  async function loadMarket(page) {
    put(mBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/trade/market?" + acQs(Object.assign(base(), { page: page || 1 }))); }
    catch (e) { if (!stale(my)) put(mBox, errbox(e)); return; }
    if (stale(my)) return;
    const tx = r.tax;
    const lotCols = [["Предмет", x => itemLine(x.code, x.name, x.icon)], ["Штук", x => x.nostack ? h("span", null, acText("1"), " ", badge(T("без стопки"), "")) : fmt(x.amount)], ["Цена лота", x => fmt(x.price)],
      ["За штуку", x => x.unit === null ? acText("—") : acText(fmt(Math.round(x.unit * 100) / 100))], ["Продавец", x => h("span", null, acChar(x.uid, x.slot, x.char), " ", acAccount(x.uid, null))],
      ["Кат.", x => trCat(x.cat)], ["State", x => acText(x.state)], ["Выставлен (Gaindate)", x => dt(x.gaindate)], ["Срок (Fdate)", x => dt(x.fdate)],
      ["Пометки", x => h("span", null, x.expired ? badge(T("срок прошёл"), "warn") : null, x.overdue ? h("span", null, " ", badge(T("срок реле прошёл — лот ждёт рестарта реле или отмены владельцем"), "bad")) : null)]];
    const histCols = [["Когда (сервер)", x => dt(x.t)], ["Событие", x => x.kind === "regi" ? h("span", null, T("регистрация"), " ", h("span", { class: "mono small" }, acText(x.table)))
      : h("span", null, TR_STATE[x.state] ? T(TR_STATE[x.state]) : acText(x.state), x.deleted ? h("span", null, " ", badge(T("вещь пропала"), "bad")) : null)],
      ["Учётка", x => h("span", null, acChar(x.uid, x.slot, x.char), " ", acAccount(x.uid, x.login))], ["Другая сторона", x => x.ou !== null && x.ou !== x.uid ? h("span", null, acText(x.oname), " ", acAccount(x.ou, null)) : acText("—")],
      ["Предмет", x => x.code !== null ? itemLine(x.code, x.name, x.icon) : acText("—")], ["Штук", x => fmt(x.qty)], ["Цена лота", x => x.price === null ? acText("—") : fmt(x.price)],
      ["Кат.", x => x.cat ? trCat(x.cat) : acText("—")]];
    put(mBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      h("h3", null, "Живые лоты (Exitem)"),
      h("div", { class: "muted small" }, acText(T("Лотов сейчас {0}. Цена лота — Sprice, за штуку — Sprice / Amount; срок снятия реле — 14 суток после регистрации.", fmt(r.lots_total)))),
      r.lots_capped ? badge(T("показаны первые лоты по сроку"), "warn") : null,
      acTable(lotCols, r.lots || []),
      r.svc !== "in" ? [h("h3", null, "Лоты служебных учёток (не в ценах и итогах)"), acTable(lotCols, r.service_lots || [])] : null,
      h("h3", null, "Цены по предметам"),
      h("div", { class: "muted small" }, acText(T("Выставлено — живые лоты сейчас, продано — покупки за период {0} — {1} (за штуку).", r.period.from, r.period.to))),
      acTable([["Предмет", x => itemLine(x.code, x.name, x.icon)], ["Лотов", x => fmt(x.listed)], ["Штук выставлено", x => fmt(x.listed_qty)],
        ["Выставлено: мин — макс", x => x.lmin === null ? acText("—") : acText(fmt(Math.round(x.lmin)) + " — " + fmt(Math.round(x.lmax)))],
        ["Продаж", x => fmt(x.sold)], ["Штук продано", x => fmt(x.sold_qty)], ["Продано: средняя", x => x.savg === null ? acText("—") : acText(fmt(Math.round(x.savg)))]], r.prices || []),
      h("h3", null, "Налог аукциона"),
      tx ? acTable([["Учётки", x => x.grand ? h("b", null, T("общий итог")) : h("span", null, trCat(x.cat), x.out ? h("span", null, " ", badge(T("не в общем итоге"), "warn")) : null)],
        ["Сбор за выставление (MoneyExchangeFee)", x => acText(fmt(x.fee) + " / " + fmt(x.fee_n))], ["Сбор с продажи", x => acText(fmt(x.commission) + " / " + fmt(x.commission_n))],
        ["Возврат сбора", x => acText(fmt(x.refund) + " / " + fmt(x.refund_n))], ["Итого", x => h("b", null, acText(fmt(x.net)))]],
      [Object.assign({ cat: "player" }, tx.cats.player), Object.assign({ cat: "service", out: r.svc !== "in" }, tx.cats.service), Object.assign({ grand: true }, tx.total)]) : null,
      tx ? h("div", { class: "muted small" }, acText(T("Сумма / строк. Сбор с продажи и возврат — ItemEvent (Code 20551) «Commission at the Exchange» и «Commision Refund on a registration»."))) : null,
      h("h3", null, "История аукциона"),
      h("div", { class: "muted small" }, acText(T("Строк {0}: {1}.", fmt(r.hist_total), Object.entries(r.hist_counts || {}).map(([k, v]) => (k === "regi" ? T("регистрации") : (TR_STATE[k] ? T(TR_STATE[k]) : k)) + " " + v).join(", ") || "—"))),
      r.pages_capped ? badge(T("история листается до 10 000 строк — сузьте период"), "warn") : null,
      acTable(histCols, r.history || []),
      r.pages > 1 ? pager(r.page, r.pages, p => loadMarket(p)) : null,
      r.svc !== "in" ? [h("h3", null, "История со служебной стороной (не в общем списке)"),
        h("div", { class: "muted small" }, acText(T("Всего {0}, показаны последние {1}.", fmt(r.service_hist_total), fmt((r.service_history || []).length)))),
        acTable(histCols, r.service_history || [])] : null);
  }

  // ---- лавки
  const sLogs = h("input", { type: "checkbox", checked: true });
  async function loadStores() {
    put(sBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/trade/stores?" + acQs(Object.assign(base(), { logs: sLogs.checked ? "1" : "0" }))); }
    catch (e) { if (!stale(my)) put(sBox, errbox(e)); return; }
    if (stale(my)) return;
    const saleCols = [["Когда (сервер)", s => dt(s.t)], ["Продавец", s => h("span", null, acChar(s.su, s.si, s.sn), " ", acAccount(s.su, null))],
      ["Покупатель", s => h("span", null, acChar(s.bu, s.bi, s.bn), " ", acAccount(s.bu, null))], ["Золото", s => fmt(s.gold)],
      ["Вещи", s => h("span", null, s.items.map((i, n) => [n ? ", " : "", itemLine(i.code, i.name, i.icon), acText(" × " + i.qty)]))], ["Кат.", s => trCat(s.cat)]];
    put(sBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      h("div", { class: "note" }, acText(r.open_note)),
      (r.notes || []).map(x => h("div", { class: "note" }, acText(x))),
      acTable([["Учётки", x => x.grand ? h("b", null, T("общий итог")) : h("span", null, trCat(x.cat), x.out ? h("span", null, " ", badge(T("не в общем итоге"), "warn")) : null)],
        ["Сделок", x => fmt(x.sales)], ["Золото", x => fmt(x.gold)], ["Вещей", x => fmt(x.items)]],
      [Object.assign({ cat: "player" }, r.cats.player), Object.assign({ cat: "service", out: r.svc !== "in" }, r.cats.service), Object.assign({ grand: true }, r.total)]),
      h("h3", null, "По дням: база и журнал"),
      acTable([["День", d => d.day], ["Сделок в базе (все)", d => fmt(d.sales)], ["Золото (итог)", d => fmt(d.total.gold)],
        ["Покупок по журналу", d => d.log_unread ? badge(T("журнал за этот день не прочитан"), "warn") : (d.log_buy === null ? acText("—") : fmt(d.log_buy))],
        ["Подтверждено базой", d => d.log_ok === null ? acText("—") : fmt(d.log_ok)],
        ["", d => d.log_ok !== null && d.log_ok !== d.sales ? badge(T("расходится"), "bad") : null]], r.days || []),
      h("h3", null, "Сделки (PersonalStore*)"),
      acTable(saleCols, r.sales || []),
      r.svc !== "in" ? [h("h3", null, "Сделки со служебной стороной (не в общем итоге)"), acTable(saleCols, r.service_sales || [])] : null,
      r.log ? [h("h3", null, "Журнал Log_SelfStore"),
        h("div", { class: "muted small" }, acText(T("Файлов {0}, событий {1} (показаны последние).", fmt(r.log.files.length), fmt(r.log.events_total)))),
        acTable([["Когда", e => dt(e.t)], ["Событие", e => TR_TAG[e.tag] ? T(TR_TAG[e.tag]) : acText(e.tag)], ["Хозяин лавки", e => e.host_uid !== null && e.host_uid !== undefined ? h("span", null, acText(e.host_name), " ", acAccount(e.host_uid, null)) : acText("—")],
          ["Покупатель", e => e.buyer_uid !== null && e.buyer_uid !== undefined ? h("span", null, acText(e.buyer_name), " ", acAccount(e.buyer_uid, null)) : acText("—")],
          ["Золото", e => e.gold === null || e.gold === undefined ? acText("—") : fmt(e.gold)],
          ["Вещи / текст", e => e.tag === "error" ? h("span", { class: "mono small" }, acText(e.msg)) : h("span", null, (e.items || []).map((i, n) => [n ? ", " : "", acText(i.code + " × " + acNum(i.amount) + (i.gold !== null && i.gold !== undefined ? " @" + i.gold : ""))]))],
          ["Копия · файл", e => h("span", { class: "mono small" }, acText(e.proc + " · " + e.file))]], r.log.events || [])] : null);
  }

  svcIn.addEventListener("change", () => { loadGraph(); loadTransfers(1); loadMarket(1); loadStores(); });
  put(out,
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Кто кому"), h("span", null, "С "), fFrom, h("span", null, "по "), fTo,
      h("span", null, "Учётка "), fAcc, h("span", null, "Вид "), fGrp, h("label", null, svcIn, " служебные ≤ 5000 в общем списке"),
      h("button", { type: "button", onclick: () => { loadGraph(); loadTransfers(1); } }, "Показать")), gBox),
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Передачи построчно"), h("span", null, "Пара "), fPair,
      h("button", { type: "button", onclick: () => loadTransfers(1) }, "Показать")), tBox),
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Рынок: аукцион"), h("button", { type: "button", onclick: () => loadMarket(1) }, "Обновить")), mBox),
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Личные лавки"), h("label", null, sLogs, " журнал Log_SelfStore"),
      h("button", { type: "button", onclick: () => loadStores() }, "Показать")), sBox));
  loadGraph();
  loadTransfers(1);
  loadMarket(1);
  loadStores();
}
