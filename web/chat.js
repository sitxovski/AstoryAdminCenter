// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Журнал чата» и заглушки чата (шаг А6.12, часть «панель», 22.11.2026; решение владельца №5 — журнал + заглушка, 90 дней;
// domains/chatlog.py, /api/chat/*, операции chat.mute / chat.unmute). Журнал пишет сервер (P129, AsdaPatch v86) в joylog1.chat.message.
// Здесь — состояние (установлен ли журнал, режим P129 по копиям GameServer), поиск по журналу (даты, каналы, учётка, персонаж, подстрока текста,
// карта, сервер, отметка заглушки), сырые байты text_raw для разбора кодировки, переходы (карточка учётки и персонажа, «Античит» учётки,
// жалобы на персонажа, дела учётки), заглушки (действующие / истёкшие / снятые) и действия: поставить заглушку и снять её. Откат — в «Журнале
// действий» (снять поставленную / поставить снятую снова на остаток срока). Сервер перечитывает заглушки раз в 15 с.
// Всё из журнала (текст, имена, адресат, причины) — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (acText), без T() и без HTML.
// Общие помощники — app.js (h, T, put, mount, shell, sel, badge, errbox, stale, api, op, pager, dt, kv, notify, confirmWin, fmt) и acjournal.js
// (acText, acTable, acAccount, acChar, acQs, acDay).
"use strict";

const CH_MUTE = { 1: "отклонено заглушкой", 2: "помечено: заглушка, сообщение ушло (Mode=0)" };
const CH_MST = { active: "действует", expired: "истекла", lifted: "снята" };
const CH_SCOPE = { 1: "учётка", 2: "персонаж" };
const CH_TERMS = [["15", "15 минут"], ["60", "1 час"], ["360", "6 часов"], ["1440", "1 сутки"], ["4320", "3 суток"], ["10080", "7 суток"], ["43200", "30 суток"]];

// Дата ГГГГММДД за days суток до момента iso ("ГГГГ-ММ-ДД …"; пусто — сегодня по часам браузера) — начало окна «сообщения за период»
function chFrom(iso, days) {
  const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(String(iso || ""));
  const d = m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])) : new Date();
  d.setUTCDate(d.getUTCDate() - (days || 0));
  return d.getUTCFullYear() + String(d.getUTCMonth() + 1).padStart(2, "0") + String(d.getUTCDate()).padStart(2, "0");
}

function chMuteBadge(x) {
  if (!x.mute_state) return acText("");
  return h("span", null, badge(T(CH_MUTE[x.mute_state] || String(x.mute_state)), x.mute_state === 1 ? "bad" : "warn"),
    x.mute_id ? acText(" №" + x.mute_id) : null);
}

// Действие заглушки: предпросмотр → подтверждение (текст и предупреждения службы) → запись с отпечатком (expect).
async function chOp(name, params, reload) {
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

function chRaw(x) {
  if (!x.raw) return null;
  return h("div", { class: "muted small mono" }, acText(T("байты ({0}): {1}", x.raw.len, x.raw.hex)),
    h("div", null, acText("cp1251: " + x.raw.cp1251)), h("div", null, acText("UTF-8: " + x.raw.utf8)), h("div", null, acText("cp1256: " + x.raw.cp1256)));
}

function chGo(x, st) {
  const c = st.can || {};
  const uid = x.owner || x.uid;
  return h("span", null,
    c["players.view_net"] && x.uid ? h("button", { type: "button", class: "ghost small", onclick: () => { location.hash = "#/account/" + x.uid + "/eac"; } }, "Античит учётки") : null,
    c["reports.view"] && x.char ? h("button", { type: "button", class: "ghost small", onclick: () => { location.hash = "#/reports?" + acQs({ target: x.char }); } }, "Жалобы") : null,
    c["ac.view"] && uid ? h("button", { type: "button", class: "ghost small", onclick: () => { location.hash = "#/cases?uid=" + uid; } }, "Дела учётки") : null);
}

function chMuteForm(st, q, reload) {
  const c = st.can || {};
  if (!c["chat.mute"]) return null;
  const scopeSel = sel([["account", T("на учётку")], ["char", T("на персонажа")]], q.get("char_slot") || q.get("char") ? "char" : "account");
  const uidIn = h("input", { type: "text", maxlength: 40, class: "mono", placeholder: "учётка: номер или логин", value: q.get("char_uid") || q.get("account") || "" });
  const slotIn = h("input", { type: "text", maxlength: 3, class: "mono", placeholder: "слот", value: q.get("char_slot") || "" });
  const nameIn = h("input", { type: "text", maxlength: 20, placeholder: "или имя персонажа", value: q.get("char") || "" });
  const lim = st.limits || {};   // ★ р71 Н-3: пределы роли (gm — не дольше суток, снимает только свои)
  const termSel = sel(CH_TERMS.filter(([k]) => !lim.max_minutes || +k <= lim.max_minutes).map(([k, v]) => [k, T(v)]).concat([["", T("другой срок (минут)")]]), "60");
  const minIn = h("input", { type: "text", maxlength: 7, class: "mono", placeholder: "минут" });
  const reasonIn = h("textarea", { rows: 2, maxlength: 256, class: "grow", placeholder: "причина (обязательна, видна в списке заглушек)" });
  function params() {
    const u = uidIn.value.trim(), nm = nameIn.value.trim(), char = scopeSel.value === "char";
    const p = { scope: scopeSel.value, minutes: termSel.value || minIn.value.trim(), reason: reasonIn.value };
    if (char && nm && !u) p.char = nm;
    else if (/^\d+$/.test(u)) p.uid = u;
    else p.login = u;
    if (char && !p.char) p.idx = slotIn.value.trim();
    return p;
  }
  return h("div", { class: "card" }, h("h2", null, "Поставить заглушку"),
    h("div", { class: "row" }, scopeSel, uidIn, slotIn, nameIn),
    h("div", { class: "row" }, h("span", null, "Срок "), termSel, minIn, reasonIn,
      h("button", { type: "button", onclick: () => chOp("chat.mute", params(), reload) }, "Поставить заглушку")),
    lim.max_minutes && lim.max_minutes < st.minutes_max ? h("div", { class: "note" }, acText(T("Ваша роль: заглушка не дольше {0} мин, снять — только свои. Дольше и чужие — администратор или владелец.", lim.max_minutes))) : null,
    h("div", { class: "muted small" }, acText(T("Заглушка начинает действовать на GameServer не позже чем через {0} с: сервер перечитывает заглушки раз в {0} с. На учётку — все её персонажи и вход соулмейтом с неё; на персонажа — кто бы им ни играл. Служебные учётки (номер ≤ {1}) — только владелец. Откат — в «Журнале действий».", st.refresh_sec, st.svc_max))));
}

function chMutes(st, box, onMsgs) {
  const stSel = sel([["active", T("действующие")], ["expired", T("истёкшие")], ["lifted", T("снятые")], ["all", T("все")]], "active");
  const accIn = h("input", { type: "text", maxlength: 40, class: "mono", placeholder: "учётка: номер или логин" });
  const info = h("div", { class: "muted small" }), list = h("div");
  const pg = { page: 1 };
  async function load(page) {
    pg.page = page || 1;
    put(info, acText(T("Загружаю…")));
    let r;
    try { r = await api("/api/chat/mutes?" + acQs({ state: stSel.value, account: accIn.value.trim(), page: pg.page })); }
    catch (e) { put(info, errbox(e)); put(list); return; }
    if (!r.installed) { put(info, h("div", { class: "note" }, acText(r.note))); put(list); return; }
    put(info, acText(T("Действуют {0} · истекли {1} · сняты {2} · по фильтру {3} · страница {4} из {5}", fmt(r.counts.active), fmt(r.counts.expired),
      fmt(r.counts.lifted), fmt(r.total), r.page, r.pages)), (r.errors || []).map(x => h("div", { class: "err" }, acText(x))));
    const c = st.can || {};
    put(list, acTable([["№", x => acText("№" + x.id)], ["Состояние", x => badge(T(CH_MST[x.state] || x.state), x.state === "active" ? "warn" : "")],
      ["На кого", x => h("span", null, T(CH_SCOPE[x.scope] || String(x.scope)), x.service ? h("span", null, " ", badge(T("служебная"), "")) : null)],
      ["Учётка", x => acAccount(x.uid, x.login)], ["Персонаж", x => x.scope === 2 ? acChar(x.uid, x.slot, x.char || ("#" + x.slot)) : acText("—")],
      ["До (UTC)", x => dt(x.until)], ["Осталось, мин", x => x.state === "active" ? fmt(x.minutes_left) : "—"], ["Причина", x => h("span", { class: "small" }, acText(x.reason))],
      ["Поставил", x => x.by + " · " + dt(x.created)], ["Снята", x => x.lifted ? h("span", { class: "small" }, acText(x.lifted_by + " · " + dt(x.lifted) + " · " + (x.lift_reason || ""))) : acText("—")],
      ["", x => h("span", null,
        h("button", { type: "button", class: "ghost small", onclick: () => onMsgs(x) }, "Сообщения"),
        x.state === "active" && c["chat.unmute"] && (!x.service || st.role === "owner") && (!(st.limits || {}).unmute_own_only || x.by === st.login) ? h("button", { type: "button", class: "small", onclick: async () => {
          const why = h("textarea", { rows: 2, maxlength: 256, class: "grow", placeholder: "почему снимаете (обязательно)" });
          if (!await confirmWin(T("Снять заглушку №{0}", x.id), [why])) return;
          chOp("chat.unmute", { mute_id: x.id, reason: why.value }, () => load(pg.page));
        } }, "Снять") : null)]], r.rows), r.pages > 1 ? pager(r.page, r.pages, p => load(p)) : null);
  }
  put(box, h("div", { class: "card" }, h("h2", null, "Заглушки"),
    h("div", { class: "row" }, h("span", null, "Показать "), stSel, accIn, h("button", { type: "button", onclick: () => load(1) }, "Показать")), info, list));
  load(1);
  return load;
}

async function viewChat(my, q) {
  q = q || new URLSearchParams();
  const stBox = h("div"), formBox = h("div"), muteBox = h("div"), listBox = h("div"), info = h("div", { class: "muted small" });
  let st;
  mount(shell("#/chat", h("h1", null, "Журнал чата"), h("div", { class: "note" },
    acText(T("Сообщения игроков всех каналов, как они пришли на GameServer (P129): обычный, глобальный, широкие, шёпот, отряд, клан, армия, лавка, крики. Хранятся 90 дней. Заглушка — запрет писать в чат на срок с причиной; при Mode=0 сообщение уходит и только помечается в журнале."))),
    stBox, formBox, h("div", { class: "card" }, h("h2", null, "Поиск"), info, listBox), muteBox));
  put(stBox, h("div", { class: "muted" }, "Загружаю…"));
  try { st = await api("/api/chat/state"); } catch (e) { if (!stale(my)) put(stBox, errbox(e)); return; }
  if (stale(my)) return;
  const p129 = st.p129 || {};
  put(stBox, h("div", { class: "card" }, h("h2", null, "Состояние"),
    st.installed ? kv([["Журнал", acText(T("установлен"))], ["Строк", st.rows === null ? acText("?") : acText(fmt(st.rows))],
      ["Первая запись (UTC)", acText(dt(st.oldest))], ["Последняя запись (UTC)", acText(dt(st.newest))],
      ["Заглушек действует", acText(fmt(st.mutes_active))], ["Хранение", acText(T("{0} суток (очистка — сам сервер раз в сутки)", st.retention_days))]])
      : h("div", { class: "note" }, acText(st.note)),
    h("div", { class: p129.read ? "muted small" : "err" }, acText(p129.read ? T(p129.mode_note || "") : T("режим P129 не прочитан: {0}", p129.error || "—"))),
    p129.read ? h("div", { class: "muted small mono" }, acText(Object.entries(p129.modes || {}).map(([g, m]) => g + ": " + m + (p129.mode && p129.mode[g] !== null && p129.mode[g] !== undefined ? " (Mode=" + p129.mode[g] + ")" : "")).join(" · "))) : null,
    h("div", { class: "muted small" }, acText(T("Новая заглушка и снятие доходят до GameServer не позже чем через {0} с — сервер перечитывает заглушки раз в {0} с.", st.refresh_sec)))));
  if (!st.installed) return;
  // ---- фильтры
  const fromIn = h("input", { type: "date", value: (q.get("from") || "").replace(/^(\d{4})(\d\d)(\d\d)$/, "$1-$2-$3") });
  const toIn = h("input", { type: "date", value: (q.get("to") || "").replace(/^(\d{4})(\d\d)(\d\d)$/, "$1-$2-$3") });
  const chBoxes = st.channels.map(c => ({ c, el: h("input", { type: "checkbox" }) }));
  const accIn = h("input", { type: "text", maxlength: 40, class: "mono", placeholder: "учётка: номер или логин", value: q.get("account") || "" });
  const charIn = h("input", { type: "text", maxlength: 32, placeholder: "персонаж (имя точно)", value: q.get("char") || "" });
  const textIn = h("input", { type: "text", maxlength: 100, class: "grow", placeholder: "подстрока текста", value: q.get("text") || "" });
  const mapIn = h("input", { type: "text", maxlength: 5, class: "mono", placeholder: "карта" });
  const srvSel = sel([["", T("все серверы")]].concat((st.servers || []).map(s => [s, s])), "");
  const muteSel = sel([["", T("любые")], ["any", T("с отметкой заглушки")], ["1", T("отклонено заглушкой")], ["2", T("помечено (Mode=0)")], ["0", T("без отметки")]], "");
  const rawIn = h("input", { type: "checkbox" });
  const fx = { char_uid: q.get("char_uid") || "", char_slot: q.get("char_slot") || "", mute_id: q.get("mute_id") || "" };
  const fxNote = h("span", { class: "muted small" });
  const showFx = () => put(fxNote, fx.char_uid ? acText(T("персонаж: учётка {0}, слот {1}", fx.char_uid, fx.char_slot) + " ") : null,
    fx.mute_id ? acText(T("заглушка №{0}", fx.mute_id) + " ") : null,
    fx.char_uid || fx.mute_id ? h("button", { type: "button", class: "ghost small", onclick: () => { fx.char_uid = fx.char_slot = fx.mute_id = ""; showFx(); } }, "сбросить") : null);
  showFx();
  const pg = { page: 1 };
  async function load(page) {
    pg.page = page || 1;
    put(info, acText(T("Загружаю…")));
    let r;
    try {
      r = await api("/api/chat/messages?" + acQs({ from: acDay(fromIn.value), to: acDay(toIn.value), channel: chBoxes.filter(b => b.el.checked).map(b => b.c.code).join(","),
        account: accIn.value.trim(), char: charIn.value.trim(), char_uid: fx.char_uid, char_slot: fx.char_slot, text: textIn.value.trim(), map: mapIn.value.trim(),
        server: srvSel.value, mute: muteSel.value, mute_id: fx.mute_id, raw: rawIn.checked ? "1" : "", page: pg.page }));
    } catch (e) { if (!stale(my)) { put(info, errbox(e)); put(listBox); } return; }
    if (stale(my)) return;
    if (!r.installed) { put(info, h("div", { class: "note" }, acText(r.note))); put(listBox); return; }
    put(info, acText(T("Сообщений по фильтру {0}{1} · страница {2} из {3}", fmt(r.total), r.more ? "+" : "", r.page, r.pages)
      + (r.default_days ? " · " + T("без дат — последние {0} суток", r.default_days) : "")), (r.errors || []).map(x => h("div", { class: "err" }, acText(x))));
    put(listBox, acTable([["Время (сервер)", x => dt(x.local)], ["Сервер", x => h("span", { class: "small" }, acText(x.server + (x.map !== null && x.map !== undefined ? " · " + T("карта {0}", x.map) : "")))],
      ["Канал", x => h("span", null, T(st.channels.find(c => c.code === x.channel) ? st.channels.find(c => c.code === x.channel).name : String(x.channel)),
        x.channel_name ? h("div", { class: "muted small" }, acText(x.channel_name)) : null)],
      ["Учётка", x => h("span", null, acAccount(x.uid, x.login), x.service ? h("span", null, " ", badge(T("служебная"), "")) : null, x.gm ? h("span", null, " ", badge("GM", "")) : null)],
      ["Персонаж", x => h("span", null, acChar(x.owner, x.slot, x.char), x.owner && x.uid && x.owner !== x.uid ? h("div", { class: "muted small" }, acText(T("хозяин №{0}", x.owner))) : null)],
      ["Кому", x => x.to ? acText(x.to) : acText("—")],
      ["Текст", x => h("div", null, h("span", null, acText(x.chat_text)), chRaw(x))],
      ["Заглушка", x => chMuteBadge(x)], ["Переходы", x => chGo(x, st)]], r.rows), r.pages > 1 ? pager(r.page, r.pages, p => load(p)) : null);
  }
  put(formBox, h("div", { class: "card" }, h("h2", null, "Фильтр"),
    h("div", { class: "row" }, h("span", null, "С "), fromIn, h("span", null, " по "), toIn, accIn, charIn, mapIn, srvSel, muteSel),
    h("div", { class: "row" }, chBoxes.map(b => h("label", null, b.el, " ", T(b.c.name)))),
    h("div", { class: "row" }, textIn, h("label", null, rawIn, " байты text_raw"), fxNote, h("button", { type: "button", onclick: () => load(1) }, "Показать")),
    h("div", { class: "muted small" }, acText(T("Даты — по местному времени сервера; без дат — последние 2 суток. Поиск по тексту — без учёта регистра; без учётки и персонажа — в окне не больше 31 суток.")))),
    chMuteForm(st, q, () => { if (muteLoad) muteLoad(1); }));
  const muteLoad = chMutes(st, muteBox, m => { fx.mute_id = String(m.id); fx.char_uid = fx.char_slot = ""; fromIn.value = String(m.created || "").slice(0, 10); toIn.value = ""; showFx(); load(1); });
  load(1);
}
