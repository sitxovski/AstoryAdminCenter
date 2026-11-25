// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Очередь Discord» (шаг А7.4, 23.11.2026; решение владельца А7 №2 — в Discord только по флажку «и в Discord» в форме объявления;
// domains/outbox.py, /api/outbox). Записи adm.Outbox: что, куда, кем, статус, попытки, ошибка, где опубликовано; действия — операции outbox.*:
// отменить до публикации и повторить (community.post — owner, admin), удалить опубликованное из Discord (community.delete — только owner),
// проверочная запись (бот её забирает и отмечает «тест», в Discord не публикует). Публикует бот Oracle на ПК владельца раз в 30 с.
// Тексты записей и ошибки бота — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (acText), без T() и без HTML. Помощники — app.js и acjournal.js.
"use strict";

const OB_STATE = { hold: ["ждёт объявления в игру", ""], hold_stale: ["в игру не подтвердилось", "warn"], queued: ["ждёт бота", ""],
  claimed: ["бот взял", "warn"], unknown: ["итог неизвестен", "bad"], posted: ["опубликовано", "ok"], failed: ["ошибка", "bad"],
  cancelled: ["отменено", ""], expired: ["просрочено", "warn"], test: ["тест (не публиковалось)", "ok"] };
const OB_DEL = { queued: ["удаление ждёт бота", "warn"], claimed: ["бот удаляет", "warn"], deleted: ["удалено из Discord", ""], failed: ["удаление не вышло", "bad"] };
const OB_FILTER = [["all", "все"], ["active", "в работе"], ["posted", "опубликованные"], ["failed", "ошибки"], ["cancelled", "отменённые"],
  ["expired", "просроченные"], ["test", "проверочные"]];
const obBadge = (map, k) => { const x = map[k] || [String(k || "—"), ""]; return badge(T(x[0]), x[1]); };

async function obRun(name, params, reload) {
  let p;
  try { p = await op(name, params, true); } catch (e) { return notify(e.message, true); }
  const pre = { whiteSpace: "pre-wrap" };
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv", style: pre }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note", style: pre }, T(w)))])) return;
  try { const x = await op(name, Object.assign(p.preview.expect !== undefined ? { expect: p.preview.expect } : {}, params), false);
        notify(T(x.message || "готово")); }
  catch (e) { notify(e.message, true); }
  reload();
}

async function viewOutbox(my) {
  const info = h("div", { class: "muted small" }), warnBox = h("div"), listBox = h("div");
  const flt = h("select", null, OB_FILTER.map(([v, t]) => h("option", { value: v }, T(t))));
  flt.addEventListener("change", () => load());
  let can = {};
  const testBtn = h("button", { type: "button", class: "ghost", onclick: () => obRun("outbox.test", {}, load) }, "Проверочная запись");
  mount(shell("#/outbox", h("div", { class: "row" }, h("h1", null, "Очередь Discord"), flt,
      h("button", { type: "button", class: "ghost", onclick: () => load() }, "Обновить"), testBtn),
    h("div", { class: "note" }, "Сюда попадают только объявления, поставленные флажком «и в Discord» в окне «Объявление всем» (страница «Кто в игре»). Публикует бот Oracle на ПК владельца раз в 30 с — сервер Discord не видит."),
    info, warnBox, h("div", { class: "card" }, listBox)));

  function actions(x) {
    return h("span", null,
      x.can_cancel && can["community.post"] ? h("button", { type: "button", class: "ghost small", onclick: () => obRun("outbox.cancel", { id: x.id }, load) }, "Отменить") : null,
      x.can_retry && can["community.post"] ? h("button", { type: "button", class: "ghost small", onclick: () => obRun("outbox.retry", { id: x.id }, load) }, "Повторить") : null,
      x.can_delete && can["community.delete"] ? h("button", { type: "button", class: "ghost small", onclick: () => obRun("outbox.delete", { id: x.id }, load) }, "Удалить из Discord") : null);
  }

  async function load() {
    put(info, acText(T("Загружаю…")));
    let r;
    try { r = await api("/api/outbox?status=" + encodeURIComponent(flt.value)); } catch (e) { if (!stale(my)) { put(info, errbox(e)); put(listBox); } return; }
    if (stale(my)) return;
    can = r.can || {};
    testBtn.style.display = can["community.post"] && r.installed ? "" : "none";
    const c = r.counts || {}, L = r.limits || {};
    put(info, r.installed ? acText(T("ждёт бота {0} · опубликовано {1} · ошибок {2} · отменено {3} · просрочено {4} · тест {5} · бот последний раз брал запись {6} UTC, отчитывался {7} UTC · пределы: {8} в час, {9} в сутки, срок годности {10}–{11} мин",
        c.queued || 0, c.posted || 0, c.failed || 0, c.cancelled || 0, c.expired || 0, c.test || 0, r.bot_seen || "—", r.bot_done || "—",
        L.per_hour, L.per_day, L.ttl_min, L.ttl_max)) : acText(r.error));
    put(warnBox, (r.warnings || []).length ? h("div", { class: "card" }, h("h2", null, "Предупреждения"),
      (r.warnings || []).map(w => h("div", { class: "note" }, acText(w)))) : h("div", { class: "muted small" }, "Предупреждений нет."));
    put(listBox, acTable([["№", x => acText(x.id)], ["Создано (UTC)", x => h("span", null, acText(x.created), h("div", { class: "muted small" }, acText(x.by)))],
      ["Куда", x => h("span", null, acText(T((r.channels || {})[x.channel] || x.channel)), h("div", { class: "muted small" }, acText(x.role ? T((r.roles || {})[x.role] || x.role) : T("без упоминания"))))],
      ["Сообщение", x => h("details", null, h("summary", null, acText(x.title)), h("div", { class: "small", style: { whiteSpace: "pre-wrap" } }, acText(x.preview)))],
      ["Статус", x => h("span", null, obBadge(OB_STATE, x.state), x.del_state ? h("div", null, obBadge(OB_DEL, x.del_state)) : null,
        x.test ? h("div", { class: "muted small" }, acText(T("проверочная запись"))) : null)],
      ["Попыток", x => acText(x.attempts)], ["Срок годности (UTC)", x => acText(x.expires)],
      ["Итог", x => h("span", { class: "small" }, acText(x.done), x.error ? h("div", { class: "err" }, acText(x.error)) : null,
        x.posted_at ? h("div", { class: "muted small mono" }, acText(x.posted_at)) : null,
        x.del_error ? h("div", { class: "err" }, acText(x.del_error)) : null,
        x.changed_by ? h("div", { class: "muted small" }, acText(T("изменил {0} {1}", x.changed_by, x.changed || ""))) : null)],
      ["", x => actions(x)]], r.rows || []),
      h("div", { class: "muted small" }, acText(T("«Итог неизвестен» — бот взял запись и не отчитался дольше {0} мин. Опубликованный номер бот повторно не публикует (журнал бота на ПК, у сообщения в канале — ещё и nonce Discord). Дубль возможен только при сбое шлюза Discord в форуме updates.", L.stuck_min))),
      h("div", { class: "muted small" }, "Удаление из Discord — только владелец, отката нет: сообщение исчезает у всех (у форума — ветка целиком)."));
  }
  load();
}
