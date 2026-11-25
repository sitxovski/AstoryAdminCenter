// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Посещаемость» (шаг А6.10, 23.11.2026; решение владельца 23.11; domains/attendance.py, /api/attendance, операции
// attendance.credit / attendance.revoke). Сводка по учётке, персонажу и периоду: счёт ACount, дней всего и за период, первый и последний день,
// «сегодня уже получено» (как отвечает серверная OP_Attendance), расхождение «счёт ≠ дням»; история строк AttendanceDetail за период и журнал
// ручных отметок панели. Действия (право attendance.edit — owner, admin; gm только смотрит): засчитать прошедший день, снять прошедший день.
// Сегодняшний день панель не трогает (его отмечает сервер вместе с наградой 68788). Откат — в «Журнале действий».
// Имена, логины, причины — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (acText), без T() и без HTML. Помощники — app.js и acjournal.js.
"use strict";

// ключ запроса UUID v4 (как web/money.js): один на предпросмотр и запись — повтор после потерянного ответа не пишет второй раз
function atReq() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
  const x = [...b].map(v => v.toString(16).padStart(2, "0")).join("");
  return x.slice(0, 8) + "-" + x.slice(8, 12) + "-" + x.slice(12, 16) + "-" + x.slice(16, 20) + "-" + x.slice(20);
}
const atIso = d => d ? String(d).replace(/^(\d{4})(\d\d)(\d\d)$/, "$1-$2-$3") : "—";   // ГГГГММДД → ГГГГ-ММ-ДД

// Действие: причина → предпросмотр службы → подтверждение (текст и предупреждения) → запись с отпечатком (expect) и тем же ключом.
async function atOp(name, base, reload) {
  const reason = h("textarea", { rows: 2, maxlength: 300, class: "grow", placeholder: "причина (обязательна, 5…300 знаков)" });
  const title = name === "attendance.credit" ? T("Засчитать день {0}", atIso(base.day)) : T("Снять день {0}", atIso(base.day));
  if (!await confirmWin(title, [h("div", { class: "muted small" }, acText(T("Персонаж {0}/{1}", base.uid, base.idx))), reason], "Далее")) return null;
  const params = Object.assign({ reason: reason.value, req: atReq() }, base);
  let p;
  try { p = await op(name, params, true); } catch (e) { notify(e.message, true); return null; }
  const pv = p.preview || {};
  if (!await confirmWin(T("Подтвердите"), [h("pre", { class: "pv mono small" }, acText(pv.text)), (pv.warnings || []).map(w => h("div", { class: "note" }, acText(w)))])) return null;
  try {
    const x = await op(name, Object.assign({ expect: pv.expect }, params), false);
    notify(x.message || T("готово"));
    if (reload) reload();
    return x;
  } catch (e) { notify(e.message, true); return null; }
}

// ★ ревизия 73 М-1: откат правки по номеру строки журнала отметок (операция владельца attendance.undo_log): причина → предпросмотр → запись
async function atUndoLog(id, reload) {
  const reason = h("textarea", { rows: 2, maxlength: 300, class: "grow", placeholder: "причина (обязательна, 5…300 знаков)" });
  if (!await confirmWin(T("Откатить правку №{0}", id), [reason], "Далее")) return null;
  const params = { log_id: id, reason: reason.value, req: atReq() };
  let p;
  try { p = await op("attendance.undo_log", params, true); } catch (e) { notify(e.message, true); return null; }
  const pv = p.preview || {};
  if (!await confirmWin(T("Подтвердите"), [h("pre", { class: "pv mono small" }, acText(pv.text)), (pv.warnings || []).map(w => h("div", { class: "note" }, acText(w)))])) return null;
  try {
    const x = await op("attendance.undo_log", Object.assign({ expect: pv.expect }, params), false);
    notify(x.message || T("готово"));
    if (reload) reload();
    return x;
  } catch (e) { notify(e.message, true); return null; }
}

async function viewAttendance(my, q) {
  q = q || new URLSearchParams();
  const fromIn = h("input", { type: "date", value: atIso(q.get("from") || "").replace("—", "") });
  const toIn = h("input", { type: "date", value: atIso(q.get("to") || "").replace("—", "") });
  const accIn = h("input", { type: "text", maxlength: 50, class: "mono", placeholder: "учётка: номер или логин", value: q.get("account") || "" });
  const charIn = h("input", { type: "text", maxlength: 20, placeholder: "персонаж (имя точно)", value: q.get("char") || "" });
  const fx = { uid: q.get("uid") || "", idx: q.get("idx") || "" };
  const fxNote = h("span", { class: "muted small" });
  const showFx = () => put(fxNote, fx.uid ? acText(T("персонаж: учётка {0}, слот {1}", fx.uid, fx.idx) + " ") : null,
    fx.uid ? h("button", { type: "button", class: "ghost small", onclick: () => { fx.uid = fx.idx = ""; showFx(); } }, "сбросить") : null);
  showFx();
  // ★ ревизия 72 К-6: записи живого самотеста (via «test») — с меткой «самотест» и скрыты, пока не включён флажок
  const testIn = h("input", { type: "checkbox", onchange: () => load(pg.page) });
  const info = h("div", { class: "muted small" }), charsBox = h("div"), histBox = h("div"), adjBox = h("div");
  mount(shell("#/attendance", h("h1", null, "Посещаемость"),
    h("div", { class: "note" }, acText(T("Ежедневная награда у NPC: сервер отмечает день персонажа и выдаёт предмет 68788 (раз в календарные сутки по часам сервера). Здесь — счёт отметок, дни и ручные правки прошедших дней. Сегодняшний день панель не трогает: снять его — вторая награда, засчитать — лишить игрока сегодняшней награды."))),
    h("div", { class: "card" }, h("h2", null, "Фильтр"),
      h("div", { class: "row" }, h("span", null, "С "), fromIn, h("span", null, " по "), toIn, accIn, charIn, fxNote,
        h("button", { type: "button", onclick: () => load(1) }, "Показать")),
      h("div", { class: "muted small" }, "Даты — по часам сервера. Без дат — последние 30 суток. Без учётки и персонажа — все персонажи с отметками.")),
    info, h("div", { class: "card" }, h("h2", null, "Персонажи"), charsBox), h("div", { class: "card" }, h("h2", null, "Дни"), histBox),
    h("div", { class: "card" }, h("h2", null, "Ручные отметки панели"), adjBox)));
  const pg = { page: 1 };
  async function load(page) {
    pg.page = page || 1;
    put(info, acText(T("Загружаю…")));
    let r;
    try {
      r = await api("/api/attendance?" + acQs({ from: acDay(fromIn.value), to: acDay(toIn.value), account: fx.uid ? "" : accIn.value.trim(),
        char: fx.uid ? "" : charIn.value.trim(), uid: fx.uid, idx: fx.idx, page: pg.page,
        test: testIn.checked ? "1" : "" }));
    } catch (e) { if (!stale(my)) { put(info, errbox(e)); put(charsBox); put(histBox); put(adjBox); } return; }
    if (stale(my)) return;
    const c = r.can || {};
    const edit = x => c["attendance.edit"] && (!x.service || r.role === "owner");
    put(info, acText(T("Сегодня по часам сервера: {0} · период {1} — {2} · персонажей {3}", atIso(r.today), atIso(r.from), atIso(r.to), fmt(r.chars.length))),
      (r.errors || []).map(x => h("div", { class: "err" }, acText(x))));
    const dayIn = h("input", { type: "date" });
    put(charsBox, acTable([["Учётка", x => h("span", null, acAccount(x.uid, x.login), x.service ? h("span", null, " ", badge(T("служебная"), "")) : null)],
      ["Персонаж", x => acChar(x.uid, x.idx, x.name)], ["Счёт", x => x.count === null ? acText("—") : acText(fmt(x.count))],
      ["Дней всего", x => acText(fmt(x.days_total))], ["За период", x => acText(fmt(x.in_period))],
      ["Первый / последний", x => acText(atIso(x.first_day) + " / " + atIso(x.last_day))],
      ["Сегодня", x => x.today_got ? badge(T("уже получено"), "ok") : badge(T("ещё нет"), "")],
      ["", x => h("span", null, x.mismatch ? badge(T("счёт ≠ дням"), "warn") : null,
        h("button", { type: "button", class: "ghost small", onclick: () => { fx.uid = String(x.uid); fx.idx = String(x.idx); showFx(); load(1); } }, "Дни персонажа"),
        edit(x) ? h("button", { type: "button", class: "small", onclick: () => {
          if (!acDay(dayIn.value)) return notify(T("выберите день в поле над таблицей"), true);
          atOp("attendance.credit", { uid: x.uid, idx: x.idx, day: acDay(dayIn.value) }, () => load(pg.page));
        } }, "Засчитать день") : null)]], r.chars),
      c["attendance.edit"] ? h("div", { class: "row" }, h("span", null, "День для «Засчитать день»: "), dayIn,
        h("span", { class: "muted small" }, acText(T("прошедший, не старше {0} суток · награда {1} не выдаётся — только отметка · служебные учётки (до {2}) — только владелец", r.max_age_days, r.reward_item, r.svc_max)))) : null);
    const hs = r.history;
    put(histBox, h("div", { class: "muted small" }, acText(T("Строк за период {0} · страница {1} из {2}", fmt(hs.total), hs.page, hs.pages))),
      acTable([["День", x => acText(atIso(x.day))], ["Время записи", x => acText(x.regist)], ["Учётка", x => acAccount(x.uid, x.login)],
        ["Персонаж", x => acChar(x.uid, x.idx, x.name)], ["Строка", x => acText("№" + x.adno + (x.step !== 2 ? " · Step " + x.step : ""))],
        ["Отметка", x => x.panel ? h("span", null, badge(T("панель"), "warn"), " ", acText(x.mark)) : acText(x.mark ? x.mark : T("сервер"))],
        ["", x => x.past && x.step === 2 && edit(x) ? h("button", { type: "button", class: "small", onclick: () =>
          atOp("attendance.revoke", { uid: x.uid, idx: x.idx, day: x.day }, () => load(pg.page)) }, "Снять день") : (x.past ? null : badge(T("сегодня"), ""))]], hs.rows),
      hs.pages > 1 ? pager(hs.page, hs.pages, p => load(p)) : null);
    put(adjBox, r.installed ? acTable([["№", x => acText("№" + x.id)], ["Когда", x => acText(x.created)], ["Персонаж", x => acText(x.uid + "/" + x.idx)],
      ["День", x => acText(atIso(x.day))], ["Что", x => badge(x.delta > 0 ? T("засчитан") : T("снят"), x.delta > 0 ? "ok" : "warn")],
      ["Счёт", x => acText(x.count_before + " → " + x.count_after)], ["Причина", x => h("span", { class: "small" }, acText(x.reason))],
      ["Кто", x => h("span", null, acText(x.operator + " · " + x.via), x.via === "test" ? h("span", null, " ", badge(T("самотест"), "")) : null)],
      ["Откат", x => x.undo_of ? acText(T("откат №{0}", x.undo_of)) : x.undone_by ? acText(T("откачена №{0}", x.undone_by)) : acText("—")],
      // ★ ревизия 73 М-1: правка без записи «ok» в журнале действий (сбой журнала после сохранения) — метка и откат по журналу отметок (владелец)
      ["Журнал действий", x => x.in_audit === false ? h("span", null, badge(T("нет в журнале действий"), "warn"),
        c["attendance.undo_log"] && !x.undo_of && !x.undone_by ? h("button", { type: "button", class: "small", onclick: () => atUndoLog(x.id, () => load(pg.page)) }, "Откатить") : null)
        : x.in_audit === null || x.in_audit === undefined ? acText("?") : acText(T("есть"))]],
      r.adjustments)
      : h("div", { class: "note" }, acText(T("журнал ручных отметок не установлен (sql/adminc_25_attendance.sql)"))),
      r.installed ? h("div", { class: "row" }, h("label", null, testIn, " ", T("показать записи самотеста ({0})", r.adjustments_test))) : null,
      h("div", { class: "muted small" }, "Откатить правку — «Журнал действий» (право отката — владелец)."));
  }
  load(1);
}
