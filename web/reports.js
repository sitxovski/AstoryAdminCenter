// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Жалобы игроков» (шаг А6.11, часть «жалобы», 22.11.2026; решение владельца №6 — канал жалоб = бот Discord;
// domains/reports.py, /api/reports/*, операции report.take / report.close / report.case / report.reply).
// Жалобы подаёт бот Oracle (/report в Discord) в базу панели AsdaAdmin. Здесь — очередь (новые / в работе / закрытые), карточка (жалоба, скриншоты,
// ссылки Discord, автор ↔ учётка игры, цель — ник → персонаж и учётка, другие жалобы на ту же цель и от того же автора, переходы в карточку учётки:
// лента журналов, античит, дела) и действия: взять, закрыть с итогом, открыть дело (форма case.open из web/cases.js, предзаполненная жалобой) или
// связать с делом по номеру, ответ автору через бота (только по кнопке, текст оператора).
// Всё из жалобы (ник, описание, имя Discord, ссылки, текст ответа) — НЕДОВЕРЕННЫЙ текст: только текстовыми узлами (acText), без T() и без HTML.
// Ссылка открывается, только если служба подтвердила её правило (discord.com/channels, вложения CDN Discord); скриншот — <img> из data: с типом
// картинки, который служба определила по сигнатуре. Общие помощники — app.js, acjournal.js (acText, acTable, acAccount, acChar, acQs), cases.js
// (csOpenForm, csOp, csNo).
"use strict";

const RP_STATUS = { new: "новая", taken: "в работе", closed: "закрыта" };
const RP_CAT = { cheat: "чит / бот", scam: "мошенничество", abuse: "оскорбления", rmt: "торговля за реальные деньги (RMT)", other: "другое" };
const RP_OUT = { action: "меры приняты", case: "передано в дело", no_violation: "нарушения нет", duplicate: "повтор", insufficient: "мало данных" };
const RP_REPLY = { queued: "ждёт бота", claimed: "бот взял", sent: "отправлено", failed: "не доставлено", unknown: "неизвестно — проверьте" };
const RP_IMG = ["image/png", "image/jpeg", "image/gif", "image/webp"];

function rpBadge(st) { return badge(T(RP_STATUS[st] || st), st === "new" ? "warn" : st === "taken" ? "ok" : ""); }
function rpNo(id) { return h("button", { type: "button", class: "ghost small mono", onclick: () => { location.hash = "#/reports?id=" + id; } }, acText("№" + id)); }
function rpCat(c) { return h("span", null, T(RP_CAT[c] || c)); }

// Действие жалобы: предпросмотр → подтверждение (текст и предупреждения службы) → запись с отпечатком состояния (expect).
async function rpOp(name, params, reload) {
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

async function rpShowFile(f) {
  let r;
  try { r = await api("/api/reports/file?" + acQs({ id: f.id })); } catch (e) { return notify(e.message, true); }
  if (RP_IMG.indexOf(r.mime) < 0 || !/^[A-Za-z0-9+/=]+$/.test(r.b64)) return notify(T("файл не картинка — не показывается"), true);
  await confirmWin(T("Скриншот {0}", f.name), [h("div", { class: "muted small mono" }, acText(r.name + " · " + fmt(r.size) + " B · sha256 " + r.sha256)),
    h("img", { src: "data:" + r.mime + ";base64," + r.b64, alt: "", style: { maxWidth: "100%", maxHeight: "70vh" } })], "Закрыть");
}

function rpLinks(links) {
  if (!links || !links.length) return acText("—");
  return h("div", { class: "small" }, links.map(l => h("div", null, l.ok && /^https:\/\//.test(l.url)
    ? h("a", { href: l.url, target: "_blank", rel: "noopener noreferrer" }, acText(l.url))
    : h("span", { class: "muted" }, acText(l.url), " ", badge(T("ссылка не по правилам — не открывается"), "warn")))));
}

function rpTargets(r) {
  if (!r.targets.length) return h("div", { class: "note" }, acText(T("Персонажа с ником «{0}» нет (ни в Charinfo, ни среди удалённых) — проверьте написание.", r.target)));
  return acTable([["Учётка", t => acAccount(t.uid, t.login)], ["Персонаж", t => t.deleted ? acText(t.name) : acChar(t.uid, t.idx, t.name)],
    ["Ур.", t => String(t.level === null || t.level === undefined ? "—" : t.level)],
    ["", t => h("span", null, t.deleted ? badge(T("удалён {0}", dt(t.deleted_at)), "warn") : null, t.service ? badge(T("служебная"), "") : null)],
    ["Переходы", t => h("span", null,
      h("button", { type: "button", class: "ghost small", onclick: () => { location.hash = "#/account/" + t.uid + "/feed"; } }, "Лента журналов"),
      r.can["players.view_net"] ? h("button", { type: "button", class: "ghost small", onclick: () => { location.hash = "#/account/" + t.uid + "/eac"; } }, "Античит учётки") : null,
      r.can["ac.view"] ? h("button", { type: "button", class: "ghost small", onclick: () => { location.hash = "#/cases?uid=" + t.uid; } }, "Дела учётки") : null,
      // ★ А6.12: сообщения учётки в журнале чата за период жалобы (7 суток до подачи — по сегодня)
      can("chat.view") ? h("button", { type: "button", class: "ghost small", onclick: () => { location.hash = "#/chat?" + acQs({ account: t.uid, from: chFrom(r.created, 7) }); } },
        "Сообщения в чате") : null)]], r.targets);
}

function rpReplies(r) {
  return acTable([["№", y => String(y.id)], ["Когда", y => dt(y.created)], ["Кто", y => y.by],
    ["Состояние", y => h("span", null, badge(T(RP_REPLY[y.state] || y.state), y.state === "sent" ? "ok" : y.state === "queued" || y.state === "claimed" ? "" : "bad"),
      y.result ? h("div", { class: "muted small" }, acText(y.result + " · " + dt(y.done))) : null)],
    ["Текст", y => h("pre", { class: "small" }, acText(y.text))]], r.replies);
}

// ---- действия карточки
function rpActions(r, reload) {
  if (!r.can["reports.handle"]) return null;
  const box = h("div", { class: "card" }, h("h2", null, "Разбор"));
  const row = h("div", { class: "row" });
  if (r.status === "new") row.append(h("button", { type: "button", onclick: () => rpOp("report.take", { id: r.id }, reload) }, "Взять в работу"));
  box.append(row);
  if (r.status !== "closed") {
    const outSel = sel(Object.entries(RP_OUT).map(([k, v]) => [k, T(v)]), r.case_no ? "case" : "action");
    const note = h("textarea", { rows: 2, maxlength: 500, class: "grow", placeholder: "итог разбора (видно в панели, автору не уходит)" });
    box.append(h("div", { class: "row" }, h("span", null, "Итог "), outSel, note,
      h("button", { type: "button", onclick: () => rpOp("report.close", { id: r.id, outcome: outSel.value, note: note.value }, reload) }, "Закрыть жалобу")));
    if (!r.case_no && r.can["ac.case"]) {
      const caseIn = h("input", { type: "text", maxlength: 12, class: "mono", placeholder: "AC-NNNN" });
      const formBox = h("div");
      box.append(h("div", { class: "row" },
        h("button", { type: "button", onclick: async () => {
          let L;
          try { L = await api("/api/cases/ladder"); } catch (e) { return notify(e.message, true); }
          if (!L.can_write) return put(formBox, h("div", { class: "note" }, acText(L.store_note || T("дела открываются только панелью на сервере"))));
          const t = r.targets.find(x => !x.deleted);
          const hyp = T("Жалоба №{0} из Discord ({1}, {2}): когда — {3}.", r.id, T(RP_CAT[r.category] || r.category), r.reporter_name, r.happened || "—") + "\n" + r.body;
          put(formBox, csOpenForm(L, t ? t.uid : "", async no => {
            await rpOp("report.case", { id: r.id, case: no }, reload);
          }, { title: T("Жалоба №{0}: {1} — {2}", r.id, T(RP_CAT[r.category] || r.category), r.target), char: t ? t.name : r.target, hypothesis: hyp }));
        } }, "Открыть дело"),
        h("span", null, " или связать с делом "), caseIn,
        h("button", { type: "button", class: "ghost", onclick: () => rpOp("report.case", { id: r.id, case: caseIn.value.trim() }, reload) }, "Связать")),
      formBox);
    }
  }
  const text = h("textarea", { rows: 3, maxlength: 1500, class: "grow", placeholder: "текст автору (уйдёт как есть, личным сообщением бота)" });
  box.append(h("h3", null, "Ответ автору"), h("div", { class: "row" }, text,
    h("button", { type: "button", onclick: () => rpOp("report.reply", { id: r.id, text: text.value }, reload) }, "Ответить автору")),
    h("div", { class: "muted small" }, acText(T("Бот на ПК отправит личное сообщение в течение минуты, если он запущен. Не больше {0} ответов на жалобу и {1} в час от одного оператора.",
      r.limits.replies_per_report, r.limits.replies_per_hour))));
  return box;
}

async function rpCard(id, my, box, reload) {
  put(box, h("div", { class: "muted" }, "Загружаю…"));
  let r;
  try { r = await api("/api/reports/show?" + acQs({ id })); } catch (e) { if (!stale(my)) put(box, errbox(e)); return; }
  if (stale(my)) return;
  const again = () => { rpCard(id, my, box, reload); if (reload) reload(); };
  const rep = r.reporter || {};
  put(box, h("div", { class: "card" }, h("h2", null, acText(T("Жалоба №{0}", r.id))),
    (r.errors || []).map(x => h("div", { class: "err" }, acText(x))),
    kv([["Состояние", h("span", null, rpBadge(r.status), r.taken_by ? acText(" " + T("ведёт {0} с {1}", r.taken_by, dt(r.taken))) : null)],
      ["Категория", rpCat(r.category)], ["На кого (ник)", h("span", { class: "mono" }, acText(r.target))],
      ["Когда (со слов автора)", acText(r.happened)], ["Подана", acText(dt(r.created) + " UTC")],
      ["Автор в Discord", h("span", null, acText(r.reporter_name + " · ID " + r.reporter_id))],
      ["Учётка автора", rep.linked ? h("span", null, rep.uid ? acAccount(rep.uid, rep.login) : acText(rep.login), acText(" @" + rep.handle),
        rep.list_banned ? h("span", null, " ", badge(T("в списке банов Discord с {0}", rep.list_banned), "bad")) : null)
        : h("span", { class: "muted" }, T("Discord не привязан к учётке игры"))],
      ["Дело", r.case ? h("span", null, csNo(r.case.case_no), r.case.found === false ? badge(T("нет в журнале дел"), "bad") : null,
        r.case.status ? acText(" " + r.case.status + " · " + (r.case.title || "")) : null) : acText("—")],
      ["Итог", r.outcome ? h("span", null, h("span", null, T(RP_OUT[r.outcome] || r.outcome)), acText(" · " + r.closed_by + " · " + dt(r.closed) + " · " + (r.outcome_note || ""))) : acText("—")]]),
    h("h3", null, "Описание"), h("pre", { class: "pv" }, acText(r.body)),
    h("h3", null, "Ссылки"), rpLinks(r.links),
    h("h3", null, "Скриншоты"), r.files.length ? acTable([["Файл", f => f.name], ["Тип", f => f.mime], ["Размер", f => fmt(f.size)], ["sha256", f => h("span", { class: "mono small" }, acText(f.sha256.slice(0, 16) + "…"))],
      ["", f => f.purged ? badge(T("удалён по сроку {0}", dt(f.purged)), "") : h("button", { type: "button", class: "small", onclick: () => rpShowFile(f) }, "Показать")]], r.files) : h("div", { class: "muted" }, "нет"),
    h("h3", null, "Цель: персонаж и учётка"), rpTargets(r),
    h("h3", null, acText(T("Другие жалобы на «{0}»: {1} (авторов {2})", r.target, r.same_target.total, r.same_target.authors))),
    acTable([["№", x => rpNo(x.id)], ["Состояние", x => rpBadge(x.status)], ["Категория", x => rpCat(x.category)], ["Автор", x => x.reporter_name], ["Подана", x => dt(x.created)]], r.same_target.rows),
    h("h3", null, acText(T("Другие жалобы этого автора: {0}", r.same_author.total))),
    acTable([["№", x => rpNo(x.id)], ["Состояние", x => rpBadge(x.status)], ["Категория", x => rpCat(x.category)], ["На кого", x => x.target], ["Подана", x => dt(x.created)]], r.same_author.rows),
    h("h3", null, "Ответы автору"), rpReplies(r)), rpActions(r, again));
}

async function viewReports(my, q) {
  q = q || new URLSearchParams();
  const listBox = h("div"), cardBox = h("div"), info = h("div", { class: "muted small" });
  const stSel = sel([["open", T("новые и в работе")], ["new", T("новые")], ["taken", T("в работе")], ["closed", T("закрытые")], ["all", T("все")]], q.get("target") ? "all" : "open");
  const catSel = sel([["", T("все категории")]].concat(Object.entries(RP_CAT).map(([k, v]) => [k, T(v)])), "");
  const tgtIn = h("input", { type: "text", maxlength: 20, placeholder: "ник (начало)", value: (q.get("target") || "").slice(0, 20) });   // ★ А6.12: переход из журнала чата
  const repIn = h("input", { type: "text", maxlength: 20, class: "mono", placeholder: "Discord ID автора" });
  const mineIn = h("input", { type: "checkbox" });
  const st = { page: 1 };
  async function load(page) {
    st.page = page || 1;
    put(info, acText(T("Загружаю…")));
    let r;
    try { r = await api("/api/reports/list?" + acQs({ status: stSel.value, category: catSel.value, target: tgtIn.value.trim(), reporter: repIn.value.trim(),
      mine: mineIn.checked ? "1" : "", page: st.page })); }
    catch (e) { if (!stale(my)) { put(info, errbox(e)); put(listBox); } return; }
    if (stale(my)) return;
    put(info, acText(T("Новых {0} · в работе {1} · закрытых {2} · по фильтру {3} · страница {4} из {5}", fmt(r.counts.new), fmt(r.counts.taken), fmt(r.counts.closed),
      fmt(r.total), r.page, r.pages)));
    put(listBox, acTable([["№", x => rpNo(x.id)], ["Состояние", x => rpBadge(x.status)], ["Категория", x => rpCat(x.category)],
      ["На кого", x => h("span", { class: "mono" }, acText(x.target))], ["Автор", x => x.reporter_name], ["Подана", x => dt(x.created)],
      ["Ведёт", x => x.taken_by], ["Итог", x => x.outcome ? h("span", null, T(RP_OUT[x.outcome] || x.outcome)) : acText("—")],
      ["Дело", x => x.case_no ? csNo(x.case_no) : acText("—")], ["Файлов", x => fmt(x.n_files)], ["Ответов", x => fmt(x.n_replies)]], r.rows),
      r.pages > 1 ? pager(r.page, r.pages, p => load(p)) : null);
  }
  mount(shell("#/reports", h("h1", null, "Жалобы игроков"), h("div", { class: "note" },
    acText(T("Жалобы игроков на игроков из Discord: бот принимает их командой /report (категория, ник, когда, описание, скриншоты) и пишет в базу панели. Разбор: взять, закрыть с итогом, открыть дело, ответить автору — ответ уйдёт личным сообщением бота только по кнопке."))),
    cardBox,
    h("div", { class: "card" }, h("h2", null, "Очередь"), h("div", { class: "row" }, h("span", null, "Показать "), stSel, catSel, h("span", null, "На кого "), tgtIn,
      h("span", null, "Автор "), repIn, h("label", null, mineIn, " мои"), h("button", { type: "button", onclick: () => load(1) }, "Показать")), info, listBox)));
  const id = q.get("id");
  if (id && /^\d+$/.test(id)) rpCard(id, my, cardBox, () => load(st.page));
  load(1);
}
