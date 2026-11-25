# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_events_a5.py — самотест шага А5.4 «События и сбросы» (21.11.2026; domains/events.py, domains/cs_kinds/eventdata.py,
sql/adminc_15_events.sql, мост P127 v84).

offline(check) — на подменах (файлы стойки, часы сервера, мост, задания, Joy1): разбор Event.dat и окон без года, счастливые часы как
                 у загрузчика, состояние и его предупреждения, проверки event.set / event.off / rank.recalc / daily.reset (подтверждения,
                 сильный рейт, паритет каналов, пересечения, оператор, команды моста и их аргументы, подтверждение по Event.dat, задание
                 выключения), набор изменений «Счастливые часы» (добавить / убрать / пересечение / прошедшие даты / копии), права, консоль,
                 исходники DLL v84 и выкладчика, SQL, веб, переводы EN.
sandbox(check, ldb) — adm.LimitationReset на своей базе LocalDB (догнать / внеочередной / метка журнала / неверный режим) и daily.reset
                 через настоящий GameWriter.
live(check)    — только чтение и сухие предпросмотры: Event.dat ×3 NpcServer и зеркала GS, GameServerEvent.txt ×3, журнал сброса и задача
                 ОС, узлы моста; event.set / rank.recalc на узлах без v84 — честный отказ. Живые события, рейты и сбросы НЕ включаются.
Побочных эффектов при импорте нет.
"""
import datetime
import os
import re
import secrets
import struct
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
AP = os.path.join(PORT, "AstoryServer", "Patches", "AsdaPatch")
CYR = re.compile("[А-Яа-яЁё]")
NOW = datetime.datetime(2026, 11, 21, 3, 30)
LAYOUT = [("s_mon", 0, "B", 1), ("s_day", 100, "B", 1), ("s_hour", 200, "B", 1), ("s_min", 300, "B", 1), ("s_time", 400, "i", 4),
          ("e_mon", 800, "B", 1), ("e_day", 900, "B", 1), ("e_hour", 1000, "B", 1), ("e_min", 1100, "B", 1), ("e_time", 1200, "i", 4),
          ("value", 1600, "f", 4), ("min_level", 2000, "B", 1), ("max_level", 2100, "B", 1)]


def mk_dat(entries):
    """Event.dat 2200 б по записям {(тип, карта): (s(мес, день, час, мин), e(...), значение)}."""
    b = bytearray(2200)
    for (t, m), (s, e, v) in entries.items():
        i = 50 * t + m
        vals = {"s_mon": s[0], "s_day": s[1], "s_hour": s[2], "s_min": s[3], "s_time": s[3] + 100 * s[2] + 10000 * s[1] + 1000000 * s[0],
                "e_mon": e[0], "e_day": e[1], "e_hour": e[2], "e_min": e[3], "e_time": e[3] + 100 * e[2] + 10000 * e[1] + 1000000 * e[0],
                "value": v, "min_level": 1, "max_level": 100}
        for n, o, f, sz in LAYOUT:
            struct.pack_into("<" + f, b, o + sz * i, vals[n])
    return bytes(b)


MAPINFO = ("[MAPINFO]\r\nMapCount = 3 \r\nServerName_000=\"Sillaris\" \r\nServerName_001=\"Rein\" \r\nServerName_002=\"Conquester\" \r\n").encode()
LUCKY = b"3\r\n2026\t11\t21\t0\t1\t1.0\r\n2026\t11\t21\t2\t5\t0.5\r\n2026\t11\t22\t10\t11\t1.0\r\n"


class _Files:
    """Подмена чтения стойки: словарь путей; Event.dat NpcServer после команды моста меняется на after (если задан)."""

    lucky = LUCKY                   # ★ ревизия 44: счастливые часы для проверки сложения с событием опыта (по умолчанию — LUCKY)

    def __init__(self, dat, after=None, fail_after=False):
        self.dat, self.after, self.sent, self.fail_after, self.dat_reads, self.first_read = dat, after, False, fail_after, 0, None

    def __call__(self, rels):
        out = {}
        if self.sent and self.fail_after:
            raise OpRefusedT("файлы событий стойки не прочитаны: ssh: timeout")
        for r in rels:
            if r.endswith("Event\\Event.dat"):
                if self.sent:
                    self.dat_reads += 1
                    self.first_read = self.first_read or time.time()
                out[r] = self.after if (self.sent and self.after is not None and "NpcServer" in r) else self.dat.get(r.split("\\")[0], self.dat.get("*"))
            elif r.endswith("GameServerEvent.txt"):
                out[r] = self.lucky
            elif r.endswith("MapInfo.ini"):
                out[r] = MAPINFO
            else:
                out[r] = None
        return out


class OpRefusedT(Exception):
    """Заглушка: настоящий OpRefused подставляется в offline() (импорт core.ops — только внутри функций, без побочных эффектов)."""


def offline(check):
    global OpRefusedT
    from core.ops import OpRefused as _OR
    OpRefusedT = _OR
    from core import auth, audit, bridge, i18n, jobs, ops
    import domains.events as V
    from domains.cs_kinds import eventdata as L
    from domains import shopdata as E
    # ── разбор Event.dat и окна без года ──
    d = V.decode_dat(mk_dat({(1, 0): ((11, 10, 22, 9), (11, 11, 22, 9), 2.0), (0, 2): ((10, 17, 0, 0), (11, 17, 0, 0), 3.0)}))
    check("Event.dat: 2200 б → записи (тип, карта); MMDDчмм как у сервера (11.10 22:09 = 11102209); короче — None (NpcServer не стартует)",
          d[(1, 0)]["s_time"] == 11102209 and d[(0, 2)]["value"] == 3.0 and V.decode_dat(b"\0" * 2199) is None and V.entry_empty(d[(0, 0)]))
    check("окно без года: 21.11 03:30 — опыт 10.11…11.11 прошёл, повторится; добыча 17.10…17.11 прошла; 01.12…05.12 впереди; конец ≤ начала — никогда",
          V.phase(d[(1, 0)], NOW) == "past" and V.phase(d[(0, 2)], NOW) == "past"
          and V.phase(V.decode_dat(mk_dat({(1, 1): ((12, 1, 0, 0), (12, 5, 0, 0), 2.0)}))[(1, 1)], NOW) == "ahead"
          and V.phase(V.decode_dat(mk_dat({(1, 1): ((12, 30, 0, 0), (1, 2, 0, 0), 2.0)}))[(1, 1)], NOW) == "never"
          and V.phase(V.decode_dat(mk_dat({(1, 1): ((11, 20, 0, 0), (11, 22, 0, 0), 2.0)}))[(1, 1)], NOW) == "active")
    n, rows, err = V.lucky_rows(LUCKY)
    check("счастливые часы: как загрузчик sub_4190E0 (N, строки по 6 слов); сейчас 03:30 21.11 — первая подходящая строка 02–05 (+0.5)",
          n == 3 and err is None and V.lucky_now(rows, NOW) == (2026, 11, 21, 2, 5, 0.5) and V.lucky_now(rows, NOW.replace(hour=6)) is None)
    check("счастливые часы: слова не ложатся построчно (N ≠ строк) — ошибка разбора, а не «пусто»",
          V.lucky_rows(b"5\r\n2026\t11\t21\t0\t1\t1.0\r\n")[2] is not None and V.lucky_rows(None)[2] == "не прочитан")
    # ── состояние ──
    saved = (V.READ, V.CLOCK, V.SQL, bridge.nodes, bridge.presence, bridge.call, V._gm_uids, jobs.list_jobs, jobs.add, audit.write,
             auth.totp_confirm, V.VERIFY_S, V.VERIFY_STEP, V.VERIFY_FIRST, V.STAT, jobs.cancel)
    calls, added = [], []
    try:
        V.CLOCK = lambda: (NOW, NOW - datetime.timedelta(hours=3))
        dat_past = mk_dat({(1, 0): ((11, 10, 22, 9), (11, 11, 22, 9), 2.0), (1, 1): ((11, 10, 22, 9), (11, 11, 22, 9), 2.0),
                           (1, 2): ((11, 10, 22, 9), (11, 11, 22, 9), 2.0)})
        V.READ = _Files({"*": dat_past, "Ch2_NpcServer": mk_dat({}), "Indun_GameServer": b"\0" * 100})
        bridge.nodes = lambda: [{"node": g, "mode": 1, "ver": 84, "fresh": True} for g in V.GS]
        st = V.state()
        ws = " | ".join(st["warnings"])
        check("состояние: прошедшее окно — «включит его снова 10.11 следующего года»; NpcServer ≠ Ch2_NpcServer — «паритет Ch2 … код 6»; "
              "зеркало GS короче 2200 — «счастливые часы не загрузятся»; расписаны до 2026-11-22",
              "10.11 следующего года" in ws and "код 6" in ws and "не загрузятся" in ws and "до 2026-11-22" in ws and not st["npc_same"]
              and st["map_count"] == 3 and st["maps"] == ["Sillaris", "Rein", "Conquester"], ws)
        check("состояние: окна сгруппированы по одинаковым копиям (опыт: 3 карты в NpcServer и Indun_NpcServer), фаза past",
              [(w["type"], w["maps"], w["copies"], w["phase"]) for w in st["windows"]] == [(1, [0, 1, 2], ["Indun_NpcServer", "NpcServer"], "past")],
              st["windows"])
        # ★ А5.10: значок события у игроков — по версии узла (P128 — v85+)
        check("А5.10 состояние: значок события у v84 — «только оператору (нужна DLL v85)» на всех GS",
              st["badge_all"] == {g: False for g in V.GS} and st["badge_ver"] == 85 and set(st["badge_why"].values()) == {"ver"}
              and all(t == "только оператору (нужна DLL v85)" for t in st["badge_text"].values()), st["badge_text"])
        # ★ ревизия 49 Н-1: по ФАКТУ установки P128 (режим секции по журналу патчей), узел без пульса — «не прочитано»
        from domains import patchcfg as PCF
        _pcf = PCF.state
        try:
            PCF.state = lambda force=False, dll_only=None: {"dlls": [{"dll": "AsdaPatch", "sections": [{"name": "P128_EventBadgeAll", "modes": {
                "GameServer": "active", "Indun_GameServer": "off", "Ch2_GameServer": "active"}}]}]}
            bridge.nodes = lambda: [{"node": g, "mode": 1, "ver": 85, "fresh": g != "Ch2_GameServer"} for g in V.GS]
            b1 = V.badge_state()
            PCF.state = lambda force=False, dll_only=None: {"dlls": [{"dll": "AsdaPatch", "sections": [{"name": "P128_EventBadgeAll", "modes": {
                "GameServer": "failed", "Indun_GameServer": "absent", "Ch2_GameServer": "unread"}}]}]}
            bridge.nodes = lambda: [{"node": g, "mode": 1, "ver": 85, "fresh": True} for g in V.GS]
            b2 = V.badge_state()
            def _boom(force=False, dll_only=None):
                raise OpRefusedT("нет SSH")
            PCF.state = _boom
            b3 = V.badge_state()
        finally:
            PCF.state = _pcf
        check("ревизия 49 Н-1: значок по факту P128 — active → всем; off → «выключен»; узел без пульса → «не прочитано», а не «нужна DLL»; "
              "failed / absent / unread; журнал не прочитан → «не прочитано»",
              b1 == ({"GameServer": True, "Indun_GameServer": False, "Ch2_GameServer": None},
                     {"GameServer": "all", "Indun_GameServer": "off", "Ch2_GameServer": "nopulse"})
              and b2 == ({"GameServer": False, "Indun_GameServer": False, "Ch2_GameServer": None},
                         {"GameServer": "failed", "Indun_GameServer": "absent", "Ch2_GameServer": "unread"})
              and b3[1] == {g: "unread" for g in V.GS} and b3[0] == {g: None for g in V.GS}, (b1, b2, b3))
        bridge.nodes = lambda: [{"node": g, "mode": 1, "ver": 84, "fresh": True} for g in V.GS]
        check("А5.10 тип 0 назван честно: «добыча и золото» (шансы дропа и золота, не сумма)",
              V.TYPE_NAMES[0] == "добыча и золото" and "сумму золота в кучке не меняет" in open(V.__file__, encoding="utf-8").read())
        # ── параметры события ──
        _Files.lucky = LUCKY.replace(b"2026\t11\t22\t10\t11", b"2026\t11\t25\t10\t11")     # счастливые часы вне окна base
        cli = ops.Ctx(None, "cli:t", "owner", "", "cli")
        adm = ops.Ctx(7, "adm1", "admin", "", "web")
        audit.write = lambda *a, **k: 1

        def refused(name, p, ctx=cli, part=""):
            try:
                ops.run(ctx, name, p, dry=True)
            except ops.OpRefused as ex:
                return part in str(ex) or (print("    отказ:", ex) and False)
            return False

        def why(name, p, ctx=cli):
            """Текст отказа предпросмотра или «» (без печати)."""
            try:
                ops.run(ctx, name, p, dry=True)
            except ops.OpRefused as ex:
                return str(ex)
            return ""
        base = {"type": 1, "value": "2.0", "start": "2026-11-22 10:00", "end": "2026-11-23 10:00", "confirm": "event"}
        jobs.list_jobs = lambda limit=100, active=False: []
        check("event.set: окно через новый год — отказ «не сработает никогда»; конец ≤ начала; значение > 10 и не число — отказ",
              refused("event.set", dict(base, start="2026-12-30 10:00", end="2027-01-02 10:00"), part="через новый год")
              and refused("event.set", dict(base, end="2026-11-22 09:00"), part="не позже начала")
              and refused("event.set", dict(base, value="11"), part="от 0.0 до 10.0") and refused("event.set", dict(base, value="x2"), part="множитель"))
        check("ревизия 44 С-2: окно длиннее года (2026-11-20 → 2027-11-25) — отказ «длиннее года»; через новый год — отказ «никогда»",
              refused("event.set", dict(base, start="2026-11-20 10:00", end="2027-11-25 10:00"), part="длиннее года")
              and refused("event.set", dict(base, start="2026-12-30 10:00", end="2027-01-02 10:00"), part="не сработает никогда"))
        check("ревизия 44 С-2: окно будущего года 2027-12-01 → 2027-12-05 при часах сервера 21.11.2026 — отказ «включит его уже 01.12.2026»",
              refused("event.set", dict(base, start="2027-12-01 10:00", end="2027-12-05 10:00"), part="включит его уже 01.12.2026"))
        check("ревизия 44 С-2: ближайшее срабатывание: next_year — 21.11.2026 для окна 01.12…05.12 = 2026, для 10.11…11.11 = 2027; "
              "20.12.2026 для 05.01…10.01 = 2027",
              V.next_year({"e": datetime.datetime(2027, 12, 5, 10)}, NOW) == 2026 and V.next_year({"e": datetime.datetime(2027, 11, 11, 22, 9)}, NOW) == 2027
              and V.next_year({"e": datetime.datetime(2027, 1, 10)}, datetime.datetime(2026, 12, 20, 12)) == 2027)
        check("event.set: канал 0 / 1 / 2 — отказ «паритет Ch2 … кодом 6» (можно −1 или 3)",
              all(refused("event.set", dict(base, chan=c), part="кодом 6") for c in (0, 1, 2)))
        check("event.set: без confirm = event — отказ", refused("event.set", dict(base, confirm=""), part="confirm = event"))
        check("event.set: рейт ×3 и ×0.5 — сильная правка: у администратора отказ «только владелец», у владельца без rate_ok — отказ",
              refused("event.set", dict(base, value="3"), adm, "только владелец") and refused("event.set", dict(base, value="0.5"), adm, "только владелец")
              and refused("event.set", dict(base, value="3"), cli, "rate_ok = rate"))
        jobs.list_jobs = lambda limit=100, active=False: [{"id": 41, "op": "event.set", "status": "pending",
                                                           "params": dict(base, start="2026-11-22 20:00", end="2026-11-24 00:00")}]
        check("event.set: окно пересекается с поставленным заданием event.set того же типа (№41) — отказ; другой тип — нет",
              refused("event.set", base, part="№41") and not refused("event.set", dict(base, type=0, start="2026-11-22 10:00"), part="№41"))
        jobs.list_jobs = lambda limit=100, active=False: []
        # ── оператор и мост ──
        pres = [{"node": "GameServer", "Userindex": 2, "Charidx": 0, "charname": "GM_Test", "map": 3, "ver": 84},
                {"node": "GameServer", "Userindex": 75000, "Charidx": 0, "charname": "Player", "map": 3, "ver": 84}]
        bridge.presence = lambda uid=None: list(pres)
        V._gm_uids = lambda uids: {u for u in uids if u in (1, 2, 4)}
        V.READ = _Files({"*": mk_dat({})})
        V.CLOCK = lambda: (datetime.datetime(2026, 12, 20, 12), datetime.datetime(2026, 12, 20, 9))
        check("ревизия 44 С-2: 20.12.2026 окно 2027-01-05 → 2027-01-10 (ближайшее срабатывание — январь 2027) — предпросмотр без отказа",
              why("event.set", dict(base, start="2027-01-05 10:00", end="2027-01-10 10:00")) == "")
        V.CLOCK = lambda: (NOW, NOW - datetime.timedelta(hours=3))
        V.READ = _Files({"*": mk_dat({})}, after=mk_dat({(1, m): ((11, 22, 10, 0), (11, 23, 10, 0), 2.0) for m in range(3)}))
        pv = ops.run(cli, "event.set", base, dry=True)["preview"]
        check("event.set: аргументы моста — как тело 6038 стока (месяцы/дни/часы/минуты, v100 = 200, lv = 1 + 256·100), оператор — служебная "
              "учётка 2 с GM-флагом (игрок 75000 не годится), все 3 NpcServer, 3 карты MapInfo",
              pv["args"] == "type=1;chan=-1;map=-1;smon=11;sday=22;shour=10;smin=0;emon=11;eday=23;ehour=10;emin=0;v100=200;lv=25601"
              and pv["op"]["Userindex"] == 2 and pv["copies"] == list(V.NPC) and pv["maps"] == [0, 1, 2] and pv["auto"], pv)
        ws = " | ".join(pv["warnings"])
        check("event.set: предупреждения — окно повторится через год, выключение заданием, уровни не применяются, ответ оператору в чат",
              "следующего года" in ws and "event.off" in ws and "не применяет" in ws and "[Success EVENT SET]" in ws, ws)
        bridge.nodes = lambda: [{"node": g, "mode": 1, "ver": 83, "fresh": True} for g in V.GS]
        pres_saved = list(pres)
        for x in pres:
            x["ver"] = 83
        check("event.set: узлы v83 (без event_set) — отказ «v84+», команда не ставится", refused("event.set", base, part="v84+"))
        pres[:] = pres_saved
        for x in pres:
            x["ver"] = 84
        bridge.nodes = lambda: [{"node": g, "mode": 1, "ver": 84, "fresh": True} for g in V.GS]
        check("event.set: оператор-игрок 75000 явно — отказ «только служебная учётка»; учётка владельца 2 у администратора — отказ",
              refused("event.set", dict(base, uid=75000, idx=0), part="служебная учётка") and refused("event.set", dict(base, uid=2, idx=0), adm, "только владелец"))
        V.READ = _Files({"*": mk_dat({(1, 1): ((11, 25, 0, 0), (11, 26, 0, 0), 1.5)})})
        check("event.set: у карты 1 окно опыта впереди (25.11) — отказ «заменит … replace»; с replace — предпросмотр",
              refused("event.set", base, part="replace = replace") and "события" not in ops.run(cli, "event.set", dict(base, replace="replace"), dry=True)["preview"]["text"][:3])

        def call(op, uid, idx, node, args="", ttl=30, by="", timeout=None):
            calls.append((op, uid, idx, node, args, ttl))
            V.READ.sent = True
            V.READ.sent_at = time.time()
            return {"id": 777, "result": "what=1;sent=1;granted=0;players=0" if op == "rank_recalc" else "ok"}
        bridge.call = call
        jobs.add = lambda *a: added.append(a) or 55
        auth.totp_confirm = lambda uid, code: None
        V.VERIFY_S, V.VERIFY_STEP, V.VERIFY_FIRST = 0.5, 0.1, 0.0
        jobs.cancel = lambda jid: False
        V.READ = _Files({"*": mk_dat({})}, after=mk_dat({(1, m): ((11, 22, 10, 0), (11, 23, 10, 0), 2.0) for m in range(3)}))
        r = ops.run(cli, "event.set", base)
        check("event.set: мостом event_set от 2/0 на GameServer, Event.dat всех трёх NpcServer подтвердили, задание event.off №55 на конец + 2 мин "
              "в UTC (служба), не откатывается",
              calls[-1][:4] == ("event_set", 2, 0, "GameServer") and r["result"]["confirmed"] == list(V.NPC) and not r["result"]["unconfirmed"]
              and added and added[-1][0] == "event.off" and added[-1][2] == "service"
              and added[-1][3] == datetime.datetime(2026, 11, 23, 7, 2) and added[-1][1]["confirm"] == "event"
              and not ops.REGISTRY["event.set"].reversible, (r["message"], added[-1:]))
        V.READ = _Files({"*": mk_dat({})}, after=None)
        r = ops.run(cli, "event.set", dict(base, auto_off="0"))
        check("event.set: Event.dat не изменился за срок — итог честно «НЕ подтвердили», задания выключения нет (auto_off = 0)",
              r["result"]["unconfirmed"] == list(V.NPC) and "НЕ подтвердили" in r["message"] and len(added) == 1, r["message"])
        check("ревизия 44 С-1: задание выключения хранит ожидаемое окно (expect = запись Event.dat события, expect_window, номер команды 6038)",
              added[0][1]["expect"] == V.want_entry(V.window(base)) and added[0][1]["expect_window"] == "22.11 10:00 → 23.11 10:00 ×2.0"
              and added[0][1]["set_cmd"] == 777, added[0][1])
        # ── ревизия 44 С-1: «событие А, потом Б на те же карты» ──
        want_a = V.want_entry(V.window(dict(base, start="2026-11-20 10:00", end="2026-11-21 03:00")))
        dat_a = mk_dat({(1, m): ((11, 20, 10, 0), (11, 21, 3, 0), 2.0) for m in range(3)})
        dat_b = mk_dat({(1, m): ((11, 22, 10, 0), (11, 23, 10, 0), 2.0) for m in range(3)})
        off_a = {"id": 60, "op": "event.off", "status": "pending", "run_at": datetime.datetime(2026, 11, 21, 0, 2),
                 "params": {"type": 1, "chan": -1, "map": -1, "confirm": "event", "expect": want_a, "expect_window": V.win_text(want_a)}}
        jobs.list_jobs = lambda limit=100, active=False: [off_a]
        cancelled = []
        jobs.cancel = lambda jid: cancelled.append(jid) or True
        V.READ = _Files({"*": dat_a})
        pv = ops.run(cli, "event.set", base, dry=True)["preview"]
        V.READ = _Files({"*": dat_a}, after=dat_b)
        r = ops.run(cli, "event.set", base)
        check("ревизия 44 С-1: Б на те же карты после прошедшего А — предпросмотр «будут сняты … №60», после записи задание А №60 снято, "
              "новое задание выключения ждёт окно Б",
              pv["drop_off"] == [60] and any("№60" in x for x in pv["warnings"]) and cancelled == [60] and "№60" in r["message"]
              and added[-1][1]["expect"] == V.want_entry(V.window(base)), (pv.get("drop_off"), cancelled, r["message"]))
        jobs.list_jobs = lambda limit=100, active=False: []
        V.READ = _Files({"*": dat_b})
        n_calls = len(calls)
        check("ревизия 44 С-1: задание выключения А (expect = окно А) в свой срок при записанном Б — отказ «окно заменено», 6040 не уходит",
              refused("event.off", dict(off_a["params"], job_id=60), part="окно заменено") and len(calls) == n_calls)
        V.READ = _Files({"*": dat_b}, after=mk_dat({}))
        r = ops.run(cli, "event.off", dict(added[-1][1]))
        check("ревизия 44 С-1: задание выключения Б (expect = окно Б) — 6040 уходит, обнуление подтверждено всеми NpcServer",
              calls[-1][0] == "event_off" and r["result"]["confirmed"] == list(V.NPC), r["message"])
        jobs.list_jobs = lambda limit=100, active=False: [off_a]
        V.READ = _Files({"*": dat_a})
        check("ревизия 44 С-1: Б только на карту 1 при задании А на все карты (окно А записано) — отказ «задевает больше карт»",
              "задевает больше карт" in why("event.set", dict(base, map=1)), why("event.set", dict(base, map=1)))
        V.READ = _Files({"*": mk_dat({})})
        pv = ops.run(cli, "event.set", dict(base, map=1), dry=True)["preview"]
        check("ревизия 44 С-1: окна А в Event.dat уже нет — его задание снимается и при частичном перекрытии (оно отказало бы само)",
              pv["drop_off"] == [60], pv.get("drop_off"))
        man = {"id": 62, "op": "event.off", "status": "pending", "run_at": datetime.datetime(2026, 11, 22, 12, 0),
               "params": {"type": 1, "chan": -1, "map": -1, "confirm": "event"}}
        jobs.list_jobs = lambda limit=100, active=False: [man]
        check("ревизия 44 С-1: ручное задание выключения №62 без ожидаемого окна до конца нового окна — отказ «выключит и это событие»",
              refused("event.set", base, part="без ожидаемого окна"))
        man["run_at"] = datetime.datetime(2026, 11, 24, 12, 0)
        check("ревизия 44 С-1: ручное задание выключения после конца нового окна — не мешает", "№62" not in why("event.set", base))
        jobs.list_jobs = lambda limit=100, active=False: []
        # ── ревизия 44 Н-1: пауза до первого чтения и чтение данных только по смене времени записи ──
        V.VERIFY_FIRST = 0.3
        V.READ = _Files({"*": mk_dat({})}, after=dat_b)
        ops.run(cli, "event.set", dict(base, auto_off="0"))
        check("ревизия 44 Н-1: первое чтение Event.dat — не раньше паузы VERIFY_FIRST (0.3 с) после команды моста",
              V.READ.first_read - V.READ.sent_at >= 0.3, V.READ.first_read - V.READ.sent_at)
        V.VERIFY_FIRST = 0.0
        V.STAT = lambda rels: {x: (2200, 1) for x in rels}
        V.READ = _Files({"*": mk_dat({})}, after=None)
        r = ops.run(cli, "event.set", dict(base, auto_off="0"))
        check("ревизия 44 Н-1: время записи не менялось — данные Event.dat открыты один раз на копию за весь срок; «НЕ подтвердили … только в памяти»",
              V.READ.dat_reads == 3 and "только в памяти" in r["message"], (V.READ.dat_reads, r["message"]))
        V.STAT = None
        # ── ревизия 44 Н-2: сбой чтения и часов после отправки ──

        def clk():
            if getattr(V.READ, "sent", False):
                raise ops.OpRefused("часы сервера не прочитаны (timeout) — окно события не с чем сверить")
            return NOW, NOW - datetime.timedelta(hours=3)
        V.CLOCK = clk
        V.READ = _Files({"*": mk_dat({})}, fail_after=True)
        n_add = len(added)
        r = ops.run(cli, "event.set", base)
        check("ревизия 44 Н-2: после 6038 Event.dat и часы не читаются — итог «отправлено, проверка не прочитана» (не отказ), задание "
              "выключения с ожидаемым окном всё равно поставлено (срок — по часам предпросмотра)",
              "проверка Event.dat не прочитана" in r["message"] and r["result"]["verify_error"] and len(added) == n_add + 1
              and added[-1][1].get("expect") and added[-1][3] == datetime.datetime(2026, 11, 23, 7, 2), r["message"])
        V.READ = _Files({"*": dat_b}, fail_after=True)
        r = ops.run(cli, "event.off", {"type": 1, "confirm": "event"})
        check("ревизия 44 Н-2: 6040 — то же: «отправлен … проверка Event.dat не прочитана», не отказ",
              calls[-1][0] == "event_off" and "проверка Event.dat не прочитана" in r["message"], r["message"])
        V.CLOCK = lambda: (NOW, NOW - datetime.timedelta(hours=3))
        jobs.add = lambda *a: (_ for _ in ()).throw(RuntimeError("adm.job unavailable"))
        V.READ = _Files({"*": mk_dat({})}, after=dat_b)
        r = ops.run(cli, "event.set", base)
        check("ревизия 44 Н-2: задание выключения не поставилось — итог «отправлено … задание выключения НЕ поставлено … вручную», не отказ",
              "задание выключения НЕ поставлено" in r["message"] and r["result"]["job_error"], r["message"])
        jobs.add = lambda *a: added.append(a) or 55
        # ── ревизия 44: событие опыта + счастливые часы складываются ──
        _Files.lucky = LUCKY
        pres.append({"node": "GameServer", "Userindex": 4, "Charidx": 0, "charname": "GM_Four", "map": 3, "ver": 84})
        V.READ = _Files({"*": mk_dat({})})
        pv = ops.run(cli, "event.set", dict(base, rate_ok="rate"), dry=True)["preview"]
        check("ревизия 44: событие ×2.0 (не сильное) + счастливые часы 22.11 10–11 (+1.0) = ×3.0 — у администратора «только владелец», у "
              "владельца без rate_ok — отказ, с rate_ok — предпросмотр «второе подтверждение дано»",
              refused("event.set", base, adm, "только владелец") and refused("event.set", base, cli, "rate_ok = rate")
              and any("×3.0" in x and "второе подтверждение дано" in x for x in pv["warnings"]), pv["warnings"])
        _Files.lucky = None
        check("ревизия 44: счастливые часы не прочитаны — сложение не проверено: у администратора отказ «только владелец»",
              refused("event.set", dict(base, value="1.0", uid=4, idx=0), adm, "только владелец"))
        _Files.lucky = LUCKY
        pv = ops.run(adm, "event.set", dict(base, value="1.0", uid=4, idx=0), dry=True)["preview"]
        check("ревизия 44: ×1.0 + 1.0 = ×2.0 — не сильная (без второго подтверждения), предупреждение «рейт опыта ×2.0»",
              any("рейт опыта ×2.0" in x for x in pv["warnings"]), pv["warnings"])
        _Files.lucky = LUCKY.replace(b"2026\t11\t22\t10\t11", b"2026\t11\t25\t10\t11")
        # ── выключение ──
        V.READ = _Files({"*": mk_dat({})})
        check("event.off: событий нет — отказ «выключать нечего»; без confirm — отказ",
              refused("event.off", {"type": 1, "confirm": "event"}, part="выключать нечего") and refused("event.off", {"type": 1}, part="confirm = event"))
        V.READ = _Files({"*": mk_dat({(1, 0): ((11, 10, 22, 9), (11, 11, 22, 9), 2.0)})}, after=mk_dat({}))
        r = ops.run(cli, "event.off", {"type": 1, "confirm": "event"})
        check("event.off: event_off «type=1;chan=-1;map=-1» мостом, обнуление подтверждено всеми NpcServer",
              calls[-1][0] == "event_off" and calls[-1][4] == "type=1;chan=-1;map=-1" and r["result"]["confirmed"] == list(V.NPC), r["message"])
        V.READ = _Files({"*": mk_dat({(1, 0): ((11, 10, 22, 9), (11, 11, 22, 9), 2.0)})}, after=mk_dat({}))
        r = ops.run(cli, "event.off", {"type": 1, "chan": 3, "confirm": "event"})
        check("event.off: только Indun (канал 3) — проверяется только Indun_NpcServer", r["result"]["confirmed"] == ["Indun_NpcServer"], r["result"])
        # ── рейтинги ──
        r = ops.run(cli, "rank.recalc", {"what": 1, "confirm": "rank"})
        check("rank.recalc: мостом rank_recalc «what=1» от оператора, итог «запрос 2333 ушёл в базу»; what вне 0…3 — отказ",
              calls[-1][:2] == ("rank_recalc", 2) and calls[-1][4] == "what=1" and "2333" in r["message"]
              and refused("rank.recalc", {"what": 4, "confirm": "rank"}, part="от 0 до 3"), r["message"])
        check("ревизия 44 Н-3: rank.recalc без слова подтверждения — отказ «confirm = rank»; слово операции (задания, веб) — rank",
              refused("rank.recalc", {"what": 1}, part="confirm = rank") and ops.REGISTRY["rank.recalc"].confirm_word == "rank")
        # ── ежедневные ──
        qs = {"done": [{"Source": "task", "Edate": NOW}]}

        def sql(q, params=()):
            if "GETDATE" in q:
                return [{"n": NOW}]
            if "COUNT(*)" in q:
                return [{"n": 12}]
            if "Done = 1 AND Boundary" in q:
                return qs["done"]
            return []
        V.SQL = sql
        check("daily: граница суток — 06:00 последних наступивших суток с минутой запаса (как CRT_AsdaLimitationDailyReset)",
              V.boundary(NOW) == datetime.datetime(2026, 11, 20, 6, 0) and V.boundary(datetime.datetime(2026, 11, 21, 6, 1))
              == datetime.datetime(2026, 11, 21, 6, 0) and V.boundary(datetime.datetime(2026, 11, 21, 6, 0)) == datetime.datetime(2026, 11, 20, 6, 0))
        check("daily.reset: catchup при сделанном суточном — отказ «догонять нечего»; force без confirm — отказ; неверный режим — отказ",
              refused("daily.reset", {"mode": "catchup"}, part="догонять нечего") and refused("daily.reset", {"mode": "force"}, part="confirm = daily")
              and refused("daily.reset", {"mode": "x"}, part="неверный режим"))
        pv = ops.run(cli, "daily.reset", {"mode": "force", "confirm": "daily"}, dry=True)["preview"]
        qs["done"] = []
        pc = ops.run(cli, "daily.reset", {"mode": "catchup"}, dry=True)["preview"]
        check("daily.reset: предпросмотр force — строк 12, «суточный уже сделан», предупреждение про память GS до 06:00; catchup — граница 2026-11-20 06:00",
              "12" in pv["text"] and "уже сделан" in pv["text"] and any("06:00" in w for w in pv["warnings"]) and "2026-11-20 06:00" in pc["text"],
              (pv["text"], pc["text"]))
        # ── права и задания ──
        gm = ops.Ctx(None, "cli:gm", "gm", "", "cli")
        check("права: server.events / server.ranks / server.daily — владелец и администратор; у GM — «нет права»",
              all(auth.PERMS[k] == {"owner", "admin"} for k in ("server.events", "server.ranks", "server.daily"))
              and refused("event.set", base, gm, "нет права") and refused("daily.reset", {"mode": "catchup"}, gm, "нет права"))
        check("задания: event.set / event.off / rank.recalc / daily.reset ставятся (служба); второй фактор — у event.set и daily.reset",
              all(ops.REGISTRY[k].schedule_runner == "service" for k in ("event.set", "event.off", "rank.recalc", "daily.reset"))
              and ops.REGISTRY["event.set"].two_factor and ops.REGISTRY["daily.reset"].two_factor and not ops.REGISTRY["event.off"].two_factor)
    finally:
        (V.READ, V.CLOCK, V.SQL, bridge.nodes, bridge.presence, bridge.call, V._gm_uids, jobs.list_jobs, jobs.add, audit.write,
         auth.totp_confirm, V.VERIFY_S, V.VERIFY_STEP, V.VERIFY_FIRST, V.STAT, jobs.cancel) = saved
        _Files.lucky = LUCKY
    # ── набор изменений «Счастливые часы» ──

    class _St:
        def __init__(self, raw):
            self.t = {g: E.Table(g + "\\" + L.LUCKY, raw) for g in E.GS}

        def get(self, g, rel):
            return self.t[g]

    class _Ev:
        def __init__(self, raw, dat=None, today=datetime.date(2026, 11, 21)):
            self.st = _St(raw)
            self._events_today = today
            self._events_dat = {n: (mk_dat({}) if dat is None else dat) for n in ("NpcServer", "Indun_NpcServer", "Ch2_NpcServer")}

    def run(kind, p, raw=LUCKY, **kw):
        ev, rep = _Ev(raw, **kw), {"warnings": []}
        try:
            getattr(L, "k_" + kind.replace(".", "_"))(ev, L.norm(kind, p), rep)
        except ops.OpRefused as ex:
            return None, str(ex)
        return ev, rep
    ev, rep = run("lucky.add", {"date_from": "2026-11-23", "date_to": "2026-11-25", "h_from": 20, "h_to": 22, "value": "1.0"})
    data = ev.st.t["GameServer"].data()
    check("lucky.add: 3 дня × 20–22 +1.0 — строки в конец, счётчик 3 → 6, CRLF и прежние строки байт в байт, все 3 копии одинаковы",
          data.startswith(b"6\r\n2026\t11\t21\t0\t1\t1.0\r\n") and data.endswith(b"2026\t11\t25\t20\t22\t1.0\r\n")
          and all(ev.st.t[g].data() == data for g in E.GS) and "×2.0" in rep["text"] and rep["_balance"][0]["kind"] == "value", data[-60:])
    ev, rep = run("lucky.add", {"date_from": "2026-11-23", "date_to": "2026-11-23", "h_from": 20, "h_to": 22, "value": "1.5"})
    check("lucky.add: значение > 1.0 (рейт выше ×2) — сильная правка (второе подтверждение владельца при утверждении)",
          rep["_balance"][0]["kind"] == "rate" and E.balance_of.__doc__ is not None)
    exp_ev = mk_dat({(1, 0): ((11, 23, 0, 0), (11, 24, 0, 0), 2.0)})
    ev, rep = run("lucky.add", {"date_from": "2026-11-23", "date_to": "2026-11-23", "h_from": 20, "h_to": 22, "value": "0.5"}, dat=exp_ev)
    ev2, rep2 = run("lucky.add", {"date_from": "2026-11-25", "date_to": "2026-11-25", "h_from": 20, "h_to": 22, "value": "0.5"}, dat=exp_ev)
    ev3, rep3 = run("lucky.add", {"date_from": "2026-11-25", "date_to": "2026-11-25", "h_from": 20, "h_to": 22, "value": "0.5"}, dat=b"\0" * 10)
    check("ревизия 44: lucky.add +0.5 на часы события опыта ×2.0 (23.11) — итог ×2.5, сильная правка (второе подтверждение), предупреждение; "
          "вне события — ×1.5, обычная; Event.dat не прочитан — сильная с предупреждением «не проверено»",
          rep["_balance"][0]["kind"] == "rate" and rep["_balance"][0]["new"] == "2.5" and any("×2.5" in w for w in rep["warnings"])
          and rep2["_balance"][0]["kind"] == "value" and rep2["_balance"][0]["new"] == "1.5"
          and rep3["_balance"][0]["kind"] == "rate" and any("не проверено" in w for w in rep3["warnings"]),
          (rep["_balance"], rep2["_balance"], rep3["warnings"]))
    saved_clock = V.CLOCK
    try:
        V.CLOCK = lambda: (datetime.datetime(2026, 11, 26, 1, 0), datetime.datetime(2026, 11, 25, 22, 0))
        past = run("lucky.add", {"date_from": "2026-11-25", "date_to": "2026-11-25", "h_from": 20, "h_to": 22, "value": "0.5"}, today=None)[1]
    finally:
        V.CLOCK = saved_clock
    check("ревизия 44: «прошедшая дата» счастливых часов — по часам СЕРВЕРА (events.clock: 26.11 на сервере — 25.11 уже прошла)",
          isinstance(past, str) and "уже прошла" in past, past)
    check("lucky.add: пересечение часов с записанной строкой 21.11 02–05 — отказ; прошедшая дата — отказ; дни недели — только выбранные",
          "пересекаются" in run("lucky.add", {"date_from": "2026-11-21", "date_to": "2026-11-21", "h_from": 4, "h_to": 6, "value": "1"})[1]
          and "уже прошла" in run("lucky.add", {"date_from": "2026-11-20", "date_to": "2026-11-30", "h_from": 6, "h_to": 7, "value": "1"})[1]
          and run("lucky.add", {"date_from": "2026-11-23", "date_to": "2026-11-29", "h_from": 6, "h_to": 7, "value": "1", "days": "67"})[0]
          .st.t["GameServer"].data().startswith(b"5\r\n"))
    check("lucky.add: час_до ≤ час_от, значение > 10, день недели 8 — отказ до таблицы",
          "не позже начала" in run("lucky.add", {"date_from": "2026-11-23", "date_to": "2026-11-23", "h_from": 5, "h_to": 5, "value": "1"})[1]
          and "не больше 10.0" in run("lucky.add", {"date_from": "2026-11-23", "date_to": "2026-11-23", "h_from": 5, "h_to": 6, "value": "11"})[1]
          and "дни недели" in run("lucky.add", {"date_from": "2026-11-23", "date_to": "2026-11-23", "h_from": 5, "h_to": 6, "value": "1", "days": "8"})[1])
    ev, rep = run("lucky.del", {"date_from": "2026-11-21", "date_to": "2026-11-21", "h_from": -1})
    check("lucky.del: строки 21.11 (2) убраны, счётчик 3 → 1; нечего убирать — отказ",
          ev.st.t["Indun_GameServer"].data() == b"1\r\n2026\t11\t22\t10\t11\t1.0\r\n"
          and "убирать нечего" in run("lucky.del", {"date_from": "2026-12-01", "date_to": "2026-12-02", "h_from": -1})[1])
    bad = b"4\r\n2026\t11\t21\t0\t1\t1.0\r\n"
    check("lucky.*: счётчик ≠ строк тела — отказ «не ложатся построчно»", "построчно" in (run("lucky.del", {"date_from": "2026-11-21",
                                                                                                         "date_to": "2026-11-21", "h_from": -1}, bad)[1] or ""))
    ev = _Ev(LUCKY)
    ev.st.t["Ch2_GameServer"] = E.Table("x", LUCKY.replace(b"0.5", b"0.7"))
    try:
        L.k_lucky_add(ev, L.norm("lucky.add", {"date_from": "2026-11-23", "date_to": "2026-11-23", "h_from": 1, "h_to": 2, "value": "1"}), {"warnings": []})
        diverged = ""
    except ops.OpRefused as ex:
        diverged = str(ex)
    check("lucky.*: копия Ch2 разошлась с GameServer — отказ «копии разошлись»", "разошлись" in diverged, diverged)
    from domains import shopdata as SD
    check("набор изменений: область «Счастливые часы» в реестре видов, таблица Event\\GameServerEvent.txt ×3 GS, политика same",
          SD.AREA_OF["lucky.add"] is L and SD.SRV_POLICY[L.LUCKY] == "same" and SD.SRV_FAMILY[L.LUCKY] == "GS")
    # ── исходники: выкладчик наборов, мост, SQL, DLL v84 ──
    import sys
    sys.path.insert(0, os.path.join(AP, "tools"))
    import deploy_changeset as dcs
    import stack_layout
    check("выкладчик наборов: Event\\GameServerEvent.txt разрешён во всех трёх GameServer; NpcServer / GS панели = stack_layout",
          all(g + "\\Event\\GameServerEvent.txt" in dcs.ALLOWED for g in stack_layout.GS_FOLDERS)
          and dcs.check_roots({g + "\\Event\\GameServerEvent.txt": 1 for g in stack_layout.GS_FOLDERS}) is None
          and tuple(V.NPC) == tuple(stack_layout.NPC_FOLDERS) and tuple(V.GS) == tuple(stack_layout.GS_FOLDERS))
    sql7 = open(os.path.join(ROOT, "sql", "adminc_07_bridge.sql"), encoding="utf-8").read()
    sql15 = open(os.path.join(ROOT, "sql", "adminc_15_events.sql"), encoding="utf-8").read()
    sql4 = open(os.path.join(ROOT, "sql", "adminc_04_ops.sql"), encoding="utf-8").read()
    sql11 = open(os.path.join(ROOT, "sql", "adminc_11_verify_ops.sql"), encoding="utf-8").read()
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
    check("мост: event_set / event_off / rank_recalc в OPS и в белом списке adm.BridgeEnqueue, EVENT_VER = 84",
          all(x in bridge.OPS for x in ("event_set", "event_off", "rank_recalc")) and bridge.EVENT_VER == 84
          and "'event_set', 'event_off', 'rank_recalc')" in sql7)
    check("SQL А5.4: adm.LimitationReset (догнать = вызов CRT_AsdaLimitationDailyReset; внеочередной — то же тело под тем же замком, Done = 2), "
          "EXECUTE только обёртки (adminc_04), проверка adminc_11, выкладка до adminc_04",
          "EXEC @r = dbo.CRT_AsdaLimitationDailyReset @Source = 'admin'" in sql15 and "@Resource = 'AsdaLimitationDailyReset'" in sql15
          and "'admin-force', 2," in sql15 and "GRANT EXECUTE ON adm.LimitationReset TO [asda_ops]" in sql4
          and "'ops.adm.LimitationReset EXEC'" in sql11 and "'ops.CRT_AsdaLimitationDailyReset EXEC'" in sql11
          and dep.index("adminc_15_events.sql") < dep.index("Run 'adminc_04_ops.sql'"))
    cpp = open(os.path.join(AP, "src", "patches", "p127_admin_bridge.cpp"), encoding="utf-8-sig").read()
    p25 = open(os.path.join(AP, "src", "patches", "p25_gm_rating_recalc.cpp"), encoding="utf-8-sig").read()
    cfgh = open(os.path.join(AP, "src", "Config.h"), encoding="utf-8-sig").read()
    stand = open(os.path.join(AP, "tools", "stand_p127", "stand_p127.cpp"), encoding="utf-8-sig").read()
    dp = open(os.path.join(AP, "tools", "deploy_p127e.py"), encoding="utf-8").read()
    check("DLL v84: event_set / event_off — гейты оператора и GM-флага, шапка sub_4A7EB0 / sub_40C960 / userNum, sub_5646C0 в RelayServer "
          "(6038/29, 6040/15); rank_recalc — P25_RunRecalc (команда 6020 зовёт ту же точку); kVersion 84 или 85 (★ А5.10: P128 значок всем)",
          "pRelayConn(th, nullptr)" in cpp and "(WORD)(BYTE)pGsChannel(mgr, nullptr)" in cpp and "set ? 6038 : 6040, set ? 29 : 15" in cpp
          and "P25_RunRecalc(mgr, num, c.a[0], &a, &b)" in cpp and "RunRecalcCore(mgr, idx, what, nullptr, nullptr);" in p25
          and any("constexpr int kVersion = %d;" % v in cfgh for v in range(84, 200)))   # ★ 22.11 (P129, v86): не ниже 84
    # ★ А5.10: P128 — значок события всем (исходник, реестр, ini-шаблон, цепочка P73, стенд, выкладчик)
    p128 = open(os.path.join(AP, "src", "patches", "p128_event_badge_all.cpp"), encoding="utf-8-sig").read()
    p73s = open(os.path.join(AP, "src", "patches", "p73_eac_bridge.cpp"), encoding="utf-8-sig").read()
    regs = open(os.path.join(AP, "src", "patches", "Registry.cpp"), encoding="utf-8-sig").read()
    cfgc = open(os.path.join(AP, "src", "Config.cpp"), encoding="utf-8-sig").read()
    st128 = open(os.path.join(AP, "tools", "stand_p128", "stand_p128.cpp"), encoding="utf-8-sig").read()
    dp128 = open(os.path.join(AP, "tools", "deploy_p128.py"), encoding="utf-8").read()
    check("DLL v85 P128: 6039 (30 б) / 6041 (16 б) своему игроку из зеркала 0x5E2348…, окно s ≤ ММДДччмм < e, опыт + счастливый час, "
          "6041 опыта — только если значок зажёг P128; такт P73_OnCheckUser, сброс P73_OnConnFlag; секция [P128_EventBadgeAll] Enabled=1",
          "pToClient(th, nullptr, 6039, 30, num, b, num, 1)" in p128 and "pToClient(th, nullptr, 6041, 16, num, b, num, 1)" in p128
          and "s <= key && key < e" in p128 and "const float want = v1 + lucky;" in p128 and "else if (st.expOn)" in p128
          and "P128_OnUserTick(mgr, userNum, user);" in p73s and "P128_OnConnFlag(slot, flag);" in p73s
          and '{ L"P128_EventBadgeAll",' in regs and '{ L"P128_EventBadgeAll",' in cfgc and "kEventBadgeAll" in cfgc
          and any("constexpr int kVersion = %d;" % v in cfgh and '{ L"Version", L"%d",' % v in cfgc for v in range(85, 200))   # ★ 22.11 (P129, v86): не ниже 85
          and '{ L"P128_EventBadgeAll",' in cfgc)
    check("стенд P128: A–Q (тишина, тип 0, окно и уровни, смена карты, множитель, конец окна, будущее, опыт + час, только час не трогается, "
          "мир, разрыв, смена персонажа, оба значка, карта вне слотов) и режимы off / mismatch / nolucky; выкладчик v85 ← v84 612db6fe",
          all(('"%s ' % k) in st128 for k in ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q",
                                               "R", "S", "T"))
          and all(m in st128 for m in ('"off"', '"mismatch"', '"nolucky"')) and "pSetKey(6151200)" in st128
          and 'WANT_DLL = "e0d08ba5a4ee855451a9e8530d73710c"' in dp128 and '"612db6fef6cb800a2e557783b32d4f77"' in dp128
          and "--check-started" in dp128 and "--rollback" in dp128 and "seed_section" in dp128 and "UTF-16 BE" in dp128)
    check("ревизия 49 С-1 / Н-3 (P128): первый такт нового входа шлёт явное состояние обоих видов (6041 по неактивным, опыт при идущем "
          "часе — 6039 ×(1 + час)); новое соединение — по поколению слота g_gen (+1 в P128_OnConnFlag)",
          "if (st.fresh)" in p128 and "else     { Send6041(th, userNum, 0, map); }" in p128 and "else                   { Send6041(th, userNum, 1, map); }" in p128
          and "Send6039(th, userNum, 1, map, 1.0f + lval)" in p128 and "InterlockedIncrement(&g_gen[slot]);" in p128
          and "st.gen != gen" in p128)
    check("стенд P127: E1–E9 (GM-флаг, тело 6038 как у стока, 6040, диапазоны, нет связи, сбой отправки, учётка 6001, начало 0x4C0A90) и R0–R3",
          all(("\"%s " % k) in stand for k in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E9", "R0", "R1", "R2", "R3")) and "noevent" in stand)
    import hashlib
    built = os.path.join(AP, "tools", "p127_data", "AsdaPatch_v84p127e_612db6fe.dll")
    check("выкладчик deploy_p127e: закреплённая сборка v84 = WANT_DLL, прежняя — v82 (живая) или v83, PatchLog «живьём (v84)», --help и "
          "неизвестный ключ без SSH",
          os.path.exists(built) and hashlib.md5(open(built, "rb").read()).hexdigest() == "612db6fef6cb800a2e557783b32d4f77"
          and 'WANT_DLL = "612db6fef6cb800a2e557783b32d4f77"' in dp and "386d43f605d5ce693993fdcac43bc894" in dp and "90ba8cd8b94356ec3d12cd369e2262f3" in dp
          and "P127: живьём (v84): события 6038/6040 да" in dp and 'KNOWN_KEYS = ("--apply", "--rollback", "--check-started")' in dp)
    # ── консоль ──
    import asda_admin
    prm, dry = asda_admin.events_args("set", ["--type", "1", "--value", "2.0", "--start", "2026-11-22 10:00", "--end", "2026-11-23 10:00",
                                              "--chan", "-1", "--confirm-event", "--no-auto-off", "--dry"])

    def bad_args(sub, a):
        try:
            asda_admin.events_args(sub, a)
        except SystemExit as ex:
            return str(ex)
        return ""
    check("консоль events: ключи → параметры (канал −1 как значение), неизвестный / чужой ключ и ключ без значения — отказ без действий",
          prm == {"type": "1", "value": "2.0", "start": "2026-11-22 10:00", "end": "2026-11-23 10:00", "chan": "-1", "confirm": "event",
                  "auto_off": "0"} and dry
          and "неизвестный ключ" in bad_args("set", ["--bogus"]) and "неизвестный ключ" in bad_args("off", ["--value", "2"])
          and "нет значения" in bad_args("set", ["--type"]) and "catchup или force" in bad_args("daily", []), prm)
    # ── веб ──
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    i18 = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    blk = app[app.index("function eventsCard()"):app.index("// ---------- А5.1: задания планировщика")]
    strs = set(re.findall(r'(?:T\(|h\("[a-z0-9]+", (?:null|\{[^}]*\}), )"([^"]*[А-Яа-яЁё][^"]*)"', blk))
    miss = sorted(s for s in strs if '"%s":' % s not in i18)
    check("веб: карточка «События и сбросы» на странице «Состояние» — без innerHTML, все надписи с переводом EN",
          "eventsCard()," in app and "innerHTML" not in blk and not miss, miss[:6])
    # ── переводы ──
    msgs = ["6038 отправлен (команда №777): Event.dat записали: NpcServer, Indun_NpcServer; НЕ подтвердили за 15 с: Ch2_NpcServer — событие может "
            "идти только в памяти NpcServer до его рестарта (Event.dat не записан); выключение — задание №55 (выключит только окно 22.11 10:00 → "
            "23.11 10:00 ×2.0)",
            "6038 отправлен (команда №777): Event.dat записали: никто; проверка Event.dat не прочитана (файлы событий стойки не прочитаны: ssh: "
            "timeout) — итог записи неизвестен, посмотрите карточку «События и сбросы»; задание выключения НЕ поставлено (adm.job unavailable) — "
            "выключите вручную (event.off) после 2026-11-23 10:00",
            "6038 отправлен (команда №777): Event.dat записали: NpcServer, Indun_NpcServer, Ch2_NpcServer; выключение — задание №55 (выключит "
            "только окно 22.11 10:00 → 23.11 10:00 ×2.0); сняты прежние задания выключения: №60",
            "6038 отправлен (команда №777): Event.dat записали: никто; НЕ подтвердили за 15 с: NpcServer — событие может идти только в памяти "
            "NpcServer до его рестарта (Event.dat не записан); прежние задания выключения №60 не сняты: запись не подтверждена — к сроку они "
            "сверят окно сами",
            "6038 отправлен (команда №777): Event.dat записали: NpcServer; не сняты (уже не ждут или сбой): №61 — они откажут сами (окно заменено)",
            "6040 отправлен (команда №8): Event.dat обнулили: NpcServer",
            "6040 отправлен (команда №8): Event.dat обнулили: никто; НЕ подтвердили за 15 с: NpcServer — событие может быть выключено только в "
            "памяти NpcServer до его рестарта (Event.dat не записан)",
            "окно заменено — не выключаю: задание выключало 20.11 10:00 → 21.11 03:00 ×2.0, а сейчас записано 22.11 10:00 → 23.11 10:00 ×2.0 "
            "(NpcServer карта 0 и ещё 8) — новое событие не трогаю",
            "задание выключения №60 (окно 20.11 10:00 → 21.11 03:00 ×2.0) задевает больше карт или каналов, чем это событие — после замены оно не "
            "выключит прежнее окно на остальных — сначала выключите прежнее окно (event.off) или отмените задание, либо задайте те же карты и каналы",
            "задание выключения №62 (22.11 15:00) поставлено без ожидаемого окна и выключит и это событие — сначала выключите прежнее окно "
            "(event.off) или отмените задание, либо задайте те же карты и каналы",
            "окно 2026-11-20 10:00 → 2027-11-25 10:00 длиннее года — сервер хранит окно без года (MMDDчмм) и включал бы его каждый год с 20.11 по "
            "25.11 — задайте окно в пределах одного года",
            "окно 2027-12-01 10:00 → 2027-12-05 10:00: сервер сравнивает даты без года и включит его уже 01.12.2026 (сейчас на сервере 2026-11-21 "
            "03:30) — задайте ближайшие даты или поставьте событие заданием ближе к дате",
            "вместе со счастливыми часами (+1.0, 2026-11-22 10–11) рейт опыта ×3.0 — больше ×2: только владелец",
            "вместе со счастливыми часами (+1.0, 2026-11-22 10–11) рейт опыта ×3.0 — больше ×2: нужно второе подтверждение (ключ rate_ok = rate)",
            "вместе со счастливыми часами (+1.0, 2026-11-22 10–11) рейт опыта ×3.0 — больше ×2: второе подтверждение дано",
            "вместе со счастливыми часами (+1.0, 2026-11-22 10–11) рейт опыта ×2.0",
            "счастливые часы GameServerEvent.txt не прочитаны или не разобраны (не прочитан) — сложение с ними не проверено: только владелец",
            "после записи будут сняты прежние задания выключения этих карт: №60 (их окно заменяется — новое событие ставит своё)",
            "задание выключения выключит только это окно: если к его сроку запись Event.dat другая (новое событие) — откажет",
            "ожидаемое окно 22.11 10:00 → 23.11 10:00 ×2.0 записано у всех выбранных карт — выключается оно",
            "ожидаемое окно задания выключения (expect) испорчено — не выключаю вслепую",
            "Event.dat не прочитан или битый при повторном чтении — было / станет неизвестно, вслепую не делается",
            "Event.dat NpcServer не прочитан или битый при повторном чтении — что выключается, неизвестно, вслепую не делается",
            "задания планировщика не прочитаны (timeout) — задания выключения на этих картах не проверены",
            "нужно подтверждение: пересчёт меняет звания и топ всем игрокам (ключ confirm = rank)",
            "Event.dat не прочитан или битый: NpcServer, Ch2_NpcServer — сложение с событием опыта (6038) не проверено: при утверждении нужно "
            "второе подтверждение",
            "на эти часы есть событие опыта NpcServer (2026-11-23 ×2.0) — рейт складывается: ×2.5",
            "пересчёт условий званий: выдано 3 (персонажей в игре 10); запрос 2333 ушёл в базу — итог придёт оператору",
            "событие: опыт ×2.0, 2026-11-22 10:00 → 2026-11-23 10:00 (время сервера), все каналы, все карты; NpcServer: NpcServer, Ch2_NpcServer",
            "выключить событие «добыча и золото»: только Indun, 3 Alpen; сейчас: 17.10 00:00 → 17.11 00:00 ×3.0 (past)",
            "пересчитать рейтинги сейчас: только рейтинговые звания 65…69 (база, P23)",
            "канал 0: только поле (канал 1) — Event.dat разошёлся бы с парой (паритет Ch2 = поле), restart_stack откажет кодом 6 — можно: все каналы (−1) или только Indun (3)",
            "у этих карт уже есть идущее или будущее окно «опыт» (25.11 00:00 → 26.11 00:00 ×1.5), событие его заменит (у карты одно окно на тип) — "
            "заменить — ключ replace = replace",
            "окно 10.11 22:09 → 11.11 22:09 ×2.0 (опыт, карт 24) прошло, но не выключено — сервер включит его снова 10.11 следующего года (6040 / event.off)",
            "6038 не выполнен: команда №5: отказ — событие: у персонажа нет GM-флага (CharGmInfo) — сток не выполнил бы",
            "6020 не выполнен: команда №6: отказ — пересчёт рейтингов: слишком часто — повтор через 41 с (MinIntervalSec P25)",
            "событие: в игре нет персонажа служебной учётки 1…5000 на узле с мостом v84+ (узлы: v82) — сток выполняет команду только от оператора в игре",
            "выключение события: нет ни одного GameServer с мостом в режиме исполнения (Mode=1) — сервер команду не получит",
            "внеочередной сброс ежедневных заданий доски всем: строк к сбросу 12 (граница 2026-11-20 06:00, суточный уже сделан)",
            "суточный сброс за границу 2026-11-20 06:00 уже сделан (task, 2026-11-20 06:02:02) — догонять нечего",
            "счастливые часы: 2026-11-23…2026-11-29 (дни недели 67), 06:00–07:00 — опыт +1.0 (×2.0 при базе 1.0), строк +2 (GameServerEvent.txt ×3 GS, после рестарта)",
            "счастливые часы: убрать 2 строк (2026-11-21…2026-11-21) — GameServerEvent.txt ×3 GS, после рестарта",
            "часы пересекаются с уже записанными строками (2026-11-21 02–05 (+0.5)) — у сервера сработала бы только первая строка дня — уберите их (lucky.del) или выберите другие часы",
            "строк с датами 2026-12-01…2026-12-02 нет — убирать нечего", "поле «value»: больше 0 и не больше 10.0", "поле «value»: от 0.0 до 10.0, до двух знаков",
            "NpcServer\\Event\\Event.dat — 2199 б вместо 2200: NpcServer с таким файлом не запустится (sub_44E7D0)",
            "рейт ×3.0 — сильная правка (больше ×2 или меньше ×1): нужно второе подтверждение (ключ rate_ok = rate)",
            "Счастливые часы: добавить (GameServerEvent.txt ×3 GS, опыт +значение в часы каждого дня диапазона; рестарт стойки)"]
    tok = i18n.LANG.set("en")
    try:
        bad_tr = [(m, i18n.tr(m)) for m in msgs if CYR.search(i18n.tr(m))]
    finally:
        i18n.LANG.reset(tok)
    check("переводы EN (core/i18n.py): тексты А5.4 (итоги, предпросмотр, отказы, вложенные ответы узла, части через «; ») — без кириллицы",
          not bad_tr, bad_tr[:3])
    import ast
    lits = []
    for f in (os.path.join(ROOT, "domains", "events.py"), os.path.join(ROOT, "domains", "cs_kinds", "eventdata.py")):
        for nd in ast.walk(ast.parse(open(f, encoding="utf-8").read())):
            if isinstance(nd, ast.Call) and getattr(nd.func, "id", "") == "OpRefused" and nd.args:
                a = nd.args[0]
                a = a.left if isinstance(a, ast.BinOp) else a
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    lits.append(a.value)
    semi = [x for x in lits if "; " in x]
    check("тексты отказов А5.4 (все OpRefused обоих модулей, %d) — без «; »" % len(lits), len(lits) > 40 and not semi, semi[:3])


def sandbox(check, ldb):
    """adm.LimitationReset на своей базе LocalDB: таблицы доски и журнал — как в board_quest_fix_20261028.sql, сток сброса — живой текст М-2."""
    from core import db, ops, audit
    import domains.events as V
    name = "AsdaEvJoy_" + secrets.token_hex(3)
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Arabic_CI_AS" % name)
    saved = (V.SQL, audit.write)
    try:
        cn = ldb(name)
        c = cn.cursor()
        c.execute("CREATE TABLE dbo.CRT_LimitationQuest (Userindex INT, Charidx TINYINT, Quest_Index INT, Quest_Type TINYINT, Quest_Count INT, Quest_Flag TINYINT)")
        fix = open(os.path.join(PORT, "AstoryServer", "SQL", "board_quest_fix_20261028.sql"), encoding="utf-8").read()
        ddl = fix[fix.index("IF OBJECT_ID('dbo.AsdaLimitationResetLog', 'U') IS NULL"):]
        c.execute(ddl[:ddl.index("\nGO")])
        m2 = open(os.path.join(PORT, "AstoryServer", "SQL", "board_quest_m2_fix_20261028.sql"), encoding="utf-8").read()
        proc = m2[m2.index("CREATE OR ALTER PROC dbo.CRT_AsdaLimitationDailyReset"):]
        c.execute(proc[:re.search(r"^\s*GO\s*$", proc, re.M).start()])
        text = open(os.path.join(ROOT, "sql", "adminc_15_events.sql"), encoding="utf-8").read().replace("USE [Joy1];", "USE [%s];" % name)
        for batch in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I):
            if batch.strip():
                c.execute(batch)
        rows = [(9001, 0, 20013, 1, 2, 3), (9001, 0, 20000, 0, 5, 3), (9002, 1, 20014, 1, 0, 1), (9002, 1, 20022, 2, 3, 3), (9003, 0, 20015, 1, 1, 0)]
        c.executemany("INSERT dbo.CRT_LimitationQuest VALUES (?, ?, ?, ?, ?, ?)", rows)
        state = lambda: sorted(tuple(x) for x in c.execute("SELECT Userindex, Quest_Index, Quest_Count, Quest_Flag FROM dbo.CRT_LimitationQuest").fetchall())
        r1 = tuple(c.execute("EXEC adm.LimitationReset 0").fetchone())
        s1 = state()
        r2 = tuple(c.execute("EXEC adm.LimitationReset 0").fetchone())
        check("стенд: adm.LimitationReset 0 (догнать) — сделан (rc 1, «выполнено» 1, счётчиков 2), только Quest_Type 1; повтор за ту же границу — rc 0",
              r1[:3] == (1, 1, 2) and r2[0] == 0
              and s1 == [(9001, 20000, 5, 3), (9001, 20013, 0, 0), (9002, 20014, 0, 1), (9002, 20022, 3, 3), (9003, 20015, 0, 0)], (r1, r2, s1))
        c.execute("UPDATE dbo.CRT_LimitationQuest SET Quest_Count = 4, Quest_Flag = 3 WHERE Quest_Index = 20013")
        r3 = tuple(c.execute("EXEC adm.LimitationReset 1").fetchone())
        log = [tuple(x) for x in c.execute("SELECT Source, Done FROM dbo.AsdaLimitationResetLog ORDER BY Id").fetchall()]
        check("стенд: adm.LimitationReset 1 (внеочередной) — снова сброс (rc 1), журнал: admin|1, admin|0, admin-force|2 (метку суток не трогает)",
              r3[:3] == (1, 1, 1) and log == [("admin", 1), ("admin", 0), ("admin-force", 2)], (r3, log))
        r4 = tuple(c.execute("EXEC adm.LimitationReset 5").fetchone())
        r5 = tuple(c.execute("EXEC adm.LimitationReset 0").fetchone())
        check("стенд: неверный режим — rc −3 без записи; догнать после внеочередного — по-прежнему rc 0 (Done = 2 не метка суток)",
              r4[0] == -3 and r5[0] == 0 and c.execute("SELECT COUNT(*) FROM dbo.AsdaLimitationResetLog").fetchone()[0] == 4, (r4, r5))
        # daily.reset через настоящий GameWriter (подмена подключения на стенд)
        c.execute("UPDATE dbo.CRT_LimitationQuest SET Quest_Count = 7 WHERE Quest_Index = 20015")
        db.set_override("ops", lambda database: ldb(name))
        V.SQL = lambda q, params=(): [{"n": 1}] if "COUNT" in q else ([{"n": datetime.datetime.now()}] if "GETDATE" in q else [])
        audit.write = lambda *a, **k: 1
        cli = ops.Ctx(None, "cli:t", "owner", "", "cli")
        r = ops.run(cli, "daily.reset", {"mode": "force", "confirm": "daily"})
        cnt = c.execute("SELECT Quest_Count FROM dbo.CRT_LimitationQuest WHERE Quest_Index = 20015").fetchone()[0]
        check("стенд: daily.reset force через GameWriter — EXEC adm.LimitationReset, зафиксировано (счётчик 7 → 0), итог «сброшено»",
              cnt == 0 and "сброшено" in r["message"], (cnt, r["message"]))
        cn.close()
    finally:
        db.set_override("ops", None)
        V.SQL, audit.write = saved
        try:
            m.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % name)
            m.cursor().execute("DROP DATABASE [%s]" % name)
        except Exception:
            pass


def live(check):
    """Только чтение и сухие предпросмотры (dry=True): ничего не включается, не выключается и не сбрасывается."""
    from core import config, ops
    import domains.events as V
    from domains import load_all
    load_all()      # ★ ревизия 87 Н-1 (24.11): разделы — как у службы и консоли; иначе операция чужого раздела — «неизвестная операция»
    if config.get().on_server:
        return check("живой самотест А5.4 — с ПК", True)
    st = V.state()
    check("живое состояние (SSH, только чтение): Event.dat трёх NpcServer прочитан, 2200 б; GameServerEvent.txt трёх GS прочитан и одинаков",
          all(st["npc"][n]["read"] and st["npc"][n]["size"] == 2200 for n in V.NPC)
          and len({st["lucky"][g]["md5"] for g in V.GS}) == 1 and all(st["lucky"][g]["read"] for g in V.GS) and st["map_count"],
          ([(n, st["npc"][n]["md5"]) for n in V.NPC], [(g, st["lucky"][g]["md5"], st["lucky"][g]["rows"]) for g in V.GS], st["warnings"][:3]))
    check("живое состояние: окна событий разобраны (тип, карты, фаза), список карт Indun = поле", isinstance(st["windows"], list)
          and all(w["phase"] in ("active", "ahead", "past", "never") for w in st["windows"]), [(w["type_name"], w["window"], w["phase"]) for w in st["windows"]])
    # ★ ревизия 49 Н-1: по факту установки P128 — узел без пульса «не прочитано», ниже v85 «нужна DLL», иначе режим секции по журналу патчей
    nd = {n["node"]: n for n in st["nodes"]}
    check("А5.10 живое: значок события у игроков на каждом GS — нет пульса → «не прочитано», DLL ниже v85 → «нужна DLL v85», v85+ → режим "
          "[P128_EventBadgeAll] по журналу патчей; текст строки есть",
          set(st["badge_why"]) == set(V.GS) and all(
              (st["badge_why"][g] == "nopulse") if not (nd.get(g) or {}).get("fresh")
              else (st["badge_why"][g] == "ver") if int(nd[g].get("ver") or 0) < 85
              else st["badge_why"][g] in ("all", "off", "failed", "absent", "unread") for g in V.GS)
          and all(st["badge_text"][g] == V.BADGE_TEXT[st["badge_why"][g]] for g in V.GS), (st["badge_why"], st["nodes"]))
    d = V.daily_state()
    check("живые ежедневные (только чтение): граница суток, строк к сбросу, журнал сброса и задача ОС прочитаны",
          d["boundary"] and isinstance(d["pending_rows"], int) and d["log"] is not None, (d["boundary"], d["pending_rows"], d["done"], d["task"]))
    cli = ops.Ctx(None, "cli:selftest@pc", "owner", "", "cli")
    vers = {int(n.get("ver") or 0) for n in st["nodes"]}
    loc = datetime.datetime.strptime(st["server_now"], "%Y-%m-%d %H:%M:%S")
    p = {"type": 1, "value": "1.0", "start": (loc + datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
         "end": (loc + datetime.timedelta(days=1, hours=1)).strftime("%Y-%m-%d %H:%M"), "confirm": "event", "auto_off": "0"}
    if (loc + datetime.timedelta(days=1, hours=1)).year != (loc + datetime.timedelta(days=1)).year:
        p["start"], p["end"] = (loc + datetime.timedelta(days=2)).strftime("%Y-%m-%d 01:00"), (loc + datetime.timedelta(days=2)).strftime("%Y-%m-%d 02:00")
    res = {}
    for name, prm in (("event.set", p), ("rank.recalc", {"what": 3, "confirm": "rank"})):
        try:
            ops.run(cli, name, prm, dry=True)
            res[name] = "предпросмотр"
        except ops.OpRefused as ex:
            res[name] = str(ex)
    ok = all(v == "предпросмотр" or "v84+" in v or "GM-флаг" in v or "Mode=1" in v for v in res.values()) if max(vers or {0}) >= 84 \
        else all("v84+" in v or "Mode=1" in v for v in res.values())
    check("живые сухие предпросмотры event.set / rank.recalc (ничего не отправлено): на узлах без v84 — честный отказ «v84+»", ok, (res, sorted(vers)))
    try:
        pv = ops.run(cli, "daily.reset", {"mode": "catchup"}, dry=True)["preview"]["text"]
    except ops.OpRefused as ex:
        pv = str(ex)
    check("живой сухой предпросмотр daily.reset catchup (ничего не сброшено): «догонять нечего» или текст с границей суток",
          "догонять нечего" in pv or d["boundary"] in pv, pv)
