# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""notes.py — «Заметки к выпуску»: черновик changelog для игроков и публикация в форум Discord updates (шаг А7.7, 24.11.2026; решение
владельца А7 №7 — черновик заметок для игроков в панели и кнопка «Опубликовать»; №2 — тексты EN / RU / AR пишутся руками, канал и роль
выбираются; разбор Reports/admin_center/research_a7_releases_20261123.md §3 А7.7; отчёт impl_a7_releases_20261123.md §А7.7 и
«Исправления по ревизии 82»).

ОТКУДА ТЕКСТ. Changelog лежит на ПК владельца (Docs\\Changelog, файлы только дописываются, текущий назван в
  Docs\\Process\\AGENT_RULES_PORT.md «Changelog (текущий)»). Сервер ПК не видит, SMB не используется: консоль ПК (asda_admin.py notes push
  или задание ПК notes.push в «Заданиях») читает текущий файл и пишет его как есть в AsdaAdmin adm.NotesSnap процедурой adm.NotesSnapPut
  логином asda_admin по VPN — тот же путь, что снимок выпуска А7.1. Тот же файл и md5 — только отметка «ПК присылал». Панель changelog НЕ
  пишет: ни файл, ни снимок.
РАЗБОР (parse). Запись changelog — строка «- …» с начала строки и всё до следующей такой строки, заголовка «## …» или «---».
  ★ р83 В-1 — КЛЮЧ: 16 hex sha1 от нормализованного заголовка первой строки: жирная часть (если она не одни метки) или вся строка, без **,
  без меток […], без скобок «перенесено …» и без ВСЕХ скобок статуса в конце («(клиент, следующий выпуск)», «(сервер, уже действует …)»),
  пробелы схлопнуты, без регистра. Дата раздела в ключ НЕ входит (дата, оставшаяся в самом заголовке, входит). Так перенос в новый файл со
  сменой метки, скобки статуса и раздела ключ не меняет (строки 230 и 920 файла 2026-11-16). Одинаковые заголовки различаются порядковым
  номером. Второй признак — хэш нормализованного «Что стало» (what_hash): запись с другим ключом, но тем же «Что стало», что у
  опубликованной, помечается «похоже на уже опубликованное» и не отмечается по умолчанию (решает оператор). Ключ прежней формулы (р82)
  считается для перевода сохранённых публикаций и реестра на новый (adm.NotesEntrySync). ПРАВИЛО для changelog: при переносе записи в новый
  файл первую строку не менять (отметку «перенесено» писать в теле) — тогда ключ стабилен и без этих эвристик.
  Вид: client, server, release (метка [ВЫПУСК] и alpha-… — ★ р82 М-1), clarify (уточнение / исправление записи, исходная не найдена), service
  (админ-центр, инструменты, сборка, проверки, шлюз, бот, прочее). Уточнение, у которого найдена исходная запись, получает её вид и состояние.
  Состояние: клиент — «в выпуске alpha-…» (строка выпуска после записи или «вошло в alpha-…»), иначе «ещё не в выпуске»; сервер — «уже
  действует» или «ещё не действует», иначе «статус не указан».
  ★ р82 В-1 — ЧУВСТВИТЕЛЬНОЕ: признаки античита / EAC / автоблока / режима Mode, порогов и пределов, номеров персонажей и учёток, стойки и
  процессов сервера, номеров патчей, админ-центра, шлюза gp7, таблиц и баз, IP и путей — в заголовке или «Что стало». Такая запись по
  умолчанию без галочки, помечена, и «Заполнить RU» её не переносит (оператор пишет своими словами). ★ р83 М-1: и у остальных записей из
  RU-заготовки выброшены отдельные пункты с внутренними деталями (LEAK_RX / SENS_RX) и с фрагментами в `…`. Галочка по умолчанию — выпуск, клиент в выпуске,
  сервер «уже действует», если запись не чувствительная и не скрыта.
РЕЕСТР (★ р82 В-2). Каждый снимок записывается и в постоянный реестр adm.NotesEntry по ключу. Неопубликованная запись прежнего файла остаётся
  в списке («из файла …»), пока её не опубликуют или не скроют (notes.hide, откат — вернуть).
«НЕ ОПУБЛИКОВАНО». Учёт — adm.NotesPost / adm.NotesPostEntry по ключу записи; «опубликовано» выводится из итога бота в adm.Outbox (статус 2,
  не проверочная, не удалено), а не из постановки в очередь. Занята — опубликована, ждёт бота или «итог неизвестен» (★ р82 М-2: до решения
  оператора notes.resolve «ветки нет» / «ветка есть»). Ошибка публикации освобождает записи сразу; повтор записи очереди вида notes запрещён —
  повтор = новая публикация. Отметка «уже опубликовано вне панели» (notes.mark) — для опубликованного руками; снимается откатом.
ПУБЛИКАЦИЯ (notes.publish, community.post — owner, admin). Одна запись adm.Outbox вида notes в форум updates (новая ветка, имя — заголовок,
  ★ р82 М-3: за сутки не повторяется — бот ищет свою прерванную ветку по имени), роль Patch Ping или без упоминания; текст — как у объявлений
  А7.4 (outbox.compose), пределы Discord — 2000 / 100 знаков UTF-16. Публикует бот Oracle на ПК (outbox_bot.py). Отметка «тест» — бот
  отмечает «тест» и Discord не вызывает. Откат: ждёт бота или ошибка — отмена записи очереди; опубликовано — удаление ветки (только owner);
  «итог неизвестен» — только решением оператора (возможен дубль). Кто уже прочитал — не вернуть.
ОПЕРАЦИИ: notes.push (задание ПК), notes.resync (перечитать реестр по последнему снимку), notes.draft, notes.hide (откат), notes.mark (откат),
  notes.publish (откат), notes.resolve («итог неизвестен»: ветки нет / ветка есть).
Побочных эффектов при импорте нет.
"""
import datetime
import hashlib
import json
import os
import re
import socket

from core import config, db
from core.ops import Operation, OpRefused, register
from domains import outbox

CHANNEL = "updates"                      # только форум updates (решение №7: «публикация в forum updates»)
ROLES = {"patch": "Patch Ping", "": "без упоминания"}   # роль — Patch Ping или без упоминания
TTL_DEF = 1440                           # срок годности записи очереди, мин (заметки не срочные: бот на ПК может быть выключен до суток)
SNAP_MAX = 4000000                       # = CK_adm_NotesSnap_size
DRAFT_MAX = 100000                       # = CK_adm_NotesDraft_size
KEYS_MAX = 200                           # записей changelog в одной публикации / отметке
NOTE_MIN, NOTE_MAX = 3, 200              # причина отметки «опубликовано вне панели» / скрытия / решения «итог неизвестен»
PC_STALE_H = 24                          # снимок старше — пометка «changelog с ПК устарел»
BODY_MAX = 6000                          # полный текст записи на экране
STUCK_MIN = outbox.STUCK_MIN             # бот взял и молчит дольше — «итог неизвестен» (как в «Очереди Discord»)
FILE_RX = re.compile(r"^CHANGELOG_\d{4}-\d{2}-\d{2}(?:_\d+)?\.md$")                    # имя файла changelog
CURRENT_RX = re.compile(r"Changelog \(текущий\):\s*`[^`]*?(CHANGELOG_[0-9_-]+\.md)`")  # строка текущего changelog в правилах агентов
NOT_INSTALLED = "таблиц заметок нет (sql/adminc_31_notes.sql не установлен)"
NO_SNAP = "changelog с ПК ещё не присылался — на ПК: python AstoryAdminCenter\\asda_admin.py notes push (или задание ПК notes.push)"
PUT_CODES = {1: outbox.PUT_CODES[1], 2: outbox.PUT_CODES[2], 3: outbox.PUT_CODES[3],
             4: "поля заметок не прошли проверку базы (роль, длина, срок, @everyone / @here)",
             5: "запись changelog уже опубликована или ждёт бота — снимите её галочку и обновите страницу",
             6: "публикации заметок нет или она снята — обновите страницу",
             7: "ветка с таким заголовком за сутки уже была — дайте другой заголовок, например «… (часть 2)»"}   # коды adm.NotesPublishPut / EntryPut
_UNKNOWN_ERR = ("итог неизвестен", "проверьте канал")    # тексты бота «итог неизвестен» (outbox_bot.Worker.one) — = LIKE в adm.NotesEntryPut
# признаки секрета в тексте changelog: такой снимок не отправляется (changelog секретов не держит — правило, это страховка; ★ р82 М-5 шире)
SECRET_RX = ((re.compile(r"[MNO][A-Za-z\d_-]{23,25}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,}"), "токен Discord"),
             (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), "токен Telegram"),
             (re.compile(r"-----BEGIN [A-Z ]*KEY-----"), "закрытый ключ"),
             (re.compile(r"(?i)\b(?:password|passwd|pwd|пароль|token|secret|api[_-]?key|apikey|client[_-]?secret|access[_-]?key)\s*[:=]\s*[^\s,;)]{6,}"),
              "пароль или ключ в виде «имя=значение»"),
             (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}"), "токен Bearer"),
             (re.compile(r"(?i)(?:Server|Data Source)\s*=[^;\n]+;[^\n]*?(?:Pwd|Password)\s*=\s*[^;\s]+"), "строка подключения с паролем"),
             (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "ключ AWS"))
_IP = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")                                       # IPv4
_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/][^\s`'\"«»)]*|[\\/]Users[\\/][^\s`'\"«»)]*|\\\\[A-Za-z0-9][^\s`'\"«»)]*")   # путь Windows / UNC
# ★ р82 В-1: признаки «чувствительного» — внутренности защиты и стойки, данные игроков, внутренние имена (по заголовку и «Что стало»)
SENS_RX = ((re.compile(r"(?i:античит)|\bEAC\b|\bEacServer\b|(?i:easy anti-?cheat)"), "античит / EAC"),
           (re.compile(r"(?i)автоблок"), "автоблок"),
           (re.compile(r"\bMode\s*=\s*\d"), "режим Mode"),
           (re.compile(r"(?i)порог|поблажк|\bпредел"), "пороги и пределы"),
           (re.compile(r"\b\d{4,}/\d{1,3}\b|(?i:(?:учётк|персонаж)\w*\s+№?\s?\d{3,})"), "номер персонажа или учётки"),
           (re.compile(r"(?i)процесс\w*\s+стойк|\bстойк[аиуе]\b|GameServer|NpcServer|LoginManager|LoginPatch|AsdaPatch|SrvDbPatch|DBPatch|AddonNPC"),
            "стойка и процессы сервера"),
           (re.compile(r"\bP\d{2,3}\b|\bL\d{2}\b"), "номер серверного патча"),
           (re.compile(r"(?i)шлюз|\bgp7\b|переподключ"), "шлюз gp7 и его процессы"),      # ★ р83 М-1
           (re.compile(r"(?i)админ-центр|мост\w*\s+админ"), "админ-центр"),
           (re.compile(r"\b(?:dbo|adm|ac|san|chat|joylog1)\.\w+|\bJoy1\b|AsdaStoryLogin|AsdaAdmin\b|\bSQL\b"), "таблица или база"),
           (_IP, "IP-адрес"), (_PATH, "путь к файлу"))
# признаки внутренних деталей в тексте для игроков: предупреждение в предпросмотре (решает оператор) — те же, что «чувствительное», и ещё
LEAK_RX = SENS_RX + ((re.compile(r"(?i)\b[\w-]+\.(?:py|sql|cpp|h|bat|ps1|ini|json|md|log|dll|exe)\b"), "имя файла"),
                     (re.compile(r"(?i)\bport/|\bTools/|_backup"), "внутреннее имя проекта или базы"),
                     (re.compile(r"\b[0-9a-f]{12,}\b"), "хэш или номер сборки"))
_SEC = re.compile(r"^##\s+(.*)$")                                          # заголовок раздела changelog
_DATE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")                       # ДД.ММ.ГГГГ
_DATE_SHORT = re.compile(r"\((\d{2})\.(\d{2})\b(?!\.\d)")                  # «(ДД.ММ)» без года — год берётся из раздела
_REL_HEAD = re.compile(r"ВЫПУСК клиента\s+(alpha-[0-9A-Za-z.\-]+)")        # заголовок раздела выпуска
_ALPHA = re.compile(r"alpha-\d[0-9A-Za-z.\-]*")                            # номер выпуска клиента
_IN_REL = re.compile(r"вошло в (alpha-[0-9A-Za-z.\-]+?)(?=[;,)\]\s]|$)")   # «вошло в alpha-…» в метке
_TAGS = re.compile(r"^(?:\*\*)?((?:\[[^\]]+\]\s*)+)")                      # метки «[…]» в начале строки
_CLAR = re.compile(r"(?i)^(?:уточнение|исправление)\s+(?:к\s+)?(?:записи|пункту)")    # уточнение / исправление записи
_QUOTE = re.compile(r"«([^»]{6,})»")                                       # цитата исходной записи
_KEY = re.compile(r"^[0-9a-f]{16}$")                                       # ключ записи
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")                            # управляющие символы


def _norm(s):
    """Пробелы схлопнуты, края обрезаны."""
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _plain(s):
    """Строка для игрока: без **жирного** и с одним пробелом."""
    return _norm(str(s or "").replace("**", ""))


def key_text_r82(head):
    """Текст ключа ревизии 82 (первая строка без **, меток […] и скобок «перенесено …») — только для перевода прежних ключей."""
    t = str(head or "").replace("**", "")
    t = re.sub(r"\[[^\]]*\]", " ", t)
    t = re.sub(r"\([^()]*перенес[^()]*\)", " ", t, flags=re.I)
    return _norm(t).strip(" .:—-").casefold()


def key_text(head):
    """★ р83 В-1: текст ключа — заголовок первой строки (жирная часть, если она не одни метки, иначе вся строка) без **, меток […], скобок
    «перенесено …» и всех скобок статуса в конце; пробелы схлопнуты, без регистра."""
    h = str(head or "")
    m = re.match(r"\*\*(.+?)\*\*", h)
    if m and not re.fullmatch(r"(?:\[[^\]]+\]\s*)+", m.group(1).strip()):
        h = m.group(1)
    t = h.replace("**", "")
    t = re.sub(r"\[[^\]]*\]", " ", t)
    t = re.sub(r"\([^()]*перенес[^()]*\)", " ", t, flags=re.I)
    t = _norm(t).rstrip(" .:—-")
    while True:                                   # все скобки в конце заголовка — статус («(…; …)»), в ключ не входят
        u = re.sub(r"\s*\([^()]*\)$", "", t).rstrip(" .:—-")
        if u == t or not u:
            break
        t = u
    return _norm(t).strip(" .:—-").casefold()


def entry_key(head, date=None, n=1):
    """Устойчивый ключ записи: 16 hex sha1 (нормализованный заголовок [+ порядковый номер одинаковых]). date — не используется (★ р83 В-1:
    дата раздела в ключ не входит, дата в самом заголовке уже в нём)."""
    src = key_text(head) + ("" if n <= 1 else "|%d" % n)
    return hashlib.sha1(src.encode("utf-8")).hexdigest()[:16]


def entry_key_prev(head, date, n=1):
    """Ключ ревизии 82 (нормализованная строка + дата записи) — только для перевода сохранённых публикаций и реестра на новый ключ."""
    src = key_text_r82(head) + "|" + (date or "") + ("" if n <= 1 else "|%d" % n)
    return hashlib.sha1(src.encode("utf-8")).hexdigest()[:16]


def what_hash(lines):
    """★ р83 В-1: второй признак записи — 16 hex sha1 нормализованного «Что стало» (пусто — "")."""
    t = _norm(" ".join(lines or [])).casefold()
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:16] if t else ""


_TICKS = re.compile(r"`[^`]*`")                    # фрагменты в обратных кавычках — внутренние имена


def ru_lines(what):
    """★ р83 М-1: пункты «Что стало» для RU-заготовки — без пунктов с фрагментами в `…` и с внутренними деталями (LEAK_RX / SENS_RX) →
    (пункты, сколько выброшено)."""
    out, cut = [], 0
    for w in what:
        v = _norm(w).strip(" ,;:")
        if not v or _TICKS.search(v) or any(rx.search(v) for rx, _w in LEAK_RX):   # пункт с `…` — технический целиком (без «как в .»)
            cut += 1
            continue
        out.append(v)
    return out, cut


def _date_of(text):
    """Первая дата ДД.ММ.ГГГГ в тексте или ""."""
    m = _DATE.search(text or "")
    return "%s.%s.%s" % m.groups() if m else ""


def _date_entry(head, sdate):
    """★ р82 В-2: дата записи — ДД.ММ.ГГГГ из первой строки; «(ДД.ММ)» — с годом раздела; иначе дата раздела."""
    d = _date_of(head)
    if d:
        return d
    m = _DATE_SHORT.search(head or "")
    if m and sdate:
        return "%s.%s.%s" % (m.group(1), m.group(2), sdate[-4:])
    return sdate or ""


def _title_of(head):
    """Заголовок записи: жирная часть первой строки (если это не одни метки), иначе первая строка; без «.» в конце, до 200 знаков."""
    m = re.match(r"\*\*(.+?)\*\*\s*(.*)$", head)
    if m:
        bold, rest = m.group(1).strip(), m.group(2).strip()
        t = bold if not re.fullmatch(r"(?:\[[^\]]+\]\s*)+", bold) else (bold + " " + rest)
    else:
        t = head
    t = _plain(t).rstrip(".")
    return t[:200]


def _classify(title, tags, head):
    """Вид записи → client | server | release | service (уточнения — отдельно, в parse)."""
    tl, gl = title.lower(), " ".join(tags).lower()
    if "выпуск" in gl and _ALPHA.search(head):            # ★ р82 М-1: «[ВЫПУСК] alpha-8.1.2-…» — выпуск и без слова «выложен»
        return "release"
    if any(w in gl for w in ("инструменты", "админка", "сборка", "проверки")):
        return "service"
    if tl.startswith(("админ-центр", "шлюз", "бот")):
        return "service"
    if tl.startswith("клиент") or "клиент" in gl:
        return "client"
    if tl.startswith("сервер"):
        return "service" if "админ-центр" in tl else "server"     # «Сервер и админ-центр: …», «мост админ-центра» — инструменты администрации
    return "service"


def _server_status(text):
    """Состояние серверной записи по её словам → live | pending | unknown."""
    s = text.lower()
    if "не выложено" in s or "следующий выпуск" in s or "не выложен" in s:
        return "live" if "уже действует" in s else "pending"
    if "уже действует" in s or "выложено" in s or "выложен" in s or "действует" in s or "применено" in s:
        return "live"
    return "unknown"


def _what(head, body):
    """Что стало — строки для игрока (RU-предзаполнение): пункты блока «Что стало», иначе пункты записи без «Причины», иначе первая строка
    без меток и без «Причина: …»."""
    out, on, seen_what = [], False, False
    for ln in body:
        st = ln.strip()
        if st.startswith("Что стало"):
            on, seen_what = True, True
            continue
        if st.startswith("Причина") or st.startswith("- Причина"):
            if seen_what or out:
                break
            continue
        if on and st.startswith("- "):
            out.append(_plain(st[2:]))
        elif on and st and out and not st.startswith("- ") and ln.startswith("    "):
            out[-1] += " " + _plain(st)
    if not seen_what:
        for ln in body:
            st = ln.strip()
            if st.startswith("Причина") or st.startswith("- Причина"):
                break
            if st.startswith("- "):
                out.append(_plain(st[2:]))
    if not out:
        t = _plain(_TAGS.sub("", head))
        t = re.split(r"\s+Причина:", t)[0].strip()
        if t:
            out.append(t)
    return [x for x in out if x]


def sensitive_in(*texts):
    """★ р82 В-1: признаки «чувствительного» → [вид] (пусто — нет)."""
    t = "\n".join(x or "" for x in texts)
    return [what for rx, what in SENS_RX if rx.search(t)]


def mask(s):
    """★ р82 М-5: IP-адреса и пути в тексте → «[IP]» / «[путь]» (RU-заготовка всегда, полный текст — для всех, кроме owner)."""
    return _PATH.sub("[путь]", _IP.sub("[IP]", str(s or "")))


def _source_of(x, done):
    """★ р82 М-1: исходная запись уточнения — по цитате «…» в заголовке (последняя раньше с таким текстом), «записи выше» — предыдущая."""
    m = _QUOTE.search(x["title"])
    if m:
        q = m.group(1).strip(" …").casefold()
        for y in reversed(done):
            if q and q in y["title"].casefold() and y["key"] != x["key"]:
                return y
    if "выше" in x["title"].lower() and done:
        return done[-1]
    return None


def parse(text):
    """Текст changelog → [запись] в порядке файла: key, key_v1 (ключ прежней формулы — для перевода), date, section, head, title, area, status,
    release, sens, what_hash, visible, default, ru, ru_cut (сколько пунктов выброшено из RU), body, of_key / of_title (исходная запись уточнения)."""
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    entries, cur, section, sdate, srel = [], None, "", "", ""

    def close():
        """Закончить текущую запись."""
        if cur is not None:
            entries.append(cur)
    for ln in lines:
        m = _SEC.match(ln)
        if m:
            close()
            cur = None
            section = _norm(m.group(1))
            sdate = _date_of(section)
            r = _REL_HEAD.search(section)
            srel = r.group(1) if r else ""
            if srel:
                entries.append({"_release_mark": srel})
            continue
        if ln.strip() == "---":
            close()
            cur = None
            continue
        if ln.startswith("- "):
            close()
            cur = {"head": ln[2:].rstrip(), "body": [], "section": section, "sdate": sdate, "srel": srel}
            continue
        if cur is not None:
            cur["body"].append(ln.rstrip())
    close()
    out, seen, seen1, pend = [], {}, {}, []
    for e in entries:
        if "_release_mark" in e:
            for x in pend:                        # клиентские записи до строки выпуска вошли в этот выпуск
                if x["area"] == "client" and x["status"] == "unreleased":
                    x["release"], x["status"] = e["_release_mark"], "released"
            pend = []
            continue
        head = e["head"]
        date = _date_entry(head, e["sdate"])          # дата для экрана (в ключ не входит)
        k0 = key_text(head)
        seen[k0] = seen.get(k0, 0) + 1
        k1 = (key_text_r82(head), date)
        seen1[k1] = seen1.get(k1, 0) + 1
        tg = _TAGS.match(head)
        tags = re.findall(r"\[([^\]]+)\]", tg.group(1)) if tg else []
        title = _title_of(head)
        area = _classify(title, tags, head)
        full = head + "\n" + "\n".join(e["body"])
        what = _what(head, e["body"])
        x = {"key": entry_key(head, None, seen[k0]), "key_v1": entry_key_prev(head, date, seen1[k1]), "date": date, "section": e["section"],
             "head": head, "title": title, "area": area, "release": "", "status": "", "ru": "", "ru_cut": 0, "body": full.strip()[:BODY_MAX],
             "of_key": "", "of_title": "", "sens": sensitive_in(title, "\n".join(what)), "what_hash": what_hash(what)}
        if _CLAR.match(title):
            src = _source_of(x, out)
            if src:
                x.update(area=src["area"], status=src["status"], release=src["release"], of_key=src["key"], of_title=src["title"])
                x["sens"] = list(dict.fromkeys(x["sens"] + src["sens"]))     # чувствительность исходной записи переходит на уточнение
            else:
                x.update(area="clarify", status="unknown")
        elif area == "client":
            m = _IN_REL.search(title + " " + " ".join(tags))
            if m:
                x["release"], x["status"] = m.group(1), "released"
            else:
                x["status"] = "unreleased"
                pend.append(x)
        elif area == "server":
            x["status"] = _server_status(title + " " + " ".join(tags))
        elif area == "release":
            m = _REL_HEAD.search(e["section"])
            a = _ALPHA.search(head)
            x["release"] = a.group(0) if a else (m.group(1) if m else "")
            x["status"] = "released"
        else:
            x["status"] = "service"
        if x["area"] == "release" and x["release"]:
            x["ru"] = "• Выпуск клиента %s" % x["release"]
            x["sens"] = []                        # RU выпуска — только номер выпуска, подробности строки выпуска игрокам не идут
        else:
            ru, cut = ru_lines(what)
            x["ru"], x["ru_cut"] = mask("\n".join("• " + w for w in ru)), cut
        out.append(x)
    for x in out:
        x["visible"] = x["area"] in ("client", "server", "release", "clarify")
        x["default"] = (not x["sens"]) and (x["area"] == "release" or (x["area"] == "client" and x["status"] == "released")
                                            or (x["area"] == "server" and x["status"] == "live"))
    return out


def last_release(entries):
    """Последний выпуск клиента в файле (по строкам выпуска) или ""."""
    rel = [x["release"] for x in entries if x["area"] == "release" and x["release"]]
    return rel[-1] if rel else ""


def secrets_in(text):
    """Признаки секрета в тексте → [вид] (пусто — чисто)."""
    return [what for rx, what in SECRET_RX if rx.search(text or "")]


def leaks_in(*texts):
    """Признаки внутренних деталей в тексте для игроков → [вид] без повторов (для предупреждения)."""
    t = "\n".join(x or "" for x in texts)
    return list(dict.fromkeys(what for rx, what in LEAK_RX if rx.search(t)))


# ── ПК: снимок changelog ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def pc_dir():
    """Каталог changelog и файл правил агентов на ПК (через asda_paths — правило проекта). На сервере — PortCodeError."""
    import sys
    tools = config.port_code(os.path.join(os.path.dirname(config.HERE), "AstoryClient", "Tools"))
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import asda_paths as P                    # noqa: E402 — модуль путей проекта без побочных эффектов
    return os.path.join(P.PORT_DOCS, "Changelog"), os.path.join(P.PORT_DOCS, "Process", "AGENT_RULES_PORT.md")


def current_file(ch_dir, rules_path):
    """Имя текущего changelog: из правил агентов («Changelog (текущий): `…`»), иначе самый новый CHANGELOG_ГГГГ-ММ-ДД[_N].md."""
    try:
        with open(rules_path, encoding="utf-8") as f:
            m = CURRENT_RX.search(f.read())
        if m and FILE_RX.match(m.group(1)) and os.path.isfile(os.path.join(ch_dir, m.group(1))):
            return m.group(1)
    except OSError:
        pass
    if not os.path.isdir(ch_dir):                      # ★ 25.11 (М-10): публичный клон — каталога Docs/Changelog нет
        raise OpRefused("нет каталога changelog %s — заметки к выпуску собираются из Docs/Changelog рабочей среды" % ch_dir)
    names = sorted(n for n in os.listdir(ch_dir) if FILE_RX.match(n))
    if not names:
        raise OpRefused("в каталоге changelog нет файлов CHANGELOG_ГГГГ-ММ-ДД.md")
    return names[-1]


def pc_collect(ch_dir=None, rules_path=None, now=None):
    """Снимок текущего changelog на ПК → dict(file, text, md5, host, collected_utc). Только ПК."""
    if ch_dir is None:
        ch_dir, rules_path = pc_dir()
    name = current_file(ch_dir, rules_path or "")
    with open(os.path.join(ch_dir, name), encoding="utf-8") as f:
        text = f.read()
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return {"file": name, "text": text, "md5": hashlib.md5(text.encode("utf-8")).hexdigest(), "host": socket.gethostname()[:64],
            "collected_utc": now.strftime("%Y-%m-%d %H:%M:%S")}


def sync_registry(cn, snap_id, file_name, entries):
    """★ р82 В-2: записи снимка → постоянный реестр adm.NotesEntry (процедурой; прежние ключи публикаций переводятся на новые) → число записей.
    ★ р84 Н-2: в начале отметка полноты снимка сбрасывается — оборванная запись не оставит прежнюю отметку."""
    db.admin_rows(cn, "SET NOCOUNT ON; EXEC adm.NotesSnapDone ?, NULL", (int(snap_id),))
    for x in entries:
        db.admin_rows(cn, "SET NOCOUNT ON; EXEC adm.NotesEntrySync ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
                      (x["key"], x["key_v1"], x["date"] or "", x["title"][:200], x["area"], x["status"][:12], x["release"][:40] or None,
                       ", ".join(x["sens"])[:300] or None, x["ru"], x["body"], file_name, int(snap_id), x["what_hash"] or None))
    # ★ р83 М-4: отметка «реестр по снимку записан целиком» — последним шагом; без неё панель предупреждает
    db.admin_rows(cn, "SET NOCOUNT ON; EXEC adm.NotesSnapDone ?, ?", (int(snap_id), len(entries)))
    return len(entries)


def push_pc(by, snap, cn_factory=None):
    """Снимок → adm.NotesSnapPut (логин asda_admin) и реестр записей. → dict(id, new, md5, chars, entries)."""
    if not FILE_RX.match(snap.get("file") or ""):
        raise OpRefused("имя файла changelog не по образцу CHANGELOG_ГГГГ-ММ-ДД.md — не записан")
    text = snap.get("text") or ""
    if not text or len(text) > SNAP_MAX:
        raise OpRefused("changelog пуст или больше %d знаков — не записан" % SNAP_MAX)
    bad = secrets_in(text)
    if bad:
        raise OpRefused("в changelog похоже на секрет (%s) — снимок не отправлен, уберите это из файла" % ", ".join(bad))
    cn = (cn_factory or db.admin)()
    try:
        if not _installed(cn):
            raise OpRefused(NOT_INSTALLED)
        r = db.admin_rows(cn, "SET NOCOUNT ON; DECLARE @id INT, @new BIT; EXEC adm.NotesSnapPut ?, ?, ?, ?, ?, ?, @id OUTPUT, @new OUTPUT; "
                              "SELECT @id AS id, @new AS new", (snap["file"], text, snap["md5"], snap.get("host") or "", _safe_by(by),
                                                                datetime.datetime.strptime(snap["collected_utc"], "%Y-%m-%d %H:%M:%S")))[0]
        n = sync_registry(cn, int(r["id"]), snap["file"], parse(text))
        return {"id": int(r["id"]), "new": bool(r["new"]), "md5": snap["md5"], "chars": len(text), "entries": n}
    finally:
        cn.close()


def _safe_by(by):
    """Кто прислал — без имени пользователя Windows (как releases.safe_by)."""
    return re.sub(r"^cli:[^@]*@", "cli@", str(by or ""))[:32]


# ── чтение ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _installed(cn):
    """Установлен ли adminc_31 с реестром ревизии 82."""
    return bool(db.admin_rows(cn, "SELECT 1 AS ok WHERE OBJECT_ID(N'adm.NotesSnap', N'U') IS NOT NULL AND OBJECT_ID(N'adm.NotesEntry', N'U') IS NOT NULL "
                                  "AND OBJECT_ID(N'adm.NotesEntrySync', N'P') IS NOT NULL"))


def _read(fn):
    """fn(соединение AsdaAdmin) → результат; ошибка базы — отказ с понятным текстом."""
    try:
        cn = db.admin()
    except db.DbError as ex:
        raise OpRefused("заметки к выпуску не прочитаны: %s" % ex)
    try:
        return fn(cn)
    except db.DbError as ex:
        raise OpRefused("заметки к выпуску не прочитаны: %s" % ex)
    finally:
        cn.close()


def _iso(v):
    """Дата / время → строка «ГГГГ-ММ-ДД ЧЧ:ММ:СС» (или None)."""
    return v.isoformat(sep=" ") if hasattr(v, "isoformat") else (str(v) if v is not None else None)


def unknown_error(err):
    """★ р82 М-2: ошибка бота означает «итог неизвестен» (ветка могла появиться) — то же правило, что LIKE в adm.NotesEntryPut."""
    s = str(err or "")
    return any(w in s for w in _UNKNOWN_ERR)


def post_state(r, now):
    """Состояние публикации для записи changelog (то же правило, что «занято» в adm.NotesEntryPut) → published | queued | unknown | failed | test |
    deleted | revoked | free."""
    if r["is_test"]:
        return "test"
    if r["kind"] == "manual":
        return "published" if r["revoked_utc"] is None else "revoked"
    st = r["status"]
    if st is None or r["o_test"]:
        return "test" if r["o_test"] else "free"
    if st == 2:
        return "deleted" if r["del_status"] == 2 else "published"
    if st in (0, 7):
        return "queued"
    if st == 1:
        old = r["claimed_utc"] is not None and (now - r["claimed_utc"]).total_seconds() > STUCK_MIN * 60
        return "unknown" if old else "queued"
    if st == 3:
        return "unknown" if unknown_error(r["error"]) else "failed"
    return "free"


_BUSY = ("published", "queued", "unknown")     # состояния, при которых запись второй раз в публикацию не берётся
BUSY_TEXT = {"published": "запись «%s» уже опубликована (публикация №%s) — снимите её галочку",
             "queued": "запись «%s» уже ждёт бота (публикация №%s) — снимите её галочку",
             "unknown": "запись «%s» в публикации с итогом «неизвестен» (публикация №%s) — проверьте форум updates и решите «ветки нет» или «ветка есть» в истории публикаций"}
_RANK = {"published": 3, "unknown": 2, "queued": 1}   # какое состояние показывать, если записей у ключа несколько


def _states(cn, now):
    """Ключ записи → dict(state, post, outbox, kind, whats, ptitle) — сильнейшее состояние среди публикаций (опубликовано > итог неизвестен >
    в очереди). ★ р84 М-1: whats — хэши «Что стало» опубликованных записей этого ключа на момент публикации (None — хэш не сохранён),
    ptitle — заголовок опубликованной."""
    rows = db.admin_rows(cn, "SELECT e.entry_key, e.what_hash, e.entry_title, p.id AS post_id, p.kind, p.is_test, p.revoked_utc, o.id AS oid, o.status, "
                             "o.is_test AS o_test, o.del_status, o.attempts, o.expires_utc, o.claimed_utc, o.error FROM adm.NotesPostEntry e "
                             "JOIN adm.NotesPost p ON p.id = e.post_id LEFT JOIN adm.Outbox o ON o.id = p.outbox_id")
    out, whats, ptitle = {}, {}, {}
    for r in rows:
        st = post_state(r, now)
        k = r["entry_key"]
        if st == "published":
            whats.setdefault(k, set()).add(r["what_hash"])
            ptitle.setdefault(k, r["entry_title"])
        cur = out.get(k)
        if st in _BUSY and (cur is None or _RANK[st] > _RANK.get(cur["state"], 0)):
            out[k] = {"state": st, "post": r["post_id"], "outbox": r["oid"], "kind": r["kind"]}
        elif st in ("test", "failed") and (cur is None or (cur["state"] == "test" and st == "failed")):   # свободна: показать последнюю ошибку
            out[k] = {"state": st, "post": r["post_id"], "outbox": r["oid"], "kind": r["kind"]}
    for k, v in out.items():
        v["whats"], v["ptitle"] = whats.get(k, set()), ptitle.get(k, "")
    return out


def _snap(cn):
    """Последний снимок changelog (строка adm.NotesSnap) или None."""
    r = db.admin_rows(cn, "SELECT TOP 1 id, file_name, payload, payload_md5, host, pushed_by, collected_utc, pushed_utc, seen_utc, seen_count, "
                          "DATEDIFF(minute, seen_utc, SYSUTCDATETIME()) AS age_min FROM adm.NotesSnap ORDER BY id DESC")
    return r[0] if r else None


def _registry(cn):
    """Реестр записей adm.NotesEntry: ключ → строка."""
    return {r["entry_key"]: r for r in db.admin_rows(cn, "SELECT entry_key, entry_date, title, area, status, rel, sens, ru, body, file_name, first_snap, "
                                                         "last_snap, hidden_by, hidden_utc, hidden_note, what_hash FROM adm.NotesEntry")}


def _draft(cn):
    """Черновик (dict полей) или None."""
    r = db.admin_rows(cn, "SELECT payload, snap_id, changed_by, changed_utc FROM adm.NotesDraft WHERE id = 1")
    if not r:
        return None
    try:
        d = json.loads(r[0]["payload"])
    except ValueError:
        d = {}
    return dict(d if isinstance(d, dict) else {}, _by=r[0]["changed_by"], _at=_iso(r[0]["changed_utc"]), _snap=r[0]["snap_id"])


POST_STATE = {0: "queued", 1: "claimed", 2: "posted", 3: "failed", 4: "cancelled", 5: "expired", 6: "test", 7: "hold"}   # статус adm.Outbox → слово


def _post_word(r, now):
    """Состояние публикации для истории (с «итог неизвестен», удалением и отметками вне панели)."""
    if r["kind"] == "manual":
        return "revoked" if r["revoked_utc"] else "manual"
    st = POST_STATE.get(r["status"], str(r["status"]))
    if st == "posted" and r["del_status"] == 2:
        return "deleted"
    if st == "posted" and r["del_status"] in (0, 1):
        return "deleting"
    if not r["is_test"] and (r["status"] == 3 and unknown_error(r["error"]) or
                             r["status"] == 1 and r["claimed_utc"] is not None and (now - r["claimed_utc"]).total_seconds() > STUCK_MIN * 60):
        return "unknown"
    return st


def _posts(cn, now):
    """История публикаций (30 последних) с состоянием записи очереди."""
    rows = db.admin_rows(cn, "SELECT TOP 30 p.id, p.kind, p.outbox_id, p.is_test, p.title, p.note, p.created_by, p.created_utc, p.revoked_by, "
                             "p.revoked_utc, o.status, o.del_status, o.error, o.discord_message_id, o.done_utc, o.claimed_utc, "
                             "(SELECT COUNT(*) FROM adm.NotesPostEntry e WHERE e.post_id = p.id) AS n "
                             "FROM adm.NotesPost p LEFT JOIN adm.Outbox o ON o.id = p.outbox_id ORDER BY p.id DESC")
    out = []
    for r in rows:
        st = _post_word(r, now)
        out.append({"id": r["id"], "kind": r["kind"], "outbox": r["outbox_id"], "test": bool(r["is_test"]), "title": r["title"], "note": r["note"] or "",
                    "by": r["created_by"], "created": _iso(r["created_utc"]), "state": st, "error": r["error"] or "", "entries": int(r["n"] or 0),
                    "done": _iso(r["done_utc"]), "revoked": _iso(r["revoked_utc"]), "revoked_by": r["revoked_by"] or "", "can_resolve": st == "unknown"})
    return out


def _from_registry(r):
    """Строка реестра → запись в виде результата parse (для записей прежних файлов). ★ р83 М-5: чувствительность и RU пересчитываются по
    текущим правилам (реестр мог быть записан прежними)."""
    sens = [s for s in (r["sens"] or "").split(", ") if s]
    lines = [ln[2:] if ln.startswith("• ") else ln for ln in (r["ru"] or "").split("\n") if ln.strip()]
    sens = list(dict.fromkeys(sens + sensitive_in(r["title"], "\n".join(lines))))
    ru, cut = ru_lines(lines)
    return {"key": r["entry_key"], "key_v1": "", "date": r["entry_date"], "section": "", "head": r["title"], "title": r["title"], "area": r["area"],
            "status": r["status"], "release": r["rel"] or "", "ru": mask("\n".join("• " + w for w in ru)), "ru_cut": cut, "body": r["body"] or "",
            "of_key": "", "of_title": "", "sens": sens, "what_hash": r["what_hash"] or "",
            "visible": r["area"] in ("client", "server", "release", "clarify"), "default": False}


def _entries(cn, s, states):
    """★ р82 В-2: записи последнего снимка + неопубликованные записи прежних файлов из реестра (не скрытые) → (список, реестр)."""
    reg = _registry(cn)
    cur = parse(s["payload"]) if s else []
    keys = {x["key"] for x in cur}
    for x in cur:
        x["file"], x["old"] = s["file_name"], False
    extra = []
    for k, r in reg.items():
        if k in keys:
            continue
        st = (states.get(k) or {}).get("state")
        if st in _BUSY:                      # опубликованное из прежних файлов в черновик не возвращается
            continue
        x = _from_registry(r)
        x["file"], x["old"] = r["file_name"], True
        extra.append(x)
    extra.sort(key=lambda x: (x["date"][-4:], x["date"][3:5], x["date"][:2]))
    out = extra + cur
    for x in out:
        r = reg.get(x["key"])
        x["hidden"] = bool(r and r["hidden_utc"])
        x["hidden_note"] = (r["hidden_note"] or "") if r else ""
        if x["hidden"]:
            x["default"] = False
        st = states.get(x["key"]) or {"state": "free", "post": None, "outbox": None, "kind": None}
        x.update(pub=st["state"], pub_post=st["post"], pub_outbox=st["outbox"], pub_kind=st["kind"], similar="")
        # ★ р84 М-1: ключ опубликован, но «Что стало» у опубликованной другое (и ни одна публикация ключа не с этим «Что стало») — не
        #   «опубликовано», а «похоже на уже опубликованное»: без галочки, решает оператор (adm.NotesEntryPut такую запись не считает занятой)
        wh = st.get("whats") or set()
        if st["state"] == "published" and x.get("what_hash") and wh and None not in wh and x["what_hash"] not in wh:
            x.update(pub="free", pub_post=None, pub_outbox=None, pub_kind=None, similar=st.get("ptitle") or x["title"], default=False)
    # ★ р83 В-1: второй признак — то же «Что стало», что у опубликованной записи с другим ключом: «похоже на уже опубликованное», без галочки
    pub_hash = {}
    for k, v in states.items():
        if v.get("state") == "published":
            for h in v.get("whats") or ():
                if h:
                    pub_hash.setdefault(h, v.get("ptitle") or (reg.get(k) or {}).get("title") or "")
    for x in out:
        if x["pub"] not in _BUSY and x.get("what_hash") and x["what_hash"] in pub_hash:
            x["similar"], x["default"] = pub_hash[x["what_hash"]], False
    return out, reg


def view(q=None, role=None):
    """Экран «Заметки к выпуску»: снимок changelog, записи с состоянием публикации (и неопубликованные из прежних файлов), черновик, история
    публикаций, пределы, предупреждения. role — роль смотрящего: полный текст записей с IP и путями видит только owner (★ р82 М-5)."""
    base = {"channel": CHANNEL, "roles": ROLES, "limits": {"text_max": outbox.TEXT_MAX, "msg_max": outbox.MSG_MAX, "title_max": outbox.TITLE_MAX,
            "mention_max": outbox.MENTION_MAX, "ttl_def": TTL_DEF, "ttl_min": outbox.TTL_MIN, "ttl_max": outbox.TTL_MAX, "keys_max": KEYS_MAX,
            "per_hour": outbox.PER_HOUR, "per_day": outbox.PER_DAY, "stale_h": PC_STALE_H}, "langs": [k for k, _f in outbox.LANGS],
            "flags": {k: f for k, f in outbox.LANGS}}

    def go(cn):
        """Всё чтение — одним соединением."""
        if not _installed(cn):
            return None
        now = db.admin_rows(cn, "SELECT SYSUTCDATETIME() AS t")[0]["t"]
        s = _snap(cn)
        states = _states(cn, now)
        ent, reg = _entries(cn, s, states)
        prev_file = db.admin_rows(cn, "SELECT TOP 1 file_name FROM adm.NotesSnap WHERE file_name <> ? ORDER BY id DESC", (s["file_name"],)) if s else []
        done = db.admin_rows(cn, "SELECT reg_count, reg_done_utc FROM adm.NotesSnap WHERE id = ?", (s["id"],))[0] if s else None
        return s, ent, reg, _draft(cn), _posts(cn, now), now, prev_file, done
    got = _read(go)
    if got is None:
        return dict(base, installed=False, error=NOT_INSTALLED, snap=None, entries=[], draft=None, posts=[], warnings=[NOT_INSTALLED])
    s, entries, reg, draft, posts, now, prev_file, done = got
    warn = []
    if role != "owner":                               # ★ р83 М-3: IP и пути — только owner, во всех текстовых полях записей и истории
        for x in entries:
            for f in ("head", "title", "body", "section", "of_title", "similar", "hidden_note"):
                if x.get(f):
                    x[f] = mask(x[f])
        for x in posts:
            for f in ("title", "note", "error"):
                if x.get(f):
                    x[f] = mask(x[f])
    if not s:
        return dict(base, installed=True, error="", snap=None, entries=entries, draft=draft, posts=posts, warnings=[NO_SNAP], now=_iso(now))
    age = int(s["age_min"] or 0)
    if age > PC_STALE_H * 60:
        warn.append("changelog с ПК присылался больше %d ч назад (%s UTC) — новые записи могли не попасть, пришлите снимок заново" % (PC_STALE_H, _iso(s["seen_utc"])))
    if not done or done["reg_done_utc"] is None or int(done["reg_count"] or -1) != len([x for x in entries if not x["old"]]):
        warn.append("реестр записей по снимку №%d записан не полностью (связь прервалась или реестр не перечитан) — на ПК: python "
                    "AstoryAdminCenter\\asda_admin.py notes resync" % s["id"])
    old = [x for x in entries if x["old"] and x["visible"] and not x["hidden"]]
    if prev_file and old:
        warn.append("changelog сменился (%s → %s): из прежних файлов не опубликовано записей, видимых игрокам: %d — они в списке с пометкой «из файла …», "
                    "пока их не опубликуют или не скроют" % (prev_file[0]["file_name"], s["file_name"], len(old)))
    snap = {"id": s["id"], "file": s["file_name"], "md5": s["payload_md5"], "host": s["host"], "by": s["pushed_by"], "collected": _iso(s["collected_utc"]),
            "pushed": _iso(s["pushed_utc"]), "seen": _iso(s["seen_utc"]), "seen_count": s["seen_count"], "age_min": age, "chars": len(s["payload"])}
    rel = last_release([x for x in entries if not x["old"]])
    return dict(base, installed=True, error="", snap=snap, entries=entries, draft=draft, posts=posts, warnings=warn, now=_iso(now),
                title_hint=("Astory %s" % rel) if rel else "", release=rel)


# ── проверка полей ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _keys(p):
    """Ключи записей из параметров (список 16 hex, без повторов, не больше KEYS_MAX) или отказ."""
    ks = (p or {}).get("keys")
    if not isinstance(ks, list) or not ks:
        raise OpRefused("отметьте хотя бы одну запись changelog")
    out = []
    for k in ks:
        if not isinstance(k, str) or not _KEY.match(k):
            raise OpRefused("ключ записи changelog — 16 шестнадцатеричных знаков")
        if k not in out:
            out.append(k)
    if len(out) > KEYS_MAX:
        raise OpRefused("в одной публикации не больше %d записей changelog" % KEYS_MAX)
    return out


def _load(sid):
    """Снимок (последний; sid — должен совпасть), записи (с прежними файлами) и состояния → (snap row, entries, states, now)."""
    def go(cn):
        """Чтение одним соединением."""
        if not _installed(cn):
            raise OpRefused(NOT_INSTALLED)
        s = _snap(cn)
        if not s:
            raise OpRefused(NO_SNAP)
        now = db.admin_rows(cn, "SELECT SYSUTCDATETIME() AS t")[0]["t"]
        states = _states(cn, now)
        return s, _entries(cn, s, states)[0], states, now
    s, entries, states, now = _read(go)
    if sid not in (None, "") and str(sid) != str(s["id"]):
        raise OpRefused("пришёл новый снимок changelog (№%d) — обновите страницу и проверьте отметки" % s["id"])
    return s, entries, states, now


def _picked(entries, keys, states, allow_busy):
    """Записи по ключам в порядке списка; нет в списке — отказ; скрытые и занятые (если не allow_busy) — отказ с названием."""
    by = {x["key"]: x for x in entries}
    miss = [k for k in keys if k not in by]
    if miss:
        raise OpRefused("записи changelog %s нет в последнем снимке — обновите страницу" % miss[0])
    for k in keys:
        if by[k].get("hidden"):
            raise OpRefused("запись «%s» скрыта — сначала верните её" % by[k]["title"][:80])
    if not allow_busy:
        for k in keys:
            st = by[k].get("pub")                 # ★ р84 М-1: состояние записи с учётом хэша «Что стало» (_entries)
            if st in _BUSY:
                raise OpRefused(BUSY_TEXT[st] % (by[k]["title"][:80], by[k].get("pub_post")))
    ks = set(keys)
    return [x for x in entries if x["key"] in ks]


def _role(p):
    """Роль из параметров: patch или "" — иначе отказ."""
    r = str((p or {}).get("role") or "")
    if r not in ROLES:
        raise OpRefused("роль для заметок — Patch Ping или без упоминания")
    return r


def _title(p):
    """Заголовок ветки: строка 1…100 знаков UTF-16 без управляющих символов — иначе отказ."""
    t = (p or {}).get("title")
    if not isinstance(t, str):
        raise OpRefused("заголовок ветки — строка")
    t = _norm(t)
    if not t or outbox.dlen(t) > outbox.TITLE_MAX:
        raise OpRefused("заголовок ветки форума updates — от 1 до %d знаков" % outbox.TITLE_MAX)
    if _CTRL.search(t):
        raise OpRefused("в заголовке ветки управляющие символы")
    return t


def compose_fields(ctx, p):
    """Поля публикации → dict для outbox (канал updates, роль, тексты, срок, заголовок). Отказы — как у объявления А7.4 плюс свои."""
    role, title = _role(p), _title(p)
    ttl = (p or {}).get("ttl")
    dc = outbox.check(ctx, {"channel": CHANNEL, "role": role, "en": (p or {}).get("en"), "ru": (p or {}).get("ru"), "ar": (p or {}).get("ar"),
                            "ttl": TTL_DEF if ttl in (None, "") else ttl}, title)
    return dc


def _title_taken(title):
    """★ р82 М-3 / р83 М-2: номер записи очереди с тем же заголовком в форуме updates за сутки (не тест; отменённое и просроченное не в счёт,
    только если бот его не брал) или None. Та же проверка — в adm.NotesPublishPut и adm.OutboxPut (код 7 / 5)."""
    r = _read(lambda cn: db.admin_rows(cn, "SELECT TOP 1 id FROM adm.Outbox WHERE transport = 'discord' AND channel_key = 'updates' AND is_test = 0 "
                                           "AND title = ? AND NOT (status IN (4, 5) AND claimed_utc IS NULL) "
                                           "AND created_utc > DATEADD(DAY, -1, SYSUTCDATETIME()) ORDER BY id DESC",
                                       (title,)))
    return int(r[0]["id"]) if r else None


def _msg_md5(dc):
    """Отпечаток текста публикации (заголовок, роль, тексты, срок) — для expect."""
    return hashlib.md5(json.dumps([dc["title"], dc["role"], dc["en"], dc["ru"], dc["ar"], int(dc["ttl"])], ensure_ascii=False).encode("utf-8")).hexdigest()


# ── операции ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
@register
class NotesPush(Operation):
    """Задание ПК: прислать службе текущий changelog (как есть) — adm.NotesSnap и реестр adm.NotesEntry. Исполняет консоль ПК (asda_admin.py
    notes push или jobs run-due). Пишет только AsdaAdmin; файлы changelog не меняются."""
    name, title = "notes.push", "Заметки к выпуску: прислать changelog с ПК"
    perm, reversible, schedule_runner = "notes.push", False, "pc"

    def target(self, p):
        """Цель журнала."""
        return "notes:snap"

    def schedule_check(self, ctx, p):
        """Постановка в задания ПК — без проверок (всё проверяет исполнение на ПК)."""
        return None

    def preview(self, ctx, p):
        """Собрать снимок на ПК и показать, что уйдёт (на сервере — отказ)."""
        if config.get().on_server:
            raise OpRefused("changelog лежит на ПК владельца — снимок присылает консоль ПК, поставьте задание ПК")
        snap = pc_collect()
        ent = parse(snap["text"])
        return {"text": "changelog %s: %d знаков, записей %d (видны игрокам %d), md5 %s" % (
            snap["file"], len(snap["text"]), len(ent), sum(1 for x in ent if x["visible"]), snap["md5"]),
            "warnings": ["в changelog похоже на секрет (%s) — снимок не отправится" % ", ".join(secrets_in(snap["text"]))] if secrets_in(snap["text"]) else [],
            "snap": snap}

    def apply(self, ctx, p, prev):
        """Записать снимок и реестр."""
        r = push_pc(ctx.login, prev.get("snap"))
        return {"after": {"id": r["id"], "new": r["new"], "md5": r["md5"], "entries": r["entries"]},
                "message": ("changelog записан: снимок №%d (%d знаков)" % (r["id"], r["chars"])) if r["new"]
                else "changelog не изменился: снимок №%d, отмечено «ПК присылал»" % r["id"]}


@register
class NotesResync(Operation):
    """★ р82 В-2: перечитать реестр записей по последнему снимку (после обновления разбора; переводит прежние ключи публикаций на новые). Пишет
    только AsdaAdmin adm.NotesEntry / NotesPostEntry процедурой."""
    name, title, perm, reversible = "notes.resync", "Заметки к выпуску: перечитать реестр записей по снимку", "notes.push", False

    def target(self, p):
        """Цель журнала."""
        return "notes:registry"

    def preview(self, ctx, p):
        """Сколько записей в последнем снимке."""
        def go(cn):
            """Последний снимок."""
            if not _installed(cn):
                raise OpRefused(NOT_INSTALLED)
            return _snap(cn)
        s = _read(go)
        if not s:
            raise OpRefused(NO_SNAP)
        return {"text": "перечитать реестр по снимку №%d (%s): записей %d" % (s["id"], s["file_name"], len(parse(s["payload"]))),
                "warnings": ["пишется только база панели AsdaAdmin (реестр записей) — в Discord ничего не уходит"], "expect": {"snap": s["id"]}}

    def apply(self, ctx, p, prev):
        """Записать реестр."""
        def go(cn):
            """Снимок → реестр."""
            s = _snap(cn)
            return s, sync_registry(cn, s["id"], s["file_name"], parse(s["payload"]))
        s, n = _read(go)
        return {"after": {"snap": s["id"], "entries": n}, "message": "реестр записей перечитан по снимку №%d: записей %d" % (s["id"], n)}


@register
class NotesDraft(Operation):
    """Сохранить черновик заметок (adm.NotesDraft, одна строка): отмеченные записи, заголовок, тексты, роль, срок. Ничего не публикует."""
    name, title, perm, reversible = "notes.draft", "Заметки к выпуску: сохранить черновик", "notes.draft", False

    def target(self, p):
        """Цель журнала."""
        return "notes:draft"

    def _payload(self, p):
        """Поля черновика → (dict, JSON) или отказ."""
        p = p or {}
        keys = p.get("keys") or []
        if not isinstance(keys, list) or len(keys) > 2000 or any(not isinstance(k, str) or not _KEY.match(k) for k in keys):
            raise OpRefused("ключ записи changelog — 16 шестнадцатеричных знаков")
        d = {"keys": keys, "role": _role(p), "ttl": p.get("ttl") if p.get("ttl") not in (None, "") else TTL_DEF}
        for f in ("title", "en", "ru", "ar"):
            v = p.get(f) or ""
            if not isinstance(v, str):
                raise OpRefused("поле черновика %s — строка" % f)
            d[f] = v.replace("\r\n", "\n")
        text = json.dumps(d, ensure_ascii=False)
        if len(text) > DRAFT_MAX:
            raise OpRefused("черновик больше %d знаков — не сохранён" % DRAFT_MAX)
        return d, text

    def preview(self, ctx, p):
        """Что сохранится."""
        d, text = self._payload(p)
        return {"text": "сохранить черновик заметок: отмечено записей %d, заголовок «%s», EN %d / RU %d / AR %d знаков" % (
            len(d["keys"]), d["title"][:100], len(d["en"]), len(d["ru"]), len(d["ar"])),
            "warnings": ["пишется только база панели AsdaAdmin (adm.NotesDraft) — в Discord ничего не уходит"]}

    def apply(self, ctx, p, prev):
        """Сохранить."""
        d, text = self._payload(p)
        sid = (p or {}).get("snap")
        sid = int(sid) if isinstance(sid, int) or (isinstance(sid, str) and sid.isdigit()) else None
        _read(lambda cn: db.admin_rows(cn, "SET NOCOUNT ON; EXEC adm.NotesDraftSet ?, ?, ?", (text, sid, ctx.login[:32])))
        return {"after": {"keys": len(d["keys"])}, "message": "черновик заметок сохранён (записей %d)" % len(d["keys"])}


def _entries_tx(cn, post, items):
    """Записи changelog в публикацию (в открытой транзакции) — код 5 у любой → отказ с названием записи."""
    for x in items:
        c = int(db.admin_rows(cn, "SET NOCOUNT ON; DECLARE @c INT; EXEC adm.NotesEntryPut ?, ?, ?, ?, @c OUTPUT, ?; SELECT @c AS code",
                              (post, x["key"], x["date"] or "", x["title"][:200], x.get("what_hash") or None))[0]["code"])
        if c:
            raise OpRefused("запись «%s»: %s" % (x["title"][:80], PUT_CODES.get(c, "очередь Discord: код %d" % c)))


EXPECT_CHANGED = "черновик или снимок изменились с предпросмотра — откройте предпросмотр заново"


def _same_expect(p, prev):
    """Отпечаток подтверждённого предпросмотра (expect из браузера) = отпечаток, посчитанный сейчас (снимок, записи, текст, тест). Нет — отказ."""
    want = (p or {}).get("expect")
    if not isinstance(want, dict) or want != prev.get("expect"):
        raise OpRefused(EXPECT_CHANGED)


def _tx_begin():
    """Соединение AsdaAdmin с открытой транзакцией (фиксирует ops._finish после журнала)."""
    cn = db.admin()
    cn.autocommit = False
    return cn


def _tx_abort(cn):
    """Откатить и закрыть соединение."""
    try:
        cn.rollback()
    finally:
        cn.close()


def _outbox_row(oid):
    """Строка adm.Outbox для отката и решения «итог неизвестен» (или отказ)."""
    r = _read(lambda cn: db.admin_rows(cn, "SELECT o.id, o.kind, o.status, o.is_test, o.del_status, o.discord_message_id, o.error, o.claimed_utc, "
                                           "o.expires_utc, SYSUTCDATETIME() AS now_utc, (SELECT COUNT(*) FROM adm.Outbox x WHERE x.transport = 'discord' "
                                           "AND x.id <> o.id AND x.done_utc > o.claimed_utc) AS bot_after FROM adm.Outbox o WHERE o.id = ?", (int(oid),)))
    if not r:
        raise OpRefused("записи очереди Discord №%d нет" % int(oid))
    return r[0]


def _bot_released(r):
    """★ р83 М-7: бот точно не держит захват записи «бот взял»: срок годности прошёл или бот после захвата отчитался по другим записям."""
    return r["status"] != 1 or r["expires_utc"] <= r["now_utc"] or bool(r["bot_after"])


def _is_unknown(r):
    """Запись очереди в «итог неизвестен»: ошибка бота «итог неизвестен» или бот взял и молчит дольше STUCK_MIN."""
    if r["status"] == 3:
        return unknown_error(r["error"])
    return r["status"] == 1 and r["claimed_utc"] is not None and (r["now_utc"] - r["claimed_utc"]).total_seconds() > STUCK_MIN * 60


@register
class NotesPublish(Operation):
    """Опубликовать заметки к выпуску в форум updates (через очередь adm.Outbox, бот Oracle на ПК). Откат — отмена записи очереди (ждёт бота или
    ошибка) или удаление ветки ботом (опубликовано; только owner). «Итог неизвестен» откатом не снимается — notes.resolve."""
    name, title, perm, reversible = "notes.publish", "Заметки к выпуску: опубликовать в Discord (форум updates)", "community.post", True

    def target(self, p):
        """Цель журнала."""
        return "notes:publish"

    def _plan(self, ctx, p):
        """Проверить поля и записи → (тест, поля Discord, снимок, записи)."""
        p = p or {}
        test = bool(p.get("test"))
        keys = _keys(p)
        dc = compose_fields(ctx, p)
        s, entries, states, now = _load(p.get("snap"))
        items = _picked(entries, keys, states, allow_busy=test)
        if not test:
            t = _title_taken(dc["title"])
            if t:
                raise OpRefused("ветка с заголовком «%s» за сутки уже была (запись очереди №%d) — для следующей части дайте другой заголовок, например «… (часть 2)»"
                                % (dc["title"], t))
        return test, dc, s, items

    def preview(self, ctx, p):
        """Полный текст, как в Discord, и предупреждения."""
        test, dc, s, items = self._plan(ctx, p)
        outbox.budget(test=test)
        msg = outbox.preview_text(dc)
        n_msg = outbox.dlen(outbox.compose("x" * outbox.MENTION_MAX if dc["role"] else "", dc["en"], dc["ru"], dc["ar"]))
        w = []
        if test:
            w.append("ТЕСТ: бот заберёт запись и отметит «тест», в Discord ничего не уйдёт, записи changelog не станут «опубликованными»")
            w.append("роль: Patch Ping" if dc["role"] else "без упоминания роли")
        else:
            w.append("ПУБЛИЧНО: новая ветка в форуме updates — её увидят все участники сервера Discord, пинг роли Patch Ping" if dc["role"]
                     else "ПУБЛИЧНО: новая ветка в форуме updates — её увидят все участники сервера Discord, без пинга роли")
        miss = [k.upper() for k, _f in outbox.LANGS if not dc.get(k)]
        if miss:
            w.append("в Discord нет текста на %s" % " ".join(miss))
        lk = leaks_in(dc["title"], dc["en"], dc["ru"], dc["ar"])
        if lk:
            w.append("в тексте похоже на внутренние детали (%s) — игрокам это обычно не нужно, проверьте" % ", ".join(lk))
        sim = [x for x in items if x.get("similar")]
        if sim:
            w.append("похоже на уже опубликованное (то же «Что стало»): %s — проверьте, что это не повтор" % ", ".join("«%s»" % mask(x["title"][:60]) for x in sim[:5]))
        sens = [x for x in items if x["sens"]]
        if sens:
            w.append("отмечены записи с чувствительным (%d: %s) — их текст в RU не подставлялся, проверьте, что написано своими словами"
                     % (len(sens), ", ".join(dict.fromkeys(k for x in sens for k in x["sens"]))))
        doms = outbox.link_domains(dc["title"], dc["en"], dc["ru"], dc["ar"])
        if doms:
            w.append("ссылки в тексте ведут на: %s (превью ссылок в Discord отключено)" % ", ".join(doms))
        w.append("длина: сообщение %d из %d знаков (с упоминанием роли), имя ветки %d из %d" % (n_msg, outbox.MSG_MAX, outbox.dlen(dc["title"]), outbox.TITLE_MAX))
        w.append("записи changelog станут «опубликованными», когда бот отчитается об успехе, а не при постановке в очередь")
        w.append("откат — в «Журнале действий»: до публикации — отмена записи очереди, после — удаление ветки из Discord (только владелец), "
                 "кто уже прочитал — не вернуть")
        w.append("в Discord публикует бот Oracle на ПК владельца (раз в 30 с), если он запущен — итог виден на странице «Очередь Discord», срок годности %d мин"
                 % dc["ttl"])
        return {"text": "опубликовать заметки к выпуску: форум updates, ветка «%s», записей changelog %d (снимок №%d, %s)\nтекст в Discord:\n%s" % (
            dc["title"], len(items), s["id"], s["file_name"], msg),
            "warnings": w, "expect": {"snap": s["id"], "keys": [x["key"] for x in items], "md5": _msg_md5(dc), "test": test}}

    def apply(self, ctx, p, prev):
        """Запись очереди + публикация + её записи — одной транзакцией (фиксация после журнала)."""
        test, dc, s, items = self._plan(ctx, p)
        _same_expect(p, prev)
        cn = _tx_begin()
        try:
            r = db.admin_rows(cn, "SET NOCOUNT ON; DECLARE @id INT, @post INT, @code INT; EXEC adm.NotesPublishPut ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                                  "@id OUTPUT, @post OUTPUT, @code OUTPUT; SELECT @code AS code, @id AS id, @post AS post",
                              (dc["title"], dc["en"], dc["ru"] or None, dc["ar"] or None, dc["role"] or None, int(dc["ttl"]), ctx.login[:32],
                               1 if test else 0, s["id"]))[0]
            code = int(r["code"])
            if code:
                raise OpRefused(PUT_CODES.get(code, "очередь Discord: код %d" % code))
            oid, post = int(r["id"]), int(r["post"])
            _entries_tx(cn, post, items)
        except BaseException:
            _tx_abort(cn)
            raise
        return {"_commit": cn.commit, "_close": cn.close, "before": None,
                "after": {"outbox": oid, "post": post, "test": test, "entries": len(items), "snap": s["id"]},
                "message": ("заметки к выпуску — проверочная запись очереди Discord №%d (публикация №%d, записей %d): бот отметит «тест», в Discord ничего не уйдёт"
                            if test else "заметки к выпуску — запись очереди Discord №%d (публикация №%d, записей %d): публикует бот на ПК")
                % (oid, post, len(items))}

    def undo(self, ctx, row):
        """Откат: ждёт бота — отмена; ошибка — закрыть запись (записи свободны); опубликовано — удаление ветки (owner); «итог неизвестен» — отказ."""
        a = json.loads(row.get("after_json") or "{}")
        oid = a.get("outbox")
        if not oid:
            raise OpRefused("в журнале нет номера записи очереди — откат не выполнен")
        r = _outbox_row(oid)
        oid = int(oid)
        if r["is_test"]:
            raise OpRefused("проверочная публикация — в Discord ничего не уходило, откатывать нечего")
        st = int(r["status"])
        if _is_unknown(r):
            raise OpRefused("итог публикации №%d неизвестен — ветка могла появиться, откат мог бы дать дубль: проверьте форум updates и решите «ветки нет» "
                            "или «ветка есть» в истории публикаций" % oid)
        if st == 0:
            proc, args, msg = "adm.OutboxCancel", (oid, ctx.login[:32]), "запись очереди Discord №%d отменена — заметки не опубликованы" % oid
        elif st == 3:
            proc, args, msg = ("adm.NotesOutboxClose", (oid, ctx.login[:32], "откат публикации заметок", STUCK_MIN, 0),
                               "запись очереди Discord №%d в ошибке закрыта — заметки не опубликованы, записи свободны" % oid)
        elif st == 2 and r["discord_message_id"] is not None and r["del_status"] in (None, 3):
            if not ctx.can("community.delete"):
                raise OpRefused("заметки уже опубликованы — удалить ветку из Discord может только владелец (community.delete)")
            proc, args, msg = "adm.OutboxDelete", (oid, ctx.login[:32]), "удаление ветки заметок (запись очереди №%d) поставлено боту — кто уже прочитал, не вернуть" % oid
        elif st == 1:
            raise OpRefused("бот публикует запись №%d прямо сейчас — повторите откат через минуту" % oid)
        elif st == 2 and r["del_status"] in (0, 1):
            raise OpRefused("удаление ветки по записи №%d уже поставлено боту — итог виден в «Очереди Discord»" % oid)
        elif st == 2:
            raise OpRefused("ветка по записи №%d уже удалена из Discord — откатывать нечего" % oid)
        else:
            raise OpRefused("запись очереди Discord №%d не опубликована и не ждёт бота (%s) — откатывать нечего" % (oid, POST_STATE.get(st, str(st))))
        cn = _tx_begin()
        try:
            n = int(db.admin_rows(cn, "SET NOCOUNT ON; EXEC %s %s" % (proc, ", ".join("?" * len(args))), args)[0]["n"])
            if n != 1:
                raise OpRefused("запись очереди Discord №%d изменилась — откройте «Очередь Discord» заново" % oid)
        except BaseException:
            _tx_abort(cn)
            raise
        return {"_commit": cn.commit, "_close": cn.close, "before": {"outbox": oid, "status": st}, "after": {"outbox": oid, "undo": proc},
                "message": msg}


def _note(p):
    """Причина из параметров (3…200 знаков) или отказ."""
    note = _norm((p or {}).get("note") if isinstance((p or {}).get("note"), str) else "")
    if not NOTE_MIN <= len(note) <= NOTE_MAX:
        raise OpRefused("причина отметки — от %d до %d знаков (где и когда это уже публиковалось)" % (NOTE_MIN, NOTE_MAX))
    return note


def _mark_tx(cn, note, by, snap_id, items):
    """Отметка «опубликовано вне панели» и её записи (в открытой транзакции) → номер отметки."""
    r = db.admin_rows(cn, "SET NOCOUNT ON; DECLARE @post INT, @code INT; EXEC adm.NotesMarkPut ?, ?, ?, @post OUTPUT, @code OUTPUT; "
                          "SELECT @code AS code, @post AS post", (note, by[:32], snap_id))[0]
    if int(r["code"]):
        raise OpRefused(PUT_CODES.get(int(r["code"]), "очередь Discord: код %d" % int(r["code"])))
    post = int(r["post"])
    _entries_tx(cn, post, items)
    return post


@register
class NotesMark(Operation):
    """Отметить записи changelog «уже опубликовано вне панели» (без Discord) — например, то, что владелец публиковал руками раньше. Откат —
    снять отметку."""
    name, title, perm, reversible = "notes.mark", "Заметки к выпуску: отметить «опубликовано вне панели»", "community.post", True

    def target(self, p):
        """Цель журнала."""
        return "notes:mark"

    def _plan(self, ctx, p):
        """Причина, снимок, записи."""
        p = p or {}
        if not ctx.can("community.post"):
            raise OpRefused("нет права «community.post» (публикация в Discord — owner и admin)")
        note = _note(p)
        keys = _keys(p)
        s, entries, states, now = _load(p.get("snap"))
        return note, s, _picked(entries, keys, states, allow_busy=False)

    def preview(self, ctx, p):
        """Список записей и что будет."""
        note, s, items = self._plan(ctx, p)
        lines = ["%s — %s" % (x["date"] or "—", mask(x["title"][:100])) for x in items[:20]]
        if len(items) > 20:
            lines.append("и ещё %d" % (len(items) - 20))
        return {"text": "отметить «уже опубликовано вне панели» записей changelog: %d (причина: %s)\n%s" % (len(items), note, "\n".join(lines)),
                "warnings": ["в Discord ничего не уходит — пишется только база панели AsdaAdmin (adm.NotesPost), записи пропадут из черновика",
                             "откат — в «Журнале действий» (отметка снимается, записи снова в черновике)"],
                "expect": {"snap": s["id"], "keys": [x["key"] for x in items]}}

    def apply(self, ctx, p, prev):
        """Записать отметку (фиксация после журнала)."""
        note, s, items = self._plan(ctx, p)
        _same_expect(p, prev)
        cn = _tx_begin()
        try:
            post = _mark_tx(cn, note, ctx.login, s["id"], items)
        except BaseException:
            _tx_abort(cn)
            raise
        return {"_commit": cn.commit, "_close": cn.close, "before": None, "after": {"post": post, "entries": len(items)},
                "message": "отмечено «опубликовано вне панели»: записей %d (отметка №%d)" % (len(items), post)}

    def undo(self, ctx, row):
        """Снять отметку."""
        a = json.loads(row.get("after_json") or "{}")
        post = a.get("post")
        if not post:
            raise OpRefused("в журнале нет номера отметки — откат не выполнен")
        cn = _tx_begin()
        try:
            n = int(db.admin_rows(cn, "SET NOCOUNT ON; EXEC adm.NotesMarkRevoke ?, ?", (int(post), ctx.login[:32]))[0]["n"])
            if n != 1:
                raise OpRefused("отметка №%d уже снята или её нет" % int(post))
        except BaseException:
            _tx_abort(cn)
            raise
        return {"_commit": cn.commit, "_close": cn.close, "before": {"post": int(post)}, "after": {"post": int(post), "revoked": True},
                "message": "отметка №%d снята — записи снова в черновике" % int(post)}


@register
class NotesHide(Operation):
    """★ р82 В-2: скрыть записи changelog из черновика (например, неопубликованные записи прежнего файла, которые игрокам не нужны) или вернуть.
    Ничего не публикует. Откат — обратное действие."""
    name, title, perm, reversible = "notes.hide", "Заметки к выпуску: скрыть или вернуть записи", "notes.draft", True

    def target(self, p):
        """Цель журнала."""
        return "notes:hide"

    def _plan(self, p):
        """Ключи (есть в реестре), скрыть или вернуть, причина (для скрытия)."""
        p = p or {}
        keys = _keys(p)
        hide = bool(p.get("hide", True))
        note = _note(p) if hide else ""
        reg = _read(lambda cn: _registry(cn) if _installed(cn) else None)
        if reg is None:
            raise OpRefused(NOT_INSTALLED)
        miss = [k for k in keys if k not in reg]
        if miss:
            raise OpRefused("записи changelog %s нет в реестре — пришлите снимок или выполните notes resync" % miss[0])
        todo = [k for k in keys if bool(reg[k]["hidden_utc"]) != hide]
        if not todo:
            raise OpRefused("все отмеченные записи уже скрыты" if hide else "все отмеченные записи уже видны")
        return keys, hide, note, todo, reg

    def preview(self, ctx, p):
        """Что скроется или вернётся."""
        keys, hide, note, todo, reg = self._plan(p)
        lines = ["%s — %s" % (reg[k]["entry_date"] or "—", mask(reg[k]["title"][:100])) for k in todo[:20]]
        return {"text": ("скрыть из черновика записей changelog: %d (причина: %s)\n%s" % (len(todo), note, "\n".join(lines))) if hide
                else ("вернуть в черновик записей changelog: %d\n%s" % (len(todo), "\n".join(lines))),
                "warnings": ["в Discord ничего не уходит — пишется только база панели AsdaAdmin (реестр записей)"], "expect": {"keys": todo, "hide": hide}}

    def apply(self, ctx, p, prev):
        """Записать (фиксация после журнала)."""
        keys, hide, note, todo, reg = self._plan(p)
        _same_expect(p, prev)
        cn = _tx_begin()
        try:
            for k in todo:
                db.admin_rows(cn, "SET NOCOUNT ON; EXEC adm.NotesEntryHide ?, ?, ?, ?", (k, 1 if hide else 0, ctx.login[:32], note or None))
        except BaseException:
            _tx_abort(cn)
            raise
        return {"_commit": cn.commit, "_close": cn.close, "before": {"keys": todo, "hidden": not hide}, "after": {"keys": todo, "hidden": hide},
                "message": ("скрыто записей changelog: %d" if hide else "возвращено записей changelog: %d") % len(todo)}

    def undo(self, ctx, row):
        """Обратное действие для тех же записей."""
        a = json.loads(row.get("after_json") or "{}")
        keys, hide = a.get("keys") or [], bool(a.get("hidden"))
        if not keys:
            raise OpRefused("в журнале нет записей — откат не выполнен")
        cn = _tx_begin()
        try:
            for k in keys:
                db.admin_rows(cn, "SET NOCOUNT ON; EXEC adm.NotesEntryHide ?, ?, ?, ?", (k, 0 if hide else 1, ctx.login[:32], "откат" if hide else None))
        except BaseException:
            _tx_abort(cn)
            raise
        return {"_commit": cn.commit, "_close": cn.close, "before": a, "after": {"keys": keys, "hidden": not hide},
                "message": ("возвращено записей changelog: %d" if hide else "скрыто записей changelog: %d") % len(keys)}


@register
class NotesResolve(Operation):
    """★ р82 М-2: решение по публикации с «итог неизвестен». «Ветки нет» — запись очереди закрывается, записи свободны (опубликовать заново).
    «Ветка есть» — запись очереди закрывается, записи отмечаются «опубликовано вне панели» с номером записи. Откат есть только у «ветка есть»
    (отметка снимается); «ветки нет» не откатывается — если ветка нашлась, отметьте записи «опубликовано вне панели» (notes.mark)."""
    name, title, perm, reversible = "notes.resolve", "Заметки к выпуску: итог неизвестен — ветки нет / ветка есть", "community.post", True

    def target(self, p):
        """Цель журнала."""
        return "notes:resolve:%s" % ((p or {}).get("post"),)

    def _plan(self, ctx, p):
        """Публикация, её запись очереди (в «итог неизвестен»), записи, решение, причина."""
        p = p or {}
        thread = str(p.get("thread") or "")
        if thread not in ("none", "exists"):
            raise OpRefused("решение — «ветки нет» или «ветка есть»")
        note = _note(p)
        try:
            pid = int(p.get("post"))
        except (TypeError, ValueError):
            raise OpRefused("номер публикации — целое от 1")

        def go(cn):
            """Публикация и её записи."""
            if not _installed(cn):
                raise OpRefused(NOT_INSTALLED)
            r = db.admin_rows(cn, "SELECT id, kind, outbox_id, is_test, snap_id FROM adm.NotesPost WHERE id = ?", (pid,))
            e = db.admin_rows(cn, "SELECT entry_key AS [key], entry_date AS date, entry_title AS title, what_hash FROM adm.NotesPostEntry WHERE post_id = ?",
                              (pid,))
            return r, e
        r, items = _read(go)
        if not r or r[0]["kind"] != "discord" or r[0]["is_test"]:
            raise OpRefused("публикации заметок №%d нет или это не публикация в Discord" % pid)
        o = _outbox_row(r[0]["outbox_id"])
        if not _is_unknown(o):
            raise OpRefused("у публикации №%d итог известен (%s) — решать нечего" % (pid, POST_STATE.get(o["status"], str(o["status"]))))
        if thread == "none" and not _bot_released(o):     # ★ р83 М-7: живой, но зависший бот мог бы ещё создать ветку
            raise OpRefused("бот взял запись №%d и, возможно, ещё держит её — «ветки нет» можно после срока годности записи (%s UTC) или после того, "
                            "как бот отчитается по другим записям" % (int(o["id"]), _iso(o["expires_utc"])))
        return thread, note, r[0], o, items

    def preview(self, ctx, p):
        """Что будет при каждом решении."""
        thread, note, post, o, items = self._plan(ctx, p)
        return {"text": ("публикация №%d (запись очереди №%d): ветки в форуме updates нет — запись очереди закрывается, записей changelog %d снова свободны"
                         if thread == "none" else
                         "публикация №%d (запись очереди №%d): ветка в форуме updates есть — запись очереди закрывается, записей changelog %d отмечаются "
                         "«опубликовано вне панели»") % (post["id"], o["id"], len(items)),
                "warnings": ["сначала проверьте форум updates глазами: «ветки нет» при существующей ветке даст дубль при следующей публикации"
                             if thread == "none" else "удалить ветку из Discord после этого можно только руками в Discord (номер сообщения бот не записал)"],
                "expect": {"post": post["id"], "outbox": o["id"], "thread": thread}}

    def apply(self, ctx, p, prev):
        """Закрыть запись очереди и (для «ветка есть») отметить записи — одной транзакцией."""
        thread, note, post, o, items = self._plan(ctx, p)
        _same_expect(p, prev)
        cn = _tx_begin()
        try:
            n = int(db.admin_rows(cn, "SET NOCOUNT ON; EXEC adm.NotesOutboxClose ?, ?, ?, ?, ?",
                                  (int(o["id"]), ctx.login[:32], ("оператор: ветки нет — " if thread == "none" else "оператор: ветка есть — ") + note,
                                   STUCK_MIN, 1 if thread == "exists" else 0))[0]["n"])
            if n != 1:
                raise OpRefused("запись очереди Discord №%d изменилась — откройте «Очередь Discord» заново" % int(o["id"]))
            mark = _mark_tx(cn, "ветка есть: запись очереди №%d — %s" % (int(o["id"]), note), ctx.login, post["snap_id"], items) if thread == "exists" else None
        except BaseException:
            _tx_abort(cn)
            raise
        return {"_commit": cn.commit, "_close": cn.close, "before": {"outbox": int(o["id"]), "status": int(o["status"])},
                "after": {"outbox": int(o["id"]), "thread": thread, "mark": mark},
                "message": ("публикация №%d: ветки нет — записи свободны" % post["id"]) if thread == "none"
                else "публикация №%d: ветка есть — записи отмечены «опубликовано вне панели» (отметка №%d)" % (post["id"], mark)}

    def undo(self, ctx, row):
        """Откат «ветка есть» — снять отметку; «ветки нет» не откатывается."""
        a = json.loads(row.get("after_json") or "{}")
        if a.get("thread") != "exists" or not a.get("mark"):
            raise OpRefused("решение «ветки нет» не откатывается — если ветка нашлась, отметьте записи «опубликовано вне панели»")
        cn = _tx_begin()
        try:
            n = int(db.admin_rows(cn, "SET NOCOUNT ON; EXEC adm.NotesMarkRevoke ?, ?", (int(a["mark"]), ctx.login[:32]))[0]["n"])
            if n != 1:
                raise OpRefused("отметка №%d уже снята или её нет" % int(a["mark"]))
        except BaseException:
            _tx_abort(cn)
            raise
        return {"_commit": cn.commit, "_close": cn.close, "before": a, "after": {"mark": int(a["mark"]), "revoked": True},
                "message": "отметка №%d снята — записи снова в черновике" % int(a["mark"])}
