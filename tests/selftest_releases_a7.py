# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_releases_a7.py — самотест шага А7.1 «Выпуски: статус» (23.11.2026; domains/releases.py, sql/adminc_26_releases.sql, /api/releases,
web/releases.js, операция release.push, консоль asda_admin.py releases show|push, проверки adminc_10, откат adminc_99).

offline(check)      — права (releases.view — owner, admin; releases.push — owner), операция release.push (исполнитель «pc», без отката, без второго
                      фактора, на сервере — отказ), маршрут; корень ROOT_PUB_HEX = Releases/keys/root.pub = вшитому в лаунчер (Config.h) и в игру
                      (AsdaUpdateCheckSubsystem.cpp); Ed25519 на чистом Python — векторы RFC 8032 и сверка с cryptography (подписи и подмены);
                      проверка указателей на НАСТОЯЩИХ Releases = asda_update_format.envelope_open (второй путь), подмены (нагрузка, чужой
                      корень, отозванный ключ, мусорные подписи), пороги срока 14 / 3 суток и подсказки «продлить»; внешняя часть на подставном
                      сервере (нет keyring, нет канала, не JSON, большой ответ); снимок ПК на своём дереве (releases.log, latest.json, Inbox тем же
                      deploy.py, журналы: ГОТОВО / ОШИБКА / ОСТАНОВЛЕНО / не завершён, ошибка с путём и паролем, ключи — содержимое закрытых файлов
                      и ключа выгрузки в снимок не попадает), настоящий снимок этого ПК без утечек; предупреждения (устарел, ошибка батника, нет
                      копий ключей, не выгружено, Inbox); тексты без «; », переводы EN, веб (без innerHTML, раздел, подписи EN, node --check),
                      adminc_26 (батчи, QUOTED_IDENTIFIER отдельным батчем, уровень 100, права), выкладка (-x -I после adminc_23), adminc_10 / 99,
                      консоль, импорт без побочных эффектов.
sandbox(check, ldb) — СВОЯ база LocalDB: adminc_02 + adminc_26 дважды; до установки — «не установлен»; push_pc: новая строка, тот же снимок —
                      только отметка seen (строк не прибавилось, seen_count 2), изменился — новая строка; pc_status и view() с подставным сервером
                      обновлений; устаревание по seen_utc; release.push через ops.run (журнал adm.audit — запись «ok»), маршрут /api/releases (EN).
live(check)         — живая dev: сервер обновлений (с ПК) — все подписи верны, версии и сроки = второму пути (asda_update_format на тех же байтах);
                      права asda_admin на adm.ReleasePcStatus; release.push с ПК (пишет только AsdaAdmin: строку или отметку) и чтение обратно (md5);
                      служба на сервере (SSH) видит те же указатели и тот же снимок, сбор снимка на сервере — отказ; без входа — 401.
Побочных эффектов при импорте нет.
"""
import ast
import base64
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
RELEASES = os.path.join(PORT, "Releases")
UE_TOOLS = os.path.join(PORT, "AstoryClient", "Tools")
CYR = re.compile("[А-Яа-яЁё]")
UTC = datetime.timezone.utc
# RFC 8032 §7.1, TEST 1 и TEST 2: (открытый ключ, сообщение, подпись)
RFC = [("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
       ("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")]
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика


def _read(*p):
    return open(os.path.join(*p), encoding="utf-8").read()


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


def _route(path):
    from api import server
    for meth, rx, fn, perm, _full in server.ROUTES:
        if meth == "GET" and rx.match(path):
            return fn, perm
    return None, None


def _refused(fn):
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    return None


def _files_fetch(base, override=None):
    """Подставной сервер обновлений: путь → байты файла из base (override: путь → байты | исключение)."""
    def fetch(path):
        if override and path in override:
            v = override[path]
            if isinstance(v, Exception):
                raise v
            return v
        try:
            with open(os.path.join(base, *path.split("/")), "rb") as f:
                return f.read()
        except OSError:
            raise RuntimeError("HTTP 404")
    return fetch


def _env(kind, obj, seed):
    """Подписанный конверт (cryptography — только ПК, для подмен в самотесте)."""
    sys.path.insert(0, UE_TOOLS) if UE_TOOLS not in sys.path else None
    import asda_update_format as F
    return F.envelope_sign(kind, obj, seed)


def _tree(tmp, now):
    """Своё дерево ПК: port/{Releases, DEPLOY, Build/EAC} → paths для releases.pc_collect."""
    import asda_update_format as F
    rel = os.path.join(tmp, "Releases")
    for d in ("keys/private", "keys/backup", "channels"):
        os.makedirs(os.path.join(rel, *d.split("/")))
    root_seed, rel_seed = secrets.token_bytes(32), secrets.token_bytes(32)
    rpub, kpub = F.ed_public_bytes(root_seed), F.ed_public_bytes(rel_seed)
    open(os.path.join(rel, "keys", "root.pub"), "wb").write(rpub)
    ring = {"format": "asda-keyring/1", "seq": 3, "created": now.isoformat(), "release_keys": [{"id": F.key_id(kpub), "pub": kpub.hex(), "revoked": False}]}
    json.dump(F.envelope_sign("keyring", ring, root_seed), open(os.path.join(rel, "keys", "keyring.json"), "w"))
    exp = (now + datetime.timedelta(days=10)).replace(microsecond=0).isoformat()
    for ch, ver, seq in (("alpha", "alpha-9.0.0-12.2026", 80), ("launcher", "launcher-1.0.7-12.2026", 8)):
        json.dump(F.envelope_sign("channel", {"format": "asda-channel/1", "channel": ch, "version": ver, "seq": seq, "min_version": ver,
                                              "expires": exp, "created": now.isoformat(), "manifest": {"sha256": "ab" * 32, "size": 10}}, rel_seed),
                  open(os.path.join(rel, "channels", ch + ".json"), "w"))
    json.dump(F.envelope_sign("version", {"format": "asda-version/1", "channel": "alpha", "version": "alpha-9.0.0-12.2026", "seq": 80,
                                          "min_version": "alpha-9.0.0-12.2026", "expires": exp}, rel_seed), open(os.path.join(rel, "version.json"), "w"))
    # закрытые файлы — с меткой: она не должна попасть в снимок (файлы не открываются)
    open(os.path.join(rel, "keys", "private", "release-%s.dpapi" % F.key_id(kpub)), "wb").write(b"SECRETMARK-release")
    open(os.path.join(rel, "keys", "private", "root-%s.dpapi" % F.key_id(rpub)), "wb").write(b"SECRETMARK-root")
    with open(os.path.join(rel, "releases.log"), "w", encoding="utf-8") as f:
        for i in range(35):
            f.write("2026-12-%02dT10:00:00+00:00\talpha-8.%d.0-12.2026\tseq=%d\tmanifest=%s\tfiles=174\tsize=6077184095\tnew=%d\t"
                    "build=@@ASTORY_DEV_ROOT_ESC@@\\Build\\EAC\\2026-12-%02d_1000\\Windows\n" % (i % 28 + 1, i, 40 + i, "cd" * 32, 1000 + i, i % 28 + 1))
    eac = os.path.join(tmp, "Build", "EAC")
    os.makedirs(eac)
    json.dump({"build": "2026-12-01_1000", "build_dir": "@@ASTORY_DEV_ROOT_ESC@@\\Build\\EAC\\2026-12-01_1000", "game_root": "D:\\x\\Windows",
               "manifest": "D:\\x\\m.json", "mode": "code", "written": "2026-12-01 10:00:00"}, open(os.path.join(eac, "latest.json"), "w"))
    dep = os.path.join(tmp, "DEPLOY")
    inbox = os.path.join(dep, "Patch", "Inbox")
    plog, blog = os.path.join(dep, "Patch", "Logs"), os.path.join(dep, "Build", "Logs")
    for d in (inbox, plog, blog):
        os.makedirs(d)
    open(os.path.join(inbox, "README.md"), "w").write("x")
    open(os.path.join(inbox, "client_9.zip"), "wb").write(b"z" * 1234)
    os.makedirs(os.path.join(inbox, "ClientDir"))
    logs = {
        (plog, "patch-all_2026-12-01_100000.log"): "[10:00:00] === patch-all\n[10:03:00] ГОТОВО за 3.0 мин. Журнал: @@ASTORY_DEV_ROOT_ESC@@\\AstoryClient\\DEPLOY\\Patch\\Logs\\x.log\n",
        (plog, "patch-all_2026-12-02_100000.log"): "[10:00:00] === patch-all\n[10:01:00] ОШИБКА: нет ключа выкладки C:\\Users\\owner\\.ssh\\asdaupd_upload\n",
        (plog, "patch-upload_2026-12-02_110000.log"): "[11:00:00] === patch-upload\n[11:01:00] ОШИБКА: asda_release upload: код 2 в @@ASTORY_DEV_ROOT_ESC@@\\Releases\\x\n",
        (plog, "patch-resign_2026-12-02_120000.log"): "[12:00:00] === patch-resign\n[12:00:05] ОСТАНОВЛЕНО пользователем\n",
        (plog, "keys-backup_2026-12-02_130000.log"): "[13:00:00] === keys-backup\n[13:00:05] ОШИБКА: пароли не совпали\n",
        (blog, "build-release_2026-12-02_090000.log"): "[09:00:00] === build-release\n[09:06:00] строка\n",
        (blog, "build-dev_check_2026-12-01_080000.log"): "[08:00:00] === build-dev\n[08:00:10] ГОТОВО за 0.2 мин. Журнал: D:\\x\n",
        (blog, "_bg_build-dev_console.txt"): "мусор", (blog, "launcher-1.0.6_release_console.log"): "мусор"}
    for (d, n), t in logs.items():
        open(os.path.join(d, n), "w", encoding="utf-8").write(t)
    up = os.path.join(tmp, "upload_key")
    open(up, "wb").write(b"SECRETMARK-upload")
    paths = {"port": tmp, "releases": rel, "deploy": dep, "deploy_py": os.path.join(PORT, "AstoryClient", "DEPLOY", "_tools", "deploy.py"), "inbox": inbox,
             "logs": {"patch": plog, "build": blog}, "latest": os.path.join(eac, "latest.json"), "upload_key": up}
    return paths, rpub


def offline(check):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    if UE_TOOLS not in sys.path:
        sys.path.insert(0, UE_TOOLS)
    from core import auth, config, i18n, ops
    import domains
    domains.load_all()
    from domains import releases as R
    import asda_update_format as F
    roles = ("owner", "admin", "gm", "support")
    check("выпуски: releases.view — owner, admin (gm нет — кухня выпуска, как logs.view); releases.push — owner",
          {r for r in roles if auth.can(r, "releases.view")} == {"owner", "admin"} and {r for r in roles if auth.can(r, "releases.push")} == {"owner"})
    op = ops.REGISTRY.get("release.push")
    check("выпуски: операция release.push — право releases.push, исполнитель «pc» (задание ПК), без отката, без второго фактора",
          op is not None and op.perm == "releases.push" and op.schedule_runner == "pc" and not op.reversible and not ops.needs_two_factor("release.push"))
    fn, perm = _route("/api/releases")
    check("выпуски: маршрут GET /api/releases — право releases.view", fn is not None and perm == "releases.view", perm)
    rp = open(os.path.join(RELEASES, "keys", "root.pub"), "rb").read().hex()
    cfg_h = _read(PORT, "AstoryClient", "Launcher", "src", "Config.h")
    sub = _read(PORT, "AstoryClient", "Source", "AsdaReborn", "Private", "UI", "AsdaUpdateCheckSubsystem.cpp")
    check("выпуски: корень ROOT_PUB_HEX = Releases/keys/root.pub = kRootPubHex лаунчера (Config.h) = игры (AsdaUpdateCheckSubsystem.cpp); "
          "адрес = kUpdateUrl лаунчера", R.ROOT_PUB_HEX == rp and ('kRootPubHex = "%s"' % rp) in cfg_h and rp in sub
          and ('kUpdateUrl = "%s"' % R.UPDATE_URL) in cfg_h and R.SIG_PREFIX == F.SIG_PREFIX)
    # ---- Ed25519
    rfc = [R.ed25519_verify(bytes.fromhex(p), bytes.fromhex(s), bytes.fromhex(m)) for p, m, s in RFC]
    rfc_bad = [R.ed25519_verify(bytes.fromhex(p), bytes.fromhex(s), bytes.fromhex(m) + b"\0") for p, m, s in RFC]
    check("выпуски Ed25519: векторы RFC 8032 TEST 1 и 2 — верны, с изменённым сообщением — нет", all(rfc) and not any(rfc_bad), (rfc, rfc_bad))
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization as S
    agree = 0
    for i in range(40):
        k = Ed25519PrivateKey.generate()
        pub = k.public_key().public_bytes(S.Encoding.Raw, S.PublicFormat.Raw)
        m = secrets.token_bytes(i * 5)
        sg = bytearray(k.sign(m))
        bad = bytearray(sg)
        bad[i % 64] ^= 1 << (i % 8)
        agree += (R.ed25519_verify(pub, bytes(sg), m) is True and F.ed_verify(pub, bytes(sg), m) is True
                  and R.ed25519_verify(pub, bytes(bad), m) == F.ed_verify(pub, bytes(bad), m) is False
                  and R.ed25519_verify(pub, bytes(sg), m + b"x") is False)
    junk = [R.ed25519_verify(b"", b"", b""), R.ed25519_verify(b"\0" * 32, b"\0" * 64, b""), R.ed25519_verify(b"\xff" * 32, b"\xff" * 64, b"a"),
            R.ed25519_verify("x", b"", b"")]
    check("выпуски Ed25519: 40 случайных ключей — чистый Python = cryptography (подпись верна, подмена бита и сообщения — нет); мусор — False без "
          "исключений", agree == 40 and not any(junk), (agree, junk))
    # ---- указатели на настоящих Releases (второй путь — asda_update_format.envelope_open)
    now = datetime.datetime.now(UTC)
    rd = lambda *p: json.load(open(os.path.join(RELEASES, *p), encoding="utf-8"))
    ring_env = rd("keys", "keyring.json")
    envs = [("channel", "alpha", rd("channels", "alpha.json"), ""), ("channel", "launcher", rd("channels", "launcher.json"), ""),
            ("version", "version.json", rd("version.json"), "")]
    res = R.check_pointers(ring_env, envs, now)
    root = bytes.fromhex(rp)
    ring2 = F.envelope_open("keyring", ring_env, {F.key_id(root): root})
    tr2 = F.keyring_trusted(ring2)
    two = [F.envelope_open(k, e, tr2) for k, _n, e, _x in envs]
    check("выпуски: настоящие Releases — keyring и три указателя «подпись верна»; версия, seq, min_version, срок = asda_update_format.envelope_open",
          res["keyring"]["sig"] == "ok" and res["keyring"]["seq"] == ring2["seq"] and all(p["sig"] == "ok" for p in res["pointers"])
          and [(p["version"], p["seq"], p["min_version"], p["expires"]) for p in res["pointers"]]
          == [(o["version"], o["seq"], o.get("min_version"), o.get("expires")) for o in two], res)
    # подмены
    alpha = dict(envs[0][2])
    pl = bytearray(base64.b64decode(alpha["payload"]))
    pl[pl.index(b'"seq":') + 6] = ord("9")
    forged = dict(alpha, payload=base64.b64encode(bytes(pl)).decode())
    r1 = R.check_pointers(ring_env, [("channel", "alpha", forged, "")], now)
    seed = secrets.token_bytes(32)
    r2 = R.check_pointers(_env("keyring", ring2, seed), [envs[0]], now)               # keyring чужим корнем
    rv = dict(ring2, release_keys=[dict(k, revoked=True) for k in ring2["release_keys"]])
    r3 = R.check_pointers(_env("keyring", rv, seed), [envs[0]], now, root_hex=F.ed_public_bytes(seed).hex())   # ключ выпуска отозван
    r4 = R.check_pointers(ring_env, [("channel", "alpha", dict(alpha, sigs=[1, {"key": 5}, {"key": "x", "sig": "@@"}, "z"]), ""),
                                     ("channel", "x", {"payload": "!!"}, ""), ("channel", "y", [], ""),
                                     ("version", "v", {"payload": base64.b64encode(b'{"format":"asda-channel/1"}').decode(), "sigs": []}, "")], now)
    check("выпуски подмены: нагрузка изменена — «НЕ сошлась» (значения показаны с пометкой); чужой корень keyring — каналы «не проверена»; "
          "отозванный ключ — «НЕ сошлась»; мусорные подписи, нагрузка не base64, не объект, чужой формат — «НЕ сошлась» без исключений",
          r1["pointers"][0]["sig"] == "bad" and r1["pointers"][0]["seq"] is not None and any("НЕ сошлась" in w for w in r1["warnings"])
          and r2["keyring"]["sig"] == "bad" and r2["pointers"][0]["sig"] == "unverified" and any("подписи каналов не проверены" in w for w in r2["warnings"])
          and r3["keyring"]["sig"] == "ok" and r3["pointers"][0]["sig"] == "bad"
          and [p["sig"] for p in r4["pointers"]] == ["bad"] * 4, (r1["pointers"][0]["sig"], r2["keyring"], r3["pointers"][0]["sig"], r4["pointers"]))
    # пороги срока
    exp = _read(RELEASES, "channels", "alpha.json") and R.expiry("2027-02-19T17:21:21+00:00", now)
    at = lambda d: datetime.datetime(2027, 2, 19, 17, 21, 21, tzinfo=UTC) - datetime.timedelta(days=d)
    lv = [R.expiry("2027-02-19T17:21:21+00:00", at(d))[1] for d in (20, 14.01, 13.9, 3.01, 2.9, 0.01, -0.5)] + [R.expiry(None)[1], R.expiry("мусор")[1]]
    check("выпуски срок: 20 / 14,01 — ok, 13,9 — warn, 3,01 — warn, 2,9 — urgent, 0,01 — urgent, после — expired; нет срока — none, мусор — bad "
          "(пороги WARN_DAYS 14, URGENT_DAYS 3)", lv == ["ok", "ok", "warn", "warn", "urgent", "urgent", "expired", "none", "bad"]
          and (R.WARN_DAYS, R.URGENT_DAYS) == (14, 3) and exp[1] in ("ok", "warn", "urgent", "expired"), lv)
    ws = []
    for d, word in ((10, "— продлить:"), (2, "— срочно продлить:"), (-1, "просрочена")):
        r = R.check_pointers(ring_env, envs, at(d) if d >= 0 else at(0) + datetime.timedelta(days=1))
        ws += r["warnings"]
        al = [w for w in r["warnings"] if w.startswith("alpha:")]
        la = [w for w in r["warnings"] if w.startswith("launcher:")]
        check("выпуски срок: за %s сут до срока alpha — «%s 6_Resign.bat в DEPLOY\\Patch, затем 4_Upload.bat», у launcher — своя подсказка (батника нет)" % (d, word),
              al and word in al[0] and "6_Resign.bat в DEPLOY\\Patch, затем 4_Upload.bat" in al[0] and (d > 0 and d < 10 or not la or "--channel launcher resign" in la[0])
              and any("version.json" in w for w in r["warnings"]), r["warnings"])
    # ---- внешняя часть на подставном сервере
    o1 = R.outside(fetch=_files_fetch(RELEASES), now=now)
    o2 = R.outside(fetch=_files_fetch(RELEASES, {"keys/keyring.json": RuntimeError("HTTP 404"), "channels/launcher.json": b"<html>",
                                                 "version.json": RuntimeError("ответ больше 64 КБ")}), now=now)
    check("выпуски снаружи (подставной сервер): всё есть — подписи верны, предупреждений нет; без keyring — «не получен (HTTP 404) — подписи каналов не "
          "проверены», канал не JSON и большой ответ — «не получен (…)», значения alpha показаны «не проверена»",
          all(p["sig"] == "ok" for p in o1["pointers"]) and not [w for w in o1["warnings"] if "подпись" in w and "истекает" not in w]
          and o2["keyring"]["sig"] == "unverified" and "HTTP 404" in o2["warnings"][0]
          and o2["pointers"][0]["sig"] == "unverified" and o2["pointers"][0]["version"]
          and any("launcher: не получен (ответ не JSON)" == w for w in o2["warnings"])
          and any("version.json: не получен (ответ больше 64 КБ)" == w for w in o2["warnings"]), (o1["warnings"], o2["warnings"]))
    ws += o2["warnings"]
    # ---- снимок ПК на своём дереве
    tmp = tempfile.mkdtemp(prefix="asda_rel_")
    try:
        nowt = datetime.datetime(2026, 12, 3, 12, 0, 0, tzinfo=UTC)
        paths, _rpub = _tree(tmp, nowt)
        snap = R.pc_collect(paths, nowt)
        text, md5 = R.payload_text(snap)
        kinds = {(r["area"], r["kind"]): r for r in snap["runs_by_kind"]}
        check("выпуски снимок ПК (своё дерево): releases.log — 30 новых сверху, сборка — имя папки; latest.json — без путей; Inbox тем же deploy.py "
              "(README не клиент; zip с размером, папка без размера)",
              len(snap["releases"]) == 30 and snap["releases"][0]["seq"] == 74 and snap["releases"][0]["build"] == "2026-12-07_1000"
              and snap["latest_build"] == {"build": "2026-12-01_1000", "mode": "code", "written": "2026-12-01 10:00:00"}
              and sorted((x["name"], x["type"], x["size"]) for x in snap["inbox"]["items"]) == [("ClientDir", "папка", None), ("client_9.zip", "zip", 1234)],
              (snap["releases"][:1], snap["latest_build"], snap["inbox"]))
        check("выпуски снимок ПК: итоги прогонов — последний patch-all ОШИБКА (путь к .ssh скрыт целиком), patch-upload ОШИБКА с путём → имя файла, "
              "patch-resign — остановлен, build-release — не завершён, build-dev_check — ГОТОВО 0,2 мин, keys-backup с паролем — текст скрыт; "
              "файлы не по образцу имени пропущены",
              kinds[("patch", "patch-all")]["result"] == "error" and kinds[("patch", "patch-all")]["error"] == "(текст ошибки скрыт: в нём упоминаются секреты)"
              and kinds[("patch", "patch-upload")]["error"] == "asda_release upload: код 2 в …\\x"
              and kinds[("patch", "patch-resign")]["result"] == "stopped" and kinds[("build", "build-release")]["result"] == "unfinished"
              and kinds[("build", "build-dev_check")]["result"] == "done" and kinds[("build", "build-dev_check")]["minutes"] == 0.2
              and kinds[("patch", "keys-backup")]["error"].startswith("(текст ошибки скрыт") and len(snap["runs_by_kind"]) == 6
              and snap["runs_recent"][0]["kind"] == "keys-backup", snap["runs_by_kind"])
        k = snap["keys"]
        check("выпуски снимок ПК: ключи — корень (не вшитый в лаунчер — отметка), закрытые части «есть», keyring seq 3 подпись верна, копий 0, ключ "
              "выгрузки «есть»; содержимое закрытых файлов и ключа выгрузки в снимок не попало, утечек нет (leaks пуст); подписанное на ПК сверяется с вшитым "
              "корнем — у чужого корня «не проверена»",
              k["root_pinned"] is False and k["root_private"] and k["keyring_seq"] == 3 and k["keyring_sig"] == "ok" and k["backups"] == 0
              and k["upload_key"] is True and all(x["private"] for x in k["release_keys"]) and "SECRETMARK" not in text and R.leaks(text) == []
              and snap["local"]["keyring"]["sig"] == "bad" and all(x["sig"] == "unverified" for x in snap["local"]["pointers"]), (k, R.leaks(text)))
        t2, md52 = R.payload_text(dict(snap, collected_utc="2030-01-01 00:00:00"))
        check("выпуски снимок ПК: md5 не зависит от времени сбора (одинаковый снимок — та же отметка), текст — каноничный JSON", md52 == md5 and t2 != text)
        lk = [R.leaks(x) for x in ('{"a":"D:\\\\Astory"}', '{"a":".ssh"}', '{"a":"x.dpapi"}', '{"a":"k.keybackup"}', '{"a":"asdaupd_upload"}',
                                    '{"a":"Password=1"}', '{"a":"пароль"}')]
        why = [_refused(lambda: R.push_pc("t", dict(snap, extra="D:\\x\\y"), cn_factory=lambda: 1 / 0)),
               _refused(lambda: R.push_pc("t", dict(snap, extra="x" * R.PC_MAX_CHARS), cn_factory=lambda: 1 / 0))]
        check("выпуски: leaks ловит путь, .ssh, .dpapi, keybackup, ключ выгрузки, пароль; push_pc с утечкой или больше предела — отказ ДО базы",
              all(lk) and all(why) and "X:\\" in why[0] and "больше" in why[1], (lk, why))
        ws += why
        # предупреждения
        remote = R.check_pointers(ring_env, envs, nowt)
        pc = {"installed": True, "have": True, "stale": True, "seen_utc": "2026-12-01 10:00:00", "snap": snap}
        pw = R.pc_warnings(pc, remote)
        ws += pw
        check("выпуски предупреждения ПК: устарел (> %d ч), patch-all и patch-upload — ошибкой, patch-resign — остановлен, корень не = лаунчеру, копий ключей "
              "нет, Inbox не пуст, на ПК подписано новее, чем на сервере (alpha, launcher, version.json — не выгружено)" % R.PC_STALE_H,
              any("старше 24 ч" in w for w in pw) and any(w.startswith("последний прогон patch-all") and w.endswith("ошибкой") for w in pw)
              and any(w.startswith("последний прогон patch-upload") for w in pw) and any(w.endswith("остановлен вручную") for w in pw)
              and any("не совпадает с вшитым" in w for w in pw) and any("резервных копий" in w for w in pw)
              and any(w.startswith("в Inbox лежит клиент (2)") for w in pw) and sum("не выгружено (4_Upload)" in w for w in pw) == 3, pw)
        nk = R.pc_warnings({"installed": True, "have": True, "stale": False, "snap": dict(snap, keys=dict(k, upload_key=False, release_keys=[
            dict(x, private=False) for x in k["release_keys"]]))}, None)
        ws += nk + R.pc_warnings({"installed": True, "have": False}, None) + R.pc_warnings({"installed": False, "error": R.NOT_INSTALLED}, None)
        check("выпуски предупреждения ПК: нет закрытой части действующего ключа, нет ключа выгрузки; не присылал — «ещё не присылал»; не установлен — "
              "«adminc_26 не установлен»", any("нет закрытой части" in w for w in nk) and any("ключа выгрузки" in w for w in nk)
              and R.pc_warnings({"installed": True, "have": False}, None)[0].startswith("ПК ещё не присылал")
              and R.pc_warnings({"installed": False, "error": R.NOT_INSTALLED}, None) == [R.NOT_INSTALLED])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    r74_offline(check, R, F, ring_env, envs, now, op, config, ops, i18n)
    # настоящий снимок этого ПК
    real = R.pc_collect()
    rt, _m = R.payload_text(real)
    loc = R.check_pointers(ring_env, envs, now)
    check("выпуски: настоящий снимок этого ПК — без утечек (%d знаков < %d), releases.log прочитан (последний = канал alpha Releases), keyring "
          "ПК подпись верна, корень = вшитому в лаунчер" % (len(rt), R.PC_MAX_CHARS),
          not R.leaks(rt) and len(rt) < R.PC_MAX_CHARS and real["releases"] and real["releases"][0]["version"] == loc["pointers"][0]["version"]
          and real["keys"]["keyring_sig"] == "ok" and real["keys"]["root_pinned"] and not real["errors"], (R.leaks(rt), real.get("errors")))
    # на сервере сбор — отказ
    cfg = config.get()
    was = cfg.on_server
    cfg.on_server = True
    try:
        srv = [_refused(lambda: op.preview(ops.Ctx(1, "o", "owner", "", "web"), {}))]
        try:
            R.pc_paths()
            srv.append(None)
        except config.PortCodeError as ex:
            srv.append(str(ex))
    finally:
        cfg.on_server = was
    check("выпуски: на сервере release.push — отказ «собирает только ПК», pc_paths — PortCodeError (код порта на сервере не исполняется)",
          all(srv) and "только ПК" in srv[0], srv)
    ws += srv[:1]
    texts = ws + [R.NOT_INSTALLED, op.title, R.resign_hint("alpha"), R.resign_hint("launcher"),
                  "снимок ПК не прочитан: AsdaAdmin: x", "снимок ПК №5 повреждён (не JSON)",
                  "снимок ПК: выпусков 30, прогонов 17, в Inbox 0, 11268 знаков, md5 6df727a29306afeae3d485b42cc60658",
                  "снимок ПК записан: №3 (11268 знаков)", "снимок ПК не изменился: №3, отмечено «ПК присылал»",
                  "keyring: срок подписи 2027-01-01T00:00:00+00:00 (осталось 5.0 сут) — нужна ротация ключей на ПК",
                  "конверт channel: не объект JSON", "конверт channel: нагрузка повреждена", "конверт version: чужой формат нагрузки"]
    check("выпуски: тексты отказов и предупреждений без «; »", all("; " not in x for x in texts if x), [x for x in texts if x and "; " in x])
    i18n.set_lang("en")
    try:
        miss = [(x, i18n.tr(x)) for x in texts if x and CYR.search(i18n.tr(x))]
    finally:
        i18n.set_lang("ru")
    check("выпуски EN: предупреждения, отказы, итоги, подсказки «продлить» — без русских слов (%d строк)" % len(texts), not miss, miss[:6])
    sys.path.insert(0, HERE) if HERE not in sys.path else None
    import selftest_patchcfg_a5 as P
    sh, n2 = P.shadowed_translations()
    check("выпуски: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n2, not sh, sh[:5])
    # ---- веб
    js, app, idx, wi = _read(ROOT, "web", "releases.js"), _read(ROOT, "web", "app.js"), _read(ROOT, "web", "index.html"), _read(ROOT, "web", "i18n.js")
    check("выпуски веб: раздел #/releases с правом releases.view, маршрут viewReleases(my), скрипт после attendance.js; без innerHTML, данные — acText, "
          "кнопок запуска батников нет (только «Обновить» — ?force=1)",
          '["#/releases", "Выпуски", "releases.view"' in app and 'case "releases": return viewReleases(my);' in app
          and 0 < idx.index("/attendance.js") < idx.index("/releases.js") and "innerHTML" not in js and "op(" not in js
          and '"/api/releases" + (force ? "?force=1" : "")' in js and "T(x." not in js and "T(p." not in js)
    q = re.compile(r'"((?:[^"\\]|\\.)*)"')
    labels = {x for x in q.findall(js) if CYR.search(x)}
    have = set(re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted(labels - have)
    check("выпуски веб EN: у русских строк раздела есть перевод в web/i18n.js (%d строк)" % len(labels), not lack, lack[:8])
    keys = re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi)
    tail = wi[wi.index("★ А7.1 (23.11): «Выпуски»"):]
    dup = sorted({x for x in re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', tail) if keys.count(x) > 1})
    check("выпуски веб EN: новые ключи web/i18n.js не дублируют прежние", not dup, dup[:8])
    for f in ("releases.js", "app.js", "i18n.js"):
        try:
            r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", f)], capture_output=True, timeout=60)
            check("выпуски: node --check web/%s" % f, r.returncode == 0, r.stderr[-300:])
        except (OSError, subprocess.SubprocessError) as ex:
            check("выпуски: node --check web/%s (node не запустился)" % f, False, str(ex))
    # ---- SQL и выкладка
    sql = _read(ROOT, "sql", "adminc_26_releases.sql")
    bs = _batches(sql)
    body = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    check("выпуски adminc_26: QUOTED_IDENTIFIER ON отдельным батчем до CREATE, уровень 100 (нет TRY_CONVERT, IIF, FORMAT, THROW, STRING_SPLIT, ISJSON), "
          "asda_admin — SELECT, INSERT, UPDATE только seen_utc / seen_count, DENY DELETE",
          bs[0].strip().endswith("SET QUOTED_IDENTIFIER ON;") and "CREATE TABLE" not in bs[0] and "CREATE TABLE adm.ReleasePcStatus" in sql
          and not re.search(r"\b(TRY_CONVERT|TRY_CAST|IIF|FORMAT|THROW|STRING_SPLIT|ISJSON|OPENJSON)\b", body)
          and re.findall(r"GRANT ([\w ,()]+?)\s+ON adm\.ReleasePcStatus TO \[asda_admin\]", body) == ["SELECT, INSERT", "UPDATE (seen_utc, seen_count)"]
          and "DENY  DELETE                         ON adm.ReleasePcStatus TO [asda_admin]" in body)
    dep = _read(ROOT, "deploy", "deploy_admin_center.py")
    check("выпуски: выкладка — adminc_26 с -x -I в AsdaAdmin после adminc_23 и до проверок прав (adminc_10)",
          "Run 'adminc_26_releases.sql' 'AsdaAdmin' -xi" in dep and dep.index("Run 'adminc_23_reports.sql'") < dep.index("Run 'adminc_26_releases.sql'")
          < dep.index("adminc_10_verify.sql') 2>&1"))
    v10, v99 = _read(ROOT, "sql", "adminc_10_verify.sql"), P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    check("выпуски: adminc_10 — SELECT / INSERT / UPDATE seen_utc = 1, UPDATE payload / DELETE = 0; adminc_99 — откат шага (DROP TABLE)",
          "'adm.ReleasePcStatus SELECT'" in v10 and "'adm.ReleasePcStatus UPDATE seen_utc', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ReleasePcStatus','OBJECT','UPDATE','seen_utc','COLUMN'), 1" in v10
          and "'adm.ReleasePcStatus UPDATE payload', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ReleasePcStatus','OBJECT','UPDATE','payload','COLUMN'), 0" in v10
          and "'adm.ReleasePcStatus DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ReleasePcStatus','OBJECT','DELETE'), 0" in v10
          and (v99 is None or "DROP TABLE adm.ReleasePcStatus" in v99))
    cli = _read(ROOT, "asda_admin.py")
    check("выпуски: консоль — releases show | push [--dry] (push — операцией release.push, журнал adm.audit), справка",
          'if cmd == "releases":' in cli and 'ops.run(_cli_ctx(), "release.push", {}, dry="--dry" in args)' in cli and "  releases …" in cli)
    code = _read(ROOT, "domains", "releases.py")
    tree = ast.parse(code)
    top = [type(n).__name__ for n in tree.body]
    check("выпуски: импорт domains/releases без побочных эффектов (верхний уровень — импорты, константы, функции, классы); запросов записи в базу — "
          "только INSERT / UPDATE seen adm.ReleasePcStatus",
          set(top) <= {"Expr", "Import", "ImportFrom", "Assign", "FunctionDef", "ClassDef"}
          and all(isinstance(n.value, ast.Constant) for n in tree.body if isinstance(n, ast.Expr))
          and sorted(set(re.findall(r"\b(INSERT|UPDATE|DELETE)\s+(adm\.\w+)", code))) == [("INSERT", "adm.ReleasePcStatus"), ("UPDATE", "adm.ReleasePcStatus")]
          and "SET seen_utc = SYSUTCDATETIME(), seen_count = seen_count + 1" in code)


def r74_offline(check, R, F, ring_env, envs, now, op, config, ops, i18n):
    """★ ревизия 74 офлайн: М-1 канал в нагрузке и откат keyring, М-2 типы и outside() без исключений с кэшем итога, М-3 маскирование путей
    и leaks(), М-4 md5 снимка не зависит от времени, К-2 без пояснения в снимке, К-4 одна загрузка на промах кэша и запрет перенаправлений."""
    import threading
    import time as _t
    root_seed, rel_seed = secrets.token_bytes(32), secrets.token_bytes(32)
    rpub, kpub = F.ed_public_bytes(root_seed), F.ed_public_bytes(rel_seed)
    rhex = rpub.hex()
    ring = F.envelope_sign("keyring", {"format": "asda-keyring/1", "seq": 2, "release_keys": [{"id": F.key_id(kpub), "pub": kpub.hex(), "revoked": False}]},
                           root_seed)
    exp = (now + datetime.timedelta(days=60)).replace(microsecond=0).isoformat()
    ch = {c: F.envelope_sign("channel", {"format": "asda-channel/1", "channel": c, "version": c + "-1.0.0-12.2026", "seq": 5, "expires": exp,
                                         "manifest": {"sha256": "ab" * 32, "size": 1}}, rel_seed) for c in ("alpha", "launcher")}
    vl = F.envelope_sign("version", {"format": "asda-version/1", "channel": "launcher", "version": "launcher-1.0.0-12.2026", "seq": 5, "expires": exp}, rel_seed)
    ok = R.check_pointers(ring, [("channel", "alpha", ch["alpha"], ""), ("channel", "launcher", ch["launcher"], "")], now, root_hex=rhex)
    sw = R.check_pointers(ring, [("channel", "alpha", ch["launcher"], ""), ("channel", "launcher", ch["alpha"], ""),
                                 ("version", "version.json", vl, "")], now, root_hex=rhex)
    ws = sw["warnings"]
    check("выпуски р74 М-1: верно подписанные каналы, переставленные местами, и version.json не канала alpha — «НЕ сошлась» с текстом «конверт канала … "
          "выдан за …» (как лаунчер, Updater.cpp:93); на своих местах — «подпись верна»",
          [p["sig"] for p in ok["pointers"]] == ["ok", "ok"] and [p["sig"] for p in sw["pointers"]] == ["bad", "bad", "bad"]
          and sw["pointers"][0]["error"] == "конверт канала launcher выдан за alpha" and sw["pointers"][2]["error"] == "конверт канала launcher выдан за alpha",
          sw["pointers"])
    keys_ok = {"keyring_seq": 3, "root_pinned": True, "backups": 1, "upload_key": True, "release_keys": [{"private": True, "revoked": False}]}
    rb = R.pc_warnings({"installed": True, "have": True, "stale": False, "snap": {"keys": keys_ok}}, {"keyring": {"seq": 1}, "pointers": []})
    same = R.pc_warnings({"installed": True, "have": True, "stale": False, "snap": {"keys": keys_ok}}, {"keyring": {"seq": 3}, "pointers": []})
    ws += rb
    check("выпуски р74 М-1: keyring на сервере обновлений seq ниже, чем на ПК, — предупреждение «откат keyring»; равный — без него",
          rb == ["keyring на сервере обновлений seq 1 ниже, чем на ПК (3) — откат keyring или не выгружено"] and same == [], (rb, same))
    # М-2: три подмены типов
    bad_ring = F.envelope_sign("keyring", {"format": "asda-keyring/1", "seq": "7", "release_keys": "не список"}, root_seed)
    forged = {"payload": base64.b64encode(json.dumps({"format": "asda-channel/1", "channel": "alpha", "seq": "73", "version": 5,
                                                      "manifest": {"sha256": 123, "size": "x"}, "previous": {"seq": [1]},
                                                      "expires": 20270101}).encode()).decode(), "sigs": []}
    errs = []
    try:
        t1 = R.check_pointers(bad_ring, [("channel", "alpha", forged, "")], now, root_hex=rhex)
        t2 = R.pc_warnings({"installed": True, "have": True, "stale": False, "snap": {"keys": {"keyring_seq": "x"}, "local": {"pointers": [
            {"name": "alpha", "seq": "80", "expires": 5}, "мусор", {"name": "launcher", "seq": True}]}}},
            {"keyring": {"seq": "1"}, "pointers": [{"name": "alpha", "seq": 73}, {"name": "launcher", "seq": 7}, 5]})
    except Exception as ex:
        errs.append("%s: %s" % (ex.__class__.__name__, ex))
        t1, t2 = None, None
    check("выпуски р74 М-2: release_keys не список, manifest.sha256 не строка (и прочие поля не того типа), seq строкой при сверке ПК и сервера — "
          "без TypeError: keyring «верна», ключей нет — канал «НЕ сошлась», поля — None / пусто, сверки seq нет",
          not errs and t1["keyring"]["sig"] == "ok" and t1["keyring"]["keys"] == [] and t1["keyring"]["seq"] is None
          and t1["pointers"][0]["sig"] == "bad" and t1["pointers"][0]["manifest"] == "" and t1["pointers"][0]["seq"] is None
          and t1["pointers"][0]["version"] is None and t1["pointers"][0]["level"] == "none" and t1["pointers"][0]["prev_seq"] is None
          and not [w for w in t2 if "не выгружено" in w or "откат keyring" in w], (errs, t1 and t1["pointers"], t2))
    calls = []

    def boom(path):
        calls.append(path)
        raise TypeError("подмена")
    saved = R._fetch_url
    R._cache.update(at=0.0, data=None)
    R._fetch_url = boom
    try:
        o1 = R.outside()
        o2 = R.outside()
    finally:
        R._fetch_url = saved
        R._cache.update(at=0.0, data=None)
    ws += o1["warnings"]
    check("выпуски р74 М-2: неожиданное исключение разбора — итог «ответ сервера обновлений не разобран: TypeError» (не 500), и он кэшируется: "
          "второе открытие раздела не ходит на сервер обновлений",
          o1["warnings"] == ["ответ сервера обновлений не разобран: TypeError"] and o2 is o1 and len(calls) == 1 and o1["pointers"] == [], (o1, calls))
    # К-4: одна загрузка на промах кэша, перенаправления запрещены
    cnt = []

    def slow(path):
        cnt.append(path)
        _t.sleep(0.05)
        return open(os.path.join(RELEASES, *path.split("/")), "rb").read()
    R._cache.update(at=0.0, data=None)
    R._fetch_url = slow
    try:
        th = [threading.Thread(target=R.outside) for _ in range(6)]
        for x in th:
            x.start()
        for x in th:
            x.join(30)
    finally:
        R._fetch_url = saved
        R._cache.update(at=0.0, data=None)
    code = _read(ROOT, "domains", "releases.py")
    check("выпуски р74 К-4: 6 вкладок одновременно при пустом кэше — одна загрузка (4 файла, остальные ждут итог); перенаправления запрещены "
          "(свой HTTPRedirectHandler с отказом)", len(cnt) == 4 and "def redirect_request" in code and "перенаправление %d запрещено" in code, cnt)
    # М-3: маскирование и leaks
    import getpass
    cases = [(r"нет файла C:\Users\John Smith\Documents\x.log код 2", r"нет файла …\x.log код 2"),
             ('запуск "C:\\Program Files\\Epic Games\\UE_5.6\\x.exe" не удался', 'запуск "…\\x.exe" не удался'),
             ("запуск 'D:\\A B\\c d\\y.bat' не удался", "запуск '…\\y.bat' не удался"),
             ("C:/Users/john/x.txt и E:\\q\\r.log", "…\\x.txt и …\\r.log"), (r"\\@@ASTORY_SERVER_HOSTNAME@@\H\x\y.z", r"…\y.z"),
             ("ВЫКЛАДКА ГОТОВА: https://@@ASTORY_UPDATE_HOST@@/x", "ВЫКЛАДКА ГОТОВА: https://@@ASTORY_UPDATE_HOST@@/x")]
    got = [R._mask(a) for a, _b in cases]
    check("выпуски р74 М-3: маскирование — путь с пробелами в имени пользователя, пути в кавычках целиком, X:/, UNC → только имя файла; адрес https "
          "не трогается", got == [b for _a, b in cases], list(zip(got, [b for _a, b in cases])))
    raw = [json.dumps({"e": a}, ensure_ascii=False) for a in (r"C:\Users\John Smith\x", "C:/Users/john/x", r"…\Users\x", "/Users/x",
                                                               "user " + getpass.getuser(), os.path.expanduser("~").replace("\\", "/"))]
    lk = [R.leaks(x) for x in raw]
    check("выпуски р74 М-3: leaks ловит X:\\ и X:/, \\Users\\ и /Users/, имя пользователя Windows и домашнюю папку (оба вида слэшей); маскированные "
          "строки — чисто", all(lk) and not any(R.leaks(json.dumps({"e": g}, ensure_ascii=False)) for g in got), (lk, got))
    # М-4 и К-2: md5 снимка через 4 ч тот же, в снимке нет изменчивых полей и пояснения
    tmp = tempfile.mkdtemp(prefix="asda_rel74_")
    try:
        t0 = datetime.datetime(2026, 12, 3, 12, 0, 0, tzinfo=UTC)
        paths, _rp = _tree(tmp, t0)
        s0, s4 = R.pc_collect(paths, t0), R.pc_collect(paths, t0 + datetime.timedelta(hours=4))
        m0, m4 = R.payload_text(s0)[1], R.payload_text(s4)[1]
        flat = json.dumps(s0, ensure_ascii=False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    check("выпуски р74 М-4: повторный сбор снимка через 4 ч — тот же md5 (в подписанном на ПК нет days_left / level / warnings — досчитывает служба); "
          "К-2: в снимке нет русского пояснения о сроке ключей (оно в web/releases.js через T())",
          m0 == m4 and all("days_left" not in p and "level" not in p for p in s0["local"]["pointers"]) and "warnings" not in s0["local"]
          and "expiry_note" not in s0["keys"] and "бессрочны" not in flat
          and "Ключи выпуска Ed25519 бессрочны. Срок есть только у подписи каналов и keyring." in _read(ROOT, "web", "releases.js"), (m0, m4))
    check("выпуски р74 К-3: кто прислал — «cli@машина» без имени пользователя Windows", R.safe_by("cli:bob@PC1") == "cli@PC1"
          and R.safe_by("tester") == "tester" and R.safe_by(None) == "")
    po = ops.REGISTRY.get("release.prune")
    pref = None
    try:
        po.preview(ops.Ctx(None, "o", "owner", "", "cli"), {})
    except ops.OpRefused as ex:
        pref = str(ex)
    ws += [pref or "", po.title, "оставить 100 последних снимков ПК", "старых снимков ПК убрано: 3 (оставлено до 100)",
           "launcher: не получен (перенаправление 301 запрещено)", "alpha: подпись НЕ сошлась (конверт канала launcher выдан за alpha)"]
    check("выпуски р74 М-4: release.prune с ПК — отказ «убирает служба на сервере»", pref and "служба" in pref, pref)
    check("выпуски р74: новые тексты без «; »", all("; " not in x for x in ws if x), [x for x in ws if x and "; " in x])
    i18n.set_lang("en")
    try:
        miss = [(x, i18n.tr(x)) for x in ws if x and CYR.search(i18n.tr(x))]
    finally:
        i18n.set_lang("ru")
    check("выпуски р74 EN: новые предупреждения и отказы — без русских слов (%d строк)" % len([x for x in ws if x]), not miss, miss[:6])


def r74_sandbox(check, a, R, ops):
    """★ ревизия 74 на своей базе: остаток срока подписанного на ПК досчитывает служба (М-4), предел истории adm.ReleasePcPrune (М-4)."""
    loc = {"keyring": {"seq": 1, "sig": "ok"}, "pointers": [{"name": "alpha", "kind": "channel", "version": "alpha-2.0.0-12.2026", "seq": 90,
                                                             "expires": "2099-01-01T00:00:00+00:00", "sig": "ok"}, "мусор"]}
    R.push_pc("tester", {"format": R.PC_FORMAT, "host": "PC1", "collected_utc": "2026-12-01 10:00:00", "local": loc})
    st = R.pc_status()
    p0 = st["snap"]["local"]["pointers"]
    check("выпуски стенд (р74 М-4): в снимке ПК нет days_left / level — их досчитывает служба по expires при чтении; мусорная строка отброшена",
          len(p0) == 1 and p0[0]["level"] == "ok" and p0[0]["days_left"] > 1000, p0)
    before = a.cursor().execute("SELECT COUNT(*) FROM adm.ReleasePcStatus").fetchone()[0]
    for i in range(105 - before):
        R.push_pc("tester", {"format": R.PC_FORMAT, "host": "PC1", "collected_utc": "2026-12-01 10:00:00", "n": i})
    top = a.cursor().execute("SELECT MAX(id) FROM adm.ReleasePcStatus").fetchone()[0]
    d1 = R.prune(1)
    left = a.cursor().execute("SELECT COUNT(*), MAX(id) FROM adm.ReleasePcStatus").fetchone()
    d2 = R.prune(1000)
    op = ops.REGISTRY["release.prune"]
    rp = ops.run(ops.Ctx(None, "service:daily", "owner", "", "test"), "release.prune", {})
    from core import sched
    check("выпуски стенд (р74 М-4): 105 снимков → adm.ReleasePcPrune(1) оставляет 100 последних (предел ниже 100 не опускается), повтор — 0; "
          "операция release.prune — служба (DAILY 01:10), право releases.push, без отката; удаляет только процедура",
          d1 == 5 and tuple(left) == (100, top) and d2 == 0 and op.schedule_runner == "service" and not op.reversible
          and ("release.prune", __import__("datetime").time(1, 10)) in sched.DAILY and rp["message"].startswith("старых снимков ПК убрано: 0"),
          (d1, tuple(left), top, d2, rp["message"]))


class _Req:
    def __init__(self, q, role):
        self.query = q
        self.session = {"user": {"role": role, "login": "t_" + role, "id": 1}}


def sandbox(check, ldb):
    """Своя база LocalDB: adminc_02 + adminc_26, запись снимка ПК, отметка seen, чтение, маршрут."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    if UE_TOOLS not in sys.path:
        sys.path.insert(0, UE_TOOLS)
    from core import db, i18n, ops
    import domains
    domains.load_all()
    from domains import releases as R
    name = "AsdaRel_" + secrets.token_hex(3)
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s]" % name)
    try:
        a = ldb(name)
        for b in _batches(_read(ROOT, "sql", "adminc_02_schema.sql")):
            a.cursor().execute(b)
        db.set_override("admin", lambda database: ldb(name))
        try:
            st0 = R.pc_status()
            check("выпуски стенд: до adminc_26 — «не установлен» (installed False, текст NOT_INSTALLED), push — отказ тем же текстом",
                  st0["installed"] is False and st0["error"] == R.NOT_INSTALLED
                  and _refused(lambda: R.push_pc("t", {"format": R.PC_FORMAT, "host": "h", "collected_utc": "2026-12-01 10:00:00"})) == R.NOT_INSTALLED)
            for _ in range(2):
                for b in _batches(_read(ROOT, "sql", "adminc_26_releases.sql")):
                    a.cursor().execute(b)
            check("выпуски стенд: настоящий adminc_26 дважды (повтор безопасен, без asda_admin — выдача прав пропущена)",
                  a.cursor().execute("SELECT COUNT(*) FROM sys.tables WHERE name = 'ReleasePcStatus'").fetchone()[0] == 1)
            s1 = {"format": R.PC_FORMAT, "host": "PC1", "collected_utc": "2026-12-01 10:00:00", "releases": [{"version": "alpha-1.0.0-12.2026"}],
                  "runs_by_kind": [], "keys": {"backups": 1, "root_pinned": True, "upload_key": True, "release_keys": [{"private": True, "revoked": False}]}}
            w1 = R.push_pc("cli:bob@PC1", s1)
            w2 = R.push_pc("tester", dict(s1, collected_utc="2026-12-01 11:00:00"))
            n2 = a.cursor().execute("SELECT COUNT(*), MAX(seen_count) FROM adm.ReleasePcStatus").fetchone()
            w3 = R.push_pc("tester", dict(s1, releases=[{"version": "alpha-1.0.1-12.2026"}]))
            n3 = a.cursor().execute("SELECT COUNT(*) FROM adm.ReleasePcStatus").fetchone()[0]
            check("выпуски стенд: первый push — новая строка; тот же снимок (другое время сбора) — строка та же, seen_count 2; снимок изменился — новая строка",
                  w1["new"] and not w2["new"] and w2["id"] == w1["id"] and tuple(n2) == (1, 2) and w3["new"] and w3["id"] > w1["id"] and n3 == 2,
                  (w1, w2, tuple(n2), w3, n3))
            st = R.pc_status()
            pb = [r[0] for r in a.cursor().execute("SELECT pushed_by FROM adm.ReleasePcStatus ORDER BY id").fetchall()]
            check("выпуски стенд: pc_status — последний снимок (версия 1.0.1), свежий (stale False), история 2 строки, хост PC1; кто прислал — "
                  "без имени пользователя Windows («cli@PC1», ★ р74 К-3) и наружу не отдаётся",
                  st["have"] and st["snap"]["releases"][0]["version"] == "alpha-1.0.1-12.2026" and st["stale"] is False and len(st["history"]) == 2
                  and st["host"] == "PC1" and "by" not in st and pb == ["cli@PC1", "tester"], (st, pb))
            a.cursor().execute("UPDATE adm.ReleasePcStatus SET seen_utc = DATEADD(hour, -30, SYSUTCDATETIME())")
            st2 = R.pc_status()
            check("выпуски стенд: ПК не присылал 30 ч — stale True, предупреждение «данные ПК старше 24 ч»",
                  st2["stale"] and st2["age_h"] >= 29 and any("старше 24 ч" in w for w in R.pc_warnings(st2, None)), st2.get("age_h"))
            fake = _files_fetch(RELEASES)
            v = R.view(fetch=fake)
            check("выпуски стенд: view() — снаружи (подставной сервер = Releases, подписи верны) + снимок ПК + общие предупреждения",
                  all(p["sig"] == "ok" for p in v["outside"]["pointers"]) and v["pc"]["have"] and any("старше 24 ч" in w for w in v["warnings"]))
            r74_sandbox(check, a, R, ops)
            # операция release.push через ops.run (журнал) — сбор подменён своим снимком
            saved = R.pc_collect
            R.pc_collect = lambda paths=None, now=None: dict(s1, releases=[{"version": "alpha-1.0.2-12.2026"}])
            try:
                r = ops.run(ops.Ctx(None, "cli:selftest", "owner", "", "cli"), "release.push", {})
                r2 = ops.run(ops.Ctx(None, "cli:selftest", "owner", "", "cli"), "release.push", {})
                gm = _refused(lambda: ops.run(ops.Ctx(5, "g", "gm", "", "web"), "release.push", {}))
                adm = _refused(lambda: ops.run(ops.Ctx(6, "a", "admin", "", "web"), "release.push", {}))
            finally:
                R.pc_collect = saved
            au = a.cursor().execute("SELECT COUNT(*) FROM adm.audit WHERE action = 'release.push' AND result = 'ok'").fetchone()[0]
            check("выпуски стенд: release.push через ops.run — снимок записан, повтор — «не изменился» (строка та же), запись «ok» в adm.audit на каждый "
                  "прогон; admin и gm — отказ «нет права»", r["message"].startswith("снимок ПК записан") and r2["message"].startswith("снимок ПК не изменился")
                  and au == 2 and gm and "нет права" in gm and adm and "нет права" in adm, (r["message"], r2["message"], au, gm, adm))
            from api import server
            fn, _perm = _route("/api/releases")
            R._cache.update(at=0.0, data=None)
            orig = R._fetch_url
            R._fetch_url = lambda path: fake(path)
            try:
                i18n.set_lang("en")
                try:
                    out = fn(_Req({}, "admin"), None)
                finally:
                    i18n.set_lang("ru")
            finally:
                R._fetch_url = orig
                R._cache.update(at=0.0, data=None)
            check("выпуски API (EN): /api/releases для admin — снаружи и снимок ПК, предупреждения по-английски, can: releases.push нет у admin",
                  out["pc"]["have"] and out["outside"]["pointers"] and not [w for w in out["warnings"] if CYR.search(w)]
                  and out["can"]["releases.push"] is False, out["warnings"])
        finally:
            db.set_override("admin", None)
    finally:
        m2 = ldb("master")
        try:
            m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % name)
            m2.cursor().execute("DROP DATABASE [%s]" % name)
        except Exception:
            pass


def _stored(R, snap):
    """Снимок, как он записан (без остатка срока, который служба досчитывает при чтении, ★ р74 М-4) — для сверки md5."""
    loc = snap.get("local") or {}
    return dict(snap, local=dict(loc, pointers=[{k: v for k, v in x.items() if k not in R.VOLATILE} for x in loc.get("pointers") or []]))


def live(check):
    """Живая dev: сервер обновлений с ПК (второй путь — asda_update_format), права asda_admin, push с ПК и чтение, служба на сервере, 401."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    if UE_TOOLS not in sys.path:
        sys.path.insert(0, UE_TOOLS)
    from core import config, db, ops
    import domains
    domains.load_all()
    from domains import releases as R
    import asda_update_format as F
    o = R.outside(force=True, fetch=R._fetch_url)
    raw = {p: R._fetch_url(p) for p in ("keys/keyring.json", "channels/alpha.json", "channels/launcher.json", "version.json")}
    root = bytes.fromhex(R.ROOT_PUB_HEX)
    ring = F.envelope_open("keyring", json.loads(raw["keys/keyring.json"]), {F.key_id(root): root})
    tr = F.keyring_trusted(ring)
    two = [F.envelope_open(k, json.loads(raw[p]), tr) for k, p in (("channel", "channels/alpha.json"), ("channel", "channels/launcher.json"),
                                                                    ("version", "version.json"))]
    check("живое: сервер обновлений — keyring и три указателя «подпись верна»; версия, seq, min_version, срок = asda_update_format на тех же байтах",
          o["keyring"]["sig"] == "ok" and all(p["sig"] == "ok" for p in o["pointers"])
          and [(p["version"], p["seq"], p["min_version"], p["expires"]) for p in o["pointers"]]
          == [(x["version"], x["seq"], x.get("min_version"), x.get("expires")) for x in two], o)
    cn = db.admin()
    try:
        pr = db.admin_rows(cn, "SELECT HAS_PERMS_BY_NAME('adm.ReleasePcStatus','OBJECT','SELECT') AS s, HAS_PERMS_BY_NAME('adm.ReleasePcStatus','OBJECT','INSERT') AS i, "
                               "HAS_PERMS_BY_NAME('adm.ReleasePcStatus','OBJECT','UPDATE','seen_utc','COLUMN') AS u, "
                               "HAS_PERMS_BY_NAME('adm.ReleasePcStatus','OBJECT','UPDATE','payload','COLUMN') AS up, "
                               "HAS_PERMS_BY_NAME('adm.ReleasePcStatus','OBJECT','DELETE') AS d")[0]
    finally:
        cn.close()
    check("живое: права asda_admin на adm.ReleasePcStatus — SELECT, INSERT, UPDATE seen_utc есть; UPDATE payload и DELETE нет",
          (pr["s"], pr["i"], pr["u"], pr["up"], pr["d"]) == (1, 1, 1, 0, 0), pr)
    r = ops.run(ops.Ctx(None, "cli:selftest", "owner", "", "cli"), "release.push", {})
    st = R.pc_status()
    snap = R.pc_collect()
    _t, md5 = R.payload_text(snap)
    check("живое: release.push с ПК (%s) — пишет только AsdaAdmin; чтение обратно: последний снимок = собранному сейчас (md5), свежий" % r["message"],
          st["have"] and not st["stale"] and R.payload_text(_stored(R, st["snap"]))[1] == md5, (r["message"], st.get("error")))
    probe = ("import sys, json\nsys.path.insert(0, '.')\nfrom domains import releases as R\nfrom core import config\n"
             "o = R.outside(force=True)\ns = R.pc_status()\n"
             "try:\n    R.pc_paths()\n    pc = 'нет отказа'\nexcept config.PortCodeError:\n    pc = 'PortCodeError'\n"
             "print('RLPROBE ' + json.dumps({'ring': o['keyring']['sig'], 'ptr': [(p['name'], p['version'], p['seq'], p['sig']) for p in o['pointers']], "
             "'md5': R.payload_text(dict(s['snap'], local=dict(s['snap']['local'], pointers=[{k: v for k, v in x.items() if k not in R.VOLATILE} "
             "for x in s['snap']['local']['pointers']])))[1] if s.get('have') else None, 'pc': pc}, ensure_ascii=True))\n")
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    ssh = exe if os.path.exists(exe) else "ssh"
    try:
        p = subprocess.run([ssh, "-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", config.SSH_HOST,
                            r'cmd /c "cd /d @@ASTORY_SERVER_ROOT@@\AdminCenter && set PYTHONIOENCODING=utf-8 && '
                            r'@@ASTORY_SERVER_PYTHON@@ -"'],
                           input=probe.encode("utf-8"), capture_output=True, timeout=300)
        out = (p.stdout + p.stderr).decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as ex:
        out = "ssh: %s" % ex
    mm = re.search(r"RLPROBE (\{.*\})", out)
    got = json.loads(mm.group(1)) if mm else {}
    check("служба на сервере (SSH): сервер обновлений виден, подписи верны на чистом Python (без cryptography), указатели = ПК; снимок ПК тот же (md5); "
          "сбор снимка на сервере — PortCodeError",
          got.get("ring") == "ok" and [tuple(x) for x in got.get("ptr", [])] == [(p["name"], p["version"], p["seq"], "ok") for p in o["pointers"]]
          and got.get("md5") == md5 and got.get("pc") == "PortCodeError", out[-600:])
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/releases" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/releases без входа — 401", code == 401, code)
