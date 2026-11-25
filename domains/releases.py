# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""releases.py — раздел «Выпуски»: состояние выпуска клиента и лаунчера, только чтение (шаг А7.1, 23.11.2026; разбор
Reports/admin_center/research_a7_releases_20261123.md §3 А7.1, решение владельца А7 №6: панель только показывает статус, сам выпуск —
батниками DEPLOY на ПК, из панели не запускается).

ДВЕ ЧАСТИ
  * СНАРУЖИ — то, что служба на сервере видит сама: подписанные указатели на сервере обновлений UPDATE_URL (их же читают лаунчер и игра):
    keys/keyring.json, channels/alpha.json, channels/launcher.json, version.json. Версия, seq, min_version, прошлая версия, манифест,
    срок подписи (expires) с предупреждением «продлить» за WARN_DAYS и «срочно» за URGENT_DAYS. Подпись проверяется как у лаунчера
    (Launcher/src/Updater.cpp, Tools/asda_update_format.envelope_open): корень ROOT_PUB_HEX (вшит в лаунчер, Launcher/src/Config.h) →
    keyring → неотозванные ключи выпуска → конверт. Ed25519 — на чистом Python (RFC 8032, ed25519_verify ниже): на сервере нет
    cryptography / nacl, только pyodbc (разбор §1, dev 23.11). Нет keyring — «подпись не проверена», а не «верна».
  * С ПК — то, чего сервер не видит: releases.log, Build\\EAC\\latest.json, содержимое DEPLOY\\Patch\\Inbox, итоги последних прогонов батников
    (DEPLOY\\Patch\\Logs, DEPLOY\\Build\\Logs — итог «ГОТОВО» / «ОШИБКА» / «ОСТАНОВЛЕНО» пишет DEPLOY\\_tools\\deploy.py), ключи выпуска
    «есть / срок», подписанные на ПК каналы (видно «подписано, но не выгружено»). Собирает консоль ПК (pc_collect, только ПК —
    config.port_code) и пишет в AsdaAdmin adm.ReleasePcStatus логином asda_admin по VPN (push_pc) — тот же путь, каким консоль ПК
    пишет adm.job (asda_admin.py jobs run-due). Запуск: asda_admin.py releases push (вручную или задачей планировщика ПК) или задание
    ПК release.push (операция ниже, исполнитель «pc»). Одинаковый снимок второй раз не пишется: только отметка «ПК присылал».
СЕКРЕТЫ НАРУЖУ НЕ УХОДЯТ. О ключах — только «есть / нет», id открытой части, отозван ли, число резервных копий; закрытые файлы не
  открываются (os.path.isfile). Ключ выгрузки SFTP — только «есть / нет». Любой абсолютный путь в снимке заменяется на имя файла
  (_mask); самотест проверяет, что в снимке нет «X:\\», «.ssh», «.dpapi», «keybackup».
Побочных эффектов при импорте нет.
"""
import base64
import datetime
import hashlib
import importlib.util
import json
import os
import re
import socket
import threading
import time

from core import config, db
from core.ops import Operation, OpRefused, register

UPDATE_URL = "https://@@ASTORY_UPDATE_HOST@@"            # сервер обновлений (Launcher/src/Config.h kUpdateUrl, asda_release.UPLOAD_URL)
# Открытый корневой ключ выпуска — тот же, что вшит в лаунчер (Launcher/src/Config.h) и в игру (AsdaUpdateCheckSubsystem.cpp); самотест
# сверяет с ними и с Releases/keys/root.pub. Скачанному root.pub служба не доверяет: подмену сервера обновлений так не увидеть.
ROOT_PUB_HEX = "@@ASTORY_LAUNCHER_ROOT_PUBKEY@@"
CHANNELS = ("alpha", "launcher")                          # каналы обновлений (DEPLOY\\_tools\\deploy.py GAME_CHANNEL, LAUNCHER_CHANNEL)
SIG_PREFIX = b"ASDA-UPD-v1\0"                             # разделение доменов подписи (asda_update_format.SIG_PREFIX, FORMAT_v1.md)
# Порог предупреждения о сроке подписи. Срок — 90 суток от выпуска или 6_Resign (asda_update_format.EXPIRES_DAYS). Просроченный указатель
# лаунчер не отвергает, а пишет «подписанный указатель просрочен» (Launcher/src/Updater.cpp:107) — защита от заморозки перестаёт работать.
# Продлевает только владелец на своём ПК (ключ под DPAPI) и только сам — ПК бывает недоступен неделю. 14 суток = два выходных и запас на
# 6_Resign + 4_Upload; 3 суток — «срочно».
WARN_DAYS, URGENT_DAYS = 14, 3
PC_STALE_H = 24                                           # снимок ПК старше суток — пометка «данные ПК устарели»
CACHE_S = 300                                             # кэш внешней части (сервер обновлений — чужой хост, не дёргать с каждой вкладки)
FORCE_MIN_S = 30                                          # «обновить сейчас» — не чаще раза в 30 с
FETCH_TIMEOUT_S = 10
MAX_ENVELOPE = 64 * 1024                                  # предел ответа на один указатель: указатели весят < 1 КБ (у лаунчера kMaxEnvelope — 1 МиБ, Updater.cpp:30; ★ р74 К-1)
PC_KEEP = 100                                             # ★ р74 М-4: служба хранит столько последних РАЗНЫХ снимков ПК (adm.ReleasePcPrune, не меньше 100 — предел в процедуре)
RELEASES_ROWS = 30                                        # выпусков из releases.log в снимке
RUNS_RECENT = 20                                          # последних прогонов батников (все виды вместе)
ERR_MAX = 240                                             # длина текста ошибки прогона
TAIL_BYTES = 8192                                         # хвост журнала прогона, в котором ищется итог
PC_FORMAT = "asda-relpc/1"                                # формат снимка ПК
PC_MAX_CHARS = 400000                                     # = CK_adm_ReleasePcStatus_size
NOT_INSTALLED = "таблицы adm.ReleasePcStatus нет (sql/adminc_26_releases.sql не установлен)"

# ── Ed25519, проверка подписи (RFC 8032 §5.1.7, эталонный алгоритм RFC; только проверка — закрытых ключей тут нет) ─────────────
_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _recover_x(y, sign):
    """x по y и знаку (RFC 8032 §5.1.3) → x или None."""
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


def _add(a, b):
    """Сумма точек в расширенных координатах (X, Y, Z, T)."""
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s, pt):
    """s · pt (двоичный метод)."""
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


def _eq(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def ed25519_verify(pub, sig, msg):
    """Подпись Ed25519 верна → True; неверна или мусор → False (как asda_update_format.ed_verify)."""
    if not isinstance(pub, (bytes, bytearray)) or not isinstance(sig, (bytes, bytearray)) or len(pub) != 32 or len(sig) != 64:
        return False
    a = _decompress(bytes(pub))
    r = _decompress(bytes(sig[:32]))
    s = int.from_bytes(sig[32:], "little")
    if a is None or r is None or s >= _L:
        return False
    h = int.from_bytes(hashlib.sha512(bytes(sig[:32]) + bytes(pub) + bytes(msg)).digest(), "little") % _L
    return _eq(_mul(s, _G), _add(r, _mul(h, a)))


def key_id(pub):
    """id ключа: первые 8 байт SHA-256 открытого ключа, hex (asda_update_format.key_id)."""
    return hashlib.sha256(pub).hexdigest()[:16]


def open_envelope(kind, env, trusted):
    """Конверт {payload, sigs} → (нагрузка | None, подпись, текст ошибки). Подпись: "ok" — верна доверенным ключом; "bad" — ни одна подпись
    доверенным ключом не сошлась; "unverified" — доверенных ключей нет (keyring не получен). Нагрузка показывается и при "bad" — с пометкой."""
    if not isinstance(env, dict):
        return None, "bad", "конверт %s: не объект JSON" % kind
    try:
        payload = base64.b64decode(env.get("payload") or "", validate=True)
        obj = json.loads(payload.decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None, "bad", "конверт %s: нагрузка повреждена" % kind
    if not isinstance(obj, dict) or obj.get("format") != "asda-%s/1" % kind:
        return None, "bad", "конверт %s: чужой формат нагрузки" % kind
    if trusted is None:                                 # keyring не получен или не сошёлся: проверять нечем
        return obj, "unverified", ""
    msg = SIG_PREFIX + kind.encode("ascii") + b"\0" + payload
    sigs = env.get("sigs")
    for s in sigs if isinstance(sigs, list) else []:
        if not isinstance(s, dict) or not isinstance(s.get("key"), str) or not isinstance(s.get("sig"), str):
            continue
        pub = trusted.get(s["key"])
        if pub is None:
            continue
        try:
            sig = base64.b64decode(s["sig"], validate=True)
        except ValueError:
            continue
        if ed25519_verify(pub, sig, msg):
            return obj, "ok", ""
    return obj, "bad", "конверт %s: нет действительной подписи доверенным ключом" % kind


def keyring_trusted(ring, include_revoked=False):
    """Нагрузка keyring → {id: pub} ключей выпуска (по умолчанию — только неотозванных, как у клиента)."""
    out = {}
    keys = ring.get("release_keys") if isinstance(ring, dict) else None
    for k in keys if isinstance(keys, list) else []:
        try:
            pub = bytes.fromhex(k["pub"])
        except (KeyError, TypeError, ValueError):
            continue
        if len(pub) == 32 and (include_revoked or not k.get("revoked")) and key_id(pub) == k.get("id"):
            out[k["id"]] = pub
    return out


def _parse_iso(v):
    try:
        t = datetime.datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def expiry(iso, now=None):
    """Срок подписи → (суток осталось | None, уровень: ok | warn | urgent | expired | none | bad)."""
    if not iso:
        return None, "none"
    if not isinstance(iso, str):                     # ★ р74 М-2: срок не строкой — «не разобран», не TypeError
        return None, "bad"
    t = _parse_iso(iso)
    if t is None:
        return None, "bad"
    now = now or datetime.datetime.now(datetime.timezone.utc)
    left = (t - now).total_seconds() / 86400.0
    lvl = "expired" if left < 0 else "urgent" if left < URGENT_DAYS else "warn" if left < WARN_DAYS else "ok"
    return round(left, 1), lvl


def _s(v):
    """★ р74 М-2: строковое поле нагрузки (нагрузка читается и без верной подписи — типы не доверены) → str | None."""
    return v[:200] if isinstance(v, str) else None


def _i(v):
    """★ р74 М-2: целое поле нагрузки (bool — не целое) → int | None."""
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _pointer(kind, name, obj, sig, err, now):
    """Строка таблицы указателей (все поля приведены к типам: str / int / None)."""
    obj = obj if isinstance(obj, dict) else {}
    prev = obj.get("previous") if isinstance(obj.get("previous"), dict) else {}
    man = obj.get("manifest") if isinstance(obj.get("manifest"), dict) else {}
    row = {"name": name, "kind": kind, "channel": _s(obj.get("channel")), "version": _s(obj.get("version")), "seq": _i(obj.get("seq")),
           "min_version": _s(obj.get("min_version")), "created": _s(obj.get("created")), "expires": _s(obj.get("expires")), "sig": sig,
           "error": err, "manifest": (_s(man.get("sha256")) or "")[:16], "manifest_size": _i(man.get("size")),
           "prev_version": _s(prev.get("version")), "prev_seq": _i(prev.get("seq"))}
    return with_expiry(row, now)


def with_expiry(row, now=None):
    """Остаток срока и уровень — досчитывает служба по expires (★ р74 М-4: в снимке ПК их нет, иначе md5 менялся бы каждые 2,4 ч)."""
    left, lvl = expiry(row.get("expires"), now)
    return dict(row, days_left=left, level=lvl)


def resign_hint(name):
    """Как продлить подпись указателя (батник есть только у канала alpha: DEPLOY\\_tools\\deploy.py cmd_patch_resign)."""
    if name in ("alpha", "version.json"):
        return "6_Resign.bat в DEPLOY\\Patch, затем 4_Upload.bat"     # без «\цифра»: в английском шаблоне это ссылка на группу
    return "asda_release.py --channel %s resign, затем upload (батника нет)" % name


def check_pointers(ring_env, envs, now=None, root_hex=ROOT_PUB_HEX):
    """Проверка набора указателей одним кодом для сервера обновлений и для копии на ПК. ring_env — конверт keyring (или None); envs —
    [(вид, имя, конверт | None, ошибка получения)] → dict(keyring, pointers, warnings)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    root = bytes.fromhex(root_hex)
    out = {"keyring": {"seq": None, "sig": "unverified", "error": "", "keys": [], "expires": None}, "pointers": [], "warnings": []}
    trusted = None                                      # None — проверять нечем («не проверена»); {} — ключей нет (все отозваны) — «НЕ сошлась»
    if ring_env is not None:
        ring, sig, err = open_envelope("keyring", ring_env, {key_id(root): root})
        out["keyring"].update(sig=sig, error=err)
        if ring:
            rk = ring.get("release_keys")
            out["keyring"].update(seq=_i(ring.get("seq")), expires=_s(ring.get("expires")),
                                  keys=[{"id": _s(k.get("id")), "revoked": bool(k.get("revoked"))}
                                        for k in (rk if isinstance(rk, list) else []) if isinstance(k, dict)])
        if ring and sig == "ok":
            trusted = keyring_trusted(ring)
        if sig != "ok":
            out["warnings"].append("keyring: подпись корнем не сошлась — подписи каналов не проверены")
        else:
            left, lvl = expiry(ring.get("expires"), now)
            if lvl in ("warn", "urgent", "expired"):
                out["warnings"].append("keyring: срок подписи %s (осталось %s сут) — нужна ротация ключей на ПК" % (ring.get("expires"), left))
    else:
        out["keyring"]["error"] = "keyring не получен — подписи каналов не проверены"
    for kind, name, env, ferr in envs:
        if env is None:
            out["pointers"].append(_pointer(kind, name, None, "unverified", ferr or "нет данных", now))
            out["warnings"].append("%s: не получен (%s)" % (name, ferr or "нет данных"))
            continue
        obj, sig, err = open_envelope(kind, env, trusted)
        # ★ р74 М-1: канал в нагрузке = имени файла (как лаунчер, Updater.cpp:93: подписанный launcher.json, выложенный как alpha.json, —
        #   подмена); version.json — только канала alpha (его читает игра)
        want = "alpha" if kind == "version" else name
        if obj is not None and obj.get("channel") != want:
            sig, err = "bad", "конверт канала %s выдан за %s" % (_s(obj.get("channel")) or "?", want)
        row = _pointer(kind, name, obj, sig, err, now)
        out["pointers"].append(row)
        if sig == "bad":
            out["warnings"].append("%s: подпись НЕ сошлась (%s)" % (name, err))
        if row["level"] == "expired":
            out["warnings"].append("%s: подпись просрочена с %s — продлить: %s" % (name, row["expires"], resign_hint(name)))
        elif row["level"] == "urgent":
            out["warnings"].append("%s: подпись истекает через %s сут (%s) — срочно продлить: %s" % (name, row["days_left"], row["expires"],
                                                                                                    resign_hint(name)))
        elif row["level"] == "warn":
            out["warnings"].append("%s: подпись истекает через %s сут (%s) — продлить: %s" % (name, row["days_left"], row["expires"],
                                                                                             resign_hint(name)))
    return out


POINTERS = [("channel", ch, "channels/%s.json" % ch) for ch in CHANNELS] + [("version", "version.json", "version.json")]


def _fetch_url(path):
    """GET UPDATE_URL/path → байты (не больше MAX_ENVELOPE). Сбой — RuntimeError с понятной причиной. ★ р74 К-4: перенаправления запрещены
    (указатели лежат по постоянным адресам; https → http или на чужой хост служба не идёт)."""
    import ssl
    import urllib.error
    import urllib.request

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise RuntimeError("перенаправление %d запрещено" % code)
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()), NoRedirect)
    req = urllib.request.Request(UPDATE_URL + "/" + path, headers={"User-Agent": "AstoryAdminCenter/1", "Cache-Control": "no-cache"})
    try:
        with opener.open(req, timeout=FETCH_TIMEOUT_S) as r:
            data = r.read(MAX_ENVELOPE + 1)
    except urllib.error.HTTPError as ex:
        raise RuntimeError("HTTP %d" % ex.code)
    except (urllib.error.URLError, OSError, ssl.SSLError) as ex:
        raise RuntimeError(str(getattr(ex, "reason", ex))[:160] or ex.__class__.__name__)
    if len(data) > MAX_ENVELOPE:
        raise RuntimeError("ответ больше %d КБ" % (MAX_ENVELOPE // 1024))
    return data


def _get_env(fetch, path):
    """(конверт | None, ошибка)."""
    try:
        return json.loads(fetch(path).decode("utf-8")), ""
    except RuntimeError as ex:
        return None, str(ex)
    except (ValueError, UnicodeDecodeError):
        return None, "ответ не JSON"


_lock = threading.Lock()
_fetch_lock = threading.Lock()                       # ★ р74 К-4: один сбор за раз — остальные вкладки ждут его итог, а не идут сами
_cache = {"at": 0.0, "data": None}


def _fresh(force):
    with _lock:
        age = time.time() - _cache["at"]
        if _cache["data"] and (age < CACHE_S and not force or age < FORCE_MIN_S):
            return _cache["data"]
    return None


def outside(force=False, fetch=None, now=None):
    """Внешняя часть: указатели с сервера обновлений (кэш CACHE_S; force — заново, но не чаще FORCE_MIN_S). fetch(path) → байты — подмена
    для самотеста (тогда без кэша). ★ р74 М-2: любой сбой разбора — итог с ошибкой, и он тоже кэшируется (не 500 и не 5 запросов на открытие)."""
    if fetch is None:
        hit = _fresh(force)
        if hit:
            return hit
        with _fetch_lock:
            hit = _fresh(False)                      # пока ждали — другой поток уже собрал
            if hit:
                return hit
            res = _collect_outside(_fetch_url, now)
            with _lock:
                _cache.update(at=time.time(), data=res)
            return res
    return _collect_outside(fetch, now)


def _collect_outside(f, now):
    at = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        ring_env, ring_err = _get_env(f, "keys/keyring.json")
        envs = []
        for kind, name, path in POINTERS:
            env, err = _get_env(f, path)
            envs.append((kind, name, env, err))
        res = check_pointers(ring_env, envs, now)
        if ring_env is None:
            res["keyring"]["error"] = "keyring не получен (%s) — подписи каналов не проверены" % ring_err
            res["warnings"].insert(0, res["keyring"]["error"])
    except Exception as ex:                          # подмена нагрузки неожиданного вида — показать, а не уронить раздел
        why = "ответ сервера обновлений не разобран: %s" % ex.__class__.__name__
        res = {"keyring": {"seq": None, "sig": "unverified", "error": why, "keys": [], "expires": None}, "pointers": [], "warnings": [why]}
    res.update(url=UPDATE_URL, at=at, warn_days=WARN_DAYS, urgent_days=URGENT_DAYS)
    return res


# ── часть ПК: сбор (только ПК) ────────────────────────────────────────────────────────────────────────────────────────────────────────
# ★ р74 М-3: пути в кавычках — целиком до кавычки (пробелы внутри); без кавычек — папки могут содержать пробелы (C:\Users\John Smith\…),
#   последний сегмент — без пробелов; оба вида слэшей (X:\ и X:/); UNC \\сервер\…
_ABS = re.compile(r"\"[A-Za-z]:[\\/][^\"\r\n]*\"|'[A-Za-z]:[\\/][^'\r\n]*'"
                  r"|(?<![A-Za-z])[A-Za-z]:[\\/](?:[^\\/:\r\n\"'<>|*?]*[\\/])*[^\s\\/:\"'<>|*?]*"
                  r"|\\\\[^\s\"'<>|*?]+")
_LOG_RX = re.compile(r"^(?P<kind>[a-z][a-z0-9_.-]*?)_(?P<d>\d{4}-\d{2}-\d{2})_(?P<t>\d{6})\.log$")
_DONE = re.compile(r"\] ГОТОВО за ([\d.]+) мин")
_FAIL = re.compile(r"\] ОШИБКА: (.*)")
_STOP = re.compile(r"\] ОСТАНОВЛЕНО")
_SECRETISH = re.compile(r"(?i)password|passwd|пароль|парол|\.ssh|\.dpapi|keybackup|asdaupd_upload")   # текст ошибки с этим — не отправляется


def _mask(s):
    """Абсолютные пути → имя файла (…\\имя): в снимке ПК не бывает путей (ни к секретам, ни вообще)."""
    if not isinstance(s, str):
        return s
    def one(m):
        t = m.group(0)
        q = t[0] if t[0] in "\"'" else ""
        body = t[1:-1] if q else t
        return q + "…\\" + (re.split(r"[\\/]", body.rstrip("\\/"))[-1] or "") + q
    return _ABS.sub(one, s)


def mask_deep(v):
    if isinstance(v, dict):
        return {k: mask_deep(x) for k, x in v.items()}
    if isinstance(v, list):
        return [mask_deep(x) for x in v]
    return _mask(v)


def pc_paths():
    """Пути ПК (через AstoryClient\\Tools\\asda_paths.py — правило проекта) → dict. На сервере — PortCodeError."""
    import sys
    tools = config.port_code(os.path.join(os.path.dirname(config.HERE), "AstoryClient", "Tools"))   # HERE = AstoryAdminCenter
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import asda_paths as P                    # noqa: E402 — модуль путей проекта без побочных эффектов
    port = P.PORT_DIR
    deploy = os.path.join(port, "AstoryClient", "DEPLOY")
    return {"port": port, "releases": os.path.join(port, "Releases"), "deploy": deploy, "deploy_py": os.path.join(deploy, "_tools", "deploy.py"),
            "inbox": os.path.join(deploy, "Patch", "Inbox"), "logs": {"patch": os.path.join(deploy, "Patch", "Logs"),
                                                                       "build": os.path.join(deploy, "Build", "Logs")},
            "latest": os.path.join(port, "Build", "EAC", "latest.json"),
            "upload_key": os.path.join(os.path.expanduser("~"), ".ssh", "asdaupd_upload")}


def _deploy_mod(path):
    """DEPLOY\\_tools\\deploy.py как модуль под своим именем (импорт без побочных эффектов: только константы и функции) — разбор Inbox тем
    же кодом, что у батников (inbox_items, read_state)."""
    spec = importlib.util.spec_from_file_location("asda_deploy_tools", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_releases_log(text, limit=RELEASES_ROWS):
    """releases.log (asda_release.py: время \\t версия \\t seq= \\t manifest= \\t files= \\t size= \\t new= \\t build=) → новые сверху."""
    rows = []
    for ln in text.splitlines():
        parts = ln.strip().split("\t")
        if len(parts) < 3:
            continue
        r = {"time": parts[0], "version": parts[1]}
        for p in parts[2:]:
            k, _, v = p.partition("=")
            r[k] = v
        b = (r.get("build") or "").rstrip("\\/")
        seg = re.split(r"[\\/]", b) if b else []
        r["build"] = (seg[-2] if len(seg) >= 2 and seg[-1].lower() == "windows" else seg[-1]) if seg else ""
        rows.append({"time": r["time"], "version": r["version"], "seq": _int(r.get("seq")), "manifest": (r.get("manifest") or "")[:16],
                     "files": _int(r.get("files")), "size": _int(r.get("size")), "new": _int(r.get("new")), "build": r["build"]})
    return list(reversed(rows))[:limit]


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def run_result(tail):
    """Хвост журнала прогона → (итог: done | error | stopped | unfinished, минут | None, текст ошибки)."""
    res, mins, err = "unfinished", None, ""
    for ln in tail.splitlines():
        m = _DONE.search(ln)
        if m:
            res, mins, err = "done", float(m.group(1)), ""
            continue
        m = _FAIL.search(ln)
        if m:
            res, err = "error", _mask(m.group(1).strip())[:ERR_MAX]
            if _SECRETISH.search(err):
                err = "(текст ошибки скрыт: в нём упоминаются секреты)"
            continue
        if _STOP.search(ln):
            res = "stopped"
    return res, mins, err


def _tail(path):
    with open(path, "rb") as f:
        f.seek(0, 2)
        n = f.tell()
        f.seek(max(0, n - TAIL_BYTES))
        return f.read().decode("utf-8", "replace")


def collect_runs(log_dirs):
    """Итоги прогонов DEPLOY: последний по каждому виду и RUNS_RECENT последних всего → (по видам, последние)."""
    allr = []
    for area, d in sorted(log_dirs.items()):
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            m = _LOG_RX.match(n)
            if m:
                allr.append((m.group("d") + " " + m.group("t"), area, m.group("kind"), os.path.join(d, n)))
    allr.sort(reverse=True)
    cache = {}

    def row(x):
        if x[3] not in cache:
            try:
                res, mins, err = run_result(_tail(x[3]))
            except OSError as ex:
                res, mins, err = "unread", None, ex.__class__.__name__
            st = x[0]
            cache[x[3]] = {"area": x[1], "kind": x[2], "started": "%s %s:%s:%s" % (st[:10], st[11:13], st[13:15], st[15:17]),
                           "result": res, "minutes": mins, "error": err}
        return cache[x[3]]
    last = {}
    for x in allr:
        last.setdefault((x[1], x[2]), x)
    by_kind = sorted((row(x) for x in last.values()), key=lambda r: (r["area"], r["kind"]))
    return by_kind, [row(x) for x in allr[:RUNS_RECENT]]


def _read_env(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def collect_keys(rel, upload_key):
    """Ключи выпуска: «есть / нет» и срок — без ключей и путей. Закрытые файлы не открываются."""
    priv = os.path.join(rel, "keys", "private")
    out = {"root_id": None, "root_pinned": False, "root_private": False, "keyring_seq": None, "keyring_expires": None, "keyring_sig": "unverified",
           "release_keys": [], "backups": 0, "backup_newest": None, "upload_key": os.path.isfile(upload_key)}   # ★ р74 К-2: пояснение — подпись в web/releases.js
    try:
        with open(os.path.join(rel, "keys", "root.pub"), "rb") as f:
            root = f.read()
    except OSError:
        root = b""
    if len(root) == 32:
        out.update(root_id=key_id(root), root_pinned=root.hex() == ROOT_PUB_HEX,
                   root_private=os.path.isfile(os.path.join(priv, "root-%s.dpapi" % key_id(root))))
        ring_env = _read_env(os.path.join(rel, "keys", "keyring.json"))
        ring, sig, _err = open_envelope("keyring", ring_env, {key_id(root): root}) if ring_env else (None, "bad", "")
        out["keyring_sig"] = sig
        if ring:
            out.update(keyring_seq=ring.get("seq"), keyring_expires=ring.get("expires"))
            for k in ring.get("release_keys") or []:
                if isinstance(k, dict):
                    out["release_keys"].append({"id": k.get("id"), "revoked": bool(k.get("revoked")),
                                                "private": os.path.isfile(os.path.join(priv, "release-%s.dpapi" % k.get("id")))})
    bdir = os.path.join(rel, "keys", "backup")
    try:
        bs = [os.path.getmtime(os.path.join(bdir, n)) for n in os.listdir(bdir) if n.endswith(".keybackup")]
    except OSError:
        bs = []
    out["backups"] = len(bs)
    out["backup_newest"] = time.strftime("%Y-%m-%d", time.localtime(max(bs))) if bs else None
    return out


def collect_inbox(paths):
    """Содержимое Inbox тем же кодом, что у батников (deploy.inbox_items / read_state): имена, вид, размер файла, время; итог обработки."""
    out = {"items": [], "state": None, "error": ""}
    try:
        dm = _deploy_mod(paths["deploy_py"])
        dm.INBOX, dm.INBOX_STATE = paths["inbox"], os.path.join(paths["inbox"], "_state.json")   # те же, что у батников (самотест — своя папка)
        items = dm.inbox_items()
        st = dm.read_state()
    except Exception as ex:                             # Inbox — сведения, не условие снимка
        out["error"] = "Inbox не прочитан: %s" % _mask(str(ex))[:200]
        return out
    for p in items:
        try:
            s = os.stat(p)
        except OSError:
            continue
        isdir = os.path.isdir(p)
        out["items"].append({"name": os.path.basename(p), "type": "папка" if isdir else ("zip" if p.lower().endswith(".zip") else "файл"),
                             "size": None if isdir else s.st_size, "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(s.st_mtime))})
    if st:
        out["state"] = {"config": st.get("config"), "was_eac_ready": bool(st.get("was_eac_ready")), "processed": st.get("processed")}
    return out


def pc_collect(paths=None, now=None):
    """Снимок ПК → dict (без путей и секретов). Только ПК."""
    paths = paths or pc_paths()
    now = now or datetime.datetime.now(datetime.timezone.utc)
    rel = paths["releases"]
    snap = {"format": PC_FORMAT, "host": socket.gethostname()[:64], "collected_utc": now.strftime("%Y-%m-%d %H:%M:%S"), "errors": []}
    try:
        with open(os.path.join(rel, "releases.log"), encoding="utf-8") as f:
            snap["releases"] = parse_releases_log(f.read())
    except OSError as ex:
        snap["releases"] = []
        snap["errors"].append("releases.log не прочитан: %s" % ex.__class__.__name__)
    lt = _read_env(paths["latest"])
    snap["latest_build"] = {k: lt.get(k) for k in ("build", "mode", "written")} if isinstance(lt, dict) else None
    snap["inbox"] = collect_inbox(paths)
    snap["runs_by_kind"], snap["runs_recent"] = collect_runs(paths["logs"])
    snap["keys"] = collect_keys(rel, paths["upload_key"])
    ring_env = _read_env(os.path.join(rel, "keys", "keyring.json"))
    envs = [(kind, name, _read_env(os.path.join(rel, *p.split("/"))), "нет файла") for kind, name, p in POINTERS]
    loc = check_pointers(ring_env, envs, now)
    # ★ р74 М-4: в снимке — только то, что не меняется со временем (без days_left, level, warnings): иначе md5 менялся бы каждые 2,4 ч
    #   и каждая отправка писала новую строку; остаток срока досчитывает служба (pc_status → with_expiry)
    snap["local"] = {"keyring": loc["keyring"], "pointers": [{k: v for k, v in p.items() if k not in VOLATILE} for p in loc["pointers"]]}
    return mask_deep(snap)


VOLATILE = ("days_left", "level")                    # поля указателя, зависящие от «сейчас» — в снимок ПК не входят


def payload_text(snap):
    """Каноничный JSON снимка (ключи по алфавиту) и его md5 — одинаковый снимок даёт тот же md5. collected_utc в md5 не входит."""
    body = {k: v for k, v in snap.items() if k != "collected_utc"}
    text = json.dumps(snap, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text, hashlib.md5(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def leaks(text):
    """Признаки утечки в тексте снимка → [что найдено] (пусто — чисто). Текст — JSON: проверяется и он, и он же с «\\\\» → «\\».
    ★ р74 М-3: и X:/, \\Users\\ и /Users/, имя пользователя Windows и домашняя папка (оба вида слэшей, без учёта регистра)."""
    import getpass
    t = text + "\n" + text.replace("\\\\", "\\")
    bad = []
    for rx, what in ((r"(?<![A-Za-z])[A-Za-z]:[\\/]", "X:\\"), (r"(?i)[\\/]Users[\\/]", "\\Users\\"), (r"\.ssh", ".ssh"), (r"\.dpapi", ".dpapi"),
                     (r"keybackup", "keybackup"), (r"asdaupd_upload", "asdaupd_upload"), (r"(?i)password|passwd|пароль", "password")):
        if re.search(rx, t):
            bad.append(what)
    low = t.lower().replace("/", "\\")
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    home = os.path.expanduser("~")
    if len(user) >= 3 and user.lower() in low:
        bad.append("user")
    if len(home) > 3 and home.lower().replace("/", "\\") in low:
        bad.append("home")
    return bad


def push_pc(by, snap=None, cn_factory=None):
    """Снимок ПК → AsdaAdmin adm.ReleasePcStatus (логин asda_admin). Тот же md5, что у последней строки, — только отметка seen.
    → dict(id, new, md5, chars)."""
    snap = snap if snap is not None else pc_collect()
    text, md5 = payload_text(snap)
    if len(text) > PC_MAX_CHARS:
        raise OpRefused("снимок ПК больше %d знаков (%d) — не записан" % (PC_MAX_CHARS, len(text)))
    bad = leaks(text)
    if bad:
        raise OpRefused("в снимке ПК найдено то, что наружу не отправляется (%s) — не записан" % ", ".join(bad))
    cn = (cn_factory or db.admin)()
    try:
        if not _installed(cn):
            raise OpRefused(NOT_INSTALLED)
        last = db.admin_rows(cn, "SELECT TOP 1 id, payload_md5 FROM adm.ReleasePcStatus ORDER BY id DESC")
        if last and last[0]["payload_md5"] == md5:
            db.admin_rows(cn, "UPDATE adm.ReleasePcStatus SET seen_utc = SYSUTCDATETIME(), seen_count = seen_count + 1 WHERE id = ?",
                          (int(last[0]["id"]),))
            return {"id": int(last[0]["id"]), "new": False, "md5": md5, "chars": len(text)}
        r = db.admin_rows(cn, "SET NOCOUNT ON; INSERT adm.ReleasePcStatus (payload, payload_md5, host, pushed_by, collected_utc) "
                              "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?)",
                          (text, md5, str(snap.get("host") or "")[:64], safe_by(by),
                           datetime.datetime.strptime(snap["collected_utc"], "%Y-%m-%d %H:%M:%S")))
        return {"id": int(r[0]["id"]), "new": True, "md5": md5, "chars": len(text)}
    finally:
        cn.close()


def safe_by(by):
    """★ р74 К-3: кто прислал — без имени пользователя Windows («cli:<пользователь>@<машина>» консоли → «cli@<машина>»; журнал действий
    adm.audit пишет консоль как у всех операций, это не трогается)."""
    return re.sub(r"^cli:[^@]*@", "cli@", str(by or ""))[:32]


def prune(keep=PC_KEEP, cn_factory=None):
    """★ р74 М-4: оставить keep последних снимков ПК (adm.ReleasePcPrune; процедура не опускает предел ниже 100) → удалено строк. Зовёт только
    служба (операция release.prune раз в сутки, core/sched DAILY); у asda_admin прямого DELETE нет."""
    cn = (cn_factory or db.admin)()
    try:
        if not _installed(cn):
            raise OpRefused(NOT_INSTALLED)
        r = db.admin_rows(cn, "SET NOCOUNT ON; DECLARE @n INT; EXEC adm.ReleasePcPrune @Keep = ?, @Deleted = @n OUTPUT; SELECT @n AS n", (int(keep),))
        return int(r[0]["n"] or 0) if r else 0
    finally:
        cn.close()


def _installed(cn):
    return bool(db.admin_rows(cn, "SELECT 1 AS ok WHERE OBJECT_ID(N'adm.ReleasePcStatus', N'U') IS NOT NULL"))


# ── часть ПК: чтение службой ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def pc_status(cn_factory=None):
    """Последний снимок ПК → dict(installed, have, pushed_utc, seen_utc, age_h, stale, host, by, snap, error)."""
    out = {"installed": True, "have": False, "stale": True, "age_h": None, "error": "", "snap": None, "history": []}
    try:
        cn = (cn_factory or db.admin)()
    except db.DbError as ex:
        return dict(out, error="снимок ПК не прочитан: %s" % ex)
    try:
        if not _installed(cn):
            return dict(out, installed=False, error=NOT_INSTALLED)
        r = db.admin_rows(cn, "SELECT TOP 1 id, payload, host, pushed_by, collected_utc, pushed_utc, seen_utc, seen_count, "
                              "DATEDIFF(minute, seen_utc, SYSUTCDATETIME()) AS age_min FROM adm.ReleasePcStatus ORDER BY id DESC")
        hist = db.admin_rows(cn, "SELECT TOP 10 id, pushed_utc, seen_utc, seen_count, host FROM adm.ReleasePcStatus ORDER BY id DESC")
    except db.DbError as ex:
        return dict(out, error="снимок ПК не прочитан: %s" % ex)
    finally:
        cn.close()
    out["history"] = [{"id": h["id"], "pushed_utc": _ts(h["pushed_utc"]), "seen_utc": _ts(h["seen_utc"]), "seen_count": h["seen_count"],
                       "host": h["host"]} for h in hist]
    if not r:
        return out
    x = r[0]
    try:
        snap = json.loads(x["payload"])
    except ValueError:
        return dict(out, error="снимок ПК №%s повреждён (не JSON)" % x["id"])
    age = float(x["age_min"] or 0) / 60.0
    loc = snap.get("local") if isinstance(snap, dict) else None
    if isinstance(loc, dict) and isinstance(loc.get("pointers"), list):     # ★ р74 М-4: остаток срока — по часам службы
        loc["pointers"] = [with_expiry(p) for p in loc["pointers"] if isinstance(p, dict)]
    out.update(have=True, id=x["id"], host=x["host"], collected_utc=_ts(x["collected_utc"]), pushed_utc=_ts(x["pushed_utc"]),
               seen_utc=_ts(x["seen_utc"]), seen_count=x["seen_count"], age_h=round(age, 1), stale=age > PC_STALE_H, snap=snap)
    return out                                       # ★ р74 К-3: кто прислал (pushed_by) наружу не отдаётся


def _ts(v):
    return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime.datetime) else (str(v) if v is not None else None)


PATCH_KINDS = ("patch-all", "patch-process", "patch-make", "patch-verify", "patch-upload", "patch-resign", "launcher-release")


def pc_warnings(pc, out):
    """Предупреждения по снимку ПК и его сверке со снаружи → [текст]."""
    w = []
    if not pc.get("installed"):
        return [pc.get("error") or NOT_INSTALLED]
    if pc.get("error"):
        return [pc["error"]]
    if not pc.get("have"):
        return ["ПК ещё не присылал данные (asda_admin.py releases push на ПК владельца)"]
    if pc.get("stale"):
        w.append("данные ПК старше %d ч (последний раз ПК присылал %s UTC) — ПК выключен или отправка не запускалась" % (PC_STALE_H, pc["seen_utc"]))
    s = pc.get("snap") or {}
    for r in s.get("runs_by_kind") or []:
        if r.get("kind") in PATCH_KINDS and r.get("result") in ("error", "stopped"):
            w.append(("последний прогон %s (%s) закончился ошибкой" if r["result"] == "error" else "последний прогон %s (%s) остановлен вручную")
                     % (r["kind"], r["started"]))
    k = s.get("keys") or {}
    if k and not k.get("root_pinned"):
        w.append("корневой ключ на ПК не совпадает с вшитым в лаунчер")
    if k and not any(x.get("private") and not x.get("revoked") for x in k.get("release_keys") or []):
        w.append("на ПК нет закрытой части действующего ключа выпуска — подписать выпуск или 6_Resign нельзя")
    if k and not k.get("backups"):
        w.append("резервных копий ключей выпуска нет (DEPLOY\\Patch\\Keys_Backup.bat)")
    if k and not k.get("upload_key"):
        w.append("на ПК нет ключа выгрузки на сервер обновлений — 4_Upload не пройдёт")
    if (s.get("inbox") or {}).get("items"):
        w.append("в Inbox лежит клиент (%d) — следующий 0_Patch_All возьмёт его" % len(s["inbox"]["items"]))
    # ★ р74 М-1: откат keyring на сервере обновлений (старый keyring, подписанный корнем, — без позднего отзыва ключа)
    rs, ls = _i(((out or {}).get("keyring") or {}).get("seq")), _i(k.get("keyring_seq")) if k else None
    if rs is not None and ls is not None and rs < ls:
        w.append("keyring на сервере обновлений seq %d ниже, чем на ПК (%d) — откат keyring или не выгружено" % (rs, ls))
    remote = {p.get("name"): p for p in (out or {}).get("pointers") or [] if isinstance(p, dict)}
    loc = (s.get("local") or {}).get("pointers")
    for p in loc if isinstance(loc, list) else []:
        rp = remote.get(p.get("name")) if isinstance(p, dict) else None
        # ★ р74 М-2: сравниваются только целые seq и строковые сроки (подменённая нагрузка не роняет раздел)
        if not rp or _i(rp.get("seq")) is None or _i(p.get("seq")) is None:
            continue
        if p["seq"] > rp["seq"] or (p["seq"] == rp["seq"] and (_s(p.get("expires")) or "") > (_s(rp.get("expires")) or "")):
            w.append("%s: на ПК подписано новее (seq %s, срок %s), чем на сервере обновлений (seq %s, срок %s) — не выгружено (4_Upload)"
                     % (p["name"], p["seq"], p.get("expires"), rp["seq"], rp.get("expires")))
    return w


def view(force=False, fetch=None, cn_factory=None):
    """Раздел «Выпуски» целиком: снаружи + ПК + предупреждения."""
    out = outside(force=force, fetch=fetch)
    pc = pc_status(cn_factory)
    return {"outside": out, "pc": pc, "warnings": list(out.get("warnings") or []) + pc_warnings(pc, out), "pc_stale_h": PC_STALE_H}


@register
class ReleasePush(Operation):
    """★ А7.1: задание ПК — прислать службе снимок конвейера выпуска (releases.log, Inbox, итоги батников, ключи «есть / срок»). Исполняет
    консоль ПК (asda_admin.py jobs run-due / watch; задание ставится в «Задания» панели). Пишет только AsdaAdmin adm.ReleasePcStatus."""
    name, title = "release.push", "Выпуски: прислать снимок ПК"
    perm, reversible, schedule_runner = "releases.push", False, "pc"

    def schedule_check(self, ctx, p):
        return None

    def preview(self, ctx, p):
        if config.get().on_server:
            raise OpRefused("снимок конвейера выпуска собирает только ПК владельца (DEPLOY, Releases и ключи — там) — поставьте задание ПК")
        snap = pc_collect()
        text, md5 = payload_text(snap)
        return {"text": "снимок ПК: выпусков %d, прогонов %d, в Inbox %d, %d знаков, md5 %s" % (
            len(snap.get("releases") or []), len(snap.get("runs_by_kind") or []), len((snap.get("inbox") or {}).get("items") or []), len(text), md5),
            "warnings": leaks(text), "snap": snap}

    def apply(self, ctx, p, prev):
        r = push_pc(ctx.login, prev.get("snap"))
        return {"after": {"id": r["id"], "new": r["new"], "md5": r["md5"]},
                "message": ("снимок ПК записан: №%d (%d знаков)" % (r["id"], r["chars"])) if r["new"]
                else "снимок ПК не изменился: №%d, отмечено «ПК присылал»" % r["id"]}


@register
class ReleasePrune(Operation):
    """★ р74 М-4: служба раз в сутки (core/sched DAILY) оставляет PC_KEEP последних разных снимков ПК (adm.ReleasePcPrune). Новая строка
    появляется только при изменении снимка (прогон батника, Inbox), так что 100 снимков — долгая история; у asda_admin прямого DELETE нет."""
    name, title = "release.prune", "Выпуски: убрать старые снимки ПК"
    perm, reversible, schedule_runner = "releases.push", False, "service"

    def preview(self, ctx, p):
        if not config.get().on_server and ctx.via != "test":
            raise OpRefused("старые снимки ПК убирает служба на сервере (раз в сутки) — с ПК не запускается")
        return {"text": "оставить %d последних снимков ПК" % PC_KEEP, "warnings": []}

    def apply(self, ctx, p, prev):
        n = prune(PC_KEEP)
        return {"after": {"deleted": n, "keep": PC_KEEP}, "message": "старых снимков ПК убрано: %d (оставлено до %d)" % (n, PC_KEEP)}
