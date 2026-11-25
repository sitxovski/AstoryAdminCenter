// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Данные игры → Карты» (шаг А4.8, 20.11.2026; область domains/cs_kinds/mapdata.py):
// правка СУЩЕСТВУЮЩИХ записей — цена телепорта кристаллом (MapWarpCost.txt [откуда][куда] во всех GameServer, только сервер; −1 — запрет)
// и «карта открыта» (OpenMapInfo.ini MAP_<n> Use в копиях поля GameServer и Ch2_GameServer; зеркало — реестр карт порта). Остальное — на
// чтение: MapInfo (тип, группа города, точки входа/возврата), зоны переходов, прибытие кристалла (Total_PortalConfig), кристаллы и их
// подписи, персонажи на карте (Joy1). Позиции уходят в набор изменений (проверка, двойное подтверждение сильной правки, выкладка рестартом
// стойки). Общие помощники — из app.js, shops.js и skilldata.js: h(), T(), put(), mount(), shell(), table(), kv(), sel(), numIn(), csRun(),
// shopsTabs(), lookup(), can(), notify(), errbox(), stale(), api(), sdText(), sdAddAll().
"use strict";

function mdCopies(obj) {
  return Object.entries(obj || {}).map(([g, v]) => g + ": " + (v === null || v === undefined ? "—" : v)).join(", ");
}

async function mdMapCard(box, target, mid) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let m;
  try { m = await lookup("map", mid); } catch (e) { put(box, errbox(e)); return; }
  const rows = m.warp_row.map(r => Object.assign({}, r, { cur: r.cost.GameServer, inp: numIn(r.cost.GameServer, -1, 2000000000) }));
  const collect = () => rows.filter(r => r.inp.value.trim() !== "" && +r.inp.value !== r.cur)
    .map(r => ["warp.cost", { from: m.id, to: r.to, cost: +r.inp.value }]);
  const btn = can("data.edit") ? h("button", { type: "button", onclick: () => sdAddAll(target, T("Цены телепорта с карты {0}", m.name), collect()) },
    "Добавить в набор") : null;
  const hold = (m.holders === null ? [T("не прочитано ({0})", m.holders_error || "—")]
    : (m.holders.length ? m.holders.slice(0, 30).map(x => x.name + " (" + x.u + "/" + x.c + ", " + x.where + ")") : [T("никто")]))
    .concat(m.holders_notes || []);   // ревизия 40 В-2: Charinpos (19/20/22) и перенос P108 — в списке; нет таблицы P108 — пометка
  const crys = m.crystals === null ? T("не прочитано") : (m.crystals.length
    ? m.crystals.map(c => T("NPC {0} ({1},{2}) → карты {3}", c.type, c.x, c.z, c.to.join(", "))).join("; ") : T("нет"));
  put(box,
    h("div", { class: "card" }, h("h2", null, sdText(T("Карта {0} ({1})", m.name, m.id))),
      kv([[T("Тип (+63)"), sdText(m.type + " — " + T(m.type_name))], [T("Лимит игроков (+56)"), m.users], [T("Город (+62) / группа (+130)"), m.town + " / " + m.group],
        [T("Открыта (Use, копии поля)"), sdText(mdCopies(m.use))], [T("Реестр карт порта (open_use)"), m.registry === null ? "—" : m.registry],
        [T("Прибытие кристалла (Total_PortalConfig)"), m.total ? sdText("USE " + m.total.use + ", " + m.total.x + "," + m.total.z) : "—"],
        [T("Точки входа/возврата (+98/+108)"), m.points.length ? m.points.map(p => p[0] + "," + p[1]).join("; ") : "—"],
        [T("Кристаллы на карте (P40 Crystals)"), sdText(crys)],
        [T("Стоят или возрождаются здесь (Joy1)"), h("div", null, ...hold.map(x => h("div", null, sdText(x))))]])),
    h("div", { class: "card" }, h("h3", null, "Зоны переходов с этой карты (PortalIP_Info, только чтение)"),
      table([["Зона", z => z.k], ["Куда", z => sdText(z.to_name)], ["Прямоугольник", z => z.x0 + "," + z.z0 + " … " + z.x1 + "," + z.z1],
        ["Прибытие", z => z.ax + "," + z.az], ["INDUN", z => z.indun]], m.zones)),
    h("div", { class: "card" }, h("h3", null, "Входы на эту карту (зоны других карт)"),
      table([["Откуда", z => sdText(z.frm_name)], ["Зона", z => z.k], ["Прибытие", z => z.ax + "," + z.az]], m.inbound)),
    h("div", { class: "card" }, h("h3", null, "Подписи кнопок кристаллов (клиент, только чтение)"),
      table([["NSR", c => c.nsr], ["Кнопка", c => c.btn], ["Подпись", c => sdText(c.caption)], ["Куда", c => sdText(c.to_name)]], m.captions)),
    h("div", { class: "card" }, h("h3", null, "Цены телепорта кристаллом с этой карты (MapWarpCost.txt, только сервер)"),
      h("div", { class: "note" }, sdText(T("−1 — переход запрещён (сервер молчит), 0 — бесплатно. Правка ложится на все GameServer по их числу (у Indun своя база — другое прежнее значение ячейки — отказ). Маршрут без кристалла при P40 — отказ «не подействует». Изменение больше чем в 2 раза и «запрещён ↔ разрешён» — второе подтверждение владельца. Подписи кнопок кристаллов клиент не пересчитывает."))),
      table([["Куда", r => sdText(r.to_name)], ["GameServer", r => r.cost.GameServer], ["Indun", r => r.cost.Indun_GameServer],
        ["Ch2", r => r.cost.Ch2_GameServer], ["Станет", r => r.inp]], rows), btn));
}

async function viewMapData(my) {
  const out = h("div");
  mount(shell("#/shops", h("h1", null, "Карты"), shopsTabs("#/shops/maps"), h("div", { class: "note" },
    sdText(T("Цены телепорта кристаллом (MapWarpCost.txt всех GameServer) и открытые карты (OpenMapInfo.ini копий поля). Только существующие записи; точки прибытия, зоны переходов и MapInfo — на чтение. Позиция попадает в набор изменений: проверка показывает «было → станет», кого это касается (Joy1) и хватит ли потоков (ThreadInfo), выкладка — рестартом стойки с объявлением. Реестр карт порта (маршруты трекера) — клиентской половиной, не обязательна для сервера."))), out));
  let sets = [];
  try { sets = (await api("/api/shops/sets")).items.filter(x => x.status === "draft" || x.status === "checked"); } catch (e) { sets = []; }
  if (stale(my)) return;
  const target = sel([["", T("новый набор")]].concat(sets.map(x => [x.id, "№" + x.id + " " + x.title])), sets.length ? sets[0].id : "");
  const card = h("div");
  let r;
  try { r = await lookup("maps", ""); } catch (e) { put(out, errbox(e)); return; }
  if (stale(my)) return;
  const rows = r.rows.map(x => Object.assign({}, x, { cur: x.use.GameServer, inp: x.editable && x.use.GameServer !== null && x.use.GameServer !== undefined
    ? sel([[1, T("открыта")], [0, T("закрыта")]], x.use.GameServer) : null }));
  const collect = () => rows.filter(x => x.inp && +x.inp.value !== x.cur).map(x => ["map.open", { map: x.id, use: +x.inp.value }]);
  const btn = can("data.edit") ? h("button", { type: "button", onclick: () => sdAddAll(target, T("Открытые карты"), collect()) }, "Добавить в набор") : null;
  const thr = Object.keys(r.threads || {}).map(g => T("{0}: открыто {1}, потоков (ThreadInfo COUNT) {2}", g, r.opened[g], r.threads[g])).join("; ");
  put(out, h("div", { class: "card" }, h("div", { class: "row" }, h("span", null, sdText(T("Набор"))), target,
      can("data.edit") ? null : h("span", { class: "muted small" }, sdText(T("правка — с правом «data.edit»")))),
    h("div", { class: "muted small" }, sdText(thr)), r.cfg_error ? errbox(new Error(T("patches.ini не прочитан ({0})", r.cfg_error))) : null,
    // ревизия 40: установка патчей по журналу запуска (С-2) и таблицы, которые не прочитаны (справка частично, мелочь 6) — уже переведены службой
    ...(r.patch_notes || []).concat(r.read_errors || []).map(x => h("div", { class: "muted small" }, sdText(x))),
    table([["Карта", x => x.id], ["Имя", x => sdText(x.name)], ["Тип", x => sdText(x.type + " " + T(x.type_name))], ["Группа", x => x.group],
      ["Use (поле)", x => sdText(mdCopies(x.use))], ["Реестр порта", x => x.registry === null ? "—" : x.registry],
      ["Прибытие кристалла", x => x.total ? x.total.x + "," + x.total.z : "—"],
      ["Станет", x => x.inp || sdText(T("не правится (тип)"))]], rows, x => mdMapCard(card, target, x.id)), btn), card);
}
