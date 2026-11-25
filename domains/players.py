# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""players.py — раздел «Игроки» (волна А0: ТОЛЬКО ЧТЕНИЕ): поиск, карточка учётки, карточка персонажа. 16.11.2026.

ИСТОЧНИКИ (схема снята с живой БД 16.11.2026):
  учётка      AsdaStoryOp.dbo.Us_member (Userindex ↔ Us_id; us_block, us_pw*, Flag/UserNum), BlockList / BlockHistory;
              Joy1.dbo.CharGmInfo (операторы), Userindex 0…5000 — служебные учётки (гейт sub_52ECF0 сервера);
              AsdaStoryLogin: [user] (username = Us_id; столбец password закрыт правами), GP7Balance, GP7PurchaseLog;
              joylog1.dbo.LogInfo — входы (IP, MAC) — только с правом players.view_net.
  персонаж    Joy1.dbo.Charinfo, CharPos (карта Poridx, Posx/Posy, Usernum ≠ −1 = в игре), ClanMember/ClanData,
              Item (все сумки), ItemPostBox (премиум-ящик), Exitem (лоты аукциона), CharSkill, CharPetList, CharFriend,
              SoulMate (по учётке), CharFame (звания), CharEpisode (задания), CharIntroduce, CharGmInfo;
              удалённые — Del_Charinfo / Del_item. Склад (Plate 5) — у КАЖДОГО персонажа свой (ревизия А0 №8):
              он в карточке персонажа; в карточке учётки — сводно по всем персонажам.
  ⚠ Пока игрок в игре, GameServer держит персонажа в памяти — карточка показывает состояние на последнее сохранение.
Побочных эффектов при импорте нет.
"""
import datetime
import re

from core import db
from domains import refdata

OPERATOR_MAX_UID = 5000      # служебные учётки (asda_give.OPERATOR_MAX_UID)
SEARCH_LIMIT = 50

ITEM_COLS = ("Userindex, Charidx, Uuid, Code, Plate, Posx, Amount, Durability, Weight, Upcount, AcuUpcnt, MaxupCnt, "
             "Updamage, Opidx1, OpValue1, Opidx2, OpValue2, Opidx3, Opvalue3, Opidx4, Opvalue4, OPidx5, Opvalue5, "
             "Cell1, Cell2, Cell3, Cell4, Refine, Owner, GainDate, Fdate, Rdate")
CHAR_COLS = ("Userindex, Charidx, Charname, Gender, Lvl, Expe, JobCount, Class, Job, Subjob, SkillPoint, MaxWeight, "
             "Weight, MaxHp, MaxMp, Hp, Mp, ActPoint, DonationPoint, Strength, Agility, Health, Spell, Mentality, "
             "Fortune, StrengthP, AgilityP, HealthP, SpellP, MentalityP, FortuneP, MinAttack, MaxAttack, MinMagicAtt, "
             "MaxMagicAtt, MagicDefense, MinDefense1, MaxDefense1, Critical, Evasion, WareCount, CwareCount, PetCount")

IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){1,3}\.?$")
MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([-:]?[0-9A-Fa-f]{2}){2,5}$")


# Адреса, по которым учётки НЕ связываются (ревизия А0 №3): заглушка «0», сам сервер, адреса стойки и VPN.
# Связь по IP — только по публичным адресам (ipaddress.is_global): частные 192.168.x.x общие у всех за одним роутером.
NOT_LINKABLE_IPS = {"@@ASTORY_SERVER_WAN_IP@@", "@@ASTORY_SERVER_LAN_IP@@", "@@ASTORY_SERVER_VPN_IP@@"}


def _linkable_ip(ip):
    """Годится ли IP для поиска связанных учёток."""
    import ipaddress
    ip = (ip or "").strip()
    if not ip or ip in NOT_LINKABLE_IPS:
        return False
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


# 19.11 (research_accounts_rest.md §2, В8): MAC виртуальных адаптеров склеивал разные учётки (живой dev: Hyper-V 00-15-5D — 3 учётки).
# Не связываем по OUI известных ВМ и по локально назначенным адресам (бит 0x02 первого байта: ВМ, VPN, случайный MAC Windows/Android).
VIRTUAL_OUIS = {"00155d",                           # Microsoft Hyper-V / WSL / Docker Desktop
                "005056", "000c29", "000569", "001c14",   # VMware
                "080027", "0a0027",                 # VirtualBox (адаптер гостя / host-only)
                "001c42",                           # Parallels
                "00163e",                           # Xen
                "525400",                           # QEMU / KVM
                "02004c"}                           # Microsoft Loopback / виртуальные TAP
LINK_CROWD = 5            # на IP больше стольких учёток — «общая сеть» (NAT, общежитие, мобильный оператор), не «одна машина»


def _linkable_mac(mac):
    """Годится ли MAC: 6 байт, не нули и не широковещательный, не виртуальный адаптер и не локально назначенный."""
    h = re.sub(r"[-:]", "", (mac or "").strip()).lower()
    if len(h) != 12 or not all(c in "0123456789abcdef" for c in h) or h in ("000000000000", "ffffffffffff"):
        return False
    if h[:6] in VIRTUAL_OUIS:
        return False
    return not (int(h[:2], 16) & 0x02)                # локально назначенный (второй младший бит первого байта)


def _end(r, now):
    """Конец сессии: Logout; пуст и сессия открыта (учётка сейчас в игре, mark_open) — текущее время (ревизия 28 М-2: иначе вход
    второй учётки за NAT во время игры выглядел «не пересекались» = «одна машина»); пуст у прочих (сбой) — точка входа."""
    if r.get("Logout"):
        return r["Logout"]
    return (now or datetime.datetime.now()) if r.get("_open") else r["Login"]


def mark_open(rows, online):
    """Пометить последнюю строку LogInfo без Logout у учётки, которая сейчас в игре (_open) — её сессия ещё идёт."""
    if online:
        last = max((r for r in rows if r.get("Login")), key=lambda r: r["Login"], default=None)
        if last is not None and not last.get("Logout"):
            last["_open"] = True
    return rows


def _overlap(a, b, now):
    """Пересекаются ли сессии [Login, конец] (конец — _end)."""
    a0, a1 = a["Login"], _end(a, now)
    b0, b1 = b["Login"], _end(b, now)
    if not (a0 and b0):
        return False
    return a0 <= b1 and b0 <= a1


def _online_ids(ids):
    """Учётки из ids, которые сейчас в игре по БД (Us_member.Flag/UserNum или CharPos.UserNum ≠ −1)."""
    ids = sorted({int(x) for x in ids})[:2000]
    if not ids:
        return set()
    marks = ",".join("?" * len(ids))
    with db.GameReader("asdastoryop") as op, db.GameReader("joy1") as j:
        a = {r["Userindex"] for r in op.rows("SELECT Userindex FROM Us_member WHERE Userindex IN (%s) AND (Flag <> 0 OR UserNum <> -1)"
                                              % marks, ids)}
        b = {r["Userindex"] for r in j.rows("SELECT DISTINCT Userindex FROM CharPos WHERE Userindex IN (%s) AND UserNum <> -1" % marks, ids)}
    return a | b


def link_degree(mine, theirs, crowd, now=None):
    """Связь учётки с другой по входам (глубина 1). mine/theirs — строки LogInfo (IpAddress, Mac, Login, Logout); crowd —
    {IP: учёток на нём}. → (ключ, by_ip, by_mac): mac_ip «MAC+IP», mac «MAC», ip_apart «IP (не пересекались)»,
    ip_net «IP (общая сеть)» — одновременные сессии на одном IP = разные машины за NAT; или IP, где учёток > LINK_CROWD."""
    ips = {(r["IpAddress"] or "").strip() for r in mine if _linkable_ip(r["IpAddress"])}
    macs = {(r["Mac"] or "").strip().upper() for r in mine if _linkable_mac(r["Mac"])}
    t_ip = [r for r in theirs if (r["IpAddress"] or "").strip() in ips]
    by_mac = any((r["Mac"] or "").strip().upper() in macs for r in theirs)
    shared = {(r["IpAddress"] or "").strip() for r in t_ip}
    by_ip = bool(shared)
    if by_mac:
        return ("mac_ip" if by_ip else "mac"), by_ip, by_mac
    if not by_ip:
        return None, False, False
    apart = False
    for ip in shared:
        if crowd.get(ip, 0) > LINK_CROWD:
            continue
        m_s = [r for r in mine if (r["IpAddress"] or "").strip() == ip]
        t_s = [r for r in t_ip if (r["IpAddress"] or "").strip() == ip]
        if not any(_overlap(a, b, now) for a in m_s for b in t_s):
            apart = True
    return ("ip_apart" if apart else "ip_net"), True, False


LINK_TITLES = {"mac_ip": "MAC+IP", "mac": "MAC", "ip_apart": "IP (не пересекались)", "ip_net": "IP (общая сеть)"}
LINK_ORDER = {"mac_ip": 0, "mac": 1, "ip_apart": 2, "ip_net": 3}


BLK_COLS = ("(SELECT COUNT(*) FROM BlockList b WHERE b.Userindex = m.Userindex) AS blk_rows, "
            "(SELECT COUNT(*) FROM BlockList b WHERE b.Userindex = m.Userindex AND b.CloseDate >= GETDATE()) AS blk_act, "
            "(SELECT MAX(b.CloseDate) FROM BlockList b WHERE b.Userindex = m.Userindex) AS blk_until")


def _job_targets(c):
    """Допустимые цели смены профессии (domains/jobchange.targets) с подписями для интерфейса."""
    try:
        from domains import jobchange
        return [dict(t, label=jobchange._jname(t["job"], t.get("subjob", 0))) for t in jobchange.targets(c)]
    except Exception:
        return []


def _max_level():
    """Потолок уровня сервера для интерфейса (P29); не прочитан — None (кнопка покажется, сервер-сторона всё равно проверит)."""
    try:
        from domains import srvtables
        return srvtables.max_level()
    except Exception:
        return None


def block_state(us_block, rows, active, until):
    """Блок как его видит СЕРВЕР при входе (владелец 17.11: «помечен как забаненный, а бан был на час»):
    us_block = 5 и все строки BlockList истекли — вход пройдёт, истёкший блок снимет UP_AC_LiftExpiredBlock (P50/P51,
    ac0t) → «истёк»; us_block ≠ 0 и есть действующая строка или строк нет вовсе → «действует»; иначе — нет блока."""
    if not us_block:
        return {"state": "expired" if rows else "none", "until": until}
    if us_block == 5 and rows and not active:
        return {"state": "expired", "until": until}
    return {"state": "active", "until": until if rows else None}


class NotFound(Exception):
    """Цель поиска не найдена."""


def _like(s):
    """Шаблон LIKE с экранированием спецсимволов."""
    return "%" + re.sub(r"([%_\[])", r"[\1]", s) + "%"


def _item_view(r):
    """Строка Item → вид для панели (+ название и иконка, опции, камни)."""
    info = refdata.item(r["Code"])
    opts = []
    for i, (k, v) in enumerate((("Opidx1", "OpValue1"), ("Opidx2", "OpValue2"), ("Opidx3", "Opvalue3"),
                                ("Opidx4", "Opvalue4"), ("OPidx5", "Opvalue5")), 1):
        if r.get(k) not in (None, -1, 0) or r.get(v) not in (None, -1, 0):
            opts.append({"slot": i, "id": r.get(k), "value": r.get(v)})
    sockets = []
    for k in ("Cell1", "Cell2", "Cell3", "Cell4"):
        c = r.get(k)
        if c not in (None, -1, 0):
            s = refdata.item(c)
            sockets.append({"code": c, "ru": s["ru"], "name": s["name"], "icon": s["icon"]})
    out = {k: r.get(k) for k in ("Uuid", "Code", "Plate", "Posx", "Amount", "Durability", "Weight", "Upcount",
                                 "AcuUpcnt", "MaxupCnt", "Updamage", "Refine", "Owner", "GainDate", "Fdate", "Rdate",
                                 "Charidx")}
    out.update(name=info["ru"], name_en=info["en"], name_loc=info["name"], table=info["table"], icon=info["icon"], options=opts, sockets=sockets)
    return out


def search(q, net=False):
    """Поиск учёток: число → Userindex; IP / MAC (право net) → по входам; иначе логин и имя персонажа (с удалёнными).

    → [dict(Userindex, Us_id, us_block, us_rdate, chars[], match)]."""
    q = (q or "").strip()
    if not q:
        return []
    found = {}   # Userindex → причина совпадения

    def add(uid, why):
        found.setdefault(int(uid), why)

    with db.GameReader("asdastoryop") as op, db.GameReader("joy1") as j:
        if q.isdigit() and len(q) <= 10:
            for r in op.rows("SELECT Userindex FROM Us_member WHERE Userindex = ?", (int(q),)):
                add(r["Userindex"], "номер учётки")
        # 19.11: Discord ID (15–20 цифр) и @handle — по копии привязок бота (domains/discordlinks.py, без паролей)
        from domains import discordlinks
        dl = discordlinks.find(q)
        if dl:
            logins = sorted({l for l, _ in dl})[:SEARCH_LIMIT]
            why = {l.lower(): w for l, w in dl}
            for r in op.rows("SELECT Userindex, Us_id FROM Us_member WHERE Us_id IN (%s)" % ",".join("?" * len(logins)), logins):
                add(r["Userindex"], why.get((r["Us_id"] or "").lower(), "Discord"))
        if net and (IP_RE.match(q) or MAC_RE.match(q)):
            with db.GameReader("joylog1") as lg:
                col = "IpAddress" if IP_RE.match(q) else "Mac"
                for r in lg.rows("SELECT DISTINCT TOP (%d) Userindex FROM LogInfo WHERE %s LIKE ?" % (SEARCH_LIMIT, col),
                                 (q.rstrip(".") + "%" if col == "IpAddress" else _like(q.replace(":", "-")),)):
                    add(r["Userindex"], "IP" if col == "IpAddress" else "MAC")
        for r in op.rows("SELECT TOP (%d) Userindex FROM Us_member WHERE Us_id LIKE ? ORDER BY Userindex" % SEARCH_LIMIT,
                         (_like(op.text(q)),)):
            add(r["Userindex"], "логин")
        for r in j.rows("SELECT TOP (%d) Userindex, Charname FROM Charinfo WHERE Charname LIKE ? ORDER BY Userindex"
                        % SEARCH_LIMIT, (_like(j.text(q)),)):
            add(r["Userindex"], "персонаж " + r["Charname"])
        for r in j.rows("SELECT TOP (%d) Userindex, Charname FROM Del_Charinfo WHERE Charname LIKE ? ORDER BY Edate DESC"
                        % SEARCH_LIMIT, (_like(j.text(q)),)):
            add(r["Userindex"], "удалённый персонаж " + r["Charname"])
        if not found:
            return []
        ids = sorted(found)[:SEARCH_LIMIT]
        marks = ",".join("?" * len(ids))
        acc = {r["Userindex"]: r for r in op.rows(
            "SELECT m.Userindex, m.Us_id, m.us_block, m.us_rdate, m.Flag, %s FROM Us_member m WHERE m.Userindex IN (%s)"
            % (BLK_COLS, marks), ids)}
        chars = {}
        for r in j.rows("SELECT Userindex, Charidx, Charname, Lvl, Job FROM Charinfo WHERE Userindex IN (%s) "
                        "ORDER BY Charidx" % marks, ids):
            chars.setdefault(r["Userindex"], []).append({"Charidx": r["Charidx"], "Charname": r["Charname"],
                                                          "Lvl": r["Lvl"], "job": refdata.job(r["Job"])})
    out = []
    for uid in ids:
        a = acc.get(uid) or {"Userindex": uid, "Us_id": None, "us_block": None, "us_rdate": None, "Flag": None}
        a = dict(a)
        a.update(chars=chars.get(uid, []), match=found[uid], service=uid <= OPERATOR_MAX_UID,
                 block=block_state(a.get("us_block"), a.pop("blk_rows", 0), a.pop("blk_act", 0), a.pop("blk_until", None)))
        out.append(a)
    return out


LIST_PAGE = 20               # строк на страницу списка (слово владельца 16.11: «пагинация по 20»)
LIST_SORTS = {"uid": "m.Userindex", "login": "m.Us_id", "created": "m.us_rdate DESC, m.Userindex"}


def list_accounts(page=1, size=LIST_PAGE, sort="uid", online_only=False):
    """Все учётки страницами (владелец 16.11: «при открытии раздела уже должен быть список игроков»).

    → {items[{Userindex, Us_id, us_block, us_rdate, chars[], online, service}], total, page, pages, size}."""
    size = max(1, min(int(size), 200))
    order = LIST_SORTS.get(sort, LIST_SORTS["uid"])
    with db.GameReader("asdastoryop") as op, db.GameReader("joy1") as j:
        online_ids = None
        if online_only:
            online_ids = sorted({r["Userindex"] for r in j.rows("SELECT DISTINCT Userindex FROM CharPos WHERE Usernum <> -1")})
            total = len(online_ids)
        else:
            total = op.one("SELECT COUNT(*) AS n FROM Us_member")["n"]
        pages = max(1, (total + size - 1) // size)
        page = max(1, min(int(page), pages))
        if online_only:
            ids = online_ids[(page - 1) * size: page * size]
            rows = op.rows("SELECT m.Userindex, m.Us_id, m.us_block, m.us_rdate, m.Flag, %s FROM Us_member m WHERE m.Userindex IN (%s)"
                           % (BLK_COLS, ",".join("?" * len(ids))), ids) if ids else []
            rows.sort(key=lambda r: ids.index(r["Userindex"]))
        else:
            rows = op.rows("SELECT m.Userindex, m.Us_id, m.us_block, m.us_rdate, m.Flag, %s FROM Us_member m ORDER BY %s "
                           "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" % (BLK_COLS, order), ((page - 1) * size, size))
        ids = [r["Userindex"] for r in rows]
        chars, online = {}, set()
        if ids:
            marks = ",".join("?" * len(ids))
            for r in j.rows("SELECT c.Userindex, c.Charidx, c.Charname, c.Lvl, c.Job, p.Usernum FROM Charinfo c "
                            "LEFT JOIN CharPos p ON p.Userindex = c.Userindex AND p.Charidx = c.Charidx "
                            "WHERE c.Userindex IN (%s) ORDER BY c.Charidx" % marks, ids):
                chars.setdefault(r["Userindex"], []).append({"Charidx": r["Charidx"], "Charname": r["Charname"],
                                                              "Lvl": r["Lvl"], "job": refdata.job(r["Job"])})
                if r["Usernum"] not in (None, -1):
                    online.add(r["Userindex"])
    items = []
    for r in rows:
        a = dict(r)
        a.update(chars=chars.get(r["Userindex"], []), online=r["Userindex"] in online,
                 service=r["Userindex"] <= OPERATOR_MAX_UID,
                 block=block_state(a.get("us_block"), a.pop("blk_rows", 0), a.pop("blk_act", 0), a.pop("blk_until", None)))
        items.append(a)
    return {"items": items, "total": total, "page": page, "pages": pages, "size": size}


def account(uid, net=False):
    """Карточка учётки по Userindex."""
    uid = int(uid)
    with db.GameReader("asdastoryop") as op, db.GameReader("joy1") as j:
        m = op.one("SELECT Userindex, Us_id, us_block, us_rdate, igsNID, Realcash, BonusCash, Seridx, Gsidx, Threadidx, "
                   "Channel, Poridx, UserNum, Flag, us_pwset, us_pwfail, us_pwfail_at, "
                   "CASE WHEN us_pwhash IS NULL THEN 0 ELSE 1 END AS has_password FROM Us_member WHERE Userindex = ?", (uid,))
        if not m:
            raise NotFound("учётки %d нет" % uid)
        from domains import password as _pw
        _lk, _until = _pw.lock_state(m)
        m["pw_locked_until"] = _until if _lk else None           # замок UPUserLogin: ≥ 10 неудач, последняя моложе 15 мин
        blocks = op.rows("SELECT Cou, grade, BlackDate, CloseDate, Reason FROM BlockList WHERE Userindex = ?", (uid,))
        history = op.rows("SELECT Cou, grade, BlackDate, CloseDate, Reason FROM BlockHistory WHERE Userindex = ? "
                          "ORDER BY BlackDate DESC", (uid,))
        chars = j.rows("SELECT c.Userindex, c.Charidx, c.Charname, c.Gender, c.Lvl, c.Class, c.Job, c.Subjob, "
                       "p.Poridx, p.Posx, p.Posy, p.Usernum, p.Channel, p.LastDate, p.State AS pos_state, cm.Cname AS clan, cm.Grade AS clan_grade, "
                       "(SELECT TOP 1 i.Amount FROM Item i WHERE i.Userindex = c.Userindex AND i.Charidx = c.Charidx "
                       "AND i.Code = ? AND i.Plate = 2) AS gold "
                       "FROM Charinfo c LEFT JOIN CharPos p ON p.Userindex = c.Userindex AND p.Charidx = c.Charidx "
                       "LEFT JOIN ClanMember cm ON cm.Userindex = c.Userindex AND cm.Charidx = c.Charidx "
                       "WHERE c.Userindex = ? ORDER BY c.Charidx", (refdata.GOLD_CODE, uid))
        for c in chars:
            c["job"] = refdata.job(c["Job"])
            c["map"] = refdata.map_name(c["Poridx"]) if c.get("Poridx") is not None else ""
            c["online"] = c.get("Usernum") not in (None, -1)
            c["stuck_state"] = c.get("pos_state") == 1        # «в сети» по State 1 без номера (UPSMConnect) — перепроверка 9 М4
        # 18.11: ключ набора корзины — Edate строкой (CONVERT 121: datetime-параметр сравнивался бы с округлением); восстановленные —
        # adm.CharRestored (domains/charrestore.py; таблицы может не быть до выкладки adminc_05)
        try:
            deleted = j.rows("SELECT CONVERT(varchar(23), d.Edate, 121) AS ekey, d.Edate, d.Charidx, d.Charname, d.Lvl, d.Job, "
                             "r.NewCharidx AS restored_to, r.RestoredAt AS restored_at FROM Del_Charinfo d LEFT JOIN adm.CharRestored r "
                             "ON r.Userindex = d.Userindex AND r.Charidx = d.Charidx AND r.Edate = d.Edate WHERE d.Userindex = ? "
                             "ORDER BY d.Edate DESC", (uid,))
        except db.DbError:
            deleted = j.rows("SELECT CONVERT(varchar(23), Edate, 121) AS ekey, Edate, Charidx, Charname, Lvl, Job FROM Del_Charinfo "
                             "WHERE Userindex = ? ORDER BY Edate DESC", (uid,))
        for d in deleted:
            d["job"] = refdata.job(d["Job"])
        gm = j.rows("SELECT Charidx, GMFlag, GMDate FROM CharGmInfo WHERE UserIndex = ?", (uid,))
        warehouse = [_item_view(r) for r in j.rows(
            "SELECT %s FROM Item WHERE Userindex = ? AND Plate = 5 ORDER BY Posx" % ITEM_COLS, (uid,))]
        soul = j.rows("SELECT Smidx, Userindex, Ouserindex, info, State, SmLvl, SmExp, FriendShip, FinalDate, Regdate "
                      "FROM SoulMate WHERE Userindex = ? OR Ouserindex = ?", (uid, uid))
        # ★ 25.11.2026 (владелец: «показывать не только номера, но и имена обоих»): логин и персонажи обеих учёток пары
        sm_ids = sorted({int(x) for s in soul for x in (s["Userindex"], s["Ouserindex"]) if x is not None})
        sm_login, sm_chars = {}, {}
        if sm_ids:
            qs = ",".join("?" * len(sm_ids))
            for r in op.rows("SELECT Userindex, Us_id FROM Us_member WHERE Userindex IN (%s)" % qs, sm_ids):
                sm_login[int(r["Userindex"])] = r["Us_id"] or ""
            for r in j.rows("SELECT Userindex, Charname FROM Charinfo WHERE Userindex IN (%s) ORDER BY Userindex, Charidx" % qs, sm_ids):
                sm_chars.setdefault(int(r["Userindex"]), []).append(r["Charname"] or "")
        for s in soul:
            for k, nk in (("Userindex", "a"), ("Ouserindex", "b")):
                u = s.get(k)
                s[nk + "_login"] = sm_login.get(int(u), "") if u is not None else ""
                s[nk + "_chars"] = sm_chars.get(int(u), []) if u is not None else []
    gp7 = {"user": None, "balance": None, "purchases": []}
    if m.get("Us_id"):
        with db.GameReader("asdastorylogin") as g:
            u = g.one("SELECT id, username, role FROM dbo.[user] WHERE username = ?", (m["Us_id"],))
            if u:
                gp7["user"] = u
                gp7["balance"] = g.one("SELECT balance, present, updated_at FROM GP7Balance WHERE user_id = ?", (u["id"],))
                gp7["purchases"] = g.rows("SELECT TOP 30 id, item_code, amount, balance_before, balance_after, success, "
                                          "created_at FROM GP7PurchaseLog WHERE user_id = ? ORDER BY id DESC", (u["id"],))
                for p in gp7["purchases"]:
                    p["name"] = refdata.item(p["item_code"])["name"] if p.get("item_code") is not None else ""
    netinfo = None
    if net:
        with db.GameReader("joylog1") as lg:
            logins = lg.rows("SELECT TOP 50 idx, Charidx, IpAddress, Mac, Login, Logout, State FROM LogInfo "
                             "WHERE Userindex = ? ORDER BY idx DESC", (uid,))
            # 19.11 (research §2): связи «одна машина» — глубина 1; MAC виртуальных/локальных адаптеров не в счёт; общий IP с
            # одновременными сессиями или с > LINK_CROWD учётками — «общая сеть» (разные машины за NAT), а не «одна машина»
            mine = lg.rows("SELECT TOP 5000 IpAddress, Mac, Login, Logout FROM LogInfo WHERE Userindex = ? ORDER BY idx DESC", (uid,))
            ips = sorted({r["IpAddress"].strip() for r in mine if _linkable_ip(r["IpAddress"])})[:200]
            macs = sorted({r["Mac"].strip() for r in mine if _linkable_mac(r["Mac"])})[:200]
            linked = []
            if ips or macs:
                ip_in = ("IpAddress IN (%s)" % ",".join("?" * len(ips))) if ips else "1 = 0"
                mac_in = ("Mac IN (%s)" % ",".join("?" * len(macs))) if macs else "1 = 0"
                theirs = lg.rows("SELECT TOP 20000 Userindex, IpAddress, Mac, Login, Logout FROM LogInfo WHERE Userindex <> ? AND (%s OR %s) "
                                 "ORDER BY idx DESC" % (ip_in, mac_in), (uid,) + tuple(ips) + tuple(macs))   # ревизия 28 К-7
                crowd = {r["IpAddress"].strip(): int(r["n"]) for r in lg.rows(
                    "SELECT IpAddress, COUNT(DISTINCT Userindex) AS n FROM LogInfo WHERE %s GROUP BY IpAddress" % ip_in, tuple(ips))} if ips else {}
                per = {}
                for r in theirs:
                    per.setdefault(int(r["Userindex"]), []).append(r)
                on = _online_ids([uid] + list(per))           # ревизия 28 М-2: у кого сессия идёт сейчас
                mark_open(mine, uid in on)
                for u, rs in per.items():
                    mark_open(rs, u in on)
                    key, by_ip, by_mac = link_degree(mine, rs, crowd)
                    if key:
                        linked.append({"Userindex": u, "last": max((x["Login"] for x in rs if x["Login"]), default=None),
                                       "by_ip": int(by_ip), "by_mac": int(by_mac), "degree": key, "degree_title": LINK_TITLES[key]})
                linked.sort(key=lambda x: (LINK_ORDER[x["degree"]], -(x["last"].timestamp() if x["last"] else 0)))
                linked = linked[:50]
        if linked:
            with db.GameReader("asdastoryop") as op:
                ids = [r["Userindex"] for r in linked]
                names = {r["Userindex"]: r["Us_id"] for r in op.rows(
                    "SELECT Userindex, Us_id FROM Us_member WHERE Userindex IN (%s)" % ",".join("?" * len(ids)), ids)}
            for r in linked:
                r["Us_id"] = names.get(r["Userindex"])
        netinfo = {"logins": logins, "linked": linked, "eac": eac_summary(uid)}
    import datetime
    now = datetime.datetime.now()
    for b in blocks:                                  # строка, чей срок вышел, — «истекла» (вход её снимет)
        b["expired"] = bool(b["CloseDate"] and b["CloseDate"] < now)
    m["block"] = block_state(m["us_block"], len(blocks), sum(1 for b in blocks if not b["expired"]),
                             max((b["CloseDate"] for b in blocks), default=None))
    from domains import accountclose, discordlinks
    try:
        disc = discordlinks.card(uid, m.get("Us_id"), m["block"])
    except Exception as ex:                           # реестр/копия не прочитаны — карточка всё равно открывается
        disc = {"error": "привязки Discord не прочитаны: %s" % ex.__class__.__name__}
    # 19.11 (research §3): строка CharGmInfo у игровой учётки > 5000 GM-команд не даёт, но обходит EAC-кик, автоблок и правила имени
    gm_warn = bool(gm) and uid > OPERATOR_MAX_UID
    return {"account": m, "service": uid <= OPERATOR_MAX_UID, "blocks": blocks, "block_history": history,
            "chars": chars, "deleted": deleted, "gm": gm, "gm_warning": gm_warn, "warehouse": warehouse, "soulmate": soul, "gp7": gp7,
            "net": netinfo, "discord": disc, "closed": accountclose.closed_state(blocks, now)}


# ───────────── сводка античита учётки (19.11, research §4 (а); живая точка EacServer — отдельной волной) ─────────────
EAC_TABLES = (("other", "P73: события моста EAC", "event_kind LIKE 'P73%'"), ("kick_block", "автоблок по кикам (P48/P69)", None),
              ("login_check_refusal", "отказы сверки входа", None), ("operator_refusal", "отказы операторских действий", None),
              ("identity_mismatch", "несовпадение учётки сессии", None), ("packet_validator", "проверка пакетов", None),
              ("move_combat", "скорость движения и боя", None), ("sign_replay", "подпись пакетов", None))


def eac_summary(uid):
    """По учётке: число событий и последнее — по каждой таблице ac.* журнала античита; KICK-события P73 разобраны отдельно;
    10 последних событий. Без IP (они в ленте под тем же правом). Ошибка таблицы — в errors, остальное считается."""
    out = {"tables": [], "recent": [], "errors": [], "kicks": {"received": 0, "done": 0, "operator": 0, "last": None}}
    with db.GameReader("joylog1") as lg:
        for t, title, extra in EAC_TABLES:
            cond = "user_index = ?" + (" AND " + extra if extra else "")
            try:
                r = lg.one("SELECT COUNT(*) AS n, MAX(ev_local) AS last FROM ac.%s WHERE %s" % (t, cond), (uid,))
                if r and r["n"]:
                    out["tables"].append({"table": "ac." + t, "title": title, "n": r["n"], "last": r["last"]})
                    kind = "event_kind" if t in ("other", "kick_block", "packet_validator", "move_combat", "sign_replay") else (
                        "check_result" if t == "login_check_refusal" else ("refusal_kind" if t == "operator_refusal" else "logon_kind"))
                    for e in lg.rows("SELECT TOP 10 event_id, ev_local, char_name, %s AS kind FROM ac.%s WHERE %s ORDER BY ev_local DESC"
                                     % (kind, t, cond), (uid,)):
                        out["recent"].append(dict(e, table="ac." + t))
            except db.DbError as ex:
                out["errors"].append("ac.%s: %s" % (t, ex))
        try:
            for r in lg.rows("SELECT event_kind, COUNT(*) AS n, MAX(ev_local) AS last FROM ac.other WHERE user_index = ? AND "
                             "event_kind LIKE 'P73: KICK%' GROUP BY event_kind", (uid,)):
                k = r["event_kind"] or ""
                slot = ("operator" if "не выполнен" in k else ("done" if "выполнен" in k else ("received" if "получен" in k else None)))
                if slot:
                    out["kicks"][slot] += int(r["n"])
                if r["last"] and (out["kicks"]["last"] is None or r["last"] > out["kicks"]["last"]):
                    out["kicks"]["last"] = r["last"]
        except db.DbError as ex:
            out["errors"].append("ac.other: %s" % ex)
    import datetime
    out["recent"].sort(key=lambda e: e["ev_local"] or datetime.datetime.min, reverse=True)
    out["recent"] = out["recent"][:10]
    return out


GP7_PAGE = 20


def gp7_page(uid, kind="purchases", page=1, size=GP7_PAGE):
    """Покупки (GP7PurchaseLog) или подарки (GP7GiftLog: отправленные учёткой и полученные её персонажами) страницами;
    итог трат — сумма успешных покупок. Только просмотр (решение владельца 19.11: правки баланса нет, testFixedBalance)."""
    uid, size = int(uid), max(1, min(int(size), 100))
    with db.GameReader("asdastoryop") as op:
        m = op.one("SELECT Us_id FROM Us_member WHERE Userindex = ?", (uid,))
    if not m:
        raise NotFound("учётки %d нет" % uid)
    with db.GameReader("joy1") as j:
        # ревизия 28 К-6: имена из Joy1 уже в виде игры (fix_text); recipient_name — Arabic_CI_AS → параметр обратно to_db_text
        names = [db.to_db_text(r["Charname"]) for r in j.rows("SELECT Charname FROM Charinfo WHERE Userindex = ?", (uid,)) if r["Charname"]]
    with db.GameReader("asdastorylogin") as g:
        u = g.one("SELECT id FROM dbo.[user] WHERE username = ?", (m["Us_id"],))
        if kind == "gifts":
            cond = "sender_userindex = ?" + (" OR sender_user_id = ?" if u else "") + (
                (" OR recipient_name IN (%s)" % ",".join("?" * len(names))) if names else "")
            args = [uid] + ([u["id"]] if u else []) + names
            total = g.one("SELECT COUNT(*) AS n FROM GP7GiftLog WHERE %s" % cond, args)["n"]
            pages = max(1, (total + size - 1) // size)
            page = max(1, min(int(page), pages))
            rows = g.rows("SELECT order_id, sender_userindex, sender_name, recipient_name, code1, code2, code3, code4, code5, code6, code7, "
                          "amount, state, test_mode, created_at, settled_at, settle_result FROM GP7GiftLog WHERE %s ORDER BY created_at DESC "
                          "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" % cond, args + [(page - 1) * size, size])
            for r in rows:
                r["sender_name"], r["recipient_name"] = db.fix_text(r["sender_name"]), db.fix_text(r["recipient_name"])
                r["sent"] = r["sender_userindex"] == uid
                r["items"] = [{"code": r["code%d" % i], "name": refdata.item(r["code%d" % i])["name"]}
                              for i in range(1, 8) if r.get("code%d" % i)]
            return {"kind": kind, "items": rows, "total": total, "page": page, "pages": pages, "size": size}
        if not u:
            return {"kind": kind, "items": [], "total": 0, "page": 1, "pages": 1, "size": size, "spent": 0}
        s = g.one("SELECT COUNT(*) AS n, SUM(CASE WHEN success = 1 THEN amount ELSE 0 END) AS spent FROM GP7PurchaseLog WHERE user_id = ?",
                  (u["id"],))
        total = s["n"]
        pages = max(1, (total + size - 1) // size)
        page = max(1, min(int(page), pages))
        rows = g.rows("SELECT id, item_code, amount, balance_before, balance_after, success, created_at FROM GP7PurchaseLog "
                      "WHERE user_id = ? ORDER BY id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY", (u["id"], (page - 1) * size, size))
        for p in rows:
            p["name"] = refdata.item(p["item_code"])["name"] if p.get("item_code") is not None else ""
        return {"kind": kind, "items": rows, "total": total, "page": page, "pages": pages, "size": size, "spent": s["spent"] or 0}


def discord_bans():
    """Реестр банов Discord (BANNED_PLAYERS.md) против блока входа: [{Userindex, login, Us_id, block, mismatch}] — расхождения первыми.
    None — копии реестра нет."""
    from domains import gifts
    reg = gifts.banned()
    if reg is None:
        return None
    ids = sorted(reg)
    acc = {}
    if ids:
        with db.GameReader("asdastoryop") as op:
            for r in op.rows("SELECT m.Userindex, m.Us_id, m.us_block, %s FROM Us_member m WHERE m.Userindex IN (%s)"
                             % (BLK_COLS, ",".join("?" * len(ids))), ids):
                acc[r["Userindex"]] = r
    out = []
    for uid in ids:
        r = acc.get(uid)
        b = block_state(r["us_block"], r["blk_rows"], r["blk_act"], r["blk_until"]) if r else None
        out.append({"Userindex": uid, "login": reg[uid], "Us_id": r["Us_id"] if r else None, "block": b,
                    "exists": bool(r), "mismatch": bool(r) and b["state"] != "active"})
    out.sort(key=lambda x: (not x["mismatch"], x["Userindex"]))
    return out


# 19.11 (решение владельца п.6): почтовый ящик и аукцион в карточке — что за строка ящика (вид, покупка, цена, выдано панелью), лот
# (номер → след, истёк ли, когда реле снимет), замок аукциона (Plate 11/12) и журнал лотов персонажа.
POSTBOX_TYPES = {0: "расходник магазина (Functional)", 1: "снаряжение магазина (Shell)"}   # UPCashitemBuy; 3 / 4 — смысл не подтверждён


def _postbox_more(j, uid, idx, postbox):
    """Строки ящика: вид, дата покупки и цена по Orderidx (ItemPostBoxCart / AsdaStoryOp.Sale* / CashUse), выдано ли панелью."""
    import json
    orders = sorted({int(p["Orderidx"]) for p in postbox})[:200]
    cart, sale, cash, panel = {}, {}, {}, set()
    if orders:
        ph = ",".join("?" * len(orders))
        for r in j.rows("SELECT Orderidx, Code, MIN(Created) AS Created, MIN(Price) AS Price FROM ItemPostBoxCart WHERE Orderidx IN (%s) "
                        "GROUP BY Orderidx, Code" % ph, orders):
            cart[(int(r["Orderidx"]), int(r["Code"]))] = r
        try:
            with db.GameReader("asdastoryop") as op:
                for t in ("SaleFunctional", "SalePremium"):
                    for r in op.rows("SELECT Orderidx, Code, MIN(Edate) AS Edate, MIN(Report) AS Report FROM %s WHERE Userindex = ? "
                                     "AND Orderidx IN (%s) GROUP BY Orderidx, Code" % (t, ph), [uid] + orders):
                        sale[(int(r["Orderidx"]), int(r["Code"]))] = dict(r, src=t)
                for r in op.rows("SELECT Orderidx, SUM(Realcash) AS Realcash FROM CashUse WHERE Orderidx IN (%s) GROUP BY Orderidx" % ph,
                                 orders):
                    cash[int(r["Orderidx"])] = r["Realcash"]
        except db.DbError:
            pass
        try:
            from core import audit
            for a in audit.query("items.post", limit=1000):
                if a.get("result") != "ok" or a.get("undone_by"):
                    continue
                for t in (json.loads(a.get("after_json") or "{}").get("sent") or []):
                    if int(t.get("uid", -1)) == uid and int(t.get("idx", -1)) == idx:
                        panel.update(int(r[1]) for r in t.get("rows") or [])
        except Exception:
            pass
    for p in postbox:
        o, c = int(p["Orderidx"]), int(p["Code"])
        p["type"] = POSTBOX_TYPES.get(int(p["iType"]), "вид %s — смысл не подтверждён" % p["iType"])
        cr, sl = cart.get((o, c)), sale.get((o, c))
        p["bought"] = (sl or {}).get("Edate") or (cr or {}).get("Created")
        p["price"] = (cr or {}).get("Price") if cr else cash.get(o)
        p["shop"] = (sl or {}).get("Report") or ("корзина GP7" if cr else None)
        p["panel"] = o in panel


def _lots_more(lots):
    """Лот: истёк ли (Fdate прошла) и когда реле снимет его по ItemDeleteTime (с ac0z — вернёт владельцу)."""
    import datetime
    from domains import feed
    now = datetime.datetime.now()
    for p in lots:
        p["expired"] = bool(p.get("Fdate") and p["Fdate"] < now)
        p["relay_due"] = p["Gaindate"] + datetime.timedelta(days=feed.LOT_DELETE_DAYS) if p.get("Gaindate") else None
        p["relay_due_late"] = p["Fdate"] + datetime.timedelta(days=feed.LOT_DELETE_DAYS) if p.get("Fdate") else None
        p["relay_overdue"] = feed.lot_overdue(p, now)          # ★ ревизия 27 М-4


def _lot_log(uid, idx, limit=40):
    """Журнал лотов персонажа: выставления (ExchangeRegi*) и события лота (ExchangeEvent: отмена, таймаут, возврат, покупка)."""
    out = []
    try:
        with db.GameReader("joylog1") as lg:
            for t in ("ExchangeRegi", "ExchangeRegiFunctional", "ExchangeRegiGear", "ExchangeRegiNoStack", "ExchangeRegiSowel"):
                for r in lg.rows("SELECT TOP %d Edate, Code, Serial FROM [dbo].[%s] WHERE Userindex = ? AND Charidx = ? ORDER BY Edate DESC"
                                 % (limit, t), (uid, idx)):
                    out.append(dict(r, table=t, State="выставлен"))
            for r in lg.rows("SELECT TOP %d Edate, Code, Serial, Amount, Ramount, Gm, State FROM ExchangeEvent WHERE Userindex = ? "
                             "AND Charidx = ? ORDER BY Edate DESC" % limit, (uid, idx)):
                out.append(dict(r, table="ExchangeEvent"))
    except db.DbError:
        return []
    for r in out:
        r["name"] = refdata.item(r["Code"])["name"]
    out.sort(key=lambda x: x["Edate"], reverse=True)
    return out[:limit]


def character(uid, idx):
    """Карточка персонажа (Userindex, Charidx)."""
    uid, idx = int(uid), int(idx)
    with db.GameReader("joy1") as j:
        c = j.one("SELECT %s FROM Charinfo WHERE Userindex = ? AND Charidx = ?" % CHAR_COLS, (uid, idx))
        if not c:
            raise NotFound("персонажа %d/%d нет" % (uid, idx))
        c["job"] = refdata.job(c["Job"])
        c["subjob"] = refdata.job(c["Subjob"]) if c.get("Subjob") else ""
        pos = j.one("SELECT Poridx, Posx, Posy, Usernum, Gsidx, Threadidx, Channel, Cporidx, Partyidx, State, SoulState, "
                    "LastDate FROM CharPos WHERE Userindex = ? AND Charidx = ?", (uid, idx))
        if pos:
            pos["map"] = refdata.map_name(pos["Poridx"])
            pos["online"] = pos.get("Usernum") not in (None, -1)
        clan = j.one("SELECT m.Clanidx, m.Cname, m.Grade, m.Callname, m.DonationPoint, d.Captain, d.Lvl, d.JoinCnt, "
                     "d.Maxcnt FROM ClanMember m LEFT JOIN ClanData d ON d.Clanidx = m.Clanidx "
                     "WHERE m.Userindex = ? AND m.Charidx = ?", (uid, idx))
        items = [_item_view(r) for r in j.rows(
            "SELECT %s FROM Item WHERE Userindex = ? AND Charidx = ? ORDER BY Plate, Posx"
            % ITEM_COLS, (uid, idx))]
        gold = next((i["Amount"] for i in items if i["Code"] == refdata.GOLD_CODE and i["Plate"] == 2), None)
        gold_posx = next((i["Posx"] for i in items if i["Code"] == refdata.GOLD_CODE and i["Plate"] == 2), None)
        bags = {}
        for it in items:
            if it["Code"] == refdata.GOLD_CODE and it["Plate"] == 2:
                continue
            bags.setdefault(int(it["Plate"]), []).append(it)
        postbox = j.rows("SELECT iType, Orderidx, Code, Amount FROM ItemPostBox WHERE Userindex = ? AND Charidx = ? "
                         "ORDER BY Orderidx", (uid, idx))
        for p in postbox:
            inf = refdata.item(p["Code"])
            p.update(name=inf["name"], icon=inf["icon"])
        lots = j.rows("SELECT CONVERT(varchar(36), Eid) AS Eid, idx, Gidx, State, Code, Plate, Amount, Upcount, Sprice, Stime, Gaindate, "
                      "Fdate FROM Exitem WHERE Userindex = ? AND Charidx = ? ORDER BY Fdate", (uid, idx))
        for p in lots:
            inf = refdata.item(p["Code"])
            p.update(name=inf["name"], icon=inf["icon"])
        _postbox_more(j, uid, idx, postbox)
        _lots_more(lots)
        skills = j.rows("SELECT Skillidx, Lvl FROM CharSkill WHERE Userindex = ? AND Charidx = ? ORDER BY Skillidx",
                        (uid, idx))
        for s in skills:
            s["name"] = refdata.skill(s["Skillidx"])
        pets = j.rows("SELECT PetUnique, Plate, Petindex, PetName, FullNess, PetLvl, PetMaxLvl, PetExp, Active, Edate "
                      "FROM CharPetList WHERE Userindex = ? AND Charidx = ? ORDER BY PetUnique", (uid, idx))
        for p in pets:
            p["kind"] = refdata.pet(p["Petindex"])
        friends = j.rows("SELECT Fuserindex, Fcharidx, Charname FROM CharFriend WHERE Userindex = ? AND Charidx = ?",
                         (uid, idx))
        intro = j.one("SELECT Intro FROM CharIntroduce WHERE Userindex = ? AND Charidx = ?", (uid, idx))
        counts = j.one("SELECT (SELECT COUNT(*) FROM CharFame WHERE Userindex = ? AND Charidx = ?) AS fame, "
                       "(SELECT COUNT(*) FROM CharEpisode WHERE Userindex = ? AND Charidx = ?) AS episodes, "
                       "(SELECT COUNT(*) FROM CharQuest WHERE Userindex = ? AND Charidx = ?) AS quests",
                       (uid, idx, uid, idx, uid, idx))
        gm = j.one("SELECT GMFlag, GMDate FROM CharGmInfo WHERE UserIndex = ? AND Charidx = ?", (uid, idx))
        # окно инвентаря: ёмкости сумок (как у сервера) и можно ли сейчас править (учётка не в игре)
        from domains import items as _items
        ad = _items._ReaderAdapter(j)
        mig = j.one("SELECT CASE WHEN OBJECT_ID('dbo.AsdaMigrationLog', 'U') IS NULL THEN 0 ELSE 1 END AS t")["t"]
        bag60 = bool(mig) and bool(j.one("SELECT COUNT(*) AS n FROM dbo.AsdaMigrationLog WHERE MigKey = ?",
                                         (_items.BAG60_MIGKEY,))["n"]) and _items.p96_enabled()   # как у сервера (ревизия А1 R10)
        caps = {1: 60 if bag60 else 30, 2: 60, 3: _items.EQUIP_SLOTS, 5: min(int(c.get("WareCount") or 0), _items.WARE_MAX)}
        editable, why = _items.online_state(ad, uid)
    with db.GameReader("asdastoryop") as op:
        acc = op.one("SELECT m.Us_id, m.us_block, %s FROM Us_member m WHERE m.Userindex = ?" % BLK_COLS, (uid,))
    return {"char": c, "login": acc["Us_id"] if acc else None, "blocked": acc["us_block"] if acc else None,
            "block": block_state(acc["us_block"], acc["blk_rows"], acc["blk_act"], acc["blk_until"]) if acc else None,
            "max_level": _max_level(),
            "job_targets": _job_targets(c),
            "service": uid <= OPERATOR_MAX_UID, "pos": pos, "clan": clan, "gold": gold,
            "bags": [{"plate": k, "title": refdata.PLATES.get(k, "Сумка %d" % k), "items": v} for k, v in sorted(bags.items())],
            "postbox": postbox, "lots": lots, "locks": [it for k in (11, 12) for it in bags.get(k, [])], "lot_log": _lot_log(uid, idx),
            "skills": skills, "pets": pets, "friends": friends,
            "intro": intro["Intro"] if intro else "", "counts": counts, "gm": gm,
            "caps": caps, "gold_posx": gold_posx, "editable": editable, "edit_block": why, "slot_names": _items.SLOT_NAMES}
