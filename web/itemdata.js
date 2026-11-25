// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Данные игры → Предметы» (шаг А4.4, 20.11.2026; область domains/cs_kinds/itemdata.py, пара сервер + клиент):
// поиск предмета или самоцвета, карточка «сервер (все GS) / клиент», правка полей белого списка (прочность, вес, уровни, требование
// класса, стопка; уровень самоцвета); позиция уходит в набор изменений (проверка, отказы «дюп и целостность», двойное подтверждение
// сильной правки, выкладка рестартом стойки, клиентская половина — консолью ПК с ведомостями ItemDB).
// Общие помощники — из app.js и shops.js: h(), T(), put(), mount(), shell(), table(), kv(), sel(), numIn(), csRun(), shopsTabs(), lookup().
"use strict";

async function idAdd(target, kind, params, title) {
  let id = target.value;
  if (!id) {
    const x = await csRun("shop.cs_create", { title: title, note: T("правка предметов (сервер + клиент)"), order_mode: "together", urgent: false });
    if (!x || !x.result) return;
    id = x.result.id;
  }
  const r = await csRun("shop.cs_item_add", { cs: +id, kind, params });
  if (r) location.hash = "#/shops/set/" + id;
}

async function idItemCard(box, target, code) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let m;
  try { m = await lookup("item", code); } catch (e) { put(box, errbox(e)); return; }
  const srv = m.server.GameServer || {};
  const inputs = {};
  const rows = m.fields.map(([name, label, lo, hi]) => {
    const cur = srv[name];
    const inp = numIn(cur === undefined ? "" : cur, lo, hi);
    inputs[name] = inp;
    const others = Object.entries(m.server).filter(([g]) => g !== "GameServer").map(([g, v]) => g + ": " + (v ? v[name] : "—")).join(", ");
    return { name, label, cur, cli: m.client ? m.client[name] : null, others, inp };
  });
  const held = m.held ? T("записей {0}, сумма Amount {1}, наибольшая стопка {2}", m.held.rows, m.held.amount, m.held.max === undefined ? "—" : m.held.max)
    : T("не прочитано ({0})", m.held_error || "—");
  const meta = m.meta ? T("тип {0}, подтип {1}, ток.24 = {2}, сумка {3}", m.meta.type, m.meta.subtype, m.meta.t24, m.plate) : "—";
  const btn = can("data.edit") ? h("button", { type: "button", onclick: () => {
    const f = {};
    rows.forEach(r => { const v = r.inp.value.trim(); if (v !== "" && +v !== r.cur) f[r.name] = +v; });
    if (!Object.keys(f).length) { notify(T("ни одно поле не изменено"), true); return; }
    idAdd(target, "item.set", { code: m.code, fields: f }, T("Предмет {0}: поля карточки", m.code));
  } }, "Добавить в набор") : null;
  put(box,
    h("div", { class: "card" }, h("h2", null, itemLine(m.code, m.name, m.icon)),
      kv([[T("Сервер (GameServer)"), meta], [T("На руках у игроков"), held], [T("Значения класса у этого типа"), (m.jobs || []).join(", ") || "—"],
        [T("Клиент: колонки ≠ DataHex"), m.client ? (m.client._bad || T("нет")) : T("карточки нет")]]),
      h("div", { class: "note" }, T("Правка ложится на item_table всех GameServer и на item_list клиента (колонка, байты записи и ведомость _value_overlay — перегенерация её не сотрёт). Смена стопки и вес стопочного предмета, который есть у игроков (вместе с почтой, аукционом, подарками и неоткаченными изъятиями), — отказ, и это перепроверяется перед выкладкой и откатом сервера. Стопку можно менять только у предметов, которые сервер считает стопочными (ток.3 = 4, ток.24 = 1). Изменение больше чем в 2 раза, смена стопки, вес стопки и класс — второе подтверждение владельца."))),
    h("div", { class: "card" }, h("h3", null, "Поля карточки"),
      table([["Поле", r => T(r.label)], ["Сервер", r => r.cur === undefined ? "—" : r.cur], ["Другие GS", r => r.others || "—"],
        ["Клиент", r => r.cli === null || r.cli === undefined ? "—" : r.cli], ["Станет", r => r.inp]], rows), btn));
}

async function idGemCard(box, target, code) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let m;
  try { m = await lookup("gem", code); } catch (e) { put(box, errbox(e)); return; }
  const lvl = numIn(m.server.GameServer === null ? "" : m.server.GameServer, 0, 255);
  put(box, h("div", { class: "card" }, h("h2", null, itemLine(m.code, m.name, m.icon)),
    kv([[T("Сервер: мин. уровень (Cellob ток.16)"), Object.entries(m.server).map(([g, v]) => g + ": " + (v === null ? "—" : v)).join(", ")],
      [T("Клиент: sowell_list.RequiredLevel / DataHex +65"), m.client === null ? "—" : m.client + " / " + m.client_hex]]),
    h("div", { class: "kv edit" }, h("div", null, "Новый мин. уровень"), lvl),
    h("div", { class: "note" }, T("Самоцветы, уже вставленные в вещи, тоже подчиняются новому уровню: сервер не даст надеть вещь персонажу ниже уровня.")),
    can("data.edit") ? h("button", { type: "button", onclick: () => idAdd(target, "gem.level", { code: m.code, level: lvl.value },
      T("Самоцвет {0}: мин. уровень", m.code)) }, "Добавить в набор") : null));
}

async function viewItemData(my) {
  const out = h("div");
  mount(shell("#/shops", h("h1", null, "Предметы"), shopsTabs("#/shops/items"), h("div", { class: "note" },
    T("Правка существующих предметов и самоцветов (пара: сервер — все GameServer, клиент — item_list / sowell_list с ведомостью): позиция попадает в набор изменений, проверка показывает «было → станет» и «на руках у игроков», выкладка сервера — рестартом стойки с объявлением, клиент — консолью ПК и выпуском.")), out));
  let sets = [];
  try { sets = (await api("/api/shops/sets")).items.filter(x => x.status === "draft" || x.status === "checked"); } catch (e) { sets = []; }
  if (stale(my)) return;
  const target = sel([["", T("новый набор")]].concat(sets.map(x => [x.id, "№" + x.id + " " + x.title])), sets.length ? sets[0].id : "");
  const q = h("input", { class: "wide", placeholder: "код или часть названия предмета" });
  const found = h("div"), card = h("div");
  const open = code => (code >= 7001 && code < 20551 ? idGemCard : idItemCard)(card, target, code);
  const find = async () => {
    put(found, h("div", { class: "muted small" }, "Ищу…"));
    try {
      const r = await lookup("items", q.value);
      put(found, r.rows.length ? table([["Код", x => x.code], ["Предмет", x => itemLine(x.code, x.name, x.icon)],
        ["Вид", x => T(x.code < 20551 ? "самоцвет" : "предмет")]], r.rows, x => open(x.code)) : h("div", { class: "muted small" }, T("ничего не найдено")));
    } catch (e) { put(found, errbox(e)); }
  };
  q.addEventListener("change", find);
  put(out, h("div", { class: "card" }, h("div", { class: "row" }, q, h("button", { type: "button", onclick: find }, "Найти"), h("span", null, T("Набор")), target,
    can("data.edit") ? null : h("span", { class: "muted small" }, T("правка — с правом «data.edit»"))), found), card);
}
