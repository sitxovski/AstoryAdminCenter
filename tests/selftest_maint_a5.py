# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_maint_a5.py — самотест шага А5.3 «Режим обслуживания» (21.11.2026; domains/maint.py, SQL L09, LoginPatch L09).

offline(check)       — на подменах: операции maint.on / maint.off (права, подтверждение, объявление или явное «без объявления», отключение
                       игроков только по выбору, «не прочитано» ≠ «нет», SQL L09 не применён — отказ, второй фактор из браузера,
                       перепроверка перед записью, проверка после), задания (job.add с вторым фактором, список операций заданий),
                       состояние DLL по журналу патчей, консоль (ключи, справка), переводы EN, веб (без innerHTML), SQL-права панели,
                       исходники DLL L09 и выкладчика, тексты отказов без «; ».
sandbox(check, ldb)  — СТЕНД SQL L09 на своём экземпляре LocalDB (AsdaL09Stand: базы Joy1 / AsdaStoryOP / JoyLog1 с теми же именами,
                       что у живой стойки, — врезка ставится по md5 живого тела): тело UPUserLogin из живого текста (md5 C19F6E7C…),
                       l09_01_migrate дважды, отказ на чужом теле, l09_10_smoke (все ветки входа), права как у asda_ops / asda_admin,
                       операции панели на настоящей процедуре (сразу и заданием службы), откат l09_99_rollback байт в байт и повтор.
live(check)          — только чтение: состояние SQL L09 на живой Joy1 (таблицы нет — честный отказ maint.on «не применена»), права
                       asda_admin (VIEW DEFINITION на UPUserLogin), журнал патчей LoginManager (L09 не действует — живая DLL v10),
                       кто в игре по мосту; сухие предпросмотры. Режим НЕ включается. Побочных эффектов при импорте нет.
"""
import json
import os
import re
import secrets
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
SQLDIR = os.path.join(PORT, "AstoryServer", "Docs", "SQL")
LP = os.path.join(PORT, "AstoryServer", "Patches", "LoginPatch")
WANT_MD5 = "C19F6E7C3775B9FFC5CAC1354D7D5D19"
CYR = re.compile("[А-Яа-яЁё]")


def _refused(fn, part=""):
    from core import ops
    try:
        fn()
    except ops.OpRefused as ex:
        return part in str(ex), str(ex)
    except SystemExit as ex:
        return part in str(ex), str(ex)
    return False, "нет отказа"


class _Fake:
    """Подмены состояния: SQL, DLL, игроки; запись режима."""

    def __init__(self):
        self.sql = {"read": True, "error": "", "table": True, "gate": True, "mode": 0, "changed_at": "2026-11-21 01:00:00",
                    "changed_by": "cli:x", "reason": "", "refused": 0, "admitted": 0, "world_gate": True}
        self.dll = {"read": True, "error": "", "found": True, "l09_ok": False, "dll_md5": "2dcf9be9", "lm_start": "2026-11-19 12:28:07",
                    "log_file": "PatchLog_20261119.txt", "head": "", "total": "", "world_line": "on", "gate_fail": 0, "gate_fail_last": "",
                    "gate_fail_now": False}
        self.pl = {"bridge_read": True, "players": [], "operators": [], "bridge_error": "", "db_read": True, "db_logged": 0,
                   "db_error": "", "gm_outside": []}
        self.sets, self.announces, self.kicks, self.totp = [], [], [], []
        self.announce_fail = None
        self.announce_failed = []          # ★ ревизия 43 Н-3: узлы, до которых объявление не дошло (частичная рассылка)


def _install(fk):
    from core import auth, ops
    from domains import maint as M
    saved = (M.sql_state, M.dll_state, M.players_state, M._set, M.ops_run, ops._kick, auth.totp_confirm)
    M.sql_state = lambda: dict(fk.sql)
    def _dll(force=False):        # ★ ревизия 43б Н-4: как настоящий dll_state — md5 сборки и строка установки WorldGate
        if not fk.dll.get("read"):
            return {"read": False, "error": fk.dll.get("error"), "active": None, "dll_known": None, "world": None}
        act = fk.dll["l09_ok"] if fk.dll.get("found") else None
        world = {"on": True, "off": False}.get(fk.dll.get("world_line") or "") if act else (False if act is False else None)
        return dict(fk.dll, dll_known=fk.dll.get("dll_md5") in M.L09_DLL_MD5, active=act, world=world)
    M.dll_state = _dll
    M.players_state = lambda: dict(fk.pl)

    def _set(ctx, mode, reason):
        fk.sets.append((mode, reason, ctx.login))
        old = fk.sql["mode"]
        fk.sql["mode"] = mode
        return {"old": old, "mode": mode, "refused": fk.sql["refused"], "admitted": fk.sql["admitted"]}
    M._set = _set

    def _run(ctx, name, p, dry=False):
        if name != "live.announce":
            return ops.run(ctx, name, p, dry)
        if fk.announce_fail:
            raise ops.OpRefused(fk.announce_fail)
        fk.announces.append(p["text"])
        if fk.announce_failed:
            return {"message": "разослано на 2 узл. (не вышло: %s)" % "; ".join(fk.announce_failed),
                    "result": {"sent": [{"node": "GameServer"}], "failed": list(fk.announce_failed)}}
        return {"message": "разослано на 3 узл.", "result": {"sent": [{"node": "GameServer"}], "failed": []}}
    M.ops_run = _run

    def _kick(ctx, name, tgt, params, uids, why):
        fk.kicks.append(list(uids))
        return [{"uid": u, "char": "c%d" % u, "node": "GameServer", "cmd": 1} for u in uids]
    ops._kick = _kick
    auth.totp_confirm = lambda uid, code: fk.totp.append(code) if code == "123456" else (_ for _ in ()).throw(auth.AuthError("код не подошёл"))
    return saved


def _restore(saved):
    from core import auth, ops
    from domains import maint as M
    (M.sql_state, M.dll_state, M.players_state, M._set, M.ops_run, ops._kick, auth.totp_confirm) = saved


def _ops_offline(check):
    from core import audit, ops
    from domains import maint as M
    fk = _Fake()
    saved = _install(fk)
    saved_audit = audit.write
    rows = []
    audit.write = lambda *a, **k: rows.append((a[1], k.get("result"), k.get("message"))) or len(rows)
    cli = ops.Ctx(None, "cli:t", "owner", "", "cli")
    web = ops.Ctx(7, "boss", "owner", "1.2.3.4", "web")
    gm = ops.Ctx(8, "gm1", "gm", "", "web")
    ok = {"confirm": "maint", "announce": "Server maintenance / Обслуживание сервера"}
    try:
        r = _refused(lambda: ops.run(gm, "maint.on", ok), "нет права")
        check("maint.on: роль gm — отказ «нет права» (server.maintenance — владелец и администратор)", r[0], r[1])
        r = _refused(lambda: ops.run(cli, "maint.on", {"announce": "x"}), "--confirm-maint")
        check("maint.on: без подтверждения — отказ «нужно подтверждение --confirm-maint»", r[0], r[1])
        r = _refused(lambda: ops.run(cli, "maint.on", {"confirm": "maint"}), "без объявления")
        check("maint.on: без текста объявления и без явного silent — отказ «включение без объявления»", r[0] and not fk.sets, r[1])
        r = _refused(lambda: ops.run(cli, "maint.on", dict(ok, announce="я" * 96)), "длиннее")
        check("maint.on: объявление длиннее 95 байт cp1251 — отказ (проверка live.announce)", r[0], r[1])
        r = _refused(lambda: ops.run(cli, "maint.on", dict(ok, kick="all")), "неверный выбор")
        check("maint.on: kick не из {'', players} — отказ", r[0], r[1])
        r = _refused(lambda: ops.run(cli, "maint.on", dict(ok, reason="x" * 201)), "причина длиннее")
        check("maint.on: причина длиннее 200 — отказ", r[0], r[1])
        fk.sql.update(read=False, error="нет связи")
        r = _refused(lambda: ops.run(cli, "maint.on", ok), "не прочитано")
        check("maint.on: состояние входа не прочитано — отказ «ничего не делаю» (не прочитано ≠ выключено)", r[0] and not fk.sets, r[1])
        fk.sql.update(read=True, error="", table=False, gate=None, mode=None)
        r = _refused(lambda: ops.run(cli, "maint.on", ok), "SQL-часть L09 не применена")
        check("maint.on: таблицы adm.LoginMaintenance нет — отказ «SQL-часть L09 не применена … по слову владельца»", r[0], r[1])
        fk.sql.update(table=True, gate=False, mode=0)
        r = _refused(lambda: ops.run(cli, "maint.on", ok), "SQL-часть L09 не применена")
        check("maint.on: таблица есть, врезки в UPUserLogin нет — тот же отказ (таблица без врезки никого не держит)", r[0], r[1])
        fk.sql.update(gate=None)
        r = _refused(lambda: ops.run(cli, "maint.on", ok), "VIEW DEFINITION")
        check("maint.on: тело UPUserLogin не видно (нет VIEW DEFINITION) — отказ «врезка не подтверждена», а не «врезки нет»", r[0], r[1])
        fk.sql.update(gate=True, mode=1)
        r = _refused(lambda: ops.run(cli, "maint.on", ok), "уже включён")
        check("maint.on: режим уже включён — отказ с временем и автором", r[0] and "cli:x" in r[1], r[1])
        fk.sql.update(mode=0)
        fk.pl.update(bridge_read=False, bridge_error="нет ни одного узла моста с пульсом")
        r = _refused(lambda: ops.run(cli, "maint.on", dict(ok, kick="players")), "не прочитано")
        check("maint.on: выбрано отключить игроков, а мост не прочитан — отказ (не «никого нет»)", r[0], r[1])
        p = ops.run(cli, "maint.on", ok, dry=True)["preview"]
        w = " | ".join(p["warnings"])
        check("maint.on предпросмотр: «сначала объявление», DLL L09 не действует (текст «ошибка входа 28»), мост не прочитан, уже вошедшие "
              "играют дальше", "сначала объявление" in w and "ошибка входа 28" in w and "не прочитано" in w, w)
        check("maint.on предпросмотр (р43 С-1): DLL L09 не действует — честно «вход в мир с выбора персонажа НЕ закрыт», вошедшие по БД смогут "
              "войти, галочка их не достаёт", "НЕ закрыт" in w and "галочка «отключить игроков» их не достаёт" in w and "закрыт (LoginPatch L09)" not in w, w)
        fk.pl.update(bridge_read=True, bridge_error="", players=[{"uid": 6001, "owner": 6001}, {"uid": 6002, "owner": 1}],
                     operators=[{"uid": 2}], db_logged=5, gm_outside=[75000])
        p = ops.run(cli, "maint.on", ok, dry=True)["preview"]
        w = " | ".join(p["warnings"])
        check("maint.on предпросмотр: игроки вне 1…5000 в игре — «НЕ отключаются» (2 учётки сессий), вошли по БД 5, CharGmInfo 75000 не "
              "пускается", "НЕ отключаются" in w and ": 2 —" in w and ": 5" in w and "75000" in w, w)
        fk.dll.update(l09_ok=True, dll_md5=M.L09_DLL_MD5[0])
        p = ops.run(cli, "maint.on", ok, dry=True)["preview"]
        check("maint.on предпросмотр: DLL L09 действует — предупреждения про «ошибка входа 28» нет, «вход в мир … закрыт»",
              not any("ошибка входа 28" in x for x in p["warnings"]) and any(x == M.WORLD_CLOSED for x in p["warnings"]), p["warnings"])
        # ★ ревизия 43б Н-4: «закрыт» — только когда сходится всё; каждое отдельное «не сошлось» — своё «НЕ закрыт» / «неизвестно»
        cases = [("чужая сборка (md5 не L09)", dict(dll_md5="3cbfea529defba88cda9a7f9213d4dde"), {}, M.WORLD_OPEN_DLL[:60]),
                 ("L09 без гейта (WorldGate=0)", dict(world_line="off"), {}, M.WORLD_OPEN_NOGATE[:60]),
                 ("строки установки L09 нет", dict(world_line=""), {}, "закрыт ли вход в мир с выбора персонажа, неизвестно"),
                 ("нет процедуры adm.LoginMaintenanceGate", {}, dict(world_gate=False), M.WORLD_OPEN_PROC[:60]),
                 ("процедура не прочитана", {}, dict(world_gate=None), "закрыт ли вход в мир с выбора персонажа, неизвестно")]
        for name, dd, sd, want in cases:
            keep_d, keep_s = dict(fk.dll), dict(fk.sql)
            fk.dll.update(dd)
            fk.sql.update(sd)
            p = ops.run(cli, "maint.on", ok, dry=True)["preview"]
            check("maint.on предпросмотр (р43б Н-4): %s — НЕ «вход в мир закрыт», а «%s…»" % (name, want[:40]),
                  not any(x == M.WORLD_CLOSED for x in p["warnings"]) and any(x.startswith(want) for x in p["warnings"]), p["warnings"])
            fk.dll.clear(); fk.dll.update(keep_d)
            fk.sql.clear(); fk.sql.update(keep_s)
        # ★ ревизия 43б Н-3: сбои гейта видны — «сейчас НЕ работает» (последний сбой без восстановления) и «давал сбой» (восстановился)
        fk.dll.update(gate_fail=3, gate_fail_last="03:10:49", gate_fail_now=True)
        p = ops.run(cli, "maint.on", ok, dry=True)["preview"]
        check("maint.on предпросмотр (р43б Н-3): последний сбой гейта без восстановления — «гейт входа в мир сейчас НЕ работает … 03:10:49 … 3»",
              any(x == M.GATE_FAIL_NOW % ("03:10:49", 3) for x in p["warnings"]), p["warnings"])
        fk.dll.update(gate_fail_now=False)
        p = ops.run(cli, "maint.on", ok, dry=True)["preview"]
        check("maint.on предпросмотр (р43б Н-3): гейт восстановился — «давал сбой 3 раз (последний в 03:10:49) … сейчас работает»",
              any(x == M.GATE_FAIL_PAST % (3, "03:10:49") for x in p["warnings"]) and not any(x.startswith("гейт входа в мир сейчас") for x in p["warnings"]),
              p["warnings"])
        fk.dll.update(gate_fail=0, gate_fail_last="", gate_fail_now=False, dll_md5="2dcf9be9")
        fk.dll.update(read=False, error="SSH")
        p = ops.run(cli, "maint.on", ok, dry=True)["preview"]
        check("maint.on предпросмотр: журнал патчей не прочитан — «… закрыт ли вход в мир, неизвестно» (не «не действует», не «закрыт»)",
              any("неизвестно" in x for x in p["warnings"]) and not any(x in (M.WORLD_CLOSED,) or x.startswith("вход в мир с выбора персонажа НЕ")
                                                                         for x in p["warnings"]), p["warnings"])
        fk.dll.update(read=True, error="", l09_ok=False)

        fk.announce_fail = "нет ни одного GameServer с мостом в режиме исполнения (Mode=1)"
        r = _refused(lambda: ops.run(cli, "maint.on", ok), "НЕ включён")
        check("maint.on: объявление не разослано — отказ, режим НЕ включён (запись не делалась)", r[0] and not fk.sets and fk.sql["mode"] == 0, r[1])
        fk.announce_fail = None
        fk.announce_failed = ["Indun_GameServer: команда №7: итог неизвестен за 22 с (узел мог выполнить)"]
        r = _refused(lambda: ops.run(cli, "maint.on", ok), "не до всех узлов")
        check("maint.on (р43 Н-3): объявление дошло не до всех узлов — отказ «НЕ включён, часть игроков уже получила», записи нет",
              r[0] and "Indun_GameServer" in r[1] and "НЕ включён" in r[1] and not fk.sets, r[1])
        res = ops.run(cli, "maint.on", dict(ok, partial="partial"))
        check("maint.on (р43 Н-3): с явным partial — включён, итог с перечнем не дошедших", fk.sets and fk.sets[-1][0] == 1
              and "не вышло" in res["message"], res["message"])
        r = _refused(lambda: ops.run(cli, "maint.on", dict(ok, partial="yes")), "частичного")
        check("maint.on: partial не из {'', partial} — отказ", r[0], r[1])
        fk.sets.clear(); fk.announces.clear(); fk.sql.update(mode=0); fk.announce_failed = []
        r = _refused(lambda: ops.run(web, "maint.on", ok), "")
        check("maint.on из браузера без кода второго фактора — отказ, запись не делалась", r[0] and not fk.sets, r[1])
        res = ops.run(web, "maint.on", dict(ok, totp="123456", reason="плановое"))
        check("maint.on из браузера: свежий код второго фактора проверен, объявление ДО записи, запись Mode 1 с причиной, итог «включён»",
              fk.totp == ["123456"] and fk.announces == [ok["announce"]] and fk.sets == [(1, "плановое", "boss")]
              and res["message"].startswith(M.ON_DONE) and "объявление: разослано на 3 узл." in res["message"], res["message"])
        check("maint.on: уже вошедших игроков НЕ отключил (выбора kick не было)", not fk.kicks)
        r = _refused(lambda: ops.run(cli, "maint.on", ok), "уже включён")
        check("maint.on повторно — отказ «уже включён»", r[0], r[1])
        fk.sql.update(mode=0)
        fk.sets.clear()
        res = ops.run(cli, "maint.on", {"confirm": "maint", "silent": "silent", "kick": "players"})
        check("maint.on консолью: явное «без объявления» и kick=players — объявления нет, отключены мостом только учётки сессий вне 1…5000 "
              "(6001, 6002), итог с числом", fk.kicks == [[6001, 6002]] and len(fk.announces) == 1 and "отключено мостом: 2" in res["message"],
              res["message"])
        fk.sql.update(refused=4, admitted=1)
        r = _refused(lambda: ops.run(cli, "maint.off", {"confirm": "maint", "kick": "players"}), "незачем")
        check("maint.off: kick — отказ «незачем»", r[0], r[1])
        r = _refused(lambda: ops.run(cli, "maint.off", {}), "--confirm-maint")
        check("maint.off: без подтверждения — отказ", r[0], r[1])
        res = ops.run(web, "maint.off", {"confirm": "maint"})
        check("maint.off из браузера: второй фактор не нужен, запись Mode 0, итог со счётчиками отказов и допусков",
              fk.sets[-1][0] == 0 and "отказано входов: 4" in res["message"] and "допущено служебных: 1" in res["message"], res["message"])
        r = _refused(lambda: ops.run(cli, "maint.off", {"confirm": "maint"}), "уже выключен")
        check("maint.off повторно — отказ «уже выключен»", r[0], r[1])

        # перепроверка в apply: между предпросмотром и записью режим включили другим путём
        fk.sql.update(mode=0)
        orig = M.sql_state
        n = {"i": 0}

        def flip():
            n["i"] += 1
            return dict(fk.sql, mode=1 if n["i"] > 1 else 0)
        M.sql_state = flip
        before = len(fk.sets)
        r = _refused(lambda: ops.run(cli, "maint.on", {"confirm": "maint", "silent": "silent"}), "уже включён")
        check("maint.on: перепроверка ПЕРЕД записью (режим включили после предпросмотра) — отказ, записи нет", r[0] and len(fk.sets) == before, r[1])
        M.sql_state = orig
        # проверка после записи
        M_set = M._set
        M._set = lambda ctx, mode, reason: {"old": 0, "mode": 1, "refused": 0, "admitted": 0}
        fk.sql.update(mode=0)
        try:
            ops.run(cli, "maint.on", {"confirm": "maint", "silent": "silent"})
            vfail = False
        except RuntimeError as ex:
            vfail = "после записи" in str(ex)
        check("maint.on: проверка после записи (режим не стал 1) — сбой «после записи режим = 0» в журнал, а не «готово»",
              vfail and any(x[1] == "error" for x in rows), rows[-1:])
        M._set = M_set
    finally:
        audit.write = saved_audit
        _restore(saved)


def _jobs_offline(check):
    from core import audit, ops
    from domains import stack
    fk = _Fake()
    saved = _install(fk)
    saved_audit = audit.write
    audit.write = lambda *a, **k: 1
    try:
        sch = {s["op"]: s for s in stack.schedulable(ops.Ctx(1, "a", "admin", "", "web"))}
        check("задания: maint.on / maint.off ставятся (исполнитель — служба), слово подтверждения maint, второй фактор — только у включения",
              sch.get("maint.on", {}).get("runner") == "service" and sch["maint.on"]["confirm"] == "maint" and sch["maint.on"]["two"]
              and sch.get("maint.off", {}).get("two") is False, sch.get("maint.on"))
        check("задания: роль gm операций режима не видит", "maint.on" not in {s["op"] for s in stack.schedulable(ops.Ctx(1, "g", "gm", "", "web"))})
        import datetime
        at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).isoformat()
        web = ops.Ctx(7, "boss", "owner", "", "web")
        r = _refused(lambda: ops.run(web, "job.add", {"op": "maint.on", "at": at, "params": {"confirm": "maint", "announce": "x"}}, dry=True),
                     "второго фактора")
        check("job.add maint.on из браузера без кода — отказ «нужен свежий код второго фактора» (как у стойки)", r[0], r[1])
        p = ops.run(web, "job.add", {"op": "maint.on", "at": at, "params": {"confirm": "maint", "announce": "Обслуживание"}, "totp": "1"},
                    dry=True)["preview"]
        check("job.add maint.on: предпросмотр — второй фактор потребуется, текст объявления в окне, «проверяются в момент запуска»",
              p["two"] and any("Обслуживание" in w for w in p["warnings"]) and any("в момент запуска" in w for w in p["warnings"]), p["warnings"])
        r = _refused(lambda: ops.run(web, "job.add", {"op": "maint.on", "at": at, "params": {"announce": "x"}, "totp": "1"}, dry=True),
                     "--confirm-maint")
        check("job.add maint.on без подтверждения — отказ при постановке (schedule_check)", r[0], r[1])
        r = _refused(lambda: ops.run(web, "job.add", {"op": "maint.off", "at": at, "params": {"confirm": "maint", "kick": "players"}}, dry=True),
                     "незачем")
        check("job.add maint.off с kick — отказ сразу при постановке (р43, мелочь 3), а не в срок", r[0], r[1])
        p = ops.run(web, "job.add", {"op": "maint.off", "at": at, "params": {"confirm": "maint"}}, dry=True)["preview"]
        check("job.add maint.off из браузера — без второго фактора", p["two"] is False, p)
        # задание служба исполняет от имени автора (via job): второй фактор не спрашивается, проверки — те же
        job = {"id": 77, "op": "maint.on", "params": {"confirm": "maint", "announce": "Обслуживание"}, "created_uid": None,
               "created_by": "cli:t", "created_role": "owner", "created_host": __import__("socket").gethostname()[:64]}
        from core import jobs as J
        fin = []
        saved_j = (J.finish, J._repeat)
        J.finish, J._repeat = (lambda jid, st, text="", aid=None: fin.append((jid, st, text))), (lambda job, now: None)
        try:
            st, text = J.run_job(job)
        finally:
            J.finish, J._repeat = saved_j
        check("задание maint.on исполняется службой: объявление, запись Mode 1, итог done", st == "done" and fk.sets and fk.sets[-1][0] == 1
              and fin and fin[-1][1] == "done", (st, text))
    finally:
        audit.write = saved_audit
        _restore(saved)


def _ps_dll_local(check, M):
    """★ ревизия 43б Н-3 / Н-4: настоящий скрипт _PS_DLL на ПК над своим журналом (cp1251, строки как у DLL 98e5308b): установка
    с WorldGate=1, сбой гейта, восстановление, ещё сбой — после строки итога «=== » (строки работы читаются до конца файла)."""
    import shutil
    import tempfile
    root = tempfile.mkdtemp(prefix="asda_l09_ps_")
    try:
        d = os.path.join(root, "LoginManager", "Log", "Log_Patch")
        os.makedirs(d)
        lines = ["[01:00:00] старый запуск", "[01:00:00] LoginPatch — старт 2026-11-20 01:00:00, PID 11",
                 "[01:00:01]   [OK] L09_LoginMaintenance", "[01:00:01] === итог",
                 "[02:00:00] LoginPatch — старт 2026-11-21 02:00:00, PID 22",
                 "[02:00:01]     L09: отправка 1004 @0x00407B2F -> L09_Send; статус 28 процедуры => 4101 код 28 (нотис 7017, без разрыва); "
                 "вход в мир (1016, UPCharSoulState @0x0040B41A) — гейт adm.LoginMaintenanceGate (WorldGate=1, соединение 0); соулмейт",
                 "[02:00:01]   [OK] L09_LoginMaintenance", "[02:00:01] === итог: применено 9, ошибок 0",
                 "[03:10:49]     L09: [L09-GATE-FAIL] СБОЙ ГЕЙТА ВХОДА В МИР (выбор персонажа), учётка 6001 — …",
                 "[03:10:52]     L09: [L09-GATE-OK] гейт входа в мир снова работает (сбоев подряд было 1; входов в мир без проверки: 0)",
                 "[03:20:07]     L09: [L09-GATE-FAIL] СБОЙ ГЕЙТА ВХОДА В МИР (выбор персонажа), учётка 6002 — …"]
        with open(os.path.join(d, "PatchLog_20261121.txt"), "wb") as f:
            f.write(("\r\n".join(lines) + "\r\n").encode("cp1251", errors="replace"))
        script = os.path.join(root, "dll.ps1")
        with open(script, "wb") as f:
            f.write(b"\xef\xbb\xbf" + M._PS_DLL.replace("__ROOT__", root).encode("utf-8"))
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script],
                           capture_output=True, timeout=120)
        out = p.stdout.decode("utf-8", errors="replace").strip().splitlines()
        r = json.loads(out[-1]) if out else {}
        check("DLL (р43б Н-3 / Н-4): скрипт журнала патчей на своём журнале — [OK] L09, строка установки WorldGate=1 → world «on», сбоев гейта 2, "
              "последний 03:20:07 без восстановления после него → «сейчас не работает»",
              r.get("ok") is True and r.get("world") == "on" and r.get("fail") == 2 and r.get("fail_last") == "03:20:07"
              and r.get("fail_now") is True, (r, p.stderr[-300:]))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _dll_offline(check):
    from domains import maint as M
    saved = M.DLL_READ
    try:
        M._dll_cache.update(at=0.0, data=None)
        M.DLL_READ = lambda: {"read": True, "error": "", "dll_md5": M.L09_DLL_MD5[0], "lm_start": "x", "log_file": "f",
                              "head": "h", "found": True, "l09_ok": True, "total": "=== итог", "world_line": "on"}
        d = M.dll_state(force=True)
        check("DLL: в последнем запуске «[OK] L09_LoginMaintenance» — действует, сборка L09 узнана по md5, гейт входа в мир по строке WorldGate=1",
              d["active"] is True and d["dll_known"] and d["world"] is True, d)
        M.DLL_READ = lambda: {"read": True, "error": "", "dll_md5": "3cbfea529defba88cda9a7f9213d4dde", "lm_start": "x", "log_file": "f",
                              "head": "h", "found": True, "l09_ok": True, "total": "=== итог", "world_line": "on"}
        d = M.dll_state(force=True)
        check("DLL (р43б): прежняя сборка 3cbfea52 — не сборка L09 панели (не выкладывать)", d["active"] is True and not d["dll_known"], d)
        _ps_dll_local(check, M)
        M.DLL_READ = lambda: {"read": True, "error": "", "dll_md5": "2dcf9be9008975242692421fe376799d", "lm_start": "x", "log_file": "f",
                              "head": "h", "found": True, "l09_ok": False, "total": "t"}
        d = M.dll_state(force=True)
        check("DLL: запуск найден, L09 в нём нет (живая v10) — «не действует», а не «не прочитано»", d["active"] is False and not d["dll_known"], d)
        M.DLL_READ = lambda: {"read": True, "error": "", "dll_md5": "x", "lm_start": "", "log_file": "", "head": "", "found": False,
                              "l09_ok": False, "total": ""}
        d = M.dll_state(force=True)
        check("DLL: в журнале нет запуска — active None «не прочитано» (не «не действует»)", d["active"] is None and "нет запуска" in d["error"], d)

        def boom():
            from core import hostshell
            raise hostshell.HostError("команда на сервере не уложилась в 45 с")
        M.DLL_READ = boom
        d = M.dll_state(force=True)
        check("DLL: сбой SSH — read False, active None", d["read"] is False and d["active"] is None, d)
        d2 = M.dll_state()
        check("DLL: кэш 60 с — повторное чтение без force не ходит на сервер", d2 is d)
        ps = M._PS_DLL
        check("DLL: скрипт PowerShell — только чтение (FileStream с совместным доступом), журнал строго PatchLog_<8 цифр>.txt, запуск по "
              "«…, PID N», L09 до строки итога «=== »", "'Read', 'ReadWrite'" in ps and r"'^PatchLog_\d{8}\.txt$'" in ps
              and ", PID \\d+" in ps and r"\[OK\]\s+L09_LoginMaintenance" in ps and "Remove-Item" not in ps and "Set-Content" not in ps
              and r"\[L09-GATE-FAIL\]" in ps and r"\[L09-GATE-OK\]" in ps and "WorldGate=1" in ps)
    finally:
        M.DLL_READ = saved
        M._dll_cache.update(at=0.0, data=None)


def _cli_offline(check):
    import asda_admin
    r = _refused(lambda: asda_admin.maint_args(["--confirm-maint", "--bogus"]), "неизвестный ключ")
    check("консоль maint: неизвестный ключ — отказ без действий", r[0], r[1])
    r = _refused(lambda: asda_admin.maint_args(["--announce"]), "нет значения")
    check("консоль maint: --announce без значения — отказ", r[0], r[1])
    r = _refused(lambda: asda_admin.maint_args(["--announce", "--silent"]), "нет значения")
    check("консоль maint: значение ключа не может быть другим ключом", r[0], r[1])
    p = asda_admin.maint_args(["--confirm-maint", "--silent", "--kick-players", "--reason", "плановое", "--announce", "Текст"])
    check("консоль maint: ключи → параметры операции", p == {"confirm": "maint", "silent": "silent", "kick": "players", "reason": "плановое",
                                                             "announce": "Текст"}, p)
    check("консоль: справка описывает maint state / on / off и задание по расписанию", "maint …" in asda_admin.__doc__
          and "--kick-players" in asda_admin.__doc__ and "jobs add maint.on" in asda_admin.__doc__)
    import sys
    p = subprocess.run([sys.executable, os.path.join(ROOT, "asda_admin.py"), "--help"], capture_output=True, timeout=60)
    check("консоль: asda_admin.py --help — только справка, код 0", p.returncode == 0 and b"maint" in p.stdout)


def _i18n_offline(check):
    from core import i18n
    from domains import maint as M
    msgs = [M.NEED_SQL, M.NEED_DLL, M.DLL_UNREAD % "SSH", M.WORLD_CLOSED, M.WORLD_OPEN % 5, M.WORLD_OPEN % "не прочитано", M.OVERLAP_NOTE, M.ON_DONE,
            # ★ ревизия 43б Н-3 / Н-4
            M.WORLD_OPEN_NOGATE % 4, M.WORLD_OPEN_DLL % ("3cbfea529defba88cda9a7f9213d4dde", "98e5308b", "не прочитано"), M.WORLD_OPEN_PROC % 0,
            M.WORLD_UNKNOWN % M.WORLD_WHY_LOG, M.WORLD_UNKNOWN % M.WORLD_WHY_LINE, M.WORLD_UNKNOWN % M.WORLD_WHY_SQL,
            M.GATE_FAIL_NOW % ("03:20:07", 2), M.GATE_FAIL_PAST % (2, "03:20:07"),
            "объявление дошло не до всех узлов моста (не вышло: Indun_GameServer: команда №7: итог неизвестен за 22 с (узел мог выполнить)) — режим обслуживания НЕ "
            "включён, часть игроков объявление уже получила (включить всё равно — явный выбор partial)",
            "неверный выбор частичного объявления (можно: нет или partial)",
            "объявление, дошедшее не до всех узлов моста, режим НЕ остановит (выбрано явно)",
            M.ON_DONE + " (он уже был включён к моменту записи; объявление: разослано на 3 узл.; отключено мостом: 2)",
            M.ON_DONE + " (отключение игроков не завершено: игрок в игре, отключить мостом не вышло: учётка 6001: мост не может вывести игрока "
                        "(узел без пульса, Mode=0 или игрок не виден мосту))",
            "включение без объявления: нужен текст объявления в игру или явное «без объявления» (silent = silent)",
            "состояние входа не прочитано (в adm.LoginMaintenance нет строки Id = 1) — ничего не делаю", "режим обслуживания уже включён (с 2026-11-21, boss)",
            "режим обслуживания уже выключен (с ?, ?)", "нужно подтверждение: ключ --confirm-maint (в панели — галочка подтверждения)",
            "неверный выбор отключения (можно: не отключать или players)", "отключить игроков можно только с правом «players.kick»",
            "сначала объявление в игру (мост): «Server»", "без объявления в игру (выбрано явно)",
            "кто в игре по данным моста — не прочитано (нет ни одного узла моста с пульсом)",
            "выбрано отключить игроков, а кто в игре по данным моста не прочитано — ничего не делаю",
            "после включения будут отключены мостом игроки вне 1…5000: 3 (штатный выход с записью)",
            "в игре игроков вне 1…5000: 2 — они НЕ отключаются (отключить — галочка «отключить игроков» или live.kick)",
            "вошли по БД (Us_member.Flag = 1) учёток вне 1…5000: 5",
            "у учёток вне 1…5000 есть строка CharGmInfo (75000) — режим их не пустит, допуск только по номеру 1…5000",
            "включить режим обслуживания: вход только служебным учёткам 1…5000, остальным — статус 28",
            "объявление не разослано (нет ни одного узла моста с пульсом) — режим обслуживания НЕ включён (без объявления — явное «без объявления»)",
            "режим обслуживания выключен (отказано входов: 4, допущено служебных: 1)",
            "режим обслуживания выключен (отказано входов: 4, допущено служебных: 1) — объявление: разослано на 2 узл.",
            "за время режима отказано входов: 4, допущено служебных: 1", "после выключения — объявление в игру (мост): «Open»",
            "выключить режим обслуживания (включён 2026-11-21, boss)", "при выключении отключать игроков незачем",
            "без объявления в игру", "в срок будут отключены мостом игроки вне 1…5000",
            "готовность SQL-части L09 и состояние режима проверяются в момент запуска задания", "причина длиннее 200 символов",
            "после записи режим обслуживания = 0, ожидалось 1", "тело UPUserLogin не прочитано (нет права VIEW DEFINITION у asda_admin) — "
            "врезка L09 не подтверждена, ничего не делаю", "в журнале патчей нет запуска", "нет ни одного узла моста с пульсом",
            "задание «Вход: включить режим обслуживания (только служебные 1…5000)» на 2026-11-21 05:00 UTC (исполнитель: service)"]
    tok = i18n.LANG.set("en")
    try:
        bad = [(m, i18n.tr(m)) for m in msgs if CYR.search(i18n.tr(m))]
    finally:
        i18n.LANG.reset(tok)
    check("переводы EN (core/i18n.py): все тексты А5.3 (отказы, предупреждения, итоги, вложенные части, название операции в задании) — без "
          "кириллицы", not bad, bad[:3])
    refusals = [M.NEED_SQL, M.NEED_DLL, M.DLL_UNREAD, M.WORLD_CLOSED, M.WORLD_OPEN, M.OVERLAP_NOTE, M.WORLD_OPEN_NOGATE, M.WORLD_OPEN_DLL,
                M.WORLD_OPEN_PROC, M.WORLD_UNKNOWN, M.GATE_FAIL_NOW, M.GATE_FAIL_PAST]
    src = open(os.path.join(ROOT, "domains", "maint.py"), encoding="utf-8").read()
    lits = re.findall(r'OpRefused\("([^"]+)"', src)
    check("тексты отказов maint.py без «; » (%d отказов)" % len(lits), lits and not any("; " in x for x in lits + refusals), lits)


def _web_offline(check):
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    i18 = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    a = app.index("function maintCard()")
    b = app.index("// ---------- А5.1: задания планировщика")
    nxt = app.find("\n// ---------- ", a)       # ★ р43б: после карточки режима могут встать чужие карточки (А5.4) — блок только до них
    if 0 <= nxt < b:
        b = nxt
    block = app[a:b]
    check("веб: карточка «Режим обслуживания» на странице «Состояние», состояние из /api/maint, действия — только с правом server.maintenance",
          "maintCard()," in app and '"/api/maint"' in block and 'can("server.maintenance")' in block)
    check("веб: в карточке режима нет innerHTML / insertAdjacentHTML (данные — только текстовыми узлами)",
          "innerHTML" not in block and "insertAdjacentHTML" not in block)
    check("веб: включение — свежий код второго фактора, выключение — без него; «без объявления» и «отключить игроков» — только при включении",
          "totp: code.value.trim()" in block and 'x.silent = "silent"' in block and 'x.kick = "players"' in block)
    keys = set(re.findall(r'^\s*"([^"]+)":', i18, flags=re.M)) | set(re.findall(r',\s*"([^"]+)":', i18))
    lits = set(re.findall(r'"([^"\n]*[А-Яа-яЁё][^"\n]*)"', block))
    miss = sorted(x for x in lits if x not in keys)
    check("веб: все русские строки карточки режима есть в web/i18n.js (EN)", not miss, miss[:6])
    jf = app[app.index("function jobForm("):app.index("// ---------- А5.2")]
    lits = set(re.findall(r'"([^"\n]*[А-Яа-яЁё][^"\n]*)"', jf))
    miss = sorted(x for x in lits if x not in keys)
    check("веб: форма заданий знает операции режима (объявление, «без объявления», «отключить игроков», подтверждение, второй фактор по two), "
          "строки переведены", 'o.op.startsWith("maint.")' in jf and "o.two" in jf and not miss, miss[:6])
    dup = [k for k in re.findall(r'"([^"]+)":', i18[i18.index("А5.3 (21.11)"):]) if i18.count('"%s":' % k) > 1]
    check("веб: ключи А5.3 в web/i18n.js не дублируют прежние", not dup, dup)


def _static_offline(check):
    g = open(os.path.join(ROOT, "sql", "adminc_03_grants.sql"), encoding="utf-8").read()
    o = open(os.path.join(ROOT, "sql", "adminc_04_ops.sql"), encoding="utf-8").read()
    v = open(os.path.join(ROOT, "sql", "adminc_10_verify.sql"), encoding="utf-8").read()
    vo = open(os.path.join(ROOT, "sql", "adminc_11_verify_ops.sql"), encoding="utf-8").read()
    check("SQL-права: asda_admin — VIEW DEFINITION только на dbo.UPUserLogin (Joy1), EXECUTE по-прежнему запрещён; проверка adminc_10",
          "GRANT VIEW DEFINITION ON dbo.UPUserLogin TO [asda_admin];" in g and "'Joy1.UPUserLogin VIEW DEFINITION'" in v
          and "'Joy1.UPUserLogin EXEC'" in v)
    check("SQL-права: asda_ops — EXECUTE adm.LoginMaintenanceSet и запрет прямой записи таблицы — только если SQL L09 применён",
          "IF OBJECT_ID(N'adm.LoginMaintenanceSet', N'P') IS NOT NULL GRANT EXECUTE ON adm.LoginMaintenanceSet TO [asda_ops];" in o
          and "DENY INSERT, UPDATE, DELETE ON adm.LoginMaintenance TO [asda_ops]" in o)
    check("SQL-права: adminc_11 — число исполняемых объектов Joy1 = 9 (★ А5.4: + adm.LimitationReset; +1 при L09), UPDATE / INSERT таблицы режима = 0, "
          "UPUserLogin EXEC = 0",
          "9 + CASE WHEN OBJECT_ID(N'Joy1.adm.LoginMaintenanceSet', N'P') IS NULL THEN 0 ELSE 1 END" in vo
          and "'ops.adm.LoginMaintenance UPDATE'" in vo and "'ops.Joy1.UPUserLogin EXEC'" in vo)
    mig = open(os.path.join(SQLDIR, "l09_01_migrate.sql"), encoding="utf-8").read()
    rb = open(os.path.join(SQLDIR, "l09_99_rollback.sql"), encoding="utf-8").read()
    check("SQL L09: миграция по md5 живого тела (C19F6E7C…), единственный якорь и заголовок, копия тела, Mode 0 по умолчанию; откат — из копии "
          "со сверкой md5 до и после, таблица — только после снятия врезки",
          "0xC19F6E7C3775B9FFC5CAC1354D7D5D19" in mig and "якорь" in mig and "UPUserLogin_bak_20261121_l09" in mig
          and "DEFAULT (0)" in mig and "THROW 50043" in rb and "THROW 50044" in rb and "THROW 50045" in rb)
    gate_txt = mig[mig.index("DECLARE @gate"):mig.index("DECLARE @new")]
    check("SQL L09 (р43): врезка целиком под IF OBJECT_ID(adm.LoginMaintenance) (Н-1); двоичная сортировка — в самих REPLACE / CHARINDEX, не "
          "в переменной (мелочь 1); гейт входа в мир adm.LoginMaintenanceGate + WorldRefused (С-1); откат удаляет и гейт",
          "IF OBJECT_ID(N''adm.LoginMaintenance'', N''U'') IS NOT NULL" in gate_txt and "@d COLLATE Latin1_General_BIN2, @anchor" in mig
          and "= @d COLLATE Latin1_General_BIN2;" not in mig and "CREATE OR ALTER PROCEDURE adm.LoginMaintenanceGate" in mig
          and "WorldRefused" in mig and "DROP PROCEDURE adm.LoginMaintenanceGate" in rb and "@bak COLLATE" not in rb)
    sm = open(os.path.join(SQLDIR, "l09_10_smoke.sql"), encoding="utf-8").read()
    check("SQL L09 smoke (р43 Н-4, р43б С-1): защита безусловная — стенд только LocalDB + метка AsdaL09StandMarker, иначе отказ без "
          "-v L09SmokeOnLive=yes, без VIEW SERVER STATE и при работающей стойке (порога по числу учёток нет); игровая учётка — номером ниже "
          "IDENTITY", "THROW 50090" in sm and "THROW 50091" in sm and "THROW 50092" in sm and "$(L09SmokeOnLive)" in sm
          and "SERVERPROPERTY('IsLocalDB')" in sm and "master.dbo.AsdaL09StandMarker" in sm and "us_member) > 100" not in sm
          and "IDENT_CURRENT('AsdaStoryOP.dbo.us_member') = @ident" in sm and "OUTPUT inserted.Userindex" not in sm)
    src = open(os.path.join(LP, "src", "patches", "l09_login_maintenance.cpp"), encoding="utf-8").read()
    api = open(os.path.join(LP, "src", "LoginApi.h"), encoding="utf-8").read()
    reg = open(os.path.join(LP, "src", "patches", "Registry.cpp"), encoding="utf-8").read()
    cfg = open(os.path.join(LP, "src", "Config.h"), encoding="utf-8").read()
    check("DLL L09: площадка call 0x415A40 @0x407B2F (e8 0c df 00 00), 1004/Status → 4101/Code тем же вызовом, что AcceptIp (размер 1, "
          "заголовок 0, флаг 1), Status 1…7 — не ставится, Code — только с текстом у клиента (р43, мелочь 5); Config Version 11; патч в реестре",
          "kLoginReplyCall = 0x00407B2F" in api and "{ 0xE8, 0x0C, 0xDF, 0x00, 0x00 }" in src
          and "kOpLoginRefuse, 1, slot, &code, hdr, 1" in src and "status < 8" in src and "!CodeHasText(code)" in src
          and "case 0x10" not in src[src.index("bool CodeHasText"):src.index("bool CodeHasText") + 600]
          and "constexpr int kVersion = 11;" in cfg and '{ L"L09_LoginMaintenance"' in reg)
    check("DLL L09 (р43 С-1): второй гейт — call 0x40F440 @0x40B41A (EXEC UPCharSoulState в 1016, e8 21 40 00 00) → EXEC "
          "adm.LoginMaintenanceGate; отказ — 4101/Code сессии, *out = 0 (стоковая ветка ошибки); обе площадки сверяются до записи",
          "kSelSoulStateCall = 0x0040B41A" in api and "{ 0xE8, 0x21, 0x40, 0x00, 0x00 }" in src and "EXEC adm.LoginMaintenanceGate %d" in src
          and "okReply || !okWorld" in src and 'L"WorldGate"' in open(os.path.join(LP, "src", "Config.cpp"), encoding="utf-8").read())
    l04 = open(os.path.join(LP, "src", "patches", "l04_login_identity.cpp"), encoding="utf-8").read()
    check("DLL L09 (р43б): Н-1 — гейт на соединении 0 (g_sql(…, out, 0, db, …)), Н-2 — режим 2 решает L04c до sub_4037B0 (L09_MateGate через "
          "L04c_SetMaintGate, отказ 1027 код 0), Н-3 — окно после сбоя WorldErrorSec с удвоением и строки [L09-GATE-FAIL] / [L09-GATE-OK]",
          'out, 0, db, dst, "EXEC adm.LoginMaintenanceGate %d"' in src and "L04c_SetMaintGate(g_mateByL04c" in src
          and "g_maintGate(fr, realUser, clientUi)" in l04 and "kind == 2 ? 0 : 3" in l04 and "wait *= 2" in src
          and "[L09-GATE-FAIL]" in src and "[L09-GATE-OK]" in src and "WorldGate=1" in src
          and 'L"WorldErrorSec"' in open(os.path.join(LP, "src", "Config.cpp"), encoding="utf-8").read())
    dep = open(os.path.join(LP, "tools", "deploy_l09.py"), encoding="utf-8").read()
    pinned = os.path.join(LP, "tools", "l09_data", "LoginPatch_v11_l09_98e5308b.dll")
    import hashlib
    h = hashlib.md5(open(pinned, "rb").read()).hexdigest() if os.path.exists(pinned) else "нет файла"
    from domains import maint as M
    check("DLL L09: закреплённая сборка 98e5308b… (р43б: гейт на соединении 0, режим 2 в L04c, сбои видны) = панели (L09_DLL_MD5, прежних "
          "d5e97e0c / 3cbfea52 там нет) = выкладчику (want), прежняя v10 2dcf9be9 (prev)",
          h == "98e5308b8d7f292ff397087b9021e4c9" and M.L09_DLL_MD5 == (h,) and '"want": "%s"' % h in dep
          and '"prev": "2dcf9be9008975242692421fe376799d"' in dep, h)
    import sys
    p = subprocess.run([sys.executable, os.path.join(LP, "tools", "deploy_l09.py"), "--help"], capture_output=True, timeout=60)
    q = subprocess.run([sys.executable, os.path.join(LP, "tools", "deploy_l09.py"), "--bogus"], capture_output=True, timeout=60)
    check("deploy_l09.py: --help — справка, код 0, без SSH; неизвестный ключ — код 1 без действий",
          p.returncode == 0 and b"deploy_l09" in p.stdout and q.returncode == 1 and "неизвестный ключ".encode("utf-8") in q.stdout,
          (p.returncode, q.returncode))
    bat = open(os.path.join(LP, "tools", "regress_all.bat"), encoding="ascii", errors="replace").read()
    check("регресс LoginPatch: test_l09 и стенд stand_l09 (5 режимов) в regress_all.bat; падение exe (отрицательный код) — провал "
          "(!errorlevel! neq 0 вместо «if errorlevel 1»); р43 — режимы стенда worldmismatch, badcode, noworld",
          "test_l09" in bat and "stand_l09.exe" in bat and "if errorlevel 1" not in bat and bat.count("!errorlevel! neq 0") >= 4
          and "on off mismatch worldmismatch badcfg badcode noworld all" in bat)
    adm = open(os.path.join(ROOT, "asda_admin.py"), "rb").read()
    check("asda_admin.py (р43, мелочь 2): концы строк CRLF, как в Perforce (ни одной голой LF)", adm.count(b"\n") == adm.count(b"\r\n") > 0)


def offline(check):
    _ops_offline(check)
    _jobs_offline(check)
    _dll_offline(check)
    _cli_offline(check)
    _i18n_offline(check)
    _web_offline(check)
    _static_offline(check)


# ─────────────────────────────── стенд SQL L09 (LocalDB, свой экземпляр) ───────────────────────────────
INSTANCE = "AsdaL09Stand"

STAND_SQL = {
    "AsdaStoryOP": [
        """CREATE TABLE dbo.us_member (Userindex INT IDENTITY(6001,1) NOT NULL PRIMARY KEY, Us_id VARCHAR(61) NOT NULL, us_block TINYINT NOT NULL,
             us_rdate DATETIME NOT NULL, igsNID INT NOT NULL, Realcash INT NOT NULL, BonusCash INT NOT NULL, Seridx TINYINT NULL, Gsidx TINYINT NULL,
             Threadidx TINYINT NULL, Channel TINYINT NULL, Poridx TINYINT NULL, UserNum SMALLINT NULL, Flag TINYINT NULL, Loginidx BIGINT NULL,
             Portalidx BIGINT NULL, us_pwhash BINARY(32) NULL, us_pwsalt BINARY(16) NULL, us_pwset DATETIME NULL, us_pwfail TINYINT NOT NULL DEFAULT 0,
             us_pwfail_at DATETIME NULL)""",
        # тело — как живое AsdaStoryOP.dbo.UPStartinfoUP (21.11.2026)
        """CREATE PROCEDURE [dbo].[UPStartinfoUP] @Uid VARCHAR(61),@Userindex INT,@Flag TINYINT,@idx BIGINT
AS
	SET NOCOUNT ON
	DECLARE @idx1 BIGINT,@Loginidx BIGINT
	IF @Flag=1
	BEGIN
		UPDATE dbo.Us_member SET Flag=1,Loginidx=@idx WHERE Userindex=@Userindex
		SET @Loginidx=@idx
	END
	ELSE IF @Flag=0
	BEGIN
		UPDATE dbo.Us_member SET Flag=0, UserNum=-1,@idx1=Loginidx WHERE Userindex=@Userindex
		SET @Loginidx=@idx1
	END
	RETURN @Loginidx""",
    ],
    "JoyLog1": [
        """CREATE TABLE dbo.Loginfo (Loginidx BIGINT IDENTITY(1,1) PRIMARY KEY, Seridx TINYINT, Userindex INT, Charidx TINYINT, IpAddress VARCHAR(15),
             Mac VARCHAR(20), Login DATETIME, Logout DATETIME NULL, State TINYINT)""",
        # тело — как живое JoyLog1.dbo.UPLoginGame (21.11.2026)
        """CREATE PROC [dbo].[UPLoginGame]  @Seridx TINYINT,@Userindex INT,@Charidx TINYINT,@IP VARCHAR(15), @DATE DATETIME,@State TINYINT, @Mac VARCHAR(20) = ''
AS
	SET NOCOUNT ON
	DECLARE @Loginidx BIGINT
	IF @charidx=0
	BEGIN
		INSERT INTO dbo.Loginfo ( Seridx,Userindex,Charidx,IpAddress,Mac, Login, Logout,State )
		VALUES ( 1, @Userindex,13,@Ip,@Mac, @DATE, NULL,@State)
		SET @Loginidx=@@IDENTITY
	END
	ELSE
	BEGIN
		INSERT INTO dbo.Loginfo ( Seridx,Userindex,Charidx,IpAddress,Mac, Login, Logout,State )
		VALUES ( @Seridx+1, @Userindex,@Charidx,@Ip,@Mac,@DATE, NULL,@State)
		SET @Loginidx=@@IDENTITY
	END
	RETURN @Loginidx""",
    ],
    "Joy1": [
        "CREATE TABLE dbo.CharPos (Userindex INT, Charidx TINYINT, UserNum SMALLINT, Partyidx INT, Captain TINYINT, SoulState TINYINT, State TINYINT)",
        "CREATE TABLE dbo.CharGmInfo (UserIndex INT, Charidx TINYINT, GMFlag TINYINT, GMDate DATETIME DEFAULT GETDATE())",
        # стенд: снятие истёкшего блока не участвует в режиме (у us_block = 5 без строк BlockList живое тоже ничего не делает)
        "CREATE PROC [dbo].[UP_AC_LiftExpiredBlock] @Userindex INT AS SET NOCOUNT ON; RETURN 0",
    ],
}


def _localdb(*a):
    return subprocess.run(["sqllocaldb"] + list(a), capture_output=True, timeout=180)


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


def _exec_file(cn, path):
    """Файл T-SQL по пакетам GO → [наборы строк последнего пакета …] (все наборы всех пакетов)."""
    out = []
    for b in _batches(open(path, encoding="utf-8").read()):
        cur = cn.cursor()
        cur.execute(b)
        while True:
            if cur.description:
                out.append([tuple(r) for r in cur.fetchall()])
            if not cur.nextset():
                break
    return out


def _exec_text(cn, text):
    """Как _exec_file, но из строки (для подстановки переменной sqlcmd $(L09SmokeOnLive), которую pyodbc не раскрывает)."""
    out = []
    for b in _batches(text):
        cur = cn.cursor()
        cur.execute(b)
        while True:
            if cur.description:
                out.append([tuple(r) for r in cur.fetchall()])
            if not cur.nextset():
                break
    return out


def _smoke_guard(check, conn, j):
    """★ ревизия 43б С-1: l09_10_smoke.sql отказывает БЕЗ порога по числу учёток — стенд только по положительному признаку
    (LocalDB + master.dbo.AsdaL09StandMarker). Здесь метку снимаем: так стенд выглядит как живая база (учёток меньше 100)."""
    import pyodbc
    sm = open(os.path.join(SQLDIR, "l09_10_smoke.sql"), encoding="utf-8").read()
    count = lambda: j.cursor().execute("SELECT (SELECT COUNT(*) FROM AsdaStoryOP.dbo.us_member), (SELECT Mode FROM adm.LoginMaintenance "
                                       "WHERE Id = 1), @@TRANCOUNT").fetchone()
    before = tuple(count())
    j.cursor().execute("DROP TABLE master.dbo.AsdaL09StandMarker")
    pool = []
    try:
        try:
            _exec_text(j, sm)
            e1 = ""
        except pyodbc.Error as ex:
            e1 = str(ex)
        check("стенд L09 (р43б С-1): smoke без метки стенда (учёток %d < 100, как на живой Joy1) и без ключа — отказ 50090, ничего не сделано"
              % before[0], "50090" in e1 and tuple(count()) == before, (e1[:160], before, tuple(count())))
        yes = sm.replace("$(L09SmokeOnLive)", "yes")
        # сначала «стойка остановлена» (своих соединений без имени программы нет: у pyodbc имя «Python»), потом — «работает»
        # (закрытые соединения остаются в пуле ODBC, поэтому этот шаг — последним)
        try:
            res = _exec_text(j, yes)
            e3 = ""
        except pyodbc.Error as ex:
            res, e3 = [], str(ex)
        total = res[-1][0][0] if res and res[-1] else e3[:160]
        check("стенд L09 (р43б С-1): smoke с ключом yes при остановленной «стойке» — выполняется (%s), всё откачено" % total,
              bool(re.match(r"ok=\d+ fail=0$", str(total))) and tuple(count()) == before, (total, tuple(count())))
        for _ in range(10):        # «стойка»: один процесс, 10 соединений без имени программы (как пул LoginManager / DBManager)
            pool.append(pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=(localdb)\\%s;DATABASE=Joy1;Trusted_Connection=yes;APP=;"
                                       % INSTANCE, autocommit=True, timeout=60))
        try:
            _exec_text(j, yes)
            e2 = ""
        except pyodbc.Error as ex:
            e2 = str(ex)
        check("стенд L09 (р43б С-1): smoke с ключом yes при «работающей стойке» (10 соединений одного процесса без имени программы) — отказ "
              "50091, ничего не сделано", "50091" in e2 and tuple(count()) == before, e2[:160])
    finally:
        for c in pool:
            c.close()
        j.cursor().execute("IF OBJECT_ID(N'master.dbo.AsdaL09StandMarker', N'U') IS NULL CREATE TABLE master.dbo.AsdaL09StandMarker (Id INT)")


def _md5(cn):
    return cn.cursor().execute("SELECT CONVERT(VARCHAR(32), HASHBYTES('MD5', CONVERT(VARBINARY(MAX), OBJECT_DEFINITION(OBJECT_ID(N'dbo.UPUserLogin')))), 2)"
                               ).fetchone()[0]


class _Drain:
    """Курсор, который после каждого запроса дочитывает все ответы (без MARS иначе «Connection is busy»)."""

    def __init__(self, cn):
        self.cn = cn

    def execute(self, sql, params=()):
        cur = self.cn.cursor()
        cur.execute(sql, params) if params else cur.execute(sql)
        while cur.nextset():
            pass
        cur.close()


def _login(cn, login, pw="e10adc3949ba59abbe56e057f20f883e"):
    cur = cn.cursor()
    r = cur.execute("SET NOCOUNT ON; EXEC dbo.UPUserLogin ?, ?, '127.0.0.1', 0, '', '', '', ''", (login, pw)).fetchone()
    while cur.nextset():                     # дочитать ответ (без MARS соединение иначе занято)
        pass
    cur.close()
    return int(r[0]), int(r[7])


def sandbox(check, ldb):
    import pyodbc
    srv = r"(localdb)\%s" % INSTANCE
    conn = lambda database: pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=%s;DATABASE=%s;Trusted_Connection=yes;" % (srv, database),
                                           autocommit=True, timeout=60)
    _localdb("stop", INSTANCE, "-k")
    _localdb("delete", INSTANCE)
    c = _localdb("create", INSTANCE, "-s")
    if c.returncode != 0:
        return check("стенд L09: свой экземпляр LocalDB %s создан" % INSTANCE, False, c.stdout[-300:] + c.stderr[-300:])
    try:
        _sandbox(check, conn)
    finally:
        _localdb("stop", INSTANCE, "-k")
        _localdb("delete", INSTANCE)


def _sandbox(check, conn):
    import pyodbc
    import shutil
    import tempfile
    m = conn("master")
    # файлы баз — в своей временной папке: в папке профиля по умолчанию могут лежать чужие Joy1.mdf (другие стенды), DROP DATABASE их не тронет
    fdir = tempfile.mkdtemp(prefix="asda_l09_stand_")
    admin_db = "AsdaAdminL09_" + secrets.token_hex(3)
    made = []

    def mk(d, coll):
        f = os.path.join(fdir, d)
        m.cursor().execute("CREATE DATABASE [%s] ON (NAME = N'%s', FILENAME = N'%s.mdf') LOG ON (NAME = N'%s_log', FILENAME = N'%s_log.ldf') "
                           "COLLATE %s" % (d, d, f, d, f, coll))
        made.append(d)
    try:
        for d in ("Joy1", "AsdaStoryOP", "JoyLog1"):
            mk(d, "Arabic_CI_AS")
        mk(admin_db, "Cyrillic_General_CI_AS")
        # ★ ревизия 43б С-1: метка стенда — по ней (и по LocalDB) l09_10_smoke.sql узнаёт стенд; на живой базе её нет
        m.cursor().execute("IF OBJECT_ID(N'master.dbo.AsdaL09StandMarker', N'U') IS NULL CREATE TABLE master.dbo.AsdaL09StandMarker (Id INT)")
        _sandbox_body(check, conn, admin_db)
    finally:
        for d in made:
            try:
                m.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [%s]" % (d, d))
            except pyodbc.Error:
                pass
        m.close()
        shutil.rmtree(fdir, ignore_errors=True)


def _sandbox_body(check, conn, admin_db):
    import pyodbc
    for d, stmts in STAND_SQL.items():
        cn = conn(d)
        for s in stmts:
            cn.cursor().execute(s)
        cn.close()
    j = conn("Joy1")
    j.cursor().execute(open(os.path.join(SQLDIR, "l09_fn_ac_pwhash.def.sql"), encoding="utf-8").read())
    j.cursor().execute(open(os.path.join(SQLDIR, "l09_upuserlogin_before.def.sql"), encoding="utf-8", newline="").read())
    md0 = _md5(j)
    check("стенд L09: UPUserLogin создана из живого текста (AstoryServer/Docs/SQL/l09_upuserlogin_before.def.sql) — md5 тела = живому C19F6E7C…",
          md0 == WANT_MD5, md0)
    # отказ на чужом теле
    j.cursor().execute("DROP PROCEDURE dbo.UPUserLogin")
    alt = open(os.path.join(SQLDIR, "l09_upuserlogin_before.def.sql"), encoding="utf-8", newline="").read().replace("SET @MaxFail = 10", "SET @MaxFail = 11")
    j.cursor().execute(alt)
    try:
        _exec_file(j, os.path.join(SQLDIR, "l09_01_migrate.sql"))
        refused = False
    except pyodbc.Error as ex:
        refused = "50021" in str(ex) or "md5" in str(ex)
    d_alt = j.cursor().execute("SELECT CHARINDEX(N'[L09-GATE]', OBJECT_DEFINITION(OBJECT_ID(N'dbo.UPUserLogin')))").fetchone()[0]
    check("стенд L09: миграция на ЧУЖОМ теле (другая константа) — отказ 50021, тело не тронуто, копии нет",
          refused and d_alt == 0 and j.cursor().execute("SELECT OBJECT_ID(N'dbo.UPUserLogin_bak_20261121_l09')").fetchone()[0] is None)
    j.cursor().execute("DROP PROCEDURE dbo.UPUserLogin")
    j.cursor().execute(open(os.path.join(SQLDIR, "l09_upuserlogin_before.def.sql"), encoding="utf-8", newline="").read())
    check("стенд L09: тело восстановлено из живого текста (md5 C19F6E7C…)", _md5(j) == WANT_MD5)
    res = _exec_file(j, os.path.join(SQLDIR, "l09_01_migrate.sql"))
    md1 = _md5(j)
    ok1 = any(r and r[0][0] == "l09_01_migrate: OK" and r[0][1] == 0 for r in res)
    check("стенд L09: l09_01_migrate — врезка поставлена, копия тела есть, итог «OK», режим 0", ok1 and md1 != WANT_MD5, res[-1:])
    bak = j.cursor().execute("SELECT CONVERT(VARCHAR(32), HASHBYTES('MD5', CONVERT(VARBINARY(MAX), REPLACE(OBJECT_DEFINITION(OBJECT_ID("
                             "N'dbo.UPUserLogin_bak_20261121_l09')) COLLATE Latin1_General_BIN2, N'CREATE PROC [dbo].[UPUserLogin_bak_20261121_l09]', "
                             "N'CREATE PROC [dbo].[UPUserLogin]'))), 2)").fetchone()[0]
    check("стенд L09: копия dbo.UPUserLogin_bak_20261121_l09 = прежнее тело (с прежним именем md5 C19F6E7C…)", bak == WANT_MD5, bak)
    cur_def = j.cursor().execute("SELECT OBJECT_DEFINITION(OBJECT_ID(N'dbo.UPUserLogin'))").fetchone()[0]
    before = open(os.path.join(SQLDIR, "l09_upuserlogin_before.def.sql"), encoding="utf-8", newline="").read()
    gs, ge = cur_def.index("\t-- ★ [L09-GATE]"), cur_def.index("-- [/L09-GATE]\n\n") + len("-- [/L09-GATE]\n\n")
    check("стенд L09: тело с врезкой = прежнее тело + ровно один блок [L09-GATE] перед «IF ( @id1=@id AND @block =0  )», остальное байт в байт",
          cur_def[:gs] + cur_def[ge:] == before and cur_def[ge:].startswith("\tIF ( @id1=@id AND @block =0  )") and cur_def.count("[L09-GATE]") == 1)
    _exec_file(j, os.path.join(SQLDIR, "l09_01_migrate.sql"))
    check("стенд L09: повторная миграция — «врезка уже стоит», тело то же", _md5(j) == md1)
    # ★ ревизия 43б С-1: защита smoke безусловная — без метки стенда (как на живой базе, где учёток меньше 100) отказ без ключа; с ключом —
    #   отказ при «работающей стойке» (процесс с пулом ≥ 10 соединений без имени программы)
    _smoke_guard(check, conn, j)
    # дымовая проверка — тем же файлом, что для живой базы
    res = _exec_file(j, os.path.join(SQLDIR, "l09_10_smoke.sql"))
    total = res[-1][0][0] if res and res[-1] else ""
    fails = [r for r in (res[-2] if len(res) > 1 else []) if r[1] != "OK"]
    check("стенд L09: l09_10_smoke — %s (все ветки: Mode 0 — оба входят, Mode 1 — игровая 28 без пометки «вошла», неверный пароль 3, нет учётки "
          "2, служебная 1, «в игре» 28 вместо 4, блок 5, выключение)" % total, bool(re.match(r"ok=\d+ fail=0$", total)) and not fails, fails[:3])
    check("стенд L09: после дымовой проверки всё откачено (учёток 0, режим 0)", j.cursor().execute(
        "SELECT (SELECT COUNT(*) FROM AsdaStoryOP.dbo.us_member) + (SELECT Mode FROM adm.LoginMaintenance WHERE Id = 1)").fetchone()[0] == 0)
    # ★ ревизия 43 Н-1: таблицу режима удалили вручную (не откатом) — вход идёт как без режима, а не падает у всех
    jd = _Drain(j)
    jd.execute("SET NOCOUNT ON; INSERT AsdaStoryOP.dbo.us_member (Us_id, us_block, us_rdate, igsNID, Realcash, BonusCash, Poridx, UserNum, Flag, "
               "us_pwhash, us_pwsalt, us_pwfail) SELECT 'n1_pl', 0, GETDATE(), 0, 0, 0, 3, -1, 0, "
               "dbo.FN_AC_PwHash(0x02, 'e10adc3949ba59abbe56e057f20f883e'), 0x02, 0")
    jd.execute("EXEC adm.LoginMaintenanceSet 1, N'n1', NULL")
    jd.execute("DROP TABLE adm.LoginMaintenance")
    try:
        st = _login(j, "n1_pl")
    except pyodbc.Error as ex:
        st = ("ошибка", str(ex)[:120])
    check("стенд L09 (р43 Н-1): таблицу режима удалили вручную при Mode 1 — вход игровой учётки идёт как без режима (1), без ошибки 208",
          st[0] == 1, st)
    res = _exec_file(j, os.path.join(SQLDIR, "l09_01_migrate.sql"))
    check("стенд L09 (р43 Н-1): повторная миграция пересоздаёт таблицу (Mode 0), md5 прежнего тела возвращается из копии, итог «OK»",
          any(r and r[0][0] == "l09_01_migrate: OK" and r[0][1] == 0 for r in res) and _md5(j) == md1, res[-1:])
    jd.execute("SET NOCOUNT ON; DELETE AsdaStoryOP.dbo.us_member; DELETE JoyLog1.dbo.Loginfo")
    # права как у панели
    jc = j.cursor()
    jc.execute("CREATE USER t_ops WITHOUT LOGIN; GRANT EXECUTE ON adm.LoginMaintenanceSet TO t_ops; DENY INSERT, UPDATE, DELETE ON adm.LoginMaintenance TO t_ops; "
               "DENY EXECUTE ON SCHEMA::dbo TO t_ops")
    jc.execute("CREATE USER t_admin WITHOUT LOGIN; ALTER ROLE db_datareader ADD MEMBER t_admin; DENY INSERT, UPDATE, DELETE, EXECUTE TO t_admin; "
               "GRANT VIEW DEFINITION ON dbo.UPUserLogin TO t_admin")
    jc.execute("CREATE USER t_blind WITHOUT LOGIN; ALTER ROLE db_datareader ADD MEMBER t_blind")
    jc.execute("EXECUTE AS USER = 't_ops'")
    r1 = jc.execute("SET NOCOUNT ON; EXEC adm.LoginMaintenanceSet 1, N't_ops', N'проверка прав'").fetchone()
    try:
        jc.execute("UPDATE adm.LoginMaintenance SET Mode = 0 WHERE Id = 1")
        upd = True
    except pyodbc.Error:
        upd = False
    try:
        jc.execute("EXEC dbo.UPUserLogin 'x', 'y', '1', 0, '', '', '', ''")
        ex_ul = True
    except pyodbc.Error:
        ex_ul = False
    jc.execute("REVERT")
    check("стенд L09, права asda_ops: adm.LoginMaintenanceSet исполняется (цепочка владения dbo), прямой UPDATE таблицы и EXEC UPUserLogin — нет",
          r1 is not None and int(r1[1]) == 1 and not upd and not ex_ul, (r1, upd, ex_ul))
    jc.execute("EXECUTE AS USER = 't_admin'")
    g_admin = jc.execute("SELECT CHARINDEX(N'[L09-GATE]', OBJECT_DEFINITION(OBJECT_ID(N'dbo.UPUserLogin'))), "
                         "(SELECT Mode FROM adm.LoginMaintenance WHERE Id = 1)").fetchone()
    try:
        jc.execute("EXEC adm.LoginMaintenanceSet 0, N't_admin', NULL")
        ex_set = True
    except pyodbc.Error:
        ex_set = False
    jc.execute("REVERT")
    jc.execute("EXECUTE AS USER = 't_blind'")
    g_blind = jc.execute("SELECT OBJECT_DEFINITION(OBJECT_ID(N'dbo.UPUserLogin'))").fetchone()[0]
    jc.execute("REVERT")
    check("стенд L09, права asda_admin: тело UPUserLogin видно (врезка подтверждается), режим читается, сменить его нельзя; без VIEW DEFINITION "
          "тело = NULL — поэтому «не прочитано», а не «врезки нет»", g_admin[0] > 0 and int(g_admin[1]) == 1 and not ex_set and g_blind is None,
          (tuple(g_admin), ex_set))
    j.cursor().execute("EXEC adm.LoginMaintenanceSet 0, N'стенд', NULL")
    j.close()
    _panel_on_stand(check, conn, admin_db)
    # откат байт в байт и повтор
    j = conn("Joy1")
    _exec_file(j, os.path.join(SQLDIR, "l09_99_rollback.sql"))
    gone = j.cursor().execute("SELECT OBJECT_ID(N'adm.LoginMaintenance'), OBJECT_ID(N'adm.LoginMaintenanceSet')").fetchone()
    check("стенд L09: l09_99_rollback — тело UPUserLogin снова = живому до врезки (md5 C19F6E7C…), таблица и процедура удалены",
          _md5(j) == WANT_MD5 and gone[0] is None and gone[1] is None, _md5(j))
    _exec_file(j, os.path.join(SQLDIR, "l09_99_rollback.sql"))
    check("стенд L09: повторный откат — «врезки нет», без ошибки", _md5(j) == WANT_MD5)
    j.cursor().execute("INSERT AsdaStoryOP.dbo.us_member (Us_id, us_block, us_rdate, igsNID, Realcash, BonusCash, Poridx, UserNum, Flag, us_pwhash, us_pwsalt, "
                       "us_pwfail) SELECT 'after_rb', 0, GETDATE(), 0, 0, 0, 3, -1, 0, dbo.FN_AC_PwHash(0x00, 'e10adc3949ba59abbe56e057f20f883e'), 0x00, 0")
    st = _login(j, "after_rb")
    check("стенд L09: после отката процедура работает как до L09 (вход игровой учётки → 1)", st[0] == 1, st)
    j.cursor().execute("DELETE AsdaStoryOP.dbo.us_member; DELETE JoyLog1.dbo.Loginfo")
    res = _exec_file(j, os.path.join(SQLDIR, "l09_01_migrate.sql"))
    check("стенд L09: цикл «откат → применение» повторяется (врезка снова на месте)", any(r and r[0][0] == "l09_01_migrate: OK" for r in res)
          and _md5(j) == md1)
    j.close()


def _panel_on_stand(check, conn, admin_db):
    """Операции панели на настоящей процедуре стенда: чтение — как asda_admin (GameReader), запись — как asda_ops (GameWriter), журнал —
    своя AsdaAdmin стенда; мост — подставной (узлов нет: «не прочитано»), журнал патчей — подстановка «L09 не действует»."""
    import datetime
    from core import bridge, config, db, jobs, ops
    from domains import maint as M
    cn = conn(admin_db)
    for f in ("adminc_02_schema.sql", "adminc_14_jobs.sql"):
        for b in _batches(open(os.path.join(ROOT, "sql", f), encoding="utf-8").read()):
            cn.cursor().execute(b)
    cn.close()

    class NoBridge:
        def nodes(self):
            return []

        def presence(self, uid=None):
            return []
    saved = (M.DLL_READ, config.get().on_server)
    db.set_override("admin", lambda database: conn(admin_db))
    db.set_override("game", lambda database: conn({"AsdaStoryOp": "AsdaStoryOP", "joylog1": "JoyLog1"}.get(database, database)))
    db.set_override("ops", lambda database: conn({"AsdaStoryOp": "AsdaStoryOP"}.get(database, database)))
    bridge.set_fake(NoBridge())
    M.DLL_READ = lambda: {"read": True, "error": "", "dll_md5": "2dcf9be9008975242692421fe376799d", "lm_start": "x", "log_file": "f", "head": "h",
                          "found": True, "l09_ok": False, "total": "t"}
    M._dll_cache.update(at=0.0, data=None)
    config.get().on_server = False
    cli = ops.Ctx(None, "cli:stand@pc", "owner", "", "cli")
    try:
        s = M.state(force=True)
        check("панель на стенде: state() — SQL L09 прочитан (таблица и врезка есть, режим 0), DLL «не действует», мост «не прочитано»",
              s["ready"] and s["sql"]["mode"] == 0 and s["dll"]["active"] is False and not s["players"]["bridge_read"], s["sql"])
        res = ops.run(cli, "maint.on", {"confirm": "maint", "silent": "silent", "reason": "стенд"})
        q = M.sql_state()
        check("панель на стенде: maint.on (без объявления, явно) — adm.LoginMaintenanceSet под записью, Mode 1, кто и причина записаны",
              q["mode"] == 1 and q["changed_by"] == "cli:stand@pc" and q["reason"] == "стенд" and res["message"].startswith(M.ON_DONE), q)
        j = conn("Joy1")
        jc = _Drain(j)
        jc.execute("INSERT AsdaStoryOP.dbo.us_member (Us_id, us_block, us_rdate, igsNID, Realcash, BonusCash, Poridx, UserNum, Flag, us_pwhash, us_pwsalt, "
                   "us_pwfail) SELECT 'stand_pl', 0, GETDATE(), 0, 0, 0, 3, -1, 0, dbo.FN_AC_PwHash(0x01, 'e10adc3949ba59abbe56e057f20f883e'), 0x01, 0")
        jc.execute("SET IDENTITY_INSERT AsdaStoryOP.dbo.us_member ON; INSERT AsdaStoryOP.dbo.us_member (Userindex, Us_id, us_block, us_rdate, igsNID, "
                   "Realcash, BonusCash, Poridx, UserNum, Flag, us_pwhash, us_pwsalt, us_pwfail) SELECT 3, 'stand_op', 0, GETDATE(), 0, 0, 0, 3, -1, 0, "
                   "dbo.FN_AC_PwHash(0x01, 'e10adc3949ba59abbe56e057f20f883e'), 0x01, 0; SET IDENTITY_INSERT AsdaStoryOP.dbo.us_member OFF")
        a, b = _login(j, "stand_pl"), _login(j, "stand_op")
        check("стенд: включено панелью — игровая учётка получает 28 (Userindex 0), служебная 3 входит (1)", a == (28, 0) and b == (1, 3), (a, b))
        gc = j.cursor()
        g1 = gc.execute("SET NOCOUNT ON; EXEC adm.LoginMaintenanceGate 6001").fetchone()[0]
        while gc.nextset():
            pass
        gc.close()
        q2 = M.sql_state()
        check("стенд (р43 С-1): включено панелью — гейт входа в мир (его спрашивает LoginPatch L09 на 1016) отказывает учётке 6001, «Состояние» "
              "видит счётчик отказов входа в мир", int(g1) == 1 and q2.get("world_refused") == 1, (g1, q2.get("world_refused")))
        r = _refused(lambda: ops.run(cli, "maint.on", {"confirm": "maint", "silent": "silent"}), "уже включён")
        check("панель на стенде: повторное включение — отказ «уже включён»", r[0], r[1])
        res = ops.run(cli, "maint.off", {"confirm": "maint"})
        check("панель на стенде: maint.off — Mode 0, итог «отказано входов: 1, допущено служебных: 1»",
              M.sql_state()["mode"] == 0 and "отказано входов: 1" in res["message"] and "допущено служебных: 1" in res["message"], res["message"])
        jc.execute("UPDATE AsdaStoryOP.dbo.us_member SET Flag = 0")
        check("стенд: выключено — игровая учётка снова входит", _login(j, "stand_pl")[0] == 1)
        jc.execute("UPDATE AsdaStoryOP.dbo.us_member SET Flag = 0")
        # по расписанию: задание службы
        now = jobs.utc_now()
        at = now + datetime.timedelta(minutes=5)
        jid = jobs.add("maint.on", {"confirm": "maint", "silent": "silent"}, "service", at, "", "", "cli:stand@pc", None, "owner")
        out = jobs.run_due("service", now=at + datetime.timedelta(seconds=5))
        row = jobs.get(jid)
        check("стенд: задание maint.on исполнено службой в срок — done, Mode 1, игровая учётка — 28",
              row["status"] == "done" and M.sql_state()["mode"] == 1 and _login(j, "stand_pl")[0] == 28, (out, row["status"], row.get("result")))
        jid2 = jobs.add("maint.off", {"confirm": "maint"}, "service", at, "", "", "cli:stand@pc", None, "owner")
        jobs.run_due("service", now=at + datetime.timedelta(seconds=6))
        check("стенд: задание maint.off — done, Mode 0", jobs.get(jid2)["status"] == "done" and M.sql_state()["mode"] == 0, jobs.get(jid2)["result"])
        ca = conn(admin_db)
        acts = [tuple(r) for r in ca.cursor().execute("SELECT action, result FROM adm.audit WHERE action LIKE 'maint.%' ORDER BY id").fetchall()]
        ca.close()
        check("стенд: журнал adm.audit — maint.on ok, отказ refused, maint.off ok, задания (via job) ok",
              acts.count(("maint.on", "ok")) == 2 and ("maint.on", "refused") in acts and acts.count(("maint.off", "ok")) == 2, acts)
        jc.execute("DELETE AsdaStoryOP.dbo.us_member; DELETE JoyLog1.dbo.Loginfo")
        j.close()
    finally:
        db.set_override("admin", None)
        db.set_override("game", None)
        db.set_override("ops", None)
        bridge.set_fake(None)
        M.DLL_READ, config.get().on_server = saved
        M._dll_cache.update(at=0.0, data=None)


# ─────────────────────────────── живой блок (только чтение) ───────────────────────────────

def live(check):
    from core import config, db, ops
    from domains import maint as M
    from domains import load_all
    load_all()      # ★ ревизия 87 Н-1 (24.11): разделы — как у службы и консоли; иначе операция чужого раздела — «неизвестная операция»
    if config.get().on_server:
        return check("живой самотест А5.3 — с ПК (SSH)", True)
    s = M.sql_state()
    check("живая Joy1: состояние SQL L09 прочитано (таблица %s, врезка %s, режим %s)" % (s.get("table"), s.get("gate"), s.get("mode")),
          s["read"], s.get("error"))
    with db.GameReader("joy1") as j:
        p = j.one("SELECT HAS_PERMS_BY_NAME('dbo.UPUserLogin','OBJECT','VIEW DEFINITION') AS v, HAS_PERMS_BY_NAME('dbo.UPUserLogin','OBJECT','EXECUTE') AS e, "
                  "CONVERT(VARCHAR(32), HASHBYTES('MD5', CONVERT(VARBINARY(MAX), OBJECT_DEFINITION(OBJECT_ID(N'dbo.UPUserLogin')))), 2) AS md5")
    check("живая Joy1: asda_admin видит тело UPUserLogin (VIEW DEFINITION = 1), исполнять не может (EXECUTE = 0); md5 тела — %s"
          % ("живое до L09 C19F6E7C…" if p["md5"] == WANT_MD5 else p["md5"]), p["v"] == 1 and p["e"] == 0, p)
    if p["md5"] == WANT_MD5:
        check("живая Joy1: SQL L09 НЕ применён (тело — до врезки, таблицы нет) — так и ожидается до слова владельца",
              s["table"] is False and s["gate"] is False, s)
    d = M.dll_state(force=True)
    check("живой LoginManager: журнал патчей прочитан по SSH, последний запуск найден; L09 %s (LoginPatch.dll %s)"
          % ("действует" if d.get("active") else "не действует", d.get("dll_md5")),
          d.get("read") and d.get("active") is not None, d.get("error"))
    pl = M.players_state()
    check("живой мост: кто в игре прочитан или честно «не прочитано» (%s); БД: вошли вне 1…5000 = %s"
          % ("прочитано" if pl["bridge_read"] else pl["bridge_error"], pl["db_logged"]), pl["db_read"], pl["db_error"])
    cli = ops.Ctx(None, "cli:selftest@pc", "owner", "", "cli")
    try:
        prev = ops.run(cli, "maint.on", {"confirm": "maint", "silent": "silent"}, dry=True)["preview"]
        r = (False, "сухой предпросмотр прошёл: %s" % prev["text"])
        ready = True
    except ops.OpRefused as ex:
        r, ready = (True, str(ex)), False
    if not s.get("table") or not s.get("gate"):
        check("живой сухой предпросмотр maint.on: SQL L09 не применён — честный отказ «не применена … по слову владельца» (ничего не записано)",
              r[0] and "SQL-часть L09 не применена" in r[1], r[1])
    else:
        check("живой сухой предпросмотр maint.on (SQL L09 применён): предпросмотр без записи, режим не включён", ready and M.sql_state()["mode"] == s["mode"], r[1])
