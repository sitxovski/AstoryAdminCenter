// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Шансы: выпало против заявленного» (шаг А6.5, 22.11.2026; domains/odds.py, /api/odds/*). ТОЛЬКО ЧТЕНИЕ.
// Заточка: UpgradeData.Flag = успех (Ev — текст свитка, не исход), шанс — ItemUpgrade.txt + купон шанса, в зоне t44 — × OverUpgrade;
// высшая переработка — UpperRefineTable, перенос — порог 60 зашит в GameServer, извлечение — ExtractionRateTable. Бустеры — веса
// GachaItemRateTable при условии «не промах» (промах бустер не тратит). Премиум-коробки gp7 — равномерно по строкам пула автомата.
// Критерий: биномиальный (два исхода) или хи-квадрат (много), поправка Холма; «мало данных» — без вывода. Служебные ≤ 5000 — отдельно.
// Значения из базы и журналов — только текстовыми узлами (acText, itemLine), без HTML. Помощники — h(), T(), put(), mount(), shell(), sel(),
// badge(), errbox(), stale(), api(), fmt() (app.js) и acText(), acQs(), acDay(), acTable() (acjournal.js).
"use strict";

const OD_VERDICT = { ok: "согласуется", deviation: "отклонение", few: "мало данных", contradiction: "противоречит таблице" };
const OD_CLASS = { ok: "ok", deviation: "bad", few: "", contradiction: "bad" };
const OD_WHY = { destroy_noscroll: "разрушение: свитки при разрушении не пишутся", stage_unknown: "откат: ступень до неизвестна",
  scroll_unknown: "свиток не определён", scroll_ambiguous: "купоны не различить", ev_mismatch: "Ev не по свиткам",
  no_table_row: "типа свитка нет в ItemUpgrade", stage_below: "ступень ниже t44 в зоне t44", over_no_row: "строки OverUpgrade нет",
  no_item: "предмет не определён", t44_changed: "предел t44 в строке не равен текущему (SowelCombine менялась)",
  rule_bad: "исход против правила сервера", half_observed: "зона t44, предмет разрушается при неудаче — исход виден наполовину" };
const OD_REFUSE = { "9": "промах", "10": "нет ячейки", "11": "флаг +35 вещи", "12": "нет ячейки", "13": "нет ячейки", "14": "нет ячейки",
  "15": "неизвестный код", "16": "перевес" };
const OD_CAT = { main: "Игроки (> 5000)", service: "Служебные ≤ 5000 (отдельно)", all: "Все учётки" };

const odNum = (x, d) => x === null || x === undefined ? acText("—") : acText(Number(x).toFixed(d));
const odPct = x => x === null || x === undefined ? acText("—") : acText((x * 100).toFixed(3) + " %");
const odP = t => t.p === null || t.p === undefined ? acText("—") : acText(Number(t.p).toPrecision(3) + " / " + Number(t.p_adj).toPrecision(3));
const odVerdict = t => badge(T(OD_VERDICT[t.verdict] || t.verdict), OD_CLASS[t.verdict] || "");
const odTitle = (r, cat) => T(OD_CAT[r.svc === "in" ? "all" : cat]);
const odVerdicts = v => acText(Object.entries(v || {}).map(([k, n]) => T(OD_VERDICT[k] || k) + " " + n).join(", "));

async function viewOdds(my) {
  const out = h("div");
  mount(shell("#/odds", h("h1", null, "Шансы: выпало против заявленного"), h("div", { class: "note" },
    acText(T("Сравнение журналов JoyLog1 и журналов стойки с ТЕКУЩИМИ таблицами сервера: если таблица менялась в периоде, старые попытки считаются против новой. Критерий — точный биномиальный (два исхода) или хи-квадрат (много исходов), поправка Холма на число проверок. «Мало данных» — меньше 30 попыток (у хи-квадрата — и ожидание корзины меньше 5): вывода нет. Шанс «100 %» сервера — это 1 − 1e-5: расхождение с ним — «противоречит таблице» при любом числе попыток. Попытки, где предел t44 в строке не равен текущему SowelCombine или исход против правила сервера, и зона t44 у предметов, которые при неудаче разрушаются, — вне критерия, отдельным счётом. Служебные учётки ≤ 5000 по умолчанию — отдельно."))), out));
  const svcIn = h("input", { type: "checkbox" });
  const fFrom = h("input", { type: "date" }), fTo = h("input", { type: "date" });
  const fAlpha = sel([["0.01", "0.01"], ["0.05", "0.05"], ["0.001", "0.001"]], "0.01");
  const bLogs = h("input", { type: "checkbox", checked: true });
  const uBox = h("div"), bBox = h("div"), xBox = h("div");
  const base = () => ({ from: acDay(fFrom.value), to: acDay(fTo.value), svc: svcIn.checked ? "in" : "sep", alpha: fAlpha.value });
  const head = r => [(r.errors || []).map(x => h("div", { class: "err" }, acText(x))), (r.notes || []).map(x => h("div", { class: "note" }, acText(x))),
    r.period ? h("div", { class: "muted small" }, acText(T("Период {0} — {1} (сутки по часам сервера), уровень значимости {2}.", r.period.from, r.period.to, r.alpha))) : null,
    (r.capped || []).length ? badge(T("строк больше, чем читается за раз — сузьте период: {0}", r.capped.join(", ")), "warn") : null];
  const testCols = [["Итог", t => odVerdict(t)], ["p / с поправкой", t => odP(t)]];

  // ---- заточка и прочее
  async function loadUpgrade() {
    put(uBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/odds/upgrade?" + acQs(base())); }
    catch (e) { if (!stale(my)) put(uBox, errbox(e)); return; }
    if (stale(my)) return;
    const sec = cat => {
      const s = r[cat];
      if (!s) return null;
      return [h("h3", null, odTitle(r, cat)),
        h("div", { class: "muted small" }, acText(T("Попыток {0}: успех {1}, неудача {2}, откат {3}, разрушение {4}. Неудача не по правилу сервера: {5}. Итоги проверок:",
          fmt(s.attempts), fmt(s.outcomes.success), fmt(s.outcomes.fail), fmt(s.outcomes.reset), fmt(s.outcomes.destroy), fmt(s.rule_bad))), " ", odVerdicts(s.verdicts)),
        Object.keys(s.excluded || {}).length ? h("div", { class: "muted small" }, acText(T("Вне критерия: {0}.", Object.entries(s.excluded).map(([k, n]) => T(OD_WHY[k] || k) + " " + n).join(", ")))) : null,
        h("h3", null, "По ступени до попытки"),
        acTable([["Ступень", x => x.stage === null ? acText("?") : acText(String(x.stage))], ["Попыток", x => fmt(x.n)], ["Успех", x => fmt(x.success)],
          ["Неудача", x => fmt(x.fail)], ["Откат", x => fmt(x.reset)], ["Разрушение", x => fmt(x.destroy)], ["С известным шансом", x => fmt(x.known)],
          ["Успехов среди них", x => fmt(x.known_success)], ["Ожидалось успехов", x => odNum(x.expected, 1)]], s.stages || []),
        h("h3", null, "По свитку"),
        acTable([["Свиток", g => itemLine(g.scroll, g.name, null)], ["Тип", g => acText(String(g.st))], ["Купон шанса", g => g.rate ? acText("+" + g.rate + " %") : acText("—")],
          ["Зона", g => g.zone === "over" ? acText(T("зона t44") + " k=" + g.k) : T("обычная")], ["Ступени", g => acText(g.stage_min + "–" + g.stage_max)],
          ["Попыток", g => fmt(g.n)], ["Успех", g => fmt(g.success)], ["Заявлено", g => odPct(g.prob)], ["Ожидалось", g => odNum(g.expected, 1)],
          ["Откат / разрушение", g => acText(g.reset + " / " + g.destroy)],
          ["Не по правилу (вне критерия)", g => g.rule_bad ? badge(Object.entries(g.off || {}).map(([k, n]) => T(OD_WHY[k] || k) + " " + n).join(", "), "warn") : acText("0")]]
          .concat(testCols), s.groups || []),
        h("h3", null, "Высшая переработка, перенос, извлечение"),
        acTable([["Что", t => t.what === "refine" ? acText(T("высшая переработка, шанс") + " " + t.c) : t.what === "refine_loss" ? acText(T("потеря материала при неудаче, шанс") + " " + t.c)
          : t.what === "bless" ? acText(T("перенос (порог зашит в GameServer)") + " ≤ " + t.c) : T("извлечение (4 исхода)")],
          ["Попыток", t => fmt(t.n)], ["Успех", t => t.what === "extract" ? acText(Object.entries(t.obs || {}).map(([k, n]) => k + ":" + n).join(" ")) : fmt(t.success)],
          ["Заявлено", t => t.what === "extract" ? acText(Object.entries(t.probs || {}).map(([k, p]) => k + ":" + (p * 100).toFixed(1) + "%").join(" ")) : odPct(t.prob)]].concat(testCols),
          (s.refine || []).concat(s.refine_loss || [], [s.bless], s.extract ? [s.extract] : [])),
        s.refine_unmatched ? badge(T("высшая переработка: рецепт не определён у {0} попыток", fmt(s.refine_unmatched)), "warn") : null,
        h("div", { class: "muted small" }, acText(T("Без розыгрыша (только счёт): сброс ItemUpgrade — {0}; обмен GaChaTran* — {1}.",
          (s.reset || []).map(x => x.state + " " + x.n).join(", ") || "—", fmt(s.tran))))];
    };
    put(uBox, head(r), r.tables ? h("div", { class: "muted small" }, acText(T("Таблицы сервера: ItemUpgrade {0} строк, OverUpgrade {1}, UpperRefineTable {2}, ExtractionRateTable {3}.",
      acNum(r.tables.item_upgrade), acNum(r.tables.over_upgrade), acNum(r.tables.upper_refine), (r.tables.extraction || []).join(" ") || "—"))) : null, sec("main"), sec("service"));
  }

  // ---- бустеры
  async function loadBoosters() {
    put(bBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/odds/boosters?" + acQs(Object.assign(base(), { logs: bLogs.checked ? "1" : "0" }))); }
    catch (e) { if (!stale(my)) put(bBox, errbox(e)); return; }
    if (stale(my)) return;
    const sec = cat => {
      const s = r[cat];
      if (!s) return null;
      return [h("h3", null, odTitle(r, cat)),
        h("div", { class: "muted small" }, acText(T("Призов {0}, вскрытий без приза {1}, призов не по текущей таблице (вне критерия) {2}. Итоги проверок:",
          fmt(s.draws), fmt(s.lost || 0), fmt(s.stale || 0))), " ", odVerdicts(s.verdicts)),
        s.replay ? h("div", { class: "muted small" }, acText(T("Log_GachaItem: строк {0}; сумма весов как сейчас — {1} (приз совпал {2}, не совпал {3}); сумма другая (таблица была иной) — {4}; без строки — {5}.",
          fmt(s.replay.lines), fmt(s.replay.same_total), fmt(s.replay.match), fmt(s.replay.mismatch), fmt(s.replay.other_total), fmt(s.replay.no_row)))) : null,
        (s.no_row || []).length ? badge(T("бустеры без строки GachaItemRateTable: {0}", s.no_row.map(x => x.code + "×" + x.n).join(", ")), "warn") : null,
        acTable([["Строка таблицы", x => acText(String(x.row))], ["Бустеры", x => h("span", null, x.boosters.slice(0, 4).map((b, i) => [i ? ", " : "", itemLine(b.code, b.name, null), acText(" ×" + b.n)]))],
          ["Вскрытий", x => fmt(x.n)], ["Кодов в строке", x => fmt(x.codes)], ["Корзин", x => fmt(x.bins)], ["Хи-квадрат / степеней", x => x.chi2 === null ? acText("—") : acText(x.chi2.toFixed(2) + " / " + x.df)]]
          .concat(testCols, [["Не по текущей таблице (вне критерия)", x => (x.outside || []).length ? h("span", null, x.outside.map((o, i) => [i ? ", " : "", itemLine(o.code, o.name, null), acText(" ×" + o.n)])) : acText("—")],
            ["Коды: выпало / ожидалось", x => h("span", { class: "small" }, (x.top || []).slice(0, 6).map((c, i) => [i ? "; " : "", acText(c.code + ": " + c.n + " / " + c.expected.toFixed(1))]))]]),
          s.rows || [])];
    };
    const p = r.replay;
    put(bBox, head(r), h("div", { class: "note" }, acText(T("Выпавшее — распределение при условии «не промах и приз принят сервером»: после броска GameServer отказывает при промахе, нехватке ячейки, флаге вещи, неизвестном коде и перевесе — бустер не тратится, в базе и Log_GachaItem ничего (GameServer.c:94338–94522)."))),
      r.refused ? h("div", { class: "muted small" }, acText(T("Отказы после броска по журналу Log_CRTJIN (все учётки, учётки в строке нет): {0}.",
        Object.entries(r.refused).map(([k, n]) => T(OD_REFUSE[k] || k) + " (" + k + ") " + n).join(", ") || "—"))) : null,
      h("div", { class: "muted small" }, acText(T("Строк GachaItemRateTable: {0}. Вскрытий без приза в журнале: {1}.", acNum(r.table_rows), fmt(r.lost)))),
      sec("main"), sec("service"),
      p ? [h("h3", null, "Журнал Log_GachaItem: розыгрыш по текущей таблице"),
        h("div", { class: "muted small" }, acText(T("Все учётки. Строк {0}; сумма весов как сейчас — {1} (приз совпал {2}, не совпал {3}); сумма другая (таблица была иной) — {4}; без строки — {5}.",
          fmt(p.lines), fmt(p.same_total), fmt(p.match), fmt(p.mismatch), fmt(p.other_total), fmt(p.no_row)))),
        (p.bad || []).length ? acTable([["Когда", x => dt(x.t)], ["Строка", x => acText(String(x.row))], ["Бросок", x => fmt(x.rate)], ["В журнале", x => acText(String(x.code))],
          ["По таблице", x => acText(x.want === null ? "—" : String(x.want))]], p.bad) : null] : null);
  }

  // ---- премиум-коробки gp7
  async function loadBoxes() {
    put(xBox, h("div", { class: "muted" }, "Загружаю…"));
    let r;
    try { r = await api("/api/odds/boxes?" + acQs(base())); }
    catch (e) { if (!stale(my)) put(xBox, errbox(e)); return; }
    if (stale(my)) return;
    const sec = cat => {
      const s = r[cat];
      if (!s) return null;
      return [h("h3", null, odTitle(r, cat)),
        h("div", { class: "muted small" }, acText(T("Розыгрышей {0}; не по текущей таблице (строка или код другие) — {1}. Итоги проверок:", fmt(s.draws), fmt(s.mismatch))), " ", odVerdicts(s.verdicts)),
        acTable([["Автомат", x => acText(String(x.box))], ["Строк пула", x => fmt(x.pool)], ["Розыгрышей", x => fmt(x.n)], ["Строк в корзине", x => fmt(x.bin_rows)],
          ["Корзин", x => fmt(x.bins)], ["Хи-квадрат / степеней", x => x.chi2 === null ? acText("—") : acText(x.chi2.toFixed(2) + " / " + x.df)]].concat(testCols,
          [["Коды: выпало / ожидалось", x => h("span", { class: "small" }, (x.top || []).slice(0, 6).map((c, i) => [i ? "; " : "", acText(c.code + ": " + c.n + " / " + c.expected.toFixed(1))]))]]),
          s.boxes || [])];
    };
    const d = r.days || {};
    put(xBox, head(r), h("div", { class: "muted small" }, acText(T("Сутки журнала шлюза: прочитано {0}, из кэша {1}, файла нет {2}, не прочитано {3}. Строк PrimiumGaChaTable: {4}.",
      fmt(d.read || 0), fmt(d.cached || 0), fmt(d.missing || 0), fmt((d.unread || []).length), acNum(r.pool_rows)))), sec("main"), sec("service"));
  }

  svcIn.addEventListener("change", () => { loadUpgrade(); loadBoosters(); loadBoxes(); });
  put(out,
    h("div", { class: "card" }, h("div", { class: "row" }, h("span", null, "С "), fFrom, h("span", null, "по "), fTo, h("span", null, "Уровень значимости "), fAlpha,
      h("label", null, svcIn, " служебные ≤ 5000 в общем итоге"), h("button", { type: "button", onclick: () => { loadUpgrade(); loadBoosters(); loadBoxes(); } }, "Показать"))),
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Заточка и прочие улучшения")), uBox),
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Бустеры"), h("label", null, bLogs, " журнал Log_GachaItem"),
      h("button", { type: "button", onclick: () => loadBoosters() }, "Обновить")), bBox),
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Премиум-коробки gp7"), h("button", { type: "button", onclick: () => loadBoxes() }, "Обновить")), xBox));
  loadUpgrade();
  loadBoosters();
  loadBoxes();
}
