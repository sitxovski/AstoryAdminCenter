// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Данные игры → Монстры и добыча» (шаг А4.3, 20.11.2026; область domains/cs_kinds/monsters.py, только сервер):
// поиск моба, основной / мировой / квестовый дроп, деньги, опыт, копание (MiningItemTable); шанс «было → станет» по правилам
// розыгрыша сервера; позиция уходит в набор изменений (проверка, двойное подтверждение сильной правки, выкладка рестартом стойки).
// Общие помощники — из app.js и shops.js: h(), T(), put(), mount(), shell(), table(), kv(), sel(), numIn(), csRun(), shopsTabs(), lookup().
"use strict";
const MOB_RND = 100000;
const mobSpan = (lo, hi) => Math.max(0, Math.min(hi, MOB_RND - 1) - Math.max(lo, -1));
const mobPRate = r => mobSpan(-1, r) / MOB_RND;                                   // (rate+1)/100 000, независимая строка
const mobPPct = r => (r < 0 ? 0 : (Math.min(r, 99) + 1) / 100);                    // (rate+1)/100, процентный бросок
function mobCum(rates) { let top = -1; return rates.map(r => { const p = mobSpan(top, r) / MOB_RND; top = Math.max(top, r); return p; }); }
function mobPct(p) {
  if (p >= 1) return "100 %";
  if (p <= 0) return "0 %";
  return (p * 100).toFixed(4).replace(/0+$/, "").replace(/\.$/, "") + " %";
}

async function mobSets() {
  try { return (await api("/api/shops/sets")).items.filter(x => x.status === "draft" || x.status === "checked"); } catch (e) { return []; }
}

// Позиция → набор (выбранный черновик или новый) → карточка набора
async function mobAdd(target, kind, params, title) {
  let id = target.value;
  if (!id) {
    const x = await csRun("shop.cs_create", { title: title, note: T("правка монстров и добычи (только сервер)"), order_mode: "together", urgent: false });
    if (!x || !x.result) return;
    id = x.result.id;
  }
  const r = await csRun("shop.cs_item_add", { cs: +id, kind, params });
  if (r) location.hash = "#/shops/set/" + id;
}

function mobRowsEditor(cols, rows, odds) {
  // cols: [[подпись, ключ, мин, макс, ширина|"text"]], rows: [{…}], odds(rows) → [шанс]
  const box = h("div");
  const state = rows.map(r => Object.assign({}, r));
  const draw = () => {
    const ps = odds(state);
    put(box, table(cols.map(([label, key, lo, hi, kindc]) => [label, (r) => {
      const i = state.indexOf(r);
      if (kindc === "ro") return r[key];
      const inp = kindc === "text" ? h("input", { value: r[key], class: "mono", size: 16 }) : numIn(r[key], lo, hi);
      inp.addEventListener("change", () => { state[i][key] = kindc === "text" ? inp.value.trim() : +inp.value; draw(); });
      return inp;
    }]).concat([["Шанс", r => mobPct(ps[state.indexOf(r)] || 0)],
      ["", r => cols.fixed ? null : h("button", { type: "button", class: "ghost", onclick: () => { state.splice(state.indexOf(r), 1); draw(); } }, "убрать")]]), state),
      cols.fixed ? null : h("div", { class: "row" }, h("button", { type: "button", class: "ghost", onclick: () => {
        state.push(Object.assign({}, cols.blank)); draw(); } }, "Добавить строку")));
  };
  draw();
  return { el: box, get: () => state };
}

async function mobCard(box, target, id) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let m;
  try { m = await lookup("mob", id); } catch (e) { put(box, errbox(e)); return; }
  const add = can("data.edit");
  const btn = (kind, params, label) => add ? h("button", { type: "button", onclick: () => mobAdd(target, kind, params(), T("Монстр {0}: {1}", m.id, T(label))) }, "Добавить в набор") : null;
  // основной дроп
  const dcols = [["Предмет (код)", "item", 1, 2147483647], ["rate из 100 000", "rate", -1, MOB_RND], ["Количество", "count", 1, 32767]];
  dcols.blank = { item: 0, rate: 0, count: 1 };
  const dodds = rows => m.mode === 1 ? mobCum(rows.map(r => r.rate)).map(p => p * mobPPct(m.rgate)) : rows.map(r => mobPRate(r.rate));
  const drop = mobRowsEditor(dcols, m.drop, dodds);
  // деньги, мировой, опыт
  const mmin = numIn(m.money.min, 0, 32767), mmax = numIn(m.money.max, 0, 32767), mch = numIn(m.money.chance, -1, 100);
  const widx = numIn(m.world.index, -1, 32767), wcnt = numIn(m.world.count, -1, 20), wgate = numIn(m.world.gate, -1, MOB_RND);
  const wbox = h("div");
  const wshow = async () => {
    const g = mobPRate(+wgate.value);
    if (+widx.value < 0) { put(wbox, h("div", { class: "muted small" }, T("мировой дроп выключен (индекс −1)"))); return; }
    try {
      const w = await lookup("world", widx.value);
      put(wbox, h("div", { class: "muted small" }, T("гейт {0}; раз {1}; записей WorldDropItem {2}", mobPct(g), wcnt.value, w.records)),
        table([["Предмет", x => itemLine(x.item, x.name, null)], ["Порог", x => x.rate], ["Шанс", x => mobPct(x.share * g)]], w.items));
    } catch (e) { put(wbox, errbox(e)); }
  };
  [widx, wgate, wcnt].forEach(x => x.addEventListener("change", wshow));
  const exp = numIn(m.exp, 0, 2000000000);
  // квестовый
  const qgate = numIn(m.quest.gate, 0, 255);
  const qcols = [["Задание", "quest", 0, 0, "ro"], ["Шаг", "step", 0, 0, "ro"], ["Предмет (код)", "item", 1, 2147483647], ["Шанс из 100", "rate", -128, 127]];
  qcols.fixed = true;
  const quest = mobRowsEditor(qcols, m.quest.rows, rows => rows.map(r => mobPPct(r.rate)));
  const copies = Object.entries(m.copies).map(([k, v]) => k + ": " + (v.missing ? T("нет записи") : v.same ? T("так же") : T("отличается: +{0}", v.offs))).join("; ");
  put(box,
    h("div", { class: "card" }, h("h2", null, T("Монстр {0} {1}", m.id, m.name || m.ko)),
      kv([[T("Имя (корейское, Monster.ai)"), m.ko], [T("Уровень (+0x04)"), m.level], [T("HP (+0x2D)"), m.hp],
        [T("Режим дропа (+167)"), m.mode === 1 ? T("рулетка: один предмет, гейт {0}", mobPct(mobPPct(m.rgate))) : T("каждая строка независимо")],
        [T("Копии"), copies]]),
      h("div", { class: "note" }, T("HP и уровень — вторая очередь (нужна пара с клиентом Mob_list). Шанс — «чистый», без множителя событий и статов игрока."))),
    h("div", { class: "card" }, h("h3", null, "Основной дроп (Monster.ai +174)"), drop.el,
      btn("mob.drop", () => ({ mob: m.id, rows: drop.get().map(r => [r.item, r.rate, r.count]) }), "основной дроп")),
    h("div", { class: "card" }, h("h3", null, "Деньги (+169…+173)"), h("div", { class: "kv edit" }, h("div", null, "Минимум"), mmin, h("div", null, "Максимум"), mmax,
      h("div", null, "Шанс из 100"), mch), btn("mob.money", () => ({ mob: m.id, min: mmin.value, max: mmax.value, chance: mch.value }), "деньги")),
    h("div", { class: "card" }, h("h3", null, "Мировой дроп (+394 / +396 / +398)"), h("div", { class: "kv edit" }, h("div", null, "Запись WorldDropItem.itm"), widx,
      h("div", null, "Сколько раз"), wcnt, h("div", null, "Гейт из 100 000"), wgate), wbox,
      btn("mob.world", () => ({ mob: m.id, index: widx.value, count: wcnt.value, gate: wgate.value }), "мировой дроп")),
    h("div", { class: "card" }, h("h3", null, "Квестовый дроп (+402 / +403)"),
      h("div", { class: "kv edit" }, h("div", null, "Гейт (1 — включён)"), qgate), quest.el,
      h("div", { class: "muted small" }, T("Задание, шаг и условие не правятся (связь с таблицами заданий). Справка порта DT_MobQuestDrop игрой не читается.")),
      btn("mob.qdrop", () => ({ mob: m.id, gate: qgate.value, rows: quest.get().map(r => [r.item, r.rate]) }), "квестовый дроп")),
    h("div", { class: "card" }, h("h3", null, "Опыт (+0x35)"), h("div", { class: "kv edit" }, h("div", null, "Опыт"), exp),
      btn("mob.exp", () => ({ mob: m.id, exp: exp.value }), "опыт")));
  wshow();
}

async function mineCard(box, target) {
  let meta;
  try { meta = await lookup("mine", ""); } catch (e) { put(box, errbox(e)); return; }
  const map = sel(meta.maps.map(x => [x, x]), meta.maps[3] || meta.maps[0]);
  const typ = sel(Array.from({ length: meta.types }, (_, i) => [i, T("тип {0}", i)]), 0);
  const body = h("div");
  const load = async () => {
    put(body, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await lookup("mine", map.value + ":" + typ.value); } catch (e) { put(body, errbox(e)); return; }
    const cols = [["Предмет (код)", "item", 1, 2147483647], ["Ур. от", "lvmin", 0, 127], ["Ур. до", "lvmax", 0, 127], ["Кол-во от", "cmin", 1, 32767],
      ["Кол-во до", "cmax", 1, 32767], ["Порог (накопительный)", "rate", 0, MOB_RND], ["Опыт", "exp", 0, 2000000000], ["Маска классов", "mask", 0, 0, "text"]];
    cols.blank = { item: 0, lvmin: 1, lvmax: 100, cmin: 1, cmax: 1, rate: MOB_RND, exp: 0, mask: "ffffffffffffffff" };
    const ed = mobRowsEditor(cols, r.rows, rows => mobCum(rows.map(x => x.rate)));
    put(body, kv([[T("Файл"), r.file], [T("Секторов"), r.sectors], [T("Сектора одинаковы"), r.uniform ? T("да") : r.why],
      [T("Копии NpcServer одинаковы"), r.copies_same ? T("да") : T("нет")]]),
      h("div", { class: "note" }, T("Правка ложится одинаково на ВСЕ сектора файла (сервер берёт макс. количество из сектора с номером строки). Пороги растут; после последнего — пусто.")),
      ed.el, can("data.edit") ? h("button", { type: "button", onclick: () => mobAdd(target, "mine.drop",
        { map: r.map, type: r.type, rows: ed.get().map(x => [x.item, x.lvmin, x.lvmax, x.cmin, x.cmax, x.rate, x.exp, x.mask]) },
        T("Копание {0}, тип {1}", r.map, r.type)) }, "Добавить в набор") : null);
  };
  map.addEventListener("change", load);
  typ.addEventListener("change", load);
  put(box, h("div", { class: "kv edit" }, h("div", null, "Карта (MapInfo.ini)"), map, h("div", null, "Тип копания"), typ), body);
  load();
}

async function viewMonsters(my) {
  const out = h("div");
  mount(shell("#/shops", h("h1", null, "Монстры и добыча"), shopsTabs("#/shops/monsters"), h("div", { class: "note" },
    T("Правка существующих мобов и таблиц копания (только сервер, все копии стойки; у Indun — своя база): позиция попадает в набор изменений, проверка показывает шанс «было → станет», изменение больше чем в 2 раза — второе подтверждение владельца, выкладка — рестартом стойки с объявлением.")), out));
  const sets = await mobSets();
  if (stale(my)) return;
  const target = sel([["", T("новый набор")]].concat(sets.map(x => [x.id, "№" + x.id + " " + x.title])), sets.length ? sets[0].id : "");
  const q = h("input", { class: "wide", placeholder: "id или часть имени моба" });
  const found = h("div"), card = h("div"), mine = h("div");
  const find = async () => {
    put(found, h("div", { class: "muted small" }, "Ищу…"));
    try {
      const r = await lookup("mobs", q.value);
      put(found, h("div", { class: "muted small" }, T("найдено {0} из {1}", r.rows.length, r.total)),
        table([["id", x => x.id], ["Имя", x => x.name || "—"], ["Имя (корейское)", x => x.ko], ["Уровень", x => x.level], ["Опыт", x => x.exp],
          ["Строк дропа", x => x.drops]], r.rows, x => mobCard(card, target, x.id)));
    } catch (e) { put(found, errbox(e)); }
  };
  q.addEventListener("change", find);
  const tabMob = h("button", { type: "button" }, "Монстры"), tabMine = h("button", { type: "button", class: "ghost" }, "Копание");
  const pane = h("div");
  const showMob = () => { tabMob.className = ""; tabMine.className = "ghost"; put(pane, h("div", { class: "card" }, h("div", { class: "row" }, q,
    h("button", { type: "button", onclick: find }, "Найти")), found), card); };
  const showMine = () => { tabMob.className = "ghost"; tabMine.className = ""; put(pane, h("div", { class: "card" }, mine)); if (!mine.childNodes.length) mineCard(mine, target); };
  tabMob.addEventListener("click", showMob);
  tabMine.addEventListener("click", showMine);
  put(out, h("div", { class: "card" }, h("div", { class: "row" }, tabMob, tabMine, h("span", null, T("Набор")), target,
    can("data.edit") ? null : h("span", { class: "muted small" }, T("правка — с правом «data.edit»")))), pane);
  showMob();
}
