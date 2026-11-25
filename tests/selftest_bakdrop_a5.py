# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_bakdrop_a5.py — самотест шага А5.8 «Уборка служебных копий *_bak_*» (21.11.2026; domains/bakdrop.py, sql/adminc_17_bakdrop.sql,
/api/bakdrop, карточка «Служебные копии», консоль db bak / db bakdrop).

offline(check)  — каталог в SQL (вердикты, у «нужна откату» файл отката есть и называет копию, у «можно убрать» файл есть), имена «можно убрать»
                  не встречаются в исходниках DLL (AsdaPatch / LoginPatch / DBPatch / SrvDbPatch / AddonNPC) и в коде панели, разбор имён и
                  ссылок, выбор свежего бэкапа, права (только владелец), операция не ставится заданием, ключи консоли, переводы EN, отказы без
                  «; », SQL (подпись, CONTROL только на «можно убрать», даты ГГГГММДД, QUOTED_IDENTIFIER, без sysadmin / db_owner / TRUSTWORTHY),
                  выкладка / проверка прав / откат, веб без innerHTML.
sandbox(check)  — СВОЙ экземпляр LocalDB (AsdaA58Stand): AsdaAdmin, Joy1 и joylog1 (уровень совместимости 100, сортировки как на сервере),
                  логин asda_admin с запретами сервера; настоящие adminc_16 и adminc_17 (дважды, под SET LANGUAGE Russian); копии трёх вердиктов;
                  отказы (нет бэкапа, бэкап старый, изменён после бэкапа, нужна откату, неизвестно, ссылки в той же и в другой базе, без слова,
                  из браузера без второго фактора, не владелец, заданием), прямой DROP под asda_admin — отказ, транзакция откатывается целиком,
                  успешное удаление со снимком DDL / строк / файла бэкапа.
live(check)     — только чтение сервера: список копий подписанной процедурой, вердикты, «можно убрать» без ссылок, права asda_admin, сухой
                  предпросмотр (ничего не удаляется: число копий до и после одинаково).
Побочных эффектов при импорте нет.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = os.path.dirname(ROOT)
INSTANCE = "AsdaA58Stand"
DROP_LIVE = ["dbo.UPUserLogin_bak_20261012_ac0", "dbo.UPUserLogin_bak_20261012_ac0r", "dbo.UPUserLogin_bak_20261012_ac1",
             "dbo.UP_AC_IdentityCheck_bak_20261012_ac0r", "dbo.cashgift_bak_procs_20261101"]
CAT_RX = re.compile(r"\(N'(\w+)', N'(\w+)', N'(\w+)', '(\w)', '(\w+)', N'((?:[^']|'')*)',\s*(NULL|N'(?:[^']|'')*'),\s*(NULL|N'(?:[^']|'')*'),\s*"
                    r"N'((?:[^']|'')*)'\)", re.S)
BODY_FILES = (("UPUserLogin_bak_20261012_ac0", "ac0_99_rollback.sql"), ("UPUserLogin_bak_20261012_ac0r", "ac0r_99_rollback.sql"),
              ("UPUserLogin_bak_20261012_ac1", "ac1_99_rollback.sql"), ("UP_AC_IdentityCheck_bak_20261012_ac0r", "ac0r_99_rollback.sql"))
REF_DIR = os.path.join(PORT, "AstoryServer", "Docs", "SQL", "bak_copies")
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика


def _norm_body(text, name):
    body = re.sub(r"^\s*CREATE\s+PROC(?:EDURE)?\s+\[dbo\]\.\[%s\]" % re.escape(name), "", text, flags=re.I)
    return re.sub(r"\s+", " ", body).strip()


def body_in_rollback(name, rollback_file, text=None):
    """Тело копии (эталон из bak_copies или text) целиком входит в файл отката → (да/нет, длина нормализованного тела)."""
    if text is None:
        text = open(os.path.join(REF_DIR, name + ".def.sql"), encoding="utf-8").read()
    b = _norm_body(text, name)
    r = re.sub(r"\s+", " ", open(os.path.join(PORT, "AstoryServer", "Docs", "SQL", rollback_file), encoding="utf-8-sig").read())
    return bool(b) and b in r, len(b)


DEDUP = ["Item", "Exitem", "Del_item", "Del_Exitem", "ItemPostBox", "gifts", "CharEpisode", "Del_CharEpisode", "CharSkillitem", "ItemCoolTime",
         "CharFishBookInfo", "Del_CharFishBookInfo", "CharSlot", "Del_CharSlot", "SellitemAlarm"]


def _refused(fn):
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    except SystemExit as ex:
        return "SystemExit: %s" % ex
    return None


def _ctx(via="cli", role="owner", uid=None, login="cli:selftest@a58"):
    from core import ops
    return ops.Ctx(uid, login, role, "", via)


def catalog_from_sql():
    """Каталог из sql/adminc_17_bakdrop.sql → [dict(db, sch, name, kind, verdict, needed_by, ref_file)] (с 30 строками item_dedup)."""
    sql = open(os.path.join(ROOT, "sql", "adminc_17_bakdrop.sql"), encoding="utf-8").read()
    s = lambda v: None if v == "NULL" else v[2:-1].replace("''", "'")
    out = [{"db": m[0], "sch": m[1], "name": m[2], "kind": m[3], "verdict": m[4], "needed_by": s(m[6]), "ref_file": s(m[7])}
           for m in CAT_RX.findall(sql)]
    for t in DEDUP:
        for sfx, f in (("", r"Reports\item_dedup\stage2\sql\05_rollback.sql"), ("b", r"Reports\item_dedup\stage2\sql_f1\05_rollback.sql")):
            out.append({"db": "Joy1", "sch": "dbo", "name": "%s_bak_dedup_20261101%s" % (t, sfx), "kind": "U", "verdict": "rollback",
                        "needed_by": "item_dedup", "ref_file": f})
    return out


def _catalog_offline(check):
    cat = catalog_from_sql()
    by = {}
    for r in cat:
        by.setdefault(r["verdict"], []).append(r)
    check("копии: каталог разобран из SQL (можно убрать 5, нужна откату ≥ 40, неизвестно 2)",
          len(by.get("drop", [])) == 5 and len(by.get("rollback", [])) >= 40 and len(by.get("unknown", [])) == 2,
          {k: len(v) for k, v in by.items()})
    check("копии: «можно убрать» — ровно проверенные 21.11 (ac0 / ac0r / ac1 / IdentityCheck ac0r / cashgift)",
          sorted("%s.%s" % (r["sch"], r["name"]) for r in by["drop"]) == sorted(DROP_LIVE))
    keys = [("%s.%s.%s" % (r["db"], r["sch"], r["name"])).lower() for r in cat]
    check("копии: в каталоге нет повторов", len(keys) == len(set(keys)))
    bad = []
    for r in by["rollback"]:
        f = os.path.join(PORT, r["ref_file"] or "")
        if not r["ref_file"] or not os.path.isfile(f):
            bad.append((r["name"], "нет файла %s" % r["ref_file"]))
            continue
        if r["name"].lower() not in open(f, encoding="utf-8", errors="replace").read().lower():
            bad.append((r["name"], "файл не называет копию"))
    check("копии: у каждой «нужна откату» файл отката есть и называет копию (%d; в том числе в комментарии — это безопасная сторона: "
          "копия остаётся)" % len(by["rollback"]), not bad, bad)
    miss = [r["name"] for r in by["drop"] if not r["ref_file"] or not os.path.isfile(os.path.join(PORT, r["ref_file"]))]
    check("копии: у каждой «можно убрать» файл-доказательство на месте", not miss, miss)
    # ★ ревизия 48 (мелочь 2): эталонные тексты копий (сняты с живого OBJECT_DEFINITION 21.11 в Server/Docs/SQL/bak_copies) — тело без
    #   заголовка CREATE PROC, пробелы схлопнуты, С УЧЁТОМ регистра — целиком входит в файл отката; откат копию не читает
    for name, f in BODY_FILES:
        ok, n = body_in_rollback(name, f)
        t = open(os.path.join(PORT, "AstoryServer", "Docs", "SQL", f), encoding="utf-8-sig", errors="replace").read()
        check("копии: %s — тело эталона (%d знаков) целиком в %s, откат копию не читает" % (name, n, f),
              ok and name not in re.sub(r"--[^\n]*|/\*.*?\*/", "", t, flags=re.S))
    # имена «можно убрать» — нигде в исходниках DLL и в коде панели (кроме каталога, модуля уборки и самотестов)
    hits = []
    roots = [os.path.join(PORT, "AstoryServer", "Patches", d) for d in ("AsdaPatch", "LoginPatch", "DBPatch", "SrvDbPatch", "AddonNPC")]
    names = [n.split(".", 1)[1].lower() for n in DROP_LIVE]
    for base in roots + [ROOT]:
        for dp, dn, fn in os.walk(base):
            dn[:] = [d for d in dn if d not in ("__pycache__", ".git", "build", "Release", "Debug", "x64", "tests", "data")]
            for f in fn:
                if not f.lower().endswith((".cpp", ".h", ".c", ".hpp", ".ini", ".py", ".js", ".sql", ".bat", ".ps1")):
                    continue
                if f in ("adminc_17_bakdrop.sql", "bakdrop.py"):
                    continue
                try:
                    txt = open(os.path.join(dp, f), encoding="utf-8", errors="replace").read().lower()
                except OSError:
                    continue
                hits += [(os.path.relpath(os.path.join(dp, f), PORT), n) for n in names if n in txt]
    check("копии: имена «можно убрать» не встречаются в исходниках DLL (AsdaPatch, LoginPatch, DBPatch, SrvDbPatch, AddonNPC) и коде панели",
          not hits, hits[:10])


def _logic_offline(check, K):
    from core import auth, ops
    check("копии: имена — «имя» → dbo.имя, регистр-повторы убраны", K.names_arg({"names": "a_bak, dbo.A_BAK,x.y"}) == ["dbo.a_bak", "x.y"])
    for bad in ({"names": []}, {"names": "a;drop"}, {"names": "db.dbo.x"}, {"names": "[dbo].[x]"}, {}):
        check("копии: имена — %r — отказ" % bad.get("names"), _refused(lambda: K.names_arg(bad)) is not None)
    check("копии: имена — больше %d за раз — отказ" % K.MAX_NAMES, _refused(lambda: K.names_arg({"names": ["t%d" % i for i in range(K.MAX_NAMES + 1)]})))
    row = {"refs": "Joy1.dbo.UPUserLogin_bak_20261012_ac1 (text), joylog1.dbo.UseCash (expr), Joy1.dbo.T1 (fk)"}
    check("копии: ссылки разобраны (база, схема, имя, вид)", K.refs_of(row) == [("Joy1", "dbo", "UPUserLogin_bak_20261012_ac1", "text"),
                                                                                 ("joylog1", "dbo", "UseCash", "expr"), ("Joy1", "dbo", "T1", "fk")])
    o = K.outer_refs(row, "Joy1", ["dbo.UPUserLogin_bak_20261012_ac1", "dbo.T1"])
    check("копии: ссылки из выбранных копий той же базы не мешают, из другой базы и внешний ключ — мешают",
          [x[2] for x in o] == ["UseCash", "T1"], o)
    now = datetime.datetime(2026, 11, 21, 12, 0, 0)
    b = lambda i, h, v=True, bs=7: {"id": i, "verified": v, "backup_set_id": bs, "finished_at": now - datetime.timedelta(hours=h),
                                     "verified_at": now - datetime.timedelta(hours=h), "started_at": now - datetime.timedelta(hours=h, minutes=1)}
    rows = [b(9, 7), b(8, 1), b(7, 0.5, v=False)]
    check("копии: свежий бэкап — первый годный не старше срока", K.pick_backup(rows, 6, now)["id"] == 8)
    check("копии: свежий бэкап — заданный номер старше срока — нет", K.pick_backup(rows, 6, now, want=9) is None)
    check("копии: свежий бэкап — без набора в истории — нет", K.pick_backup([b(5, 1, bs=None)], 6, now) is None)
    check("копии: вердикт — не в каталоге = неизвестно, нужна откату — с причиной, ссылки — блок",
          K.classify({"verdict": "drop", "in_catalog": False})[0] == "unknown"
          and K.classify({"verdict": "rollback", "in_catalog": True, "needed_by": "L09"}) == ("rollback", "нужна откату: L09")
          and K.classify({"verdict": "drop", "in_catalog": True, "present": True, "refs_n": 1, "refs": "x"})[1].startswith("на неё ссылаются")
          and K.classify({"verdict": "drop", "in_catalog": True, "present": True, "refs_n": 0}) == ("drop", None))
    from domains import dbbackup as B
    old = [{"id": i, "db": "Joy1", "status": "done", "verified": True, "started_at": now - datetime.timedelta(days=90 - i),
            "finished_at": now - datetime.timedelta(days=90 - i), "file_path": "x"} for i in range(1, 9)]
    plain = sorted(r["id"] for r, _w in B.prune_plan(old, now))
    pinned = sorted(r["id"] for r, _w in B.prune_plan(old, now, pinned={2}))
    check("копии (рев. 48 Н-4): бэкап из журнала удаления копий автоуборка не удаляет (старый №2 — защищён), остальные — как прежде",
          2 in plain and 2 not in pinned and set(plain) - {2} == set(pinned), (plain, pinned))
    check("копии: право db.bakdrop — только владелец", {r for r in ("owner", "admin", "gm", "support") if auth.can(r, "db.bakdrop")} == {"owner"})
    op = ops.REGISTRY.get("db.bakdrop")
    check("копии: операция db.bakdrop зарегистрирована, не откатывается, заданием не ставится, второй фактор и слово bakdrop",
          op is not None and not op.reversible and not getattr(op, "schedule_runner", None) and op.two_factor and op.confirm_word == "bakdrop")
    from domains import stack
    check("копии: в списке операций заданий её нет", all(x["op"] != "db.bakdrop" for x in stack.schedulable(_ctx())))
    for role in ("admin", "gm"):
        w = _refused(lambda: ops.run(_ctx(role=role), "db.bakdrop", {"db": "Joy1", "names": "x"}, dry=True))
        check("копии: роль %s — отказ по праву до чтения базы" % role, w and "db.bakdrop" in w, w)


def _cli_offline(check):
    sys.path.insert(0, ROOT)
    import asda_admin as A
    ok = A.db_args(["bakdrop", "--db", "Joy1", "--obj", "dbo.a,dbo.b", "--backup", "4", "--confirm-bakdrop", "--dry"])
    check("копии: консоль — bakdrop --db --obj --backup --confirm-bakdrop --dry разобраны",
          ok == ("bakdrop", {"--db": "Joy1", "--obj": "dbo.a,dbo.b", "--backup": "4", "--confirm-bakdrop": True, "--dry": True}), ok)
    check("копии: консоль — bak --all разобран", A.db_args(["bak", "--all"]) == ("bak", {"--all": True}))
    for bad in (["bakdrop", "--force"], ["bakdrop", "--obj"], ["bak", "--db", "Joy1"], ["bakdrop", "--confirm"]):
        check("копии: консоль — %s — отказ без действий" % " ".join(bad), (_refused(lambda: A.db_args(bad)) or "").startswith("SystemExit"))
    w = _refused(lambda: A._db(["bakdrop", "--db", "Joy1"]))
    check("копии: консоль — bakdrop без --obj — отказ до операции", w and "--obj" in w, w)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "asda_admin.py"), "--help"], capture_output=True, timeout=60)
    out = r.stdout.decode("utf-8", "replace")
    check("копии: консоль --help — справка bak / bakdrop, без действий", r.returncode == 0 and "bakdrop --db Joy1 --obj" in out and "bak [--all]" in out)


SAMPLES = [
    "нужно подтверждение удаления служебных копий (слово bakdrop) — ничего не удалено",
    "база вне списка панели или это база самой панели — ничего не удалено",
    "список имён копий — JSON-массив строк «схема.имя» — ничего не удалено",
    "неизвестный объект (нет в каталоге служебных копий панели) — ничего не удалено: dbo.Foo_bak_1",
    "копия нужна откату, панель её не удаляет — ничего не удалено: dbo.Item_bak_charge_20261101",
    "происхождение копии не установлено, панель её не удаляет — ничего не удалено: dbo.UPUserLogin_BAk",
    "нет свежего проверенного бэкапа этой базы (не старше 6 ч, RESTORE VERIFYONLY пройден, набор в истории msdb) — ничего не удалено, сначала сделайте бэкап",
    "объекта нет в базе или он другого вида — ничего не удалено: dbo.x",
    "объект создан или изменён после начала бэкапа №5 (в бэкапе его нынешнего вида нет) — ничего не удалено, нужен новый бэкап: dbo.x",
    "на копию ссылаются другие объекты — ничего не удалено: dbo.a ← joylog1.dbo.UseCash (expr)",
    "список служебных копий не прочитан: ошибка SQL",
    "настройки уборки копий (adm.bakdrop_cfg) не прочитаны — ничего не удалено",
    "не выбраны копии для удаления (names — список «схема.имя»)",
    "имя копии a;b — только латиница, цифры и «_» (схема.имя) — ничего не удалено",
    "за один раз — не больше 60 копий",
    "база master — не игровая база списка панели (уборка копий в AsdaAdmin не делается) — ничего не удалено",
    "копии dbo.x нет в списке служебных копий базы Joy1 — ничего не удалено",
    "копия dbo.Item_bak_charge_20261101 нужна откату (откат укладки P100 (19_stack_rollback.sql)), панель её не удаляет — ничего не удалено",
    "происхождение копии dbo.Foo_bak не установлено (нет в каталоге или сток), панель её не удаляет — ничего не удалено",
    "копии dbo.x в базе Joy1 нет — ничего не удалено",
    "на копию dbo.a ссылаются другие объекты (joylog1.dbo.UseCash) — ничего не удалено",
    "номер бэкапа — число",
    "копия создана или изменена после начала бэкапа №5 (dbo.x) — нужен новый бэкап, ничего не удалено",
    "удалить служебные копии базы Joy1: 2 (dbo.a, dbo.b), бэкап №5 от 2026-11-21 05:00 UTC (1.5 ч назад)",
    "удаление одной транзакцией: ссылки на копии проверяются ещё раз прямо перед DROP, снимок DDL и строк — в журнале удаления",
    "удаляются только копии каталога «можно убрать» — у процедуры удаления прав на другие объекты нет",
    "нужно подтверждение удаления: слово bakdrop (в панели — ввести слово, в консоли — ключ --confirm-bakdrop)",
    "удаление служебных копий — только сейчас: из браузера (слово и второй фактор) или консолью ПК, не заданием",
    "удаление не выполнено (транзакция отменена): ошибка SQL",
    "процедура удаления вернула 1 строк журнала вместо 2",
    "удалено служебных копий базы Joy1: 2 (dbo.a, dbo.b), снимок — журнал удаления №3…4, бэкап №5",
    "после удаления копии ещё на месте: dbo.a",
    "нужна откату: откат L09 (l09_99_rollback.sql)",
    "происхождение не установлено (нет в каталоге или сток) — панель не удаляет",
    "на сервере нет",
    "на неё ссылаются: Joy1.dbo.x (text)",
    "бэкапы базы не прочитаны (DbError)",
    "журнал удалений не прочитан (DbError)",
    "Служебные копии: удалить (бэкап базы, второе подтверждение)",
    "ссылки на копии прочитаны не во всех базах (причины — в списке служебных копий) — ничего не удалено: joylog1",
    "строки копии изменены после бэкапа №5 или это не прочитать (число строк снимка бэкапа, последняя запись, перезапуск SQL Server) — ничего не удалено, нужен новый бэкап: dbo.x",
    "строки копии не совпадают со снимком бэкапа №5 или снимка нет (dbo.x) — нужен новый бэкап, ничего не удалено",
    "список служебных копий не прочитан: нет набора «базы, где ссылки не прочитаны»",
    "база стенда Joy1_stand_5 оставлена прошлым прогоном (--keep) — заменить её можно только с ключом --drop-kept, восстановление не начато",
    "оставленные --keep базы стенда не прочитаны (OperationalError)",
    "будут удалены оставленные --keep базы стенда: Joy1_stand_5",
    "оставленные --keep базы стенда не трогаются: Joy1_stand_5 (удалить — ключ --drop-kept)",
    "база не ONLINE (OFFLINE)",
    "нет пользователя подписи adm_bakdrop_u (база добавлена в список после установки adminc_17)",
    "модулей без текста (WITH ENCRYPTION): 1",
    "серверные триггеры без текста (WITH ENCRYPTION)",
]


def _i18n_offline(check, K):
    from core import i18n
    i18n.set_lang("en")
    try:
        cyr = re.compile("[А-Яа-яЁё]")
        smp = SAMPLES + [K.NO_UNDO % (5, 5, 5), K.NEED_BACKUP % ("Joy1", 6, "Joy1")]
        bad = [(s[:70], i18n.tr(s)[:90]) for s in smp if cyr.search(i18n.tr(s))]
        check("копии: переводы EN — без русских букв (%d образцов)" % len(smp), not bad, bad)
    finally:
        i18n.set_lang("ru")
    try:
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        import selftest_patchcfg_a5 as P
        sh, n = P.shadowed_translations()
        check("копии: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n, not sh, sh[:5])
    except ImportError as ex:
        check("копии: сверка перехватов переводов загружена", False, str(ex))


def _static_offline(check):
    sql = open(os.path.join(ROOT, "sql", "adminc_17_bakdrop.sql"), encoding="utf-8").read()
    body = re.sub(r"/\*.*?\*/|--[^\n]*", " ", sql, flags=re.S)
    check("копии SQL: QUOTED_IDENTIFIER ON отдельным пакетом до таблиц (урок А5.1)",
          re.match(r"\s*SET ANSI_NULLS ON;\s*SET QUOTED_IDENTIFIER ON;\s*GO", body) is not None)
    check("копии SQL: даты только ГГГГММДД (урок А5.7, ошибка 190 у русского входа)", not re.search(r"'{1,2}\d{4}-\d{2}-\d{2}", body))
    check("копии SQL: нет sysadmin, db_owner, db_ddladmin, TRUSTWORTHY, ALTER ANY, xp_cmdshell; смена контекста — только EXECUTE AS USER adm_bakdrop_x",
          not re.search(r"sysadmin|db_owner|db_ddladmin|TRUSTWORTHY|ALTER\s+ANY|xp_cmdshell", body, re.I)
          and re.findall(r"EXECUTE\s+AS\s+\S+\s*=\s*\S+", body, re.I) == ["EXECUTE AS USER = N''adm_bakdrop_x'';"],
          re.findall(r"EXECUTE\s+AS\s+\S+\s*=\s*\S+", body, re.I))
    check("копии SQL: подпись — две процедуры (BakScan, BakDrop), закрытый ключ стирается, логин из сертификата",
          body.count("ADD SIGNATURE TO adm.Bak") == 2 and "REMOVE PRIVATE KEY" in body and "CREATE LOGIN adm_bakdrop_signer FROM CERTIFICATE" in body)
    g = re.findall(r"GRANT CONTROL ON OBJECT::[^\n]*", body)
    check("копии SQL: CONTROL выдаётся только исполнителю adm_bakdrop_x и только объектам каталога с verdict = 'drop' (одно место выдачи)",
          len(g) == 1 and "TO adm_bakdrop_x" in g[0] and "k.verdict = 'drop'" in body[body.index("GRANT CONTROL ON OBJECT::"):body.index("GRANT CONTROL ON OBJECT::") + 400], g)
    check("копии SQL: удаление — одной транзакцией с XACT_ABORT, повторная проверка ссылок внутри неё, снимок до DROP",
          "SET XACT_ABORT ON" in body and body.index("BEGIN TRANSACTION") < body.index("EXEC adm.BakScan @db") < body.index("INSERT adm.bakdrop_log")
          < body.index("N'DROP TABLE '") < body.index("COMMIT TRANSACTION"))
    check("копии SQL: asda_admin — EXECUTE BakState / BakDrop и SELECT, прямой записи в каталог и журнал нет",
          "GRANT EXECUTE ON adm.BakDrop TO [asda_admin]" in body and "DENY INSERT, UPDATE, DELETE ON adm.bakdrop_log TO [asda_admin]" in body
          and "GRANT EXECUTE ON adm.BakScan" not in body and not re.search(r"GRANT\s+(INSERT|UPDATE|DELETE)[^;]*adm\.bakdrop", body))
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read().replace("\r\n", "\n")
    check("копии выкладка: adminc_17 сразу после adminc_16 в AsdaAdmin",
          "Run 'adminc_16_dbbackup.sql' 'AsdaAdmin'\nRun 'adminc_17_bakdrop.sql' 'AsdaAdmin'" in dep)
    ver = open(os.path.join(ROOT, "sql", "adminc_10_verify.sql"), encoding="utf-8").read()
    check("копии проверка прав: EXECUTE BakDrop есть, записи в журнал / каталог, ALTER ANY SCHEMA, CONTROL Joy1 и копии отката — нет",
          all(x in ver for x in ("'adm.BakDrop EXEC'", "'adm.bakdrop_log INSERT'", "'adm.bakdrop_obj UPDATE'", "'Joy1 ALTER ANY SCHEMA'",
                                 "'Joy1 CONTROL'", "'Joy1.AsdaProcBackup CONTROL'")))
    rb = P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    blk = rb[rb.index("уборка служебных копий А5.8"):] if rb is not None else None
    if blk is None:
        P.skip("копии откат (рев. 48 Н-3)", "нет sql/adminc_99_rollback.sql")
    else:
        check("копии откат (рев. 48 Н-3): пользователи adm_bakdrop_u / adm_bakdrop_x — курсором по ВСЕМ базам сервера (не перечнем), логин и сертификат",
          "DROP LOGIN adm_bakdrop_signer" in blk and "DROP CERTIFICATE adm_bakdrop_cert" in blk and "CURSOR LOCAL FAST_FORWARD FOR SELECT name FROM sys.databases" in blk
          and "DROP USER adm_bakdrop_x" in blk and not re.search(r"USE \[(Joy1|joylog1|AsdaStoryOp|AsdaStoryLogin)\];[^\n]*adm_bakdrop", blk))
    src = open(os.path.join(ROOT, "domains", "bakdrop.py"), encoding="utf-8").read()
    bad = re.findall(r'OpRefused\(\s*"([^"]*; [^"]*)"', src) + re.findall(r'THROW 508\d\d, N\'([^\']*; [^\']*)\'', sql)
    check("копии: отказы и THROW без «; »", not bad, bad)
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    i = app.index("function bakCard()")
    card = app[i:app.index("\n}\n", i)]
    check("копии веб: карточка без innerHTML, удаление — db.bakdrop со словом и кодом второго фактора, кнопки восстановления нет",
          "innerHTML" not in card and '"db.bakdrop"' in card and "totp" in card and "confirm" in card and "restore" not in card
          and 'can("db.view") ? bakCard() : null' in app)
    js = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    need = ["Служебные копии", "можно убрать", "нужна откату", "неизвестно", "Удалить выбранные ({0})", "Подтвердите удаление", "Журнал удалений"]
    check("копии веб: надписи карточки переведены (i18n.js)", all('"%s":' % x in js for x in need), [x for x in need if '"%s":' % x not in js])
    srv = open(os.path.join(ROOT, "api", "server.py"), encoding="utf-8").read()
    check("копии API: GET /api/bakdrop — право db.view", '@route("GET", r"/api/bakdrop", perm="db.view")' in srv)


def _hostshell_offline(check):
    """★ А5.9: длинный скрипт PowerShell по SSH — через stdin (предел командной строки cmd.exe 8191), короткий — как прежде."""
    from core import hostshell
    seen = []

    class R:
        returncode, stdout, stderr = 0, b"ok", b""
    keep = hostshell.subprocess.run
    hostshell.subprocess.run = lambda cmd, **kw: seen.append((cmd, kw.get("input"))) or R()
    try:
        hostshell.powershell("'x'", 10)
        hostshell.powershell("; ".join("'%04d'" % i for i in range(3000)), 10)
    finally:
        hostshell.subprocess.run = keep
    (c1, i1), (c2, i2) = seen
    check("хост (А5.9): короткий скрипт — -EncodedCommand без stdin; длинный — короткая команда (< 8000 знаков), base64 скрипта в stdin",
          i1 is None and "-EncodedCommand" in " ".join(c1) and i2 and len(" ".join(c2)) < 8000 and "-EncodedCommand" not in " ".join(c2)
          and len(i2) > 7000,
          (len(" ".join(c2)), i2 and len(i2)))
    # ★ А6.13 (22.11): по SSH [Console]::In.ReadToEnd() конца ввода не получает (висит до таймаута) — читатель stdin только конвейер $input
    tail = c2[-1]
    check("хост (А6.13): длинный скрипт читается конвейером $input, не [Console]::In / OpenStandardInput (по SSH они висят до таймаута)",
          "@($input) -join ''" in tail and "[Console]::In" not in tail and "OpenStandardInput" not in tail, tail[-160:])


def offline(check):
    sys.path.insert(0, ROOT)
    from domains import load_all
    load_all()
    from domains import bakdrop as K
    _hostshell_offline(check)
    _catalog_offline(check)
    _logic_offline(check, K)
    _cli_offline(check)
    _i18n_offline(check, K)
    _static_offline(check)


# ---------------------------------------------------------------------------------------------------------------- песочница LocalDB

def sandbox(check, _ldb=None):
    import pyodbc
    import selftest_dbbackup_a5 as D
    srv = "(localdb)\\" + INSTANCE
    raw = lambda database: pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=%s;DATABASE=%s;Trusted_Connection=yes;" % (srv, database),
                                          autocommit=True, timeout=60)
    run = lambda *a: subprocess.run(["sqllocaldb"] + list(a), capture_output=True, timeout=180)
    run("stop", INSTANCE, "-k")
    run("delete", INSTANCE)
    c = run("create", INSTANCE, "-s")
    if c.returncode != 0:
        return check("копии стенд: свой экземпляр LocalDB %s создан" % INSTANCE, False, (c.stdout + c.stderr)[-300:])
    fdir = tempfile.mkdtemp(prefix="asda_a58_")
    try:
        _sandbox(check, raw, fdir, D)
    finally:
        run("stop", INSTANCE, "-k")
        run("delete", INSTANCE)
        shutil.rmtree(fdir, ignore_errors=True)


JOY1_OBJECTS = [
    "CREATE TABLE dbo.Charinfo (Userindex INT, Charname VARCHAR(20)); INSERT dbo.Charinfo VALUES (1,'a'),(2,'b')",
    "CREATE PROCEDURE dbo.UPUserLogin_bak_20261012_ac0 @id VARCHAR(61) AS SELECT 1 AS ac0",
    "CREATE PROCEDURE dbo.UPUserLogin_bak_20261012_ac0r @id VARCHAR(61) AS SELECT 2 AS ac0r",
    "CREATE PROCEDURE dbo.UPUserLogin_bak_20261012_ac1 @id VARCHAR(61) AS EXEC dbo.UPUserLogin_bak_20261012_ac0 @id",
    "CREATE PROCEDURE dbo.UP_AC_IdentityCheck_bak_20261012_ac0r @u INT AS SELECT @u AS u",
    "CREATE TABLE dbo.cashgift_bak_procs_20261101 (Name SYSNAME NOT NULL, Def NVARCHAR(MAX) NULL, Taken DATETIME NOT NULL DEFAULT GETDATE()); "
    "INSERT dbo.cashgift_bak_procs_20261101 (Name, Def) VALUES (N'UPGivenitem', NULL), (N'UpCreateCharEventitem', NULL)",
    "CREATE TABLE dbo.Item_bak_charge_20261101 (Uuid BIGINT); INSERT dbo.Item_bak_charge_20261101 VALUES (1),(2),(3)",
    "CREATE TABLE dbo.AsdaProcBackup (Patch VARCHAR(10), ProcName SYSNAME, Definition NVARCHAR(MAX), SavedAt DATETIME)",
    "CREATE TABLE dbo.Foo_bak_20261121 (x INT)",
    "CREATE PROCEDURE dbo.UPUserLogin_BAk AS SELECT 0",
]


def _sandbox(check, raw, fdir, D):
    import pyodbc
    from core import db
    from domains import dbbackup as B
    m = raw("master")
    for d, coll in (("AsdaAdmin", "Cyrillic_General_CI_AS"), ("Joy1", "Arabic_CI_AS"), ("joylog1", "Arabic_CI_AS")):
        f = os.path.join(fdir, d)
        m.cursor().execute("CREATE DATABASE [%s] ON (NAME = N'%s', FILENAME = N'%s.mdf') LOG ON (NAME = N'%s_log', FILENAME = N'%s_log.ldf') COLLATE %s"
                           % (d, d, f, d, f, coll))
        if d != "AsdaAdmin":
            m.cursor().execute("ALTER DATABASE [%s] SET COMPATIBILITY_LEVEL = 100" % d)       # как Joy1 / joylog1 на сервере
    m.cursor().execute("CREATE LOGIN asda_admin WITH PASSWORD = N'Aa1-stand-%s', CHECK_POLICY = OFF" % os.urandom(6).hex())
    a = raw("AsdaAdmin")
    for b in D._batches(open(os.path.join(ROOT, "sql", "adminc_02_schema.sql"), encoding="utf-8").read()):
        a.cursor().execute(b)
    a.cursor().execute("CREATE USER asda_admin FOR LOGIN asda_admin WITH DEFAULT_SCHEMA = adm")
    a.cursor().execute("GRANT SELECT, INSERT ON adm.audit TO asda_admin; GRANT UPDATE (undone_by) ON adm.audit TO asda_admin; "
                       "GRANT SELECT ON adm.users TO asda_admin; GRANT UPDATE (totp_last) ON adm.users TO asda_admin")
    for b in D._batches(open(os.path.join(ROOT, "sql", "adminc_14_jobs.sql"), encoding="utf-8").read()):
        a.cursor().execute(b)
    j, jl = raw("Joy1"), raw("joylog1")
    for q in JOY1_OBJECTS:
        j.cursor().execute(q)
    deny = ("ALTER ROLE db_datareader ADD MEMBER asda_admin; DENY INSERT, UPDATE, DELETE, EXECUTE, ALTER, REFERENCES, CREATE TABLE, CREATE PROCEDURE, "
            "CREATE FUNCTION, CREATE VIEW TO asda_admin")                      # как adminc_03_grants на сервере
    for cn in (j, jl):
        cn.cursor().execute("CREATE USER asda_admin FOR LOGIN asda_admin; " + deny)
    a.cursor().execute("SET LANGUAGE Russian")      # как Windows-вход Administrator на сервере (dmy)
    try:
        for k in (1, 2):
            for f in ("adminc_16_dbbackup.sql", "adminc_17_bakdrop.sql"):
                for b in D._batches(open(os.path.join(ROOT, "sql", f), encoding="utf-8").read()):
                    a.cursor().execute(b)
        check("копии стенд: adminc_16 и adminc_17 выполнены дважды под SET LANGUAGE Russian (повтор безопасен)", True)
    except pyodbc.Error as ex:
        return check("копии стенд: adminc_16 / adminc_17 выполнены", False, str(ex)[:600])
    bk = os.path.join(fdir, "bk")
    os.makedirs(bk)
    a.cursor().execute("UPDATE adm.dbbackup_cfg SET folder = ?", bk)
    q = lambda cn, sql, *p: cn.cursor().execute(sql, *p).fetchall()
    priv = q(a, "SELECT pvt_key_encryption_type_desc FROM sys.certificates WHERE name = 'adm_bakdrop_cert'")
    check("копии стенд: у сертификата подписи нет закрытого ключа", priv and priv[0][0] == "NO_PRIVATE_KEY", priv)
    ctl = sorted((r[0], r[1]) for r in q(j, "SELECT u.name, OBJECT_NAME(p.major_id) FROM sys.database_permissions p JOIN sys.database_principals u "
                                             "ON u.principal_id = p.grantee_principal_id WHERE u.name LIKE 'adm[_]bakdrop[_]%' AND p.permission_name = 'CONTROL'"))
    check("копии стенд: CONTROL — только у исполнителя без входа adm_bakdrop_x и ровно на 5 копий «можно убрать» (не на копии отката, не на неизвестные)",
          ctl == sorted(("adm_bakdrop_x", n.split(".")[1]) for n in DROP_LIVE), ctl)
    imp = q(j, "SELECT g.name, p.permission_name, t.name FROM sys.database_permissions p JOIN sys.database_principals g ON g.principal_id = p.grantee_principal_id "
               "JOIN sys.database_principals t ON t.principal_id = p.major_id WHERE p.class = 4")
    xl = q(j, "SELECT authentication_type_desc FROM sys.database_principals WHERE name = 'adm_bakdrop_x'")
    check("копии стенд: олицетворять adm_bakdrop_x может только логин подписи, у adm_bakdrop_x входа нет",
          [tuple(x) for x in imp] == [("adm_bakdrop_u", "IMPERSONATE", "adm_bakdrop_x")] and xl and xl[0][0] == "NONE", (imp, xl))
    dbp = sorted(r[0] for r in q(j, "SELECT p.permission_name FROM sys.database_permissions p JOIN sys.database_principals u "
                                    "ON u.principal_id = p.grantee_principal_id WHERE u.name = 'adm_bakdrop_u' AND p.class = 0"))
    roles = q(j, "SELECT r.name FROM sys.database_role_members x JOIN sys.database_principals r ON r.principal_id = x.role_principal_id "
                 "JOIN sys.database_principals u ON u.principal_id = x.member_principal_id WHERE u.name = 'adm_bakdrop_u'")
    check("копии стенд: на уровне базы у логина подписи только CONNECT и VIEW DEFINITION, ролей нет", dbp == ["CONNECT", "VIEW DEFINITION"]
          and not roles, (dbp, roles))
    seq = [0]

    def as_admin(database):
        seq[0] += 1
        cn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=(localdb)\\%s;DATABASE=%s;Trusted_Connection=yes;APP=a58sb%d;"
                            % (INSTANCE, database, seq[0]), autocommit=True, timeout=120)
        return D._AsLogin(cn, "asda_admin")

    def direct(database, sql):
        cn = as_admin(database)
        try:
            cn.cursor().execute(sql)
            return None
        except pyodbc.Error as ex:
            return str(ex)
        finally:
            cn.close()
    w = direct("Joy1", "EXECUTE AS USER = N'adm_bakdrop_x'; REVERT;")
    check("копии стенд: asda_admin сам олицетворить adm_bakdrop_x не может", w is not None, (w or "")[:200])
    w = direct("Joy1", "DROP TABLE dbo.cashgift_bak_procs_20261101")
    check("копии стенд: asda_admin сам DROP TABLE копии — отказ", w is not None and q(j, "SELECT OBJECT_ID('dbo.cashgift_bak_procs_20261101')")[0][0],
          (w or "")[:200])
    w = direct("AsdaAdmin", "INSERT adm.bakdrop_log (batch, db, sch, name, kind, backup_id, backup_file, backup_finished, by_login) "
                            "VALUES (NEWID(), 'Joy1', 'dbo', 'x', 'U', 1, 'x', SYSUTCDATETIME(), 'x')")
    check("копии стенд: asda_admin пишет в журнал удалений напрямую — отказ 229", w and "(229)" in w, (w or "")[:200])
    w = direct("AsdaAdmin", "CREATE TABLE #bak (db SYSNAME, sch SYSNAME, name SYSNAME, oid INT, type CHAR(2), type_desc NVARCHAR(60), created DATETIME2, "
                            "modified DATETIME2, rows_n BIGINT, kb BIGINT); CREATE TABLE #bakref (db SYSNAME, sch SYSNAME, name SYSNAME, rdb SYSNAME, "
                            "rsch NVARCHAR(128), rname NVARCHAR(400), rtype CHAR(2), how VARCHAR(10)); EXEC adm.BakScan")
    check("копии стенд: внутреннюю adm.BakScan asda_admin сам не вызывает (229)", w and "(229)" in w, (w or "")[:200])
    a.cursor().execute("INSERT adm.users (login, role, pw_hash, pw_salt, pw_iter) VALUES (N'a58owner', 'owner', 0x00, 0x00, 1)")
    uid = q(a, "SELECT id FROM adm.users WHERE login = N'a58owner'")[0][0]
    hooks = (B.FILE_INFO, B.DELETE_FILE, B.COUNTS)
    B.FILE_INFO = lambda p: (os.path.getsize(p), "0" * 32)
    B.DELETE_FILE = lambda p: False
    def fcounts(dbname):                              # настоящий снимок строк (ревизия 48 Н-1 сверяет с ним строки копий)
        cn = as_admin(dbname)
        try:
            return {str(r[0]): int(r[1]) for r in cn.cursor().execute(B.COUNT_SQL).fetchall()}
        finally:
            cn.close()
    B.COUNTS = fcounts
    db.set_override("admin", lambda database: as_admin("AsdaAdmin"))
    try:
        _sandbox_ops(check, a, j, jl, uid, q, as_admin, direct)
    finally:
        db.set_override("admin", None)
        B.FILE_INFO, B.DELETE_FILE, B.COUNTS = hooks
        for cn in (a, j, jl, m):
            try:
                cn.close()
            except Exception:
                pass


def _sandbox_ops(check, a, j, jl, uid, q, as_admin, direct):
    from core import auth, ops
    from domains import bakdrop as K, dbbackup as B
    cli = _ctx("cli")
    exists = lambda n: q(j, "SELECT OBJECT_ID(?)", n)[0][0] is not None

    def proc(dbn, names, bid, by, confirm):         # adm.BakDrop в обход панели → «текст (код)» | None
        _r, err, code = K.call("SET NOCOUNT ON; EXEC adm.BakDrop @db = ?, @names = ?, @backup_id = ?, @by = ?, @confirm = ?",
                               (dbn, names, bid, by, confirm))
        return "%s (%s)" % (err, code) if err else None
    # 1. список копий подписанной процедурой под asda_admin
    K.forget()
    st = K.state()
    it = {"%s.%s" % (x["sch"], x["name"]): x for x in st["items"] if x["db"] == "Joy1"}
    check("копии стенд: список прочитан под asda_admin (подписанная adm.BakState)", st["read"], st.get("error"))
    if not st["read"]:
        return
    check("копии стенд: вердикты — можно убрать / нужна откату / неизвестно (в том числе «копийное» имя вне каталога)",
          it.get("dbo.cashgift_bak_procs_20261101", {}).get("verdict") == "drop" and it.get("dbo.Item_bak_charge_20261101", {}).get("verdict") == "rollback"
          and it.get("dbo.Foo_bak_20261121", {}).get("verdict") == "unknown" and not it["dbo.Foo_bak_20261121"]["in_catalog"]
          and it.get("dbo.UPUserLogin_BAk", {}).get("verdict") == "unknown" and "dbo.Charinfo" not in it, sorted(it))
    c = it["dbo.cashgift_bak_procs_20261101"]
    check("копии стенд: размер и строки копии прочитаны (cashgift — 2 строки), даты UTC", c["rows_n"] == 2 and c["kb"] is not None and c["created_utc"],
          (c["rows_n"], c["kb"], c["created_utc"]))
    a0 = it["dbo.UPUserLogin_bak_20261012_ac0"]
    check("копии стенд: ссылка ac1 → ac0 найдена (текст), ac0r не считается ссылкой на ac0 (граница имени)",
          {x[2] for x in K.refs_of(a0)} == {"UPUserLogin_bak_20261012_ac1"} and {x[3] for x in K.refs_of(a0)} == {"expr", "text"}
          and not a0["droppable"]
          and it["dbo.UPUserLogin_bak_20261012_ac0r"]["refs_n"] == 0, (a0["refs_n"], a0["refs"]))
    absent = [x for x in st["items"] if not x["present"]]
    check("копии стенд: строки каталога, которых нет на сервере, показаны как «нет»", absent and all(x["in_catalog"] for x in absent), len(absent))
    # 2. отказы до бэкапа
    w = _refused(lambda: ops.run(cli, "db.bakdrop", {"db": "Joy1", "names": "dbo.cashgift_bak_procs_20261101"}, dry=True))
    check("копии стенд: свежего проверенного бэкапа нет — отказ с предложением сделать бэкап", w and "сначала сделайте бэкап" in w, w)
    w = proc("Joy1", '["dbo.cashgift_bak_procs_20261101"]', 1, "t", "bakdrop")
    check("копии стенд: процедура без бэкапа — отказ 50807, копия на месте", w and "50807" in w and exists("dbo.cashgift_bak_procs_20261101"), w)
    r = ops.run(cli, "db.backup", {"dbs": "Joy1"})
    bid = q(a, "SELECT MAX(id) FROM adm.dbbackup WHERE db = 'Joy1' AND verified = 1")[0][0]
    check("копии стенд: бэкап Joy1 сделан и проверен (А5.7)", bid is not None, r["message"])
    for names, want in ((["dbo.Item_bak_charge_20261101"], "нужна откату"), (["dbo.UPUserLogin_BAk"], "не установлено"),
                        (["dbo.Foo_bak_20261121"], "не установлено"), (["dbo.Charinfo"], "нет в списке"),
                        (["dbo.UPUserLogin_bak_20261012_ac0"], "ссылаются")):
        w = _refused(lambda: ops.run(cli, "db.bakdrop", {"db": "Joy1", "names": names}, dry=True))
        check("копии стенд: предпросмотр %s — отказ «%s»" % (names[0], want), w and want in w, w)
    for names, code in ((["dbo.Item_bak_charge_20261101"], "50805"), (["dbo.Foo_bak_20261121"], "50804"), (["dbo.UPUserLogin_BAk"], "50806"),
                        (["dbo.UPUserLogin_bak_20261012_ac0"], "50810")):
        w = proc("Joy1", json.dumps(names), bid, "t", "bakdrop")
        check("копии стенд: процедура в обход панели %s — отказ %s, объект на месте" % (names[0], code), w and code in w and exists(names[0]), w)
    w = proc("Joy1", '["dbo.cashgift_bak_procs_20261101"]', bid, "t", "yes")
    check("копии стенд: процедура без слова bakdrop — отказ 50801", w and "50801" in w, w)
    w = proc("AsdaAdmin", '["adm.audit"]', bid, "t", "bakdrop")
    check("копии стенд: процедура по базе AsdaAdmin — отказ 50802", w and "50802" in w, w)
    # 3. ссылка из другой базы
    jl.cursor().execute("CREATE PROCEDURE dbo.UseCash AS SELECT COUNT(*) FROM Joy1.dbo.cashgift_bak_procs_20261101")
    w = _refused(lambda: ops.run(cli, "db.bakdrop", {"db": "Joy1", "names": "dbo.cashgift_bak_procs_20261101"}, dry=True))
    w2 = proc("Joy1", '["dbo.cashgift_bak_procs_20261101"]', bid, "t", "bakdrop")
    check("копии стенд: ссылка из joylog1 — отказ и в предпросмотре, и в процедуре (50810)", w and "joylog1.dbo.UseCash" in w and w2 and "50810" in w2,
          (w, w2))
    jl.cursor().execute("DROP PROCEDURE dbo.UseCash")
    # 4. бэкап устарел / объект изменён после бэкапа
    a.cursor().execute("UPDATE adm.dbbackup SET finished_at = DATEADD(HOUR, -7, finished_at), verified_at = DATEADD(HOUR, -7, verified_at) WHERE id = ?", bid)
    w = _refused(lambda: ops.run(cli, "db.bakdrop", {"db": "Joy1", "names": "dbo.cashgift_bak_procs_20261101"}, dry=True))
    w2 = proc("Joy1", '["dbo.cashgift_bak_procs_20261101"]', bid, "t", "bakdrop")
    check("копии стенд: бэкап старше 6 ч — отказ в предпросмотре и 50807 в процедуре", w and "не старше 6 ч" in w and w2 and "50807" in w2, (w, w2))
    a.cursor().execute("UPDATE adm.dbbackup SET finished_at = DATEADD(HOUR, 7, finished_at), verified_at = DATEADD(HOUR, 7, verified_at) WHERE id = ?", bid)
    j.cursor().execute("ALTER PROCEDURE dbo.UP_AC_IdentityCheck_bak_20261012_ac0r @u INT AS SELECT @u + 0 AS u")
    w = _refused(lambda: ops.run(cli, "db.bakdrop", {"db": "Joy1", "names": "dbo.UP_AC_IdentityCheck_bak_20261012_ac0r"}, dry=True))
    w2 = proc("Joy1", '["dbo.UP_AC_IdentityCheck_bak_20261012_ac0r"]', bid, "t", "bakdrop")
    check("копии стенд: объект изменён после бэкапа — отказ в предпросмотре и 50809 в процедуре", w and "после начала бэкапа" in w
          and w2 and "50809" in w2, (w, w2))
    ops.run(cli, "db.backup", {"dbs": "Joy1"})
    bid = q(a, "SELECT MAX(id) FROM adm.dbbackup WHERE db = 'Joy1' AND verified = 1")[0][0]
    cg = ["dbo.cashgift_bak_procs_20261101"]
    # ★ ревизия 48 Н-1: строки таблицы изменены после бэкапа — DDL-даты этого не видят; сверка со снимком строк и с последней записью
    j.cursor().execute("INSERT dbo.cashgift_bak_procs_20261101 (Name, Def) VALUES (N'late', NULL)")
    w = _refused(lambda: ops.run(cli, "db.bakdrop", {"db": "Joy1", "names": cg}, dry=True))
    w2 = proc("Joy1", json.dumps(cg), bid, "t", "bakdrop")
    check("копии стенд (рев. 48 Н-1): строка дописана после бэкапа — отказ в предпросмотре (снимок строк) и 50812 в процедуре, копия на месте",
          w and "не совпадают со снимком" in w and w2 and "50812" in w2 and exists(cg[0]), (w, w2))
    j.cursor().execute("DELETE dbo.cashgift_bak_procs_20261101 WHERE Name = N'late'")
    w = _refused(lambda: ops.run(cli, "db.bakdrop", {"db": "Joy1", "names": cg}, dry=True))
    w2 = proc("Joy1", json.dumps(cg), bid, "t", "bakdrop")
    check("копии стенд (рев. 48 Н-1): строк столько же, но запись была после бэкапа — процедура всё равно отказывает (50812, последняя запись)",
          w is None and w2 and "50812" in w2 and exists(cg[0]), (w, w2))
    # ★ ревизия 48 С-1: база списка не ONLINE / без пользователя подписи / с модулем без текста — «не прочитано», не «ссылок нет»
    a.cursor().execute("EXEC joylog1.sys.sp_executesql N'CREATE PROCEDURE dbo.UseCash AS SELECT COUNT(*) FROM Joy1.dbo.cashgift_bak_procs_20261101'")
    a.cursor().execute("ALTER DATABASE joylog1 SET OFFLINE WITH ROLLBACK IMMEDIATE")
    K.forget()
    st = K.state()
    w = _refused(lambda: ops.run(cli, "db.bakdrop", {"db": "Joy1", "names": cg}, dry=True))
    w2 = proc("Joy1", json.dumps(cg), bid, "t", "bakdrop")
    check("копии стенд (рев. 48 С-1): joylog1 OFFLINE — в списке «не прочитано», отказ в предпросмотре и 50811 в процедуре, копия на месте",
          any(x["db"] == "joylog1" and "ONLINE" in x["why"] for x in st.get("unread", [])) and w and "не во всех базах" in w and "joylog1" in w
          and w2 and "50811" in w2 and exists(cg[0]), (st.get("unread"), w, w2))
    a.cursor().execute("ALTER DATABASE joylog1 SET ONLINE")
    a.cursor().execute("EXEC joylog1.sys.sp_executesql N'DROP USER adm_bakdrop_u'")
    seen_old = direct("joylog1", "SELECT COUNT(*) FROM sys.sql_modules WHERE definition LIKE N'%cashgift_bak_procs_20261101%'")
    cn_old = as_admin("joylog1")
    try:                                               # воспроизведение: так прежний поиск видел joylog1 без пользователя подписи
        n_old = cn_old.cursor().execute("SELECT COUNT(*) FROM sys.sql_modules WHERE definition LIKE N'%cashgift_bak_procs_20261101%'").fetchone()[0]
    finally:
        cn_old.close()
    n_real = q(a, "SELECT COUNT(*) FROM joylog1.sys.sql_modules WHERE definition LIKE N'%cashgift_bak_procs_20261101%'")[0][0]
    check("копии стенд (рев. 48 С-1): воспроизведение — под asda_admin без пользователя подписи ссылка UseCash в joylog1 не видна (молча 0)",
          seen_old is None and n_old == 0 and n_real == 1, (seen_old, n_old, n_real))
    w = _refused(lambda: ops.run(cli, "db.bakdrop", {"db": "Joy1", "names": cg}, dry=True))
    w2 = proc("Joy1", json.dumps(cg), bid, "t", "bakdrop")
    check("копии стенд (рев. 48 С-1): в joylog1 нет adm_bakdrop_u — отказ в предпросмотре и 50811 в процедуре (а не «ссылок нет»)",
          w and "joylog1" in w and w2 and "50811" in w2 and exists(cg[0]), (w, w2))
    a.cursor().execute("EXEC joylog1.sys.sp_executesql N'CREATE USER adm_bakdrop_u FOR LOGIN adm_bakdrop_signer; GRANT VIEW DEFINITION TO adm_bakdrop_u; "
                       "GRANT SELECT ON sys.sql_expression_dependencies TO adm_bakdrop_u; GRANT IMPERSONATE ON USER::adm_bakdrop_x TO adm_bakdrop_u'")
    a.cursor().execute("EXEC joylog1.sys.sp_executesql N'DROP PROCEDURE dbo.UseCash'")
    a.cursor().execute("EXEC joylog1.sys.sp_executesql N'CREATE PROCEDURE dbo.EncX WITH ENCRYPTION AS SELECT 1 AS x'")
    K.forget()
    st = K.state()
    w2 = proc("Joy1", json.dumps(cg), bid, "t", "bakdrop")
    check("копии стенд (рев. 48 С-1): модуль WITH ENCRYPTION в joylog1 — «не прочитано», 50811", any("ENCRYPTION" in x["why"] for x in st.get("unread", []))
          and w2 and "50811" in w2, (st.get("unread"), w2))
    a.cursor().execute("EXEC joylog1.sys.sp_executesql N'DROP PROCEDURE dbo.EncX'")
    w2 = proc("Joy1 ", json.dumps(cg), bid, "t", "bakdrop")
    check("копии стенд (рев. 48, мелочь 1): имя базы с хвостовым пробелом — отказ 50802", w2 and "50802" in w2, w2)
    ops.run(cli, "db.backup", {"dbs": "Joy1"})
    bid = q(a, "SELECT MAX(id) FROM adm.dbbackup WHERE db = 'Joy1' AND verified = 1")[0][0]
    # 5. путь применения: без слова, из браузера без второго фактора, заданием, не владелец
    batch = ["dbo.UPUserLogin_bak_20261012_ac0", "dbo.UPUserLogin_bak_20261012_ac1", "dbo.cashgift_bak_procs_20261101"]
    pv = ops.run(cli, "db.bakdrop", {"db": "Joy1", "names": batch}, dry=True)["preview"]
    check("копии стенд: ac0 вместе с ac1 (ссылка внутри выбора) — предпросмотр проходит, бэкап — свежий", pv["backup_id"] == bid
          and "отмены нет" in pv["warnings"][0], pv["text"])
    w = _refused(lambda: ops.run(cli, "db.bakdrop", {"db": "Joy1", "names": batch}))
    check("копии стенд: без слова bakdrop — отказ, копии на месте", w and "слово bakdrop" in w and all(exists(n) for n in batch), w)
    web = _ctx("web", uid=uid, login="a58owner")
    w = _refused(lambda: ops.run(web, "db.bakdrop", {"db": "Joy1", "names": batch, "confirm": "bakdrop", "totp": "000000"}))
    check("копии стенд: из браузера без настроенного второго фактора — отказ, копии на месте", w and "второй фактор" in w
          and all(exists(n) for n in batch), w)
    w = _refused(lambda: ops.run(_ctx("job"), "db.bakdrop", {"db": "Joy1", "names": batch, "confirm": "bakdrop"}))
    check("копии стенд: заданием — отказ", w and "не заданием" in w, w)
    # 6. атомарность: DDL-триггер отменяет DROP таблицы — откатываются и уже удалённые в этой транзакции процедуры, журнала нет
    j.cursor().execute("CREATE TRIGGER a58_block ON DATABASE FOR DROP_TABLE AS IF EVENTDATA().value('(/EVENT_INSTANCE/ObjectName)[1]', 'sysname') "
                       "= N'cashgift_bak_procs_20261101' BEGIN RAISERROR('a58 block', 16, 1); ROLLBACK; END")
    n0 = q(a, "SELECT COUNT(*) FROM adm.bakdrop_log")[0][0]
    try:
        ops.run(cli, "db.bakdrop", {"db": "Joy1", "names": batch, "confirm": "bakdrop"})
        got = "прошло"
    except Exception as ex:
        got = str(ex)
    check("копии стенд: сбой DROP посреди — откат всей транзакции (процедуры на месте, журнала нет)", got != "прошло" and all(exists(n) for n in batch)
          and q(a, "SELECT COUNT(*) FROM adm.bakdrop_log")[0][0] == n0, got[:200])
    j.cursor().execute("DROP TRIGGER a58_block ON DATABASE")
    # 7. успех: браузер со словом и вторым фактором (проверка кода подменена — настоящая проверена в А5.3), снимок, журнал, права
    seen = []
    keep = auth.totp_confirm
    auth.totp_confirm = lambda u, code: seen.append((u, code))
    try:
        r = ops.run(web, "db.bakdrop", {"db": "Joy1", "names": batch, "confirm": "bakdrop", "totp": "123456"})
    finally:
        auth.totp_confirm = keep
    log = q(a, "SELECT sch + '.' + name, RTRIM(kind), ddl, rows_n, backup_id, backup_file, by_login FROM adm.bakdrop_log ORDER BY id")
    ok = (seen == [(uid, "123456")] and not any(exists(n) for n in batch) and len(log) == 3 and all(x[4] == bid and x[5] and x[6] == "a58owner" for x in log))
    check("копии стенд: из браузера со словом и кодом — 3 копии удалены одной транзакцией, журнал на каждую (бэкап, файл, автор)", ok, (r["message"], log))
    d = {x[0]: x for x in log}
    t = d.get("dbo.cashgift_bak_procs_20261101")
    check("копии стенд: снимок таблицы — столбцы (тип, сортировка, NULL, DEFAULT — ревизия 48) и число строк",
          t and t[2].startswith("CREATE TABLE [dbo].[cashgift_bak_procs_20261101] ([Name] sysname") and "NVARCHAR(MAX)".lower() in t[2].lower()
          and "[Taken] datetime NOT NULL DEFAULT (getdate())" in t[2] and t[3] == 2, t and t[2][:200])
    p = d.get("dbo.UPUserLogin_bak_20261012_ac1")
    check("копии стенд: снимок процедуры — полный текст", p and "CREATE PROCEDURE dbo.UPUserLogin_bak_20261012_ac1" in p[2], p and p[2][:120])
    au = q(a, "SELECT TOP 1 action, result, message FROM adm.audit ORDER BY id DESC")
    check("копии стенд: запись журнала панели db.bakdrop ok (бэкап и номера журнала удаления)", au and au[0][0] == "db.bakdrop" and au[0][1] == "ok"
          and "журнал удаления" in au[0][2], au)
    check("копии стенд: копии отката и неизвестные не тронуты", all(exists(n) for n in ("dbo.Item_bak_charge_20261101", "dbo.AsdaProcBackup",
                                                                                       "dbo.Foo_bak_20261121", "dbo.UPUserLogin_BAk")))
    check("копии стенд (рев. 48 Н-4): бэкап из журнала удаления — в защищённых от автоуборки (dbbackup.pinned)", bid in B.pinned(), B.pinned())
    r2 = ops.run(cli, "db.bakdrop", {"db": "Joy1", "names": "dbo.UPUserLogin_bak_20261012_ac0r", "confirm": "bakdrop"})
    check("копии стенд: консолью со словом — удалено (ac0r)", not exists("dbo.UPUserLogin_bak_20261012_ac0r") and "ac0r" in r2["message"], r2["message"])
    st = K.state()
    check("копии стенд: после удаления — в списке «нет на сервере», журнал удалений виден панели (4 строки)",
          st["read"] and all(not x["present"] for x in st["items"] if "%s.%s" % (x["sch"], x["name"]) in batch) and len(st["log"]) == 4,
          (st.get("error"), len(st.get("log") or [])))


# ---------------------------------------------------------------------------------------------------------------- живьём (только чтение)

def live(check):
    sys.path.insert(0, ROOT)
    from domains import load_all
    load_all()
    from core import db, ops
    from domains import bakdrop as K
    st = K.state()
    check("копии (живьём): список прочитан подписанной adm.BakState (asda_admin)", st["read"], st.get("error"))
    if not st["read"]:
        return
    it = {"%s.%s.%s" % (x["db"], x["sch"], x["name"]): x for x in st["items"]}
    drop = [it.get("Joy1." + n) for n in DROP_LIVE]
    check("копии (живьём): 5 копий «можно убрать» есть на сервере и без ссылок",
          all(x and x["present"] and x["verdict"] == "drop" and x["refs_n"] == 0 for x in drop),
          [(n, x and (x["present"], x["refs_n"], x["refs"])) for n, x in zip(DROP_LIVE, drop)])
    check("копии (живьём, рев. 48 С-1): ссылки прочитаны во всех базах (нет «не прочитано»)", not st.get("unread"), st.get("unread"))
    # ★ ревизия 48 (мелочь 2): живой OBJECT_DEFINITION четырёх копий = эталону репозитория, тело целиком в файле отката (SqlClient: сохраняет
    #   корейские комментарии, которые sqlcmd выводит «?»)
    import base64
    from core import hostshell
    ps = ("$cn = New-Object System.Data.SqlClient.SqlConnection('Server=lpc:.\\SQLEXPRESS;Database=Joy1;Integrated Security=SSPI'); $cn.Open(); "
          "foreach ($n in %s) { $c = $cn.CreateCommand(); $c.CommandText = \"SELECT OBJECT_DEFINITION(OBJECT_ID(N'dbo.$n'))\"; "
          "'DEF|' + $n + '|' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$c.ExecuteScalar())) }; $cn.Close()"
          % ",".join("'%s'" % n for n, _f in BODY_FILES))
    try:
        got = {l.split("|")[1]: base64.b64decode(l.split("|")[2]).decode("utf-8") for l in hostshell.powershell(ps, 120).splitlines()
               if l.startswith("DEF|")}
    except Exception as ex:
        got = {"error": str(ex)[:200]}
    for name, f in BODY_FILES:
        live_t = got.get(name)
        ref = open(os.path.join(REF_DIR, name + ".def.sql"), encoding="utf-8").read()
        ok = live_t is not None and _norm_body(live_t, name) == _norm_body(ref, name) and body_in_rollback(name, f, live_t)[0]
        check("копии (живьём, рев. 48): %s — живой текст = эталону, целиком в %s" % (name, f), ok, (got.get("error"), live_t and len(live_t)))
    rb = [x for x in st["items"] if x["verdict"] == "rollback" and x["present"]]
    check("копии (живьём): копии отката на месте (≥ 40)", len(rb) >= 40, len(rb))
    unk = [k for k, x in it.items() if x["verdict"] == "unknown" and x["present"]]
    check("копии (живьём): неизвестные — только сток (UPUserLogin_BAk, OpStat_SaleItem_Original) или новые вне каталога (показаны)",
          "Joy1.dbo.UPUserLogin_BAk" in unk and "AsdaStoryOp.dbo.OpStat_SaleItem_Original" in unk, unk)
    with db.GameReader("joy1") as r:
        perm = r.rows("SELECT HAS_PERMS_BY_NAME('Joy1', 'DATABASE', 'ALTER ANY SCHEMA') AS s, HAS_PERMS_BY_NAME('Joy1', 'DATABASE', 'CONTROL') AS c, "
                      "HAS_PERMS_BY_NAME('dbo.cashgift_bak_procs_20261101', 'OBJECT', 'CONTROL') AS o, IS_SRVROLEMEMBER('sysadmin') AS a")[0]
    check("копии (живьём): у asda_admin своих прав удалить копию нет (ALTER ANY SCHEMA / CONTROL / sysadmin)",
          perm["s"] == 0 and perm["c"] == 0 and perm["o"] == 0 and perm["a"] == 0, perm)
    n0 = sum(1 for x in st["items"] if x["present"])
    try:
        r = ops.run(_ctx("cli"), "db.bakdrop", {"db": "Joy1", "names": DROP_LIVE}, dry=True)
        txt = r["preview"]["text"]
        good = r["dry"] and len(r["preview"]["names"]) == 5
    except ops.OpRefused as ex:
        txt = str(ex)
        good = "сначала сделайте бэкап" in txt               # нет свежего бэкапа — честный отказ, не сбой
    n1 = sum(1 for x in K.state()["items"] if x["present"])
    check("копии (живьём): сухой предпросмотр удаления 5 копий (или отказ «нет свежего бэкапа») — ничего не удалено", good and n0 == n1, (txt, n0, n1))
