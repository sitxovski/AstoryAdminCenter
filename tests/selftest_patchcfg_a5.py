# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_patchcfg_a5.py — самотест шага А5.5 «patches.ini и конфиги» (21.11.2026; domains/patchcfg_src.py, domains/patchcfg.py,
domains/cs_kinds/patchcfg.py, семьи копий движка наборов domains/shopdata.py, выкладчик deploy_changeset.py).

offline(check)       — каталог по НАСТОЯЩИМ исходникам DLL (Config.cpp, места чтения, пределы, зависимости, реестр INDEX.md); IniTable
                       (UTF-16 с BOM и cp1251, концы строк, пробелы, кавычки, повтор секции); виды patch.set / config.set на подставной
                       стойке (копии AsdaPatch ×3 — Indun своей базой, AddonNPC ×3, LoginPatch, DBPatch, SrvDbPatch ×5, Collection.ini ×3):
                       предел и тип, неизвестные ключ / секция, только просмотр, P127 и панель, зависимости P30 / P25 / L04, сильная
                       правка, охват all / field / indun, паритет Ch2, ключа / секции нет в живом файле, ожидающие наборы, выкладчик
                       (ALLOWED, check_roots, busy_for); состояние (журнал патчей: действует / журнал / выключен / не встал / сам выключился /
                       ждёт рестарта / нет секции / не прочитано, секреты скрыты); конфиги (секреты без содержимого); переводы; веб; консоль.
sandbox(check, ldb)  — набор целиком на песочнице стойки: создать → проверить → утвердить (сильная — второе подтверждение) → НАСТОЯЩИЙ сухой
                       прогон deploy_changeset → выкладка подставным рестартом (файлы UTF-16: изменилась только строка значения) → откат
                       (байт в байт как были); ожидающий набор с той же целью — отказ.
live(check)          — только чтение: ini всех копий и журналы патчей по SSH, режимы, Ch2 = поле, конфиги без секретов; сухая оценка
                       позиции (ничего не записано, набор не создаётся).
Ни рестартов стойки, ни записи в живые ini. Побочных эффектов при импорте нет.
"""
import contextlib
import hashlib
import json
import os
import re
import sys

BS = "\\"
GS3 = ("GameServer", "Indun_GameServer", "Ch2_GameServer")
NPC3 = ("NpcServer", "Indun_NpcServer", "Ch2_NpcServer")
SDB5 = ("RelayServer", "Indun_RelayServer", "Ch2_RelayServer", "ItemRelayServer", "OperationServer")
PINI, DBINI, SDBINI, COLL = "ConfigSet" + BS + "patches.ini", "ConfigSet" + BS + "dbpatch.ini", "ConfigSet" + BS + "srvdbpatch.ini", "ini" + BS + "Collection.ini"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _md5(b):
    return hashlib.md5(b).hexdigest()


def make_ini(dll, version=None, utf16=True, tweak=None):
    """ini как его создаёт DLL (CreateFull/BuildSectionText): комментарии + [секция] + ключ=умолчание, CRLF; MasterEnable=1.
    tweak — {(секция, ключ): строка целиком | None (убрать ключ)}; ключ «!drop» секции — убрать секцию."""
    from domains.cs_kinds import patchcfg as K
    d = K.catalog()["dlls"][dll]
    tweak = tweak or {}
    out = []
    for s in d["sections"]:
        if tweak.get((s["name"], "!drop")):
            continue
        if s.get("comment"):
            out.append(s["comment"].replace("\r\n", "\n").replace("\n", "\r\n"))
        out.append("[%s]\r\n" % s["name"])
        for k in s["keys"]:
            if k.get("comment"):
                out.append(k["comment"].replace("\r\n", "\n").replace("\n", "\r\n"))
            line = "%s=%s\r\n" % (k["key"], k["def"])
            if k["key"] == "Version":
                line = "Version=%s\r\n" % (version if version is not None else d["version"])
            if k["key"] == "MasterEnable":
                line = "MasterEnable=1\r\n"
            t = tweak.get((s["name"], k["key"]), "")
            if t is None:
                continue
            out.append(t + "\r\n" if t else line)
        out.append("\r\n")
    text = "".join(out)
    return (b"\xff\xfe" + text.encode("utf-16-le")) if utf16 else text.encode("cp1251", "replace")


def collection(t1="9000"):
    return ("[COLLECTION_INFO]\r\nCollectionTypeCount = 2\r\n\r\nCollectionTypeAniTime00 = 6000\r\nCollectionTypeAniTime01 = %s\r\n" % t1).encode("ascii")


# живые значения dev 21.11 (patches.ini ×3 8358418B): мост P127 включён и действует, шахта P120 включена
BASE_TW = {("P127_AdminBridge", "PollMs"): "PollMs  =  500 ", ("P120_MineTravel", "Enabled"): "Enabled=1",
           ("P127_AdminBridge", "Enabled"): "Enabled=1", ("P127_AdminBridge", "Mode"): "Mode=1"}


def stack_files(indun_tweak=None, ch2_tweak=None):
    out = {}
    asda = make_ini("AsdaPatch", tweak=dict(BASE_TW))
    for g in GS3:
        tw = dict(BASE_TW)
        if g == "Indun_GameServer" and indun_tweak:
            tw.update(indun_tweak)
        if g == "Ch2_GameServer" and ch2_tweak:
            tw.update(ch2_tweak)
        out[g + BS + PINI] = make_ini("AsdaPatch", tweak=tw) if tw != BASE_TW else asda
    for n in NPC3:
        out[n + BS + PINI] = make_ini("AddonNPC")
        out[n + BS + COLL] = collection()
    out["LoginManager" + BS + PINI] = make_ini("LoginPatch")
    out["DBManager" + BS + DBINI] = make_ini("DBPatch")
    for r in SDB5:
        out[r + BS + SDBINI] = make_ini("SrvDbPatch")
    return out


@contextlib.contextmanager
def fake_stack(files=None, pending=None):
    """Подставная стойка (selftest_shops.synthetic) + ini этого шага + ожидающие наборы (cs_kinds/patchcfg.PENDING_SOURCE)."""
    import selftest_shops as T
    from domains.cs_kinds import patchcfg as K
    saved = K.PENDING_SOURCE
    with T.synthetic() as (raw, md5, cli):
        for rel, b in (files or stack_files()).items():
            raw[rel], md5[rel] = b, _md5(b)
        K.PENDING_SOURCE = pending or (lambda: [])
        try:
            yield raw, md5
        finally:
            K.PENDING_SOURCE = saved


def _ev(items, cs_id=None):
    from domains import shopdata as SD
    e = SD.Eval([{"pos": i + 1, "kind": k, "params": p} for i, (k, p) in enumerate(items)], False)
    e.cs_id = cs_id
    return e.run()


def _errs(ev):
    return [e for r in ev.positions for e in r["errors"]] + list(ev.errors)


def _try_norm(kind, p):
    from domains import shopdata as SD
    try:
        SD.norm(kind, p)
        return None
    except Exception as ex:
        return str(ex)


def _ps(dll="AsdaPatch", section="P127_AdminBridge", key="PollMs", value="1000", scope="all"):
    return {"dll": dll, "section": section, "key": key, "value": value, "scope": scope}


# =====================================================================================================================
def offline(check):
    from domains import patchcfg_src as PS, shopdata as SD, patchcfg as V
    from domains.cs_kinds import patchcfg as K
    if SD.SRV_TOOLS not in sys.path:
        sys.path.insert(0, SD.SRV_TOOLS)
    import deploy_changeset as dc
    cat = K.catalog()
    a = cat["dlls"]["AsdaPatch"]
    sec = {s["name"]: s for s in a["sections"]}
    key = lambda s, k: next(x for x in sec[s]["keys"] if x["key"] == k)
    check("А5.5 каталог по исходникам: 5 DLL = DLL_INI (ini и семьи), AsdaPatch Version = kVersion Config.h, ≥ 90 секций и ≥ 600 ключей, "
          "у каждой DLL секция General с Version и MasterEnable",
          set(cat["dlls"]) == set(K.DLL_INI) and all((cat["dlls"][d]["ini"], cat["dlls"][d]["family"]) == K.DLL_INI[d] for d in K.DLL_INI)
          and a["version"] == int(re.search(r"kVersion\s*=\s*(\d+)", open(os.path.join(PS.PATCHES, "AsdaPatch", "src", "Config.h"),
                                                                          encoding="utf-8-sig").read()).group(1))
          and len(a["sections"]) >= 90 and sum(len(s["keys"]) for s in a["sections"]) >= 600
          and all({"Version", "MasterEnable"} <= {k["key"] for k in cat["dlls"][d]["sections"][0]["keys"]} for d in cat["dlls"]))
    check("А5.5 каталог: места чтения и пределы — P127 PollMs Clamp 100…5000 (int), Enabled — bool, P40 Crystals — str, P25 MaxGrantsPerPass "
          "if 1…100000, P101 Sites маска 0…15, P110 Mode «? 1 : 0» 0…1; у ключа — файл и строка чтения",
          (key("P127_AdminBridge", "PollMs")["lo"], key("P127_AdminBridge", "PollMs")["hi"], key("P127_AdminBridge", "PollMs")["type"]) == (100, 5000, "int")
          and key("P127_AdminBridge", "Enabled")["type"] == "bool" and key("P40_CrystalTeleportGate", "Crystals")["type"] == "str"
          and (key("P25_GmRatingRecalc", "MaxGrantsPerPass")["lo"], key("P25_GmRatingRecalc", "MaxGrantsPerPass")["hi"]) == (1, 100000)
          and (key("P101_CashGift", "Sites")["lo"], key("P101_CashGift", "Sites")["hi"]) == (0, 15)
          and (key("P110_Job4PointPools", "Mode")["lo"], key("P110_Job4PointPools", "Mode")["hi"]) == (0, 1)
          and key("P127_AdminBridge", "PollMs")["reads"][0]["file"].endswith("p127_admin_bridge.cpp"))
    lp = {s["name"]: s for s in cat["dlls"]["LoginPatch"]["sections"]}
    check("А5.5 каталог: зависимости по коду — P127 вызывает P25_RunRecalc / P123_PortalMoveTo, L09 — L04c_* (L04_LoginIdentity); описание "
          "секции из INDEX.md (P40, P120, L09 — строки реестра)",
          "P25_GmRatingRecalc" in sec["P127_AdminBridge"]["needs"] and "P123_GmMapJump" in sec["P127_AdminBridge"]["needs"]
          and "L04_LoginIdentity" in lp["L09_LoginMaintenance"]["needs"]
          and sec["P40_CrystalTeleportGate"]["index"] and sec["P120_MineTravel"]["index"] and lp["L09_LoginMaintenance"]["index"],
          (sec["P127_AdminBridge"]["needs"], lp["L09_LoginMaintenance"]["needs"], len(sec["P40_CrystalTeleportGate"]["index"])))
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(ROOT, "domains", "patchcfg_src.py"), "--help"], capture_output=True, timeout=60)
    r2 = subprocess.run([sys.executable, os.path.join(ROOT, "domains", "patchcfg_src.py"), "--bogus"], capture_output=True, timeout=60)
    check("А5.5 patchcfg_src.py: --help — шапка и код 0 (каталог не пишется), неизвестный ключ — код 1", r.returncode == 0 and b"--write" in r.stdout
          and r2.returncode == 1, (r.returncode, r2.returncode))

    # ---- IniTable
    raw16 = make_ini("AsdaPatch", tweak={("P127_AdminBridge", "PollMs"): "PollMs  =  500 ", ("P12_DefaultServerIp", "Value"): 'Value="1.2.3.4"'})
    t = K.IniTable("x", raw16)
    same = t.data() == raw16
    t.set("p127_adminbridge", "pollms", "1000")
    t.set("P12_DefaultServerIp", "Value", "5.6.7.8")
    new = t.data()
    lines_old, lines_new = raw16[2:].decode("utf-16-le").split("\r\n"), new[2:].decode("utf-16-le").split("\r\n")
    diff = [(o, n) for o, n in zip(lines_old, lines_new) if o != n]
    check("А5.5 IniTable UTF-16 с BOM: без правки — байт в байт; правка без учёта регистра меняет ТОЛЬКО значение (пробелы вокруг «=» и хвост "
          "как были, кавычки сохранены), BOM и CRLF на месте, число строк то же",
          same and new[:2] == b"\xff\xfe" and len(lines_old) == len(lines_new)
          and sorted(diff) == sorted([("PollMs  =  500 ", "PollMs  =  1000 "), ('Value="1.2.3.4"', 'Value="5.6.7.8"')]), diff)
    t1 = K.IniTable("y", b"[A]\r\n; c\r\nk = 1\r\n[a]\r\nk=2\r\n[B]\nz=3\n")
    t2 = K.IniTable("z", "[С]\r\nключ=1\r\n".encode("cp1251"))
    t2.set("С", "ключ", "2")
    check("А5.5 IniTable: первая секция при повторе (как GetPrivateProfileString), число заголовков 2, смешанные концы строк сохраняются; "
          "cp1251 — туда-обратно", t1.find("a", "k")[1:] == ("1", 2) and t1.get("B", "z") == "3" and t2.data() == "[С]\r\nключ=2\r\n".encode("cp1251")
          and K.IniTable("q", b"[A]\nk=1\n").data() == b"[A]\nk=1\n", (t1.find("a", "k"), t2.data()))

    # ---- нормализация и отказы
    bad = {
        "диапазон": _try_norm("patch.set", _ps(value="50")), "не целое": _try_norm("patch.set", _ps(value="1x")),
        "bool 2": _try_norm("patch.set", _ps(key="Enabled", value="2")), "секция": _try_norm("patch.set", _ps(section="P999_Nope")),
        "ключ": _try_norm("patch.set", _ps(key="NoSuchKey")), "Version": _try_norm("patch.set", _ps(section="General", key="Version", value="84")),
        "путь": _try_norm("patch.set", _ps(key="SecretFile", value="x")), "узел": _try_norm("patch.set", _ps(key="NodeName", value="x")),
        "DLL": _try_norm("patch.set", _ps(dll="Evil")), "scope": _try_norm("patch.set", _ps(scope="half")),
        "scope LM": _try_norm("patch.set", _ps(dll="LoginPatch", section="L01_LoginLogMask", key="Enabled", value="0", scope="field")),
        "перевод строки": _try_norm("patch.set", _ps(section="P40_CrystalTeleportGate", key="Crystals", value="46:1\n[General]")),
        "конфиг": _try_norm("config.set", {"file": "ConfigSet" + BS + "ThreadInfo.ini", "section": "MAX_INIT_THREAD", "key": "COUNT", "value": "5"}),
        "адрес P12": _try_norm("patch.set", _ps(section="P12_DefaultServerIp", key="Value", value="1.1.1.1")),
    }
    check("А5.5 позиции: отказы — вне предела Clamp, не целое, bool не 0/1, неизвестные секция и ключ, Version, путь, имя узла, адрес P12, чужая "
          "DLL, scope, scope у одной копии, перевод строки, конфиг вне белого списка",
          all(bad.values()) and "100…5000" in bad["диапазон"] and "неизвестная секция" in bad["секция"] and "неизвестный ключ" in bad["ключ"]
          and "только просмотр" in bad["Version"] and "только просмотр" in bad["путь"], bad)
    check("А5.5 позиции: ключи с «Ip» / «Pass» в имени (MaxPendingPerIp, MaxGrantsPerPass, CheckIp) — не адреса и не секреты",
          not K.is_view_only("MaxPendingPerIp") and not K.is_view_only("MaxGrantsPerPass") and not K.is_view_only("CheckIp")
          and K.is_view_only("CounterFile") and K.is_view_only("ConnectionString") and K.is_secret("ConnectionString") and not K.is_secret("SecretRepeatKick"))

    with fake_stack() as (raw, md5):
        e = _ev([("patch.set", _ps())])
        s = e.summary()
        f = s["server"]["files"]
        check("А5.5 patch.set P127 PollMs 500 → 1000: ×3 GameServer (одна база), строка ini «было → станет», сильная (патч защиты P127 — "
              "второе подтверждение), предупреждение «только при старте процесса»",
              not _errs(e) and len(f) == 1 and sorted(f[0]["gs"]) == sorted(GS3) and f[0]["diff"][0][1:] == ["PollMs  =  500 ", "PollMs  =  1000 "]
              and s["balance_strong"] and any("только при старте процесса" in w for w in e.positions[0]["warnings"]), (_errs(e), f))
        e = _ev([("patch.set", _ps(key="Enabled", value="0"))])
        e2 = _ev([("patch.set", _ps(key="Mode", value="0"))])
        check("А5.5 P127 (мост панели): Enabled=0 и Mode=0 — отказ всегда («панелью не выключается»)",
              any("мост P127 нужен панели" in x for x in _errs(e)) and any("мост P127 нужен панели" in x for x in _errs(e2)), (_errs(e), _errs(e2)))
        e = _ev([("patch.set", _ps(section="P30_MapSlots", key="Enabled", value="0"))])
        e2 = _ev([("patch.set", _ps(section="P30_MapSlots", key="Enabled", value="0")), ("patch.set", _ps(section="P120_MineTravel", key="Enabled", value="0")),
                  ("patch.set", _ps(section="P40_CrystalTeleportGate", key="Enabled", value="0"))])
        check("А5.5 зависимости: P30=0 при включённых P120 / P40 — отказ «от него зависит включённый P120»; P30, P120 и P40 выключаются одним "
              "набором — можно (сильная: выключение патча)",
              any("зависит включённый P120_MineTravel" in x for x in _errs(e)) and not _errs(e2) and e2.summary()["balance_strong"], (_errs(e), _errs(e2)))
        e = _ev([("patch.set", _ps(section="P25_GmRatingRecalc", key="Enabled", value="0"))])
        e2 = _ev([("patch.set", _ps(dll="LoginPatch", section="L04_LoginIdentity", key="CheckSoulMate", value="0"))])
        check("А5.5 зависимости: P25=0 при включённом P127 (rank_recalc) — отказ; L04 CheckSoulMate=0 при включённом L09 — отказ",
              any("P127_AdminBridge" in x for x in _errs(e)) and any("L09_LoginMaintenance" in x for x in _errs(e2)), (_errs(e), _errs(e2)))
        e = _ev([("patch.set", _ps(section="General", key="MasterEnable", value="0"))])
        e2 = _ev([("patch.set", _ps(dll="LoginPatch", section="General", key="MasterEnable", value="0"))])
        b2 = [b for b in e2.summary()["balance"] if b["strong"]]
        check("ревизия 45 С-2: MasterEnable=0 у AsdaPatch — отказ (снимает мост P127, как P127 Enabled=0); у LoginPatch — особая сильная "
              "правка с текстом «режим обслуживания панели перестанет работать» и вторым фактором",
              any("мост P127 нужен панели" in x for x in _errs(e)) and not _errs(e2)
              and any("режим обслуживания панели" in b["what"] for b in b2) and all(b["totp"] for b in b2)
              and any("режим обслуживания панели" in w for w in e2.positions[0]["warnings"]), (_errs(e), _errs(e2), b2[:2]))
        e = _ev([("patch.set", _ps(value="500"))])
        check("А5.5 уже стоит во всех копиях — отказ «менять нечего»", any("менять нечего" in x for x in _errs(e)), _errs(e))
        e = _ev([("patch.set", _ps(scope="field"))])
        e2 = _ev([("patch.set", _ps(scope="indun"))])
        e3 = _ev([("patch.set", _ps(scope="all")), ("patch.set", _ps(scope="indun", value="900"))])
        check("А5.5 охват: field — GameServer + Ch2 (пара вместе), indun — только Indun (своя база), all + indun на один ключ — отказ «уже правит позиция»",
              not _errs(e) and sorted(e.summary()["server"]["files"][0]["gs"]) == ["Ch2_GameServer", "GameServer"]
              and not _errs(e2) and e2.summary()["server"]["files"][0]["gs"] == ["Indun_GameServer"]
              and any("уже правит позиция" in x for x in _errs(e3)), (_errs(e), _errs(e2), _errs(e3)))
        e = _ev([("patch.set", _ps(dll="LoginPatch", section="L01_LoginLogMask", key="Enabled", value="0"))])
        e2 = _ev([("patch.set", _ps(dll="DBPatch", section="P23_TitleRankFeed", key="IntervalSec", value="900"))])
        e3 = _ev([("patch.set", _ps(dll="SrvDbPatch", section="P126_DbReconnect", key="Enabled", value="0"))])
        e4 = _ev([("patch.set", _ps(dll="AddonNPC", section="N21_RespawnFreeTile", key="Radius", value="4"))])
        check("А5.5 прочие DLL: LoginPatch (LoginManager), DBPatch (DBManager, dbpatch.ini), SrvDbPatch (5 копий srvdbpatch.ini), AddonNPC (×3 NpcServer) — "
              "по одной правке, файлы своих копий",
              not any(map(_errs, (e, e2, e3, e4))) and e.summary()["server"]["files"][0]["gs"] == ["LoginManager"]
              and e2.summary()["server"]["files"][0]["gs"] == ["DBManager"] and sorted(e3.summary()["server"]["files"][0]["gs"]) == sorted(SDB5)
              and sorted(e4.summary()["server"]["files"][0]["gs"]) == sorted(NPC3), [_errs(x) for x in (e, e2, e3, e4)])
        man = {r: {} for r in e3.summary()["base"]}
        man2 = {r: {} for r in _ev([("patch.set", _ps())]).summary()["base"]}
        check("А5.5 выкладчик: ALLOWED — ini DLL всех копий и Collection.ini ×3; check_roots: srvdbpatch ×5 и patches.ini ×3 — годно, Ch2 без "
              "поля — СТОП, dbpatch у LoginManager — СТОП; busy_for — LoginManager.exe / RelayServer.exe / DBManager.exe по путям",
              dc.check_roots(man) is None and dc.check_roots(man2) is None
              and dc.check_roots({"Ch2_GameServer" + BS + PINI: 1}) is not None and dc.check_roots({"LoginManager" + BS + DBINI: 1}) is not None
              and all(n + BS + COLL in dc.ALLOWED for n in NPC3) and "LoginManager" + BS + PINI in dc.ALLOWED
              and {"LoginManager\\LoginManager.exe", "RelayServer\\RelayServer.exe", "DBManager\\DBManager.exe"} <= set(
                  dc.busy_for({"LoginManager" + BS + PINI: 1, "RelayServer" + BS + SDBINI: 1, "DBManager" + BS + DBINI: 1})[0]))
        e = _ev([("config.set", {"file": COLL, "section": "COLLECTION_INFO", "key": "CollectionTypeAniTime01", "value": "9500"})])
        e2 = _ev([("config.set", {"file": COLL, "section": "COLLECTION_INFO", "key": "CollectionTypeAniTime05", "value": "9500"})])
        e3 = _ev([("config.set", {"file": COLL, "section": "COLLECTION_INFO", "key": "CollectionTypeCount", "value": "3"})])
        e4 = _ev([("config.set", {"file": COLL, "section": "COLLECTION_INFO", "key": "CollectionTypeAniTime01", "value": "50"})])
        check("А5.5 config.set Collection.ini: AniTime01 9000 → 9500 ×3 NpcServer; AniTime05 (типов 2) — отказ «не читает»; CollectionTypeCount — "
              "не правится; 50 мс — вне 100…65535",
              not _errs(e) and sorted(e.summary()["server"]["files"][0]["gs"]) == sorted(NPC3)
              and any("не читает" in x for x in _errs(e2)) and any("не правится" in x for x in _errs(e3)) and _errs(e4), [_errs(x) for x in (e, e2, e3, e4)])
        e = _ev([("patch.set", _ps(section="P40_CrystalTeleportGate", key="Crystals", value="46:31"))])
        check("А5.5 P40 Crystals: строка, которую P40 не разберёт (карта 31 > 29) — отказ", any("P40" in x for x in _errs(e)), _errs(e))
        e = _ev([("patch.set", _ps())], cs_id=7)
        pend_other = [{"id": 5, "status": "approved", "server_state": "dry_ok", "kind": "patch.set", "params": _ps(value="2000")}]
        pend_same = [{"id": 6, "status": "checked", "server_state": "none", "kind": "patch.set", "params": _ps(value="1000")}]
    with fake_stack(pending=lambda: pend_other) as _x:
        e = _ev([("patch.set", _ps())], cs_id=7)
        g1 = K.apply_guard({"id": 7, "items": [{"pos": 1, "kind": "patch.set", "params": _ps()}]}, "apply")
    with fake_stack(pending=lambda: pend_same) as _x:
        e2 = _ev([("patch.set", _ps())], cs_id=7)
    with fake_stack(pending=lambda: (_ for _ in ()).throw(RuntimeError("нет базы"))) as _x:
        e3 = _ev([("patch.set", _ps())], cs_id=7)
    check("А5.5 ожидающие наборы: та же цель с другим значением — ошибка «уже ждёт в наборе №5» (и apply_guard перед выкладкой); то же значение — "
          "предупреждение; не прочитаны — ошибка (не прочитано ≠ нет)",
          any("набор №5" in x or "наборе №5" in x for x in _errs(e)) and g1 and any("наборе №6" in w for w in e2.warnings) and not _errs(e2)
          and any("не прочитаны" in x for x in _errs(e3)), (_errs(e), g1, e2.warnings[:2], _errs(e3)))
    files = stack_files(indun_tweak={("P127_AdminBridge", "PollMs"): "PollMs=700"})
    with fake_stack(files) as _x:
        e = _ev([("patch.set", _ps())])
        diffs = {tuple(f["gs"]): f["diff"] for f in e.summary()["server"]["files"]}
    check("А5.5 Indun своей базой: у Indun PollMs=700 — правка по его строке (700 → 1000), поле и Ch2 — 500 → 1000; предупреждение «копии расходились»",
          not _errs(e) and diffs.get(("Indun_GameServer",), [[0, 0, 0]])[0][1:] == ["PollMs=700", "PollMs=1000"]
          and any("расходились" in w for w in e.positions[0]["warnings"]), (diffs, _errs(e)))
    files = stack_files(ch2_tweak={("P120_MineTravel", "LogPerMinute"): "LogPerMinute=31"})
    with fake_stack(files) as _x:
        e = _ev([("patch.set", _ps())])
    check("А5.5 паритет Ch2: Ch2 patches.ini ≠ полю — ошибка «сначала stack_parity»", any("stack_parity" in x for x in _errs(e)), _errs(e))
    files = stack_files(indun_tweak={("P127_AdminBridge", "PollMs"): None})
    files2 = stack_files()
    # ★ ревизия 45 С-5: при Version живой DLL ≠ каталогу раньше срабатывает отказ по версии — секцию проверяем при той же Version
    files2["LoginManager" + BS + PINI] = make_ini("LoginPatch", tweak={("L09_LoginMaintenance", "!drop"): True})
    with fake_stack(files) as _x:
        e = _ev([("patch.set", _ps())])
    with fake_stack(files2) as _x:
        e2 = _ev([("patch.set", _ps(dll="LoginPatch", section="L09_LoginMaintenance", key="Enabled", value="1"))])
    check("А5.5 живой файл: ключа нет (у Indun) — отказ «живая DLL его не знает»; секции нет (L09 при LoginPatch v10) — отказ «после выкладки допишет»",
          any("живая DLL его не знает" in x for x in _errs(e)) and any("допишет сама" in x for x in _errs(e2)), (_errs(e), _errs(e2)))
    dup = stack_files()
    dup["LoginManager" + BS + PINI] = make_ini("LoginPatch") + "[L01_LoginLogMask]\r\nEnabled=1\r\n".encode("utf-16-le")
    with fake_stack(dup) as _x:
        e = _ev([("patch.set", _ps(dll="LoginPatch", section="L01_LoginLogMask", key="Enabled", value="0"))])
    check("А5.5 повтор секции в файле — отказ «правка неоднозначна»", any("неоднозначна" in x for x in _errs(e)), _errs(e))
    revision45(check)

    # ---- состояние (подмена чтения стойки)
    log = ("AsdaPatch — старт 2026-11-19 12:28:09, PID 4321\r\nХост   : @@ASTORY_SERVER_HOSTNAME@@\r\n  [OK]       P127_AdminBridge — мост\r\n"
           "  [ВЫКЛ]     P08_FunctionItemUseCheckOff — x\r\n  [MISMATCH] P40_CrystalTeleportGate — x\r\n  [OK]       P110_Job4PointPools — y\r\n"
           "=== итог: применено 2, пропущено 1, ошибок 1 ===\r\n")
    run = V.last_run(log)
    check("А5.5 журнал патчей: последний запуск — старт, PID, итог, отметки [OK] / [ВЫКЛ] / [MISMATCH]",
          run["start"] == "2026-11-19 12:28:09" and run["pid"] == 4321 and run["total"] == [2, 1, 1]
          and run["marks"] == {"P127_AdminBridge": "ok", "P08_FunctionItemUseCheckOff": "off", "P40_CrystalTeleportGate": "bad",
                               "P110_Job4PointPools": "ok"} and V.last_run("нет паспорта") is None, run)
    fs = stack_files()
    raw_tab = {}
    for rel, b in fs.items():
        raw_tab[rel] = b
    p110 = fs["GameServer" + BS + PINI]
    raw_tab["GameServer" + BS + PINI] = make_ini("AsdaPatch", tweak=dict(list(BASE_TW.items()) + [(("P110_Job4PointPools", "Mode"), "Mode=0")]))
    saved = V._read

    def fake_read(ini_rels, log_dirs, stat_rels):
        ini = {r: raw_tab.get(r) for r in ini_rels}
        logs = {d: (None if d == "Indun_GameServer" else log) for d in log_dirs}
        st = {r: (len(raw_tab.get(r) or b""), "2026-11-19 12:00") for r in stat_rels}
        return ini, logs, st
    V._read = fake_read
    try:
        S = V.state(force=True, dll_only="AsdaPatch")
    finally:
        V._read = saved
    d0 = S["dlls"][0]
    ss = {s["name"]: s for s in d0["sections"]}
    check("А5.5 состояние: режимы по журналу — P127 действует, P110 Mode=0 — журнал, P08 в ini включён, а при запуске [ВЫКЛ] — «сам выключился», "
          "P40 [MISMATCH] — не встал, нет в журнале — nolog, Indun журнал не прочитан — «не прочитано»; Ch2 ≠ полю — предупреждение паритета; "
          "секреты (ConnectionString) скрыты",
          ss["P127_AdminBridge"]["modes"]["GameServer"] == "active" and ss["P110_Job4PointPools"]["modes"]["GameServer"] == "journal"
          and ss["P08_FunctionItemUseCheckOff"]["modes"]["GameServer"] == "self_off" and ss["P40_CrystalTeleportGate"]["modes"]["GameServer"] == "failed"
          and ss["P01_RareItemNotice6616"]["modes"]["GameServer"] == "nolog" and ss["P127_AdminBridge"]["modes"]["Indun_GameServer"] == "unread"
          and any("паритет Ch2" in w for w in S["warnings"])
          and all(v in (None, "•••", "") for k in ss["P53_AcJournal"]["keys"] if k["key"] == "ConnectionString" for v in k["values"].values()),
          ({n: ss[n]["modes"] for n in ("P127_AdminBridge", "P110_Job4PointPools", "P08_FunctionItemUseCheckOff")}, S["warnings"][:3]))
    del p110

    def fake_read2(ini_rels, log_dirs, stat_rels):
        ini = {r: b"[COLLECTION_INFO]\r\nCollectionTypeCount=2\r\n" if "Collection" in r else
               (b"[DB]\r\nGAMEPASS=secret\r\n" if "ServerInfo" in r and r.startswith("DBManager") else b"[X]\r\nA=1\r\n") for r in ini_rels}
        st = {r: (10, "2026-11-19 12:00") for r in stat_rels}
        return ini, {}, st
    V._read = fake_read2
    try:
        C = V.configs()["configs"]
    finally:
        V._read = saved
    sec_rows = [c for c in C if c["secret"]]
    check("А5.5 конфиги стойки: файлы с паролями / DSN (LoginMng, DBMng, DBInfo ×5, Mgame, EacServer, PasswordSQL) — без содержимого (размер и "
          "время), файл с «пароль=» внутри — содержимое скрыто; правится только Collection.ini (белый список)",
          all(c["text"] is None for c in sec_rows) and any(c["file"] == "LoginMng.ini" for c in sec_rows)
          and any(c["file"] == "ConfigSet\\ServerInfo.ini" and c["folder"] == "DBManager" and c["secret"] for c in C)
          and {c["file"] for c in C if c["edit"]} == {COLL}, [(c["folder"], c["file"]) for c in sec_rows][:4])

    # ---- переводы, веб, консоль
    from core import i18n
    i18n.set_lang("en")
    try:
        tr_ok = (i18n.tr("ключ PollMs: допустимо 100…5000 (код) — 50 вне предела").startswith("key PollMs: allowed 100…5000")
                 and i18n.tr("AsdaPatch [P30_MapSlots] Enabled — сильная правка: выключение патча P30_MapSlots").endswith("strong change: turning patch P30_MapSlots off")
                 and "rebuild the changeset" in i18n.tr("ConfigSet\\patches.ini: правка Ch2_GameServer без пары GameServer (паритет Ch2 — restart_stack код 6) — пересоберите набор")
                 and "without its pair" in i18n.tr("ConfigSet\\patches.ini: правка Ch2_GameServer без пары GameServer (паритет Ch2 — restart_stack код 6) — пересоберите набор"))
    finally:
        i18n.set_lang("ru")
    check("А5.5 переводы EN: предел, сильная правка (вложенный перевод причины), пара Ch2 (вложенный)", tr_ok)
    js = open(os.path.join(ROOT, "web", "patchcfg.js"), encoding="utf-8").read()
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    shops = open(os.path.join(ROOT, "web", "shops.js"), encoding="utf-8").read()
    check("А5.5 веб: web/patchcfg.js подключён, вкладка «Настройки патчей» (#/shops/patches, право patchcfg.view), без innerHTML, позиции — "
          "shop.cs_item_add patch.set / config.set через общий sdAddAll",
          "/patchcfg.js" in html and "#/shops/patches" in shops and "innerHTML" not in js and "patch.set" in js and "config.set" in js
          and "/api/patchcfg" in js and "sdAddAll" in js)
    from core import auth
    check("А5.5 права: patchcfg.view / patchcfg.edit — владелец и администратор, patchcfg.apply — только владелец; области — patchcfg.edit / apply",
          auth.PERMS["patchcfg.view"] == {"owner", "admin"} and auth.PERMS["patchcfg.edit"] == {"owner", "admin"}
          and auth.PERMS["patchcfg.apply"] == {"owner"} and SD.area_perm("patch.set", "apply") == "patchcfg.apply"
          and SD.area_perm("config.set", "edit") == "patchcfg.edit")
    adm = os.path.join(ROOT, "asda_admin.py")
    r1 = subprocess.run([sys.executable, adm, "patchcfg", "--bogus"], capture_output=True, timeout=120)
    r2 = subprocess.run([sys.executable, adm, "patchcfg"], capture_output=True, timeout=120)
    check("А5.5 консоль: patchcfg с неизвестным ключом и без подкоманды — отказ без чтения стойки (код ≠ 0)", r1.returncode != 0 and r2.returncode != 0,
          (r1.returncode, r2.returncode, r1.stdout[-200:]))


# =====================================================================================================================
_SAMP = [("(.+?)", "Бета"), ("(.+)", "Альфа"), (r"(-?\d+)", "7"), ("([0-9A-F]+)", "1F"), ("([0-9.]+)", "1.5"), (r"(\d+)", "8")]
_CYR = re.compile(r"[А-Яа-яЁё]")


def _sample(pat):
    """Образец текста по шаблону таблицы переводов (подстановки — «Альфа», 7, …) → строка | None (шаблон не разворачивается)."""
    body = pat[1:-1] if pat.startswith("^") and pat.endswith("$") else pat
    s = body
    for a, b in _SAMP:
        s = s.replace(a, b)
    u = re.sub(r"\\(.)", lambda m: m.group(1), s, flags=re.S)
    try:
        return u if re.fullmatch(body, u, re.S) else None
    except re.error:
        return None


def shadowed_translations():
    """★ ревизия 45 В-1: сверка переводов ВСЕХ областей — для каждого шаблона core/i18n.PATTERNS образец его же текста; если его первым
    ловит ДРУГОЙ шаблон и перевод от этого хуже (в EN осталось больше русских слов, чем дал бы свой шаблон) — перехват. → [(образец,
    получилось, свой перевод, перехватчик)]; число образцов."""
    from core import i18n
    i18n.set_lang("en")
    base = list(i18n.PATTERNS)
    bad, n = [], 0
    try:
        for idx, (rx, _en) in enumerate(base):
            s = _sample(rx.pattern)
            if not s:
                continue
            n += 1
            first = next((j for j, (r2, _e) in enumerate(base) if r2.match(i18n.item_names(s))), idx)
            if first == idx:
                continue
            got = i18n.tr(s)
            i18n.PATTERNS[:] = [base[idx]] + base
            try:
                own = i18n.tr(s)
            finally:
                i18n.PATTERNS[:] = base
            strip = lambda t: t.replace("Альфа", "").replace("Бета", "")
            if got != own and len(_CYR.findall(strip(got))) > len(_CYR.findall(strip(own))):
                bad.append((s[:160], got[:160], own[:160], base[first][0].pattern[:100]))
    finally:
        i18n.PATTERNS[:] = base
        i18n.set_lang("ru")
    return bad, n


def revision45(check):
    """★ ревизия 45 (21.11.2026): проверки исправлений А5.5 — offline, подставная стойка."""
    from domains import patchcfg as V, shopcs
    from domains.cs_kinds import patchcfg as K
    from core import i18n
    cat = K.catalog()
    sec = {d: {s["name"]: s for s in cat["dlls"][d]["sections"]} for d in cat["dlls"]}
    kd = lambda d, s, k: next(x for x in sec[d][s]["keys"] if x["key"] == k)

    # ---- В-1: переводы всех областей
    bad, n = shadowed_translations()
    i18n.set_lang("en")
    try:
        hand = {x: i18n.tr(x) for x in (
            "витрина 6800, список 1, место 2: сейчас не 3 — пересоберите набор",
            "реестр карт: у карты 7 server.open_use не true — пересоберите набор",
            "RewardTable.BIN запись 5: Exp сейчас 7, при проверке было 9 — пересоберите набор",
            "QuestBook.json 10.name: сейчас не «abc» — пересоберите набор",
            "item_table.txt code=1: col сейчас 2, при проверке было 3 — пересоберите набор",
            "ConfigSet\\patches.ini: правка Ch2_GameServer без пары GameServer (паритет Ch2 — restart_stack код 6) — пересоберите набор",
            "ConfigSet\\patches.ini: копии X — не из семьи GSP (GameServer) — пересоберите набор")}
    finally:
        i18n.set_lang("ru")
    check("ревизия 45 В-1: сверка переводов всех областей — у каждого из %d образцов (по шаблону каждой области таблицы) первым срабатывает "
          "шаблон, который переводит не хуже своего; образцы ревизии (витрина 6800, реестр карт, RewardTable, QuestBook, item_table, пары Ch2) — "
          "целиком по-английски" % n,
          n > 2000 and not bad and all("пересоберите" not in v and "сейчас" not in v and "правка" not in v for v in hand.values())
          and "without its pair" in hand["ConfigSet\\patches.ini: правка Ch2_GameServer без пары GameServer (паритет Ch2 — restart_stack код 6) — пересоберите набор"],
          (bad[:4], [v for v in hand.values() if _CYR.search(v)][:3]))

    # ---- В-2: файл → своя секция, зависимости через чтение чужих секций
    a = sec["AsdaPatch"]
    files_ok = all(a[s]["files"] and all(os.path.basename(f).startswith(p) for f in a[s]["files"])
                   for s, p in (("P55_PacketValidator", "p55_"), ("P64_StatePreamble", "p64_"), ("P69_IntegrityAutoBlock", "p69_"),
                                ("P48_KickAutoBlock", "p48_")))
    hard = {k: [u for u, _k, _w in v] for k, v in K.hard_deps("AsdaPatch").items()}
    hn = {k: [u for u, _k, _w in v] for k, v in K.hard_deps("AddonNPC").items()}
    soft = {(s["name"], f["section"], f["key"]) for s in a.values() for f in s.get("reads_foreign") or [] if not f.get("hard")}
    check("ревизия 45 В-2: файл → секция по реестру патчей (p55 / p64 / p69 / p48 — свои секции, не P47 / P53); жёсткие P47 → P55, P64, P129 (★ 22.11, v86) "
          "(«if (!GetBool(P47, Enabled)) return Failed») и AddonNPC P53 → N14, N15; мягкие — P127 / P73 → [P48] SoulMateSessionAccount, "
          "P48 → [P53] KickJournalWhenP48Off, P81 → [P80] RelayWhileMoving, P69 → P47 / P55 / P61; ложных «P53 вызывает P47» больше нет; "
          "сборка AddonNPC / LoginPatch / DBPatch — по build.bat (AcJournal.cpp из AsdaPatch)",
          files_ok and sorted(hard.get(("AsdaPatch", "P47_IdentityOperatorGate"), [])) == ["P129_ChatLog", "P55_PacketValidator", "P64_StatePreamble"]
          and sorted(hn.get(("AddonNPC", "P53_AcJournal"), [])) == ["N14_CombatLimits", "N15_SkillArea"]
          and {("P127_AdminBridge", "P48_KickAutoBlock", "SoulMateSessionAccount"), ("P73_EacBridge", "P48_KickAutoBlock", "SoulMateSessionAccount"),
               ("P48_KickAutoBlock", "P53_AcJournal", "KickJournalWhenP48Off"), ("P81_ActionCodeGuard", "P80_CrouchSpeedJumpRelay", "RelayWhileMoving"),
               ("P69_IntegrityAutoBlock", "P55_PacketValidator", "Enabled")} <= soft
          and not any("P55_KickAttribution" in x or "P69_TakeKickMark" in x for x in (a["P53_AcJournal"].get("needs") or {}).get("P47_IdentityOperatorGate", []))
          and not any("P48_" in x for x in (a["P47_IdentityOperatorGate"].get("needs") or {}).get("P53_AcJournal", []))
          and any("AcJournal.cpp" in f for f in cat["dlls"]["LoginPatch"]["sources"]) and kd("LoginPatch", "P53_AcJournal", "FlushIntervalMs")["reads"]
          and (kd("LoginPatch", "P53_AcJournal", "FlushIntervalMs")["lo"], kd("LoginPatch", "P53_AcJournal", "FlushIntervalMs")["hi"]) == (50, 60000),
          (files_ok, hard, hn, sorted(soft)[:6]))
    with fake_stack() as _x:
        e = _ev([("patch.set", _ps(section="P47_IdentityOperatorGate", key="Enabled", value="0"))])
        e2 = _ev([("patch.set", _ps(section="P47_IdentityOperatorGate", key="Enabled", value="0")),
                  ("patch.set", _ps(section="P55_PacketValidator", key="Enabled", value="0")),
                  ("patch.set", _ps(section="P64_StatePreamble", key="Enabled", value="0")),
                  ("patch.set", _ps(section="P129_ChatLog", key="Enabled", value="0"))])   # ★ 22.11 (P129, v86): тоже зависит от P47
        e3 = _ev([("patch.set", _ps(section="P48_KickAutoBlock", key="SoulMateSessionAccount", value="0"))])
        e4 = _ev([("patch.set", _ps(dll="AddonNPC", section="P53_AcJournal", key="Enabled", value="0"))])
    check("ревизия 45 В-2: P47 Enabled=0 при включённых P55 / P64 — отказ «от него зависит включённый P55_PacketValidator»; вместе с P55, P64 и P129 "
          "одним набором — можно; [P48] SoulMateSessionAccount — предупреждение «читает и P127_AdminBridge / P73_EacBridge»; AddonNPC P53 "
          "Enabled=0 при включённых N14 / N15 — отказ",
          any("зависит включённый P55_PacketValidator" in x for x in _errs(e)) and not _errs(e2)
          and any("читает и P127_AdminBridge" in w for w in e3.positions[0]["warnings"]) and any("читает и P73_EacBridge" in w for w in e3.positions[0]["warnings"])
          and any("N14_CombatLimits" in x for x in _errs(e4)), (_errs(e), _errs(e2), e3.positions[0]["warnings"][:4], _errs(e4)))

    # ---- В-3: значение выключает патч
    mm = kd("AsdaPatch", "P30_MapSlots", "MaxMaps")
    with fake_stack() as _x:
        e = _ev([("patch.set", _ps(section="P30_MapSlots", key="MaxMaps", value="20"))])
        e2 = _ev([("patch.set", _ps(section="P30_MapSlots", key="MaxMaps", value="23")), ("patch.set", _ps(section="P120_MineTravel", key="Enabled", value="0")),
                  ("patch.set", _ps(section="P40_CrystalTeleportGate", key="Enabled", value="0"))])
        e3 = _ev([("patch.set", _ps(section="P30_MapSlots", key="MaxMaps", value="27"))])
        e4 = _try_norm("patch.set", _ps(section="P30_MapSlots", key="MaxMaps", value="31"))
    check("ревизия 45 В-3: P30 MaxMaps — constexpr kStockSlots = 23 / kHardMax = 30 разобраны (≤ 23 — Disabled, предел 30); MaxMaps=20 при "
          "включённых P120 / P40 — отказ; 23 вместе с выключением P120 и P40 — сильная правка «значение выключает патч»; 27 — без отказа; 31 — "
          "вне предела",
          mm["hi"] == 30 and {(o[0], o[1]) for o in mm["off_when"]} == {("<", 23), ("==", 23)}
          and any("MaxMaps=20" in x and "P120_MineTravel" in x for x in _errs(e)) and not _errs(e2)
          and any("значение выключает патч P30_MapSlots" in b["what"] for b in e2.summary()["balance"] if b["strong"])
          and not _errs(e3) and e4 and "…30" in e4, (_errs(e), _errs(e2), _errs(e3), e4))

    # ---- В-4: подключение / адрес / путь — по типу значения
    vo = {k: _try_norm("patch.set", _ps(key=k, value="x")) for k in ("Server", "Login", "Driver")}
    files = stack_files()
    files["GameServer" + BS + PINI] = make_ini("AsdaPatch", tweak=dict(list(BASE_TW.items()) + [(("P120_MineTravel", "EnterFrom"), "EnterFrom=10.1.2.3")]))
    for g in ("Ch2_GameServer",):
        files[g + BS + PINI] = files["GameServer" + BS + PINI]
    with fake_stack(files) as _x:
        e = _ev([("patch.set", _ps(section="P120_MineTravel", key="EnterFrom", value="3", scope="field"))])
    allvo = [(d, s["name"], k["key"]) for d in cat["dlls"] for s in cat["dlls"][d]["sections"] for k in s["keys"] if k.get("view_only")]
    check("ревизия 45 В-4: [P127_AdminBridge] Server / Login / Driver — только просмотр (буфер уходит в строку подключения DRIVER=…;SERVER=…;"
          "UID=…, p127_admin_bridge.cpp:1867); живое значение-адрес у строкового ключа — отказ «живое значение»; по каталогу ≥ 20 ключей "
          "только просмотра по типу значения во всех DLL (пути, адреса, подключения AcJournal ×4)",
          all(v and "только просмотр" in v and "подключение к базе" in v for v in vo.values())
          and any("живое значение" in x for x in _errs(e)) and len(allvo) >= 20
          and {("LoginPatch", "P53_AcJournal", "Database"), ("DBPatch", "P53_AcJournal", "DbConfigFile")} <= set(allvo), (vo, _errs(e), len(allvo)))

    # ---- С-1: пределы — тернарные, константы, несколько переменных, исключённые значения, циклы
    lim = {k: _try_norm("patch.set", _ps(section=s, key=k, value=v)) for s, k, v in (
        ("P120_MineTravel", "RefuseCode", "300"), ("P120_MineTravel", "MineMap", "30"), ("P120_MineTravel", "ExitTo", "-1"),
        ("P120_MineTravel", "Range", "17"), ("P40_CrystalTeleportGate", "RefuseCode", "1"), ("P61_TrafficEncryption", "TxQueueKB", "70000"),
        ("P61_TrafficEncryption", "MaxPendingHandshakes", "600"), ("P55_PacketValidator", "RateMovePerSec", "20000"),
        ("P88_TitleEvents", "Threshold190", "0"))}
    with fake_stack() as _x:
        e = _ev([("patch.set", _ps(section="P69_IntegrityAutoBlock", key="Stage2Count", value="10"))])
        e2 = _ev([("patch.set", _ps(section="P69_IntegrityAutoBlock", key="Stage1Count", value="10")),
                  ("patch.set", _ps(section="P69_IntegrityAutoBlock", key="Stage2Count", value="15"))])
        e3 = _ev([("patch.set", _ps(section="P11_ServerAnnounceSources", key="RefineFailWindowSec", value="77"))])
    check("ревизия 45 С-1: пределы — P120 RefuseCode 300 / MineMap 30 / ExitTo −1 / Range 17 (одно условие на четыре ключа, kOpenHardMax), "
          "P40 RefuseCode=1 (недопустимое значение), P61 TxQueueKB 70000 и MaxPendingHandshakes 600 (тернарные, AsdaWire::kMaxSlots), P55 Rate*, "
          "P88 Threshold* (циклы) — отказ; P69 Stage2Count 10 < Stage1 20 — ошибка «ступени станут негодны», обе ступени одним набором — можно; "
          "целое без предела — сильная правка «предел не подтверждён»",
          all(lim.values()) and not _errs(e2) and any("ступени P69" in x for x in _errs(e))
          and any("предел не подтверждён" in b["what"] for b in e3.summary()["balance"] if b["strong"]), (lim, _errs(e), _errs(e2), _errs(e3)))

    # ---- С-3: защитные секции
    check("ревизия 45 С-3: сильная правка — P44, P62, P63, P64, P56, P57, P60, P66, P81, P92, P95, P107, AddonNPC N14 / N15 / N20, guard / bounds "
          "по имени, любая секция с Mode; обычные (P01, P120) — нет",
          all(K.strong_section("AsdaPatch", sec["AsdaPatch"][n]) for n in (
              "P44_ExchangeIntegrity", "P62_SlotUniqueness", "P63_InFlightLock", "P64_StatePreamble", "P56_CombatLimits", "P57_MoveGuard",
              "P60_ValueGuard", "P66_PositionGuard", "P81_ActionCodeGuard", "P92_HostileTargetGuard", "P95_ItemUseGuard", "P107_CantActGate",
              "P18_WarehouseDupeAndBounds", "P110_Job4PointPools"))
          and all(K.strong_section("AddonNPC", sec["AddonNPC"][n]) for n in ("N14_CombatLimits", "N15_SkillArea", "N20_PartyShareClamp"))
          and not K.strong_section("AsdaPatch", sec["AsdaPatch"]["P01_RareItemNotice6616"]) and not K.strong_section("AsdaPatch", sec["AsdaPatch"]["P120_MineTravel"]))

    # ---- С-4: конфиги стойки в EN
    i18n.set_lang("en")
    try:
        untr = [t for row in V.STACK_CONFIGS for t in (row[2], row[3]) if t and _CYR.search(i18n.tr(t))]
    finally:
        i18n.set_lang("ru")
    check("ревизия 45 С-4: каждая строка STACK_CONFIGS («что читается» и «почему только просмотр») переводится на EN", not untr, untr[:3])

    # ---- С-5 / С-6: версия живой DLL ≠ каталогу
    v = cat["dlls"]["AsdaPatch"]["version"]
    f_old, f_new = stack_files(), stack_files()
    for g in GS3:
        f_old[g + BS + PINI] = make_ini("AsdaPatch", version=v - 2, tweak=dict(BASE_TW))
        f_new[g + BS + PINI] = make_ini("AsdaPatch", version=v + 1, tweak=dict(BASE_TW))
    with fake_stack(f_old) as _x:
        e = _ev([("patch.set", _ps())])
    with fake_stack(f_new) as _x:
        e2 = _ev([("patch.set", _ps())])
    check("ревизия 45 С-5 / С-6: Version в ini (живая DLL) %d при каталоге по исходнику %d — отказ «сначала выложите DLL Version %d отдельным "
          "рестартом»; живая новее каталога — отказ «каталог устарел»" % (v - 2, v, v),
          any(("Version в ini %d" % (v - 2)) in x and ("выложите DLL Version %d" % v) in x for x in _errs(e))
          and any("каталог устарел" in x for x in _errs(e2)), (_errs(e)[:1], _errs(e2)[:1]))

    # ---- Н-1: файл, который не собирается обратно байт в байт
    raw = make_ini("LoginPatch") + b"\x00"                            # нечётная длина UTF-16
    t = K.IniTable("LoginManager" + BS + PINI, raw)
    files = stack_files()
    files["LoginManager" + BS + PINI] = raw
    with fake_stack(files) as _x:
        e = _ev([("patch.set", _ps(dll="LoginPatch", section="L01_LoginLogMask", key="Enabled", value="0"))])
    check("ревизия 45 Н-1: IniTable — файл не собирается обратно байт в байт (нечётная длина UTF-16) — помечен, правка — отказ; чистый — без пометки",
          t.bad == "utf-16-le" and any("не собирается обратно байт в байт" in x for x in _errs(e))
          and K.IniTable("x", make_ini("LoginPatch")).bad is None, (t.bad, _errs(e)))

    # ---- Н-2: охват в пересечении ожидающих наборов, недоделанные выкладки
    pend = [{"id": 9, "status": "approved", "server_state": "dry_ok", "kind": "patch.set", "params": _ps(scope="indun", value="700")}]
    with fake_stack(pending=lambda: pend) as _x:
        e = _ev([("patch.set", _ps(scope="field", value="900"))], cs_id=3)
        e2 = _ev([("patch.set", _ps(scope="all", value="900"))], cs_id=3)
    import inspect
    src = inspect.getsource(K.pending_items)
    check("ревизия 45 Н-2: ожидающий набор indun=700 и новый field=900 — копии не пересекаются, ошибки нет; all=900 — ошибка «уже ждёт»; "
          "ожидающими считаются и наборы с недоделанной выкладкой / откатом (partial, partial_apply, partial_rollback, unknown)",
          not _errs(e) and any("наборе №9" in x for x in _errs(e2)) and all(w in src for w in ("'partial_apply'", "'partial_rollback'", "'unknown'")),
          (_errs(e), _errs(e2)))

    # ---- Н-3 / Н-5: текст второго подтверждения и второй фактор
    cs = {"id": 1, "items": [{"kind": "patch.set"}], "check": {"balance_strong": True, "balance": [
        {"pos": 1, "what": "AsdaPatch [P63_InFlightLock] Lock6096 — сильная правка: выключение", "old": "1", "new": "0", "codes": [],
         "kind": "patch", "strong": True, "gate": True, "totp": True}]}}
    try:
        shopcs.CsApprove._balance(cs, {})
        no = None
    except Exception as ex:
        no = str(ex)
    calls = []
    from core import auth
    saved = auth.totp_confirm
    auth.totp_confirm = lambda uid, code: calls.append((uid, code))
    try:
        class _C:
            via, user_id = "web", 5
        shopcs.CsApprove._totp(cs, {"totp": "123456"}, _C())
        _C.via = "cli"
        shopcs.CsApprove._totp(cs, {}, _C())
    finally:
        auth.totp_confirm = saved
    check("ревизия 45 Н-3 / Н-5: второе подтверждение настроек патчей — «сильная правка настроек серверных патчей», без «на руках у игроков»; "
          "MasterEnable=0 / выключение защиты — код второго фактора при утверждении из браузера (из консоли ПК — без него)",
          no and "настроек серверных патчей" in no and "на руках" not in no and calls == [(5, "123456")], (no, calls))

    # ---- Н-4: «ждёт рестарта» по секундам с запасом на MergeMissing, хвост журнала без паспорта
    check("ревизия 45 Н-4: ini записан через 20 с после старта (MergeMissing) — не «изменён после старта», через 10 мин — изменён; время без "
          "секунд в ту же минуту — «не знаем»",
          V.ini_newer("2026-11-19 12:28:29", "2026-11-19 12:28:09") is False and V.ini_newer("2026-11-19 12:38:09", "2026-11-19 12:28:09") is True
          and V.ini_newer("2026-11-19 12:28", "2026-11-19 12:28:09") is None)
    saved = V._read

    def fake_tail(ini_rels, log_dirs, stat_rels):
        fs = stack_files()
        ini = {r: fs.get(r) for r in ini_rels}
        logs = {d: "строки без паспорта\r\n" for d in log_dirs}
        logs.update({d + "#trunc": True for d in log_dirs})
        return ini, logs, {r: (1, "2026-11-19 12:00:00") for r in stat_rels}
    V._read = fake_tail
    try:
        S = V.state(force=True, dll_only="LoginPatch")
    finally:
        V._read = saved
    check("ревизия 45 Н-4: журнал больше 1 МБ, в хвосте нет паспорта — режимы «не прочитано», а не «нет в журнале», с предупреждением",
          all(m == "unread" for s in S["dlls"][0]["sections"] for m in s["modes"].values() if m != "general")
          and any("в прочитанном хвосте нет паспорта" in w for w in S["warnings"]), S["warnings"][:2])

    # ---- Н-6: длина строки по буферу места чтения
    long_ = _try_norm("patch.set", _ps(section="P120_MineTravel", key="EnterNpc", value="1," * 70))
    check("ревизия 45 Н-6: строка длиннее буфера GetStr места чтения (P120 EnterNpc — wchar_t buf[128] → 127) — отказ «буфер чтения в DLL»",
          kd("AsdaPatch", "P120_MineTravel", "EnterNpc")["maxlen"] == 127 and long_ and "буфер чтения" in long_, long_)

    # ---- Н-7 и мелочи
    js = open(os.path.join(ROOT, "web", "patchcfg.js"), encoding="utf-8").read()
    check("ревизия 45 Н-7 и мелочи: в конфигах без пометки «секрет» скрываются и USER= / LOGIN= / ID=; THREADID= — нет; окно «Конфиги стойки» "
          "добавляет позицию config.set (pcCfgEdit); чтения вне шаблона (P20) показываются во вкладке; DBPatch Version — умолчание 11 (kVersion)",
          V._looks_secret("[DB]\r\nUSER=sa\r\n") and V._looks_secret("LOGIN=x") and V._looks_secret("ID=5") and not V._looks_secret("THREADID=1")
          and "function pcCfgEdit" in js and "\"config.set\"" in js and "d.outside" in js
          and kd("DBPatch", "General", "Version")["def"] == str(cat["dlls"]["DBPatch"]["version"])
          and any(o.startswith("P20_PartyInviteValidation/") for o in cat["dlls"]["AsdaPatch"]["reads_outside_template"])
          and not any(o.startswith("P22_DbFameHigh/") for o in cat["dlls"]["AsdaPatch"]["reads_outside_template"]))


# =====================================================================================================================
def sandbox(check, ldb):
    """Набор «Настройки патчей» целиком на песочнице стойки (НАСТОЯЩИЙ deploy_changeset, подставной restart_stack)."""
    import selftest_shops_sandbox as X
    from core import ops
    from domains import shopcs
    from domains.cs_kinds import patchcfg as K
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with X.sandbox(ldb) as (st, env):
        files = stack_files()
        for rel, b in files.items():
            p = st.path(rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b)
        before = {rel: open(st.path(rel), "rb").read() for rel in files}
        cid = X._run(ctx, "shop.cs_create", title="ПЕСОЧНИЦА А5.5", note="самотест песочницы А5.5: настройки патчей")["result"]["id"]
        X._run(ctx, "shop.cs_item_add", cs=cid, kind="patch.set", params=_ps())
        X._run(ctx, "shop.cs_item_add", cs=cid, kind="patch.set", params=_ps(dll="SrvDbPatch", section="P126_DbReconnect", key="Enabled", value="0"))
        X._run(ctx, "shop.cs_item_add", cs=cid, kind="config.set", params={"file": COLL, "section": "COLLECTION_INFO",
                                                                           "key": "CollectionTypeAniTime01", "value": "9500"})
        X._run(ctx, "shop.cs_check", cs=cid)
        cs = shopcs.get(cid)
        _r, no = X._try(ctx, "shop.cs_approve", cs=cid)
        X._run(ctx, "shop.cs_approve", cs=cid, balance_ok="balance")
        check("песочница А5.5: только сервер, сильная правка (P127, выключение P126) — без второго подтверждения отказ, владелец — утверждён",
              cs["check"]["ok"] and cs["check"]["server_needed"] and not cs["check"]["client_needed"] and no and "второе подтверждение" in no
              and shopcs.get(cid)["status"] == "approved", (cs["check"]["errors"], no))
        cid2 = X._run(ctx, "shop.cs_create", title="ПЕСОЧНИЦА А5.5 б", note="самотест песочницы А5.5: другой набор")["result"]["id"]
        X._run(ctx, "shop.cs_item_add", cs=cid2, kind="patch.set", params=_ps(value="2000"))
        X._run(ctx, "shop.cs_check", cs=cid2)
        c2 = shopcs.get(cid2)["check"]
        check("песочница А5.5: второй набор с той же целью и другим значением — проверка с ошибкой «уже ждёт в наборе №…» (настоящий SQL adm.changeset)",
              not c2["ok"] and any(("наборе №%d" % cid) in x for x in c2["errors"]), c2["errors"][:3])
        X._run(ctx, "shop.cs_cancel", cs=cid2)
        X._run(ctx, "shop.cs_server_dry", cs=cid)
        man = json.load(open(shopcs.manifest_path(cid), encoding="utf-8"))
        want = sorted([g + BS + PINI for g in GS3] + [r + BS + SDBINI for r in SDB5] + [n + BS + COLL for n in NPC3])
        check("песочница А5.5: сухой прогон НАСТОЯЩЕГО deploy_changeset — patches.ini ×3 GS, srvdbpatch.ini ×5, Collection.ini ×3",
              shopcs.get(cid)["server_state"] == "dry_ok" and sorted(man["files"]) == want, sorted(man["files"]))
        r, e = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
        after = {rel: open(st.path(rel), "rb").read() for rel in files}
        g = after["GameServer" + BS + PINI]
        chg = [(o, n) for o, n in zip(before["GameServer" + BS + PINI][2:].decode("utf-16-le").split("\r\n"), g[2:].decode("utf-16-le").split("\r\n")) if o != n]
        check("песочница А5.5: выложено рестартом — в patches.ini (UTF-16, BOM) изменилась одна строка «PollMs  =  1000 », Ch2 = поле, srvdbpatch ×5 "
              "Enabled=0, Collection ×3 9500; LoginManager / DBManager не тронуты",
              r and shopcs.get(cid)["server_state"] == "applied" and g[:2] == b"\xff\xfe" and chg == [("PollMs  =  500 ", "PollMs  =  1000 ")]
              and after["Ch2_GameServer" + BS + PINI] == g and all(b"CollectionTypeAniTime01 = 9500" in after[n + BS + COLL] for n in NPC3)
              and all(K.IniTable("t", after[x + BS + SDBINI]).get("P126_DbReconnect", "Enabled") == "0" for x in SDB5)
              and after["LoginManager" + BS + PINI] == before["LoginManager" + BS + PINI], (e, chg))
        r2, e2 = X._try(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart")
        back = {rel: open(st.path(rel), "rb").read() for rel in files}
        check("песочница А5.5: откат рестартом — все файлы байт в байт как до набора", r2 and back == before, e2)


# =====================================================================================================================
def live(check):
    """Только чтение (SSH): ничего не пишется, набор не создаётся."""
    from core import config
    from domains import patchcfg as V
    from domains.cs_kinds import patchcfg as K
    if config.get().on_server:
        return check("живой самотест А5.5 — с ПК", True)
    S = V.state(force=True)
    by = {d["dll"]: d for d in S["dlls"]}
    check("живое (SSH, только чтение): ini всех копий прочитаны — AsdaPatch ×3, AddonNPC ×3, LoginPatch, DBPatch, SrvDbPatch ×5; журналы "
          "патчей прочитаны, у каждой копии есть последний запуск",
          set(by) == set(K.DLL_INI) and all(c["read"] and c["run"] for d in S["dlls"] for c in d["copies"])
          and [len(by[d]["copies"]) for d in ("AsdaPatch", "AddonNPC", "LoginPatch", "DBPatch", "SrvDbPatch")] == [3, 3, 1, 1, 5],
          [(d["dll"], [(c["folder"], c["read"], c["log"]) for c in d["copies"]]) for d in S["dlls"]])
    check("живое: паритет Ch2 = поле (patches.ini GS и NpcServer, srvdbpatch Relay); режимы разобраны (ни одного «не прочитано»)",
          not any("паритет Ch2" in w for w in S["warnings"])
          and all(m != "unread" for d in S["dlls"] for s in d["sections"] for m in s["modes"].values()), S["warnings"][:4])
    secret_vals = [v for d in S["dlls"] for s in d["sections"] for k in s["keys"] if k["secret"] for v in k["values"].values() if v not in (None, "", "•••")]
    check("живое: значения секретных ключей не показываются", not secret_vals)
    C = V.configs()["configs"]
    check("живые конфиги стойки: прочитаны, у файлов с паролями / DSN содержимого нет", all(c["read"] for c in C)
          and all(c["text"] is None for c in C if c["secret"]) and any(c["secret"] for c in C), [(c["folder"], c["file"], c["read"]) for c in C if not c["read"]])
    from domains import shopdata as SD
    from domains.cs_kinds import patchcfg as K2
    saved = K2.PENDING_SOURCE
    K2.PENDING_SOURCE = saved
    try:
        live_v = next(k["values"]["GameServer"] for s in by["AsdaPatch"]["sections"] if s["name"] == "P127_AdminBridge" for k in s["keys"] if k["key"] == "PollMs")
        nv = "600" if live_v != "600" else "700"
        ev = SD.Eval([{"pos": 1, "kind": "patch.set", "params": _ps(value=nv)}], False)
        ev.cs_id = None
        ev.run()
        s = ev.summary()
        files = s["server"]["files"]
        lv = {str(c.get("version")) for c in by["AsdaPatch"]["copies"]}
        cv = str(by["AsdaPatch"]["version_src"])
        if lv == {cv}:
            check("живая сухая оценка patch.set P127 PollMs (ничего не записано): ×3 GameServer, одна строка «было → станет», сильная правка",
                  not _errs(ev) and files and sorted(files[0]["gs"]) == sorted(GS3) and len(files[0]["diff"]) == 1 and s["balance_strong"],
                  (_errs(ev), [(f["table"], f["gs"], f["diff"]) for f in files]))
        else:
            # ★ ревизия 45 С-5 / С-6: живая DLL другой Version, чем исходник каталога (v82 при v84 до выкладки deploy_p127e) — отказ
            check("живая сухая оценка patch.set P127 PollMs (ничего не записано): Version живой DLL %s ≠ каталогу %s — отказ «сначала выложите "
                  "DLL» (ревизия 45 С-5 / С-6)" % ("/".join(sorted(lv)), cv),
                  any("Version в ini" in x for x in _errs(ev)) and not files, _errs(ev)[:2])
    finally:
        K2.PENDING_SOURCE = saved
