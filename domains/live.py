# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""live.py — действия ЖИВЬЁМ через мост P127 (волна А2, 18.11.2026): отключить игрока с сервера, объявление всем, «кто в игре».

Мост — core/bridge.py (очередь AsdaAdmin.adm.bridge_cmd, исполнение — в нити карты GameServer, DLL AsdaPatch P127). Моста нет
(не выложен / пульс старый / узел в режиме «только слушать») — отказ с причиной, ничего не делается. Журнал панели (adm.audit)
пишет ops.run, итог команды — adm.bridge_cmd (номер — в «после»). Не откатываются (действие уже произошло на сервере).
Побочных эффектов при импорте нет.
"""
import time

from core import bridge
from core.ops import Operation, OpRefused, register

ANNOUNCE_MAX = 95          # байт cp1251 в теле 3113 (+4…+99), клиент читает ≤ 96
CP1251_WARN = "в тексте есть символы вне cp1251 (эмодзи, арабский и т. п.) — в игре они станут «?»"   # ★ ревизия 42 (мелочь)


def cp1251_lossy(text):
    """★ ревизия 42: есть ли в тексте символы, которых нет в cp1251 (тело 3113 — cp1251, они станут «?»)."""
    try:
        text.encode("cp1251")
        return False
    except UnicodeEncodeError:
        return True


def who(uid=None):
    """Кто в игре по данным мостов + состояние узлов (для API /api/bridge)."""
    from domains import refdata
    rows = bridge.presence(uid)
    for r in rows:
        try:
            r["map_name"] = refdata.map_name(int(r["map"])) or ""        # ★ А5.2: «кто в игре» по картам — название карты
        except Exception:
            r["map_name"] = ""
        for k in ("since", "seen"):
            if r.get(k) is not None:
                r[k] = str(r[k])
    nodes = bridge.nodes()
    for n in nodes:
        for k in ("started", "heartbeat"):
            if n.get(k) is not None:
                n[k] = str(n[k])
    return {"nodes": nodes, "presence": rows}


@register
class LiveKick(Operation):
    name, title, perm, reversible = "live.kick", "Живьём: отключить игрока с сервера (мост)", "players.kick", False

    def target(self, p):
        return "account:%s" % p.get("uid")

    def preview(self, ctx, p):
        try:
            uid = int(p["uid"])
        except (KeyError, TypeError, ValueError):
            raise OpRefused("неверные параметры")
        rows = bridge.can_kick(uid)
        if not rows:
            raise OpRefused("мост не может отключить учётку %d: её нет в игре по данным моста, узел без пульса или в режиме "
                            "«только слушать»" % uid)
        return {"text": "отключить с сервера (штатный выход с записью): %s"
                        % ", ".join("%s на %s (карта %s)" % (r["charname"], r["node"], r["map"]) for r in rows),
                "expect": [[r["node"], int(r["user_num"])] for r in rows], "uid": uid}

    def apply(self, ctx, p, prev):
        try:
            done = bridge.kick_and_wait([prev["uid"]], by=ctx.login)
        except bridge.BridgeError as ex:
            raise OpRefused(str(ex))
        return {"before": {"uid": prev["uid"], "presence": prev["expect"]}, "after": {"uid": prev["uid"], "kicked": done},
                "message": "отключён: " + ", ".join("%s на %s" % (d["char"], d["node"]) for d in done)}


@register
class LiveAnnounce(Operation):
    name, title, perm, reversible = "live.announce", "Живьём: объявление всем игрокам (мост, 3113)", "server.announce", False
    schedule_runner = "service"           # ★ А5.1: ставится в задания планировщика (исполняет служба на сервере, core/jobs.py)

    def target(self, p):
        return "server"

    def schedule_check(self, ctx, p):
        """Текст и цвет (то же при постановке в задание, без опроса моста) → (текст, rgb)."""
        text = str(p.get("text") or "").strip()
        if not text:
            raise OpRefused("пустое объявление")
        if len(text.encode("cp1251", "replace")) > ANNOUNCE_MAX:
            raise OpRefused("объявление длиннее %d символов" % ANNOUNCE_MAX)
        rgb = p.get("rgb") or [255, 255, 255]
        try:
            rgb = [max(0, min(255, int(c))) for c in rgb][:3]
        except (TypeError, ValueError):
            raise OpRefused("неверный цвет")
        if len(rgb) != 3:
            raise OpRefused("неверный цвет")
        if p.get("discord"):                  # ★ А7.4: «и в Discord» — поля и право community.post проверяются и при постановке в задание
            from domains import outbox
            outbox.check(ctx, p["discord"], text)
        return text, rgb

    def preview(self, ctx, p):
        text, rgb = self.schedule_check(ctx, p)
        dc = None
        if p.get("discord"):                  # ★ А7.4 (решение владельца А7 №2): объявление ещё и в Discord — только по флажку оператора
            from domains import outbox
            dc = outbox.check(ctx, p["discord"], text)
            outbox.budget()
        nodes = [n for n in bridge.nodes() if n["fresh"] and int(n["mode"]) == 1]
        if not nodes:
            raise OpRefused("нет ни одного GameServer с мостом в режиме исполнения (Mode=1)")
        out = {"text": "объявление на %s: «%s»" % (", ".join(n["node"] for n in nodes), text), "nodes": [n["node"] for n in nodes],
               "warnings": [CP1251_WARN] if cp1251_lossy(text) else [],
               "args": "r=%d;g=%d;b=%d;text=%s" % (rgb[0], rgb[1], rgb[2], text)}
        if dc:
            out["discord"] = dc
            out["text"] += "\nи в Discord:\n" + outbox.preview_text(dc)
            out["warnings"] += outbox.describe(dc)
        return out

    def apply(self, ctx, p, prev):
        dc = prev.get("discord")
        if not dc:
            return self._game(ctx, p, prev)
        # ★ А7.4: запись в очередь Discord ставится ДО объявления в игру в статусе «ждёт объявления в игру» (бот её не берёт): пределы частоты
        #   проверяются под замком adm.OutboxPut — превышен предел, и в игру ничего не уходит. Объявление в игру не разослано — запись
        #   отменяется. Разослано — запись отпускается боту в той же транзакции, что фиксируется после журнала (ops._finish).
        from core import db
        from domains import outbox
        oid = outbox.put(dc, ctx.login, hold=True)
        try:
            res = self._game(ctx, p, prev)
        except BaseException as ex:
            why = str(ex)[:300]
            try:
                outbox.release(oid, False, ctx.login, why if why.startswith("объявление не разослано") else "объявление в игру не разослано: %s" % why)
            except Exception:
                pass                          # запись остаётся «ждёт объявления в игру» — бот её не возьмёт, в очереди видна, её можно отменить
            raise
        res["after"]["discord"] = {"outbox": oid, "channel": dc["channel"], "role": dc["role"], "ttl": dc["ttl"]}
        cn = None                             # ★ р76 К6
        try:
            cn = db.admin()
            cn.autocommit = False
            n = outbox.release(oid, True, ctx.login, cn=cn)
        except Exception as ex:               # в игру уже ушло — итог операции не ломаем, запись остаётся «ждёт объявления в игру»
            if cn is not None:
                try:
                    cn.close()
                except Exception:
                    pass
            res["after"]["discord"]["released"] = False
            res["message"] += " · в Discord НЕ отпущено: запись очереди №%d не обновилась (%s)" % (oid, str(ex)[:200])
            return res
        if n != 1:
            cn.rollback()
            cn.close()
            res["after"]["discord"]["released"] = False
            res["message"] += " · в Discord НЕ отпущено: запись очереди №%d изменилась (её отменили?)" % oid
            return res
        res["after"]["discord"]["released"] = True
        res["message"] += " · в Discord: запись очереди №%d (публикует бот на ПК)" % oid
        res.update(_commit=cn.commit, _close=cn.close)
        return res

    def _game(self, ctx, p, prev):
        # ★ ревизия 41 С-2: команда ставится во ВСЕ узлы сразу, затем одно общее ожидание (срок ttl + 2 на всё, а не на каждый узел):
        #   худшее время — ttl + 2 с, а не узлы × 22 с. ttl 5…20 (по умолчанию 20; отсчёт рестарта зовёт с 8 — укладывается в предел
        #   вызова restart_stack 30 с вместе с записью журнала)
        try:
            ttl = max(5, min(20, int(p.get("ttl") or 20)))
        except (TypeError, ValueError):
            ttl = 20
        out, bad, sent = [], [], []
        for node in prev["nodes"]:
            try:
                cid, _ = bridge.enqueue("announce", 0, -1, node, prev["args"], ttl, ctx.login)
                sent.append((node, cid))
            except bridge.BridgeError as ex:
                bad.append("%s: %s" % (node, ex))
        end = time.time() + ttl + 2
        for node, cid in sent:
            row = bridge.wait(cid, max(0.0, end - time.time()))
            st = int(row["status"]) if row else 1
            if st == 2:
                out.append({"node": node, "cmd": int(cid), "result": row.get("result")})
            elif st in (0, 1):
                bad.append("%s: команда №%s: итог неизвестен за %d с (узел мог выполнить)" % (node, cid, ttl + 2))
            else:
                bad.append("%s: команда №%s: %s%s" % (node, cid, bridge.STATUS.get(st, st), (" — " + (row.get("result") or "")) if row else ""))
        if not out:
            raise OpRefused("объявление не разослано: " + "; ".join(bad))
        return {"before": None, "after": {"sent": out, "failed": bad},
                "message": "разослано на %d узл.%s" % (len(out), (" (не вышло: %s)" % "; ".join(bad)) if bad else "")}


OPERATOR_MAX_UID = 5000     # sub_52ECF0: оператор — UserIndex 0…5000
CONFIRM_NORMAL = "mobs0"    # ★ ревизия 42 В-1: подтверждение группы 0 и групп с обычными мобами карты (их точка спавна уйдёт к оператору)

# ★ ревизия 42 В-1: справка «вызываемые группы карты» — .svr NpcServer узла (NpcServer.exe.c:55880-56010: ini\MapInfo.ini [MAPINFO]
#   MonsterInfo_%03d = файл в Monster\; файл: int16 число записей в первых 4 байтах, записи по 74 байта; +0x47 u16 группа (mon+37618),
#   +0x49 u8 enable (mon+37620: 1 — сам не появляется, только по вызову = «событийный»)). Только чтение, кэш GROUPS_TTL.
NPC_OF_NODE = {"GameServer": "NpcServer", "Ch2_GameServer": "Ch2_NpcServer", "Indun_GameServer": "Indun_NpcServer"}
SVR_HEAD, SVR_REC, SVR_GROUP, SVR_ENABLE = 4, 74, 0x47, 0x49
GROUPS_TTL = 600
_groups_cache = {}


def owner_accounts():
    """★ ревизия 42 Н-4: служебные игровые учётки владельца (config owner_game_accounts, по умолчанию 1, 2)."""
    from core import config
    out = set()
    for x in str(getattr(config.get(), "owner_game_accounts", "1,2") or "").split(","):
        x = x.strip()
        if x.isdigit():
            out.add(int(x))
    return out


def parse_svr(data):
    """Байты .svr → {группа: {"total", "event"}}. Неверный размер — ValueError."""
    import struct
    if len(data) < SVR_HEAD:
        raise ValueError("файл короче заголовка")
    n = struct.unpack_from("<h", data, 0)[0]
    if n < 0 or len(data) < SVR_HEAD + SVR_REC * n:
        raise ValueError("записей %d, а байт %d" % (n, len(data)))
    out = {}
    for i in range(n):
        rec = SVR_HEAD + SVR_REC * i
        g = struct.unpack_from("<H", data, rec + SVR_GROUP)[0]
        t = out.setdefault(g, {"total": 0, "event": 0})
        t["total"] += 1
        t["event"] += 1 if data[rec + SVR_ENABLE] == 1 else 0
    return out


def groups_text(info):
    """«444 (3 соб.), 445 …» — вызываемые (событийные) группы карты."""
    return ", ".join("%d (%d)" % (g, v["event"]) for g, v in sorted(info["groups"].items()) if v["event"])


def map_groups(node, map_no, read_text=None, read_bytes=None):
    """Группы мобов карты map_no на NpcServer узла node → {"file", "groups"}. Не прочитано — OpRefused («не прочитано» ≠ «нет»)."""
    from core import config, hostshell
    npc = NPC_OF_NODE.get(node)
    if not npc:
        raise OpRefused("у узла %s нет пары NpcServer в справке — группы не прочитаны" % node)
    key = (npc, int(map_no))
    hit = _groups_cache.get(key)
    if hit and time.time() - hit[0] < GROUPS_TTL and not (read_text or read_bytes):
        return hit[1]
    rt = read_text or hostshell.read_server_file
    rb = read_bytes or hostshell.read_server_bytes
    base = config.STACK_ROOT + "\\" + npc
    try:
        ini = rt(base + "\\ini\\MapInfo.ini")
        name = None
        want = "monsterinfo_%03d" % int(map_no)
        for ln in ini.splitlines():
            k, sep, v = ln.partition("=")
            if sep and k.strip().lower() == want:
                name = v.strip().strip('"').strip()
        if not name:
            raise ValueError("в ini\\MapInfo.ini нет MonsterInfo_%03d" % int(map_no))
        groups = parse_svr(rb(base + "\\Monster\\" + name))
    except OpRefused:
        raise
    except Exception as ex:
        raise OpRefused("справка групп карты %s не прочитана (%s): %s" % (map_no, npc, str(ex)[:200]))
    info = {"file": name, "npc": npc, "groups": groups}
    if not (read_text or read_bytes):
        _groups_cache[key] = (time.time(), info)
    return info


class _LiveMob(Operation):
    """★ А5.2 (21.11.2026): 6045 / 6046 мостом от имени ОПЕРАТОРА в игре (реверс — Reports/gm_original_commands/group2_spec.md §7–8,
    GameServer.c:130327-130389; NpcServer CAi::Process_MonsterCall / Process_MonsterReturn). Сток: гейты оператор (UserIndex ≤ 5000) и
    (P47) GM-флаг, затем только пересылка в NpcServer; точка появления группы = координаты ОПЕРАТОРА (NpcServer берёт их из своей записи
    игрока), ответа нет. Поэтому цель — персонаж служебной учётки ≤ 5000 с GM-флагом, который сейчас в игре на карте с этой группой.
    Узел — DLL v83+ (MOB_VER). Необратимо (точка спавна группы остаётся сдвинутой) — подтверждение «mobs»."""
    perm, reversible = "server.monsters", False
    op, opcode = "", 0

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        try:
            uid, idx = int(p["uid"]), int(p["idx"])
        except (KeyError, TypeError, ValueError):
            raise OpRefused("неверные параметры")
        # ★ ревизия 42 В-1: номера группы по умолчанию нет — пустое поле отказ (раньше форма ставила 0 = обычные мобы многих карт)
        g_raw = p.get("group")
        if g_raw is None or isinstance(g_raw, bool) or str(g_raw).strip() == "":
            raise OpRefused("укажите номер группы (справка вызываемых групп карты — в окне)")
        try:
            group = int(g_raw)
        except (TypeError, ValueError):
            raise OpRefused("неверные параметры")
        if not 0 < uid <= OPERATOR_MAX_UID:
            raise OpRefused("монстров вызывает только служебная учётка (номер 1…5000) — так проверяет сток (оператор)")
        if uid in owner_accounts() and ctx.role != "owner":                  # ★ ревизия 42 Н-4
            raise OpRefused("от персонажей служебных учёток владельца (%s) монстров вызывает только владелец"
                            % ", ".join(map(str, sorted(owner_accounts()))))
        if not 0 <= group <= 65535:
            raise OpRefused("номер группы — 0…65535")
        mode = 0
        if self.op == "mob_pop":
            try:
                mode = int(p.get("mode") or 0)
            except (TypeError, ValueError):
                raise OpRefused("неверный режим")
            if mode not in (0, 1):
                raise OpRefused("неверный режим")
        confirm = str(p.get("confirm") or "")
        if confirm not in ("mobs", CONFIRM_NORMAL):
            raise OpRefused("нужно подтверждение действия над монстрами карты, оно не откатывается (ключ confirm = mobs)")
        from core import db
        try:
            with db.GameReader("joy1") as r:
                gm = r.rows("SELECT TOP 1 1 AS x FROM dbo.CharGmInfo WHERE Userindex = ?", (uid,))
        except db.DbError as ex:
            raise OpRefused("GM-флаг учётки не прочитан: %s" % ex)
        if not gm:
            raise OpRefused("у учётки %d нет GM-флага (CharGmInfo) — сток с P47 команду не выполнит" % uid)
        row = bridge.live_row(uid, idx, bridge.MOB_VER)
        if not row:
            raise OpRefused("персонажа %d/%d нет в игре на узле с мостом v%d+ в режиме исполнения (призыв идёт от его позиции)"
                            % (uid, idx, bridge.MOB_VER))
        # ★ ревизия 42 В-1 / С-1: справка групп карты из .svr NpcServer узла (только чтение) — группы нет — отказ; в группе обычные мобы
        #   (enable 0) или группа 0 — отдельное подтверждение mobs0; тексты — что на деле делают 6045 / 6046
        info = map_groups(row["node"], int(row["map"]))
        g = info["groups"].get(group)
        if not g:
            raise OpRefused("группы %d на карте %s нет (%s) — команда ничего не сделает, вызываемые группы карты: %s"
                            % (group, row["map"], info["file"], groups_text(info) or "нет"))
        normal = g["total"] - g["event"]
        if (normal or group == 0) and confirm != CONFIRM_NORMAL:
            raise OpRefused("группа %d на карте %s — обычные мобы карты (%d из %d): их точка появления уйдёт к оператору до рестарта стойки — "
                            "нужно отдельное подтверждение (ключ confirm = %s)" % (group, row["map"], normal, g["total"], CONFIRM_NORMAL))
        warn = []
        if uid not in owner_accounts():
            warn.append("действие идёт от персонажа служебной учётки %d — в журнале сервера (Log_Operator) оно записано на неё" % uid)
        warn.append("GM-флаг действует со следующей загрузки персонажа (перезаход) — иначе узел ответит отказом 32")
        if self.op == "mob_pop":
            warn.append("в группе %d мобов (%s, %d событийных, %d обычных): у стока ответа нет, появятся по таймеру возрождения"
                        % (g["total"], info["file"], g["event"], normal))
            if g["event"]:
                warn.append("событийные мобы группы будут возрождаться снова и снова, пока не дадите 6046 (убрать группу) или не перезапустите стойку")
            if normal:
                warn.append("обычные мобы группы (%d) получат точку появления у оператора — до рестарта стойки" % normal)
            warn.append("точка появления группы останется сдвинутой до рестарта NpcServer (стойки) — 6046 её не возвращает")
            if mode == 1:
                warn.append("режим 1: мобы появятся на своих точках роуминга, а не у персонажа")
        else:
            warn.append("6046: живые мобы группы умрут (исчезнут сразу), их агро сбросится, обычные возродятся штатно, событийные — снова "
                        "заблокированы, точку появления 6046 не возвращает")
        text = "%s: группа %d%s, от персонажа %s (%s, карта %s, клетка %s,%s)" % (
            self.title, group, (", режим %d" % mode) if self.op == "mob_pop" else "", row["charname"], row["node"], row["map"],
            row.get("x"), row.get("z"))
        return {"text": text, "warnings": warn, "row": {k: row[k] for k in ("node", "Userindex", "Charidx", "charname", "map")},
                "args": "group=%d%s" % (group, (";mode=%d" % mode) if self.op == "mob_pop" else ""), "uid": uid, "idx": idx}

    def apply(self, ctx, p, prev):
        r = prev["row"]
        try:
            row = bridge.call(self.op, prev["uid"], prev["idx"], r["node"], prev["args"], ttl=20, by=ctx.login)
        except bridge.BridgeError as ex:
            raise OpRefused("%s не выполнен: %s" % (self.opcode, ex))
        return {"before": None, "after": {"uid": prev["uid"], "idx": prev["idx"], "node": r["node"], "map": r["map"], "args": prev["args"],
                                          "cmd": int(row["id"])},
                "message": row.get("result") or "%d отправлен" % self.opcode}


@register
class LiveMobPop(_LiveMob):
    name, title, op, opcode = "live.mob_pop", "Живьём: вызвать группу монстров к оператору (6045)", "mob_pop", 6045


@register
class LiveMobReturn(_LiveMob):
    name, title, op, opcode = "live.mob_return", "Живьём: убрать (вернуть) группу монстров (6046)", "mob_return", 6046


@register
class LiveNotice(Operation):
    name, title, perm, reversible = "live.notice", "Живьём: сообщение одному игроку (мост, 3113)", "server.announce", False

    def target(self, p):
        return "account:%s" % p.get("uid")

    def preview(self, ctx, p):
        try:
            uid = int(p["uid"])
        except (KeyError, TypeError, ValueError):
            raise OpRefused("неверные параметры")
        text = str(p.get("text") or "").strip()
        if not text:
            raise OpRefused("пустое сообщение")
        if len(text.encode("cp1251", "replace")) > ANNOUNCE_MAX:
            raise OpRefused("сообщение длиннее %d символов" % ANNOUNCE_MAX)
        rgb = p.get("rgb") or [255, 255, 255]
        try:
            rgb = [max(0, min(255, int(c))) for c in rgb][:3]
        except (TypeError, ValueError):
            raise OpRefused("неверный цвет")
        if len(rgb) != 3:
            raise OpRefused("неверный цвет")
        rows = [r for r in bridge.can_kick(uid) if int(r.get("ver") or 0) >= bridge.LIVE_VER]
        if not rows:
            raise OpRefused("учётки %d нет в игре на узле с мостом v%d+ в режиме исполнения" % (uid, bridge.LIVE_VER))
        return {"text": "сообщение %s: «%s»" % (", ".join("%s на %s" % (r["charname"], r["node"]) for r in rows), text), "rows": rows,
                "args": "r=%d;g=%d;b=%d;text=%s" % (rgb[0], rgb[1], rgb[2], text), "uid": uid}

    def apply(self, ctx, p, prev):
        out, bad = [], []
        for r in prev["rows"]:
            try:
                row, text = bridge.live_call("notice", r, prev["args"], by=ctx.login)
                out.append({"char": r["charname"], "node": r["node"], "cmd": int(row["id"])})
            except bridge.BridgeError as ex:
                bad.append("%s: %s" % (r["charname"], ex))
        if not out:
            raise OpRefused("сообщение не доставлено: " + "; ".join(bad))
        return {"before": None, "after": {"uid": prev["uid"], "sent": out, "failed": bad},
                "message": "доставлено: %s%s" % (", ".join(o["char"] for o in out), (" (не вышло: %s)" % "; ".join(bad)) if bad else "")}
