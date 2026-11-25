# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_shops_sandbox.py — ПЕСОЧНИЦА путей применения и отката наборов изменений (ревизии 30 М-11 и 31, 19.11.2026).

Ни одной записи в реальные файлы стойки или порта, ни одного реального рестарта. Песочница моделирует живую среду:
  * стойка — временная папка с тремя GameServer (синтетические таблицы selftest_shops._tables); НАСТОЯЩИЕ deploy_premium_boxes и
    deploy_changeset в процессе: SSH-функции (rmd5 / rbusy / rcopy / rupload / rdel / rread), корень V2 и корень локальных
    бэкапов подменены на эту папку; процессы стойки — словарь по stack_layout.EXPECT (15 шт.), можно положить часть;
  * restart_stack — подставной с поведением настоящего (строка «все процессы стойки остановлены» после шага 3, коды 2/3/4/5/6),
    падает на любом шаге; подъём — подставной с семантикой --start-only (при живом процессе — код 7, ничего не делает);
    сам режим --start-only настоящего restart_stack.py проверяется отдельно (его шаги подменены, стойка не трогается);
  * клиент — временные копии ВСЕХ клиентских таблиц, Client.load НАСТОЯЩИЙ (читает копии; после client-apply таблицы реально
    меняются), подставные импортёры пересобирают NpcShop.json / PremiumShopBin.json, подставной asda_ml_dt_point со сторожем
    «ассет = csv_old» (как настоящий: сухой прогон с СТОП отвечает 0, запись с СТОП — провал по --expect-asset);
  * сбой SSH после рестарта, неполная стойка, сдвиг пояса времени; журнал и состояния — LocalDB; changelog / INDEX — копии.
Побочных эффектов при импорте нет.
"""
import contextlib
import datetime
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _md5(p):
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


class Stack:
    """Песочница стойки: файлы, процессы, журнал шагов подставного restart_stack и точки сбоя."""

    def __init__(self, root, raw, expect):
        self.root, self.calls, self.fail, self.expect = root, [], set(), dict(expect)
        self.procs = dict(expect)
        self.uploads = 0
        self.ssh_down = False
        self.sales = {"gp7": 0, "npc": 0}
        self.released = False
        for rel, b in raw.items():
            p = self.path(rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b)

    @property
    def running(self):
        return all(self.procs.get(k, 0) >= v for k, v in self.expect.items())

    def path(self, rel_or_abs):
        p = rel_or_abs.replace("/", "\\")
        return p if p.lower().startswith(self.root.lower()) else os.path.join(self.root, p)

    def md5(self, rel):
        if self.ssh_down:
            raise RuntimeError("подставной сбой SSH")
        p = self.path(rel)
        return _md5(p) if os.path.isfile(p) else "none"


def _hexprice(v):
    b = bytearray(248)
    struct.pack_into("<i", b, 0xA4, v)
    return bytes(b).hex()


def _client_files(cdir):
    """Копии клиентских таблиц, согласованные с selftest_shops._client_dict."""
    items = [(30000, 100), (30001, 500), (30002, 300), (30003, 900), (30004, 50), (30005, 70), (30006, 40), (30007, 45)]
    bl_head = "_row,Code," + ",".join("Slot%02dItemCode" % i for i in range(35)) + "," + ",".join("Slot%02dWeight" % i for i in range(35))
    pairs = [[30000, 100], [30005, 50]] + [[0, 0]] * 33
    bl_row = "0,1," + ",".join(str(c) for c, _ in pairs) + "," + ",".join(str(w) for _, w in pairs)
    return {
        "item_list": ("item_list.csv", "_row,ItemCode,ItemName,Price,DataHex\r\n" +
                      "".join("%d,%d,x%d,%d,%s\r\n" % (i, c, c, p, _hexprice(p)) for i, (c, p) in enumerate(items))),
        "packagetable": ("packagetable.csv", "_row,Index,Item0,Qty0,Item1,Qty1,Item2,Qty2,Item3,Qty3,Item4,Qty4,Item5,Qty5,Reserved52\r\n"
                                             "0,0,30000,5,-1,0,-1,0,-1,0,-1,0,780,0,21\r\n"),
        "booster_list": ("booster_list.csv", bl_head + "\r\n" + bl_row + "\r\n"),
        "premium_gatya": ("premium_gatya.csv", "_row,Index,SlotNumber,ItemCode,ViewSlot,Quantity\r\n0,0,0,30000,0,1\r\n1,1,0,30005,1,1\r\n"),
        "premium_gatya_data": ("premium_gatya_data.csv", "_row,Slot,Price\r\n0,0,690\r\n1,1,690\r\n"),
        "premium6000": ("PremiumShopBin.json", json.dumps([{"_row": 0, "ItemId": 30001, "Category": 2, "Sub1": 2, "Sub2": 9, "NewFlag": 0,
                                                            "GiftCode": 0, "Name": "0"}])),
        "booster15300": ("BoosterShopList.json", json.dumps([{"Order": 0, "ItemCode": 30002}])),
        "npcshop": ("NpcShop.json", json.dumps([{"NpcId": 1, "ItemCodes": [30000], "Name": "1"}])),
        "hidden": ("npc_shop_hidden.csv", "npc,code,name_ru,reason\r\n1,30006,x,y\r\n"),
    }


@contextlib.contextmanager
def sandbox(ldb):
    """Песочница целиком → (stack, env). Восстанавливает всё на выходе."""
    import selftest_shops as T
    from core import config, db
    from domains import shopcs, shopdata as SD
    if SD.SRV_TOOLS not in sys.path:
        sys.path.insert(0, SD.SRV_TOOLS)
    import deploy_premium_boxes as base
    import deploy_changeset as dc
    import stack_layout as SL
    real_load = SD.Client.load
    tmp = tempfile.mkdtemp(prefix="asda_cs_sbx_")
    name = "AsdaAdminSbx_" + secrets.token_hex(4)
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % name)
    cn = ldb(name)
    for f in ("adminc_02_schema.sql", "adminc_13_changeset.sql", "adminc_14_jobs.sql"):   # ★ ревизия 41 В-1: рестарт набора — под adm.job
        text = open(os.path.join(ROOT, "sql", f), encoding="utf-8").read()
        for batch in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I):
            if batch.strip():
                cn.cursor().execute(batch)
    cn.close()
    with T.synthetic() as (raw, _md5s, _cli):
        st = Stack(os.path.join(tmp, "v2"), raw, SL.EXPECT)
        cfg = config.get()
        saved = {"base": {k: getattr(base, k) for k in ("V2", "LOCAL_BACKUP_ROOT", "rmd5", "rbusy", "rcopy", "rupload", "rdel", "rread",
                                                        "MANIFEST", "flush", "check_roots")},
                 "cs": {k: getattr(shopcs, k) for k in ("run_deploy", "_restart", "_bring_up", "stack_counts", "sales_since", "_ue_run",
                                                        "_ue_queue", "CHANGELOG", "SERVER_INDEX", "SERVER_CARDS")},
                 "sd": {k: getattr(SD, k) for k in ("Snap", "live_md5", "CS_DIR", "BACKUP_DIR", "PANEL_TAIL", "HIDDEN_CSV", "spd_dir",
                                                    "releases_after", "SNAPSHOT")},
                 "cf": dict(SD.CLIENT_FILES), "on_server": cfg.on_server, "replace": os.replace}
        # --- стойка: SSH-функции выкладчика → файлы песочницы
        base.V2 = st.root
        base.LOCAL_BACKUP_ROOT = os.path.join(tmp, "local_backup")
        base.rmd5 = lambda p: st.md5(p)
        # ★ ревизия 33 М-3: занятость по пути — exe заняты, пока их процессы работают; файлы таблиц — только если их держат (st.held)
        st.held = set()
        base.rbusy = lambda p: ("BUSY" if (p.endswith(".exe") and any(st.procs.values())) or any(p.endswith(h) for h in st.held)
                                else "FREE")

        def rcopy(src, dst):
            if "rb_copy" in st.fail and ".bak_" in src:
                raise RuntimeError("подставной сбой копии из .bak")
            os.makedirs(os.path.dirname(st.path(dst)), exist_ok=True)
            shutil.copyfile(st.path(src), st.path(dst))

        def rupload(local, remote):
            st.uploads += 1
            if "upload2" in st.fail and st.uploads == 2:
                raise RuntimeError("подставной сбой заливки (второй файл)")
            os.makedirs(os.path.dirname(st.path(remote)), exist_ok=True)
            shutil.copyfile(local, st.path(remote))
        base.rcopy, base.rupload = rcopy, rupload
        base.rdel = lambda p: os.path.isfile(st.path(p)) and os.remove(st.path(p))
        base.rread = lambda p: open(st.path(p), "rb").read()

        def live_md5(rels):
            return {r: st.md5(r) for r in rels}

        class SbxSnap(SD.Snap):
            def __init__(self, md5=None):
                self.md5 = md5 or live_md5(SD.srv_rels())
                self._b = {}

            def raw(self, rel):
                return open(st.path(rel), "rb").read()
        SD.Snap, SD.live_md5 = SbxSnap, live_md5

        def run_deploy(manifest, args=(), mode="", timeout=900):
            old_argv, old_env = sys.argv, {k: os.environ.get(k) for k in ("ASDA_CHANGESET_MANIFEST", "ASDA_CHANGESET_MODE")}
            sys.argv = ["deploy_changeset.py"] + list(args)
            os.environ["ASDA_CHANGESET_MANIFEST"], os.environ["ASDA_CHANGESET_MODE"] = manifest, mode
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    rc = dc.main()
            except RuntimeError as ex:
                rc = 7
                buf.write("ОШИБКА: %s" % ex)
            finally:
                sys.argv = old_argv
                for k, v in old_env.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            return rc, buf.getvalue()

        def restart(manifest, mode, guard=None):
            """Подставной restart_stack: порядок, строки и коды — как у настоящего. guard (ревизия 39 Н-3) — команда перепроверки после
            остановки: здесь та же shopcs.post_stop_guard в процессе (настоящий выкладчик зовёт её отдельным процессом)."""
            st.calls.append("announce")
            if "announce" in st.fail:
                return 2, "СТОП: объявление не отправлено — стойку не трогаю"
            if "parity_pre" in st.fail:
                return 6, "СТОП до остановки: паритета нет — стойка НЕ тронута"
            st.calls.append("stop")
            if "stop" in st.fail:
                st.procs = {k: v for k, v in st.procs.items() if k != "GameServer"}
                return 3, "СТОП: процессы не остановились"
            st.procs = {}
            out = "   все процессы стойки остановлены\n"
            st.calls.append("deploy:" + (mode or "apply"))
            if guard:
                g = guard[guard.index("guard") + 1:]
                why = shopcs.post_stop_guard(int(g[0]), "rollback" if "--rollback" in g else "", "--held-ok" in g)
                st.guards = getattr(st, "guards", []) + [why]
                if why:
                    return 4, out + ("СТОП: %s не прошла — файлы не тронуты: %s\n" % ("перепроверка набора после остановки стойки",
                                                                                   "; ".join(why))) + "СТОП: выкладка не прошла — стойка ОСТАНОВЛЕНА"
            rc, o = run_deploy(manifest, ["--apply"], mode)
            out += o
            if "foreign" in st.fail:                     # чужая правка файла набора посреди выкладки (ревизия 32 М-2)
                rel = sorted(json.load(open(manifest, encoding="utf-8"))["files"])[-1]
                open(st.path(rel), "ab").write(b"#foreign")
            if rc != 0 or "ГОТОВО" not in o:
                return 4, out + "\nСТОП: выкладка не прошла — стойка ОСТАНОВЛЕНА"
            if "start" in st.fail:
                return 6, out + "\nСТОП: СУЩЕСТВЕННОЕ расхождение — стойка ОСТАНОВЛЕНА"
            st.calls.append("start")
            st.procs = dict(st.expect)
            if "start_partial" in st.fail:
                st.procs.pop("RelayServer", None)
                return 5, out + "\nпроцессы НЕ ВСЕ"
            if "after_start" in st.fail:
                return 5, out + "\nPatchLog не прочитан"
            if "ssh_after" in st.fail:
                st.ssh_down = True
            return 0, out

        def bring_up():
            st.calls.append("bring_up")
            if any(st.procs.values()):
                return 7, "СТОП (--start-only): процессы стойки работают"
            if "bring_up" in st.fail:
                return 1, "подставной сбой подъёма"
            st.procs = dict(st.expect)
            return 0, "стойка запущена"
        shopcs.run_deploy, shopcs._restart, shopcs._bring_up = run_deploy, restart, bring_up
        shopcs.stack_counts = lambda: None if st.ssh_down else dict(st.procs)
        shopcs.sales_since = lambda cs: st.sales
        # --- записи: временные копии
        docs = os.path.join(tmp, "docs")
        os.makedirs(os.path.join(docs, "_Common"))
        shopcs.CHANGELOG = os.path.join(docs, "CHANGELOG_2026-11-16.md")
        open(shopcs.CHANGELOG, "w", encoding="utf-8").write("# changelog\n")
        shopcs.SERVER_INDEX = os.path.join(docs, "INDEX.md")
        open(shopcs.SERVER_INDEX, "w", encoding="utf-8").write("# INDEX\n\n## Сводная таблица\n\n| Процесс | Патч |\n|---|---|\n| a | b |\n\n"
                                                                "## Хеши бинарей (для сверки, MD5)\n| x |\n")
        shopcs.SERVER_CARDS = os.path.join(docs, "_Common")
        SD.CS_DIR, SD.BACKUP_DIR = os.path.join(tmp, "changesets"), os.path.join(tmp, "backup")
        # --- клиент: копии ВСЕХ таблиц порта, НАСТОЯЩИЙ Client.load
        cdir = os.path.join(tmp, "port")
        os.makedirs(os.path.join(cdir, "Shop"))
        files = _client_files(cdir)
        for k, (fn, txt) in files.items():
            pth = os.path.join(cdir, fn)
            open(pth, "w", encoding="utf-8", newline="").write(txt)
            SD.CLIENT_FILES[k] = pth
        open(os.path.join(cdir, "Shop", "js1.spd"), "wb").write(struct.pack("<II", 0, 2) + struct.pack("<2I", 30000, 30006))
        SD.PANEL_TAIL, SD.HIDDEN_CSV = os.path.join(cdir, "PremiumShopBin_tail_panel.json"), SD.CLIENT_FILES["hidden"]
        SD.spd_dir = lambda: os.path.join(cdir, "Shop")
        SD.Client.load = real_load
        SD.SNAPSHOT = os.path.join(tmp, "shop_client.json")        # снимок для режима «служба на сервере» (dry_srv)
        json.dump(SD.build_client_snapshot(), open(SD.SNAPSHOT, "w", encoding="utf-8"))
        st.assets = {SD.DT[k]: open(SD.CLIENT_FILES[k], "rb").read() for k in SD.DT if os.path.isfile(SD.CLIENT_FILES[k])}
        st.imports = []

        def ue_run(script, log, marker, env=None, expect=None, require=None):
            if script == "asda_ml_dt_point.py":
                jobs = json.load(open(env["ASDA_PT_JOBS"], encoding="utf-8"))
                for j in jobs:
                    if "dt:" + j["dt"].rsplit("/", 1)[1] in st.fail:
                        return 1, "подставной сбой DT"
                    stop = st.assets.get(j["dt"]) != open(j["csv_old"], "rb").read()
                    if env.get("ASDA_PT_DRYRUN"):
                        continue                         # как настоящий: сухой прогон с СТОП — код 0 (ловит запись)
                    if stop:
                        return 1, "СТОП: ассет расходится с прежним CSV — ассет не сохранён (--expect-asset)"
                    st.assets[j["dt"]] = open(j["csv_new"], "rb").read()
                return 0, "ЗАВЕРШЕНО: точечные DT"
            st.imports.append(script)
            if "imp:" + script in st.fail:
                return 1, "подставной сбой импортёра"
            if script == "asda_import_npc_shop.py":         # пересборка NpcShop.json: .spd минус ведомость скрытых
                rawspd = open(os.path.join(cdir, "Shop", "js1.spd"), "rb").read()
                codes = list(struct.unpack_from("<%dI" % struct.unpack_from("<I", rawspd, 4)[0], rawspd, 8))
                hid = {int(r.split(",")[1]) for r in open(SD.CLIENT_FILES["hidden"], encoding="utf-8-sig").read().splitlines()[1:] if r}
                json.dump([{"NpcId": 1, "ItemCodes": [c for c in codes if c not in hid], "Name": "1"}],
                          open(SD.CLIENT_FILES["npcshop"], "w", encoding="utf-8"))
            if script == "asda_import_premium_shop_bin.py":
                base6 = json.loads(files["premium6000"][1])
                tail = json.load(open(SD.PANEL_TAIL, encoding="utf-8"))["rows"] if os.path.isfile(SD.PANEL_TAIL) else []
                json.dump(base6 + [dict(r, GiftCode=0) for r in tail], open(SD.CLIENT_FILES["premium6000"], "w", encoding="utf-8"))
            return 0, marker + " (ok)"

        class Q:
            class Slot:
                def __init__(self, kind, what, **kw):
                    st.calls.append("ue_queue:" + kind)

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False
        shopcs._ue_run, shopcs._ue_queue = ue_run, (lambda: Q)
        SD.releases_after = lambda stamp: {"at": "2026-11-20 10:00:00", "version": "alpha-8.2.0-selftest"} if st.released else None
        db.set_override("admin", lambda database: ldb(name))
        cfg.on_server = False
        try:
            yield st, {"tmp": tmp, "files": files, "cdir": cdir}
        finally:
            os.replace = saved["replace"]
            for k, v in saved["base"].items():
                setattr(base, k, v)
            for k, v in saved["cs"].items():
                setattr(shopcs, k, v)
            for k, v in saved["sd"].items():
                setattr(SD, k, v)
            SD.CLIENT_FILES.clear()
            SD.CLIENT_FILES.update(saved["cf"])
            cfg.on_server = saved["on_server"]
            db.set_override("admin", None)
            try:
                m.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [%s]" % (name, name))
            except Exception:
                pass
            m.close()
            shutil.rmtree(tmp, ignore_errors=True)


def _run(ctx, name, **p):
    from core import ops
    return ops.run(ctx, name, p)


def _try(ctx, name, **p):
    from core import ops
    try:
        return ops.run(ctx, name, p), None
    except ops.OpRefused as ex:
        return None, str(ex)


def _new_set(ctx, items, urgent=False, dry=True):
    """Набор → проверен → утверждён → (сухой прогон сервера: ПК, настоящий deploy_changeset в песочнице) → id."""
    from domains import shopcs
    cid = _run(ctx, "shop.cs_create", title="ПЕСОЧНИЦА", note="самотест песочницы: путь применения и отката", urgent=urgent)["result"]["id"]
    for kind, prm in items:
        _run(ctx, "shop.cs_item_add", cs=cid, kind=kind, params=prm)
    _run(ctx, "shop.cs_check", cs=cid)
    cs = shopcs.get(cid)
    if cs["status"] != "checked":
        raise AssertionError("набор не прошёл проверку: %s" % (cs["check"] or {}).get("errors"))
    _run(ctx, "shop.cs_approve", cs=cid)
    if dry and cs["check"]["server_needed"]:
        _run(ctx, "shop.cs_server_dry", cs=cid)
    return cid


SRV_ITEMS = [("gacha.price", {"slot": 0, "value": 700}), ("package.set", {"row": 0, "pairs": [[30000, 7]]})]


def _files_state(st, cid):
    from domains import shopcs
    man = json.load(open(shopcs.manifest_path(cid), encoding="utf-8"))
    return {("new" if st.md5(r) == f["new"] else "base" if st.md5(r) == f["base"] else "other") for r, f in man["files"].items()}


def _cmd5(env):
    from domains import shopdata as SD
    out = {k: _md5(p) for k, p in SD.CLIENT_FILES.items() if os.path.isfile(p)}
    out["spd"] = _md5(os.path.join(env["cdir"], "Shop", "js1.spd"))
    return out


def _reset_client(st, env):
    from domains import shopdata as SD
    for k, (fn, txt) in env["files"].items():
        open(SD.CLIENT_FILES[k], "w", encoding="utf-8", newline="").write(txt)
    open(os.path.join(env["cdir"], "Shop", "js1.spd"), "wb").write(struct.pack("<II", 0, 2) + struct.pack("<2I", 30000, 30006))
    if os.path.isfile(SD.PANEL_TAIL):
        os.remove(SD.PANEL_TAIL)
    for sub in ("_value_overlay", "_tail_append"):        # ★ А4.0: ведомости ItemDB песочницы — к исходному (пустые)
        d = os.path.join(SD.LEDGER_ROOT, sub)
        for fn in os.listdir(d) if os.path.isdir(d) else []:
            os.remove(os.path.join(d, fn))
    st.assets = {SD.DT[k]: open(SD.CLIENT_FILES[k], "rb").read() for k in SD.DT if os.path.isfile(SD.CLIENT_FILES[k])}


def _real_port_md5():
    """md5 НАСТОЯЩИХ клиентских файлов порта (до и после песочницы) — их песочница трогать не должна."""
    from domains import shopdata as SD
    out = {k: _md5(p) for k, p in SD.CLIENT_FILES.items() if os.path.isfile(p)}
    out.update({p: _md5(p) for p in SD.all_ledger_paths() if os.path.isfile(p)})      # ★ А4.0: и ведомости ItemDB порта
    return out


def run(check, ldb):
    """Все сценарии песочницы."""
    from core import ops
    from domains import shopcs, shopdata as SD
    real_before = _real_port_md5()
    _start_only_stand(check)
    _zone_checks(check)
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with sandbox(ldb) as (st, env):
        f0 = _cmd5(env)
        # 1. В-1: клиент не выпущен — без ключа отказ; с ключом — выложено; бэкапы; записи
        cid = _new_set(ctx, SRV_ITEMS)
        r1, e1 = _try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart")
        calls0 = list(st.calls)
        r2, e2 = _try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
        cs = shopcs.get(cid)
        bak_ok = all(os.path.isfile(st.path(r + ".bak_" + cs["server_tag"]))
                     for r in json.load(open(shopcs.manifest_path(cid), encoding="utf-8"))["files"])
        idx = open(shopcs.SERVER_INDEX, encoding="utf-8").read()
        check("песочница: сервер раньше выпуска без --unsynced-ok — отказ ДО объявления; с ключом — объявление → остановка → выкладка → "
              "старт, файлы = новые, .bak_<метка>, applied (В-1)", e1 and "--unsynced-ok" in e1 and calls0 == [] and r2
              and st.calls == ["announce", "stop", "deploy:apply", "start"] and _files_state(st, cid) == {"new"} and bak_ok
              and cs["server_state"] == "applied" and cs["status"] == "applied_server", (e1, e2, st.calls, cs["server_state"]))
        check("песочница: записи — строка «Сводной таблицы» INDEX, карточка admin-changeset-№, changelog (вехи), причина = поле набора",
              idx.index("Набор изменений админ-центра №%d" % cid) < idx.index("## Хеши бинарей") and os.path.isfile(shopcs.card_path(cs))
              and "Причина: самотест песочницы" in open(shopcs.CHANGELOG, encoding="utf-8").read())
        # 2. откат после продаж (премиум и лавки) → второе подтверждение
        st.calls.clear()
        st.sales = {"gp7": 0, "npc": 2}
        e3 = _try(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart")[1]
        r4, e4 = _try(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart", irreversible_ok=True)
        cs = shopcs.get(cid)
        check("песочница: продажи в лавках NPC после выкладки — откат без --irreversible-ok отказ ДО объявления (К-4); с ним — база, "
              "rolled_back, записи отката", e3 and "лавки NPC 2" in e3 and r4 and _files_state(st, cid) == {"base"}
              and cs["server_state"] == "rolled_back" and st.calls == ["announce", "stop", "deploy:rollback", "start"], (e3, e4, st.calls))
        st.sales = {"gp7": 0, "npc": 0}
        st.calls.clear()
        e5 = _try(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart")[1]
        check("песочница: повторный откат — переход закрыт ДО объявления", e5 and st.calls == [], e5)
        # 3. без серверной половины
        cid2 = _new_set(ctx, [("npcshop.hide", {"npc": 1, "code": 30000, "reason": "песочница"})])
        st.calls.clear()
        d1 = _try(ctx, "shop.cs_server_dry", cs=cid2)[1]
        a1 = _try(ctx, "shop.cs_server_apply", cs=cid2, confirm="restart", unsynced_ok=True)[1]
        check("песочница: нет серверной половины — server-dry и server-apply отказывают, объявления нет (В-3)", d1 and a1 and st.calls == [])
        _run(ctx, "shop.cs_cancel", cs=cid2)
        # 4. сбои на каждом шаге рестарта
        cases = (
            # точка сбоя, процессы ДО, ждём состояние, файлы, вызовы, стойка работает после
            ("announce", None, "dry_ok", {"base"}, ["announce"], True),
            ("parity_pre", None, "dry_ok", {"base"}, ["announce"], True),
            ("upload2", None, "dry_ok", {"base"}, ["announce", "stop", "deploy:apply", "bring_up"], True),     # Н-М2: частичная → база → подъём
            ("start", None, "applied", {"new"}, ["announce", "stop", "deploy:apply", "bring_up"], True),
            ("after_start", None, "applied", {"new"}, ["announce", "stop", "deploy:apply", "start"], True),
            ("stop", None, "dry_ok", {"base"}, ["announce", "stop"], False),                                   # Н-В2: стоп не завершён — не трогаем
            ("start_partial", None, "applied", {"new"}, ["announce", "stop", "deploy:apply", "start"], False),  # Н-М4
            ("announce", "GameServer", "dry_ok", {"base"}, ["announce"], False),                               # Н-В2: стойка была неполной
            ("announce", "ALL", "dry_ok", {"base"}, ["announce"], False))                                      # Н-В2: стойка лежала не нами
        for fail, pre, want_state, want_files, want_calls, up in cases:
            c = _new_set(ctx, SRV_ITEMS)
            st.calls.clear()
            st.fail, st.uploads = {fail}, 0
            st.procs = dict(st.expect)
            if pre == "GameServer":
                st.procs.pop("GameServer")
            elif pre == "ALL":
                st.procs = {}
            res, err = _try(ctx, "shop.cs_server_apply", cs=c, confirm="restart", unsynced_ok=True)
            cs = shopcs.get(c)
            check("песочница: сбой «%s»%s — состояние по md5 (%s), подъём только после своей остановки, процессы %s" % (
                  fail, " (стойка до: без %s)" % pre if pre else "", want_state, "все" if up else "не все"),
                  cs["server_state"] == want_state and _files_state(st, c) == want_files and st.calls == want_calls and st.running is up,
                  (fail, cs["server_state"], _files_state(st, c), st.calls, err, cs["server_note"]))
            st.fail = set()
            st.procs = dict(st.expect)
            if cs["server_state"] == "applied":
                _run(ctx, "shop.cs_server_rollback", cs=c, confirm="restart")
            else:
                _run(ctx, "shop.cs_cancel", cs=c)
        # 4б. Н-М2: частичная выкладка, откат частичного не прошёл — стойка НЕ поднимается
        c = _new_set(ctx, SRV_ITEMS)
        st.calls.clear()
        st.fail, st.uploads = {"upload2", "rb_copy"}, 0
        _try(ctx, "shop.cs_server_apply", cs=c, confirm="restart", unsynced_ok=True)
        cs = shopcs.get(c)
        check("песочница: частичная выкладка, довести до базы не вышло — partial_apply, стойка остановлена, без запуска (Н-М2)",
              cs["server_state"] == "partial_apply" and not st.procs and "bring_up" not in st.calls, (cs["server_state"], st.calls))
        st.fail = set()
        st.calls.clear()
        _run(ctx, "shop.cs_server_apply", cs=c, confirm="restart", unsynced_ok=True)
        cs = shopcs.get(c)
        check("песочница: повтор частичной выкладки (владелец) — applied, стойка работает", cs["server_state"] == "applied" and st.running,
              (cs["server_state"], st.calls))
        _run(ctx, "shop.cs_server_rollback", cs=c, confirm="restart")
        # 4в. ревизия 32 М-2: частичная выкладка + чужой файл — не доводить и НЕ поднимать
        c = _new_set(ctx, SRV_ITEMS)
        st.calls.clear()
        st.fail, st.uploads = {"upload2", "foreign"}, 0
        e_f = _try(ctx, "shop.cs_server_apply", cs=c, confirm="restart", unsynced_ok=True)[1]
        cs = shopcs.get(c)
        check("песочница: частичная выкладка с чужим файлом — стойка НЕ поднимается, partial_apply, сообщение владельцу (ревизия 32 М-2)",
              cs["server_state"] == "partial_apply" and not st.procs and "bring_up" not in st.calls and "чужие" in (cs["server_note"] or ""),
              (cs["server_state"], st.calls, cs["server_note"], e_f))
        st.fail = set()
        man = json.load(open(shopcs.manifest_path(c), encoding="utf-8"))
        for rel, f in man["files"].items():                # владелец вернул базу руками
            bak = st.path(rel + ".bak_" + man["tag"])
            data = open(st.path(rel), "rb").read()
            if data.endswith(b"#foreign"):
                open(st.path(rel), "wb").write(data[:-len(b"#foreign")])
            if os.path.isfile(bak) and st.md5(rel) == f["new"]:
                shutil.copyfile(bak, st.path(rel))
        st.procs = dict(st.expect)
        _run(ctx, "shop.cs_server_sync", cs=c)
        # 4г. ревизия 32 К-4: частичная доведена до базы — текст «стойка перезапущена, набор возвращён к базе»
        c = _new_set(ctx, SRV_ITEMS)
        st.fail, st.uploads = {"upload2"}, 0
        e_k4 = _try(ctx, "shop.cs_server_apply", cs=c, confirm="restart", unsynced_ok=True)[1]
        st.fail = set()
        check("песочница: частичная выкладка доведена до базы — «стойка перезапущена, набор возвращён к базе» (ревизия 32 К-4)",
              e_k4 and e_k4.startswith("стойка перезапущена, набор возвращён к базе"), e_k4)
        _run(ctx, "shop.cs_cancel", cs=c)
        # 5. Н-М3: SSH пропал после рестарта → unknown → server-sync
        c = _new_set(ctx, SRV_ITEMS)
        st.fail = {"ssh_after"}
        _try(ctx, "shop.cs_server_apply", cs=c, confirm="restart", unsynced_ok=True)
        cs = shopcs.get(c)
        st.fail, st.ssh_down = set(), False
        r6 = _run(ctx, "shop.cs_server_sync", cs=c)
        cs2 = shopcs.get(c)
        check("песочница: SSH пропал после рестарта — unknown, без автодействий; server-sync по md5 — applied (Н-М3)",
              cs["server_state"] == "unknown" and cs2["server_state"] == "applied", (cs["server_state"], cs2["server_state"]))
        _run(ctx, "shop.cs_server_rollback", cs=c, confirm="restart")
        # 6. чужой файл перед откатом
        c = _new_set(ctx, SRV_ITEMS)
        _run(ctx, "shop.cs_server_apply", cs=c, confirm="restart", unsynced_ok=True)
        victim = sorted(json.load(open(shopcs.manifest_path(c), encoding="utf-8"))["files"])[0]
        keep = open(st.path(victim), "rb").read()
        open(st.path(victim), "ab").write(b"x")
        st.calls.clear()
        e6 = _try(ctx, "shop.cs_server_rollback", cs=c, confirm="restart")[1]
        check("песочница: на стойке чужой файл — откат отказывает ДО объявления (М-8)", e6 and "чужие" in e6 and st.calls == [], e6)
        open(st.path(victim), "wb").write(keep)
        _run(ctx, "shop.cs_server_rollback", cs=c, confirm="restart")
        # 7. dry_srv
        from core import config
        c = _new_set(ctx, SRV_ITEMS, dry=False)
        config.get().on_server = True
        try:
            _run(ctx, "shop.cs_server_dry", cs=c)
        finally:
            config.get().on_server = False
        e7 = _try(ctx, "shop.cs_server_apply", cs=c, confirm="restart", unsynced_ok=True)[1]
        check("песочница: служба ставит dry_srv; server-apply требует сухой прогон ПК (М-6)", shopcs.get(c)["server_state"] == "dry_srv"
              and e7 and "dry_srv" in e7, e7)
        _run(ctx, "shop.cs_cancel", cs=c)
        # 8. Н-В1: клиент → выпуск → сервер, клиентские таблицы РЕАЛЬНО меняются первой половиной
        items = SRV_ITEMS + [("price", {"code": 30001, "value": 600}), ("npcshop.hide", {"npc": 1, "code": 30000, "reason": "песочница"}),
                             ("shop6000.add", {"code": 30003, "cat": 2, "sub1": 2, "sub2": 9, "newflag": 1})]
        _reset_client(st, env)
        c = _new_set(ctx, items + [("sell.allow", {"code": 30000})])
        _run(ctx, "shop.cs_client_dry", cs=c)
        st.calls.clear()
        _run(ctx, "shop.cs_client_apply", cs=c)
        cli_now = SD.Client.load()
        changed_d = (cli_now.price(30001), cli_now.npc[1]["shown"], sorted(cli_now.p6000), sorted(st.imports),
                     open(SD.CLIENT_FILES["item_list"], encoding="utf-8").read().splitlines()[2][:30], shopcs.get(c)["client_state"],
                     len(shopcs.get(c)["check"]["client"]))
        changed = cli_now.price(30001) == 600 and 30000 not in cli_now.npc[1]["shown"] and 30003 in cli_now.p6000
        e8 = _try(ctx, "shop.cs_released", cs=c)[1]
        st.released = True
        r9 = _run(ctx, "shop.cs_released", cs=c)
        st.calls.clear()
        r10, e10 = _try(ctx, "shop.cs_server_apply", cs=c, confirm="restart")
        cs = shopcs.get(c)
        check("песочница: клиент → выпуск → сервер: таблицы клиента реально изменились (цена 600, лавка, витрина 6000), сервер после "
              "выпуска без --unsynced-ok — applied (Н-В1, В-2)", changed and e8 and r9 and "server-apply" in r9["message"] and r10
              and cs["status"] == "released" and cs["server_state"] == "applied", (changed_d, e8, e10, cs["status"], cs["server_state"]))
        _run(ctx, "shop.cs_server_rollback", cs=c, confirm="restart")
        cs = shopcs.get(c)
        e11 = _try(ctx, "shop.cs_client_rollback", cs=c)[1]
        check("песочница: откат сервера выпущенного набора — статус released (М-9); откат клиента после выпуска — отказ",
              cs["status"] == "released" and cs["server_state"] == "rolled_back" and e11, (cs["status"], e11))
        # 8б. клиент применён, сухой прогон сервера ПОСЛЕ клиента; выпущенный набор без сервера — отмена серверной половины
        _reset_client(st, env)
        c = _new_set(ctx, items, dry=False)
        _run(ctx, "shop.cs_client_dry", cs=c)
        _run(ctx, "shop.cs_client_apply", cs=c)
        r12, e12 = _try(ctx, "shop.cs_server_dry", cs=c)
        st.released = True
        _run(ctx, "shop.cs_released", cs=c)
        r13, e13 = _try(ctx, "shop.cs_cancel", cs=c)
        cs = shopcs.get(c)
        check("песочница: сухой прогон сервера после применённого клиента — проходит (сверка только серверной части); выпущенный набор — "
              "отмена невыложенной серверной половины (Н-В1)", r12 and r13 and cs["status"] == "released" and cs["server_state"] == "rolled_back",
              (e12, e13, cs["server_state"]))
        # 8в. сервер (--unsynced-ok) → клиент
        _reset_client(st, env)
        st.released = False
        c = _new_set(ctx, items)
        _run(ctx, "shop.cs_server_apply", cs=c, confirm="restart", unsynced_ok=True)
        r14, e14 = _try(ctx, "shop.cs_client_dry", cs=c)
        r15, e15 = _try(ctx, "shop.cs_client_apply", cs=c)
        cs = shopcs.get(c)
        check("песочница: сервер (--unsynced-ok) → клиент: таблицы стойки уже новые, клиентская половина применяется (Н-В1)",
              r14 and r15 and cs["client_state"] == "applied" and cs["server_state"] == "applied", (e14, e15))
        _run(ctx, "shop.cs_client_rollback", cs=c)
        _run(ctx, "shop.cs_server_rollback", cs=c, confirm="restart")
        f_after = _cmd5(env)
        check("песочница: откат обеих половин — порт как до применения (все файлы, включая NpcShop.json и витрину 6000)",
              f_after == {k: v for k, v in f0.items()} and not os.path.isfile(SD.PANEL_TAIL), sorted(k for k in f0 if f0[k] != f_after.get(k)))
        # 9. Н-М1: сбой записи ПЕРВОГО файла; откат — без «нет бэкапа»
        _reset_client(st, env)
        a0 = dict(st.assets)
        c = _new_set(ctx, [("price", {"code": 30001, "value": 650}), ("gacha.price", {"slot": 1, "value": 777})])
        _run(ctx, "shop.cs_client_dry", cs=c)
        real_replace = os.replace

        def bad_replace(a, b):
            if a.endswith(".cs_tmp"):
                raise OSError("подставной сбой записи")
            return real_replace(a, b)
        os.replace = bad_replace
        try:
            e16 = _try(ctx, "shop.cs_client_apply", cs=c)[1]
        finally:
            os.replace = real_replace
        cs = shopcs.get(c)
        tmp_left = [x for x in os.listdir(env["cdir"]) if x.endswith(".cs_tmp")]
        r17, e17 = _try(ctx, "shop.cs_client_rollback", cs=c)
        check("песочница: сбой записи первого файла — applying, .cs_tmp убран, бэкап всех файлов до записи; откат — rolled_back (Н-М1)",
              e16 and cs["client_state"] == "applying" and not tmp_left and r17 and _cmd5(env) == f0 and st.assets == a0, (e16, e17, tmp_left))
        # 10. Н-В4: откат клиента сорвался на DT, повтор — проходит
        _reset_client(st, env)
        c = _new_set(ctx, [("price", {"code": 30001, "value": 660}), ("gacha.price", {"slot": 1, "value": 778})])
        _run(ctx, "shop.cs_client_dry", cs=c)
        _run(ctx, "shop.cs_client_apply", cs=c)
        st.fail = {"dt:DT_item_list"}
        e18 = _try(ctx, "shop.cs_client_rollback", cs=c)[1]
        st.fail = set()
        r19, e19 = _try(ctx, "shop.cs_client_rollback", cs=c)
        check("песочница: откат клиента сорвался на DT — повтор возвращает и файлы, и DT (копия applied/ не портится, Н-В4)",
              e18 and r19 and _cmd5(env) == f0 and st.assets == a0 and shopcs.get(c)["client_state"] == "rolled_back", (e18, e19))
        # 11. частичная заливка DT при применении → откат
        c = _new_set(ctx, [("price", {"code": 30001, "value": 670}), ("gacha.price", {"slot": 1, "value": 779})])
        _run(ctx, "shop.cs_client_dry", cs=c)
        st.fail = {"dt:DT_premium_gatya_data"}
        _try(ctx, "shop.cs_client_apply", cs=c)
        st.fail = set()
        r20, e20 = _try(ctx, "shop.cs_client_rollback", cs=c)
        check("песочница: DT залит частично — откат возвращает залитый, незалитый «уже прежний»", r20 and _cmd5(env) == f0 and st.assets == a0, e20)
        # 12. таблица переходов
        c = _run(ctx, "shop.cs_create", title="переходы", note="переходы песочницы")["result"]["id"]
        _run(ctx, "shop.cs_item_add", cs=c, kind="gacha.price", params={"slot": 0, "value": 701})
        bad = [op_name for op_name in ("shop.cs_approve", "shop.cs_server_dry", "shop.cs_server_apply", "shop.cs_server_rollback",
                                       "shop.cs_server_sync", "shop.cs_client_dry", "shop.cs_client_apply", "shop.cs_client_rollback",
                                       "shop.cs_released", "shop.cs_reopen")
               if _try(ctx, op_name, cs=c, confirm="restart", unsynced_ok=True)[1] is None]
        _run(ctx, "shop.cs_cancel", cs=c)
        bad += ["отменённый:" + op_name for op_name in ("shop.cs_item_add", "shop.cs_check", "shop.cs_cancel", "shop.cs_server_apply", "shop.cs_reopen")
                if _try(ctx, op_name, cs=c, kind="gacha.price", params={"slot": 0, "value": 1}, confirm="restart", unsynced_ok=True)[1] is None]
        c2 = _run(ctx, "shop.cs_create", title="без причины")["result"]["id"]
        _run(ctx, "shop.cs_item_add", cs=c2, kind="gacha.price", params={"slot": 0, "value": 702})
        _run(ctx, "shop.cs_check", cs=c2)
        no_reason = _try(ctx, "shop.cs_approve", cs=c2)[1]
        check("песочница: таблица переходов — шаг вне своего статуса отказывает; утвердить без причины нельзя (К-3)", not bad and no_reason,
              (bad, no_reason))
    real_after = _real_port_md5()
    check("песочница: настоящие клиентские файлы порта не тронуты (md5 до = после всех сценариев)", real_before == real_after and real_before,
          sorted(k for k in real_before if real_before[k] != real_after.get(k)))


def _zone_checks(check):
    """Н-В3: метки времени — UTC; выпуск из releases.log с поясом сравнивается с UTC; продажи — по UTC."""
    from core import db
    from domains import shopcs, shopdata as SD
    stamp = datetime.datetime(2026, 11, 19, 12, 30, 0)                  # UTC
    d = tempfile.mkdtemp(prefix="asda_cs_tz_")
    saved = SD.RELEASES_LOG
    try:
        SD.RELEASES_LOG = os.path.join(d, "releases.log")
        open(SD.RELEASES_LOG, "w", encoding="utf-8").write(
            "2026-11-19T15:25:00+03:00\talpha-a\tseq=1\n2026-11-19T15:35:00+03:00\talpha-b\tseq=2\n")
        r = SD.releases_after(stamp)
        ok_rel = r and r["version"] == "alpha-b" and r["at"] == "2026-11-19 12:35:00"
    finally:
        SD.RELEASES_LOG = saved
        shutil.rmtree(d, ignore_errors=True)
    now = SD.utc_now()
    off = abs((datetime.datetime.now() - datetime.datetime.utcnow()).total_seconds())
    ok_now = abs((now - datetime.datetime.utcnow()).total_seconds()) < 5
    seen = []

    class FakeReader:
        def __init__(self, key):
            self.key = key

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def one(self, sql, params=()):
            seen.append((self.key, sql, params))
            return {"m": 180, "n": 1}

        def rows(self, sql, params=()):
            return [{"x": 1}]
    saved_r = db.GameReader
    db.GameReader = FakeReader
    try:
        n = shopcs.sales_since({"check": {"sale_codes": [30001]}, "server_at": stamp})
    finally:
        db.GameReader = saved_r
    gp = [x for x in seen if "GP7PurchaseLog" in x[1]]
    npc = [x for x in seen if "BuyNPC" in x[1]]
    check("пояс времени (Н-В3): выпуск «15:35+03:00» позже выкладки 12:30 UTC, «15:25+03:00» — нет; utc_now = UTC (местный сдвиг %d мин); "
          "продажи премиума — с той же UTC-меткой, лавок NPC — окно с запасом (не позже метки)" % (off // 60),
          ok_rel and ok_now and gp and gp[0][2] == (stamp,) and npc and all(x[2][0] <= stamp for x in npc) and n == {"gp7": 1, "npc": 4},
          (r, gp[:1], npc[:1], n))


def _start_only_stand(check):
    """Настоящий restart_stack.py --start-only с подменёнными шагами (SSH, подпроцессы, ожидания): при живом процессе и при
    сбое SSH — код 7 без единой остановки/объявления; при пустой стойке — ни объявления, ни остановки, ни выкладки, только старт."""
    from domains import shopdata as SD
    if SD.SRV_TOOLS not in sys.path:
        sys.path.insert(0, SD.SRV_TOOLS)
    import restart_stack as RS
    calls = []
    state = {"procs": {"GameServer": 1}, "ssh_ok": True}

    def ssh_ps(cmd, timeout=180):
        calls.append(cmd[:40])
        if not state["ssh_ok"]:
            return 255, "ssh: connect failed"
        if "Measure-Object).Count" in cmd:
            return 0, str(sum(state["procs"].values()))
        if "Group-Object ProcessName" in cmd:
            # ★ ревизия 41 Н-4: команда counts() сама печатает метку «счёт прочитан» (Write-Output) — подмена отвечает так же
            mark = getattr(RS, "COUNTS_MARK", "")
            return 0, "\n".join("%s=%d" % kv for kv in state["procs"].items()) + (("\n" + mark) if mark and mark in cmd else "")
        if "schtasks /Create" in cmd:
            calls.append("START")
            state["procs"] = {k: v for k, v in RS.EXPECT.items()}
        return 0, "OK"

    class P:
        returncode, stdout, stderr = 0, b"", b""

    def fake_run(argv, **kw):
        calls.append("RUN " + os.path.basename(argv[1]) if len(argv) > 1 else "RUN")
        return P()
    saved = {k: getattr(RS, k) for k in ("ssh_ps", "firewall_missing", "critical_sizes", "stop_all", "graceful_stop")}
    import subprocess as _sp
    import time as _t
    import patchlog
    saved_run, saved_sleep, saved_pl, saved_argv = _sp.run, _t.sleep, patchlog.check_folder, sys.argv
    RS.ssh_ps = ssh_ps
    RS.firewall_missing = lambda: []
    RS.critical_sizes = lambda: {k: "100" for k in RS.CRITICAL_FILES}
    RS.stop_all = lambda: calls.append("STOP_ALL")
    RS.graceful_stop = lambda: calls.append("GRACEFUL")
    _sp.run, _t.sleep = fake_run, (lambda s: None)
    patchlog.check_folder = lambda d, exp, log=None: (True, {})
    out = io.StringIO()
    try:
        sys.argv = ["restart_stack.py", "--start-only"]
        with contextlib.redirect_stdout(out):
            rc_busy = RS.main()
            busy_calls = list(calls)
            calls.clear()
            state["ssh_ok"] = False
            rc_ssh = RS.main()
            ssh_calls = list(calls)
            calls.clear()
            state.update(ssh_ok=True, procs={})
            sys.argv = ["restart_stack.py", "--start-only", "--deploy", "deploy_changeset.py"]
            rc_dep = RS.main()
            dep_calls = list(calls)
            calls.clear()
            sys.argv = ["restart_stack.py", "--start-only"]
            rc_ok = RS.main()
    finally:
        for k, v in saved.items():
            setattr(RS, k, v)
        _sp.run, _t.sleep, patchlog.check_folder, sys.argv = saved_run, saved_sleep, saved_pl, saved_argv
    no_stop = lambda cl: not any(x in ("STOP_ALL", "GRACEFUL") or "announce" in x for x in cl)
    check("restart_stack.py --start-only (настоящий, шаги подменены): процесс работает — код 7, ничего не останавливает; SSH не ответил — "
          "код 7; пустая стойка — без объявления/остановки/выкладки, старт и паритет --sync (Н-В2, Н-М2)",
          rc_busy == 7 and no_stop(busy_calls) and "START" not in busy_calls and rc_ssh == 7 and "START" not in ssh_calls
          and rc_ok == 0 and "START" in calls and no_stop(calls) and not any("deploy" in x for x in calls)
          and any("stack_parity" in x for x in calls) and rc_dep == 1 and not dep_calls, (rc_busy, rc_ssh, rc_dep, rc_ok, calls[:12]))
