// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Сообщество» (шаг А7.6, 24.11.2026; решение владельца А7 №9 — хозяин реестра заявок и тестеров остаётся бот Oracle; domains/community.py,
// /api/community). Копия реестра бота (заявки в тестеры, тестеры, предупреждения /warn, баны сервера Discord) и очередь команд боту со статусами;
// действия — операции community.*: решение по заявке, роль Beta Tester, снять предупреждения (community.manage — owner, admin), бан / разбан
// Discord с блоком учётки по флажку (community.ban — owner, admin; сам блок — account.block / account.unblock своим правом), отменить / повторить
// команду, проверочная. gm — только просмотр. Реестр исключённых против блока входа — готовый блок discordBans() из app.js (как в «Учётках»).
// Ники, причины, итоги бота — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (acText), без T() и без HTML. Помощники — app.js и acjournal.js.
"use strict";

const CM_STATE = { hold: ["ждёт блока учётки", "warn"], queued: ["ждёт бота", ""], claimed: ["бот взял", "warn"], unknown: ["итог неизвестен", "bad"],
  done: ["выполнено", "ok"], failed: ["ошибка", "bad"], cancelled: ["отменено", ""], expired: ["просрочено", "warn"], test: ["тест (бот не исполнял)", "ok"] };
const CM_APP = { pending: ["на рассмотрении", "warn"], approved: ["одобрена", "ok"], rejected: ["отклонена", ""] };
const CM_FILTER = [["pending", "на рассмотрении"], ["approved", "одобренные"], ["rejected", "отклонённые"], ["all", "все"]];
const cmBadge = (map, k) => { const x = map[k] || [String(k || "—"), ""]; return badge(T(x[0]), x[1]); };
const cmWho = (uid, user, login) => h("span", null, acText(user || uid), h("div", { class: "muted small mono" }, acText(uid)),
  login ? h("div", { class: "muted small" }, acText(T("логин игры {0}", login))) : null);

// окно с полями до предпросмотра: причина (обязательно), проверочная, свои поля → объект значений или null
async function cmAsk(title, note, extra) {
  const reason = h("input", { type: "text", maxlength: "300", placeholder: "причина (3–300 знаков, уйдёт в журнал Discord и mod-log)", style: { width: "100%" } });
  const test = h("input", { type: "checkbox" });
  const fields = extra || [];
  const ok = await confirmWin(T(title), [note ? h("div", { class: "note" }, note) : null,
    h("label", null, "Причина", reason), fields.map(f => f.node),
    h("label", { class: "row" }, test, h("span", null, "проверочная — бот её не исполняет, в Discord ничего не изменится"))], "Дальше");
  if (!ok) return null;
  const out = { reason: reason.value, test: test.checked };
  for (const f of fields) Object.assign(out, f.get());
  return out;
}

async function cmRun(name, params, reload) {
  let p;
  try { p = await op(name, params, true); } catch (e) { return notify(e.message, true); }
  const pre = { whiteSpace: "pre-wrap" };
  if (!await confirmWin(T("Подтвердите"), [h("div", { class: "pv", style: pre }, T(p.preview.text)),
    (p.preview.warnings || []).map(w => h("div", { class: "note", style: pre }, T(w)))])) return;
  try { const x = await op(name, params, false); notify(T(x.message || "готово")); }
  catch (e) { notify(e.message, true); }
  reload();
}

async function viewCommunity(my) {
  const info = h("div", { class: "muted small" }), warnBox = h("div"), appsBox = h("div"), testersBox = h("div"), warnsBox = h("div"),
    bansBox = h("div"), cmdBox = h("div"), regBox = h("div"), stuckBox = h("div");
  const flt = h("select", null, CM_FILTER.map(([v, t]) => h("option", { value: v }, T(t))));
  flt.addEventListener("change", () => load());
  let can = {};
  const testBtn = h("button", { type: "button", class: "ghost", onclick: () => cmRun("community.test", {}, load) }, "Проверочная команда");
  const addBtn = h("button", { type: "button", class: "ghost", onclick: () => testerAdd() }, "Выдать роль Beta Tester");
  const banBtn = h("button", { type: "button", class: "ghost", onclick: () => ban("") }, "Бан Discord по id");
  mount(shell("#/community", h("div", { class: "row" }, h("h1", null, "Сообщество"), flt,
      h("button", { type: "button", class: "ghost", onclick: () => load() }, "Обновить"), testBtn),
    h("div", { class: "note" }, "Хозяин реестра заявок и тестеров — бот Oracle (решение владельца №9): здесь его копия, она приходит раз в 5 мин и после каждой команды. Команды исполняет бот на ПК владельца раз в 30 с — сервер Discord не видит."),
    info, stuckBox, warnBox,
    h("div", { class: "card" }, h("h2", null, "Заявки в тестеры"), appsBox),
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Тестеры (роль Beta Tester)"), addBtn), testersBox),
    h("div", { class: "card" }, h("h2", null, "Предупреждения /warn"), warnsBox),
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", null, "Баны сервера Discord"), banBtn), bansBox),
    h("div", { class: "card" }, h("h2", null, "Очередь команд боту"), cmdBox),
    h("div", { class: "card" }, h("h2", null, "Реестр исключённых (BANNED_PLAYERS.md) против блока входа"), regBox),
    h("div", { class: "muted small" }, h("a", { href: "#/reports" }, "Жалобы игроков из Discord — раздел «Жалобы игроков»"))));

  const idField = () => { const i = h("input", { type: "text", inputmode: "numeric", maxlength: "20", placeholder: "Discord id (15–20 цифр)" });
    return { node: h("label", null, "Discord id", i), get: () => ({ uid: i.value.trim() }) }; };
  const accField = (label, withHours) => {
    const c = h("input", { type: "checkbox" }), u = h("input", { type: "text", inputmode: "numeric", maxlength: "10", placeholder: "номер учётки — пусто: по привязке Discord" });
    const hr = h("select", null, [["", "навсегда"], ["24", "24 ч"], ["168", "7 суток"], ["720", "30 суток"]].map(([v, t]) => h("option", { value: v }, T(t))));
    return { node: h("div", null, h("label", { class: "row" }, c, h("span", null, label)), h("label", null, "Учётка игры (Userindex)", u),
        withHours ? h("label", null, "Срок блока", hr) : null),
      get: () => Object.assign({ account: c.checked, block_uid: u.value.trim() }, withHours && hr.value ? { hours: +hr.value } : {}) };
  };

  async function decide(a, decision) {
    const v = await cmAsk(decision === "approve" ? "Принять заявку" : "Отклонить заявку",
      T(decision === "approve" ? "Как кнопка Approve: роль Beta Tester, карточка в staff-chat, личное сообщение игроку." : "Как кнопка Reject: карточка в staff-chat, игроку бот не пишет."));
    if (v) cmRun("community.app.decide", Object.assign({ msg_id: a.msg_id, decision }, v), load);
  }
  async function testerAdd(uid) {
    const f = uid ? [] : [idField()];
    const v = await cmAsk("Выдать роль Beta Tester", uid ? acText(uid) : null, f);
    if (v) cmRun("community.tester.add", Object.assign({ uid }, v), load);
  }
  async function testerRemove(t) {
    const v = await cmAsk("Снять роль Beta Tester", T("Как remove_tester.py: роль снимается, одобренные заявки участника — «отклонено»."));
    if (v) cmRun("community.tester.remove", Object.assign({ uid: t.uid }, v), load);
  }
  async function warnsClear(uid) {
    const v = await cmAsk("Снять предупреждения", acText(uid));
    if (v) cmRun("community.warns.clear", Object.assign({ uid }, v), load);
  }
  // ★ ревизия 79 В-2: бан с блоком учётки — сначала проверка цели ботом (команда check, в Discord ничего не меняется), блок — только после
  //   «проверка прошла». Окно ждёт итог проверки до 2 мин (бот берёт команды раз в 30 с).
  async function checkFirst(uid) {
    let id;
    try { id = (await op("community.ban.check", { uid }, false)).result.cmd; } catch (e) { notify(e.message, true); return false; }
    notify(T("проверка цели — команда №{0}, ждём бота…", id));
    for (let i = 0; i < 24; i++) {
      await new Promise(res => setTimeout(res, 5000));
      let r;
      try { r = await api("/api/community?apps=pending"); } catch (e) { continue; }
      const x = (r.cmds || []).find(c => c.id === id);
      if (x && x.state === "done") return true;
      if (x && ["failed", "cancelled", "expired"].includes(x.state)) { notify(T("проверка цели не прошла: {0}", x.result || x.state), true); load(); return false; }
    }
    notify(T("бот не ответил на проверку за 2 мин (запущен ли бот Oracle на ПК) — бан с блоком не ставится"), true);
    return false;
  }
  async function ban(uid) {
    const f = (uid ? [] : [idField()]).concat(can["players.block"] ? [accField("и заблокировать учётку игры (account.block)", true)] : []);
    const v = await cmAsk("Бан сервера Discord", T("Бан выгоняет с сервера, роли не возвращаются и после разбана. Сообщения бот не удаляет. С блоком учётки бот сначала проверит цель."), f);
    if (!v) return;
    const p = Object.assign(uid ? { uid } : {}, v);
    if (p.account && !p.test && !await checkFirst(p.uid)) return;
    cmRun("community.ban", p, load);
  }
  // ★ ревизия 79 В-2: «Снять блок» у карточки «учётка заблокирована, бана нет» — обычная account.unblock (своё право, своя запись журнала)
  async function unblock(st) {
    cmRun("account.unblock", { uid: +st.uid }, load);
  }
  async function unban(b) {
    const f = can["players.unblock"] ? [accField("и снять блок учётки игры (account.unblock)", false)] : [];
    const v = await cmAsk("Разбан сервера Discord", acText(b.user || b.uid), f);
    if (v) cmRun("community.unban", Object.assign({ uid: b.uid }, v), load);
  }

  async function load() {
    put(info, acText(T("Загружаю…")));
    let r;
    try { r = await api("/api/community?apps=" + encodeURIComponent(flt.value)); } catch (e) { if (!stale(my)) { put(info, errbox(e)); } return; }
    if (stale(my)) return;
    can = r.can || {};
    const M = can["community.manage"], B = can["community.ban"];
    testBtn.style.display = M && r.installed ? "" : "none";
    addBtn.style.display = M && r.installed ? "" : "none";
    banBtn.style.display = B && r.installed ? "" : "none";
    const s = r.snap, c = r.counts || {}, cc = r.cmd_counts || {}, L = r.limits || {};
    put(info, !r.installed ? acText(r.error) : !s ? acText(T("копии реестра ещё нет")) :
      acText(T("копия реестра снята {0} UTC ({1} с назад) · заявок {2} (на рассмотрении {3}, одобрено {4}, отклонено {5}) · тестеров {6} · предупреждений {7} · банов {8} · участников {9} · приём заявок {10} · локдаун {11} · команд ждёт бота {12}, выполнено {13}, ошибок {14} · пределы: {15} в час, {16} в сутки",
        s.taken, s.age_s, s.n_apps, c.pending || 0, c.approved || 0, c.rejected || 0, s.n_testers, s.n_warns, s.n_bans, s.members === null ? "—" : s.members,
        T(s.apps_open ? "открыт" : "закрыт"), T(s.lockdown ? "да" : "нет"), (cc.queued || 0) + (cc.claimed || 0), cc.done || 0, cc.failed || 0, L.per_hour, L.per_day)));
    // ★ ревизия 79 В-2: бан с блоком не встал, а блок учётки стоит — крупно и с кнопкой «Снять блок» (обычная account.unblock, своя запись журнала)
    put(stuckBox, (r.block_stuck || []).map(st => h("div", { class: "card", style: { border: "2px solid #c0392b" } },
      h("h2", { class: "err" }, acText(T("Учётка {0} заблокирована, бана в Discord нет", st.uid))),
      h("div", null, acText(T("Команда бана №{0} не выполнена ({1}): {2}. Блок учётки — запись журнала №{3}, сам он не снимается.", st.cmd,
        T(({ failed: "ошибка", cancelled: "отменено", expired: "просрочено" })[st.state] || st.state), st.result || "—", st.block_audit))),
      can["players.unblock"] ? h("button", { type: "button", class: "ok", onclick: () => unblock(st) }, "Снять блок") : null)));
    put(warnBox, (r.warnings || []).length ? h("div", { class: "card" }, h("h2", null, "Предупреждения"),
      (r.warnings || []).map(w => h("div", { class: "note" }, acText(w)))) : h("div", { class: "muted small" }, "Предупреждений нет."));
    put(appsBox, acTable([["Карточка", x => h("span", { class: "mono small" }, acText(x.msg_id))], ["Подал", x => cmWho(x.uid, x.user, x.login)],
      ["Подана (UTC)", x => acText(x.ts)], ["Статус", x => h("span", null, cmBadge(CM_APP, x.status), x.banned ? h("div", null, badge(T("бан Discord"), "bad")) : null)],
      ["Решил", x => h("span", { class: "small" }, acText(x.decided_by), h("div", { class: "muted small" }, acText(x.decided)))],
      ["На сервере", x => acText(T(x.in_guild ? "да" : "нет"))], ["Тестер", x => acText(T(x.tester ? "да" : "нет"))],
      ["", x => x.pending_cmd ? h("span", { class: "muted small" }, acText(T("команда №{0} ждёт бота", x.pending_cmd)))
        : (M && x.status === "pending" && x.uid ? h("span", null, h("button", { type: "button", class: "ghost small", onclick: () => decide(x, "approve") }, "Принять"),
          h("button", { type: "button", class: "ghost small", onclick: () => decide(x, "reject") }, "Отклонить")) : null)]], r.apps || []));
    put(testersBox, acTable([["Участник", x => cmWho(x.uid, x.user, x.login)], ["Предупреждений", x => acText(x.warns)],
      ["", x => M ? h("button", { type: "button", class: "ghost small", onclick: () => testerRemove(x) }, "Снять роль") : null]], r.testers || []));
    put(warnsBox, acTable([["Участник", x => cmWho(x.uid, "", x.login)], ["№", x => acText(x.n)], ["Причина", x => acText(x.reason)],
      ["Выдал (Discord id)", x => h("span", { class: "mono small" }, acText(x.mod))], ["Когда (UTC)", x => acText(x.ts)],
      ["", x => M && x.n === 1 ? h("button", { type: "button", class: "ghost small", onclick: () => warnsClear(x.uid) }, "Снять все") : null]], r.warns || []));
    put(bansBox, acTable([["Участник", x => cmWho(x.uid, x.user, x.login)], ["Причина бана", x => acText(x.reason)],
      ["", x => B ? h("button", { type: "button", class: "ghost small", onclick: () => unban(x) }, "Разбан") : null]], r.bans || []),
      h("div", { class: "muted small" }, "Бан ставит и снимает бот без удаления сообщений: история участника остаётся. Роли забаненного пропадают, разбан их не возвращает."));
    put(cmdBox, acTable([["№", x => acText(x.id)], ["Создано (UTC)", x => h("span", null, acText(x.created), h("div", { class: "muted small" }, acText(x.by)))],
      ["Команда", x => h("span", null, acText(x.title), x.ref ? h("div", { class: "muted small" }, acText(T("откат команды №{0}", x.ref))) : null,
        x.app ? h("div", { class: "muted small mono" }, acText(x.app)) : null, x.test ? h("div", null, badge(T("проверочная"), "")) : null)],
      ["Кому", x => cmWho(x.target, "", x.login)], ["Причина", x => h("span", { class: "small" }, acText(x.reason))],
      ["Статус", x => h("span", null, cmBadge(CM_STATE, x.state), x.block_audit ? h("div", { class: "muted small" }, acText(T("блок учётки — журнал №{0}", x.block_audit))) : null)],
      ["Попыток", x => acText(x.attempts)],
      ["Итог", x => h("span", { class: "small" }, acText(x.done), x.result ? h("div", { class: x.state === "failed" ? "err" : "" }, acText(x.result)) : null,
        x.changed_by ? h("div", { class: "muted small" }, acText(T("изменил {0} {1}", x.changed_by, x.changed || ""))) : null,
        x.undo_note ? h("div", { class: "muted small" }, acText(T("откат: {0}", x.undo_note))) : null)],
      // ★ ревизия 79 М-4: отмена и повтор бана / разбана — только с правом community.ban
      ["", x => (x.ban ? B : M) ? h("span", null,
        x.can_cancel ? h("button", { type: "button", class: "ghost small", onclick: () => cmRun("community.cmd.cancel", { id: x.id }, load) }, "Отменить") : null,
        x.can_retry ? h("button", { type: "button", class: "ghost small", onclick: () => cmRun("community.cmd.retry", { id: x.id }, load) }, "Повторить") : null) : null]],
      r.cmds || []),
      h("div", { class: "muted small" }, acText(T("«Итог неизвестен» — бот взял команду и не отчитался дольше {0} мин. Повтор безопасен: бот сверяет текущее состояние и свой журнал на ПК. Откат команды — в «Журнале действий» (обратная команда боту), и только если команда что-то изменила.", L.stuck_min))));
    discordBans(regBox);
  }
  load();
}
