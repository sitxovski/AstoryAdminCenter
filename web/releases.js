// Copyright (c) 2026 @sitxovski (Discord)
// Админ-центр — «Выпуски» (шаг А7.1, 23.11.2026; решение владельца А7 №6 — панель только показывает статус, выпуск делается батниками DEPLOY
// на ПК и отсюда не запускается; domains/releases.py, /api/releases). Две части:
//   снаружи — указатели сервера обновлений (каналы alpha и launcher, version.json игры): версия, seq, min_version, прошлая версия, срок
//             подписи (предупреждение за 14 суток, «срочно» за 3) и проверка подписи от корня, вшитого в лаунчер;
//   с ПК    — последний снимок, который прислала консоль ПК (releases push / задание ПК release.push): releases.log, последняя сборка,
//             Inbox, итоги батников DEPLOY, ключи «есть / срок» (без ключей и путей), подписанное на ПК.
// Всё, что пришло от сервера обновлений и с ПК (версии, имена файлов, тексты ошибок батников), — НЕДОВЕРЕННЫЙ текст: только текстовыми
// узлами (acText), без T() и без HTML. Помощники — app.js и acjournal.js.
"use strict";

const RL_LEVEL = { ok: ["в порядке", "ok"], warn: ["скоро истекает", "warn"], urgent: ["срочно продлить", "bad"], expired: ["просрочена", "bad"],
  none: ["без срока", ""], bad: ["срок не разобран", "bad"] };
const RL_SIG = { ok: ["подпись верна", "ok"], bad: ["подпись НЕ сошлась", "bad"], unverified: ["подпись не проверена", "warn"] };
const RL_RUN = { done: ["ГОТОВО", "ok"], error: ["ОШИБКА", "bad"], stopped: ["остановлен", "warn"], unfinished: ["не завершён", "warn"],
  unread: ["не прочитан", "warn"] };
const rlBadge = (map, k) => { const x = map[k] || [String(k || "—"), ""]; return badge(T(x[0]), x[1]); };
const rlYes = v => v ? badge(T("есть"), "ok") : badge(T("нет"), "bad");
const rlSize = v => v === null || v === undefined ? "—" : v >= 1 << 30 ? T("{0} ГБ", (v / (1 << 30)).toFixed(2)) : T("{0} МБ", (v / (1 << 20)).toFixed(1));

function rlPointers(rows, remote) {
  return acTable([["Указатель", x => acText(x.name)], ["Версия", x => acText(x.version)], ["seq", x => acText(x.seq)],
    ["Мин. версия", x => acText(x.min_version)], ["Прошлая", x => acText(x.prev_version ? x.prev_version + " · seq " + x.prev_seq : "")],
    ["Подписан", x => acText(x.created)], ["Срок подписи", x => acText(x.expires)],
    ["Осталось", x => h("span", null, acText(x.days_left === null || x.days_left === undefined ? "—" : T("{0} сут", x.days_left)), " ", rlBadge(RL_LEVEL, x.level))],
    ["Подпись", x => h("span", null, rlBadge(RL_SIG, x.sig), x.error ? h("div", { class: "muted small" }, acText(x.error)) : null)],
    remote ? ["Манифест", x => acText(x.manifest ? x.manifest + "… · " + fmt(x.manifest_size) : "")] : ["", () => acText("")]], rows || []);
}

function rlRuns(rows) {
  return acTable([["Где", x => acText(x.area === "patch" ? "Patch" : "Build")], ["Батник", x => acText(x.kind)], ["Начат", x => acText(x.started)],
    ["Итог", x => rlBadge(RL_RUN, x.result)], ["Минут", x => acText(x.minutes === null || x.minutes === undefined ? "—" : x.minutes)],
    ["Ошибка", x => h("span", { class: "small" }, acText(x.error))]], rows || []);
}

async function viewReleases(my) {
  const warnBox = h("div"), outBox = h("div"), pcBox = h("div"), info = h("div", { class: "muted small" });
  mount(shell("#/releases", h("div", { class: "row" }, h("h1", null, "Выпуски"),
      h("button", { type: "button", class: "ghost", onclick: () => load(true) }, "Обновить")),
    h("div", { class: "note" }, "Только статус. Выпуск, продление подписи и выгрузка делаются батниками DEPLOY на ПК владельца — из панели они не запускаются."),
    info, warnBox,
    h("div", { class: "card" }, h("h2", null, "Снаружи: сервер обновлений"), outBox),
    h("div", { class: "card" }, h("h2", null, "С ПК владельца"), pcBox)));
  async function load(force) {
    put(info, acText(T("Загружаю…")));
    let r;
    try { r = await api("/api/releases" + (force ? "?force=1" : "")); } catch (e) { if (!stale(my)) { put(info, errbox(e)); put(outBox); put(pcBox); } return; }
    if (stale(my)) return;
    const o = r.outside || {}, k = o.keyring || {}, pc = r.pc || {};
    put(info, acText(T("Сервер обновлений {0} · снято {1} · предупреждение о сроке подписи за {2} сут, «срочно» за {3} сут", o.url, o.at, o.warn_days, o.urgent_days)));
    put(warnBox, (r.warnings || []).length ? h("div", { class: "card" }, h("h2", null, "Предупреждения"),
      (r.warnings || []).map(w => h("div", { class: "note" }, acText(w)))) : h("div", { class: "muted small" }, "Предупреждений нет."));
    put(outBox, h("div", { class: "muted small" }, acText(T("keyring seq {0} · подпись корнем: ", k.seq)), rlBadge(RL_SIG, k.sig),
        k.error ? h("span", null, " ", acText(k.error)) : null,
        acText(" · " + T("ключи выпуска: {0}", (k.keys || []).map(x => x.id + (x.revoked ? " (" + T("отозван") + ")" : "")).join(", ") || "—"))),
      rlPointers(o.pointers, true),
      h("div", { class: "muted small" }, "Продлить подпись канала alpha и version.json — DEPLOY\\Patch\\6_Resign.bat, затем 4_Upload.bat. У канала launcher батника нет: asda_release.py --channel launcher resign и upload."));
    if (!pc.have) {
      put(pcBox, h("div", { class: "note" }, acText(pc.error || T("ПК ещё не присылал данные"))),
        h("div", { class: "muted small" }, "Прислать с ПК: python AstoryAdminCenter\\asda_admin.py releases push (или задание ПК release.push в «Заданиях»)."));
      return;
    }
    const s = pc.snap || {}, ks = s.keys || {}, lb = s.latest_build || {}, ib = s.inbox || {};
    put(pcBox,
      h("div", { class: "row" }, acText(T("Снимок №{0}: собран {1} UTC на {2} · ПК присылал {3} UTC (раз {4})", pc.id, pc.collected_utc, pc.host, pc.seen_utc, pc.seen_count)),
        " ", pc.stale ? badge(T("данные ПК старше {0} ч", r.pc_stale_h), "warn") : badge(T("свежие"), "ok")),
      (s.errors || []).map(x => h("div", { class: "err" }, acText(x))),
      h("h3", null, "Последняя сборка"),
      h("div", null, acText(lb.build ? T("сборка {0} · режим {1} · записана {2}", lb.build, lb.mode, lb.written) : "—")),
      h("h3", null, "Выпуски (releases.log)"),
      acTable([["Время (UTC)", x => acText(x.time)], ["Версия", x => acText(x.version)], ["seq", x => acText(x.seq)], ["Файлов", x => acText(fmt(x.files))],
        ["Размер", x => acText(rlSize(x.size))], ["Новых байт", x => acText(rlSize(x.new))], ["Сборка", x => acText(x.build)],
        ["Манифест", x => acText(x.manifest ? x.manifest + "…" : "")]], s.releases || []),
      h("h3", null, "Итоги батников: последний прогон каждого"), rlRuns(s.runs_by_kind),
      h("h3", null, "Последние прогоны"), rlRuns(s.runs_recent),
      h("h3", null, "Inbox (DEPLOY\\Patch\\Inbox)"),
      ib.error ? h("div", { class: "err" }, acText(ib.error)) : null,
      acTable([["Имя", x => acText(x.name)], ["Вид", x => acText(x.type)], ["Размер", x => acText(rlSize(x.size))], ["Изменён", x => acText(x.mtime)]], ib.items || []),
      h("div", { class: "muted small" }, acText(ib.state ? T("обработан {0} · конфигурация {1} · была готовой EAC-сборкой: {2}", ib.state.processed, ib.state.config,
        ib.state.was_eac_ready ? T("да") : T("нет")) : T("клиент в Inbox не обработан (или Inbox пуст — патч берёт последнюю релизную сборку)"))),
      h("h3", null, "Ключи выпуска"),
      acTable([["Что", x => acText(x[0])], ["Состояние", x => x[1]]], [
        [T("корневой ключ {0}", ks.root_id || "—"), h("span", null, ks.root_pinned ? badge(T("= вшитому в лаунчер"), "ok") : badge(T("не совпадает с лаунчером"), "bad"),
          " ", acText(T("закрытая часть на ПК: ")), rlYes(ks.root_private))],
        [T("keyring seq {0}", ks.keyring_seq), h("span", null, rlBadge(RL_SIG, ks.keyring_sig), " ", acText(T("срок: {0}", ks.keyring_expires || T("не задан"))))],
        ...(ks.release_keys || []).map(x => [T("ключ выпуска {0}", x.id), h("span", null, x.revoked ? badge(T("отозван"), "warn") : badge(T("действует"), "ok"),
          " ", acText(T("закрытая часть на ПК: ")), rlYes(x.private))]),
        [T("резервные копии ключей"), h("span", null, acText(fmt(ks.backups)), ks.backup_newest ? acText(" · " + T("последняя {0}", ks.backup_newest)) : null,
          ks.backups ? null : h("span", null, " ", badge(T("нет"), "warn")))],
        [T("ключ выгрузки на сервер обновлений"), rlYes(ks.upload_key)]]),
      h("div", { class: "muted small" }, "Ключи выпуска Ed25519 бессрочны. Срок есть только у подписи каналов и keyring."),   // ★ р74 К-2
      h("h3", null, "Подписано на ПК (Releases)"), rlPointers((s.local || {}).pointers, false),
      h("h3", null, "История снимков"),
      acTable([["№", x => acText("№" + x.id)], ["Записан (UTC)", x => acText(x.pushed_utc)], ["ПК присылал (UTC)", x => acText(x.seen_utc)],
        ["Раз", x => acText(x.seen_count)], ["ПК", x => acText(x.host)]], pc.history || []));
  }
  load(false);
}
