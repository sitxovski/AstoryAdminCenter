// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — раздел «Данные игры → Магазины» (волна А3, 19.11.2026; А4.0/А4.1 — реестр видов: витрина 6800, магазин чести, парикмахерская): наборы изменений (черновик → проверка → утверждение →
// сухие прогоны → применение половин консолью ПК), редакторы позиций (премиум 6000, цена, белый список, лавки NPC, бустеры, наборы,
// гача), предпросмотр «было → станет», экран расхождений сервер/клиент. Данные — только через API (/api/shops/*, /api/ops/shop.*).
// Общие помощники — из app.js: h(), T(), put(), mount(), shell(), table(), kv(), badge(), notify(), confirmWin(), op(), can(), sel().
"use strict";
const CS_STATUS = { draft: "черновик", checked: "проверен", approved: "утверждён", applied_server: "сервер выложен",
  applied_client: "клиент в RawAssets/DT", released: "выпущен с клиентом", rolled_back: "отменён / откачен" };
const CS_HALF = { none: "—", dry_srv: "база сверена службой (выкладчик не прогонялся)", dry_ok: "сухой прогон пройден", applying: "запись начата (не завершена)",
  applied: "применено", partial: "применено частично", partial_apply: "выложено частично", partial_rollback: "откачено частично",
  unknown: "не прочитано после рестарта (server-sync)", rolled_back: "откачено" };
const CS_ORDER = { together: "вместе (к выпуску клиента)", client_first: "сначала клиент", server_first: "сначала сервер (только срочное)" };
const csBadge = s => badge(T(CS_STATUS[s] || s), { approved: "ok", checked: "ok", released: "ok", draft: "warn", rolled_back: "bad" }[s] || "");

async function csRun(name, params, after) {
  let p;
  try { p = await op(name, params, true); } catch (e) { notify(e.message, true); return false; }
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv" }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note" }, T(w))),
    h("div", { class: "muted small" }, "Шаг попадёт в журнал действий (цель changeset:№).")])) return false;
  try {
    const x = await op(name, params, false);
    notify(T(x.message || "готово"));
    if (after) after(x);
    return x;
  } catch (e) { notify(e.message, true); return false; }
}

function shopsTabs(active) {
  const t = (href, label) => h("a", { href, class: active === href ? "on" : "" }, label);
  return h("div", { class: "tabs" }, t("#/shops", "Наборы изменений"), t("#/shops/diverge", "Расхождения сервер / клиент"),
    can("data.view") ? t("#/shops/texts", "Тексты") : null,                        // ★ А4.2: «Данные игры → Тексты»
    can("data.view") ? t("#/shops/monsters", "Монстры и добыча") : null,           // ★ А4.3: web/monsters.js
    can("data.view") ? t("#/shops/items", "Предметы") : null,                      // ★ А4.4: web/itemdata.js
    can("data.view") ? t("#/shops/quests", "Задания") : null,                      // ★ А4.5: web/questdata.js
    can("data.view") ? t("#/shops/titles", "Звания") : null,                       // ★ А4.6: web/titledata.js
    can("data.view") ? t("#/shops/skills", "Навыки и классы") : null,              // ★ А4.7: web/skilldata.js
    can("data.view") ? t("#/shops/maps", "Карты") : null,                          // ★ А4.8: web/mapdata.js
    can("patchcfg.view") ? t("#/shops/patches", "Настройки патчей") : null);       // ★ А5.5: web/patchcfg.js
}

async function viewShops(sub, id) {
  const my = S.nav;
  if (sub === "diverge") return viewShopsDiverge(my);
  if (sub === "set") return viewShopSet(my, id);
  if (sub === "texts") return viewTexts(my);
  if (sub === "monsters") return viewMonsters(my);                                // ★ А4.3
  if (sub === "items") return viewItemData(my);                                   // ★ А4.4
  if (sub === "quests") return viewQuestData(my);                                 // ★ А4.5
  if (sub === "titles") return viewTitleData(my);                                 // ★ А4.6
  if (sub === "skills") return viewSkillData(my);                                 // ★ А4.7
  if (sub === "maps") return viewMapData(my);                                     // ★ А4.8
  if (sub === "patches") return viewPatchCfg(my);                                 // ★ А5.5
  const out = h("div", null, h("div", { class: "muted" }, "Загружаю…"));
  mount(shell("#/shops", h("h1", null, "Магазины"), shopsTabs("#/shops"), out));
  let r;
  try { r = await api("/api/shops/sets"); } catch (e) { if (!stale(my)) put(out, errbox(e)); return; }
  if (stale(my)) return;
  const create = async () => {
    const title = h("input", { class: "wide", placeholder: "что меняем и зачем" });
    const note = h("input", { class: "wide", placeholder: "причина (пойдёт в changelog)" });
    const order = sel(Object.entries(CS_ORDER).map(([k, v]) => [k, T(v)]), "together");
    const urg = h("input", { type: "checkbox" });
    if (!await confirmWin(T("Новый набор изменений"), [h("div", { class: "kv edit" }, h("div", null, "Заголовок"), title, h("div", null, "Причина"), note,
      h("div", null, "Порядок половин"), order, h("div", null, "Срочно, только сервер"), h("label", { class: "row" }, urg,
        h("span", { class: "muted small" }, "только запрет продажи и веса бустеров (решение владельца 19.11)")))], T("Создать"))) return;
    const x = await csRun("shop.cs_create", { title: title.value, note: note.value, order_mode: order.value, urgent: urg.checked });
    if (x && x.result) location.hash = "#/shops/set/" + x.result.id;
  };
  put(out, h("div", { class: "card" },
    h("div", { class: "row" }, can("shop.edit") ? h("button", { type: "button", onclick: create }, "Новый набор") : null,
      h("span", { class: "muted small" }, r.on_server ? T("служба на сервере: применение половин — консолью на ПК владельца") : T("служба на ПК"))),
    table([["№", x => x.id], ["Заголовок", x => x.title], ["Статус", x => csBadge(x.status)], ["Сервер", x => T(CS_HALF[x.server_state])],
      ["Клиент", x => T(CS_HALF[x.client_state])], ["Позиций", x => x.n], ["Автор", x => x.author], ["Изменён", x => dt(x.updated_at)]],
      r.items, x => { location.hash = "#/shops/set/" + x.id; })));
}

// ---------- набор ----------
const KIND_HELP = {
  "price": "Цена — одно поле сервера item_table ток.26 на все магазины (GXP премиума и золото лавки). Серверная половина — 3 GS, клиентская — item_list.Price + DataHex.",
  "sell.allow": "Белый список покупки SellItemTable во всех GS. Новый код — сервер после клиента.",
  "sell.deny": "Убрать из белого списка. Допускается «срочно, только сервер»: карточка видна, покупка отказывает без списания.",
  "shop6000.add": "Строка витрины 6000 (хвост панели PremiumShopBin_tail_panel.json). Код обязан быть в SellItemTable, цена клиента = ток.26.",
  "npcshop.add": "Лавка NPC: вернуть скрытый товар или дописать код в js<npc>.spd. Сервер проверяет ShopBuyFlag (ток.38). Предмет премиум-витрины — нельзя.",
  "npcshop.hide": "Лавка NPC: строка в npc_shop_hidden.csv (витрина клиента), сервер не меняется.",
  "booster.weights": "Строка GachaItemRateTable (позиция = ток.39). 35 пар «код, вес». Веса клиент не читает; смена кодов — нужен выпуск («Вид»).",
  "package.set": "Строка PackageItem_Table (5 пар). Стопка ≤ 32 767 по количеству и весу, нестопочный — по штуке в паре, вес набора ≤ 5 000.",
  "gacha.price": "Цена автомата: PrimiumGaChaPriceTable + premium_gatya_data. Число автоматов не меняется.",
  "gacha.pool": "Пул автомата PrimiumGaChaTable: строки «код количество». Шанс — равномерно по строкам (выбирает шлюз gp7).",
  // А4.1 19.11: данные игры — только правка существующих записей
  "equipshop.set": "Витрина 6800 (Freeshop.she, только клиент): заменить код на том же месте — порядок кодов = страница и слот. Сервер проверяет ShopBuyFlag (ток.38); предмет премиум-витрины — нельзя. Цена — позицией «Цена».",
  "honor.price": "Магазин чести: строка = StorePos, правка на месте во всех GS (у Indun — своей базой) и в Honor_price_table.bin. Монеты славы и требуемое воинское звание.",
  "honor.item": "Магазин чести: заменить товар строки (сервер сверяет код строки с кодом клиента — пара по позиции). Замена — сильная правка баланса.",
  "text.set": "Тексты RU / EN (только клиент, только правка существующих): RU и EN правятся одной позицией; пустое поле с отметкой «не менять» — язык не меняется. Пишется в ведомости (рецепт имён, _value_overlay, ru_dt_overrides, loc/en) — перегенерация правку не сотрёт.",
  // А4.3 20.11: монстры и добыча — только сервер, только правка существующих (редактор — вкладка «Монстры и добыча»)
  "mob.drop": "Основной дроп моба (Monster.ai +174, до 20 строк «код, rate из 100 000, количество»): шанс строки (rate+1)/100 000, каждая строка бросается отдельно. Все 6 копий Monster.ai; у Indun — своя база.",
  "mob.money": "Деньги моба (+169…+173): минимум, максимум, шанс из 100.",
  "mob.world": "Мировой дроп моба: запись WorldDropItem.itm (+394), сколько раз (+396), гейт из 100 000 (+398).",
  "mob.qdrop": "Квестовый дроп моба (+402 гейт, +403 строки): только предмет и шанс существующих строк; задание и шаг не правятся. DT_MobQuestDrop порта игрой не читается.",
  "mob.exp": "Опыт моба (Monster.ai +0x35) во всех 6 копиях.",
  "mine.drop": "Копание (NpcServer MiningItemTable): таблица добычи карты и типа — одинаково во все сектора файла; пороги накопительные из 100 000.",
  "hair.price": "Парикмахерская: цена причёски — HairTypeTable во всех GS + hairtable.csv и ведомость _value_overlay/hairtable.csv. Деньги списывает сервер, витрину рисует клиент.",
  // А4.4 20.11: предметы — пара сервер + клиент, только правка существующих (редактор — вкладка «Предметы»)
  "item.set": "Поля карточки предмета: прочность, вес, мин. и макс. уровень, требование класса, стопка — item_table во всех GS + item_list.csv и ведомость _value_overlay/item_list.csv. Стопка у предмета на руках, вес стопки сверх 32 767 — отказ.",
  "gem.level": "Минимальный уровень самоцвета: Cellob_Table во всех GS + sowell_list.csv и ведомость _value_overlay/sowell_list.csv.",
  // А4.5 20.11: задания — пара сервер + клиент, только правка существующих (редактор — вкладка «Задания»)
  "quest.reward": "Награда задания: золото, опыт, предметы A1, A2, B1 — RepayTable во всех GS (у Indun своя база) + RewardTable.BIN клиента, QuestRewardTable.json и DT_QuestRewardTable. Нестопочный предмет или самоцвет с количеством больше 1 — отказ.",
  "board.quest": "Задание доски объявлений: мин. и макс. уровень, лимит раз, опыт, золото — LimitationQuest (12 копий GS и NpcServer) + ведомость board_quest_values.json, RaidQuestData.json и DT_RaidQuestData.",
  // А4.6 20.11: звания — пара сервер + клиент, только правка существующих (редактор — вкладка «Звания»)
  "title.points": "Очки славы звания: FameInfo.txt кол. 42 во всех GS + title_list.Point (ведомость _value_overlay/title_list.csv). Слава держателей пересчитается при входе; после выкладки панель приводит Joy1.dbo.AsdaFamePoints к FameInfo.",
  "title.enabled": "Включено ли звание: FameInfo.txt кол. 1 во всех GS + title_list.Enabled. Выключить звание, которое у кого-то есть, — отказ (клиент скрыл бы строку); звание, которое выдаёт набор (оно «следующее» в кол. 10/11 другой записи), выключить тоже нельзя — каскад sub_54A610 выдал бы его скрытым. Рейтинговые 65–69 — не правятся.",
  // А4.7 20.11: навыки и классы (редактор — вкладка «Навыки и классы»)
  "skill.num": "Числа навыка: откат, дальность, область, расход MP, сила, шансы, значения и длительности эффектов (база и шаг на уровень) — SkillInfo.sif во всех GameServer и NpcServer + skill_info.csv и ведомость _value_overlay/skill_info.sif.csv. Изученный навык держит прежние числа до повышения или сброса.",
  "skill.req": "Макс. уровень и требование дерева навыка — SkillInfo.sif +43 / +190 во всех GameServer и NpcServer + skill_info клиента. Максимум ниже уровня держателя и требование 0 → больше 0 у изученного навыка — отказ. Держатели — и невосстановленная корзина удалённых; требование 0 → больше 0 у навыка, который сервер выдаёт сам (ChangeJobAddSkillTable, шаблоны Fighter / Ranger / Mage), и больше 0 → 0 у навыка строки SkillPointTable — отказ. Перед выкладкой и после остановки стойки всё перечитывается; откат, который по живым данным уже не проходит, — только вторым подтверждением владельца (--held-ok).",
  "skill.spt": "Порог строки SkillPointTable.spt (только сервер): навыки строки выдаются, когда сумма дерева станет РАВНА порогу. Сдвиг, после которого кто-то не получит навык или получит его снова уровнем 0, — отказ. Суммы деревьев — и у невосстановленной корзины удалённых; откат, который по живым данным уже не проходит, — только вторым подтверждением владельца (--held-ok).",
  "class.stat": "Базовые характеристики класса на уровне — ClassStat.txt во всех GameServer (только сервер; база берётся заново при входе).",
  "level.exp": "Накопленный опыт начала уровня — ExpTable.txt во всех GameServer + charexp.csv и ведомость _value_overlay/charexp.csv. Таблица строго растёт; персонаж уровня с опытом ниже нового порога — отказ (и в невосстановленной корзине удалённых); откат, который по живым данным уже не проходит, — только вторым подтверждением владельца (--held-ok).",
  // ★ А4.8 20.11: «Карты» (web/mapdata.js)
  "warp.cost": "Цена телепорта кристаллом [откуда][куда] — MapWarpCost.txt во всех GameServer (только сервер; у Indun своя база — другое прежнее число ячейки — отказ). −1 — переход запрещён, 0 — бесплатно. Маршрут без NPC-кристалла с этой картой в P40 Crystals — отказ «не подействует». Подписи кнопок кристаллов клиент не пересчитывает (предупреждение).",
  "map.open": "Карта открыта — OpenMapInfo.ini MAP_<n> Use в копиях поля (GameServer, Ch2_GameServer; у Indun файла нет). Только типы 0/1/3 (6 — при P120). Открытых больше ThreadInfo COUNT — отказ (сервер не стартует). Закрытие карты, на которой стоят или возрождаются персонажи (и в невосстановленной корзине), — отказ; перед выкладкой и откатом — перепроверка. Реестр карт порта — клиентской половиной (необязательной).",
  "title.cond": "Условия получения: цель (кол. 3), параметр (кол. 4), вид и порог второй ступени (кол. 43, 44) — только сервер, только поля, которые сервер читает для этого звания (ветки sub_54B260).",
  "title.bonus": "Бонус характеристики слота 0–5: код (65–71 — Сила, Выносливость, Интеллект, Энергия, Ловкость, Удача, Все; −1 — нет слота, 0 — пусто), разброс % от базы — FameInfo во всех GS + title_list.OptionTypeId. Смена кода у звания с держателями — отказ.",
};

async function lookup(what, id) { return api("/api/shops/lookup?what=" + encodeURIComponent(what) + "&id=" + encodeURIComponent(id)); }

function pairsEditor(n, pairs, label2) {
  const rows = [];
  const box = h("div", { class: "picklist", style: { maxHeight: "360px" } });
  for (let i = 0; i < n; i++) {
    const c = numIn(pairs[i] ? pairs[i][0] : 0, 0, 100000), w = numIn(pairs[i] ? pairs[i][1] : 0, 0, 2000000000);
    rows.push([c, w]);
    box.append(h("div", { class: "row" }, h("span", { class: "muted mono" }, String(i)), c, h("span", { class: "muted small" }, label2), w));
  }
  return { el: box, get: () => rows.map(([c, w]) => [+c.value || 0, +w.value || 0]).filter(x => x[0] > 0) };
}

async function addItemWin(cs, after) {
  const kinds = cs._kinds.filter(k => k.can !== false);
  const kindSel = sel(kinds.map(k => [k.id, T(k.area_title || "Магазины") + " · " + T(k.title)]), kinds[0].id);
  const form = h("div"), info = h("div", { class: "muted small" }), help = h("div", { class: "note" });
  let getParams = () => ({});
  const field = (label, el) => [h("div", null, label), el];
  const codeInfo = async (code) => {
    if (!code) return;
    try {
      const r = await lookup("code", code);
      const s = r.server, c = r.client;
      put(info, itemLine(r.code, r.name, r.icon), kv([[T("Сервер: цена ток.26"), s.price], [T("ShopBuyFlag ток.38"), s.shop_flag],
        [T("SellItemTable"), Object.entries(s.sell).map(([g, v]) => g + ": " + (v ? T("да") : T("нет"))).join(", ")],
        [T("Клиент: цена"), c.price], [T("Витрина 6000"), c.p6000 ? T("категория {0} / {1}", c.p6000.cat, c.p6000.sub1) : (c.panel_tail ? T("хвост панели") : T("нет"))],
        [T("Витрина 15300"), c.b15300 ? T("да") : T("нет")], [T("Лавки NPC"), c.npc.join(", ") || "—"],
        [T("Карта шлюза"), s.map ? JSON.stringify(s.map) : "—"]]));
    } catch (e) { put(info, errbox(e)); }
  };
  const show = async () => {
    const k = kindSel.value;
    put(help, T(KIND_HELP[k] || ""));
    put(info);
    if (k === "price" || k === "sell.allow" || k === "sell.deny") {
      const code = numIn("", 1, 100000), val = numIn("", 0, 2000000000);
      code.addEventListener("change", () => codeInfo(code.value));
      put(form, h("div", { class: "kv edit" }, field("Код", code), k === "price" ? field("Новая цена", val) : null));
      getParams = () => k === "price" ? { code: code.value, value: val.value } : { code: code.value };
    } else if (k === "shop6000.add") {
      const code = numIn("", 1, 100000), sub2 = numIn(-1, -1, 255), nf = numIn(0, 0, 255);
      const cats = (await lookup("cats6000", 0)).cats;
      const cat = sel(cats.map(c => [c.cat + "/" + c.sub1, T("категория {0} / {1} ({2} поз.)", c.cat, c.sub1, c.n)]), cats.length ? cats[0].cat + "/" + cats[0].sub1 : "");
      code.addEventListener("change", () => codeInfo(code.value));
      put(form, h("div", { class: "kv edit" }, field("Код", code), field("Категория / подкатегория", cat), field("Sub2", sub2), field("Метка NewFlag", nf)));
      getParams = () => { const [c, s1] = cat.value.split("/"); return { code: code.value, cat: c, sub1: s1, sub2: sub2.value, newflag: nf.value }; };
    } else if (k === "npcshop.add" || k === "npcshop.hide") {
      const npc = numIn(1, 1, 1000000), code = numIn("", 1, 100000), reason = h("input", { class: "wide", placeholder: "почему скрываем" });
      const shopBox = h("div", { class: "muted small" });
      const loadNpc = async () => { try { const r = await lookup("npc", npc.value);
        put(shopBox, T("в витрине {0}, скрыто {1}; лавки: {2}", r.shown.length, r.hidden.length, r.npcs.join(", ")),
          h("div", { class: "picklist" }, (k === "npcshop.hide" ? r.shown : r.hidden).map(it => h("div", { class: "pick", onclick: () => { code.value = it.code; codeInfo(it.code); } },
            itemLine(it.code, it.name, it.icon))))); } catch (e) { put(shopBox, errbox(e)); } };
      npc.addEventListener("change", loadNpc);
      code.addEventListener("change", () => codeInfo(code.value));
      put(form, h("div", { class: "kv edit" }, field("NPC (js<npc>.spd)", npc), field("Код", code), k === "npcshop.hide" ? field("Причина", reason) : null), shopBox);
      loadNpc();
      getParams = () => k === "npcshop.hide" ? { npc: npc.value, code: code.value, reason: reason.value } : { npc: npc.value, code: code.value };
    } else if (k === "booster.weights" || k === "package.set") {
      const isB = k === "booster.weights";
      const row = numIn(isB ? 1 : 0, 0, 1000000);
      const holder = h("div");
      let ed = pairsEditor(isB ? 35 : 5, [], isB ? T("вес") : T("кол-во"));
      put(holder, ed.el);
      const load = async () => {
        try {
          const r = await lookup(isB ? "booster" : "package", row.value);
          ed = pairsEditor(isB ? 35 : 5, r.server, isB ? T("вес") : T("кол-во"));
          put(holder, h("div", { class: "muted small" }, T("использует: {0}", r.users.map(u => u.name + " (" + u.code + ")").join(", ") || "—")),
            isB ? h("div", { class: "muted small" }, T("сейчас: мимо {0} %, особые 0–4: {1} %", (r.odds.miss * 100).toFixed(4), (r.odds.special * 100).toFixed(3))) : null,
            ed.el);
        } catch (e) { put(holder, errbox(e)); }
      };
      row.addEventListener("change", load);
      put(form, h("div", { class: "kv edit" }, field(isB ? "Строка GachaItemRateTable" : "Строка PackageItem_Table", h("div", { class: "row" }, row,
        h("button", { type: "button", class: "ghost", onclick: load }, "Загрузить")))), holder);
      getParams = () => ({ row: row.value, pairs: ed.get() });
    } else if (k === "gacha.price" || k === "gacha.pool") {
      const slot = sel([0, 1, 2, 3, 4].map(i => [i, T("автомат {0}", i + 1)]), 0), val = numIn("", 1, 2000000000);
      const ta = h("textarea", { rows: 10, class: "wide mono", placeholder: "код количество — по строке" });
      const sInfo = h("div", { class: "muted small" });
      const load = async () => { try { const r = await lookup("gacha", slot.value);
        put(sInfo, T("цена сервер {0}, клиент {1}; строк пула {2}", r.price, r.client_price, r.rows.length));
        if (k === "gacha.pool" && !ta.value.trim()) ta.value = r.rows.map(x => x[0] + " " + x[1]).join("\n"); } catch (e) { put(sInfo, errbox(e)); } };
      slot.addEventListener("change", () => { ta.value = ""; load(); });
      put(form, h("div", { class: "kv edit" }, field("Автомат", slot), k === "gacha.price" ? field("Новая цена", val) : null), sInfo,
        k === "gacha.pool" ? ta : null);
      load();
      getParams = () => k === "gacha.price" ? { slot: slot.value, value: val.value }
        : { slot: slot.value, rows: ta.value.split(/\n+/).map(l => l.trim().split(/[\s,;]+/).map(Number)).filter(x => x.length >= 2 && x[0] > 0).map(x => [x[0], x[1]]) };
    } else if (k === "equipshop.set") {
      const li = numIn(4, 0, 10), ix = numIn(0, 0, 9999), code = numIn("", 1, 100000);
      const box = h("div", { class: "muted small" });
      const load = async () => { try { const r = await lookup("equipshop", li.value);
        put(box, T("мест в списках: {0}", r.counts.join(", ")), h("div", { class: "picklist" }, r.codes.map((it, i) =>
          h("div", { class: "pick", onclick: () => { ix.value = i; } }, h("span", { class: "muted mono" }, String(i)), itemLine(it.code, it.name, it.icon))))); }
        catch (e) { put(box, errbox(e)); } };
      li.addEventListener("change", load);
      code.addEventListener("change", () => codeInfo(code.value));
      put(form, h("div", { class: "kv edit" }, field("Список (0–10)", li), field("Место в списке", ix), field("Новый код", code)), box);
      load();
      getParams = () => ({ list: li.value, index: ix.value, code: code.value });
    } else if (k === "honor.price" || k === "honor.item") {
      const pos = numIn(0, 0, 32767), coins = numIn("", 0, 2000000000), rank = numIn("", 0, 255), code = numIn("", 1, 100000);
      const box = h("div", { class: "muted small" });
      const load = async () => { try { const r = await lookup("honor", pos.value);
        const c = r.client;
        put(box, c ? [itemLine(r.item.code, r.item.name, r.item.icon), kv([[T("Клиент: монеты / звание"), c[7] + " / " + c[8]],
          [T("Сервер"), Object.entries(r.server).map(([g, v]) => g + ": " + (v ? v[7] + " / " + v[8] + " (" + v[1] + ")" : "—")).join(", ")],
          [T("Званий у клиента"), r.ranks], [T("Строк витрины"), r.rows]])] : T("строки нет"));
        if (c && k === "honor.price" && coins.value === "") { coins.value = c[7]; rank.value = c[8]; } } catch (e) { put(box, errbox(e)); } };
      pos.addEventListener("change", load);
      code.addEventListener("change", () => codeInfo(code.value));
      put(form, h("div", { class: "kv edit" }, field("Строка (StorePos)", pos), k === "honor.price" ? [field("Монеты славы", coins), field("Требуемое звание", rank)]
        : field("Новый код товара", code)), box);
      load();
      getParams = () => k === "honor.price" ? { pos: pos.value, coins: coins.value, rank: rank.value } : { pos: pos.value, code: code.value };
    } else if (k === "text.set") {
      getParams = await textForm(form, info, null);
    } else if (k.startsWith("mob.") || k === "mine.drop" || k === "item.set" || k === "gem.level" || k === "quest.reward"
               || k === "board.quest" || k.startsWith("title.") || k.startsWith("skill.") || k === "class.stat"
               || k === "level.exp" || k === "warp.cost" || k === "map.open" || k === "patch.set" || k === "config.set") {   // ★ А5.5 — «Настройки патчей»   // ★ А4.3; ★ А4.4 — «Предметы»; ★ А4.5 — «Задания»; ★ А4.6 — «Звания»; ★ А4.7 — «Навыки и классы»; ★ А4.8 — «Карты»
      const ta = h("textarea", { rows: 6, class: "wide mono", placeholder: "параметры позиции JSON" });
      const jerr = h("div");
      // ★ ревизия 35 К-3: нераспарсенный JSON — явная ошибка (под полем сразу и отказ при «Добавить»), а не молчаливый {}
      const parseJ = () => {
        let v;
        try { v = JSON.parse(ta.value || "{}"); } catch (e) { throw new Error(T("Параметры JSON не разобраны: {0}", e.message)); }
        if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error(T("Параметры JSON — объект {…}, а не список или число"));
        return v;
      };
      ta.addEventListener("input", () => { try { parseJ(); put(jerr); } catch (e) { put(jerr, errbox(e)); } });
      const itemKind = k === "item.set" || k === "gem.level";
      const questKind = k === "quest.reward" || k === "board.quest";
      const titleKind = k.startsWith("title.");
      const skillKind = k.startsWith("skill.") || k === "class.stat" || k === "level.exp";
      const mapKind = k === "warp.cost" || k === "map.open";
      const patchKind = k === "patch.set" || k === "config.set";
      put(form, h("div", { class: "row" }, patchKind ? h("a", { href: "#/shops/patches" }, "Открыть вкладку «Настройки патчей»")
        : mapKind ? h("a", { href: "#/shops/maps" }, "Открыть вкладку «Карты»")
        : skillKind ? h("a", { href: "#/shops/skills" }, "Открыть вкладку «Навыки и классы»")
        : titleKind ? h("a", { href: "#/shops/titles" }, "Открыть вкладку «Звания»")
        : questKind ? h("a", { href: "#/shops/quests" }, "Открыть вкладку «Задания»")
        : itemKind ? h("a", { href: "#/shops/items" }, "Открыть вкладку «Предметы»")
        : h("a", { href: "#/shops/monsters" }, "Открыть вкладку «Монстры и добыча»")),
        h("div", { class: "muted small" }, T("Удобнее править во вкладке: там шансы «было → станет». Здесь — параметры JSON, как их пишет вкладка.")), ta, jerr);
      getParams = parseJ;
    } else if (k === "hair.price") {
      const hid = numIn(0, 0, 32767), val = numIn("", 0, 2000000000);
      const box = h("div", { class: "muted small" });
      const load = async () => { try { const r = await lookup("hair", hid.value);
        put(box, kv([[T("Клиент: цена"), r.client], [T("Сервер"), Object.entries(r.server).map(([g, v]) => g + ": " + v).join(", ")], [T("Причёсок"), r.rows]])); }
        catch (e) { put(box, errbox(e)); } };
      hid.addEventListener("change", load);
      put(form, h("div", { class: "kv edit" }, field("Причёска (Id)", hid), field("Новая цена", val)), box);
      load();
      getParams = () => ({ id: hid.value, value: val.value });
    }
  };
  kindSel.addEventListener("change", show);
  await show();
  if (!await confirmWin(T("Позиция набора №{0}", cs.id), [h("div", { class: "kv edit" }, h("div", null, "Вид"), kindSel), help, form, info], T("Добавить"))) return;
  let params;
  try { params = getParams(); } catch (e) { notify(e.message, true); return; }    // ★ ревизия 35 К-3: ошибка разбора — не добавлять
  await csRun("shop.cs_item_add", { cs: cs.id, kind: kindSel.value, params }, after);
}

function checkView(c) {
  if (!c) return h("div", { class: "muted" }, "Проверки ещё не было.");
  const pos = c.positions.map(p => h("div", { class: "card" },
    h("div", { class: "row" }, h("b", null, "#" + p.pos), h("span", { class: "mono small" }, p.kind), h("span", null, p.text || "—"),
      p.urgent_ok ? badge(T("можно срочно"), "ok") : null),
    (p.lines || []).map(x => h("div", { class: "mono small" }, x)),               // ★ А4.3: шансы «было / станет»
    p.errors.map(e => h("div", { class: "err" }, e)), p.warnings.map(w => h("div", { class: "note" }, w))));
  const files = (c.server.files || []).map(f => h("details", null, h("summary", null, T("{0} — {1}: {2} → {3}", f.table, f.gs.join(", "), f.base.slice(0, 8), f.new.slice(0, 8))),
    table([["Строка", d => d[0]], ["Было", d => h("span", { class: "mono small" }, d[1])], ["Станет", d => h("span", { class: "mono small" }, d[2])]], f.diff)));
  const cli = (c.client || []).map(e => h("div", { class: "mono small" }, JSON.stringify(e).slice(0, 240)));
  const sims = Object.entries(c.sim || {}).map(([k, v]) => h("details", null, h("summary", null, T("{0}: мимо {1} %, особые 0–4 {2} %; прогон {3}: мимо {4}, особых {5}", k,
      (v.odds.miss * 100).toFixed(4), (v.odds.special * 100).toFixed(3), v.sim.n, v.sim.miss, v.sim.special)),
    table([["Позиция", r => r[0]], ["Код", r => r[1]], ["Вес", r => r[2]], ["Шанс, %", r => (r[3] * 100).toFixed(4)],
      ["Выпало из {0}", r => v.sim.hits[String(r[0])] || 0], ["Было, %", r => { const o = (v.old_odds.rows || []).find(x => x[0] === r[0]); return o ? (o[3] * 100).toFixed(4) : "—"; }]], v.odds.rows)));
  return h("div", null,
    h("div", { class: "row" }, c.ok ? badge(T("проверка пройдена"), "ok") : badge(T("есть ошибки"), "bad"),
      h("span", { class: "muted small" }, T("клиент: {0} {1}", c.client_source, c.client_built || ""))),
    c.errors.map(e => h("div", { class: "err" }, e)), c.warnings.map(w => h("div", { class: "note" }, w)),
    h("h3", null, "Позиции"), pos,
    h("h3", null, T("Сервер: файлов {0}", c.server.count)), files.length ? files : h("div", { class: "muted" }, "серверной половины нет"),
    h("h3", null, T("Клиент: правок {0}", (c.client || []).length)), cli.length ? cli : h("div", { class: "muted" }, "клиентской половины нет"),
    sims.length ? [h("h3", null, "Бустеры: шансы и прогон 100 000 открытий"), sims] : null,
    (c.balance || []).length ? [h("h3", null, "Баланс: было → станет"),
      c.balance_strong ? h("div", { class: "note" }, T("сильная правка баланса: при утверждении — второе подтверждение")) : null,
      table([["#", b => b.pos], ["Что", b => T(b.what)], ["Было", b => b.old], ["Станет", b => b.new],
        ["Сильная", b => b.strong ? badge(b.gate ? T("да — подтверждение") : T("да — сведения"), b.gate ? "bad" : "warn") : "—"]], c.balance),
      c.balance_held ? h("div", { class: "muted small" }, T("на руках у игроков: {0}", Object.entries(c.balance_held).map(([k, v]) => k + ": " + (v.stack ? T("{0} шт. в {1} стопках", v.amount, v.rows) : T("{0} экз.", v.rows))).join(", "))) : null] : null);
}

// ★ А4.0: утверждение — при сильной правке баланса второе подтверждение (число предметов на руках показывает служба)
async function csApprove(cs, after) {
  if (!(cs.check && cs.check.balance_strong)) return csRun("shop.cs_approve", { cs: cs.id }, after);
  const strong = (cs.check.balance || []).filter(b => b.strong && b.gate);
  const lines = strong.map(b => h("div", { class: "err" }, "#" + b.pos + " " + T(b.what) + ": " + b.old + " → " + b.new));
  // ★ ревизия 45 Н-3 / Н-5: настройки патчей — свой текст; MasterEnable=0 / выключение защиты — ещё и код второго фактора
  const patch = strong.length && strong.every(b => b.kind === "patch");
  const two = strong.some(b => b.totp);
  const code = h("input", { type: "text", inputmode: "numeric", autocomplete: "one-time-code", placeholder: T("код второго фактора"), size: 8 });
  if (!await confirmWin(T(patch ? "Сильная правка настроек патчей" : "Сильная правка баланса"),
    [h("div", { class: "note" }, T(patch ? "выключение патча, смена режима, патч защиты или предел, не подтверждённый кодом, — подтвердите ещё раз"
      : "значение меняется больше чем в 2 раза (или стопка / тип / замена предмета) — подтвердите ещё раз")), lines,
    two ? h("label", { class: "row" }, T("Второй фактор (MasterEnable=0 / выключение защиты):"), code) : null],
    T("Подтверждаю"))) return false;
  return csRun("shop.cs_approve", Object.assign({ cs: cs.id, balance_ok: "balance" }, two ? { totp: code.value.trim() } : {}), after);
}

async function viewShopSet(my, id) {
  const out = h("div", null, h("div", { class: "muted" }, "Загружаю…"));
  mount(shell("#/shops", h("h1", null, T("Набор изменений №{0}", id)), shopsTabs(""), out));
  let cs, meta;
  try { [cs, meta] = await Promise.all([api("/api/shops/set/" + id), api("/api/shops/sets")]); } catch (e) { if (!stale(my)) put(out, errbox(e)); return; }
  if (stale(my)) return;
  cs._kinds = meta.kinds;
  const reload = () => { if (!stale(my)) viewShopSet(S.nav, id); };
  const ed = can("shop.edit") && (cs.status === "draft" || cs.status === "checked");
  const kindTitle = k => { const x = meta.kinds.find(z => z.id === k); return x ? T(x.title) : k; };
  const btn = (label, name, extra, show) => show ? h("button", { type: "button", onclick: () => csRun(name, Object.assign({ cs: cs.id }, extra || {}), reload) }, label) : null;
  const cmds = ["client-dry", "client-apply", "server-dry", "server-apply " + cs.id + " --confirm-restart"].map(c => h("div", { class: "mono small" },
    "python asda_admin.py changeset " + (c.includes(" ") ? c : c + " " + cs.id)));
  put(out,
    h("div", { class: "card" }, kv([["Заголовок", cs.title], ["Статус", csBadge(cs.status)], ["Порядок половин", T(CS_ORDER[cs.order_mode] || cs.order_mode)],
      ["Срочно, только сервер", cs.urgent ? T("да") : T("нет")], ["Причина", cs.note || "—"], ["Автор", cs.author + " · " + dt(cs.created_at) + " UTC"],
      ["Утвердил", cs.approved_by ? cs.approved_by + " · " + dt(cs.approved_at) + " UTC" : "—"],
      ["Серверная половина", T(CS_HALF[cs.server_state]) + (cs.server_tag ? " · " + cs.server_tag : "") + (cs.server_note ? " · " + cs.server_note : "")],
      ["Клиентская половина", T(CS_HALF[cs.client_state]) + (cs.client_backup ? " · " + cs.client_backup : "")]]),
      h("div", { class: "row end" },
        ed ? h("button", { type: "button", onclick: () => addItemWin(cs, reload) }, "Добавить позицию") : null,
        btn("Проверить", "shop.cs_check", null, ed && cs.items.length),
        can("shop.edit") && cs.status === "checked" ? h("button", { type: "button", onclick: () => csApprove(cs, reload) }, "Утвердить") : null,
        btn("Вернуть в черновик", "shop.cs_reopen", null, can("shop.edit") && ["checked", "approved"].includes(cs.status)
          && ["none", "dry_srv", "dry_ok"].includes(cs.server_state) && ["none", "dry_ok"].includes(cs.client_state)),
        btn("Сверить базу сервера", "shop.cs_server_dry", null, can("shop.edit") && ["approved", "applied_server", "applied_client", "released"].includes(cs.status)
          && ["none", "dry_srv", "dry_ok"].includes(cs.server_state) && cs.check && cs.check.server_needed),
        btn("Отменить набор", "shop.cs_cancel", null, can("shop.edit") && ["draft", "checked", "approved"].includes(cs.status)
          && cs.server_state !== "applied" && cs.client_state !== "applied"))),
    h("div", { class: "card" }, h("h2", null, "Позиции"),
      table([["#", x => x.pos], ["Вид", x => kindTitle(x.kind)], ["Параметры", x => h("span", { class: "mono small" }, JSON.stringify(x.params).slice(0, 160))],
        ["Добавил", x => x.added_by], ["", x => ed ? h("button", { type: "button", class: "ghost", onclick: (ev) => { ev.stopPropagation();
          csRun("shop.cs_item_del", { cs: cs.id, pos: x.pos }, reload); } }, "убрать") : null]], cs.items)),
    h("div", { class: "card" }, h("h2", null, "Проверка: было → станет"), checkView(cs.check)),
    h("div", { class: "card" }, h("h2", null, "Применение (консоль на ПК владельца)"),
      h("div", { class: "muted small" }, "Клиентская половина — RawAssets/DT через очередь UE, выпуск клиента — только по слову владельца. Серверная — рестарт стойки с объявлением в Discord (restart_stack.py), только владелец."),
      cmds));
}

// ---------- расхождения ----------
async function viewShopsDiverge(my) {
  const out = h("div", null, h("div", { class: "muted" }, "Читаю стойку и клиент…"));
  mount(shell("#/shops", h("h1", null, "Магазины"), shopsTabs("#/shops/diverge"), out));
  let d;
  try { d = await api("/api/shops/diverge?areas=all"); } catch (e) { if (!stale(my)) put(out, errbox(e)); return; }
  if (stale(my)) return;
  const colsOf = rows => {
    const keys = rows.length ? Object.keys(rows[0]) : [];
    return keys.map(k => [T(k), r => (typeof r[k] === "object" ? JSON.stringify(r[k]) : r[k])]);
  };
  put(out, h("div", { class: "muted small" }, T("клиент: {0} {1}", d.client_source, d.client_built || "")),
    d.sections.map(s => h("div", { class: "card" }, h("h2", null, T("{0}: {1}", s.title, s.count)), s.note ? h("div", { class: "muted small" }, s.note) : null,
      s.rows.length ? h("details", null, h("summary", null, "показать"), table(colsOf(s.rows), s.rows)) : h("div", { class: "muted" }, "расхождений нет"))));
}

// ---------- ★ А4.2: «Данные игры → Тексты» (поиск, правка RU / EN одной позицией, предпросмотр «было → станет») ----------
async function textsApi(entity, q) { return api("/api/texts/search?entity=" + encodeURIComponent(entity || "") + "&q=" + encodeURIComponent(q || "")); }

function textDiff(label, was, now) {
  if (now === null || now === undefined) return h("div", { class: "muted small" }, T("{0}: не меняется", label));
  return h("div", { class: "kv" }, h("div", null, T("{0}: было", label)), h("div", { class: "mono small pre" }, was || "—"),
    h("div", null, T("{0}: станет", label)), h("div", { class: "mono small pre" }, now));
}

// Поля позиции «Тексты»: вид, ключ (поиск по коду или тексту), RU и EN с отметкой «не менять» → функция параметров
async function textForm(form, info, preset) {
  const meta = await textsApi("", "");
  const ents = meta.entities;
  const ent = sel(ents.map(e => [e.id, T(e.title)]), preset ? preset.entity : ents[0].id);
  const q = h("input", { class: "wide", placeholder: T("код или часть текста"), value: preset ? preset.key : "" });
  const found = h("div");
  // ★ ревизия 34 К-6: однострочные виды — input (Enter не вставит перевод строки), многострочные — textarea
  const multi = () => (ents.find(e => e.id === ent.value) || {}).multi;
  const mk = () => { const x = multi() ? h("textarea", { rows: 3, class: "wide" }) : h("input", { class: "wide" }); x.addEventListener("input", () => preview()); return x; };
  let ru = mk(), en = mk();
  const ruBox = h("div", null, ru), enBox = h("div", null, en);
  const keepRu = h("input", { type: "checkbox" }), keepEn = h("input", { type: "checkbox" });
  const pv = h("div");
  let cur = preset || null;
  const preview = () => put(pv, cur ? [textDiff("RU", cur.ru, keepRu.checked ? null : ru.value), textDiff("EN", cur.en, keepEn.checked || cur.en === null ? null : en.value)] : null);
  const pick = r => {
    cur = Object.assign({ entity: ent.value }, r);
    ru.value = r.ru || ""; en.value = r.en === null ? "" : r.en;
    keepEn.checked = r.en === null; keepEn.disabled = r.en === null;
    put(info, kv([[T("Ключ"), r.key], [T("Ключ EN"), r.en_key], [T("EN"), r.en === null ? T("строки нет — в EN показывается RU") : T("есть")]]));
    preview();
  };
  const find = async () => {
    put(found, h("div", { class: "muted small" }, T("Ищу…")));
    try {
      const r = await textsApi(ent.value, q.value);
      put(found, h("div", { class: "muted small" }, T("найдено {0} из {1} (источник: {2})", r.rows.length, r.total, r.source),
        r.source === "snapshot" ? " · " + T("снимок от {0} (обновляется выкладкой панели)", r.built || "?") : ""),
        table([["Ключ", x => x.key], ["RU", x => (x.ru || "").slice(0, 80)], ["EN", x => x.en === null ? "—" : (x.en || "").slice(0, 80)]], r.rows, pick));
      if (r.rows.length === 1) pick(r.rows[0]);
    } catch (e) { put(found, errbox(e)); }
  };
  [keepRu, keepEn].forEach(x => x.addEventListener("input", preview));
  [keepRu, keepEn].forEach(x => x.addEventListener("change", preview));
  q.addEventListener("change", find);
  ent.addEventListener("change", () => { cur = null; ru = mk(); en = mk(); put(ruBox, ru); put(enBox, en); preview(); find(); });
  put(form, h("div", { class: "kv edit" }, h("div", null, "Вид текста"), ent, h("div", null, "Поиск"), h("div", { class: "row" }, q,
    h("button", { type: "button", onclick: find }, "Найти"))), found,
    h("div", { class: "kv edit" }, h("div", null, "RU"), ruBox, h("div", null, ""), h("label", { class: "row" }, keepRu, h("span", null, "RU не менять")),
      h("div", null, "EN"), enBox, h("div", null, ""), h("label", { class: "row" }, keepEn, h("span", null, "EN не менять"))),
    h("h3", null, "Было → станет"), pv);
  if (preset) pick(preset); else if (q.value) await find();
  return () => {
    if (!cur) return { entity: ent.value, key: "", ru: null, en: null };      // служба откажет «ключ текста: непустой…»
    return { entity: cur.entity, key: cur.key, ru: keepRu.checked ? null : ru.value, en: keepEn.checked || cur.en === null ? null : en.value };
  };
}

async function viewTexts(my) {
  const out = h("div");
  mount(shell("#/shops", h("h1", null, "Тексты"), shopsTabs("#/shops/texts"), h("div", { class: "note" },
    T("Правка существующих текстов игры RU и EN (только клиент): позиция попадает в набор изменений; проверка показывает «было → станет», применение — консолью ПК (client-dry / client-apply), выпуск — с клиентом.")), out));
  let sets;
  try { sets = (await api("/api/shops/sets")).items.filter(x => x.status === "draft" || x.status === "checked"); } catch (e) { if (!stale(my)) put(out, errbox(e)); return; }
  if (stale(my)) return;
  const form = h("div"), info = h("div", { class: "muted small" });
  let getParams;
  try { getParams = await textForm(form, info, null); } catch (e) { put(out, errbox(e)); return; }
  const target = sel([["", T("новый набор")]].concat(sets.map(x => [x.id, "№" + x.id + " " + x.title])), sets.length ? sets[0].id : "");
  const add = async () => {
    const params = getParams();
    let id = target.value;
    if (!id) {
      const x = await csRun("shop.cs_create", { title: T("Тексты: {0} {1}", params.entity, params.key), note: T("правка текста игры (RU / EN)"), order_mode: "together", urgent: false });
      if (!x || !x.result) return;
      id = x.result.id;
    }
    const r = await csRun("shop.cs_item_add", { cs: +id, kind: "text.set", params });
    if (r) location.hash = "#/shops/set/" + id;
  };
  put(out, h("div", { class: "card" }, form, info,
    can("data.edit") ? h("div", { class: "row" }, h("span", null, T("Набор")), target, h("button", { type: "button", onclick: add }, "Добавить в набор")) :
      h("div", { class: "muted small" }, T("правка — с правом «data.edit»"))));
}
