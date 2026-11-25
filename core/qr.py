# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""qr.py — QR-код на стандартной библиотеке (для ссылки otpauth:// второго фактора). 16.11.2026.

ЗАЧЕМ. Владелец 16.11: вошёл, но «не может переключать вкладки» — разделы закрыты, пока владелец не включит второй фактор,
а включать его можно было только ручным вводом 32-символьного ключа. QR-код сканируется приложением-аутентификатором.
На сервере нет сторонних пакетов, поэтому кодировщик свой: ISO/IEC 18004, байтовый режим, уровень коррекции M,
версии 1–10 (до 213 байт — ссылке otpauth нужно ~120). Маска — по штрафам стандарта (правила N1–N4).
Проверка: tests/selftest.py сверяет матрицу бит в бит с пакетом qrcode (на ПК) для всех 8 масок и нескольких длин.
Побочных эффектов при импорте нет.
"""

# уровень M: (EC-кодовых слов на блок, [(блоков, данных в блоке), ...]) для версий 1..10
_EC_M = {
    1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]),
    6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]),
    10: (26, [(4, 43), (1, 44)]),
}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
          9: [6, 26, 46], 10: [6, 28, 50]}
_EC_BITS_M = 0            # биты уровня M в поле формата

# GF(256), порождающий многочлен 0x11D
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gmul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs(data, n):
    """n кодовых слов Рида — Соломона для data."""
    gen = [1]
    for i in range(n):
        nxt = [0] * (len(gen) + 1)
        for j, c in enumerate(gen):
            nxt[j] ^= c
            nxt[j + 1] ^= _gmul(c, _EXP[i])
        gen = nxt
    rem = list(data) + [0] * n
    for i in range(len(data)):
        f = rem[i]
        if f:
            for j, c in enumerate(gen):
                rem[i + j] ^= _gmul(c, f)
    return rem[len(data):]


def _bch(value, poly, bits):
    """Остаток BCH: value << bits по модулю poly."""
    d = value << bits
    plen = poly.bit_length()
    while d.bit_length() >= plen:
        d ^= poly << (d.bit_length() - plen)
    return (value << bits) | d


def _codewords(data, version):
    """Кодовые слова (данные + коррекция, перемешанные по блокам) для байтовых данных."""
    ec_n, groups = _EC_M[version]
    cap = sum(b * d for b, d in groups)
    bits = [0, 1, 0, 0]                                   # режим «байты»
    cnt = 8 if version < 10 else 16
    bits += [(len(data) >> i) & 1 for i in range(cnt - 1, -1, -1)]
    for b in data:
        bits += [(b >> i) & 1 for i in range(7, -1, -1)]
    if len(bits) > cap * 8:
        raise ValueError("не помещается")
    bits += [0] * min(4, cap * 8 - len(bits))             # завершитель
    bits += [0] * (-len(bits) % 8)
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = [0xEC, 0x11]
    while len(words) < cap:
        words.append(pad[(len(words) - len(bits) // 8) % 2])
    blocks, pos = [], 0
    for nb, nd in groups:
        for _ in range(nb):
            blocks.append(words[pos:pos + nd])
            pos += nd
    ecs = [_rs(b, ec_n) for b in blocks]
    out = []
    for i in range(max(len(b) for b in blocks)):
        out += [b[i] for b in blocks if i < len(b)]
    for i in range(ec_n):
        out += [e[i] for e in ecs]
    return out


_MASKS = [
    lambda i, j: (i + j) % 2 == 0, lambda i, j: i % 2 == 0, lambda i, j: j % 3 == 0, lambda i, j: (i + j) % 3 == 0,
    lambda i, j: (i // 2 + j // 3) % 2 == 0, lambda i, j: (i * j) % 2 + (i * j) % 3 == 0,
    lambda i, j: ((i * j) % 2 + (i * j) % 3) % 2 == 0, lambda i, j: ((i * j) % 3 + (i + j) % 2) % 2 == 0,
]


def _build(version, words, mask):
    """Матрица [строка][столбец] → True (тёмный) для данной маски."""
    n = version * 4 + 17
    m = [[None] * n for _ in range(n)]

    def finder(r, c):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                rr, cc = r + dr, c + dc
                if 0 <= rr < n and 0 <= cc < n:
                    m[rr][cc] = (0 <= dr <= 6 and dc in (0, 6)) or (0 <= dc <= 6 and dr in (0, 6)) or \
                                (2 <= dr <= 4 and 2 <= dc <= 4)
    finder(0, 0)
    finder(n - 7, 0)
    finder(0, n - 7)
    for r in _ALIGN[version]:
        for c in _ALIGN[version]:
            if m[r][c] is not None:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    m[r + dr][c + dc] = max(abs(dr), abs(dc)) != 1
    for i in range(8, n - 8):
        if m[6][i] is None:
            m[6][i] = i % 2 == 0
        if m[i][6] is None:
            m[i][6] = i % 2 == 0
    fmt = _bch((_EC_BITS_M << 3) | mask, 0x537, 10) ^ 0x5412
    for i in range(15):
        b = (fmt >> i) & 1 == 1
        if i < 6:
            m[i][8] = b
        elif i < 8:
            m[i + 1][8] = b
        else:
            m[n - 15 + i][8] = b
        if i < 8:
            m[8][n - i - 1] = b
        elif i < 9:
            m[8][15 - i] = b
        else:
            m[8][15 - i - 1] = b
    m[n - 8][8] = True
    if version >= 7:
        vb = _bch(version, 0x1F25, 12)
        for i in range(18):
            b = (vb >> i) & 1 == 1
            m[i // 3][i % 3 + n - 11] = b
            m[i % 3 + n - 11][i // 3] = b
    f = _MASKS[mask]
    inc, row, bit, byte = -1, n - 1, 7, 0
    col = n - 1
    while col > 0:
        if col == 6:
            col -= 1
        while True:
            for c in (col, col - 1):
                if m[row][c] is None:
                    dark = byte < len(words) and (words[byte] >> bit) & 1 == 1
                    m[row][c] = (not dark) if f(row, c) else dark
                    bit -= 1
                    if bit < 0:
                        byte, bit = byte + 1, 7
            row += inc
            if row < 0 or row >= n:
                row -= inc
                inc = -inc
                break
        col -= 2
    return m


def _penalty(m):
    """Штраф маски по правилам N1–N4 стандарта."""
    n = len(m)
    p = 0
    for lines in (m, list(zip(*m))):
        for line in lines:
            run = 1
            for i in range(1, n):
                if line[i] == line[i - 1]:
                    run += 1
                else:
                    if run >= 5:
                        p += run - 2
                    run = 1
            if run >= 5:
                p += run - 2
            s = "".join("1" if x else "0" for x in line)
            p += 40 * (s.count("10111010000") + s.count("00001011101"))
    for r in range(n - 1):
        for c in range(n - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                p += 3
    dark = sum(sum(1 for x in row if x) for row in m)
    p += 10 * (abs(dark * 100 // (n * n) - 50) // 5)
    return p


def matrix(text, mask=None, version=None):
    """QR для text (UTF-8, уровень M) → список строк '0'/'1' (без поля); mask/version — для проверки."""
    data = text.encode("utf-8")
    if version is None:
        version = next((v for v in range(1, 11)
                        if len(data) + (3 if v >= 10 else 2) <= sum(b * d for b, d in _EC_M[v][1])), None)
        if version is None:
            raise ValueError("слишком длинно для QR версии ≤10")
    words = _codewords(data, version)
    if mask is None:
        best = min(range(8), key=lambda k: _penalty(_build(version, words, k)))
        m = _build(version, words, best)
    else:
        m = _build(version, words, mask)
    return ["".join("1" if x else "0" for x in row) for row in m]
