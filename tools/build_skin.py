# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""build_skin.py — игровой скин панели: элементы окон JUI игры (рамки, заголовки, кнопки, вкладки, ячейки, поля,
полосы прокрутки, значки разделов) вырезаются из атласов игры в web/skin/. 16.11.2026.

ЗАЧЕМ. Владелец 16.11: «дизайн должен быть как в игре — текстуры, окна, шрифты, всё». Панель рисуется теми же
картинками, что и окна клиента: ничего не рисуется заново, только вырезается.

ОТКУДА (те же источники, из которых импортёр JUI собирает виджеты клиента):
  JuiSkin.ini (RE/docs) — запись скина = планы (ES) × кадры-состояния (SS: 0 обычное, 1 наведение, 2 нажато,
  3 выбрано), у кадра — атлас, UV, Diffuse (sRGB, как в D3D9-клиенте — браузер тоже sRGB, поэтому БЕЗ перевода в
  linear, в отличие от UE), цвет подписи; разбор — asda_jui_parse.parse_skins_full (общий с импортёром).
  Атласы — AsdaReborn/RawAssets/Textures/JUI/<атлас>.png.
Раскладка планов:
  * ResizeWindow из 9 планов — «девятка»: углы родного размера, стороны тянутся (как окно клиента при ресайзе);
    сохраняется картинка шаблона + отступы углов → CSS border-image;
  * остальное — планы по своим Rect в шаблоне (максимальные границы Rect) — как plane_screen_rects клиента.
ВЫХОД: web/skin/<скин>[.<кадр>].png + web/skin/skin.json {скин: {type, w, h, slice:[t,r,b,l]|null, frames:[...],
       caption:{кадр: "#rrggbb"}}} — справка для web/app.css (он ссылается на /skin/<скин>[.<кадр>].png).
ЗАПУСК: python AstoryAdminCenter/tools/build_skin.py      (нужен Pillow)
Побочных эффектов при импорте нет: вся работа в main().
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                              # AstoryAdminCenter
PORT = os.path.dirname(ROOT)                             # папка с клонами
JUI_TOOLS = os.path.join(PORT, "AstoryClient", "Tools")
TEX_DIR = os.path.join(PORT, "AstoryClient", "RawAssets", "Textures", "JUI")
OUT = os.path.join(ROOT, "web", "skin")

# Скины, которые нужны панели (имена — как в JuiSkin.ini / окнах клиента; откуда взят каждый — комментарий).
SKINS = [
    # окно: рамка и заголовок (окно «Рюкзак»: Win_Mg → WinMd_LBar/CBar/RBar, WinTitle_Bg, Gear_50_InnerCircle, CloseBtn_18)
    "win_mg", "winmd_lbar", "winmd_cbar", "winmd_rbar", "wintitle_bg", "gear_50_innercircle", "closebtn_18",
    # внутренние панели и рамки
    "win_tab", "box_white3stroke_blackfill", "box_white3stroke", "box_white1stroke", "box_white1stroke_ot15",
    "black_bottomround_white2border", "popup_win", "btnbase", "box_yellowround", "box_black", "box_brown",
    # кнопки (кадры 0/1/2) и их значки
    "wkbtn_w140", "graybtn_w140", "greenbtn_w140", "redbtn_w140", "pinkbtn_w140", "mac_btn", "bkbtn_w122",
    "rdbtn_w100", "wkbtn_w100", "smwtbtn_w67", "smredbtn_w67", "smbluebtn_w67", "smylbtn_w143", "smgybtn_w143",
    "wkbtn_iconcir", "wkbtn_iconcheck", "wkbtn_iconminus", "rdbtn_iconcancel", "trash_btn",
    # вкладки, ячейки, флажки, поля, списки, полосы
    "tabbar_w108_2btn", "slot_base", "slot_aniselect", "box_check", "black_editbox", "bk_combobox",
    "sidebar_scr", "boxicon_gold", "green_bar", "hp_redbar", "white_bar", "yello_bar", "blue2ton_bar",
    # значки разделов (кружок слева от заголовка окна)
    "winicon_inven", "winicon_systme", "winicon_myinfo", "winicon_quest", "winicon_skill", "winicon_comm",
    "winicon_warehouse", "winicon_trade", "winicon_title", "winicon_premiumstore", "winicon_weaponstore",
    "winicon_itemexchange", "winicon_sowel", "winicon_itemstrength", "winicon_misstore", "winicon_packageshop",
    "winicon_booststore", "winicon_hairshop", "winicon_premchange",
]


def _lin_to_srgb(c):
    """parse_skins_full отдаёт Diffuse в linear (для UE) — вернуть исходный sRGB байт файла."""
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


class Atlas:
    """Кэш атласов JUI."""

    def __init__(self, Image):
        self.Image = Image
        self.cache = {}

    def get(self, name):
        if name not in self.cache:
            path = os.path.join(TEX_DIR, name + ".png")
            self.cache[name] = self.Image.open(path).convert("RGBA") if os.path.isfile(path) else None
        return self.cache[name]


def _piece(atlas, fr, w, h, Image):
    """Картинка кадра плана, растянутая на w×h и умноженная на Diffuse (как D3D9: текстура × цвет вершин)."""
    if not fr["tex"] or w < 1 or h < 1:
        return None
    im = atlas.get(fr["tex"])
    if im is None:
        return None
    W, H = im.size
    u0, v0, u1, v1 = fr["uv"]
    box = (round(u0 * W), round(v0 * H), round(u1 * W), round(v1 * H))
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    c = im.crop(box)
    if c.size != (w, h):
        c = c.resize((w, h), Image.BILINEAR)
    r, g, b, a = fr["diffuse"]
    mul = (_lin_to_srgb(r), _lin_to_srgb(g), _lin_to_srgb(b), a)
    if any(abs(m - 1) > 1e-3 for m in mul):
        bands = [ch.point(lambda v, m=m: int(v * m + 0.5)) for ch, m in zip(c.split(), mul)]
        c = Image.merge("RGBA", bands)
    return c


def _frame_of(plane, i):
    """Кадр i плана; нет кадра — кадр 0 (так делает клиент: индекс состояния вне набора → нулевой)."""
    fr = plane["frames"].get(i) or plane["frames"].get(0)
    return fr or {"tex": plane["tex"], "uv": plane["uv"], "diffuse": plane["diffuse"], "capcol": None}


def _template(planes):
    """Размер шаблона = максимальные границы Rect планов."""
    w = max((p["rect"][2] for p in planes if p.get("_hasrect")), default=0)
    h = max((p["rect"][3] for p in planes if p.get("_hasrect")), default=0)
    return int(round(w)), int(round(h))


def _caption(hexcol):
    """FFE9D6BC → #e9d6bc (подпись всегда непрозрачна)."""
    if not hexcol or len(hexcol) < 8:
        return None
    return "#" + hexcol[2:8].lower()


# Скин из нескольких одинаковых кнопок (полоса вкладок) → берётся один план: панель раскладывает вкладки сама.
ONLY_PLANES = {"tabbar_w108_2btn": [0]}


def render_skin(name, s, atlas, Image):
    """Все кадры скина → [(кадр, Image)], описание."""
    planes = [p for p in s["planes"] if not p.get("invisible")]
    if name in ONLY_PLANES:
        planes = [planes[i] for i in ONLY_PLANES[name]]
    if not planes:
        return [], None
    W, H = _template(planes)
    if W <= 0 or H <= 0:
        # план без Rect (EditBox/ListBox — «на весь контрол») — родной размер UV
        fr = _frame_of(planes[0], 0)
        im = atlas.get(fr["tex"]) if fr["tex"] else None
        if im is None:
            return [], None
        u0, v0, u1, v1 = fr["uv"]
        W, H = max(1, round((u1 - u0) * im.size[0])), max(1, round((v1 - v0) * im.size[1]))
    nframes = max(max(p["frames"].keys(), default=0) for p in planes) + 1
    nine = s["type"] == "ResizeWindow" and len(planes) == 9
    out = []
    caps = {}
    for fi in range(nframes):
        cv = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for p in planes:
            x0, y0, x1, y1 = p["rect"] if p.get("_hasrect") else (0, 0, W, H)
            w, h = int(round(x1 - x0)), int(round(y1 - y0))
            fr = _frame_of(p, fi)
            pc = _piece(atlas, fr, w, h, Image)
            if pc is not None:
                cv.alpha_composite(pc, (int(round(x0)), int(round(y0))))
            if fr.get("capcol") and fi not in caps:
                caps[fi] = _caption(fr["capcol"])
        out.append((fi, cv))
    slice_ = None
    if nine:
        r0, r2, r6 = planes[0]["rect"], planes[2]["rect"], planes[6]["rect"]
        slice_ = [int(round(r0[3] - r0[1])), int(round(r2[2] - r2[0])), int(round(r6[3] - r6[1])), int(round(r0[2] - r0[0]))]
    meta = {"type": s["type"], "w": W, "h": H, "slice": slice_, "frames": [f for f, _ in out], "caption": caps,
            "outline": s.get("textoutline", 0)}
    return out, meta


JUI_GAMEMAIN = os.path.join(PORT, "Data", "Decoded", "jui", "gamemain_jui.ini")
# Доска экипировки окна «Рюкзак» (INVEN_WIN, IDNum 400 — то окно, которое игрок видит в клиенте): дерево Inven_WoodBase +
# рамки Equip_* (EQUIP_TRAYICON) + жёлтая кнопка-стрелка «подробнее» (InvenExp_*: в панели — открыть подробности предмета).
BOARD = {"window": 400, "roots": ("Inven_WoodBase", "EQUIP_TRAYICON"), "skip": (),
         "crop": (5, 39, 224, 239), "slots": "EQUIP_SET%d", "nslots": 11}


def _layout_planes(jp, s, w, h):
    """Раскладка планов скина на контрол w×h: девятка — углы родные, остальное — как plane_screen_rects клиента."""
    pls = [q for q in s["planes"] if not q.get("invisible")]
    if s["type"] == "ResizeWindow" and len(pls) == 9:
        r0, r2, r6 = pls[0]["rect"], pls[2]["rect"], pls[6]["rect"]
        cl, cr, ct, cb = r0[2] - r0[0], r2[2] - r2[0], r0[3] - r0[1], r6[3] - r6[1]
        xs, ys = [0, cl, w - cr, w], [0, ct, h - cb, h]
        return [(xs[i % 3], ys[i // 3], xs[i % 3 + 1] - xs[i % 3], ys[i // 3 + 1] - ys[i // 3], pls[i]) for i in range(9)]
    return jp.plane_screen_rects(pls, w, h)


def render_board(jp, skins, atlas, Image):
    """Картинка доски экипировки из разметки JUI (точные позиции calc_positions) + позиции слотов → (Image, meta)."""
    roots = jp.parse_jui(JUI_GAMEMAIN)
    win = next(r for r in roots if r.idnum == BOARD["window"])
    jp.calc_positions(win)
    L, T = win.abs[0], win.abs[1]
    cx0, cy0, cx1, cy1 = BOARD["crop"]
    cv = Image.new("RGBA", (cx1 - cx0, cy1 - cy0), (0, 0, 0, 0))
    slots = {}

    def draw(n, on):
        if n.idc in BOARD["skip"]:
            return
        on = on or n.idc in BOARD["roots"]
        vis = bool(n.visible)
        if not vis:
            return
        l, t, w, h = n.abs
        for i in range(BOARD["nslots"]):
            if n.idc == BOARD["slots"] % i:
                slots[i] = [int(round(l - L - cx0)), int(round(t - T - cy0))]
        s = skins.get(n.name.lower())
        if on and s and n.name.lower() not in ("noimage_icon", "slot_aniselect"):
            for rx, ry, pw, ph, pl in _layout_planes(jp, s, w, h):
                pc = _piece(atlas, _frame_of(pl, 0), max(1, int(round(pw))), max(1, int(round(ph))), Image)
                if pc is not None:
                    tmp = Image.new("RGBA", cv.size, (0, 0, 0, 0))
                    tmp.paste(pc, (int(round(l + rx - L - cx0)), int(round(t + ry - T - cy0))))
                    cv.alpha_composite(tmp)
        for c in n.children:
            draw(c, on)

    for c in win.children:
        draw(c, False)
    if len(slots) != BOARD["nslots"]:
        raise RuntimeError("на доске найдено слотов %d из %d" % (len(slots), BOARD["nslots"]))
    return cv, {"type": "board", "w": cv.size[0], "h": cv.size[1], "slots": slots, "frames": [0], "slice": None,
                "caption": {}, "outline": 0}


def main():
    for st in (sys.stdout, sys.stderr):
        st.reconfigure(encoding="utf-8", errors="replace")
    try:
        from PIL import Image
    except ImportError:
        print("нужен Pillow: pip install pillow")
        return 2
    miss = [p for p in (TEX_DIR, JUI_GAMEMAIN) if not os.path.exists(p)]
    if miss:                                       # ★ 25.11 (М-10): публичный клон — готовые web/skin лежат в репозитории
        print("нет %s — скины не пересобираются (готовые web/skin лежат в репозитории)" % ", ".join(miss))
        return 2
    sys.path.insert(0, JUI_TOOLS)
    import asda_jui_parse as jp
    skins = jp.parse_skins_full()
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):                      # пересборка с нуля (только свои png)
        if f.endswith(".png"):
            os.remove(os.path.join(OUT, f))
    atlas = Atlas(Image)
    meta, missing = {}, []
    for name in SKINS:
        s = skins.get(name)
        if not s:
            missing.append(name)
            continue
        frames, m = render_skin(name, s, atlas, Image)
        if not m:
            missing.append(name)
            continue
        for fi, im in frames:
            im.save(os.path.join(OUT, "%s%s.png" % (name, "" if fi == 0 else "." + str(fi))), optimize=True)
        meta[name] = m
    board, bmeta = render_board(jp, skins, atlas, Image)
    board.save(os.path.join(OUT, "inven_board.png"), optimize=True)
    meta["inven_board"] = bmeta
    with open(os.path.join(OUT, "skin.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1, sort_keys=True)
    print("скинов: %d, картинок: %d, не найдено: %s" % (len(meta), sum(len(m["frames"]) for m in meta.values()),
                                                         ", ".join(missing) or "—"))
    for n, m in meta.items():
        print("  %-28s %-13s %3dx%-3d slice=%s кадров=%d подпись=%s" % (n, m["type"], m["w"], m["h"], m["slice"],
                                                                       len(m["frames"]), m["caption"].get(0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
