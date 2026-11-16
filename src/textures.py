"""Procedural texture generation (numpy + pygame text) into a texture array."""
import math
import numpy as np
import pygame

SIZE = 256


class L:
    GRASS = 0
    BARK = 1
    CONCRETE = 2
    BRICK = 3
    WATER = 4
    METAL = 5
    PAPER = 6
    MUD = 7
    NEEDLES = 8
    FUR = 9
    BONE = 10
    SKIN = 11
    BLACK = 12
    WOOD = 13
    BLOOD = 14
    G_UNDER = 15
    G_DONTLOOK = 16
    G_ONEMORE = 17
    HAND = 18
    TALLY = 19
    SIGN = 20
    FLYER = 21
    GLOW = 22
    GRATE = 23
    LEAVES = 24
    MOON = 25
    CLOTH = 26
    REDCLOTH = 27
    WFUR = 28        # the Elk: matted white fur
    WFUR_B = 29      # ...and the same, soaked with blood
    COUNT = 30


EMIS = 100.0


def _noise(rng, cx, cy):
    g = rng.random((cy, cx))
    xs = np.arange(SIZE) * cx / SIZE
    x0 = np.floor(xs).astype(int)
    fx = xs - x0
    x1 = (x0 + 1) % cx
    ys = np.arange(SIZE) * cy / SIZE
    y0 = np.floor(ys).astype(int)
    fy = ys - y0
    y1 = (y0 + 1) % cy
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a = g[np.ix_(y0, x0)]
    b = g[np.ix_(y0, x1)]
    c = g[np.ix_(y1, x0)]
    d = g[np.ix_(y1, x1)]
    FX = fx[None, :]
    FY = fy[:, None]
    return (a * (1 - FX) + b * FX) * (1 - FY) + (c * (1 - FX) + d * FX) * FY


def fbm(rng, base=4, octaves=5, ax=1, ay=1):
    tot = np.zeros((SIZE, SIZE))
    amp = 1.0
    s = 0.0
    for o in range(octaves):
        cx = min(int(base * ax * 2 ** o), SIZE)
        cy = min(int(base * ay * 2 ** o), SIZE)
        tot += _noise(rng, max(cx, 1), max(cy, 1)) * amp
        s += amp
        amp *= 0.5
    return tot / s


def col(c, m):
    m = np.asarray(m)
    return np.stack([c[0] * m, c[1] * m, c[2] * m], -1)


def mix(a, b, t):
    t = np.asarray(t)[..., None]
    return a * (1 - t) + b * t


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def surf_rgba(surf):
    rgb = pygame.surfarray.array3d(surf).transpose(1, 0, 2).astype(np.float64) / 255.0
    a = pygame.surfarray.array_alpha(surf).T.astype(np.float64) / 255.0
    return rgb, a


def _font(names, size, bold=False):
    try:
        return pygame.font.SysFont(names, size, bold=bold)
    except Exception:
        return pygame.font.Font(None, size)


def graffiti(rng, lines, color, size=64):
    surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
    f = _font("impact,arialblack,arial", size, bold=False)
    total_h = len(lines) * f.get_linesize()
    y = (SIZE - total_h) // 2
    for ln in lines:
        img = f.render(ln, True, color)
        if img.get_width() > SIZE - 8:
            s = (SIZE - 8) / img.get_width()
            img = pygame.transform.smoothscale(img, (int(img.get_width() * s), int(img.get_height() * s)))
        surf.blit(img, ((SIZE - img.get_width()) // 2, y))
        y += f.get_linesize()
    rgb, a = surf_rgba(surf)
    # drips
    cols = np.where(a.max(axis=0) > 0.5)[0]
    for _ in range(40):
        if len(cols) == 0:
            break
        x = int(rng.choice(cols))
        ys = np.where(a[:, x] > 0.5)[0]
        if len(ys) == 0:
            continue
        y0 = ys.max()
        ln = int(rng.integers(6, 50))
        y1 = min(SIZE - 1, y0 + ln)
        a[y0:y1, x] = 1.0
        if x + 1 < SIZE:
            a[y0:y1 - 3, x + 1] = 1.0
        rgb[y0:y1, x] = np.array(color[:3]) / 255.0
        if x + 1 < SIZE:
            rgb[y0:y1, x + 1] = np.array(color[:3]) / 255.0
    n = fbm(rng, 8, 3)
    a = a * (n > 0.32)
    rgb = rgb * (0.7 + 0.5 * n[..., None])
    return rgb, a


def make_textures():
    rng = np.random.default_rng(1987)
    layers = [None] * L.COUNT
    ones = np.ones((SIZE, SIZE))
    yy, xx = np.mgrid[0:SIZE, 0:SIZE] / SIZE

    # GRASS / forest floor
    n1 = fbm(rng, 4, 6)
    n2 = fbm(rng, 8, 4)
    dirt = col((0.20, 0.16, 0.11), ones)
    moss = col((0.11, 0.14, 0.07), ones)
    g = mix(dirt, moss, smooth(0.4, 0.65, n2))
    g *= (0.55 + 0.8 * n1)[..., None]
    speck = rng.random((SIZE, SIZE)) > 0.985
    g[speck] = (0.30, 0.17, 0.07)
    layers[L.GRASS] = (g, ones)

    # BARK
    n = fbm(rng, 3, 5, ax=6, ay=1)
    n2 = fbm(rng, 4, 4)
    b = col((0.20, 0.16, 0.13), 0.45 + 0.9 * n)
    b *= (0.7 + 0.5 * n2)[..., None]
    cracks = np.abs(np.sin(xx * 40 + n2 * 9)) < 0.08
    b[cracks] *= 0.4
    layers[L.BARK] = (b, ones)

    # CONCRETE
    n = fbm(rng, 4, 6)
    n2 = fbm(rng, 2, 4)
    c = col((0.42, 0.41, 0.38), 0.7 + 0.45 * n)
    c *= (1 - 0.45 * smooth(0.55, 0.8, n2))[..., None]
    streak = fbm(rng, 2, 4, ax=8, ay=1)
    c *= (0.85 + 0.25 * streak)[..., None]
    for _ in range(4):
        x = rng.integers(0, SIZE)
        y = rng.integers(0, SIZE)
        for _ in range(140):
            c[y % SIZE, x % SIZE] *= 0.45
            x += rng.integers(-1, 2)
            y += rng.integers(0, 2)
    layers[L.CONCRETE] = (c, ones)

    # BRICK
    rows, colsn = 8, 4
    bh = SIZE // rows
    bw = SIZE // colsn
    br = np.zeros((SIZE, SIZE, 3))
    tints = rng.uniform(0.65, 1.15, (rows, colsn + 1))
    for r in range(rows):
        off = (bw // 2) if r % 2 else 0
        for cc in range(colsn + 1):
            x0 = cc * bw - off
            t = tints[r, cc]
            xa, xb = max(0, x0), min(SIZE, x0 + bw)
            if xb <= xa:
                continue
            br[r * bh:(r + 1) * bh, xa:xb] = np.array((0.30, 0.15, 0.10)) * t
    mortar = np.zeros((SIZE, SIZE), bool)
    for r in range(rows):
        mortar[r * bh:r * bh + 3, :] = True
        off = (bw // 2) if r % 2 else 0
        for cc in range(colsn + 1):
            x0 = cc * bw - off
            if 0 <= x0 < SIZE:
                mortar[r * bh:(r + 1) * bh, max(0, x0):min(SIZE, x0 + 3)] = True
    br[mortar] = (0.12, 0.11, 0.10)
    n = fbm(rng, 4, 6)
    grime = fbm(rng, 2, 5, ax=6, ay=1)
    br *= (0.6 + 0.6 * n)[..., None]
    br = mix(br, col((0.07, 0.09, 0.05), ones), smooth(0.5, 0.8, grime) * 0.8)
    layers[L.BRICK] = (br, ones)

    # WATER
    n = fbm(rng, 4, 5)
    w = col((0.05, 0.075, 0.05), 0.6 + 0.8 * n)
    layers[L.WATER] = (w, ones)

    # METAL (rusty)
    n = fbm(rng, 4, 6)
    n2 = fbm(rng, 6, 4)
    m = mix(col((0.16, 0.16, 0.16), ones), col((0.36, 0.16, 0.07), ones), smooth(0.35, 0.65, n2))
    m *= (0.6 + 0.6 * n)[..., None]
    layers[L.METAL] = (m, ones)

    # PAPER
    n = fbm(rng, 6, 4)
    p = col((0.80, 0.77, 0.66), 0.88 + 0.15 * n)
    stain = fbm(rng, 2, 4)
    p = mix(p, col((0.55, 0.45, 0.30), ones), smooth(0.6, 0.85, stain) * 0.6)
    # text lines
    for i in range(14):
        y = 30 + i * 15
        x1 = int(rng.integers(150, 230))
        p[y:y + 3, 26:x1] *= 0.45
    layers[L.PAPER] = (p, ones)

    # MUD / wet concrete floor
    n = fbm(rng, 4, 6)
    n2 = fbm(rng, 3, 4)
    md = col((0.16, 0.15, 0.12), 0.55 + 0.7 * n)
    md = mix(md, col((0.08, 0.11, 0.05), ones), smooth(0.55, 0.75, n2) * 0.8)
    layers[L.MUD] = (md, ones)

    # NEEDLES
    n = fbm(rng, 6, 5, ax=1, ay=4)
    nd = col((0.05, 0.09, 0.05), 0.4 + 1.0 * n)
    layers[L.NEEDLES] = (nd, ones)

    # FUR
    n = fbm(rng, 8, 4, ax=1, ay=8)
    n2 = fbm(rng, 3, 4)
    fr = col((0.11, 0.08, 0.055), 0.35 + 1.0 * n)
    fr *= (0.6 + 0.6 * n2)[..., None]
    layers[L.FUR] = (fr, ones)

    # BONE
    n = fbm(rng, 4, 6)
    n2 = fbm(rng, 3, 4)
    bn = col((0.80, 0.75, 0.62), 0.78 + 0.28 * n)
    bn = mix(bn, col((0.35, 0.25, 0.15), ones), smooth(0.6, 0.85, n2) * 0.7)
    cr = np.abs(np.sin(yy * 30 + n * 12)) < 0.04
    bn[cr] *= 0.5
    layers[L.BONE] = (bn, ones)

    # SKIN (herd)
    n = fbm(rng, 4, 6)
    n2 = fbm(rng, 3, 4)
    sk = col((0.50, 0.48, 0.42), 0.8 + 0.3 * n)
    sk = mix(sk, col((0.25, 0.18, 0.25), ones), smooth(0.6, 0.8, n2) * 0.7)
    layers[L.SKIN] = (sk, ones)

    # BLACK
    layers[L.BLACK] = (col((0.015, 0.012, 0.012), ones), ones)

    # WOOD planks
    n = fbm(rng, 2, 5, ax=1, ay=8)
    wd = col((0.30, 0.20, 0.12), 0.6 + 0.6 * n)
    for i in range(0, SIZE, 64):
        wd[:, i:i + 3] *= 0.3
    layers[L.WOOD] = (wd, ones)

    # BLOOD decal
    n = fbm(rng, 3, 5)
    n2 = fbm(rng, 8, 3, ax=1, ay=6)
    dist = np.hypot(xx - 0.5, yy - 0.5)
    a = ((n + 0.35 * (1 - dist * 2)) > 0.62).astype(float)
    a = np.maximum(a, ((n2 > 0.72) & (dist < 0.45)).astype(float))
    bl = col((0.22, 0.015, 0.01), 0.6 + 0.6 * n)
    layers[L.BLOOD] = (bl, a)

    # Graffiti
    layers[L.G_UNDER] = graffiti(rng, ["HE IS", "UNDER"], (150, 20, 15), 70)
    layers[L.G_DONTLOOK] = graffiti(rng, ["DONT", "LOOK AT", "HIM"], (170, 165, 150), 58)
    layers[L.G_ONEMORE] = graffiti(rng, ["ROOM FOR", "ONE", "MORE"], (140, 10, 10), 60)

    # HANDPRINT
    surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
    hc = (100, 10, 8, 255)
    pygame.draw.ellipse(surf, hc, (80, 120, 96, 100))
    fingers = [(70, 70, 22, 70), (100, 45, 22, 85), (128, 45, 22, 85), (154, 62, 22, 72), (52, 140, 22, 55)]
    for fx_ in fingers:
        pygame.draw.ellipse(surf, hc, fx_)
    for i in range(5):
        x = 90 + i * 16
        pygame.draw.line(surf, hc, (x, 200), (x + rng.integers(-3, 4), 200 + rng.integers(20, 55)), 4)
    rgb, a = surf_rgba(surf)
    a = a * (fbm(rng, 8, 3) > 0.3)
    layers[L.HAND] = (rgb, a)

    # TALLY marks
    surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
    tc = (25, 22, 20, 255)
    for gy in range(4):
        for gx in range(4):
            if gy * 4 + gx > 13:
                break
            bx = 14 + gx * 60
            by = 14 + gy * 60
            for i in range(4):
                pygame.draw.line(surf, tc, (bx + i * 10, by), (bx + i * 10 + rng.integers(-3, 4), by + 44), 3)
            pygame.draw.line(surf, tc, (bx - 4, by + 36), (bx + 40, by + 6), 3)
    layers[L.TALLY] = surf_rgba(surf)

    # SIGN
    surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
    surf.fill((215, 212, 200, 255))
    pygame.draw.rect(surf, (170, 20, 20), (0, 0, SIZE, 70))
    f1 = _font("arialblack,impact,arial", 52, True)
    f2 = _font("arial", 22, True)
    img = f1.render("DANGER", True, (240, 240, 235))
    surf.blit(img, ((SIZE - img.get_width()) // 2, 6))
    for i, t in enumerate(["NO ENTRY", "STORM OUTFALL #7", "HARLAN CO.", "PUBLIC WORKS"]):
        img = f2.render(t, True, (20, 20, 20))
        surf.blit(img, ((SIZE - img.get_width()) // 2, 86 + i * 34))
    pygame.draw.rect(surf, (20, 20, 20), (0, 0, SIZE, SIZE), 6)
    rgb, a = surf_rgba(surf)
    rust = fbm(rng, 4, 5)
    rgb = mix(rgb, col((0.35, 0.18, 0.08), ones), smooth(0.58, 0.8, rust))
    scratch = fbm(rng, 16, 2, ax=1, ay=4) > 0.8
    rgb[scratch] *= 0.5
    layers[L.SIGN] = (rgb, ones)

    # FLYER
    surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
    surf.fill((225, 222, 210, 255))
    f1 = _font("arialblack,impact,arial", 50, True)
    img = f1.render("MISSING", True, (15, 15, 15))
    surf.blit(img, ((SIZE - img.get_width()) // 2, 4))
    pygame.draw.rect(surf, (90, 90, 90), (68, 66, 120, 110))
    pygame.draw.ellipse(surf, (150, 150, 150), (98, 80, 60, 75))
    pygame.draw.ellipse(surf, (40, 40, 40), (110, 105, 10, 8))
    pygame.draw.ellipse(surf, (40, 40, 40), (136, 105, 10, 8))
    pygame.draw.line(surf, (60, 60, 60), (118, 135), (138, 135), 3)
    f2 = _font("arial", 20, True)
    img = f2.render("KYLE A. BRANDT  14", True, (15, 15, 15))
    surf.blit(img, ((SIZE - img.get_width()) // 2, 182))
    for i in range(3):
        pygame.draw.line(surf, (90, 90, 90), (30, 212 + i * 12), (226 - i * 30, 212 + i * 12), 3)
    rgb, a = surf_rgba(surf)
    wet = fbm(rng, 3, 4)
    rgb = mix(rgb, col((0.45, 0.40, 0.30), ones), smooth(0.55, 0.8, wet) * 0.7)
    layers[L.FLYER] = (rgb, ones)

    # GLOW
    layers[L.GLOW] = (col((1, 1, 1), ones), ones)

    # GRATE
    gx = (np.floor(xx * 16) % 2 == 0)
    g_a = ~((np.mod(xx * 16, 1) > 0.25) & (np.mod(yy * 16, 1) > 0.25))
    gr = col((0.2, 0.18, 0.16), 0.6 + 0.6 * fbm(rng, 4, 4))
    layers[L.GRATE] = (gr, g_a.astype(float))

    # LEAVES
    n = fbm(rng, 8, 4)
    lv = mix(col((0.06, 0.08, 0.04), ones), col((0.16, 0.10, 0.05), ones), smooth(0.4, 0.7, n))
    lv *= (0.5 + 0.8 * fbm(rng, 16, 3))[..., None]
    layers[L.LEAVES] = (lv, ones)

    # MOON
    d = np.hypot(xx - 0.5, yy - 0.5)
    n = fbm(rng, 4, 4)
    mn = col((0.85, 0.87, 0.92), 0.75 + 0.3 * n)
    layers[L.MOON] = (mn, (d < 0.45).astype(float))

    # CLOTH
    n = fbm(rng, 4, 5)
    weave = (np.sin(xx * SIZE * 1.5) * np.sin(yy * SIZE * 1.5) > 0) * 0.08
    cl = col((0.22, 0.23, 0.25), 0.6 + 0.6 * n + weave)
    stain = fbm(rng, 3, 4)
    cl = mix(cl, col((0.12, 0.08, 0.05), ones), smooth(0.55, 0.8, stain) * 0.8)
    layers[L.CLOTH] = (cl, ones)

    # RED CLOTH (hoodie)
    rc = col((0.42, 0.05, 0.05), 0.6 + 0.6 * n + weave)
    rc = mix(rc, col((0.12, 0.06, 0.04), ones), smooth(0.55, 0.8, stain) * 0.8)
    layers[L.REDCLOTH] = (rc, ones)

    # WHITE FUR (the Elk), from the brown fur's strand pattern
    fur = layers[L.FUR][0]
    lum = fur.mean(axis=2)
    lum = (lum - lum.min()) / (lum.max() - lum.min() + 1e-9)
    white = np.stack([0.58 + 0.42 * lum, 0.57 + 0.41 * lum, 0.54 + 0.38 * lum], -1) * 0.72
    grime = fbm(rng, 3, 4)
    white *= (1.0 - 0.25 * smooth(0.55, 0.8, grime))[..., None]
    layers[L.WFUR] = (white, ones)
    st = smooth(0.42, 0.62, fbm(rng, 4, 5))
    bloodied = white * (1 - st[..., None]) + np.array((0.42, 0.03, 0.02)) * st[..., None] * (0.6 + 0.6 * lum[..., None])
    layers[L.WFUR_B] = (bloodied, ones)

    out = np.zeros((L.COUNT, SIZE, SIZE, 4), np.uint8)
    for i, (rgb, a) in enumerate(layers):
        rgba = np.concatenate([np.clip(rgb, 0, 1), np.clip(a, 0, 1)[..., None]], -1)
        out[i] = (np.flipud(rgba) * 255).astype(np.uint8)
    return out
