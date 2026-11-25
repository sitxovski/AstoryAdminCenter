# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""server.py — HTTP-служба админ-центра: API + статика панели. 16.11.2026.

ПОЧЕМУ СТАНДАРТНАЯ БИБЛИОТЕКА. На сервере @@ASTORY_SERVER_HOSTNAME@@ есть Python 3.13 и pyodbc, но нет FastAPI/uvicorn; ставить пакеты
на игровой сервер ради службы на одного-двух пользователей незачем. ThreadingHTTPServer + свой маршрутизатор
закрывают всё, что нужно волне А0 (план ADMIN_TOOL_PLAN.md §3.1 уточнён этим решением).

ГДЕ СЛУШАЕТ. На сервере — все интерфейсы (0.0.0.0) по HTTPS (решение владельца 16.11.2026: «не только Tailscale»;
вне VPN без TLS пароль и cookie шли бы открытым текстом), сертификат — config.TLS_CERT/TLS_KEY (самоподписанный,
deploy шаг 4); cookie с Secure. На ПК — только 127.0.0.1 по HTTP (самотест, отладка).
Рукопожатие TLS идёт в потоке запроса (не в потоке приёма), с пределом времени — медленный клиент не держит приём.

ЗАЩИТА ЗАПРОСОВ
  * Host — только адреса сервера из config.public_hosts с портом службы (против DNS-rebinding);
  * сессия — cookie asda_sid (HttpOnly, SameSite=Strict), права — по роли (core.auth.PERMS) на КАЖДЫЙ маршрут;
  * любой POST несёт заголовок X-Asda-Csrf: для входа — «login» (нестандартный заголовок нельзя прислать с чужого сайта
    без CORS-проверки), для остальных — CSRF-токен сессии;
  * пока у владельца/администратора не включён второй фактор — доступны только «о себе», выход и настройка кода;
  * вход — не чаще LOGIN_RATE попыток в минуту с одного IP (поверх замка учётки);
  * тело запроса — не больше MAX_BODY; ответы API — Cache-Control: no-store; строгий CSP.
ЖУРНАЛ. Вход/выход, все операции, просмотр сетевых данных игрока (IP/MAC) — в adm.audit.
Побочных эффектов при импорте нет: служба стартует в serve().
"""
import datetime
import http.cookies
import json
import mimetypes
import os
import re
import socket
import ssl
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from core import audit, auth, config, db, i18n, ops
from domains import feed, panel_users, players, refdata, status

MAX_BODY = 64 * 1024          # предел тела запроса, байт
LOGIN_RATE = 10               # попыток входа в минуту с одного IP
COOKIE = "asda_sid"
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

_rate_lock = threading.Lock()
_rate = {}                    # ip → [времена попыток входа]
_rate_noted = {}              # ip → когда предел попыток последний раз записан в журнал
MAX_CONN = 64                 # одновременных соединений НЕ из VPN (ревизия 16.11 вечер В1: служба видна из интернета);
                              # из VPN/локально — отдельно, только предел на адрес: интернет не отрезает владельца (В1-н3)
MAX_CONN_IP = 12              # одновременных соединений с одного адреса
HEADER_DEADLINE_S = 20        # запрос (строка, заголовки, тело) должен прийти целиком за столько секунд
ROUTES = []                   # (метод, regex, функция, право | None, только_полная_сессия)


_tls_active = False           # служба поднята с TLS (serve) → cookie с Secure


def _secure():
    """Флаг Secure для cookie, когда служба отвечает по HTTPS."""
    return "; Secure" if _tls_active else ""


def session_cookie(token, max_age):
    """Set-Cookie сессии (пустой token + 0 — стереть)."""
    return "%s=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=%d%s" % (COOKIE, token, max_age, _secure())


class HttpError(Exception):
    """Ответ с кодом и сообщением."""

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def route(method, pattern, perm=None, full=True):
    """Декоратор маршрута API. perm=None — без проверки права (но с сессией, кроме входа); full=False — доступно и
    сессии «только настройка второго фактора»."""
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn, perm, full))
        return fn
    return deco


def _json_default(o):
    return audit._default(o)


NET_GROUPS = ("входы", "античит", "дела античита")    # разделы ленты с сетевыми данными — только players.view_net
IPV4_RX = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
MAC_RX = re.compile(r"\b[0-9A-Fa-f]{2}(?:[-:][0-9A-Fa-f]{2}){5}\b")
NET_KEY_RX = re.compile(r"(?i)^(ip|ipaddress|mac|.*_ip|ip_.*)$")


def _qint(q, key, default, lo, hi):
    """Целое из строки запроса в пределах [lo, hi]; мусор → default."""
    try:
        return max(lo, min(hi, int(q.get(key, default))))
    except (TypeError, ValueError):
        return default


def mask_net(v):
    """Убрать IP и MAC из значения любой вложенности (для ролей без players.view_net; ревизия А0 №2: IP лежал
    внутри JSON-строки san.case_event.row_json под ключом, которого не было в списке)."""
    if isinstance(v, str):
        return MAC_RX.sub("—", IPV4_RX.sub("—", v))
    if isinstance(v, dict):
        return {k: ("—" if NET_KEY_RX.match(str(k)) and v[k] not in (None, "") else mask_net(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [mask_net(x) for x in v]
    return v


QUERY_RX = re.compile(r'("[A-Z]+ [^ ?"]*)\?[^ "]*')


def strip_query(line):
    """Строка журнала доступа без строки запроса URL (ревизия А0 №11: в ней IP и логины из поиска)."""
    return QUERY_RX.sub(lambda m: m.group(1) + "?…", line)


def _ctx(req):
    """Контекст операции из сессии запроса."""
    u = req.session["user"]
    return ops.Ctx(u["id"], u["login"], u["role"], req.client_ip, "web")


# ---------------------------------------------------------------- маршруты: вход

@route("POST", r"/api/login", perm=None, full=False)
def api_login(req, m):
    ip = req.client_ip
    now = time.time()
    b = req.body_json()
    login = str(b.get("login") or "")[:64]
    with _rate_lock:
        if len(_rate) > 5000:                          # перепроверка В2-н3: словари не растут без предела
            for k in [k for k, v in _rate.items() if not v or now - v[-1] >= 60]:
                _rate.pop(k, None)
                _rate_noted.pop(k, None)
        lst = [t for t in _rate.get(ip, []) if now - t < 60]
        over = len(lst) >= LOGIN_RATE
        first_over = over and not _rate_noted.get(ip, 0) > now - 60
        if over:
            _rate_noted[ip] = now if first_over else _rate_noted.get(ip, now)
        else:
            lst.append(now)
        _rate[ip] = lst
    if over:
        if first_over:                                 # в журнал — раз в минуту на адрес, а не каждую попытку (не забить базу)
            audit.write(ops.Ctx(None, login or "?", "", ip, "web"), "auth.rate_limit", "ip:" + ip, None,
                        result="refused", message="предел %d попыток входа в минуту с адреса" % LOGIN_RATE)
        raise HttpError(429, "слишком много попыток входа; подождите минуту")
    cn = db.admin()
    try:
        try:
            u, need_setup = auth.authenticate(cn, login, str(b.get("password") or ""), str(b.get("totp_code") or ""), ip)
        except auth.Busy as ex:
            raise HttpError(503, str(ex))
        except auth.AuthError as ex:
            audit.write(ops.Ctx(None, login or "?", "", ip, "web"), "auth.login", "panel:" + login, None,
                        result="refused", message=str(ex))
            raise HttpError(403, str(ex))
        token, csrf = auth.session_create(cn, u, ip, req.headers.get("User-Agent", ""))
        auth.session_cleanup(cn)
    finally:
        cn.close()
    audit.write(ops.Ctx(u["id"], u["login"], u["role"], ip, "web"), "auth.login", "panel:" + u["login"], None,
                message="вход" + (" (нужно настроить второй фактор)" if need_setup else ""))
    req.set_cookie = session_cookie(token, config.get().session_abs_hours * 3600)
    return {"ok": True, "csrf": csrf, "need_totp_setup": need_setup}


@route("POST", r"/api/logout", full=False)
def api_logout(req, m):
    cn = db.admin()
    try:
        auth.session_revoke(cn, token=req.token)
    finally:
        cn.close()
    audit.write(_ctx(req), "auth.logout", "panel:" + req.session["user"]["login"], None, message="выход")
    req.set_cookie = session_cookie("", 0)
    return {"ok": True}


@route("GET", r"/api/me", full=False)
def api_me(req, m):
    u = req.session["user"]
    return {"user": auth.public_user(u), "role_title": auth.ROLE_TITLES.get(u["role"], u["role"]),
            "perms": auth.perms_of(u["role"]), "csrf": req.session["csrf"],
            "need_totp_setup": req.session["need_totp_setup"], "ref": refdata.manifest()}


@route("POST", r"/api/self/totp/begin", perm="self.manage", full=False)
def api_totp_begin(req, m):
    try:
        uri, b32 = panel_users.totp_begin(_ctx(req))
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))
    from core import qr
    return {"uri": uri, "secret": b32, "qr": qr.matrix(uri)}     # QR для приложения-аутентификатора (строки 0/1)


@route("POST", r"/api/self/totp/enable", perm="self.manage", full=False)
def api_totp_enable(req, m):
    return _run_op(req, "self.totp_enable", req.body_json(), False)


@route("POST", r"/api/self/password", perm="self.manage", full=False)
def api_self_password(req, m):
    r = _run_op(req, "self.password", req.body_json(), False)
    cn = db.admin()
    try:   # ревизия А0 №10: смена своего пароля гасит все прочие сессии этого пользователя
        auth.session_revoke_others(cn, req.session["user"]["id"], req.token)
    finally:
        cn.close()
    return r


# ---------------------------------------------------------------- маршруты: разделы

@route("GET", r"/api/status", perm="status.view")
def api_status(req, m):
    return status.snapshot(force=req.query.get("force") == "1")


@route("GET", r"/api/bridge", perm="players.view")
def api_bridge(req, m):
    """Мост P127: узлы (пульс, режим) и кто в игре по данным GameServer (?uid= — одна учётка)."""
    from domains import live
    uid = req.query.get("uid")
    return live.who(int(uid) if uid and uid.isdigit() else None)


@route("GET", r"/api/jobs", perm="jobs.view")
def api_jobs(req, m):
    """★ А5.1: задания планировщика adm.job (новые сверху; ?all=1 — и законченные) и операции, которые роль может ставить в задания.
    Управление стойкой — только restart_stack.py с ПК: из панели оно ставится заданием (исполняет консоль ПК, jobs run-due)."""
    from core import jobs
    from domains import stack
    return {"items": jobs.list_jobs(100, active=req.query.get("all") != "1"), "schedulable": stack.schedulable(_ctx(req)),
            "now_utc": jobs.utc_now().isoformat(sep=" "), "grace_s": jobs.GRACE_S}


@route("GET", r"/api/dbbackup", perm="db.view")
def api_dbbackup(req, m):
    """★ А5.7: бэкапы БД — базы списка (модель, размеры, последний бэкап любого инструмента по истории msdb), бэкапы панели, место на томе
    папки, предупреждения (возраст > WARN_HOURS, не проверен, нет ни одного). Только чтение; бэкап — операцией db.backup (заданием службы)."""
    from domains import dbbackup
    return dbbackup.state()


@route("GET", r"/api/bakdrop", perm="db.view")
def api_bakdrop(req, m):
    """★ А5.8: служебные копии (*_bak_*, AsdaProcBak*, …) игровых баз — вердикт каталога (можно убрать / нужна откату / неизвестно), размер,
    даты, происхождение, ссылки на копию, свежий проверенный бэкап базы, журнал удалений. Только чтение; удаление — операцией db.bakdrop."""
    from domains import bakdrop
    return bakdrop.state(force=req.query.get("force") == "1")   # ★ ревизия 48 (мелочь 9): из памяти 60 с, «Обновить» — не чаще раза в 15 с


@route("GET", r"/api/maint", perm="status.view")
def api_maint(req, m):
    """★ А5.3: режим обслуживания — SQL-часть L09 (таблица, врезка, режим, счётчики), DLL L09 по журналу патчей LoginManager,
    кто в игре по мосту вне 1…5000, вошедшие по БД (только чтение; ?force=1 — журнал патчей без кэша)."""
    from domains import maint
    return maint.state(force=req.query.get("force") == "1")


@route("GET", r"/api/events", perm="status.view")
def api_events(req, m):
    """★ А5.4: события опыта/добычи (Event.dat всех NpcServer и зеркал GS), счастливые часы (GameServerEvent.txt ×3), карты, часы
    сервера и предупреждения; ?daily=1 — и ежедневные задания доски (журнал сброса, задача ОС). Только чтение."""
    from domains import events
    try:
        out = events.state()
        if req.query.get("daily") == "1":
            out["daily"] = events.daily_state()
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))
    return out


@route("GET", r"/api/patchcfg", perm="patchcfg.view")
def api_patchcfg(req, m):
    """★ А5.5: настройки серверных патчей — ini наших DLL во всех копиях, режимы по журналу патчей последнего запуска, описание из реестра
    (?force=1 — без кэша); ?configs=1 — стоковые конфиги стойки (секреты без содержимого). Только чтение; правка — набором изменений."""
    from domains import patchcfg
    try:
        if req.query.get("configs") == "1":
            out = patchcfg.configs()
            for c in out["configs"]:
                c["what"], c["why"] = i18n.tr(c.get("what") or ""), i18n.tr(c.get("why") or "")
            return out
        out = patchcfg.state(force=req.query.get("force") == "1")
        # ★ ревизия 45 В-4: причины «только просмотр» у ключей — переводом отдельной таблицей (state() кэшируется общим для языков)
        vo = {k["view_only"]: i18n.tr(k["view_only"]) for d in out["dlls"] for s in d["sections"] for k in s["keys"] if k.get("view_only")}
        return dict(out, warnings=[i18n.tr(w) for w in out["warnings"]], tr=vo)
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))


@route("GET", r"/api/logs", perm="logs.view")
def api_logs(req, m):
    """★ А5.6: источники журналов стойки (белый список: копии, подпапки, шаблоны имён, кодировка, ротация, как пишет писатель) и лимиты."""
    from domains import logs
    out = logs.catalog()
    for s in out["sources"]:
        s["title"], s["rotation"], s["how"] = i18n.tr(s["title"]), i18n.tr(s["rotation"]), i18n.tr(s["how"])
    return out


def _logs_call(req, fn):
    """Общий обработчик журналов: предел частоты (429), отказы (409)."""
    from domains import logs
    try:
        return fn(logs)
    except logs.Throttled as ex:
        raise HttpError(429, str(ex))
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))


@route("GET", r"/api/logs/files", perm="logs.view")
def api_logs_files(req, m):
    """★ А5.6: файлы журнала копии (?source=&proc=[&kind=]) — новые сверху; размер и время по пути (не из листинга каталога)."""
    q, u = req.query, req.session["user"]

    def go(logs):
        logs.throttle(u["login"])
        out = logs.files(q.get("source", ""), q.get("proc", ""), q.get("kind") or None)
        if out.get("note"):
            out["note"] = i18n.tr(out["note"])
        return out
    return _logs_call(req, go)


@route("GET", r"/api/logs/tail", perm="logs.view")
def api_logs_tail(req, m):
    """★ А5.6: хвост файла журнала (?source=&proc=&file=[&kind=][&lines=][&q=][&level=][&scan=]; «следить» — &since=&sig=: тот же
    «размер:время» — без открытия данных). Секреты маскируются всегда, IP / MAC — без права logs.view_ip. Только чтение."""
    q, u = req.query, req.session["user"]

    def go(logs):
        key = (q.get("source", ""), q.get("proc", ""), q.get("kind", ""), q.get("file", ""))
        logs.throttle(u["login"], logs.norm_key(*key))                # ★ ревизия 46 С-2: ключ без учёта регистра; бюджет байт и семафор — в tail
        return logs.tail(key[0], key[1], key[3], q.get("kind") or None, q.get("lines"), q.get("q"), q.get("level") or None,
                         q.get("scan"), q.get("since"), q.get("sig"), auth.can(u["role"], "logs.view_ip"),
                         head=q.get("head") or None, user=u["login"])
    return _logs_call(req, go)


def _ac_kind_en(rec, key="kind_text"):
    """★ А6.1: текст вида журнала античита на языке запроса (сырой текст — в kind_raw, он же значение фильтра); причина «служебная» —
    переводом шаблона. Тексты видов — данные серверных патчей: перевод только из i18n.AC_KINDS, без общих шаблонов."""
    rec["kind_raw"] = rec.get(key)
    if i18n.is_en():
        rec[key] = i18n.AC_KINDS.get(rec[key], rec[key]) if isinstance(rec.get(key), str) else rec.get(key)
        if isinstance(rec.get("service"), str):
            rec["service"] = i18n.tr(rec["service"])
        if isinstance(rec.get("hint"), str):
            rec["hint"] = i18n.tr(rec["hint"])
        if isinstance(rec.get("title"), str):
            rec["title"] = i18n.tr(rec["title"])
    return rec


def _ac_call(fn):
    """★ А6.1: общий обработчик экрана «Античит»: отказ проверки ввода — 409."""
    try:
        return fn()
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))


@route("GET", r"/api/ac/catalog", perm="ac.view")
def api_ac_catalog(req, m):
    """★ А6.1: каталог видов журнала античита (номер, текст, патч, служебная — по AcJournal.cpp KindText и ac-journal-p53.md §9),
    таблицы ac.* и серверы-источники журнала. Только чтение."""
    from domains import acjournal

    def go():
        cat = acjournal.catalog_public()
        for t in cat["tables"]:
            t["title"] = i18n.tr(t["title"])
            t["kinds"] = [_ac_kind_en(dict(k), "kind") for k in t["kinds"]]
        cat["unknown_hint"] = i18n.tr(cat["unknown_hint"])
        return dict(cat, servers=acjournal.servers(), can_ip=auth.can(req.session["user"]["role"], "players.view_net"))
    return _ac_call(go)


@route("GET", r"/api/ac/events", perm="ac.view")
def api_ac_events(req, m):
    """★ А6.1: лента всех 8 таблиц ac.* по времени (?account=&char=&ip=&table=&kind=таблица:текст&server=&from=ГГГГММДД&to=&service=1
    &page=&size=). IP — в строках и в фильтре только с правом players.view_net. Только чтение."""
    from domains import acjournal
    can_ip = auth.can(req.session["user"]["role"], "players.view_net")

    def go():
        out = acjournal.events(req.query, can_ip)
        out["rows"] = [_ac_kind_en(r) for r in out["rows"]]
        return out
    return _ac_call(go)


@route("GET", r"/api/ac/summary", perm="ac.view")
def api_ac_summary(req, m):
    """★ А6.1: виды за сутки (?day=ГГГГММДД, по умолчанию — сегодня по часам SQL-сервера), топ нарушителей за 7 суток
    (ac.v_top_offenders + число нарушений без служебных), учётки за сутки (ac.v_account_daily). Только чтение."""
    from domains import acjournal

    def go():
        out = acjournal.summary(req.query.get("day") or None)
        out["kinds"] = [_ac_kind_en(k) for k in out["kinds"]]
        return out
    return _ac_call(go)


# ★ А6.2 (21.11): раздел «Деньги» — монетизация gp7, только чтение (domains/money.py). Отказ проверки ввода — 409 (как у «Античита»).
@route("GET", r"/api/money/summary", perm="money.view")
def api_money_summary(req, m):
    """★ А6.2: итоги покупок gp7 по категориям учёток (?svc=sep|in — служебные ≤ 5000 отдельно или в общем итоге), подарки по состояниям,
    висящие (?minutes=), балансы, сток рядом, testFixedBalance шлюза. Только чтение."""
    from domains import money
    return _ac_call(lambda: money.summary(req.query))


@route("GET", r"/api/money/purchases", perm="money.view")
def api_money_purchases(req, m):
    """★ А6.2: журнал покупок gp7 по всем учёткам (?account=&code=&kind=buy|gift|refund|fail&who=player|service|nolink&test=0|1&from=ГГГГММДД
    &to=&svc=&page=&size=). Только чтение."""
    from domains import money
    return _ac_call(lambda: money.purchases(req.query))


@route("GET", r"/api/money/gifts", perm="money.view")
def api_money_gifts(req, m):
    """★ А6.2: подарки gp7 (?state=H|C|R&test=0|1&hanging=1&minutes=&account=&from=&to=&page=&size=). Только чтение."""
    from domains import money
    return _ac_call(lambda: money.gifts(req.query))


@route("GET", r"/api/money/holds", perm="money.view")
def api_money_holds(req, m):
    """★ А6.2: висящие подарки 'H' старше ?minutes= — сверка gift_reconcile (подсказка commit / refund / неясно, ничего не применяется).
    Подсказка — текст сверки: переводится шаблоном. Только чтение."""
    from domains import money

    def go():
        out = money.holds(req.query)
        for h in out["holds"]:
            h["hint_raw"] = h["hint"]
            h["hint"], h["hint_why"] = i18n.tr(h["hint"]), i18n.tr(h["hint_why"])
        return out
    return _ac_call(go)


@route("GET", r"/api/money/sales", perm="money.view")
def api_money_sales(req, m):
    """★ А6.2: продажи по дням и позициям (?from=&to=ГГГГММДД — по умолчанию 30 суток, ?who=&svc=): gp7 и рядом сток (пометка «сток»,
    в итог не входит), сверка номеров заказов gp7 ↔ CashUse. Только чтение."""
    from domains import money
    return _ac_call(lambda: money.sales(req.query))


@route("GET", r"/api/money/undelivered", perm="money.view")
def api_money_undelivered(req, m):
    """★ 22.11: «Оплачено, не выдано» — заказы gp7 без строки стока своей процедуры и без ящика, причина A / B / не установлена по журналам
    (белый список domains/logs.py), до первого номера в CashUse — «неприменима» (?who=&from=&to=&minutes=&svc=&logs=0|1). Только чтение."""
    from domains import money

    def go():
        out = money.undelivered(req.query, req.session["user"]["login"])     # ★ ревизия 53 Н-2: бюджет журналов — на пользователя
        for r in out["rows"]:
            r["reason_why"] = i18n.tr(r["reason_why"]) if r.get("reason_why") else r.get("reason_why")
        return out
    return _ac_call(go)


@route("GET", r"/api/money/accounts", perm="money.view")
def api_money_accounts(req, m):
    """★ А6.2: связь учётки сайта gp7 с игровой (?account=&who=&page=&size=): баланс, покупки, служебная ли. Только чтение."""
    from domains import money
    return _ac_call(lambda: money.accounts(req.query))


# ★ А6.9 (22.11): журнал корректировок баланса gp7 (adm.GP7AdjustLog, domains/gp7adjust.py) — чтение, право money.view; сама корректировка —
#   операция money.adjust (/api/ops/money.adjust, право money.adjust — только owner). Корректировки — не выручка. Отказ проверки ввода — 409.
@route("GET", r"/api/money/adjustments", perm="money.view")
def api_money_adjustments(req, m):
    """★ А6.9: журнал корректировок (?account=&page=&size=): кому, сколько, было → стало, причина, оператор, откат. Только чтение."""
    from domains import gp7adjust
    return _ac_call(lambda: gp7adjust.adjustments(req.query))


# ★ А6.3 (21.11): «Экономика: золото» (domains/econ.py) — чтение игровых баз; снимок пишет только AsdaAdmin (операция econ.snapshot,
#   /api/ops/econ.snapshot). Отказ проверки ввода — 409.
@route("GET", r"/api/econ/summary", perm="econ.view")
def api_econ_summary(req, m):
    """★ А6.3: золото на руках по категориям, последний снимок и неучтённое, каталог источников, не считающиеся таблицы (?svc=)."""
    from domains import econ
    return _ac_call(lambda: econ.summary(req.query))


@route("GET", r"/api/econ/flows", perm="econ.view")
def api_econ_flows(req, m):
    """★ А6.3: потоки золота по дням и источникам (?from=&to=&svc=&source=); знак — по реверсу процедур Joy1."""
    from domains import econ
    return _ac_call(lambda: econ.flows(req.query))


@route("GET", r"/api/econ/richest", perm="econ.view")
def api_econ_richest(req, m):
    """★ А6.3: богатейшие персонажи по золоту Item.Code = 20551 (?n=&svc=)."""
    from domains import econ
    return _ac_call(lambda: econ.richest(req.query))


@route("GET", r"/api/econ/rare", perm="econ.view")
def api_econ_rare(req, m):
    """★ А6.3: «редкое на руках» по таблице редкого P11/P59 (?n=&svc=)."""
    from domains import econ
    return _ac_call(lambda: econ.rare(req.query))


@route("GET", r"/api/econ/unaccounted", perm="econ.view")
def api_econ_unaccounted(req, m):
    """★ А6.3: снимки золота и «снимок − журналы» = неучтённое по парам снимков и по персонажам (?id=&svc=)."""
    from domains import econ
    return _ac_call(lambda: econ.unaccounted(req.query))


# ★ А6.4 (22.11): «Передачи и рынок» (domains/trade.py) — только чтение игровых баз; право econ.view, сеть (LogInfo: IP, MAC, связь пары) —
#   только с players.view_net. Отказ проверки ввода — 409.
@route("GET", r"/api/trade/graph", perm="econ.view")
def api_trade_graph(req, m):
    """★ А6.4: граф «кто кому» за период (?from=&to=ГГГГММДД — по умолчанию 30 суток, ?account=&group=trade|store|auction|gift&svc=sep|in):
    пары по правилу M3 (ac_metrics_db), цепочки, серийники, зеркала, ящик; сеть — только с правом players.view_net."""
    from domains import trade
    return _ac_call(lambda: trade.graph(req.query, can_net=req.can("players.view_net")))


@route("GET", r"/api/trade/transfers", perm="econ.view")
def api_trade_transfers(req, m):
    """★ А6.4: передачи построчно (?from=&to=&account=&pair=N-N&group=&svc=&page=&size=), новые сверху."""
    from domains import trade
    return _ac_call(lambda: trade.transfers(req.query))


@route("GET", r"/api/trade/market", perm="econ.view")
def api_trade_market(req, m):
    """★ А6.4: рынок — живые лоты Exitem с ценами, цены по кодам, история аукциона (?page=), налог (?from=&to=&svc=)."""
    from domains import trade
    return _ac_call(lambda: trade.market(req.query))


@route("GET", r"/api/trade/stores", perm="econ.view")
def api_trade_stores(req, m):
    """★ А6.4: лавки — сделки PersonalStore*, журнал Log_SelfStore (?logs=0|1) и сверка по дням; открытые лавки — пометка «показать нельзя»."""
    from domains import trade

    def go():
        out = trade.stores(req.query, req.session["user"]["login"])     # ★ ревизия 54 Н-4: бюджет журналов — на пользователя
        out["open_note"] = i18n.tr(out["open_note"])
        return out
    return _ac_call(go)


# ★ А6.5 (22.11): «Шансы: выпало против заявленного» (domains/odds.py) — только чтение игровых баз, таблиц сервера и журналов стойки;
#   право econ.view; бюджет чтения журналов (Log_GachaItem, журнал шлюза gp7) — на пользователя запроса. Отказ проверки ввода — 409.
@route("GET", r"/api/odds/upgrade", perm="econ.view")
def api_odds_upgrade(req, m):
    """★ А6.5: заточка по ступени и свитку против ItemUpgrade / OverUpgrade, высшая переработка, перенос, извлечение (?from=&to=&svc=&alpha=)."""
    from domains import odds
    return _ac_call(lambda: odds.public(odds.upgrade(req.query)))


@route("GET", r"/api/odds/boosters", perm="econ.view")
def api_odds_boosters(req, m):
    """★ А6.5: призы бустеров против весов GachaItemRateTable, воспроизведение по Log_GachaItem (?logs=0|1&from=&to=&svc=&alpha=)."""
    from domains import odds
    return _ac_call(lambda: odds.public(odds.boosters(req.query, req.session["user"]["login"])))


@route("GET", r"/api/odds/boxes", perm="econ.view")
def api_odds_boxes(req, m):
    """★ А6.5: премиум-коробки gp7 (журнал шлюза, rewardIndex) против равномерного выбора по строкам PrimiumGaChaTable (?from=&to=&svc=&alpha=)."""
    from domains import odds
    return _ac_call(lambda: odds.public(odds.boxes(req.query, req.session["user"]["login"])))


# ★ А6.6 (22.11): «Античит: суточный отчёт» (domains/acdaily.py) — прогоны исходника ac_daily_report из AsdaAdmin adm.AcDaily; право ac.view,
#   IP и MAC — только с players.view_net (иначе маска «—»); английский вид текстов отчёта — domains/acdaily_en. Прогон — операция ac.daily
#   (/api/ops/ac.daily, право ac.daily_run). Отказ проверки ввода — 409.
def _acd_out(req, out, kind):
    from domains import acdaily_en
    if kind == "report" and i18n.is_en():
        out = acdaily_en.view(out)
    elif kind == "events" and i18n.is_en():
        out["rows"] = acdaily_en.rows(out["rows"])
    if not auth.can(req.session["user"]["role"], "players.view_net"):
        out = mask_net(out)
        out["ip_hidden"] = True
    return out


@route("GET", r"/api/acdaily/list", perm="ac.view")
def api_acdaily_list(req, m):
    """★ А6.6: прогоны суточного отчёта (?day=ГГГГММДД — с этими последними сутками окна), время службы, прежние пороги."""
    from domains import acdaily
    return _ac_call(lambda: dict(acdaily.reports(req.query), can_run=auth.can(req.session["user"]["role"], "ac.daily_run")))


@route("GET", r"/api/acdaily/report", perm="ac.view")
def api_acdaily_report(req, m):
    """★ А6.6: отчёт (?id=N | ?day=ГГГГММДД — последний за сутки | без них — последний): итог по метрикам, флаги вне владельца / фон,
    заметки, таблицы, последние события."""
    from domains import acdaily
    return _ac_call(lambda: _acd_out(req, acdaily.report(req.query), "report"))


@route("GET", r"/api/acdaily/events", perm="ac.view")
def api_acdaily_events(req, m):
    """★ А6.6: события одной метрики прогона (?id=&metric=&page=&size=) — то, что исходник пишет в CSV."""
    from domains import acdaily
    return _ac_call(lambda: _acd_out(req, acdaily.events(req.query), "events"))


@route("GET", r"/api/acdaily/md", perm="ac.view")
def api_acdaily_md(req, m):
    """★ А6.6: Markdown исходника этого прогона как есть (?id=N | ?day=)."""
    from domains import acdaily
    return _ac_call(lambda: _acd_out(req, acdaily.markdown(req.query), "md"))


# ★ А6.8 (22.11, часть «чтение»): «Античит: автоблок и EAC» (domains/autoblock.py) — сверка лестницы ac_case с patches.ini P48 / P69 тем же
#   кодом, что ac_case.py ladder --check, история автоблоков, EAC по учётке (вторая часть — точка статуса EacServer); только чтение, право ac.view. Правка
#   автоблока — набором patch.set «Настроек патчей». Отказ проверки ввода — 409.
def _ab_ladder_en(out):
    if i18n.is_en():
        out = dict(out, ladder=[dict(x, name=i18n.tr(x.get("name") or ""), mechanism=i18n.tr(x.get("mechanism") or "")) for x in out["ladder"]])
    return out


@route("GET", r"/api/autoblock/ladder", perm="ac.view")
def api_autoblock_ladder(req, m):
    """★ А6.8: лестница санкций против patches.ini AsdaPatch всех копий GameServer (сроки ступеней 3–5), паритет копий, режим P48 / P69 / P73
    по журналу патчей, счётчики киков и нарушений. Кэш 60 с."""
    from domains import autoblock
    return _ac_call(lambda: _ab_ladder_en(autoblock.ladder()))


@route("GET", r"/api/autoblock/history", perm="ac.view")
def api_autoblock_history(req, m):
    """★ А6.8: история автоблоков (?from=ГГГГММДД&to=&account=&svc=sep|in): кики и автоблоки P48, ступени P69, BlockList / BlockHistory с
    причиной, сроком, происхождением и снятием (adm.audit панели)."""
    from domains import autoblock
    return _ac_call(lambda: autoblock.history(req.query, req.session["user"]["login"]))   # ★ ревизия 58 М-2: бюджет Log_SpeedHack — на пользователя


# ★ А6.7 (22.11): «Античит: дела» (domains/cases.py) — журнал дел joylog1.san.* тем же кодом, что AstoryServer/Tools/Anticheat/ac_case.py; просмотр — право
#   ac.view (IP событий — только с players.view_net), действия — операции case.* (/api/ops/case.<действие>, права ac.case / ac.decide /
#   ac.appeal). Отказ проверки ввода — 409.
def _cs_mask(req, out):
    if auth.can(req.session["user"]["role"], "players.view_net"):
        return out
    for e in out.get("events") or []:
        e["ip"] = "•••" if e.get("ip") else e.get("ip")
    if isinstance(out.get("md"), str):
        out["md"] = MAC_RX.sub("•••", IPV4_RX.sub("•••", out["md"]))
    return out


def _cs_en(out):
    if i18n.is_en():
        if out.get("ladder"):
            out = dict(out, ladder=[dict(x, name=i18n.tr(x.get("name") or ""), mechanism=i18n.tr(x.get("mechanism") or "")) for x in out["ladder"]])
        for c in out.get("cases") or []:
            c["case_lines"] = [i18n.tr(x) for x in c.pop("lines", [])]
        if isinstance(out.get("sources"), list):
            out["sources"] = ["file: " + x[6:] if x.startswith("файл: ") else i18n.tr(x) for x in out["sources"]]
    else:
        for c in out.get("cases") or []:
            c["case_lines"] = c.pop("lines", [])
    return out


@route("GET", r"/api/cases/ladder", perm="ac.view")
def api_cases_ladder(req, m):
    """★ А6.7: лестница санкций и правила дел (ac_case_config.json исходника), хранилище доказательств, можно ли писать (только на сервере)."""
    from domains import cases
    return _ac_call(lambda: dict(_cs_en(cases.ladder(_ctx(req))), perms={p: auth.can(req.session["user"]["role"], p)
                                                                         for p in ("ac.case", "ac.decide_low", "ac.decide", "ac.appeal", "logs.view")}))


@route("GET", r"/api/cases/list", perm="ac.view")
def api_cases_list(req, m):
    """★ А6.7: дела san.v_cases (?status=&account=номер|логин&training=0|1), новые сверху, не больше 500."""
    from domains import cases
    return _ac_call(lambda: cases.case_list(_ctx(req), req.query))


@route("GET", r"/api/cases/show", perm="ac.view")
def api_cases_show(req, m):
    """★ А6.7: дело целиком (?case=AC-NNNN): поля, история, события со снимками, доказательства с sha256, блоки, BlockList сейчас, источники."""
    from domains import cases
    return _ac_call(lambda: _cs_en(_cs_mask(req, cases.show(_ctx(req), req.query.get("case")))))


@route("GET", r"/api/cases/verify", perm="ac.view")
def api_cases_verify(req, m):
    """★ А6.7: целостность (?case=AC-NNNN или все дела): файлы хранилища и sha256, лишние файлы, manifest, снимки событий, связь с BlockList."""
    from domains import cases
    return _ac_call(lambda: _cs_en(cases.verify(_ctx(req), req.query.get("case"))))


@route("GET", r"/api/autoblock/eac", perm="ac.view")
def api_autoblock_eac(req, m):
    """★ А6.8: EAC по учётке (?uid=N): процесс и порты AsdaEacServer, режим моста P73, KICK-события и журнал учётки, блок, счётчики;
    состояние сессии EAC сейчас — точка статуса службы EAC 127.0.0.1 (только на сервере). IP канала EAC и игры — только с players.view_net."""
    from domains import autoblock
    return _ac_call(lambda: autoblock.eac(req.query.get("uid"), can_net=auth.can(req.session["user"]["role"], "players.view_net")))


# ★ А6.11 (22.11, часть «имена»): «Очередь имён» (domains/namereview.py) — новые и сменённые имена за период, проверка тем же кодом, что
#   char.rename (правила A13); отметка «ок / сменить» — операция names.mark (/api/ops/names.mark). Право names.review. Отказ — 409.
@route("GET", r"/api/names/queue", perm="names.review")
def api_names_queue(req, m):
    """★ А6.11: очередь (?from=ГГГГММДД&to=&all=1&state=all|bad|open|ok|rename|stale&account=&svc=sep|in&page=&size=)."""
    from domains import namereview
    return _ac_call(lambda: dict(namereview.queue(req.query), can_rename=auth.can(req.session["user"]["role"], "players.rename")))


@route("GET", r"/api/names/marks", perm="names.review")
def api_names_marks(req, m):
    """★ А6.11: история отметок персонажа (?uid=&idx=)."""
    from domains import namereview
    return _ac_call(lambda: {"marks": namereview.marks_of(req.query.get("uid"), req.query.get("idx"))})


# ★ А6.11 (22.11, часть «жалобы», решение владельца №6): жалобы игроков из бота Discord (domains/reports.py) — очередь, карточка, скриншот;
#   разбор — операции report.take / report.close / report.case / report.reply (/api/ops/…). Право reports.view. Отказ — 409.
@route("GET", r"/api/reports/list", perm="reports.view")
def api_reports_list(req, m):
    """★ А6.11: очередь (?status=open|new|taken|closed|all&category=&target=&reporter=&mine=1&page=&size=)."""
    from domains import reports
    q = dict(req.query)
    q.pop("mine_login", None)
    if q.get("mine") == "1":
        q["mine_login"] = req.session["user"]["login"]
    return _ac_call(lambda: reports.report_list(q))


@route("GET", r"/api/reports/show", perm="reports.view")
def api_reports_show(req, m):
    """★ А6.11: карточка жалобы (?id=N) и что можно роли (разбор, дело, сеть)."""
    from domains import reports
    role = req.session["user"]["role"]
    return _ac_call(lambda: dict(reports.show(req.query.get("id")), me=req.session["user"]["login"],
                                 can={p: auth.can(role, p) for p in ("reports.handle", "ac.case", "ac.view", "players.view", "players.view_net")}))


@route("GET", r"/api/reports/file", perm="reports.view")
def api_reports_file(req, m):
    """★ А6.11: скриншот жалобы (?id=N) — base64, тип по сигнатуре (PNG / JPEG / GIF / WEBP); показ — <img src="data:…"> (CSP img-src data:)."""
    from domains import reports
    return _ac_call(lambda: reports.file_data(req.query.get("id")))


# ★ А6.12 (22.11, решение владельца №5): «Журнал чата» (domains/chatlog.py) — журнал joylog1.chat.message P129 и заглушки chat.mute; действия —
#   операции chat.mute / chat.unmute (/api/ops/…, откат — журнал действий). Право chat.view. Схемы chat нет — installed=False и пометка, не ошибка.
#   Текст сообщения — в поле chat_text (не «text»: поле text переводится _tr_fields, а слова игрока переводить нельзя). Отказ — 409.
@route("GET", r"/api/chat/state", perm="chat.view")
def api_chat_state(req, m):
    """★ А6.12: установлена ли схема chat, строк, первая и последняя запись, действующих заглушек, режим P129 по копиям, что можно роли."""
    from domains import chatlog
    role = req.session["user"]["role"]
    return _ac_call(lambda: dict(chatlog.state(), can={p: auth.can(role, p) for p in ("chat.mute", "chat.unmute", "players.view", "players.view_net",
                                                                                      "ac.view", "reports.view", "audit.undo")},
                                 role=role, login=req.session["user"]["login"], limits=chatlog.limits_of(role)))   # ★ р71 Н-3: пределы роли для экрана


@route("GET", r"/api/chat/messages", perm="chat.view")
def api_chat_messages(req, m):
    """★ А6.12: журнал (?from=ГГГГММДД&to=&channel=1,2&account=&char=&char_uid=&char_slot=&text=&map=&server=&mute=any|0|1|2&mute_id=&raw=1
    &page=&size=); поиск по тексту — бюджет на пользователя панели."""
    from domains import chatlog
    return _ac_call(lambda: chatlog.messages(req.query, user=req.session["user"]["login"]))


@route("GET", r"/api/chat/mutes", perm="chat.view")
def api_chat_mutes(req, m):
    """★ А6.12: заглушки (?state=active|expired|lifted|all&account=&page=&size=)."""
    from domains import chatlog
    return _ac_call(lambda: chatlog.mutes(req.query))


# ★ А6.10 (23.11, решение владельца 23.11): «Посещаемость» (domains/attendance.py) — сводка по учётке / персонажу / периоду, история
#   AttendanceDetail и журнал ручных отметок Joy1.adm.AttendanceAdjustLog; действия — операции attendance.credit / attendance.revoke
#   (/api/ops/…, право attendance.edit, откат — журнал действий). Право просмотра attendance.view (owner, admin, gm). Отказ ввода — 409.
@route("GET", r"/api/attendance", perm="attendance.view")
def api_attendance(req, m):
    """★ А6.10: сводка (?account=&char=&uid=&idx=&from=ГГГГММДД&to=&page=&size=) и что можно роли."""
    from domains import attendance
    role = req.session["user"]["role"]
    return _ac_call(lambda: dict(attendance.summary(req.query), role=role,
                                 can={p: auth.can(role, p) for p in ("attendance.edit", "attendance.undo_log", "players.view", "audit.undo")}))


# ★ А7.1 (23.11, решение владельца А7 №6 — только статус): «Выпуски» (domains/releases.py) — указатели сервера обновлений с проверкой подписи
#   и сроком, снимок ПК из AsdaAdmin adm.ReleasePcStatus (присылает консоль ПК: releases push / задание ПК release.push). Только чтение;
#   ?force=1 — перечитать сервер обновлений (не чаще раза в 30 с). Право releases.view (owner, admin).
@route("GET", r"/api/releases", perm="releases.view")
def api_releases(req, m):
    """★ А7.1: раздел «Выпуски» целиком; тексты предупреждений и ошибок — на языке запроса."""
    from domains import releases
    out = releases.view(force=req.query.get("force") == "1")
    o = dict(out["outside"], warnings=[i18n.tr(w) for w in out["outside"].get("warnings") or []])
    o["keyring"] = dict(o["keyring"], error=i18n.tr(o["keyring"].get("error") or ""))
    o["pointers"] = [dict(p, error=i18n.tr(p.get("error") or "")) for p in o["pointers"]]
    pc = dict(out["pc"], error=i18n.tr(out["pc"].get("error") or ""))
    role = req.session["user"]["role"]
    return dict(out, outside=o, pc=pc, warnings=[i18n.tr(w) for w in out["warnings"]],
                can={p: auth.can(role, p) for p in ("releases.push", "jobs.manage")})


# ★ А7.2 (23.11, решения владельца А7 №1, №8): «Сбои клиента» (domains/crashes.py) — сводка, которую присылает ПК (adm.ClientCrash*:
#   группы мест падения, частота, версии по времени, учётки — ссылкой на карточку), квота LogDrop (служба считает сама, ключ не нужен).
#   Только чтение; ?force=1 — перечитать LogDrop (не чаще раза в 30 с). Удаление старых .alog — операция crash.alog_prune (owner).
@route("GET", r"/api/crashes", perm="crash.view")
def api_crashes(req, m):
    """★ А7.2: раздел «Сбои клиента» целиком; тексты предупреждений и пометок — на языке запроса."""
    from domains import crashes
    out = crashes.view(force=req.query.get("force") == "1")
    s = out["summary"]
    tr_row = lambda r: dict(r, status_note=i18n.tr(r.get("status_note") or ""), version_note=i18n.tr(r.get("version_note") or ""),
                            code_name=i18n.tr(r.get("code_name") or ""))
    s = dict(s, error=i18n.tr(s.get("error") or ""), rows=[tr_row(r) for r in s.get("rows") or []],
             groups=[dict(g, code_name=i18n.tr(g.get("code_name") or ""), last_case=tr_row(g["last_case"]) if g.get("last_case") else None)
                     for g in s.get("groups") or []])
    ld = dict(out["logdrop"], error=i18n.tr(out["logdrop"].get("error") or ""))
    role = req.session["user"]["role"]
    return dict(out, summary=s, logdrop=ld, warnings=[i18n.tr(w) for w in out["warnings"]],
                can={p: auth.can(role, p) for p in ("crash.sync", "crash.prune", "jobs.manage", "players.view")})


# ★ А7.4 (23.11, решение владельца А7 №2): «Очередь Discord» (domains/outbox.py) — записи adm.Outbox (что, куда, статус, попытки, ошибка,
#   где опубликовано), предупреждения «бот не забирает» / «итог неизвестен». Только чтение; отмена, повтор, удаление и проверочная запись —
#   операции outbox.* (/api/ops/…). Право outbox.view (owner, admin). Отказ — 409.
@route("GET", r"/api/outbox", perm="outbox.view")
def api_outbox(req, m):
    """★ А7.4: очередь (?status=all|active|posted|failed|cancelled|expired|test) и что можно роли; пометки — на языке запроса."""
    from domains import outbox
    out = _ac_call(lambda: outbox.view(req.query))
    role = req.session["user"]["role"]
    return dict(out, error=i18n.tr(out.get("error") or ""), warnings=[i18n.tr(w) for w in out["warnings"]],
                rows=[dict(r, error=i18n.tr(r["error"]) if r["error"] else "", del_error=i18n.tr(r["del_error"]) if r["del_error"] else "")
                      for r in out["rows"]],
                can={p: auth.can(role, p) for p in ("community.post", "community.delete", "server.announce")})


# ★ А7.6 (24.11, решение владельца А7 №9): «Сообщество» (domains/community.py) — копия реестра бота Oracle (заявки, тестеры, предупреждения,
#   баны Discord), очередь команд боту со статусами, реестр исключённых против блока входа. Только чтение; команды — операции community.*
#   (/api/ops/…). Право community.view (owner, admin, gm). Отказ — 409. Итоги бота и пометки — на языке запроса; данные Discord — как есть.
@route("GET", r"/api/community", perm="community.view")
def api_community(req, m):
    """★ А7.6: экран «Сообщество» (?apps=pending|approved|rejected|all) и что можно роли."""
    from domains import community
    out = _ac_call(lambda: community.view(req.query))
    role = req.session["user"]["role"]
    return dict(out, error=i18n.tr(out.get("error") or ""), warnings=[i18n.tr(w) for w in out["warnings"]],
                cmds=[dict(r, result=i18n.tr(r["result"]) if r["result"] else "", title=i18n.tr(r["title"]),
                           undo_note=i18n.tr(r["undo_note"]) if r["undo_note"] else "") for r in out["cmds"]],
                block_stuck=[dict(s, result=i18n.tr(s["result"]) if s["result"] else "") for s in out["block_stuck"]],
                can={p: auth.can(role, p) for p in ("community.manage", "community.ban", "players.block", "players.unblock", "reports.view",
                                                    "audit.undo")})


# ★ А7.5 (23.11, решение владельца А7 №3): «Telegram владельцу» (domains/notify.py) — выключатели, события, отметки службы и отправителя на ПК,
#   последние записи очереди Telegram. Только чтение; выключатели и проверки — операции notify.rule.set / telegram.* (/api/ops/…). Право
#   notify.view (только owner). Отказ — 409.
@route("GET", r"/api/telegram", perm="notify.view")
def api_telegram(req, m):
    """★ А7.5: раздел Telegram и что можно роли; пометки — на языке запроса (тексты сообщений — как ушли владельцу, по-русски)."""
    from domains import notify
    out = _ac_call(lambda: notify.view())
    role = req.session["user"]["role"]
    return dict(out, error=i18n.tr(out.get("error") or ""), warnings=[i18n.tr(w) for w in out["warnings"]],
                rows=[dict(r, error=i18n.tr(r["error"]) if r["error"] else "", title=i18n.tr(r["title"]) if r["kind"] == "local" else r["title"])
                      for r in out["rows"]],
                can={p: auth.can(role, p) for p in ("notify.manage",)})


# ★ А7.7 (24.11, решение владельца А7 №7): «Заметки к выпуску» (domains/notes.py) — снимок текущего changelog с ПК (adm.NotesSnap), записи с
#   видом, состоянием и отметкой «опубликовано» (по итогу бота в adm.Outbox), черновик, история публикаций. Только чтение; черновик, отметка и
#   публикация — операции notes.* (/api/ops/…). Право notes.view (owner, admin). Отказ — 409. Тексты changelog — как есть (их пишет порт).
@route("GET", r"/api/notes", perm="notes.view")
def api_notes(req, m):
    """★ А7.7: экран «Заметки к выпуску» и что можно роли; пометки — на языке запроса."""
    from domains import notes
    role = req.session["user"]["role"]
    out = _ac_call(lambda: notes.view(req.query, role))            # ★ р82 М-5: полный текст записей с IP и путями — только owner
    return dict(out, error=i18n.tr(out.get("error") or ""), warnings=[i18n.tr(w) for w in out["warnings"]],
                posts=[dict(r, error=i18n.tr(r["error"]) if r["error"] else "") for r in out["posts"]],
                can={p: auth.can(role, p) for p in ("notes.draft", "notes.push", "community.post", "community.delete", "audit.undo", "jobs.manage")})


@route("GET", r"/api/mobgroups", perm="server.monsters")
def api_mobgroups(req, m):
    """★ ревизия 42 В-1: группы мобов карты (?node=GameServer&map=3) из .svr NpcServer узла — для окна призыва (только чтение)."""
    from domains import live
    try:
        info = live.map_groups(req.query.get("node", ""), int(req.query.get("map", "-1")))
    except ValueError:
        raise HttpError(400, "неверная карта")
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))
    return {"file": info["file"], "npc": info["npc"],
            "groups": [{"group": g, "total": v["total"], "event": v["event"]} for g, v in sorted(info["groups"].items())]}


@route("GET", r"/api/players/search", perm="players.view")
def api_search(req, m):
    return {"items": players.search(req.query.get("q", ""), net=req.can("players.view_net"))}


@route("GET", r"/api/players/list", perm="players.view")
def api_players_list(req, m):
    q = req.query
    return players.list_accounts(_qint(q, "page", 1, 1, 1000000), _qint(q, "size", players.LIST_PAGE, 1, 200),
                                 q.get("sort", "uid"), q.get("online") == "1")


@route("GET", r"/api/items/editinfo", perm="players.items_props")
def api_item_editinfo(req, m):
    """Свойства экземпляра предмета и все допустимые варианты (окно правки предмета)."""
    from domains import itemedit
    q = req.query
    try:
        return itemedit.describe(int(q.get("uid", "")), int(q.get("idx", "")), q.get("uuid", ""))
    except ValueError:
        raise HttpError(400, "неверные параметры")
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))


@route("GET", r"/api/items/giveinfo", perm="players.items_give")
def api_item_giveinfo(req, m):
    """Что и как выдастся по коду: сумка, стопка, и для снаряжения — допустимые опции, исходы гнезда 0 и ступени (окно выдачи)."""
    from domains import itemgive
    try:
        return itemgive.describe(int(req.query.get("code", "")))
    except ValueError:
        raise HttpError(400, "неверные параметры")
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))


@route("GET", r"/api/titles/char/(\d+)/(\d+)", perm="players.view")
def api_titles_char(req, m):
    """Звания персонажа: все записи FameInfo сервера с состоянием «получено / найдено / надето», слава, очки чести."""
    from domains import titles
    try:
        return titles.describe(int(m.group(1)), int(m.group(2)))
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))
    except Exception as ex:
        raise HttpError(409, "таблицы сервера не прочитаны: %s" % ex)


@route("GET", r"/api/skills/char/(\d+)/(\d+)", perm="players.view")
def api_skills_char(req, m):
    """Навыки персонажа (изученные, суммы деревьев, очки) и навыки, которые можно выдать."""
    from domains import skills
    try:
        return skills.describe(int(m.group(1)), int(m.group(2)))
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))
    except Exception as ex:
        raise HttpError(409, "таблицы сервера не прочитаны: %s" % ex)


@route("GET", r"/api/quests/char/(\d+)/(\d+)", perm="players.view")
def api_quests_char(req, m):
    """Задания персонажа: журнал, выполненные, доступные к выдаче."""
    from domains import quests
    try:
        return quests.describe(int(m.group(1)), int(m.group(2)))
    except Exception as ex:
        raise HttpError(409, "задания не прочитаны: %s" % ex)


@route("GET", r"/api/quests/rewards/(\d+)", perm="players.view")
def api_quests_rewards(req, m):
    """Варианты награды «завершить» задания (без привязки к персонажу)."""
    from domains import quests
    try:
        return {"quest": int(m.group(1)), "name": quests.refdata.quest(int(m.group(1))),
                "rewards": [{"id": v["id"], "exp": v["exp"], "gold": v["gold"], "items": v["items"], "sp": v["sp"]}
                            for v in quests.reward_variants(int(m.group(1)))]}
    except Exception as ex:
        raise HttpError(409, "таблицы сервера не прочитаны: %s" % ex)


@route("GET", r"/api/charrest/char/(\d+)/(\d+)", perm="players.view")
def api_charrest_char(req, m):
    """Внешность, баффы наборов, лагерь, ремесло, рыбалка, обучение, посещаемость персонажа (domains/charrest.py)."""
    from domains import charrest
    try:
        return charrest.describe(int(m.group(1)), int(m.group(2)))
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))
    except Exception as ex:
        raise HttpError(409, "данные персонажа не прочитаны: %s" % ex)


@route("GET", r"/api/charcopy/targets", perm="players.copy")
def api_charcopy_targets(req, m):
    """Служебные учётки (≤ 5000) и их свободные слоты — окно копии персонажа."""
    from domains import charcopy
    try:
        return charcopy.targets()
    except Exception as ex:
        raise HttpError(409, "учётки не прочитаны: %s" % ex)


@route("GET", r"/api/pets/char/(\d+)/(\d+)", perm="players.view")
def api_pets_char(req, m):
    """Питомцы персонажа."""
    from domains import pets
    try:
        return pets.describe(int(m.group(1)), int(m.group(2)))
    except Exception as ex:
        raise HttpError(409, "питомцы не прочитаны: %s" % ex)


@route("GET", r"/api/soulmate/(\d+)", perm="players.view")
def api_soulmate(req, m):
    """Соулмейт учётки: активная пара, история, персонажи (Share), кристаллы, таблица уровней."""
    from domains import soulmate
    try:
        return soulmate.describe(int(m.group(1)))
    except Exception as ex:
        raise HttpError(409, "соулмейт не прочитан: %s" % ex)


@route("GET", r"/api/soulmate/char/(\d+)/(\d+)", perm="players.view")
def api_soulmate_char(req, m):
    """Соулмейт — связь учётки персонажа (персонаж в пути — для кнопки в карточке)."""
    from domains import soulmate
    try:
        return soulmate.describe(int(m.group(1)))
    except Exception as ex:
        raise HttpError(409, "соулмейт не прочитан: %s" % ex)


@route("GET", r"/api/friends/char/(\d+)/(\d+)", perm="players.view")
def api_friends_char(req, m):
    """Друзья персонажа: строки, взаимность, онлайн друга, устаревшие имена."""
    from domains import friends
    try:
        return friends.describe(int(m.group(1)), int(m.group(2)))
    except Exception as ex:
        raise HttpError(409, "друзья не прочитаны: %s" % ex)


@route("GET", r"/api/clan/search", perm="players.view")
def api_clan_search(req, m):
    """Кланы по номеру или части имени."""
    from domains import clan
    try:
        return {"items": clan.search(req.query.get("q", ""))}
    except Exception as ex:
        raise HttpError(409, "кланы не прочитаны: %s" % ex)


@route("GET", r"/api/clan/(\d+)", perm="players.view")
def api_clan(req, m):
    """Клан: карточка, состав, объявления, лагерь."""
    from domains import clan
    try:
        return clan.describe(int(m.group(1)))
    except ops.OpRefused as ex:
        raise HttpError(404, str(ex))
    except Exception as ex:
        raise HttpError(409, "клан не прочитан: %s" % ex)


@route("GET", r"/api/gifts/catalog", perm="players.items_give")
def api_gift_catalog(req, m):
    """Позиции витрин 6000/15300 для подарка (поиск по коду или названию)."""
    from domains import gifts
    return {"items": gifts.catalog_rows(req.query.get("q", ""))}


@route("GET", r"/api/gifts/info", perm="players.items_give")
def api_gift_info(req, m):
    """Что получит игрок: код выдачи, тип покупки, состав коробки, пометки (kind gift — витрина, mail — любой код)."""
    from domains import gifts
    try:
        return gifts.describe(req.query.get("kind", "gift"), int(req.query.get("code", "")))
    except ValueError:
        raise HttpError(400, "неверные параметры")
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))
    except Exception as ex:                                   # перепроверка 19 К3: таблицы стойки не прочитаны — 409, не 500
        raise HttpError(409, "таблицы сервера не прочитаны: %s" % ex)


@route("GET", r"/api/shops/sets", perm="shop.view")
def api_shop_sets(req, m):
    """А3: наборы изменений магазинов (новые сверху)."""
    from domains import shopcs, shopdata
    # ★ А4.0: виды всех областей реестра (domains/cs_kinds) — с областью и правом правки (data.edit у областей А4)
    return {"items": shopcs.list_sets(), "kinds": [{"id": k, "title": v[0], "fields": list(v[1]), "urgent": v[2],
                                                    "area": shopdata.AREA_OF[k].AREA, "area_title": shopdata.AREA_OF[k].TITLE,
                                                    "perm": shopdata.area_perm(k, "edit"), "can": req.can(shopdata.area_perm(k, "edit"))}
                                                   for k, v in shopdata.KINDS.items()],
            "areas": [{"id": a.AREA, "title": a.TITLE} for a in shopdata.AREAS], "on_server": config.get().on_server}


@route("GET", r"/api/shops/set/(\d+)", perm="shop.view")
def api_shop_set(req, m):
    """А3: набор с позициями и итогом последней проверки (тексты — на языке запроса)."""
    from domains import shopcs
    try:
        cs = shopcs.get(int(m.group(1)))
    except ops.OpRefused as ex:
        raise HttpError(404, str(ex))
    if cs.get("check"):
        c = cs["check"]
        for p in c.get("positions", []):
            p["text"] = i18n.tr(p.get("text") or "")
            p["errors"] = [i18n.tr(x) for x in p.get("errors", [])]
            p["warnings"] = [i18n.tr(x) for x in p.get("warnings", [])]
        c["errors"] = [i18n.tr(x) for x in c.get("errors", [])]
        c["warnings"] = [i18n.tr(x) for x in c.get("warnings", [])]
        for b in c.get("balance", []):                    # ★ А4.0: правки баланса
            b["what"] = i18n.tr(b.get("what") or "")
        for p in c.get("positions", []):                  # ★ А4.3: строки «было / станет» с шансами
            if p.get("lines"):
                p["lines"] = [i18n.tr(x) for x in p["lines"]]
    return cs


@route("GET", r"/api/shops/diverge", perm="shop.view")
def api_shop_diverge(req, m):
    """А3: экран расхождений «сервер знает — клиент нет» и наоборот (живая стойка + клиент порта / снимок выкладки)."""
    from domains import shopdata
    try:
        # ★ А4.0: разделы всех областей; ★ ревизия 33 К-2: разделы данных игры А4 — по праву data.view
        d = shopdata.divergence(areas="all" if req.query.get("areas") == "all" and req.can("data.view") else None)
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))
    for s in d["sections"]:
        s["title"], s["note"] = i18n.tr(s["title"]), i18n.tr(s["note"])
        for r in s["rows"]:
            if "why" in r:
                r["why"] = i18n.tr(r["why"])
    return d


@route("GET", r"/api/shops/lookup", perm="shop.view")
def api_shop_lookup(req, m):
    """А3: текущее состояние цели для редактора позиции (код / строка бустера / пакет / автомат / лавка NPC)."""
    from domains import shopview
    try:
        if req.query.get("what", "") in (("equipshop", "honor", "hair") + shopview.MONSTER_WHAT + shopview.ITEM_WHAT + shopview.QUEST_WHAT
                                         + shopview.TITLE_WHAT + shopview.SKILL_WHAT + shopview.MAP_WHAT) and not req.can("data.view"):   # ★ ревизия 33 К-2; ★ А4.3…А4.8
            raise HttpError(403, "нет права «data.view»")
        return shopview.lookup(req.query.get("what", ""), req.query.get("id", ""))
    except ValueError:
        raise HttpError(400, "неверные параметры")
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))


@route("GET", r"/api/texts/search", perm="data.view")
def api_texts_search(req, m):
    """А4.2: тексты игры RU / EN — поиск по ключу (коду) или по тексту; виды текстов (живой порт на ПК / снимок выкладки на сервере)."""
    from domains.cs_kinds import texts
    try:
        ent = req.query.get("entity", "")
        out = texts.search(ent, req.query.get("q", "")) if ent else {"rows": []}
        out["entities"] = [dict(e, title=i18n.tr(e["title"])) for e in texts.entities()]
        return out
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))


@route("GET", r"/api/items/giveroll", perm="players.items_give")
def api_item_giveroll(req, m):
    """Кнопка «Случайно»: бросок опций, самоцвета и ступени — как у сервера при добыче (srvtables.roll_creation)."""
    from domains import itemgive, srvtables
    try:
        code = int(req.query.get("code", ""))
        if not itemgive.item_spec(code)["gear"]:
            raise HttpError(409, "опции бросаются только у брони и оружия")
        return srvtables.roll_creation(code)
    except ValueError:
        raise HttpError(400, "неверные параметры")
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))


@route("GET", r"/api/players/account/(\d+)", perm="players.view")
def api_account(req, m):
    net = req.can("players.view_net")
    try:
        r = players.account(int(m.group(1)), net=net)
    except players.NotFound as ex:
        raise HttpError(404, str(ex))
    if net:
        audit.write(_ctx(req), "players.net_view", "account:%s" % m.group(1), None,
                    message="просмотр входов (IP/MAC) и связанных учёток")
    return r


@route("GET", r"/api/players/gp7/(\d+)", perm="players.view")
def api_account_gp7(req, m):
    """19.11: покупки / подарки gp7 учётки страницами (только просмотр)."""
    q = req.query
    try:
        return players.gp7_page(int(m.group(1)), "gifts" if q.get("kind") == "gifts" else "purchases",
                                _qint(q, "page", 1, 1, 1000000))
    except players.NotFound as ex:
        raise HttpError(404, str(ex))


@route("GET", r"/api/players/discord_bans", perm="players.view")
def api_discord_bans(req, m):
    """19.11: реестр банов Discord против блока входа (расхождения первыми); копии реестра нет — items: null."""
    return {"items": players.discord_bans()}


@route("GET", r"/api/players/char/(\d+)/(\d+)", perm="players.view")
def api_char(req, m):
    try:
        return players.character(int(m.group(1)), int(m.group(2)))
    except players.NotFound as ex:
        raise HttpError(404, str(ex))


@route("GET", r"/api/players/feed/(\d+)", perm="feed.view")
def api_feed(req, m):
    q = req.query
    idx = int(q["idx"]) if q.get("idx", "").isdigit() else None
    groups = [g for g in q.get("groups", "").split(",") if g] or None
    net = req.can("players.view_net")
    if not net:
        groups = [g for g in (groups or sorted({e["group"] for e in feed.catalog()})) if g not in NET_GROUPS]
        if not groups:
            return {"items": [], "total": 0, "summary": [], "errors": [], "since": None}
    r = feed.feed(int(m.group(1)), idx, _qint(q, "days", 30, 1, 3650), groups, _qint(q, "limit", 300, 1, 2000))
    for it in r["items"]:
        it["fields"] = i18n.fields(mask_net(it["fields"]) if not net else it["fields"])
    return r


@route("GET", r"/api/feed/groups", perm="feed.view")
def api_feed_groups(req, m):
    return {"groups": sorted({e["group"] for e in feed.catalog()}), "tables": len(feed.catalog())}


@route("GET", r"/api/items/trace", perm="players.view")
def api_trace(req, m):
    try:
        r = feed.trace(req.query.get("serial", ""))
    except ValueError as ex:
        raise HttpError(400, str(ex))
    if not req.can("players.view_net"):
        r["events"] = [dict(e, fields=mask_net(e["fields"])) for e in r["events"]]
    r["events"] = [dict(e, fields=i18n.fields(e["fields"])) for e in r["events"]]
    return r


@route("GET", r"/api/items/dupes", perm="players.view")
def api_item_dupes(req, m):
    """Окно «Дюпы» (только чтение, domains/dupes.py): одинаковые Uuid, невозможные количества; full=1 — ещё «без следа появления»
    и «последнее событие — уничтожение, а строка жива» (по всем журналам, десяток секунд)."""
    from domains import dupes
    return dupes.report(full=req.query.get("full") == "1")


@route("GET", r"/api/items/recover/sources", perm="players.items_give")
def api_item_recover_sources(req, m):
    """События уничтожения номера и для каждого — предпросмотр возврата или причина отказа (domains/itemrecover.py)."""
    from domains import itemrecover
    try:
        r = itemrecover.sources(req.query.get("serial", ""))
    except ValueError as ex:
        raise HttpError(400, str(ex))
    for x in r["sources"]:
        x["fields"] = i18n.fields(x["fields"] if req.can("players.view_net") else mask_net(x["fields"]))
    return r


@route("GET", r"/api/items/search", perm="players.view")
def api_item_search(req, m):
    return {"items": refdata.search_items(req.query.get("q", ""))}


@route("GET", r"/api/audit", perm="audit.view")
def api_audit(req, m):
    q = req.query
    rows = audit.query(q.get("action", ""), q.get("login", ""), q.get("target", ""),
                       None, _qint(q, "limit", 200, 1, 1000), _qint(q, "before_id", 0, 0, 2 ** 62) or None)
    from domains import community
    notes = community.undo_notes(rows)                 # ★ ревизия 80 М-7: причины «откатывать нечего» — одним запросом на страницу
    for r in rows:
        op = ops.REGISTRY.get(r["action"])
        r["reversible"] = bool(op and op.reversible and r["result"] == "ok" and not r["undo_of"] and not r["undone_by"])
        r["two_factor"] = bool(r["reversible"] and ops.needs_two_factor(r["action"]))   # ★ ревизия 63 С-1: откат из браузера — с кодом
        why = notes.get(r["id"]) if r["reversible"] else None
        if why:                                         # ★ ревизия 79 В-1: у записи без того, что откатывать (команда боту ничего не изменила), — причина вместо кнопки
            r["reversible"], r["two_factor"], r["undo_note"] = False, False, i18n.tr(why)
        if r["action"] == "items.give" and r["result"] == "ok" and '"pending": true' in (r.get("after_json") or ""):
            from domains import itemgive as _ig                # ★ ревизия 29 М-2: поздний итог «неизвестной» живой выдачи
            note = _ig.pending_note(r.get("after_json"))
            if note:
                r["message"] = (r.get("message") or "") + " — " + note
    return {"items": rows}


@route("POST", r"/api/audit/(\d+)/undo", perm="audit.undo")
def api_undo(req, m):
    try:
        return ops.undo(_ctx(req), int(m.group(1)), req.body_json())   # ★ ревизия 63 С-1: тело — код второго фактора (totp)
    except ops.OpRefused as ex:
        raise HttpError(409, str(ex))


@route("GET", r"/api/users", perm="users.manage")
def api_users(req, m):
    return {"items": panel_users.list_users(), "roles": [{"id": r, "title": auth.ROLE_TITLES[r]} for r in auth.ROLES]}


@route("POST", r"/api/ops/([a-z_]+\.[a-z_]+)", perm=None)
def api_op(req, m):
    name = m.group(1)
    if name.startswith("self."):
        raise HttpError(404, "операции «о себе» — через /api/self/…")
    b = req.body_json()
    return _run_op(req, name, b.get("params") or {}, bool(b.get("dry")))


def _run_op(req, name, params, dry):
    """Выполнить операцию от имени пользователя сессии; отказ → 409. ★ А7.10: к предпросмотру (и к «кик + запись» — тоже предпросмотр)
    прикладывается справка операции doc (core/opdoc: что изменится, перезапуск, откат) — её показывает окно подтверждения."""
    try:
        res = ops.run(_ctx(req), name, params, dry)
    except (ops.OpRefused, auth.AuthError) as ex:
        raise HttpError(409, str(ex))
    if isinstance(res, dict) and res.get("dry"):
        from core import opdoc
        role = req.session["user"]["role"]
        # ★ ревизия 85 В-6: у job.add — справка ПЛАНИРУЕМОЙ операции и строка о самом задании (её отмене)
        res["doc"] = (opdoc.for_job(params, i18n.is_en(), role) if name == "job.add"
                      else opdoc.localized(name, ops.REGISTRY.get(name), i18n.is_en(), role))
    return res


# ★ А7.10 (24.11): «Справка» — все операции со справкой (что меняет, перезапуск, откат), правами по ролям и отметкой «доступно вам». Право —
#   status.view (есть у всех ролей): описание операций — не данные игроков; выполнить операцию без её права всё равно нельзя.
@route("GET", r"/api/opdoc", perm="status.view")
def api_opdoc(req, m):
    from core import opdoc
    out = opdoc.catalog(req.session["user"]["role"], i18n.is_en())
    out["roles"] = [{"id": r, "title": auth.ROLE_TITLES[r]} for r in auth.ROLES]      # подписи ролей переводит интерфейс (web/i18n.js)
    return out


# ★ ревизия 85 В-7 / М-9: справка одной операции — для окон, у которых нет предпросмотра через /api/ops: «о себе» (self.* идут своими маршрутами
#   /api/self/*: им нужна и сессия «только настройка второго фактора», и отзыв прочих сессий) и откат из журнала (справка исходной операции).
#   Подробности — только с правом самой операции. Сессия «только второй фактор» получает справку только self.*.
@route("GET", r"/api/opdoc/one", perm=None, full=False)
def api_opdoc_one(req, m):
    from core import opdoc
    name = req.query.get("name", "")
    op = ops.REGISTRY.get(name)
    if op is None or name not in opdoc.DOC:
        raise HttpError(404, "нет такой операции")
    if req.session["need_totp_setup"] and not name.startswith("self."):
        raise HttpError(403, "сначала включите второй фактор (раздел «О себе»)")
    role = req.session["user"]["role"]
    if not auth.can(role, op.perm):
        raise HttpError(403, "нет права «%s»" % op.perm)
    return {"doc": opdoc.localized(name, op, i18n.is_en(), role)}


# ---------------------------------------------------------------- обработчик

TR_KEYS = {"error", "errors", "message", "text", "warnings", "match", "edit_block", "notes", "case_lines", "mode_note",   # ★ р71 Н-2: режим P129 журнала чата
           "lost", "explain", "refused", "note", "why", "bridge_error", "db_error"}   # ★ А5.3: ошибки чтения в /api/maint             # 19.11: возврат по журналам, след v2, дюпы   # поля ответа с текстом для человека


def _tr_fields(v, depth=0):
    """Перевести текстовые поля ответа на язык запроса (core.i18n); прочее — как есть."""
    if not i18n.is_en() or depth > 6:
        return v
    if isinstance(v, list):
        return [_tr_fields(x, depth + 1) for x in v]
    if not isinstance(v, dict):
        return v
    out = {}
    for k, x in v.items():
        if k == "fields":                                  # перепроверка 5 М8: столбцы журналов — данные, не тексты службы
            out[k] = x
        elif k in TR_KEYS and isinstance(x, str):
            out[k] = i18n.tr(x)
        elif k in TR_KEYS and isinstance(x, list):
            out[k] = [i18n.tr(y) if isinstance(y, str) else y for y in x]
        else:
            out[k] = _tr_fields(x, depth + 1)
    return out


def host_allowed(host, cfg):
    """Заголовок Host допустим: имя из cfg.public_hosts (или адрес, на котором слушаем) и порт службы."""
    host = host.strip().lower()
    name, sep, port = host.rpartition(":")
    if not sep or not port.isdigit() or int(port) != cfg.bind_port:
        return False
    names = {x.strip().lower() for x in cfg.public_hosts.split(",") if x.strip()}
    if cfg.bind_host not in ("0.0.0.0", ""):
        names.add(cfg.bind_host.lower())
    return name in names


class Handler(BaseHTTPRequestHandler):
    """Один запрос: Host, сессия, CSRF, маршрут, JSON."""
    server_version = "AsdaAdmin"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 60                  # простой соединения, с (медленный/брошенный клиент не держит поток вечно)

    def setup(self):
        """TLS: рукопожатие здесь, в потоке запроса, с пределом времени (не в потоке приёма соединений)."""
        self._watch = None
        self._arm()                                    # рукопожатие входит в срок первого запроса
        try:
            if isinstance(self.request, ssl.SSLSocket):
                self.request.settimeout(15)
                self.request.do_handshake()
            super().setup()
        except BaseException:
            self._disarm()                             # перепроверка В1-н1: сорванное рукопожатие не оставляет таймер
            raise

    # Ревизия 16.11 вечер В1: таймаут сокета считается на ОДНО чтение — клиент, шлющий по байту, держал бы поток часами.
    # Сторож: строка, заголовки и тело запроса должны прийти за HEADER_DEADLINE_S, иначе соединение рвётся.
    def _arm(self):
        self._disarm()
        sock = self.request

        def kill():
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self._watch = threading.Timer(HEADER_DEADLINE_S, kill)
        self._watch.daemon = True
        self._watch.start()

    def _disarm(self):
        w = getattr(self, "_watch", None)
        if w:
            w.cancel()
            self._watch = None

    def handle_one_request(self):
        """Каждый запрос соединения (keep-alive) — под своим сторожем."""
        if getattr(self, "_served", False):
            self._arm()
        self._served = True
        try:
            super().handle_one_request()
        finally:
            self._disarm()

    def log_message(self, fmt, *args):
        """Журнал доступа — в stdout службы: метод, путь БЕЗ строки запроса (в ней бывают IP/логины поиска), код."""
        line = strip_query(fmt % args)
        print("%s %s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), self.client_address[0], line))

    @property
    def client_ip(self):
        return self.client_address[0]

    def body_json(self):
        """Тело запроса как dict (не JSON → 400)."""
        if self._body is None:
            return {}
        try:
            v = json.loads(self._body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise HttpError(400, "тело запроса — не JSON")
        if not isinstance(v, dict):
            raise HttpError(400, "тело запроса — не объект JSON")
        return v

    def can(self, perm):
        return bool(self.session) and auth.can(self.session["user"]["role"], perm)

    def _send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", CSP)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        if getattr(self, "set_cookie", None):
            self.send_header("Set-Cookie", self.set_cookie)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj):
        obj = _tr_fields(obj)
        self._send(code, json.dumps(obj, ensure_ascii=False, default=_json_default).encode("utf-8"),
                   "application/json; charset=utf-8", {"Cache-Control": "no-store"})

    def _host_ok(self):
        """Host = один из адресов сервера (config.public_hosts) с портом службы."""
        return host_allowed(self.headers.get("Host") or "", config.get())

    def _load_session(self):
        self.token, self.session = None, None
        raw = self.headers.get("Cookie")
        if not raw:
            return
        try:
            c = http.cookies.SimpleCookie(raw)
        except http.cookies.CookieError:
            return
        if COOKIE in c:
            self.token = c[COOKIE].value
            cn = db.admin()
            try:
                self.session = auth.session_get(cn, self.token)
            finally:
                cn.close()

    def do_GET(self):
        self._handle("GET")

    def do_HEAD(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def _handle(self, method):
        self.set_cookie = None
        self._body = None
        try:
            i18n.set_lang(self.headers.get("X-Asda-Lang"))          # язык ответа (RU / EN, владелец 16.11)
            if not self._host_ok():
                raise HttpError(421, "неверный адрес панели")
            u = urlparse(self.path)
            path = unquote(u.path)
            self.query = {k: v[0] for k, v in parse_qs(u.query).items()}
            if method == "POST":
                if self.headers.get("Transfer-Encoding"):
                    self.close_connection = True
                    raise HttpError(411, "тело запроса — только с Content-Length")
                raw_len = (self.headers.get("Content-Length") or "0").strip()
                # ревизия 16.11 вечер С1: «-1» давал rfile.read(-1) — чтение до конца соединения без предела
                if not re.fullmatch(r"[0-9]{1,9}", raw_len):      # только ASCII-цифры («²» и т.п. давали 500)
                    self.close_connection = True
                    raise HttpError(400, "неверный Content-Length")
                n = int(raw_len)
                if n > MAX_BODY:
                    self.close_connection = True      # тело не читаем — соединение дальше не годится
                    raise HttpError(413, "слишком большой запрос")
                self._body = self.rfile.read(n) if n else None
                if self._body is not None and len(self._body) != n:
                    self.close_connection = True
                    raise HttpError(400, "тело запроса оборвано")
            self._disarm()                             # запрос получен целиком — дальше работа службы, не клиента
            if not path.startswith("/api/"):
                return self._static(path)
            self._load_session()
            for meth, rx, fn, perm, full in ROUTES:
                mm = rx.match(path)
                if not mm or meth != method:
                    continue
                if fn is not api_login:
                    if not self.session:
                        raise HttpError(401, "нужно войти")
                    if self.session["need_totp_setup"] and full:
                        raise HttpError(403, "сначала включите второй фактор (раздел «О себе»)")
                    if perm and not self.can(perm):
                        raise HttpError(403, "нет права «%s»" % perm)
                if method == "POST":
                    want = "login" if fn is api_login else (self.session or {}).get("csrf")
                    if not want or self.headers.get("X-Asda-Csrf") != want:
                        raise HttpError(403, "запрос без подтверждения CSRF")
                return self._json(200, fn(self, mm))
            raise HttpError(404, "нет такого адреса")
        except HttpError as ex:
            if ex.code in (400, 411, 413, 421) and method == "POST" and self._body is None:
                self.close_connection = True           # непрочитанное тело не должно стать «следующим запросом»
            self._json(ex.code, {"ok": False, "error": ex.msg})
        except db.DbError as ex:
            self._json(502, {"ok": False, "error": str(ex)})
        except Exception as ex:
            traceback.print_exc()
            self._json(500, {"ok": False, "error": "внутренняя ошибка: %s" % ex.__class__.__name__})

    def _static(self, path):
        """Статика панели и атласы иконок (атласы — только с сессией)."""
        if path.startswith("/ref/atlas/") and path.endswith(".png"):
            self._load_session()
            if not self.session:
                raise HttpError(401, "нужно войти")
            p = refdata.atlas_path(path[len("/ref/atlas/"):-4])
            if not p:
                raise HttpError(404, "нет атласа")
            with open(p, "rb") as f:
                return self._send(200, f.read(), "image/png", {"Cache-Control": "private, max-age=86400"})
        if ":" in path or "\\" in path:          # NTFS-потоки (app.js::$DATA) и обратные косые — не отдаём
            raise HttpError(404, "нет файла")
        rel = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
        full = os.path.normpath(os.path.join(config.WEB_DIR, rel))
        if not full.startswith(os.path.normpath(config.WEB_DIR) + os.sep) or not os.path.isfile(full):
            raise HttpError(404, "нет файла")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        # картинки скина меняются только с выкладкой — час из кэша браузера (ревизия: 100 PNG качались каждый раз)
        cache = "public, max-age=3600" if rel.startswith("skin/") else "no-cache"
        with open(full, "rb") as f:
            data = f.read()
        if rel == "index.html":
            # метка версии у стилей и скриптов (время изменения файла): после выкладки браузер берёт свежие, а не
            # старую копию из кэша (16.11: стили обновились, а браузер показывал прежние)
            for name in ("app.css", "app.js", "i18n.js", "shops.js"):
                try:
                    v = int(os.path.getmtime(os.path.join(config.WEB_DIR, name)))
                except OSError:
                    continue
                data = data.replace(('"/%s"' % name).encode(), ('"/%s?v=%d"' % (name, v)).encode())
        self._send(200, data, ctype, {"Cache-Control": cache})


class Server(ThreadingHTTPServer):
    """Многопоточный сервер; потоки-демоны (остановка по Ctrl+C не ждёт зависших клиентов)."""
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._conn_mx = threading.Lock()
        self._conn = {}                                # ip → открытых соединений

    def process_request(self, request, client_address):
        """Предел соединений (всего и с адреса): сверх — сразу закрыть, поток не создаётся (ревизия 16.11 вечер В1)."""
        ip = client_address[0]
        trusted = auth.trusted_ip(ip)
        with self._conn_mx:
            ext = sum(n for k, n in self._conn.items() if not auth.trusted_ip(k))
            over = self._conn.get(ip, 0) >= MAX_CONN_IP or (not trusted and ext >= MAX_CONN)
            if not over:
                self._conn[ip] = self._conn.get(ip, 0) + 1
        if over:
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._conn_release(ip)                     # перепроверка В1-н2: поток не стартовал — счётчик не утекает
            self.shutdown_request(request)
            raise

    def _conn_release(self, ip):
        with self._conn_mx:
            left = self._conn.get(ip, 1) - 1
            if left > 0:
                self._conn[ip] = left
            else:
                self._conn.pop(ip, None)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._conn_release(client_address[0])

    def handle_error(self, request, client_address):
        """Сбои рукопожатия TLS и обрывы клиента — одной строкой с errno (служба видна из сети: сканеры шлют мусор);
        всё прочее — полной трассой."""
        import sys
        ex = sys.exc_info()[1]
        if isinstance(ex, (ssl.SSLError, ConnectionError, TimeoutError)):
            print("%s %s соединение сброшено: %s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), client_address[0],
                                                        ex.__class__.__name__, getattr(ex, "errno", "") or ""))
            return
        super().handle_error(request, client_address)


def tls_context(cfg):
    """Контекст TLS сервера (TLS 1.2+); нет файлов сертификата → None."""
    if not (os.path.isfile(cfg.tls_cert) and os.path.isfile(cfg.tls_key)):
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cfg.tls_cert, cfg.tls_key)
    return ctx


def serve(host=None, port=None):
    """Запустить службу (блокирует)."""
    global _tls_active
    from domains import load_all
    load_all()
    cfg = config.get()
    host, port = host or cfg.bind_host, port or cfg.bind_port
    cfg.bind_host, cfg.bind_port = host, port        # проверка Host сверяет с фактическим адресом (ревизия А0 №12)
    ctx = tls_context(cfg) if cfg.tls else None
    if not cfg.tls and cfg.on_server and host in ("0.0.0.0", ""):
        print("ВНИМАНИЕ: tls=0 при прослушивании всех интерфейсов — пароль пойдёт открытым текстом вне VPN")
    if cfg.tls and ctx is None:
        # на сервере без TLS не стартуем: вне VPN это открытый пароль; батник перезапустит через 10 с
        raise SystemExit("нет сертификата HTTPS (%s) — служба не запущена; выложить заново deploy_admin_center.py"
                         % cfg.tls_cert)
    srv = Server((host, port), Handler)
    if ctx:
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True, do_handshake_on_connect=False)
        _tls_active = True
    def warm():
        """Прогрев в фоне: таблицы сервера, справочники и первый снимок состояния (первое окно свойств предмета
        не ждёт разбора таблиц — владелец 16.11: «панель очень медленная»)."""
        from domains import refdata, srvtables, status
        steps = [lambda n=n: srvtables.table(n) for n in ("Item_Table.txt", "Cellob_Table.txt", "SowelCombine.txt",
                                                            "Function_Table.txt")]
        steps += [srvtables.option_groups, srvtables.option_upgrade, srvtables.item_upgrade_rows,
                  srvtables.over_upgrade_steps, lambda: refdata.item(20551), status.snapshot]
        for f in steps:                              # перепроверка 5 М10: каждый шаг сам по себе
            try:
                f()
            except Exception as ex:                  # прогрев — не условие работы
                print("прогрев: %s: %s" % (ex.__class__.__name__, ex))
    threading.Thread(target=warm, daemon=True, name="warm").start()
    if cfg.on_server:                                # ★ А1 18.11: ежедневные задачи службы (пересчёт рейтинга чести) — core/sched.py
        from core import sched
        sched.start()
    print("%s AsdaAdmin слушает %s://%s:%d/ (на сервере: %s)" % (
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "https" if ctx else "http", host, port, cfg.on_server))
    try:
        srv.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
