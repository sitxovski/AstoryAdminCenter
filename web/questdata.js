// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Данные игры → Задания» (шаг А4.5, 20.11.2026; область domains/cs_kinds/questtables.py, пара сервер + клиент):
// награда задания (RepayTable всех GameServer ↔ RewardTable клиента: золото, опыт, предметы A1, A2, B1) и задание доски объявлений
// (LimitationQuest 12 копий ↔ DT_RaidQuestData с ведомостью: уровни, лимит, опыт, золото). Позиция уходит в набор изменений (проверка,
// «кто держит задание», двойное подтверждение сильной правки, выкладка рестартом стойки, клиентская половина — консолью ПК).
// Общие помощники — из app.js и shops.js: h(), T(), put(), mount(), shell(), table(), kv(), sel(), numIn(), csRun(), shopsTabs(), lookup().
"use strict";

async function qdAdd(target, kind, params, title) {
  let id = target.value;
  if (!id) {
    const x = await csRun("shop.cs_create", { title: title, note: T("правка заданий (сервер + клиент)"), order_mode: "together", urgent: false });
    if (!x || !x.result) return;
    id = x.result.id;
  }
  const r = await csRun("shop.cs_item_add", { cs: +id, kind, params });
  if (r) location.hash = "#/shops/set/" + id;
}

// ★ ревизия 37 К-4: готовый (уже переведённый) текст или имя из данных — узлом текста: h() прогнал бы его через T() второй раз
function qdText(s) { return document.createTextNode(String(s)); }

function qdFields(rows, cur) {
  const f = {};
  rows.forEach(r => { const v = r.inp.value.trim(); if (v !== "" && +v !== cur(r)) f[r.key] = +v; });
  return f;
}

async function qdRewardCard(box, target, rid) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let m;
  try { m = await lookup("repay", rid); } catch (e) { put(box, errbox(e)); return; }
  const srv = m.server.GameServer || {};
  // ★ ревизия 37 К-5: пределы ввода — те же, что у службы (rng_reward в questtables.py отдаётся полями справки)
  const rows = m.fields.map(([key, col, label, lo, hi]) => {
    const cur = srv[key];
    const others = Object.entries(m.server).filter(([g]) => g !== "GameServer").map(([g, v]) => g + ": " + (v ? v[key] : T("нет записи"))).join(", ");
    return { key, label, cur, cli: m.client ? m.client[col] : null, others, inp: numIn(cur === undefined ? "" : cur, lo, hi) };
  });
  // ★ ревизия 37 К-4: уже переведённые строки и имена из Joy1 / справочника — узлом текста, мимо второго T()
  const quests = m.quests.length ? m.quests.map(q => T("{0} «{1}», шаг {2} ({3}), держат: {4}", q.quest, q.name, q.step,
    T(q.action === 2 ? "завершить" : "шаг"), q.holders === null ? T("не прочитано") : q.holders)) : [T("ни одна ячейка NPC эту награду не даёт")];
  // ★ ревизия 37 К-2: у копии своя база (Indun — 636 записей) — правка записи сверх неё отказ, это не ошибка
  const short = Object.entries(m.counts || {}).filter(([, n]) => n < m.rid).map(([g, n]) => T("{0}: записей {1}", g, n));
  const btn = can("data.edit") ? h("button", { type: "button", onclick: () => {
    const f = qdFields(rows, r => r.cur);
    if (!Object.keys(f).length) { notify(T("ни одно поле не изменено"), true); return; }
    qdAdd(target, "quest.reward", { rid: m.rid, fields: f }, T("Награда задания {0}", m.rid));
  } }, "Добавить в набор") : null;
  put(box,
    h("div", { class: "card" }, h("h2", null, qdText(T("Награда {0}", m.rid))),
      kv([[T("Блоки A / B (сервер)"), (m.flags.a ? "A" : "—") + " / " + (m.flags.b ? "B" : "—")],
        [T("Штраф опыта за уровень"), m.flags.pen ? T("да, база {0}", m.flags.pen_base) : T("нет")],
        [T("Профессия наградой"), m.flags.job > 0 ? m.flags.job : "—"],
        [T("Клиент (RewardTable)"), m.client ? T("запись есть") : (m.client_err || T("записи нет"))],
        [T("Задания"), h("div", null, ...quests.map(x => h("div", null, qdText(x))))]]),
      short.length ? h("div", { class: "note" }, qdText(T("У копии своя база и записи {0} в ней нет ({1}) — правка этой награды будет отказом (решение владельца 19.11: только правка существующих записей), это не ошибка панели.", m.rid, short.join(", ")))) : null,
      h("div", { class: "note" }, qdText(T("Правка ложится на RepayTable всех GameServer (у Indun своя база — запись правится по её значениям, записи нет — отказ) и на окно наград клиента (RewardTable.BIN рабочей сборки, QuestRewardTable.json и DT_QuestRewardTable точечно). Предмет награды должен быть на сервере, количество больше 1 — только у стопочных (сервер выдаёт нестопочный предмет и самоцвет в одном экземпляре), правила перепроверяются перед выкладкой и откатом. Код −1 — убрать предмет. Изменение больше чем в 2 раза и новый предмет — второе подтверждение владельца. Ход задания (цели, шаги) не правится.")))),
    h("div", { class: "card" }, h("h3", null, "Поля награды"),
      table([["Поле", r => T(r.label)], ["Сервер", r => r.cur === undefined ? "—" : r.cur], ["Другие GS", r => r.others || "—"],
        ["Клиент", r => r.cli === null || r.cli === undefined ? "—" : r.cli], ["Станет", r => r.inp]], rows), btn));
}

async function qdBoardCard(box, target, qid) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let m;
  try { m = await lookup("boards", qid); } catch (e) { put(box, errbox(e)); return; }
  const c = m.card;
  const rows = m.fields.map(([key, col, label, lo, hi]) => ({ key, label, cur: c.server[key], cli: c.client ? c.client[key] : null,
    inp: numIn(c.server[key], lo, hi) }));                               // ★ ревизия 37 К-5: пределы службы (rng_board)
  const hold = c.holders === null ? T("не прочитано ({0})", c.holders_error || "—")
    : (c.holders.length ? c.holders.map(x => T("{0} ({1}/{2}, ур. {3}), флаг {4}, сдано {5}", x.name, x.uid, x.idx, x.lvl, x.flag, x.count)) : [T("никто")]);
  const btn = can("data.edit") ? h("button", { type: "button", onclick: () => {
    const f = qdFields(rows, r => r.cur);
    if (!Object.keys(f).length) { notify(T("ни одно поле не изменено"), true); return; }
    qdAdd(target, "board.quest", { quest: c.quest, fields: f }, T("Доска: задание {0}", c.quest));
  } }, "Добавить в набор") : null;
  put(box,
    h("div", { class: "card" }, h("h2", null, qdText(T("Доска: задание {0}", c.quest))),
      kv([[T("Тип периода / режим / зона"), c.type + " / " + c.mode + " / " + c.zone], [T("Копии сервера одинаковы"), T(m.copies_same ? "да" : "нет")],
        [T("Держат сейчас (Joy1)"), h("div", null, ...[].concat(hold).map(x => h("div", null, qdText(x))))]]),
      h("div", { class: "note" }, qdText(T("Правка ложится на все 12 копий LimitationQuest.txt (GameServer и NpcServer) и на доску клиента (ведомость чисел board_quest_values.json поверх таблицы эталона, RaidQuestData.json и DT_RaidQuestData точечно). Уровни сервер проверяет при взятии, награду — при сдаче. Изменение больше чем в 2 раза — второе подтверждение владельца.")))),
    h("div", { class: "card" }, h("h3", null, "Поля задания доски"),
      table([["Поле", r => T(r.label)], ["Сервер", r => r.cur], ["Клиент", r => r.cli === null || r.cli === undefined ? "—" : r.cli],
        ["Станет", r => r.inp]], rows), btn));
}

async function viewQuestData(my) {
  const out = h("div");
  mount(shell("#/shops", h("h1", null, "Задания"), shopsTabs("#/shops/quests"), h("div", { class: "note" },
    qdText(T("Правка существующих наград заданий и заданий доски объявлений (пара: сервер — RepayTable / LimitationQuest, клиент — окно наград / доска): позиция попадает в набор изменений, проверка показывает «было → станет» и кто держит задание сейчас, выкладка сервера — рестартом стойки с объявлением, клиент — консолью ПК и выпуском."))),
    // ★ ревизия 37 К-2, М-2: справка вкладки — своя база Indun и вес награды
    h("div", { class: "note" }, qdText(T("У Indun своя база RepayTable — 636 записей против 669 у GameServer и Ch2_GameServer: награды 637–669 (задания Флэммио) у Indun нет, поэтому их правка — отказ по решению владельца 19.11 (только правка существующих записей), это не ошибка. Проверка показывает вес награды (количество × вес по слотам): награда тяжелее самой тяжёлой в данных — второе подтверждение владельца, при двух и больше предметах растущий вес — предупреждение (при перегрузе сервер выдаёт часть, и задание можно сдать повторно)."))), out));
  let sets = [];
  try { sets = (await api("/api/shops/sets")).items.filter(x => x.status === "draft" || x.status === "checked"); } catch (e) { sets = []; }
  if (stale(my)) return;
  const target = sel([["", T("новый набор")]].concat(sets.map(x => [x.id, "№" + x.id + " " + x.title])), sets.length ? sets[0].id : "");
  const q = h("input", { class: "wide", placeholder: "номер или часть названия задания" });
  const rid = numIn("", 1, 32767);
  const found = h("div"), card = h("div");
  const find = async () => {
    put(found, h("div", { class: "muted small" }, "Ищу…"));
    try {
      const r = await lookup("quests", q.value);
      put(found, r.rows.length ? table([["Задание", x => x.quest], ["Название", x => qdText(x.name)],
        ["Награды", x => h("span", null, ...x.rewards.map(n => h("a", { href: "#/shops/quests", onclick: (e) => { e.preventDefault(); qdRewardCard(card, target, n); } }, String(n) + " ")))]],
        r.rows) : h("div", { class: "muted small" }, qdText(T("ничего не найдено"))));
    } catch (e) { put(found, errbox(e)); }
  };
  q.addEventListener("change", find);
  const boards = async () => {
    put(found, h("div", { class: "muted small" }, "Загружаю…"));
    try {
      const r = await lookup("boards", "");
      put(found, table([["Задание", x => x.quest], ["Ур.", x => x.server.lvmin + "/" + x.server.lvmax], ["Лимит", x => x.server.max],
        ["Опыт", x => x.server.exp], ["Золото", x => x.server.gold], ["Клиент", x => x.client ? (x.client.lvmin + "/" + x.client.lvmax + ", " + x.client.exp + ", " + x.client.gold) : "—"]],
        r.rows, x => qdBoardCard(card, target, x.quest)));
    } catch (e) { put(found, errbox(e)); }
  };
  put(out, h("div", { class: "card" }, h("div", { class: "row" }, q, h("button", { type: "button", onclick: find }, "Найти"),
    h("span", null, qdText(T("Награда №"))), rid, h("button", { type: "button", onclick: () => rid.value && qdRewardCard(card, target, rid.value) }, "Открыть"),
    h("button", { type: "button", onclick: boards }, "Доска объявлений"), h("span", null, qdText(T("Набор"))), target,
    can("data.edit") ? null : h("span", { class: "muted small" }, qdText(T("правка — с правом «data.edit»")))), found), card);
}
