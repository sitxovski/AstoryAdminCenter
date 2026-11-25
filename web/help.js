// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Справка» по операциям (шаг А7.10, 24.11.2026; core/opdoc.py, /api/opdoc). Все операции панели по разделам: что делает,
// что изменится (базы, файлы, процессы, Discord, Telegram), нужен ли перезапуск, как откатить, кто может (роли из core/auth.PERMS), второй
// фактор, исполнитель заданий. По умолчанию — только операции, доступные вашей роли (переключатель «Показать все» — с пометкой «нет права»).
// Тексты справки приходят от службы уже на выбранном языке — только текстовыми узлами (docText из app.js), без T() и без HTML.
"use strict";

// Фильтры страницы: ключ → [подпись, проверка записи]. Подробностей нет у операций без вашего права (ревизия 85 М-8) — фильтр их не показывает.
const HELP_FILTERS = {
  external: ["меняет Discord / Telegram", x => !!x.writes && (x.writes.codes.includes("discord") || x.writes.codes.includes("telegram"))],
  irreversible: ["необратимые", x => !!x.undo && x.undo.code === "irreversible"],
  restart: ["требуют перезапуска или выпуска", x => !!x.restart && x.restart.code !== "none"],
  live: ["живьём (мост)", x => !!x.writes && x.writes.codes.includes("live")],
};

// Раздел «Справка»: загрузка /api/opdoc, поиск и фильтры, список по разделам. my — номер перехода (stale).
async function viewHelp(my) {
  const q = h("input", { placeholder: "поиск: название, имя операции, таблица, описание", class: "wide" });
  const all = h("input", { type: "checkbox" });
  const flt = {};
  const info = h("div", { class: "muted small" }), list = h("div");
  const boxes = Object.entries(HELP_FILTERS).map(([k, f]) => {
    flt[k] = h("input", { type: "checkbox" });
    flt[k].addEventListener("change", () => show());
    return h("label", { class: "row" }, flt[k], h("span", null, f[0]));
  });
  all.addEventListener("change", () => show());
  q.addEventListener("input", () => show());
  mount(shell("#/help", h("div", { class: "row" }, h("h1", null, "Справка")),
    h("div", { class: "note" }, "Справка по каждой операции панели: что она делает, что изменится и где, нужен ли перезапуск и как её отменить. Тот же блок «Что изменится / Перезапуск / Откат» показывает окно подтверждения перед выполнением."),
    h("div", { class: "note" }, "Правки персонажа делаются, только когда игрок не в игре. Если он в игре и мост работает, панель предложит отключить его с сервера (отдельная запись «Живьём: отключить игрока» в журнале действий) и покажет новый предпросмотр."),
    h("div", { class: "row" }, q), h("div", { class: "row" }, h("label", { class: "row" }, all, h("span", null, "Показать все операции, не только доступные мне")), boxes),
    info, list));
  let d;
  put(info, docText(T("Загружаю…")));
  try { d = await api("/api/opdoc"); } catch (e) { if (!stale(my)) { put(info); put(list, errbox(e)); } return; }
  if (stale(my)) return;
  const roleTitle = {};
  (d.roles || []).forEach(r => { roleTitle[r.id] = T(r.title); });

  function hit(x, t) {
    if (!t) return true;
    return [x.name, x.title, x.help, x.writes && x.writes.info, x.restart && x.restart.info, x.undo && x.undo.info, x.section].some(s => String(s || "").toLowerCase().includes(t));
  }

  function show() {
    const t = q.value.trim().toLowerCase();
    const on = Object.keys(HELP_FILTERS).filter(k => flt[k].checked);
    const rows = d.items.filter(x => (all.checked || x.allowed) && hit(x, t) && on.every(k => HELP_FILTERS[k][1](x)));
    const mine = d.items.filter(x => x.allowed).length;
    put(info, docText(T("показано {0} из {1} · доступно вам {2}", rows.length, d.items.length, mine)),
      (d.missing || []).length ? h("div", { class: "err" }, docText(T("без справки: {0}", d.missing.join(", ")))) : null);
    const groups = [];
    rows.forEach(x => {
      const g = groups.length && groups[groups.length - 1].no === x.section_no ? groups[groups.length - 1] : null;
      if (g) g.rows.push(x); else groups.push({ no: x.section_no, title: x.section, rows: [x] });
    });
    put(list, groups.length ? groups.map(g => h("div", { class: "card" }, h("h2", null, docText(g.title)), g.rows.map(x => helpItem(x, roleTitle))))
      : h("div", { class: "muted" }, T("ничего не найдено")));
  }
  show();
}

// Одна операция в списке справки
function helpItem(x, roleTitle) {
  const roles = x.roles.map(r => roleTitle[r] || r).join(", ");
  return h("div", { class: "opdoc-item" },
    h("div", { class: "row" }, h("b", null, docText(x.title)), h("span", { class: "muted mono" }, docText(x.name)),
      x.allowed ? badge(T("доступно вам"), "ok") : badge(T("нет права"), "bad"),
      x.two_factor ? badge(T("второй фактор"), "warn") : null,
      x.runner ? badge(x.runner === "pc" ? T("задание ПК") : T("задание службы")) : null),
    h("div", null, docText(x.help)),
    x.writes ? opDocBlock(x) : h("div", { class: "muted small" }, T("подробности — только у тех, кому операция доступна")),
    h("div", { class: "muted small" }, docText(T("право {0}: {1}", x.perm, roles || "—"))));
}
