// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Данные игры → Звания» (шаг А4.6, 20.11.2026; область domains/cs_kinds/titledata.py, пара сервер + клиент):
// правка СУЩЕСТВУЮЩИХ званий — включено (FameInfo кол. 1 ↔ title_list.Enabled), очки славы (кол. 42 ↔ Point), условия получения
// (кол. 3, 4, 43, 44 — только сервер, только поля, которые сервер читает для этого звания), бонусы характеристик (кол. 12+5m…14+5m ↔
// OptionTypeId). Позиции уходят в набор изменений (проверка, держатели из Joy1, двойное подтверждение сильной правки, выкладка рестартом
// стойки, клиентская половина — консолью ПК). Общие помощники — из app.js и shops.js: h(), T(), put(), mount(), shell(), table(), kv(),
// sel(), numIn(), csRun(), shopsTabs(), lookup(), can(), notify(), errbox(), stale(), api().
"use strict";

// готовый (уже переведённый) текст или имя из данных — узлом текста: h() прогнал бы его через T() второй раз (урок ревизии 37 К-4)
function tdText(s) { return document.createTextNode(String(s)); }

async function tdAddAll(target, title, positions) {
  if (!positions.length) { notify(T("ни одно поле не изменено"), true); return; }
  let id = target.value;
  if (!id) {
    const x = await csRun("shop.cs_create", { title: title, note: T("правка званий (сервер + клиент)"), order_mode: "together", urgent: false });
    if (!x || !x.result) return;
    id = x.result.id;
  }
  for (const [kind, params] of positions) {
    const r = await csRun("shop.cs_item_add", { cs: +id, kind, params });
    if (!r) return;
  }
  location.hash = "#/shops/set/" + id;
}

async function tdCard(box, target, tid) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let m;
  try { m = await lookup("title", tid); } catch (e) { put(box, errbox(e)); return; }
  const srv = m.server.GameServer;
  const others = (f) => Object.entries(m.server).filter(([g]) => g !== "GameServer").map(([g, v]) => g + ": " + (v.error ? T("нет записи") : f(v))).join(", ");
  const onSel = sel([[1, T("включено")], [0, T("выключено")]], srv.enabled ? 1 : 0);
  const pts = numIn(srv.points, 0, 32767);
  const cond = m.fields.map(([key, label, lo, hi, how, unsafe]) => ({ key, label, how, unsafe, cur: srv[key],
    inp: how && !unsafe ? numIn(srv[key], lo, hi) : null }));
  // ★ ревизия 38 К-2: имя характеристики — через T(), как в выпадающем списке (иначе в EN-интерфейсе столбец «Сервер» остаётся русским)
  const stat = (c) => c === -1 ? T("нет слота") : c === 0 ? T("пусто") : T((m.stats.find(x => x[0] === c) || [c, String(c)])[1]);
  // ★ ревизия 38 М-1: цель званий P88 задаёт patches.ini (порог по копиям; P88 выключен — порог там не действует)
  const p88 = m.p88 ? Object.entries(m.p88).map(([g, v]) => g + " " + v.thr + (v.on ? "" : " (" + T("P88 выключен") + ")")).join(", ")
    : (m.p88_error ? T("не прочитано ({0})", m.p88_error) : null);
  const bon = srv.bonus.map((b, slot) => ({ slot, b, code: sel([[-1, T("нет слота")], [0, T("пусто")]].concat(m.stats.map(([c, n]) => [c, T(n)])), b.code),
    lo: numIn(b.min, 0, 32767), hi: numIn(b.max, 0, 32767), cli: m.client ? m.client["OptionTypeId" + slot] : null }));
  const hold = m.holders === null ? [T("не прочитано ({0})", m.holders_error || "—")]
    : (m.holders.length ? m.holders.map(x => T("{0} ({1}/{2}, ур. {3}){4}", x.name, x.uid, x.idx, x.lvl, x.worn ? T(", надето") : "")) : [T("никто")]);
  const collect = () => {
    const out = [];
    if (+onSel.value !== (srv.enabled ? 1 : 0)) out.push(["title.enabled", { id: m.id, on: +onSel.value }]);
    if (pts.value.trim() !== "" && +pts.value !== srv.points) out.push(["title.points", { id: m.id, value: +pts.value }]);
    const f = {};
    cond.forEach(r => { if (r.inp && r.inp.value.trim() !== "" && +r.inp.value !== r.cur) f[r.key] = +r.inp.value; });
    if (Object.keys(f).length) out.push(["title.cond", { id: m.id, fields: f }]);
    bon.forEach(r => {
      const c = +r.code.value, lo = +r.lo.value, hi = +r.hi.value;
      if (c !== r.b.code || lo !== r.b.min || hi !== r.b.max) out.push(["title.bonus", { id: m.id, slot: r.slot, code: c, min: lo, max: hi }]);
    });
    return out;
  };
  const btn = can("data.edit") ? h("button", { type: "button", onclick: () => tdAddAll(target, T("Звание {0}", m.id), collect()) }, "Добавить в набор") : null;
  put(box,
    h("div", { class: "card" }, h("h2", null, tdText(T("Звание {0} «{1}»", m.id, m.name))),
      kv([[T("Копии FameInfo (3 GS) одинаковы"), T(m.copies_same ? "да" : "нет")],
        [T("Клиент (title_list)"), m.client ? T("запись есть ({0})", m.client_source) : T("записи нет")],
        [T("Очки в Joy1.dbo.AsdaFamePoints"), m.fame_points_db === null ? "—" : m.fame_points_db],
        [T("Набор (предпосылки / следующие)"), (srv.prereq.length ? srv.prereq.join(", ") : "—") + " / " + (srv.next.length ? srv.next.join(", ") : "—")],
        [T("Общий накопитель (кол. 45)"), srv.accum],
        [T("Выдаётся набором (записи, где оно «следующее»)"), m.set_sources && m.set_sources.length ? m.set_sources.join(", ") : "—"],
        ...(p88 !== null ? [[T("Порог P88 (patches.ini [P88_TitleEvents])"), tdText(p88)]] : []),
        [T("Держат сейчас (Joy1)"), h("div", null, ...hold.map(x => h("div", null, tdText(x))))]]),
      m.rating ? h("div", { class: "note" }, tdText(T("Рейтинговое звание: выдаёт и снимает P23 (держатель — FameRatingHolder), включённость не правится, условия сервер не читает."))) : null,
      h("div", { class: "note" }, tdText(T("Правка ложится на FameInfo.txt всех GameServer (у Indun своя база: правится по её значениям, другое прежнее значение поля — отказ) и на title_list клиента (ведомость _value_overlay/title_list.csv, DT_title_list точечно) — кроме условий: их у клиента нет, текст условия правится во вкладке «Тексты». Выключить звание, которое у кого-то есть, и сменить у такого звания код бонуса нельзя (держатель потерял бы строку в окне или увидел бы чужое имя бонуса); очки и условия у держателей — предупреждение со списком. Новых званий и номеров нет. Изменение больше чем в 2 раза, включённость, вид второй ступени и смена характеристики — второе подтверждение владельца.")))),
    h("div", { class: "card" }, h("h3", null, "Включено и очки славы"),
      table([["Поле", r => T(r[0])], ["Сервер", r => r[1]], ["Другие GS", r => r[2] || "—"], ["Клиент", r => r[3] === null || r[3] === undefined ? "—" : r[3]], ["Станет", r => r[4]]],
        [["включено", srv.enabled, others(v => v.enabled), m.client ? m.client.Enabled : null, onSel],
         ["очки славы", srv.points, others(v => v.points), m.client ? m.client.Point : null, pts]])),
    h("div", { class: "card" }, h("h3", null, "Условия получения (только сервер)"),
      table([["Поле", r => T(r.label)], ["Сервер", r => r.cur], ["Другие GS", r => others(v => v[r.key]) || "—"],
        ["Как читает сервер", r => tdText(r.unsafe ? T(r.unsafe) : (r.how ? T(r.how) : T("не читает для этого звания")))], ["Станет", r => r.inp || "—"]], cond)),
    h("div", { class: "card" }, h("h3", null, "Бонусы характеристик (% от базы)"),
      table([["Слот", r => r.slot], ["Сервер", r => tdText(stat(r.b.code) + " " + r.b.min + "…" + r.b.max)], ["Второе значение (не применяется)", r => r.b.v2.join("…")],
        ["Клиент OptionTypeId", r => r.cli === null || r.cli === undefined ? "—" : r.cli], ["Характеристика", r => r.code], ["Мин.", r => r.lo], ["Макс.", r => r.hi]], bon), btn));
}

async function viewTitleData(my) {
  const out = h("div");
  mount(shell("#/shops", h("h1", null, "Звания"), shopsTabs("#/shops/titles"), h("div", { class: "note" },
    tdText(T("Правка существующих званий (пара: сервер — FameInfo.txt всех GameServer, клиент — title_list): включено, очки славы, условия получения и бонусы характеристик. Позиция попадает в набор изменений, проверка показывает «было → станет» и кто держит звание сейчас, выкладка сервера — рестартом стойки с объявлением, клиент — консолью ПК и выпуском. После выкладки панель приводит Joy1.dbo.AsdaFamePoints к FameInfo.txt."))), out));
  let sets = [];
  try { sets = (await api("/api/shops/sets")).items.filter(x => x.status === "draft" || x.status === "checked"); } catch (e) { sets = []; }
  if (stale(my)) return;
  const target = sel([["", T("новый набор")]].concat(sets.map(x => [x.id, "№" + x.id + " " + x.title])), sets.length ? sets[0].id : "");
  const q = h("input", { class: "wide", placeholder: "номер или часть названия звания" });
  const found = h("div"), card = h("div");
  const find = async () => {
    put(found, h("div", { class: "muted small" }, "Ищу…"));
    try {
      const r = await lookup("titles", q.value);
      put(found, r.rows.length ? table([["Звание", x => x.id], ["Название", x => tdText(x.name)], ["Включено", x => x.enabled ? T("да") : T("нет")],
        ["Очки", x => x.points], ["Цель", x => x.target]], r.rows, x => tdCard(card, target, x.id)) : h("div", { class: "muted small" }, tdText(T("ничего не найдено"))));
    } catch (e) { put(found, errbox(e)); }
  };
  q.addEventListener("change", find);
  put(out, h("div", { class: "card" }, h("div", { class: "row" }, q, h("button", { type: "button", onclick: find }, "Найти"),
    h("span", null, tdText(T("Набор"))), target,
    can("data.edit") ? null : h("span", { class: "muted small" }, tdText(T("правка — с правом «data.edit»")))), found), card);
}
