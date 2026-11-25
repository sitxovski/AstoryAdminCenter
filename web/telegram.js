// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Telegram владельцу» (шаг А7.5, 23.11.2026; решение владельца А7 №3 — только владельцу, через @@@ASTORY_TELEGRAM_BOT@@, только отправка, с ПК;
// domains/notify.py, /api/telegram). Общий выключатель (по умолчанию выключен), события с выключателями, отметки службы и отправителя на ПК,
// последние записи очереди Telegram; действия — операции notify.rule.set, telegram.test (getMe, без сообщения), telegram.ping (настоящее
// проверочное сообщение). Всё — только owner (notify.view / notify.manage). Тексты записей и ошибки отправителя — НЕДОВЕРЕННЫЙ текст: только
// текстовыми узлами (acText), без T() и без HTML. Помощники — app.js, acjournal.js, outbox.js (obRun).
"use strict";

const TG_STATE = { queued: ["ждёт отправителя", ""], claimed: ["отправитель взял", "warn"], unknown: ["итог неизвестен", "bad"], sent: ["отправлено", "ok"],
  failed: ["ошибка", "bad"], cancelled: ["отменено", ""], expired: ["просрочено", "warn"], test: ["проверка (сообщения нет)", "ok"] };
const TG_PRIO = { urgent: ["срочно — всегда со звуком", "bad"], normal: ["обычное — со звуком", ""], low: ["не срочно — ночью без звука", "ok"] };
const TG_KIND = { notify: "уведомление", ping: "проверочное сообщение", test: "проверка", local: "сообщение ПК" };   // ★ р77 К-3: local — своё сообщение ПК

async function viewTelegram(my) {
  const info = h("div", { class: "muted small" }), warnBox = h("div"), masterBox = h("div"), rulesBox = h("div"), listBox = h("div");
  const testBtn = h("button", { type: "button", class: "ghost", onclick: () => obRun("telegram.test", { mode: "check" }, load) }, "Проверить Telegram");
  const pingBtn = h("button", { type: "button", class: "ghost", onclick: () => obRun("telegram.ping", {}, load) }, "Отправить проверочное сообщение");
  mount(shell("#/telegram", h("div", { class: "row" }, h("h1", null, "Telegram владельцу"),
      h("button", { type: "button", class: "ghost", onclick: () => load() }, "Обновить"), testBtn, pingBtn),
    h("div", { class: "note" }, "Уведомления о редких важных событиях — только в чат владельца, ботом @@@ASTORY_TELEGRAM_BOT@@, только отправка. Сервер Telegram не видит: события ищет служба панели, отправляет бот Oracle на ПК владельца. Токен бота лежит только на ПК (telegram.env), в панели и в базе его нет."),
    h("div", { class: "note" }, "«Проверить Telegram» — отправитель вызывает только getMe (жив ли токен и связь), сообщения в чат нет. «Отправить проверочное сообщение» — настоящая отправка в чат владельца."),
    info, warnBox, masterBox, h("div", { class: "card" }, h("h2", null, "События"), rulesBox), h("div", { class: "card" }, h("h2", null, "Очередь Telegram"), listBox),
    h("div", { class: "muted small" }, "Флаги суточного отчёта античита в Telegram не идут — только на экране «Античит: суточный отчёт» (решение владельца). Канала для игроков нет.")));

  function toggle(key, on, can) {
    return can ? h("button", { type: "button", class: "ghost small", onclick: () => obRun("notify.rule.set", { event: key, enabled: !on }, load) },
      on ? "Выключить" : "Включить") : null;
  }

  async function load() {
    put(info, acText(T("Загружаю…")));
    let r;
    try { r = await api("/api/telegram"); } catch (e) { if (!stale(my)) { put(info, errbox(e)); put(listBox); put(rulesBox); put(masterBox); } return; }
    if (stale(my)) return;
    const can = (r.can || {})["notify.manage"] && r.installed, L = r.limits || {}, c = r.counts || {};
    testBtn.style.display = can ? "" : "none";
    pingBtn.style.display = can ? "" : "none";
    put(info, r.installed ? acText(T("служба отмечалась {0} UTC ({1}) · отправитель на ПК отмечался {2} UTC · отправлено {3} · ошибок {4} · просрочено {5} · пределы: {6} в час, {7} в сутки, срок {8} мин · поиск событий раз в {9} мин · тихие часы {10}:00–{11}:00 по часам ПК",
        r.beat || "—", r.beat_host || "—", r.pc_seen || "—", c.sent || 0, c.failed || 0, c.expired || 0, L.per_hour, L.per_day, L.ttl_min, L.scan_min,
        (L.quiet || [])[0], (L.quiet || [])[1])) : acText(r.error));
    put(warnBox, (r.warnings || []).length ? h("div", { class: "card" }, h("h2", null, "Предупреждения"),
      (r.warnings || []).map(w => h("div", { class: "note" }, acText(w)))) : h("div", { class: "muted small" }, "Предупреждений нет."));
    if (!r.installed) { put(masterBox); put(rulesBox); put(listBox); return; }
    put(masterBox, h("div", { class: "card" }, h("h2", null, "Общий выключатель"),
      h("div", { class: "row" }, badge(T(r.master ? "включён" : "выключен"), r.master ? "ok" : "warn"),
        r.master_by ? h("span", { class: "muted small" }, acText(T("изменил {0} {1}", r.master_by, r.master_changed || ""))) : null,
        toggle("_master", r.master, can)),
      h("div", { class: "muted small" }, "Пока общий выключатель выключен, служба уведомлений не ставит. Проверка и проверочное сообщение работают и без него.")));
    put(rulesBox, acTable([["Событие", x => h("span", null, acText(T(x.title)), h("div", { class: "muted small" }, acText(T(x.why))))],
      ["Срочность", x => badge(T((TG_PRIO[x.prio] || [x.prio])[0]), (TG_PRIO[x.prio] || ["", ""])[1])],
      ["Повторы", x => acText(x.gap ? T("не чаще раза в {0} мин", x.gap) : T("каждое отдельно"))],
      ["Напоминание", x => acText(x.remind ? T("раз в {0} ч, пока не пройдёт", Math.round(x.remind / 60)) : T("нет"))],
      ["Ищет", x => acText(T(x.where === "pc" ? "ПК (отправитель)" : "служба панели"))],
      ["Включено", x => h("span", null, badge(T(x.enabled ? "да" : "нет"), x.enabled ? "ok" : ""),
        x.changed_by ? h("div", { class: "muted small" }, acText(T("изменил {0} {1}", x.changed_by, x.changed || ""))) : null)],
      ["", x => toggle(x.key, x.enabled, can)]], r.rules || []));
    put(listBox, acTable([["№", x => acText(x.id)], ["Создано (UTC)", x => h("span", null, acText(x.created), h("div", { class: "muted small" }, acText(x.by)))],
      ["Вид", x => h("span", null, acText(T(TG_KIND[x.kind] || x.kind)), x.event ? h("div", { class: "muted small mono" }, acText(x.event)) : null)],
      ["Сообщение", x => h("details", null, h("summary", null, acText(x.title)), h("div", { class: "small", style: { whiteSpace: "pre-wrap" } }, acText(x.text)))],
      ["Статус", x => h("span", null, obBadge(TG_STATE, x.state), x.quiet ? h("div", { class: "muted small" }, acText(T("ночью без звука"))) : null,
        x.repeats ? h("div", { class: "muted small" }, acText(T("склеено повторов: {0}", x.repeats))) : null)],
      ["Попыток", x => acText(x.attempts)], ["Срок (UTC)", x => acText(x.expires)],
      ["Итог", x => h("span", { class: "small" }, acText(x.done), x.error ? h("div", { class: x.state === "failed" || x.state === "unknown" ? "err" : "muted small" }, acText(x.error)) : null)]],
      r.rows || []));
  }
  load();
}
