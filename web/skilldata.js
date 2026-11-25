// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Данные игры → Навыки и классы» (шаг А4.7, 20.11.2026; область domains/cs_kinds/skilldata.py):
// правка СУЩЕСТВУЮЩИХ записей — числа навыка (SkillInfo.sif +47…+116 ↔ skill_info клиента), макс. уровень и требование дерева
// (+43 / +190 ↔ skill_info), порог строки SkillPointTable.spt (только сервер), базовые характеристики класса (ClassStat.txt, только
// сервер), опыт начала уровня (ExpTable.txt ↔ charexp). Позиции уходят в набор изменений (проверка, держатели и суммы деревьев из Joy1,
// двойное подтверждение сильной правки, выкладка рестартом стойки, клиентская половина — консолью ПК). Общие помощники — из app.js и
// shops.js: h(), T(), put(), mount(), shell(), table(), kv(), sel(), numIn(), csRun(), shopsTabs(), lookup(), can(), notify(), errbox(),
// stale(), api().
"use strict";

function sdText(s) { return document.createTextNode(String(s)); }

async function sdAddAll(target, title, positions) {
  if (!positions.length) { notify(T("ни одно поле не изменено"), true); return; }
  let id = target.value, created = false;
  if (!id) {
    const x = await csRun("shop.cs_create", { title: title, note: T("правка навыков и классов"), order_mode: "together", urgent: false });
    if (!x || !x.result) return;
    id = x.result.id;
    created = true;
  }
  let done = 0;
  for (const [kind, params] of positions) {
    const r = await csRun("shop.cs_item_add", { cs: +id, kind, params });
    if (!r) {
      // ревизия 39 К-4: часть позиций уже в наборе (или набор создан пустым) — сказать прямо и открыть его, а не молча остаться
      if (done || created) {
        notify(T("в набор №{0} добавлено позиций {1} из {2}: следующая не добавлена (отказ или отмена), набор частичный — проверьте его, прежде чем проверять и утверждать",
                 id, done, positions.length), true);
        location.hash = "#/shops/set/" + id;
      }
      return;
    }
    done++;
  }
  location.hash = "#/shops/set/" + id;
}

function sdChanged(rows) {
  const f = {};
  rows.forEach(r => { if (r.inp && r.inp.value.trim() !== "" && +r.inp.value !== r.cur) f[r.key] = +r.inp.value; });
  return f;
}

async function sdSkillCard(box, target, sid) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let m;
  try { m = await lookup("skill", sid); } catch (e) { put(box, errbox(e)); return; }
  const mk = (arr) => arr.map(([key, label, off, lo, hi, cur, why]) => ({ key, label, off, cur, why, cli: m.client ? m.client[key] : null,
    inp: why ? null : numIn(cur, lo, hi) }));
  const num = mk(m.fields), req = mk(m.req);
  const hold = m.holders === null ? [T("не прочитано ({0})", m.holders_error || "—")]
    : (m.holders.length ? m.holders.slice(0, 30).map(x => T("{0} ({1}/{2}, ур. {3}), навык ур. {4}", x.name, x.uid, x.idx, x.lvl, x.slvl)) : [T("никто")]);
  if (m.holders && m.holders.length > 30) hold.push(T("и ещё {0}", m.holders.length - 30));
  const copies = Object.entries(m.copies).map(([g, v]) => g + ": " + T(v.same ? "как GameServer" : "отличается")).join(", ");
  const cols = [["Поле", r => T(r.label)], ["+", r => r.off], ["Сервер", r => r.cur], ["Клиент", r => r.cli === null || r.cli === undefined ? "—" : r.cli],
    ["Станет", r => r.inp || sdText(T(r.why || ""))]];
  const lv = ["mp", "ev", "sp", "ssp", "s1v", "s1t", "s2v", "s2t", "s3v", "s3t"];
  const lvLabel = { mp: "MP", ev: "сила", sp: "шанс навыка", ssp: "шанс эффекта", s1v: "эффект 1", s1t: "эффект 1, мс", s2v: "эффект 2", s2t: "эффект 2, мс", s3v: "эффект 3", s3t: "эффект 3, мс" };
  const collect = () => {
    const out = [];
    const a = sdChanged(num), b = sdChanged(req);
    if (Object.keys(a).length) out.push(["skill.num", { id: m.id, fields: a }]);
    if (Object.keys(b).length) out.push(["skill.req", { id: m.id, fields: b }]);
    return out;
  };
  const btn = can("data.edit") ? h("button", { type: "button", onclick: () => sdAddAll(target, T("Навык {0}", m.id), collect()) }, "Добавить в набор") : null;
  put(box,
    h("div", { class: "card" }, h("h2", null, sdText(T("Навык {0}", m.name))),
      kv([[T("Дерево / вид / пассив"), m.tree + " / " + m.kind + " / " + m.passive], [T("Маска классов (+123)"), m.mask],
        [T("Состояния эффектов 1–3 (+72/+89/+106)"), m.states.join(", ")],
        [T("Открывает (навык: на уровне)"), m.next.length ? m.next.map(x => x[0] + ": " + x[1]).join(", ") : "—"],
        [T("Предшественники (навык: уровень)"), m.prereq.length ? m.prereq.map(x => x[0] + ": " + x[1]).join(", ") : "—"],
        [T("Нужен другим (навык: уровень)"), m.users.length ? m.users.map(x => x[0] + ": " + x[1]).join(", ") : "—"],
        [T("Копии SkillInfo.sif"), sdText(copies)],
        [T("Клиент (skill_info)"), m.client ? T("запись есть ({0})", m.client_source) : T("записи нет")],
        [T("Изучили (Joy1)"), h("div", null, ...hold.map(x => h("div", null, sdText(x))))]]),
      h("div", { class: "note" }, sdText(T("Правка ложится на SkillInfo.sif всех GameServer и NpcServer (по значениям каждой копии, другое прежнее значение поля — отказ) и на skill_info клиента (ведомость _value_overlay/skill_info.sif.csv, DT_skill_info точечно). Изученный навык держит числа своего уровня в CharSkill: новые игрок получит при следующем повышении или сбросе. Макс. уровень ниже уровня держателя, ниже уровня открытия «следующего» и требование дерева 0 → больше 0 у изученного навыка — отказ. Изменение больше чем в 2 раза и смена требования дерева с 0 или на 0 — второе подтверждение владельца.")))),
    h("div", { class: "card" }, h("h3", null, "Числа уровня (база и шаг)"), table(cols, num)),
    h("div", { class: "card" }, h("h3", null, "Макс. уровень и требование дерева"), table(cols, req)),
    h("div", { class: "card" }, h("h3", null, "Значения по уровням (как считает сервер сейчас)"),
      table([["Ур.", r => r.lvl]].concat(lv.map(k => [lvLabel[k], r => r[k]])), m.levels), btn));
}

async function sdSpt(box, target) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let m;
  try { m = await lookup("spt", ""); } catch (e) { put(box, errbox(e)); return; }
  const rows = m.rows.map(r => Object.assign({}, r, { inp: numIn(r.sum, 1, 127) }));
  const btn = can("data.edit") ? h("button", { type: "button", onclick: () => sdAddAll(target, T("Пороги дерева"),
    rows.filter(r => r.inp.value.trim() !== "" && +r.inp.value !== r.sum).map(r => ["skill.spt", { row: r.row, sum: +r.inp.value }])) }, "Добавить в набор") : null;
  put(box, h("div", { class: "card" }, h("h3", null, "Пороги открытия навыков (SkillPointTable.spt, только сервер)"),
    h("div", { class: "note" }, sdText(T("Навыки строки выдаются, когда сумма уровней дерева станет РАВНА порогу. Сдвиг, после которого кто-то не получит навык или получит его снова уровнем 0, — отказ (суммы деревьев — по Joy1)."))),
    table([["Строка", r => r.row], ["Дерево", r => r.tree], ["Порог", r => r.sum], ["Навыки", r => sdText(r.skills.map(x => x[1]).join(", "))], ["Станет", r => r.inp]], rows), btn));
}

async function sdClass(box, target, cls) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let m;
  try { m = await lookup("classstat", cls); } catch (e) { put(box, errbox(e)); return; }
  const rows = m.rows.map(r => Object.assign({}, r, { inps: r.stats.map(v => numIn(v, 0, 32767)) }));
  const collect = () => {
    const out = [];
    rows.forEach(r => {
      const f = {};
      r.inps.forEach((x, i) => { if (x.value.trim() !== "" && +x.value !== r.stats[i]) f[m.stats[i][0]] = +x.value; });
      if (Object.keys(f).length) out.push(["class.stat", { cls: m.cls, lvl: r.lvl, fields: f }]);
    });
    return out;
  };
  const btn = can("data.edit") ? h("button", { type: "button", onclick: () => sdAddAll(target, T("Класс {0}", m.cls), collect()) }, "Добавить в набор") : null;
  put(box, h("div", { class: "card" }, h("h3", null, sdText(T("Класс {0} ({1}): базовые характеристики (ClassStat.txt, только сервер)", m.cls, T(m.name)))),
    h("div", { class: "note" }, sdText(T("Базу сервер берёт заново при каждом входе (ClassStat[класс][уровень]) и при повышении уровня."))),
    table([["Ур.", r => r.lvl]].concat(m.stats.map(([k, n], i) => [n, r => r.inps[i]])), rows), btn));
}

async function sdExp(box, target) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let m;
  try { m = await lookup("exptable", ""); } catch (e) { put(box, errbox(e)); return; }
  const rows = m.rows.map(r => Object.assign({}, r, { inp: r.lvl > 1 ? h("input", { class: "num", value: r.exp }) : null }));
  const btn = can("data.edit") ? h("button", { type: "button", onclick: () => sdAddAll(target, T("Опыт уровней"),
    rows.filter(r => r.inp && r.inp.value.trim() !== "" && r.inp.value.trim() !== String(r.exp)).map(r => ["level.exp", { lvl: r.lvl, exp: r.inp.value.trim() }])) }, "Добавить в набор") : null;
  put(box, h("div", { class: "card" }, h("h3", null, "Опыт начала уровня (ExpTable.txt + charexp клиента)"),
    h("div", { class: "note" }, sdText(T("Таблица строго растёт; персонаж уровня с опытом ниже нового порога — отказ. Клиент: строка charexp уровня − 1 (накопленный опыт) и «опыт до следующего» соседних строк."))),
    table([["Ур.", r => r.lvl], ["Сервер", r => r.exp], ["Клиент", r => r.client === null ? "—" : r.client], ["Станет", r => r.inp || "—"]], rows), btn));
}

async function viewSkillData(my) {
  const out = h("div");
  mount(shell("#/shops", h("h1", null, "Навыки и классы"), shopsTabs("#/shops/skills"), h("div", { class: "note" },
    sdText(T("Правка существующих навыков (пара: сервер — SkillInfo.sif всех GameServer и NpcServer, клиент — skill_info), порогов дерева, базовых характеристик классов и опыта уровней. Новых навыков, классов и уровней нет, номера не меняются. Позиция попадает в набор изменений, проверка показывает «было → станет» и кого это касается (Joy1), выкладка сервера — рестартом стойки с объявлением, клиент — консолью ПК и выпуском. После выкладки панель приводит Joy1.dbo.AsdaSkillBase к SkillInfo.sif."))), out));
  let sets = [];
  try { sets = (await api("/api/shops/sets")).items.filter(x => x.status === "draft" || x.status === "checked"); } catch (e) { sets = []; }
  if (stale(my)) return;
  const target = sel([["", T("новый набор")]].concat(sets.map(x => [x.id, "№" + x.id + " " + x.title])), sets.length ? sets[0].id : "");
  const q = h("input", { class: "wide", placeholder: "номер или часть названия навыка" });
  const found = h("div"), card = h("div");
  const find = async () => {
    put(found, h("div", { class: "muted small" }, "Ищу…"));
    try {
      const r = await lookup("skills", q.value);
      put(found, r.rows.length ? table([["Навык", x => x.id], ["Название", x => sdText(x.name)], ["Дерево", x => x.tree], ["Макс.", x => x.max],
        ["Нужно очков", x => x.need], ["MP", x => x.mp], ["Сила", x => x.ev], ["Откат, мс", x => x.cool]], r.rows, x => sdSkillCard(card, target, x.id))
        : h("div", { class: "muted small" }, sdText(T("ничего не найдено"))));
    } catch (e) { put(found, errbox(e)); }
  };
  q.addEventListener("change", find);
  const cls = sel([[0, T("новичок")], [1, T("боец")], [2, T("лучник")], [3, T("маг")]], 1);
  put(out, h("div", { class: "card" }, h("div", { class: "row" }, q, h("button", { type: "button", onclick: find }, "Найти"),
    h("span", null, sdText(T("Набор"))), target,
    can("data.edit") ? null : h("span", { class: "muted small" }, sdText(T("правка — с правом «data.edit»")))), found),
    h("div", { class: "card" }, h("div", { class: "row" },
      h("button", { type: "button", onclick: () => sdSpt(card, target) }, "Пороги дерева"),
      cls, h("button", { type: "button", onclick: () => sdClass(card, target, cls.value) }, "Характеристики класса"),
      h("button", { type: "button", onclick: () => sdExp(card, target) }, "Опыт уровней"))), card);
}
