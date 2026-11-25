# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""bridge.py — живой канал «админ-центр → работающий GameServer» (мост P127, волна А2, 18.11.2026).

Разбор: Reports/admin_center/research_admin_bridge.md; DLL: AsdaPatch P127 (AstoryServer/Docs/GameServer/admin-bridge-p127.md);
SQL: sql/adminc_07_bridge.sql. Решения владельца 18.11: панели не важно, в игре ли игрок; очередь в базе AsdaAdmin; HMAC команд;
каждая команда — не больше одного раза; игрок вышел до выполнения — «нет на сервере».

ЧТО ДАЁТ
  * nodes() / available() — узлы GameServer и их пульс (старше NODE_FRESH_S — «моста нет»), режим (0 — только слушать, 1 — исполнять);
  * presence(uid) — «кто в игре» от самого GameServer (adm.bridge_presence по свежим узлам; учётка-владелец ИЛИ учётка сессии);
  * enqueue() / wait() / call() — поставить подписанную команду (adm.BridgeEnqueue) и дождаться итога с тайм-аутом;
  * kick_and_wait(uids) — путь «кик + запись»: кик всех сессий учёток мостом, ожидание штатного выхода с записью в БД
    (CharPos.UserNum = −1, Us_member.Flag = 0, строка JoyLog1.LogInfo.Logout после кика + пауза SETTLE_S — см. ниже), затем
    офлайн-запись раздела идёт как прежде, под своей блокировкой;
  * kick_plan() — рамка для core/ops.py: пока она открыта, items.online_state на ПРЕДПРОСМОТРЕ не отказывает «в игре», если мост
    может вывести игрока (узел свежий, Mode=1, игрок виден в присутствии), а записывает учётку в план кика. ops.run выполняет кик
    ДО apply (запись под блокировкой не должна ждать выхода — выход сам пишет те же строки).
  Моста нет (не выложен, пульс старый, Mode=0, игрок не виден — например, на выборе персонажа) → прежний отказ «не в игре».

ПОРЯДОК ЗАПИСЕЙ ПРИ ВЫХОДЕ (реверс А2.0, GameServer.c DisConnectUser@0x5245D0 → DBManager sub_40C5C0 / UPLogoutGame):
  GS шлёт 2003 (UPLogoutGame), затем 2154 (UPSkillItemStatusUP, UPLogoutGameSMStatus) и 2143 (UPEpisodeTime). UPLogoutGame ПЕРВЫМ
  ставит CharPos.UserNum = −1 и Us_member.Flag = 0, и только ПОТОМ пишет Charinfo (уровень, опыт, статы) и JoyLog1.LogInfo.Logout
  (EXEC JoyLog1.dbo.UPLogOut). Поэтому «UserNum = −1» ещё не значит «записано»: ждём строку LogInfo с Logout после кика и паузу.

ПОДПИСЬ: mac = HMAC-SHA256(BRIDGE_HMAC_KEY, UTF-8 "v2|nonce|op|Userindex|Charidx|node|args|ttl|deadline") — hex, deadline — секунды
  UNIX UTC (ревизия 24 К-2); ключ — в файле секретов
  службы (secrets\\asda_admin.ini) и в ConfigSet\\admin_bridge.ini каждого GameServer (кладёт tools/deploy_p127.py). Не печатается.
Побочных эффектов при импорте нет.
"""
import contextlib
import hashlib
import hmac
import threading
import time
import uuid

from . import db

OPS = ("ping", "kick", "announce", "move", "probe", "exp", "title_add", "title_del", "fame_recalc", "notice", "give", "jump",
       "mob_pop", "mob_return", "event_set", "event_off", "rank_recalc")
MOB_VER = 83                 # ★ А5.2: призыв / возврат группы монстров (mob_pop / mob_return, 6045 / 6046) — узлы с DLL v83+
EVENT_VER = 84               # ★ А5.4: события 6038 / 6040 (event_set / event_off) и пересчёт рейтингов 6020 (rank_recalc) — узлы с DLL v84+
LIVE_VER = 81                # ★ А2.2: живые правки (probe/exp/title_add/title_del/fame_recalc/notice) — узлы с DLL v81+
GIVE_VER = 82                # ★ А2.3: выдача предмета (give) и перенос в своей карте (jump) — узлы с DLL v82+ (иначе «кик + запись»)
NODE_FRESH_S = 15            # пульс старше — узла нет
SETTLE_S = 3.0               # пауза после строки LogInfo: следом за UPLogoutGame идут 2154 и 2143
KICK_TTL_S = 20              # срок команды кика
KICK_EXIT_S = 40             # сколько ждать штатного выхода после кика
KICK_WAIT_EXTRA_S = 5        # сверх срока команды: опрос узла (PollMs) и запись итога
STATUS = {0: "в очереди", 1: "захвачена узлом", 2: "выполнена", 3: "отказ", 4: "нет на сервере", 5: "просрочена",
          6: "журнал (узел в режиме «только слушать»)"}

_tl = threading.local()      # план кика текущей операции (kick_plan)
_fake = {}                   # самотест: "transport" → подставной мост (см. tests/selftest.py)


class BridgeError(Exception):
    """Мост недоступен или команда не выполнена (с понятной причиной). ★ ревизия 29: cid — номер команды (если поставлена), status /
    code — итог узла (adm.bridge_cmd.status / result_code), unknown — итога нет за срок (узел МОГ выполнить)."""

    def __init__(self, msg, cid=None, status=None, code=None, unknown=False):
        Exception.__init__(self, msg)
        self.cid, self.status, self.code, self.unknown = cid, status, code, unknown


def set_fake(transport):
    """Самотест: подставной мост (объект с методами nodes/presence/enqueue/get/db_now/exited) или None."""
    if transport is None:
        _fake.pop("t", None)
    else:
        _fake["t"] = transport


# ─────────────────────────────── транспорт (AsdaAdmin) ───────────────────────────────

class _Sql:
    """Настоящий мост: таблицы и процедуры adm.bridge_* в AsdaAdmin под логином панели."""

    def _rows(self, sql, params=()):
        cn = db.admin()
        try:
            return db.admin_rows(cn, sql, params)
        finally:
            cn.close()

    def nodes(self):
        return self._rows("SELECT node, pid, ver, proto, mode, started, heartbeat, claimed, done, errors, present, "
                          "DATEDIFF(second, heartbeat, SYSUTCDATETIME()) AS age_s FROM adm.bridge_node ORDER BY node")

    def presence(self, uid=None):
        q = ("SELECT p.node, p.user_num, p.Userindex, p.Charidx, p.session_uid, p.charname, p.map, p.x, p.z, p.since, p.seen, "
             "n.mode, n.ver FROM adm.bridge_presence p JOIN adm.bridge_node n ON n.node = p.node "
             "WHERE DATEDIFF(second, n.heartbeat, SYSUTCDATETIME()) <= ?")
        if uid is None:
            return self._rows(q + " ORDER BY p.node, p.user_num", (NODE_FRESH_S,))
        return self._rows(q + " AND (p.Userindex = ? OR p.session_uid = ?) ORDER BY p.node, p.user_num", (NODE_FRESH_S, uid, uid))

    def enqueue(self, nonce, op, uid, idx, node, args, ttl, mac, by, audit_id, deadline):
        r = self._rows("SET NOCOUNT ON; DECLARE @id BIGINT; EXEC adm.BridgeEnqueue ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, @id OUTPUT; "
                       "SELECT @id AS id, SYSUTCDATETIME() AS at_utc, GETDATE() AS at_local",
                       (nonce, op, uid, idx, node, args, ttl, mac, by, audit_id, deadline))
        return int(r[0]["id"]), r[0]["at_local"]

    def get(self, cid):
        r = self._rows("SELECT id, op, Userindex, Charidx, node, status, claimed_node, result_code, result, created, done "
                       "FROM adm.bridge_cmd WHERE id = ?", (cid,))
        return r[0] if r else None

    def exited(self, rows, since_local):
        """Выход ВСЕХ кикнутых строк записан (см. exit_written)."""
        with db.GameReader("joy1") as r, db.GameReader("asdastoryop") as op, db.GameReader("joylog1") as lg:
            return exit_written(r, op, lg, rows, since_local)


def exit_written(joy, op, log, rows, since_local):
    """★ ревизия 24 М-2/К-3: выход записан по КАЖДОЙ кикнутой строке присутствия — по ХОЗЯИНУ персонажа (CUser+0x174 = строка
    Userindex): UPLogOutGame чистит CharPos(хозяин, слот) и Us_member[хозяин], UPLogOut пишет LogInfo по Us_member[хозяин].Loginidx
    (вход соулмейтом: правится учётка сессии, а пишутся строки партнёра). Строка LogInfo — с Logout не раньше кика (без допуска)."""
    for r in rows:
        uid, idx = int(r["Userindex"]), int(r["Charidx"])
        cp = joy.rows("SELECT UserNum FROM CharPos WHERE Userindex = ? AND Charidx = ?", (uid, idx))
        if not cp or cp[0]["UserNum"] is None or int(cp[0]["UserNum"]) != -1:
            return False
        m = op.rows("SELECT Flag, UserNum FROM Us_member WHERE Userindex = ?", (uid,))
        if not m or m[0]["Flag"] != 0 or m[0]["UserNum"] != -1:
            return False
        if not log.rows("SELECT TOP 1 Logout FROM LogInfo WHERE Userindex = ? AND Logout >= ? ORDER BY Logout DESC", (uid, since_local)):
            return False
    return True


class _Reader:
    """GameReader с rows() как у GameWriter (для items.online_state)."""

    def __init__(self, r):
        self.r = r

    def rows(self, sql, params=()):
        return self.r.rows(sql, params)


def _t():
    return _fake.get("t") or _Sql()


def _key():
    k = db._secret("BRIDGE_HMAC_KEY")
    try:
        b = bytes.fromhex(k)
    except ValueError:
        raise BridgeError("ключ моста в файле секретов не hex")
    if len(b) < 16:
        raise BridgeError("ключ моста короче 16 байт")
    return b


def sign(key, nonce, op, uid, idx, node, args, ttl, deadline):
    """Подпись команды (та же строка, что проверяет P127 MacOk; ★ ревизия 24 К-2: v2 — со сроком deadline, секунды UNIX UTC)."""
    msg = "v2|%s|%s|%d|%d|%s|%s|%d|%d" % (nonce, op, uid, idx, node or "", args or "", ttl, deadline)
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).hexdigest()


# ─────────────────────────────── узлы и присутствие ───────────────────────────────

def nodes():
    """Узлы с пульсом: dict(node, mode, age_s, fresh, …)."""
    try:
        out = _t().nodes()
    except db.DbError:
        return []
    for n in out:
        n["fresh"] = n.get("age_s") is not None and int(n["age_s"]) <= NODE_FRESH_S
    return out


def available(mode=1):
    """Есть ли хоть один свежий узел в режиме ≥ mode."""
    return any(n["fresh"] and int(n["mode"]) >= mode for n in nodes())


def presence(uid=None):
    """Кто в игре по данным мостов (только свежие узлы). uid — учётка-владелец или учётка сессии."""
    try:
        return _t().presence(uid)
    except db.DbError:
        return []


def can_kick(uid):
    """Строки присутствия учётки, если мост может вывести ВСЕ её сессии (узлы свежие и Mode=1); иначе []."""
    rows = presence(uid)
    if not rows:
        return []
    fresh = {n["node"]: n for n in nodes() if n["fresh"]}
    if any(r["node"] not in fresh or int(fresh[r["node"]]["mode"]) != 1 for r in rows):
        return []
    return rows


# ─────────────────────────────── команды ───────────────────────────────

def enqueue(op, uid, idx, node, args="", ttl=30, by="", audit_id=None):
    """Поставить подписанную команду → (id, время постановки по часам SQL — local)."""
    if op not in OPS:
        raise BridgeError("неизвестная команда моста %s" % op)
    nonce = str(uuid.uuid4())
    deadline = int(time.time()) + int(ttl)                      # срок подписывается (часы панели и SQL — одна машина)
    mac = sign(_key(), nonce, op, int(uid), int(idx), node, args, int(ttl), deadline)
    try:
        return _t().enqueue(nonce, op, int(uid), int(idx), node, args or "", int(ttl), mac, (by or "")[:64], audit_id, deadline)
    except db.DbError as ex:
        raise BridgeError("команда не поставлена: %s" % ex)


def wait(cid, timeout=20.0, step=0.25):
    """Ждать итог команды (status ∉ {0, 1}) не дольше timeout → строка adm.bridge_cmd (status 1 — «неизвестно»)."""
    end = time.time() + timeout
    row = None
    while True:
        row = _t().get(cid)
        if row and int(row["status"]) not in (0, 1):
            return row
        if time.time() >= end:
            return row
        time.sleep(step)


def call(op, uid, idx, node, args="", ttl=30, by="", timeout=None):
    """Поставить и дождаться: итог 2 → строка; иначе BridgeError с причиной."""
    cid, _ = enqueue(op, uid, idx, node, args, ttl, by)
    row = wait(cid, timeout if timeout is not None else ttl + 2)
    st = int(row["status"]) if row else 1
    if st in (0, 1):
        # ★ ревизия 25 К-3: итога нет за срок — узел МОГ выполнить (захватил и не успел записать): не «отказ», а «неизвестно»
        raise BridgeError("команда №%s: итог неизвестен за %d с (узел мог выполнить) — проверьте персонажа и журнал моста" % (cid, ttl + 2),
                          cid=cid, status=st, unknown=True)
    if st != 2:
        raise BridgeError("команда №%s: %s%s" % (cid, STATUS.get(st, st), (" — " + (row.get("result") or "")) if row else ""),
                          cid=cid, status=st, code=int(row.get("result_code") or 0) if row else None)
    return row


def get_cmd(cid):
    """★ ревизия 29 М-2: строка команды из adm.bridge_cmd (поздний итог) или None."""
    try:
        return _t().get(int(cid))
    except db.DbError as ex:
        raise BridgeError("журнал моста недоступен: %s" % ex)


def kick_and_wait(uids, by="", exit_timeout=KICK_EXIT_S):
    """Путь «кик + запись», шаг 1: вывести все сессии учёток uids и дождаться штатного выхода с записью. → список кикнутых строк.
    Ничего не пишет в игровые базы. Не вышло — BridgeError (её .kicked — кого уже вывели: для журнала)."""
    done = []
    try:
        for uid in sorted(set(int(u) for u in uids)):
            rows = can_kick(uid)
            if not rows:
                raise BridgeError("учётка %d: мост не может вывести игрока (узел без пульса, Mode=0 или игрок не виден мосту)" % uid)
            started = None
            for r in rows:
                cid, at_local = enqueue("kick", int(r["Userindex"]), int(r["Charidx"]), r["node"], "", KICK_TTL_S, by)
                started = started or at_local
                # ★ ревизия 24 К-9: ждать столько, сколько живёт команда у узла (срок KICK_TTL_S) + опрос узла
                row = wait(cid, KICK_TTL_S + KICK_WAIT_EXTRA_S)
                st = int(row["status"]) if row else 1
                if st == 1 or st == 0:
                    raise BridgeError("кик %s (%s) на %s: итога нет за %d с — кик МОГ выполниться, проверьте"
                                      % (r["charname"], uid, r["node"], KICK_TTL_S + KICK_WAIT_EXTRA_S))
                if st not in (2, 4):                       # 4 — уже вышел сам: тоже годится
                    raise BridgeError("кик %s (%s) на %s: %s — %s" % (r["charname"], uid, r["node"], STATUS.get(st, st),
                                                                    (row or {}).get("result") or ""))
                done.append({"uid": uid, "char": r["charname"], "node": r["node"], "cmd": cid, "status": st,
                             "owner": int(r["Userindex"]), "idx": int(r["Charidx"])})
            end = time.time() + exit_timeout
            while not _t().exited(rows, started):
                if time.time() >= end:
                    raise BridgeError("учётка %d: после кика выход за %d с не записан (CharPos/Us_member/LogInfo хозяина) — запись не начата"
                                      % (uid, exit_timeout))
                time.sleep(0.5)
    except BridgeError as ex:
        ex.kicked = done
        raise
    if done:
        time.sleep(SETTLE_S)
    return done


def kicked_text(kicked):
    """Кто отключён (для журнала и сообщений)."""
    return ", ".join("%s на %s (команда №%s)" % (k["char"], k["node"], k["cmd"]) for k in kicked)


# ─────────────────────────────── план кика операции ───────────────────────────────

@contextlib.contextmanager
def kick_plan():
    """Рамка операции (ops.run / ops.undo): пока открыта, items.online_state без блокировки пропускает «в игре», если мост может
    вывести игрока, и записывает учётку в план; с блокировкой (запись/откат) — только записывает (для повтора отката после кика)."""
    prev = getattr(_tl, "plan", None)
    _tl.plan = {"uids": set(), "blocked": set()}
    try:
        yield _tl.plan
    finally:
        _tl.plan = prev


def plan_offer(uid, lock):
    """Зовёт items.online_state, когда учётка в игре. True — предпросмотр может продолжать (кик будет до записи)."""
    plan = getattr(_tl, "plan", None)
    if plan is None:
        return False
    if not can_kick(uid):
        return False
    if lock:
        plan["blocked"].add(int(uid))
        return False
    plan["uids"].add(int(uid))
    return True


def live_row(uid, idx, min_ver=LIVE_VER):
    """★ А2.2: строка присутствия персонажа (uid — ХОЗЯИН, idx — слот), если на его узле можно править живьём: узел свежий, Mode=1,
    версия DLL ≥ min_ver (узел v80 новых команд не знает — тогда «кик + запись»). Иначе None."""
    rows = [r for r in can_kick(uid) if int(r["Userindex"]) == int(uid) and int(r["Charidx"]) == int(idx)]
    if len(rows) != 1 or int(rows[0].get("ver") or 0) < min_ver:
        return None
    return rows[0]


def parse_kv(text):
    """«k=v;k=v» → dict (числа — int)."""
    out = {}
    for part in (text or "").split(";"):
        k, sep, v = part.partition("=")
        if sep:
            try:
                out[k.strip()] = int(v)
            except ValueError:
                out[k.strip()] = v
    return out


def probe(row, title=None, by=""):
    """★ А2.2: снимок персонажа по памяти сервера (только чтение): lvl, exp, map, x, z, owned (звание title), cap. → dict."""
    r = call("probe", int(row["Userindex"]), int(row["Charidx"]), row["node"], "" if title is None else "title=%d" % int(title),
             ttl=15, by=by)
    return parse_kv(r.get("result"))


def live_call(op, row, args, by=""):
    """★ А2.2: живая правка → (строка команды, текст итога). Отказ узла — BridgeError с текстом узла."""
    r = call(op, int(row["Userindex"]), int(row["Charidx"]), row["node"], args, ttl=20, by=by)
    return r, r.get("result") or ""


LIVE_WARN = ("игрок в игре: правка идёт ЖИВЬЁМ через сервер (как событие игры) — запись в базу делает сам сервер; журнал панели "
             "хранит номер команды моста")
LIVE_NO_UNDO = "правка живьём (мост) журналом не откатывается: у сервера нет обратного события — исправьте новым действием"

KICKED_WARN = ("игрок только что отключён с сервера мостом: предпросмотр построен по данным, которые записал его выход — "
               "проверьте и подтвердите ещё раз")


def plan_warning(uids):
    """Предупреждение в предпросмотр."""
    return ("игрок сейчас в игре (учётки %s): при применении мост ОТКЛЮЧИТ его с сервера (штатный выход с записью), затем "
            "правка запишется в базу" % ", ".join(str(u) for u in sorted(uids)))
