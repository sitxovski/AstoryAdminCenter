// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Деньги» (шаг А6.2, 21.11.2026; domains/money.py, /api/money/*). Чтение; единственная запись — корректировка баланса gp7 (А6.9).
// Монетизация gp7: итоги покупок по категориям учёток (служебные ≤ 5000 — отдельной строкой, переключатель «в общем итоге»), висящие
// подарки (сверка как gift_reconcile.py — подсказка, ничего не применяется), журнал покупок всех учёток, подарки, продажи по дням и
// позициям (рядом сток AsdaStoryOp с пометкой «сток» — зеркало заказов gp7, в итог не входит), учётка сайта ↔ игровая.
// Значения из базы (логины, имена, названия позиций, подсказки сверки) — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (acText из
// acjournal.js, itemLine из app.js), без перевода T() и без HTML. Общие помощники — h(), T(), put(), mount(), shell(), sel(), badge(),
// errbox(), stale(), api(), pager(), dt(), fmt() (app.js) и acText(), acQs(), acDay(), acTable(), acAccount() (acjournal.js).
"use strict";

const MN_KIND = { buy: "покупка", gift: "подарок", refund: "возврат подарка", fail: "отказ: не хватило баланса" };
const MN_CAT = { player: "игроки (> 5000)", service: "служебные ≤ 5000", nolink: "сайт без игровой учётки" };
const MN_STATE = { H: "заморожен, не выдан (H)", C: "выдан (C)", R: "деньги возвращены (R)" };
const MN_STOCK = { CashUse: "сток CashUse (сумма заказа)", SalePremium: "сток SalePremium", SaleFunctional: "сток SaleFunctional", SaleHair: "сток SaleHair" };

const mnCat = c => T(MN_CAT[c] || c);
// ★ ревизия 51 Н-3, М-4: деньги строки итогов — списано, возвращено (строки возврата и тестовые подарки R), итого = разность
const MN_MONEY_COLS = [["Строк", r => fmt(r.n)], ["Списано", r => fmt(r.gross)], ["Возвращено", r => fmt(r.refunded)], ["Итого", r => fmt(r.sum)], ["Отказов", r => fmt(r.fails)], ["Возвратов", r => fmt(r.refunds)], ["Тестовых подарков", r => fmt(r.test_gifts) + " / " + fmt(r.test_gift_sum)]];
const mnPos = p => itemLine(p.code, p.name, p.icon);
// ★ 22.11.2026: «Оплачено, не выдано» — итоги (сверяемые и до первого номера в CashUse) и причины по журналам (domains/money.py undelivered)
const MN_UNDEL_COLS = [["Не выдано: заказов", r => fmt(r.n)], ["Не выдано: сумма", r => fmt(r.sum)], ["Сверка неприменима: заказов", r => fmt(r.na_n)], ["Сверка неприменима: сумма", r => fmt(r.na_sum)]];
const MN_REASON = { A: "A: GameServer отбросил код", B: "B: ответ не дошёл (обрыв)", unknown: "причина не установлена", na: "сверка по номеру неприменима" };
const mnReason = x => x.reason ? badge(T(MN_REASON[x.reason] || x.reason), x.reason === "unknown" ? "warn" : "") : badge(T("журналы не разбирались"), "");

function mnPosDelivery(p) {
  if (!p.delivery) return acText("—");
  return h("span", { class: "mono small" }, acText(String(p.delivery) + (p.delivery_name && p.delivery_name !== p.name ? " · " + p.delivery_name : "")));
}

// строки категорий учёток с пометкой «не в общем итоге» + общий итог
function mnCatRows(t, cols) {
  const rows = ["player", "service", "nolink"].map(c => Object.assign({ cat: c, out: c === "service" && !t.service_in_total }, t.cats[c]));
  rows.push(Object.assign({ cat: "", grand: true }, t.total));
  return acTable([["Учётки", r => r.grand ? h("b", null, T("общий итог")) : h("span", null, mnCat(r.cat), r.out ? h("span", null, " ", badge(T("не в общем итоге"), "warn")) : null)]].concat(cols), rows);
}

async function viewMoney(my) {
  const out = h("div");
  mount(shell("#/money", h("h1", null, "Деньги"), h("div", { class: "note" },
    acText(T("Только чтение. Монетизация gp7: журнал покупок и подарков всех учёток, висящие подарки, продажи по дням и позициям. Служебные учётки ≤ 5000 по умолчанию — отдельной строкой, не в общем итоге. Сток AsdaStoryOp (CashUse, Sale*) — зеркало заказов gp7: показан рядом с пометкой «сток» и в итог не входит."))), out));
  const svcIn = h("input", { type: "checkbox" });
  const svc = () => svcIn.checked ? "in" : "sep";
  const sumBox = h("div"), holdBox = h("div"), purBox = h("div"), giftBox = h("div"), saleBox = h("div"), accBox = h("div");

  // ---- сводка
  async function loadSummary() {
    put(sumBox, h("div", { class: "muted" }, "Загружаю…"));
    let s;
    try { s = await api("/api/money/summary?" + acQs({ svc: svc() })); } catch (e) { if (!stale(my)) put(sumBox, errbox(e)); return; }
    if (stale(my)) return;
    put(sumBox, (s.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      h("div", { class: "row" }, s.test_fixed_balance ? badge(T("на шлюзе тестовый баланс testFixedBalance = {0}: игрок видит его, а не базу", fmt(s.test_fixed_balance)), "warn")
        : (s.test_fixed_balance === 0 ? badge(T("тестовый баланс шлюза выключен"), "ok") : null),
        h("span", { class: "muted small" }, acText(T("Журнал: {0} — {1} (часы сервера), учёток {2}, позиций {3}.", dt(s.first), dt(s.last), fmt(s.users), fmt(s.codes))))),
      h("h2", null, "Покупки gp7 за всё время"),
      s.purchases ? mnCatRows(s.purchases, MN_MONEY_COLS) : null,
      s.undelivered && s.undelivered.totals ? h("div", null, h("h2", null, "Списано, но не выдано"),
        h("div", { class: "muted small" }, acText(T("Покупки gp7 без строки стока своей процедуры и без ящика ItemPostbox (заказы моложе {0} мин не считаются). Входят в «Списано» выше, здесь — отдельно, чтобы не прятаться в выручке. Причины — в карточке «Оплачено, не выдано».", s.undelivered.minutes))),
        mnCatRows(s.undelivered.totals, MN_UNDEL_COLS)) : null,
      h("h2", null, "Подарки"),
      acTable([["Состояние", r => T(MN_STATE[r.state] || r.state)], ["Тест", r => r.test_mode ? badge(T("test_mode"), "warn") : acText("—")], ["Штук", r => fmt(r.n)], ["Сумма", r => fmt(r.s)]], s.gifts || []),
      h("div", { class: "muted small" }, acText(T("Висящих (заморожено, не выдано) старше {0} мин: {1}.", s.minutes, fmt(s.hanging)))),
      h("h2", null, "Балансы gp7"),
      s.balances ? mnCatRows(s.balances, [["Счетов", r => fmt(r.n)], ["С балансом > 0", r => fmt(r.positive)], ["Сумма", r => fmt(r.sum)], ["Наибольший", r => fmt(r.max)]]) : null,
      h("h2", null, "Сток AsdaStoryOp"),
      h("div", { class: "muted small" }, acText(T("CashUse, SalePremium и SaleFunctional пишет процедура Joy1.UPCashitemBuy, когда сервер кладёт оплаченный заказ gp7 в ящик; SaleHair — процедуры UPHairChange и UPWebMallHair при покупке причёски (строки CashUse у причёски нет). Номер заказа = номер строки журнала gp7. Сумма — как её записал сток, это не деньги gp7."))),
      acTable([["Таблица", r => h("span", null, badge(T("сток"), ""), " ", T(MN_STOCK[r.table] || r.table))], ["Строк", r => fmt(r.n)], ["Сумма стока", r => fmt(r.sum)],
        ["Из них служебных", r => fmt(r.svc_n)], ["Первая (сервер)", r => dt(r.first)], ["Последняя (сервер)", r => dt(r.last)]], s.stock || []));
  }

  // ---- висящие подарки
  const holdMin = h("input", { type: "number", min: 1, max: 10080, value: 10, class: "mono" });
  async function loadHolds() {
    put(holdBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/money/holds?" + acQs({ minutes: holdMin.value })); } catch (e) { if (!stale(my)) put(holdBox, errbox(e)); return; }
    if (stale(my)) return;
    put(holdBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      h("div", { class: "muted small" }, acText(T("Сверка как {0}: заморожено и не выдано старше {1} мин, окно ±{2} с. Подсказка ничего не применяет — решение «commit / refund» принимает человек консольной сверкой.", r.source, r.minutes, r.window))),
      r.counts ? h("div", { class: "muted small" }, acText(T("Заморожено сейчас: {0}, из них висящих: {1} (всего подарков {2}).", fmt(r.counts.H), fmt(r.counts.hanging), fmt(r.counts.all)))) : null,
      r.capped ? badge(T("разобраны первые {0} висящих из {1} — остальные в консольной сверке", r.holds_max, r.counts.hanging), "warn") : null,
      acTable([["Заказ", x => x.order_id], ["Заморожено (сервер)", x => dt(x.created_local)], ["Возраст, мин", x => fmt(x.age_min)],
        ["Отправитель", x => h("span", null, acAccount(x.sender_userindex, x.sender_account), " ", acText(x.sender_name), x.service ? h("span", null, " ", badge(T("служебная"), "")) : null)],
        ["Получатель", x => h("span", null, acText(x.recipient_name), " ", x.r_userindex ? acAccount(x.r_userindex, x.r_uid) : badge(T("не найден однозначно"), "warn"))],
        ["Позиции", x => h("span", null, x.items.map(p => mnPos(p)))], ["Сумма", x => fmt(x.amount)],
        ["Тест", x => x.test_mode ? badge(T("test_mode: возврат меняет только состояние"), "warn") : acText("—")],
        ["Подсказка", x => h("span", null, badge(acText(x.hint), x.hint_raw === "неясно" ? "warn" : ""), h("div", { class: "muted small" }, acText(x.hint_why)))]], r.holds));
  }

  // ---- журнал покупок
  const pAcc = h("input", { type: "text", maxlength: 50, placeholder: "номер или логин", class: "mono" });
  const pCode = h("input", { type: "number", min: 0, placeholder: "код", class: "mono" });
  const pKind = sel([["", T("все виды")]].concat(Object.entries(MN_KIND).map(([k, v]) => [k, T(v)])), "");
  const pWho = sel([["", T("все учётки")]].concat(Object.entries(MN_CAT).map(([k, v]) => [k, T(v)])), "");
  const pTest = sel([["", T("тест и не тест")], ["1", T("только тест (test_mode)")], ["0", T("без теста")]], "");
  const pFrom = h("input", { type: "date" }), pTo = h("input", { type: "date" });
  const pSize = sel([[25, "25"], [50, "50"], [100, "100"], [200, "200"]], 50);
  const pInfo = h("div", { class: "muted small" });
  async function loadPurchases(page) {
    put(pInfo, acText(T("Загружаю…")));
    let r;
    try {
      r = await api("/api/money/purchases?" + acQs({ account: pAcc.value.trim(), code: pCode.value.trim(), kind: pKind.value, who: pWho.value, test: pTest.value,
        from: acDay(pFrom.value), to: acDay(pTo.value), svc: svc(), page: page || 1, size: pSize.value }));
    } catch (e) { if (!stale(my)) { put(pInfo, errbox(e)); put(purBox); } return; }
    if (stale(my)) return;
    put(pInfo, acText(T("Строк {0} · страница {1} из {2}", fmt(r.total), r.page, r.pages)));
    put(purBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      r.totals ? mnCatRows(r.totals, MN_MONEY_COLS) : null,
      acTable([["№", x => x.id], ["Когда (сервер)", x => dt(x.created_local)], ["Вид", x => h("span", null, T(MN_KIND[x.kind] || x.kind), x.test ? h("span", null, " ", badge(T("тест"), "warn")) : null,
          x.test_refunded ? h("span", null, " ", badge(T("возвращён в тесте — не выручка"), "warn")) : null,
          x.gift_state ? h("span", null, " ", badge(acText(x.gift_state), "")) : null)],
        ["Учётка сайта", x => acText(x.site_login)], ["Игровая", x => acAccount(x.Userindex, x.Us_id)], ["Кат.", x => mnCat(x.cat)],
        ["Позиция", x => mnPos(x.pos)], ["Код выдачи", x => mnPosDelivery(x.pos)], ["Сумма", x => fmt(x.amount)],
        ["Было → стало", x => fmt(x.balance_before) + " → " + fmt(x.balance_after)], ["Получатель", x => acText(x.recipient_name)]], r.rows),
      r.pages > 1 ? pager(r.page, r.pages, p => loadPurchases(p)) : null);
  }

  // ---- подарки
  const gState = sel([["", T("все состояния")]].concat(Object.entries(MN_STATE).map(([k, v]) => [k, T(v)])), "");
  const gTest = sel([["", T("тест и не тест")], ["1", T("только тест (test_mode)")], ["0", T("без теста")]], "");
  const gHang = h("input", { type: "checkbox" });
  const gAcc = h("input", { type: "text", maxlength: 50, placeholder: "номер или логин", class: "mono" });
  const gFrom = h("input", { type: "date" }), gTo = h("input", { type: "date" });
  const gInfo = h("div", { class: "muted small" });
  async function loadGifts(page) {
    put(gInfo, acText(T("Загружаю…")));
    let r;
    try {
      r = await api("/api/money/gifts?" + acQs({ state: gState.value, test: gTest.value, hanging: gHang.checked ? "1" : "", minutes: holdMin.value,
        account: gAcc.value.trim(), from: acDay(gFrom.value), to: acDay(gTo.value), page: page || 1 }));
    } catch (e) { if (!stale(my)) { put(gInfo, errbox(e)); put(giftBox); } return; }
    if (stale(my)) return;
    put(gInfo, acText(T("Подарков {0} · страница {1} из {2}", fmt(r.total), r.page, r.pages)));
    put(giftBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      acTable([["Заказ", x => x.order_id], ["Когда (сервер)", x => dt(x.created_local)], ["Состояние", x => h("span", null, T(MN_STATE[x.state] || x.state),
          x.hanging ? h("span", null, " ", badge(T("висит"), "warn")) : null)], ["Тест", x => x.test_mode ? badge(T("test_mode"), "warn") : acText("—")],
        ["Отправитель", x => h("span", null, acAccount(x.sender_userindex, x.sender_account), " ", acText(x.sender_name), x.service ? h("span", null, " ", badge(T("служебная"), "")) : null)],
        ["Получатель", x => acText(x.recipient_name)], ["Позиции", x => h("span", null, x.items.map(p => mnPos(p)))], ["Сумма", x => fmt(x.amount)],
        ["Расчёт (сервер)", x => dt(x.settled_local)], ["Ответ 5077", x => acText(x.settle_result)], ["Строка возврата", x => acText(x.refund_log_id)]], r.rows),
      r.pages > 1 ? pager(r.page, r.pages, p => loadGifts(p)) : null);
  }

  // ---- продажи по дням и позициям
  const sFrom = h("input", { type: "date" }), sTo = h("input", { type: "date" });
  const sWho = sel([["", T("все учётки")]].concat(Object.entries(MN_CAT).map(([k, v]) => [k, T(v)])), "");
  async function loadSales() {
    put(saleBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/money/sales?" + acQs({ from: acDay(sFrom.value), to: acDay(sTo.value), who: sWho.value, svc: svc() })); }
    catch (e) { if (!stale(my)) put(saleBox, errbox(e)); return; }
    if (stale(my)) return;
    const sd = {};
    (r.stock_days || []).forEach(d => { sd[d.day] = d; });
    put(saleBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      r.period ? h("div", { class: "muted small" }, acText(T("Период {0} — {1}, сутки по часам SQL-сервера. Служебные: {2}.", r.period.from, r.period.to,
        r.svc === "in" ? T("в общем итоге") : T("отдельно, не в общем итоге")))) : null,
      h("h2", null, "По дням"),
      acTable([["День (сервер)", d => d.day], ["Покупок", d => fmt(d.total.n)], ["Списано", d => fmt(d.total.gross)], ["Возвращено", d => fmt(d.total.refunded)],
        ["Итого", d => fmt(d.total.sum)], ["Из них подарков", d => fmt(d.total.gifts)], ["Тестовых подарков", d => fmt(d.total.test_gifts)],
        ["Служебные: покупок / итого", d => fmt(d.cats.service.n) + " / " + fmt(d.cats.service.sum)],
        ["Сток CashUse: заказов / сумма", d => sd[d.day] && sd[d.day].cash_n !== null ? fmt(sd[d.day].cash_n) + " / " + fmt(sd[d.day].cash_sum) : "—"]], r.days),
      r.cross ? h("div", { class: "muted small" }, acText(T("Сверка номеров заказов gp7 (покупки без подарков) со стоком своей процедуры: заказов gp7 {0}; в CashUse (предметы) {1}, из них сведено {2}; в SaleHair (причёски) {3}, сведено {4}; только gp7 — {5}: строки стока нет ни там, ни там, в ящике ItemPostbox из них сейчас {6}, причина по данным не установлена; только сток — {7}.",
        r.cross.gp7_orders, r.cross.stock_orders, r.cross.both, r.cross.hair_orders, r.cross.hair_both, r.cross.gp7_only, r.cross.in_postbox, r.cross.stock_only + (r.cross.hair_only || 0)))) : null,
      h("h2", null, "По позициям gp7"),
      h("div", { class: "muted small" }, acText(r.svc === "in" ? T("Порядок — по сумме всех учёток.") : T("Порядок и отбор — по сумме без служебных; служебные — своими столбцами."))),
      r.codes_capped ? badge(T("показаны {0} позиций из {1} с наибольшей суммой", r.codes.length, r.codes_all), "warn") : null,
      acTable([["Позиция", c => mnPos(c.pos)], ["Код выдачи", c => mnPosDelivery(c.pos)], ["Цена по карте", c => fmt(c.pos.map_price)],
        ["Покупок", c => fmt(c.total_n)], ["Сумма", c => fmt(c.total_s)], ["Учёток (без служебных)", c => fmt(c.users)], ["Служебные: учёток / покупок / сумма", c => fmt(c.svc_users) + " / " + fmt(c.svc_n) + " / " + fmt(c.svc_s)]], r.codes),
      h("h2", null, "Сток по позициям"),
      acTable([["Таблица", c => h("span", null, badge(T("сток"), ""), " ", acText(c.table))], ["Код", c => c.code], ["Название", c => acText(c.name)],
        ["Строк", c => fmt(c.n)], ["Сумма стока", c => fmt(c.sum)], ["Из них служебных", c => fmt(c.svc_n)]], r.stock_codes || []));
  }

  // ---- оплачено, не выдано (22.11.2026)
  const uWho = sel([["", T("все учётки")]].concat(Object.entries(MN_CAT).map(([k, v]) => [k, T(v)])), "");
  const uFrom = h("input", { type: "date" }), uTo = h("input", { type: "date" });
  // ★ ревизия 53 Н-2: журналы читаются только по кнопке «Разобрать причины» (открытие раздела и смена «служебных» — без журналов)
  const undelBox = h("div");
  async function loadUndelivered(withLogs) {
    put(undelBox, h("div", { class: "muted" }, withLogs ? T("Загружаю… (журналы GameServer и шлюза читаются целиком — до минуты)") : T("Загружаю…")));
    let r;
    try { r = await api("/api/money/undelivered?" + acQs({ who: uWho.value, from: acDay(uFrom.value), to: acDay(uTo.value), svc: svc(), logs: withLogs ? "1" : "0" })); }
    catch (e) { if (!stale(my)) put(undelBox, errbox(e)); return; }
    if (stale(my)) return;
    const br = r.by_reason || {};
    put(undelBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      h("div", { class: "muted small" }, acText(T("Заказ gp7 (покупка, не подарок) списан, а строки стока своей процедуры (CashUse — предметы, SaleHair — причёски) нет и в ящике ItemPostbox его нет. Заказы моложе {0} мин не сверяются; в ящике сейчас {1}.", r.minutes, fmt(r.in_postbox)))),
      r.cutoff ? h("div", { class: "muted small" }, acText(T("Первый номер gp7 в CashUse — №{0} ({1}, сервер): у более ранних заказов номера в стоке нет, сверка по номеру неприменима.", r.cutoff.id, dt(r.cutoff.local)))) : null,
      r.totals ? mnCatRows(r.totals, MN_UNDEL_COLS) : null,
      r.logs ? h("div", { class: "muted small" }, acText(T("Причины по журналам: A — {0}, B — {1}, не установлена — {2}, неприменима — {3}. A: GameServer получил ответ и отбросил код (в журнале шлюза код < 20551 или в Buy_<день>.txt «ItemCode is Invalid»). B: сокет GameServer закрылся не позже 2 с после ответа шлюза (или отметка PURCHASE_UNCONFIRMED).", fmt(br.A), fmt(br.B), fmt(br.unknown), fmt(br.na)))) : null,
      r.capped ? badge(T("показаны {0} новых заказов из {1}", r.rows.length, r.total), "warn") : null,
      acTable([["№", x => x.id], ["Когда (сервер)", x => dt(x.created_local)], ["Учётка сайта", x => acText(x.site_login)], ["Игровая", x => acAccount(x.Userindex, x.Us_id)],
        ["Кат.", x => mnCat(x.cat)], ["Позиция", x => mnPos(x.pos)], ["Сумма", x => fmt(x.amount)],
        ["Причина", x => h("span", null, mnReason(x), x.reason_why ? h("div", { class: "muted small" }, acText(x.reason_why)) : null)]], r.rows));
  }

  // ---- учётка сайта ↔ игровая
  const aAcc = h("input", { type: "text", maxlength: 50, placeholder: "номер или логин", class: "mono" });
  const aWho = sel([["", T("все учётки")]].concat(Object.entries(MN_CAT).map(([k, v]) => [k, T(v)])), "");
  const aInfo = h("div", { class: "muted small" });
  async function loadAccounts(page) {
    put(aInfo, acText(T("Загружаю…")));
    let r;
    try { r = await api("/api/money/accounts?" + acQs({ account: aAcc.value.trim(), who: aWho.value, page: page || 1 })); }
    catch (e) { if (!stale(my)) { put(aInfo, errbox(e)); put(accBox); } return; }
    if (stale(my)) return;
    put(aInfo, acText(T("Учёток сайта {0} · страница {1} из {2} · игровых без строки сайта: {3}", fmt(r.total), r.page, r.pages, fmt(r.game_without_site))));
    put(accBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      acTable([["Сайт №", x => x.id], ["Логин сайта", x => acText(x.username)], ["Роль сайта", x => acText(x.role)], ["Игровая", x => acAccount(x.Userindex, x.Us_id)],
        ["Кат.", x => mnCat(x.cat)], ["Баланс", x => fmt(x.balance)], ["Подарочный", x => fmt(x.present)], ["Покупок", x => fmt(x.purchases)],
        ["Списано", x => fmt(x.gross)], ["Возвращено", x => fmt(x.refunded)], ["Итого", x => fmt(x.spent)], ["Последняя покупка (сервер)", x => dt(x.last)]], r.rows),
      r.pages > 1 ? pager(r.page, r.pages, p => loadAccounts(p)) : null);
  }

  // ---- ★ А6.9 (22.11.2026): корректировка баланса gp7 (операция money.adjust — только owner) и журнал корректировок (money.view).
  //   Окно подтверждения: сумма и логин сайта набираются заново, свежий код второго фактора; ключ запроса — один на окно (повтор не
  //   двигает деньги второй раз). Корректировки — не выручка: отдельная таблица, в итоги покупок не входят. Данные — только текстовыми узлами.
  const MN_ADJ_KIND = { credit: "начислить", debit: "списать" };
  const adjBox = h("div"), adjInfo = h("div", { class: "muted small" });
  const aLogin = h("input", { type: "text", maxlength: 50, placeholder: "логин сайта или игровой учётки", class: "mono", autocomplete: "off" });
  const aKind = sel(Object.entries(MN_ADJ_KIND).map(([k, v]) => [k, T(v)]), "credit");
  const aAmount = h("input", { type: "number", min: 1, max: 100000, placeholder: "сумма", class: "mono" });
  const aReason = h("input", { type: "text", maxlength: 300, placeholder: "причина (обязательна, 5…300 знаков)", class: "grow", autocomplete: "off" });
  const jAcc = h("input", { type: "text", maxlength: 50, placeholder: "номер или логин", class: "mono" });
  // ключ запроса UUID v4 (crypto.randomUUID; без него — те же 16 случайных байт getRandomValues с метками версии и варианта)
  const mnReq = () => {
    if (crypto.randomUUID) return crypto.randomUUID();
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
    const x = [...b].map(v => v.toString(16).padStart(2, "0")).join("");
    return x.slice(0, 8) + "-" + x.slice(8, 12) + "-" + x.slice(12, 16) + "-" + x.slice(16, 20) + "-" + x.slice(20);
  };
  // ★ ревизия 63 Н-2: ключ запроса живёт до успеха или правки полей — повтор после потерянного ответа уходит с ТЕМ ЖЕ ключом и получает
  //   «запрос уже выполнен: корректировка №…», а не вторую корректировку
  let adjReq = null;
  const adjReset = () => { adjReq = null; };
  [aLogin, aKind, aAmount, aReason].forEach(el => { el.addEventListener("input", adjReset); el.addEventListener("change", adjReset); });
  async function adjust() {
    const req = adjReq = adjReq || mnReq();
    const params = { login: aLogin.value.trim(), kind: aKind.value, amount: aAmount.value.trim(), reason: aReason.value, req };
    let p;
    try { p = await op("money.adjust", params, true); } catch (e) { return notify(e.message, true); }
    const pv = p.preview;
    const cAmount = h("input", { type: "text", maxlength: 6, placeholder: T("сумма ещё раз"), class: "mono", autocomplete: "off" });
    const cLogin = h("input", { type: "text", maxlength: 50, placeholder: T("логин сайта ещё раз"), class: "mono", autocomplete: "off" });
    const code = h("input", { type: "text", maxlength: 6, placeholder: T("свежий код второго фактора (не тот, которым входили)"), autocomplete: "one-time-code" });
    if (!await confirmWin(T("Подтвердите корректировку баланса gp7"), [h("div", { class: "pv" }, acText(pv.text)),
      h("div", { class: "muted small" }, acText(T("Причина: {0}", pv.reason))),
      h("div", { class: "muted small" }, acText(T("Сутки по часам сервера: {0} из {1} после этой корректировки; за операцию — до {2}.", fmt(pv.day_used), fmt(pv.day_max), fmt(pv.op_max)))),
      (pv.warnings || []).map(w => h("div", { class: "note" }, acText(w))),
      (pv.last || []).length ? h("div", null, h("div", { class: "muted small" }, acText(T("Последние корректировки учётки:"))),
        acTable([["№", x => x.id], ["Когда (сервер)", x => dt(x.created_local)], ["Изменение", x => (x.delta > 0 ? "+" : "") + fmt(x.delta)],
          ["Было → стало", x => fmt(x.balance_before) + " → " + fmt(x.balance_after)], ["Оператор", x => acText(x.operator)],
          ["Откат", x => x.undo_of ? badge(T("откат №{0}", x.undo_of), "") : x.undone_by ? badge(T("откачено №{0}", x.undone_by), "warn") : acText("—")]], pv.last))
        : h("div", { class: "muted small" }, acText(T("Корректировок у учётки ещё не было."))),
      h("div", { class: "muted small" }, acText(T("Второе подтверждение: наберите сумму и логин сайта заново."))),
      h("div", { class: "row" }, cAmount, cLogin, code)], T("Провести"))) return;
    try {
      const x = await op("money.adjust", Object.assign({}, params, { confirm_amount: cAmount.value.trim(), confirm_login: cLogin.value.trim(),
        totp: code.value.trim(), expect: pv.expect }), false);
      notify(x.message);
      adjReq = null;                                   // успех — следующая корректировка с новым ключом
      loadAdjustments(1); loadSummary();
    } catch (e) { notify(e.message, true); }
  }
  async function loadAdjustments(page) {
    put(adjInfo, acText(T("Загружаю…")));
    let r;
    try { r = await api("/api/money/adjustments?" + acQs({ account: jAcc.value.trim(), page: page || 1 })); }
    catch (e) { if (!stale(my)) { put(adjInfo, errbox(e)); put(adjBox); } return; }
    if (stale(my)) return;
    put(adjInfo, acText(T("Корректировок {0} · страница {1} из {2}", fmt(r.total), r.page, r.pages)));
    put(adjBox, (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      r.tfb_warning ? badge(acText(r.tfb_warning), "warn") : null,
      r.day ? h("div", { class: "muted small" }, acText(T("Сутки {0} (часы сервера): корректировок {1}, сумма {2} из {3}, осталось {4}; за операцию — до {5}. Откаты в лимит не входят.",
        r.day.day, fmt(r.day.n), fmt(r.day.used), fmt(r.day_max), fmt(r.day.left), fmt(r.op_max)))) : null,
      acTable([["№", x => x.id], ["Когда (сервер)", x => dt(x.created_local)], ["Учётка сайта", x => acText(x.username)], ["Игровая", x => acAccount(x.Userindex, x.Us_id)],
        ["Кат.", x => mnCat(x.cat)], ["Изменение", x => (x.delta > 0 ? "+" : "") + fmt(x.delta)], ["Было → стало", x => fmt(x.balance_before) + " → " + fmt(x.balance_after)],
        ["Причина", x => acText(x.reason)], ["Оператор", x => acText(x.operator + " · " + x.via)],
        ["Откат", x => x.undo_of ? badge(T("откат №{0}", x.undo_of), "") : x.undone_by ? badge(T("откачено №{0}", x.undone_by), "warn") : acText("—")]], r.rows),
      r.pages > 1 ? pager(r.page, r.pages, p => loadAdjustments(p)) : null);
  }

  svcIn.addEventListener("change", () => { loadSummary(); loadPurchases(1); loadSales(); loadUndelivered(); });
  put(out,
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Сводка"), h("label", null, svcIn, " служебные ≤ 5000 в общем итоге"),
      h("button", { type: "button", onclick: () => loadSummary() }, "Обновить")), sumBox),
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Висящие подарки"), h("span", null, "Старше, мин "), holdMin,
      h("button", { type: "button", onclick: () => loadHolds() }, "Показать")), holdBox),
    h("div", { class: "card" }, h("h2", null, "Журнал покупок gp7"),
      h("div", { class: "row" }, h("span", null, "Учётка "), pAcc, h("span", null, "Код "), pCode, h("span", null, "Вид "), pKind, h("span", null, "Учётки "), pWho, pTest),
      h("div", { class: "row" }, h("span", null, "С "), pFrom, h("span", null, "по "), pTo, h("span", null, "Строк "), pSize,
        h("button", { type: "button", onclick: () => loadPurchases(1) }, "Показать")), pInfo, purBox),
    h("div", { class: "card" }, h("h2", null, "Подарки gp7"),
      h("div", { class: "row" }, h("span", null, "Учётка "), gAcc, gState, gTest, h("label", null, gHang, " только висящие")),
      h("div", { class: "row" }, h("span", null, "С "), gFrom, h("span", null, "по "), gTo, h("button", { type: "button", onclick: () => loadGifts(1) }, "Показать")),
      gInfo, giftBox),
    h("div", { class: "card" }, h("h2", null, "Продажи по дням и позициям"),
      h("div", { class: "row" }, h("span", null, "С "), sFrom, h("span", null, "по "), sTo, h("span", null, "Учётки "), sWho,
        h("button", { type: "button", onclick: () => loadSales() }, "Показать")), saleBox),
    h("div", { class: "card" }, h("h2", null, "Оплачено, не выдано"),
      h("div", { class: "row" }, h("span", null, "Учётки "), uWho, h("span", null, "С "), uFrom, h("span", null, "по "), uTo,
        h("button", { type: "button", onclick: () => loadUndelivered(false) }, "Показать"),
        h("button", { type: "button", onclick: () => loadUndelivered(true) }, "Разобрать причины по журналам")), undelBox),
    can("money.adjust") ? h("div", { class: "card" }, h("h2", null, "Корректировка баланса gp7"),
      h("div", { class: "muted small" }, acText(T("Только владелец. Начислить или списать баланс учётки сайта gp7: причина обязательна, до 100 000 за операцию и 500 000 в сутки (по часам сервера), второе подтверждение — сумма и логин заново и код второго фактора. Откат — в «Журнале действий»: обратная корректировка со ссылкой."))),
      h("div", { class: "row" }, h("span", null, "Учётка "), aLogin, aKind, aAmount),
      h("div", { class: "row" }, aReason, h("button", { type: "button", class: "gold", onclick: () => adjust() }, "Предпросмотр и подтверждение"))) : null,
    h("div", { class: "card" }, h("h2", null, "Журнал корректировок баланса"),
      h("div", { class: "muted small" }, acText(T("Корректировки баланса панелью — не выручка: в журнал покупок gp7 и итоги раздела не входят."))),
      h("div", { class: "row" }, h("span", null, "Учётка "), jAcc, h("button", { type: "button", onclick: () => loadAdjustments(1) }, "Показать")),
      adjInfo, adjBox),
    h("div", { class: "card" }, h("h2", null, "Учётка сайта ↔ игровая"),
      h("div", { class: "row" }, h("span", null, "Учётка "), aAcc, h("span", null, "Учётки "), aWho, h("button", { type: "button", onclick: () => loadAccounts(1) }, "Показать")),
      aInfo, accBox));
  loadSummary();
  loadHolds();
  loadPurchases(1);
  loadGifts(1);
  loadSales();
  loadUndelivered();
  loadAccounts(1);
  loadAdjustments(1);
}
