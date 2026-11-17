"""Set dressing: small props that make the tunnels, mines, factory and woods feel lived in.

Everything here is visual (plus a few low collision boxes for the bigger props).
Props hug the walls, off the middle of each wall face, so they never cover a
valve or lever (those sit mid-face) or a key (cell centres). Ceiling dressing
(pipes, chains, roots, stalactites) is out of reach and blocks nothing.
"""
import math
import random

from engine import T, RX, RY, RZ, S, _tp
from textures import L, EMIS

SIDES = (('N', (0, 1)), ('S', (0, -1)), ('E', (1, 0)), ('W', (-1, 0)))


# ---------------------------------------------------------------------- the props
# Each draws in a local frame: origin on the floor, +z away from the wall into the room.
def barrel(b, m, rng, tint=None):
    col = tint or rng.choice(((0.45, 0.2, 0.12), (0.25, 0.32, 0.25), (0.35, 0.36, 0.4), (0.5, 0.4, 0.15)))
    b.cylinder(0.28, 0.28, 0.86, 10, L.METAL, col, m=m, cap=True)
    for y in (0.2, 0.62):
        b.cylinder(0.295, 0.295, 0.04, 10, L.METAL, (0.3, 0.28, 0.26), m=m @ T(0, y, 0))
    return 0.3


def drum_tipped(b, m, rng):
    mm = m @ T(0, 0.28, 0) @ RY(rng.uniform(-0.6, 0.6)) @ RZ(math.pi / 2) @ T(0, -0.43, 0)
    b.cylinder(0.28, 0.28, 0.86, 10, L.METAL, (0.4, 0.22, 0.12), m=mm, cap=True)
    return 0.45


def crates(b, m, rng):
    s = rng.uniform(0.5, 0.7)
    b.box((0, s / 2, 0), (s, s, s), L.WOOD, (0.8, 0.75, 0.7), m=m @ RY(rng.uniform(-0.2, 0.2)))
    if rng.random() < 0.6:
        s2 = s * rng.uniform(0.6, 0.85)
        b.box((rng.uniform(-0.1, 0.1), s + s2 / 2, 0), (s2, s2, s2), L.WOOD, (0.7, 0.66, 0.6), m=m @ RY(rng.uniform(-0.5, 0.5)))
    return s * 0.55


def sacks(b, m, rng):
    for k in range(rng.randint(2, 4)):
        mm = m @ T(rng.uniform(-0.25, 0.25), 0.12 + (0.18 if k == 3 else 0), rng.uniform(-0.1, 0.1)) @ RY(rng.random() * 3)
        b.box((0, 0, 0), (0.45, 0.24, 0.3), L.CLOTH, (0.62, 0.55, 0.42), m=mm)
        b.box((0, 0.13, 0), (0.36, 0.06, 0.22), L.CLOTH, (0.55, 0.5, 0.38), m=mm)
    return 0.0


def rubble(b, m, rng, layer=L.CONCRETE, col=(0.5, 0.47, 0.44)):
    for _ in range(rng.randint(4, 9)):
        s = rng.uniform(0.08, 0.3)
        mm = m @ T(rng.uniform(-0.45, 0.45), s * 0.3, rng.uniform(-0.25, 0.3)) @ RY(rng.random() * 6) @ RX(rng.uniform(-0.4, 0.4))
        b.box((0, 0, 0), (s * 1.3, s * 0.7, s), layer, col, m=mm)
    return 0.0


def trash(b, m, rng):
    for _ in range(rng.randint(1, 3)):
        mm = m @ T(rng.uniform(-0.3, 0.3), 0.18, rng.uniform(-0.1, 0.15)) @ RY(rng.random() * 6)
        b.cylinder(0.2, 0.12, 0.36, 7, L.BLACK, (1, 1, 1), m=mm @ T(0, -0.18, 0), cap=True)
        b.box((0, 0.2, 0), (0.05, 0.08, 0.05), L.BLACK, m=mm)
    if rng.random() < 0.5:
        b.box((0.1, 0.01, 0.25), (0.3, 0.012, 0.22), L.FLYER, (0.8, 0.8, 0.75), m=m @ RY(rng.random()))
    return 0.0


def pallet(b, m, rng, leaning=None):
    lean = rng.random() < 0.5 if leaning is None else leaning
    mm = m @ (T(0, 0.0, 0.18) @ RX(-1.35) if lean else T(0, 0.0, 0.1) @ RY(rng.uniform(-0.3, 0.3)))
    for k in range(5):
        b.box((-0.48 + k * 0.24, 0.13, 0), (0.18, 0.025, 0.85), L.WOOD, (0.85, 0.78, 0.6), m=mm)
    for sx in (-0.45, 0.0, 0.45):
        b.box((sx, 0.06, 0), (0.1, 0.1, 0.85), L.WOOD, (0.7, 0.62, 0.48), m=mm)
    return 0.0


def toolbox(b, m, rng):
    mm = m @ RY(rng.uniform(-0.4, 0.4))
    b.box((0, 0.1, 0), (0.45, 0.2, 0.22), L.METAL, (0.6, 0.12, 0.08), m=mm)
    b.box((0, 0.23, 0), (0.25, 0.03, 0.03), L.METAL, (0.2, 0.2, 0.2), m=mm)
    if rng.random() < 0.6:
        b.box((0.4, 0.015, 0.1), (0.3, 0.03, 0.04), L.METAL, (0.5, 0.5, 0.5), m=mm @ RY(0.7))      # a wrench
    return 0.0


def bucket(b, m, rng):
    b.cylinder(0.12, 0.16, 0.3, 9, L.METAL, (0.5, 0.5, 0.48), m=m)
    b.cylinder(0.14, 0.14, 0.012, 9, L.WATER, (0.4, 0.38, 0.3), m=m @ T(0, 0.22, 0), cap=True)
    return 0.0


def mine_props(b, m, rng):
    """A timber prop up the wall, a pick leaning on it, maybe an old lamp on a nail."""
    b.box((0, 1.6, -0.05), (0.18, 3.2, 0.18), L.WOOD, (0.65, 0.55, 0.42), m=m)
    if rng.random() < 0.6:
        mm = m @ T(0.35, 0, 0.1) @ RZ(-0.25)
        b.box((0, 0.45, 0), (0.04, 0.9, 0.04), L.WOOD, (0.6, 0.48, 0.35), m=mm)
        b.box((0, 0.9, 0), (0.42, 0.06, 0.05), L.METAL, (0.35, 0.33, 0.3), m=mm)
    if rng.random() < 0.4:
        b.box((0, 1.75, 0.12), (0.12, 0.18, 0.12), L.METAL, (0.25, 0.22, 0.18), m=m)
        b.box((0, 1.74, 0.12), (0.07, 0.1, 0.07), L.GLOW + EMIS, (0.35, 0.18, 0.06), m=m)   # cold, almost out
    return 0.0


def ore_heap(b, m, rng):
    rubble(b, m, rng, L.CONCRETE, (0.4, 0.36, 0.34))
    for _ in range(rng.randint(1, 3)):
        s = rng.uniform(0.05, 0.1)
        b.box((rng.uniform(-0.3, 0.3), s * 0.4, rng.uniform(-0.1, 0.2)), (s, s, s), L.METAL, (0.6, 0.5, 0.25), m=m)
    return 0.0


def bones_pile(b, m, rng):
    for _ in range(rng.randint(5, 11)):
        mm = m @ T(rng.uniform(-0.4, 0.4), 0.03, rng.uniform(-0.2, 0.3)) @ RY(rng.random() * 6) @ RZ(rng.uniform(-0.3, 0.3))
        b.box((0, 0, 0), (rng.uniform(0.15, 0.45), 0.045, 0.045), L.BONE, (0.88, 0.84, 0.78), m=mm)
    if rng.random() < 0.3:
        b.box((0, 0.09, 0.1), (0.18, 0.17, 0.22), L.BONE, (0.85, 0.8, 0.74), m=m @ RY(rng.random() * 6))
    return 0.0


def wall_pipes(b, m, rng, h, layer=L.METAL):
    """A pipe run up the wall with a valve wheel and brackets (vertical) -- tall, thin, harmless."""
    col = rng.choice(((0.42, 0.3, 0.22), (0.35, 0.38, 0.36), (0.5, 0.45, 0.3)))
    for k, dx in enumerate((-0.12, 0.12)[:rng.randint(1, 2)]):
        r = 0.06 + 0.02 * k
        b.cylinder(r, r, h, 8, layer, col, m=m @ T(dx, 0, 0.1))
        for y in (0.6, h * 0.5, h - 0.4):
            b.box((dx, y, 0.06), (0.2, 0.05, 0.1), L.METAL, (0.25, 0.24, 0.22), m=m)
    if rng.random() < 0.5:
        b.cylinder(0.14, 0.14, 0.03, 10, L.METAL, (0.55, 0.12, 0.08), m=m @ T(-0.12, 1.3, 0.22) @ RX(math.pi / 2))
    return 0.0


def wall_sign(b, m, rng, y=1.6):
    w, hh = rng.uniform(0.4, 0.7), rng.uniform(0.3, 0.45)
    b.box((0, y, 0.015), (w, hh, 0.02), L.SIGN, (0.85, 0.8, 0.7), m=m @ RZ(rng.uniform(-0.12, 0.12)))
    return 0.0


def fuse_box(b, m, rng):
    b.box((0, 1.4, 0.08), (0.42, 0.55, 0.16), L.METAL, (0.4, 0.42, 0.4), m=m)
    b.box((0.06, 1.4, 0.17), (0.3, 0.45, 0.02), L.METAL, (0.32, 0.34, 0.32), m=m @ RY(-0.3 if rng.random() < 0.4 else 0))
    b.box((0, 1.4 + 0.27 + 0.6, 0.05), (0.06, 1.2, 0.06), L.METAL, (0.3, 0.3, 0.3), m=m)        # conduit up
    return 0.0


def shelf_unit(b, m, rng):
    """A rusty shelf against the wall with junk on it."""
    for sx in (-0.55, 0.55):
        for sz in (-0.18, 0.18):
            b.box((sx, 0.9, sz), (0.05, 1.8, 0.05), L.METAL, (0.35, 0.3, 0.26), m=m @ T(0, 0, 0.22))
    for y in (0.15, 0.75, 1.35):
        b.box((0, y, 0.22), (1.15, 0.03, 0.42), L.METAL, (0.4, 0.36, 0.3), m=m)
        for _ in range(rng.randint(0, 3)):
            s = rng.uniform(0.1, 0.25)
            lay = rng.choice((L.WOOD, L.METAL, L.PAPER, L.CLOTH))
            b.box((rng.uniform(-0.45, 0.45), y + 0.015 + s / 2, 0.22), (s, s, s * 0.9), lay, (0.7, 0.65, 0.6), m=m @ RY(rng.uniform(-0.3, 0.3)))
    return 0.42


PROPS = {
    'barrel': barrel, 'drum': drum_tipped, 'crates': crates, 'sacks': sacks, 'rubble': rubble, 'trash': trash,
    'pallet': pallet, 'toolbox': toolbox, 'bucket': bucket, 'mine': mine_props, 'ore': ore_heap,
    'bones': bones_pile, 'shelf': shelf_unit,
}
# props with something to bump into: (half-depth from the wall, half-width)
SOLID = {'barrel': (0.3, 0.3), 'crates': (0.35, 0.35), 'shelf': (0.42, 0.6), 'drum': (0.3, 0.45)}

THEMES = {
    # floor props by weight, wall-mounted props by weight, how often a wall gets something
    'sewer': ({'trash': 4, 'rubble': 4, 'barrel': 2, 'crates': 2, 'bucket': 1, 'bones': 2, 'drum': 1},
              {'pipes': 5, 'sign': 1, 'fuse': 1}, 0.24),
    'mine': ({'mine': 5, 'ore': 3, 'crates': 3, 'sacks': 3, 'barrel': 2, 'bucket': 1, 'rubble': 3, 'toolbox': 1},
             {'sign': 1}, 0.22),
    'deep': ({'rubble': 5, 'trash': 3, 'barrel': 2, 'bones': 3, 'crates': 1, 'drum': 1},
             {'pipes': 4, 'fuse': 1, 'sign': 1}, 0.24),
    'factory': ({'barrel': 4, 'pallet': 4, 'crates': 3, 'shelf': 2, 'toolbox': 2, 'drum': 2, 'trash': 1, 'bucket': 1},
                {'pipes': 4, 'fuse': 3, 'sign': 2}, 0.32),
}


def _pick(rng, weights):
    tot = sum(weights.values())
    v = rng.random() * tot
    for k, w in weights.items():
        v -= w
        if v <= 0:
            return k
    return k


# ---------------------------------------------------------------------- dressing a grid
def dress_grid(b, cells, kind, center, floor_y, ceil_y, theme, seed, cell=2.0, boxes=None, skip=None):
    """Props along the walls of a grid map, plus a little on the ceiling.

    cells: (c, r) floor cells to consider; kind(c, r) -> '#' for rock; center(c, r) -> (x, z);
    floor_y / ceil_y (c, r) -> heights; boxes: list to append solid (x0, z0, x1, z1) to;
    skip(c, r) -> True to leave a cell bare (puzzle machinery, doors, cutscene spots).
    """
    rng = random.Random(seed)
    floor_w, wall_w, rate = THEMES[theme]
    hw = cell / 2
    n_props = 0
    for (c, r) in cells:
        if skip and skip(c, r):
            continue
        x, z = center(c, r)
        fy = floor_y(c, r)
        ce = ceil_y(c, r)
        for side, (dc, dr) in SIDES:
            if kind(c + dc, r + dr) != '#':
                continue
            if rng.random() > rate:
                continue
            # only dress corridors wide enough to keep a clear way past (the cell across must be open)
            wide = kind(c - dc, r - dr) != '#'
            n = (-dc, -dr)                                  # into the room, away from the wall
            yaw = math.atan2(n[0], n[1])
            along = rng.choice((-0.55, 0.55))
            tx, tz = -n[1], n[0]
            if rng.random() < 0.35 and wall_w:
                what = _pick(rng, wall_w)
                px, pz = x - n[0] * (hw - 0.02) + tx * along, z - n[1] * (hw - 0.02) + tz * along
                m = T(px, fy, pz) @ RY(yaw)
                if what == 'pipes':
                    wall_pipes(b, m, rng, max(1.0, ce - fy))
                elif what == 'sign':
                    wall_sign(b, m, rng, y=min(1.6, ce - fy - 0.4))
                elif what == 'fuse' and ce - fy > 2.3:
                    fuse_box(b, m, rng)
                n_props += 1
                continue
            if not wide:
                continue
            what = _pick(rng, floor_w)
            if what == 'mine' and ce - fy < 3.3:
                what = 'crates'
            depth = 0.35
            px, pz = x - n[0] * (hw - depth) + tx * along, z - n[1] * (hw - depth) + tz * along
            m = T(px, fy, pz) @ RY(yaw)
            PROPS[what](b, m, rng)
            n_props += 1
            if boxes is not None and what in SOLID:
                hd, hwid = SOLID[what]
                ax = abs(n[0]) * hd + abs(tx) * hwid
                az = abs(n[1]) * hd + abs(tz) * hwid
                boxes.append((px - ax, pz - az, px + ax, pz + az))
        # the ceiling: never in anyone's way
        if ce - fy > 2.6 and rng.random() < rate * 0.6:
            hang(b, x + rng.uniform(-0.5, 0.5), ce, z + rng.uniform(-0.5, 0.5), fy, theme, rng)
            n_props += 1
    return n_props


def hang(b, x, ce, z, fy, theme, rng):
    if theme == 'mine':
        # stalactites and roots
        for _ in range(rng.randint(1, 4)):
            ln = rng.uniform(0.3, min(1.4, (ce - fy) * 0.3))
            r = rng.uniform(0.05, 0.14)
            b.cylinder(r, 0.0, ln, 6, L.CONCRETE, (0.55, 0.5, 0.46),
                       m=T(x + rng.uniform(-0.6, 0.6), ce + 0.02, z + rng.uniform(-0.6, 0.6)) @ RX(math.pi))
        return
    if theme in ('factory', 'deep') and rng.random() < 0.6:
        # a chain hanging down, maybe a hook on the end
        ln = rng.uniform(0.8, min(2.4, ce - fy - 2.1))
        if ln <= 0.3:
            return
        k = 0
        y = ce
        while y > ce - ln:
            b.box((x, y - 0.06, z), (0.025, 0.12, 0.07) if k % 2 else (0.07, 0.12, 0.025), L.METAL, (0.3, 0.28, 0.26))
            y -= 0.1
            k += 1
        if rng.random() < 0.5:
            b.box((x, y - 0.1, z + 0.03), (0.03, 0.2, 0.03), L.METAL, (0.35, 0.3, 0.25))
            b.box((x, y - 0.2, z + 0.08), (0.03, 0.03, 0.12), L.METAL, (0.35, 0.3, 0.25))
        return
    # a pipe under the ceiling
    ln = rng.uniform(1.4, 2.0)
    a = rng.choice((0.0, math.pi / 2))
    m = T(x, ce - 0.2, z) @ RY(a) @ RZ(math.pi / 2) @ T(0, -ln / 2, 0)
    b.cylinder(0.09, 0.09, ln, 8, L.METAL, (0.38, 0.32, 0.26), m=m)
    b.box((0, ce - 0.1, 0), (0.04, 0.2, 0.04), L.METAL, (0.25, 0.24, 0.22), m=T(x, 0, z))


def dress_level(lv, b, theme, seed, skip=None):
    """dress_grid for the mine / deep sewer / factory levels (chapter3.Level and its children)."""
    cells = [(c, r) for r in range(lv.rows) for c in range(lv.cols) if lv.g[r][c] == '.']
    return dress_grid(b, cells, lv.kind, lv.center, lambda c, r: lv.y0, lambda c, r: float(lv.ceil[r, c]),
                      theme, seed, boxes=lv.boxes, skip=skip)


# ---------------------------------------------------------------------- the woods
def forest_floor(b, spots, ground, rng, snow=False):
    """Stumps, mushrooms, ferns, fallen branches and leaf piles at the given (x, z) spots."""
    for (x, z) in spots:
        h = ground(x, z)
        if h is None:
            continue
        roll = rng.random()
        m = T(x, h, z) @ RY(rng.random() * 6.28)
        if roll < 0.18:
            # a stump with an axe cut
            r = rng.uniform(0.18, 0.32)
            ht = rng.uniform(0.25, 0.55)
            b.cylinder(r * 1.25, r, ht, 8, L.BARK, (0.7, 0.66, 0.6), m=m @ T(0, -0.05, 0))
            b.cylinder(r * 0.98, r * 0.98, 0.012, 8, L.WOOD, (0.9, 0.78, 0.6), m=m @ T(0, ht - 0.05, 0), cap=True)
            for k in range(3):
                a = k * 2.1 + rng.random()
                b.box((math.cos(a) * r * 1.2, 0.04, math.sin(a) * r * 1.2), (r * 1.1, 0.08, 0.08), L.BARK, (0.6, 0.55, 0.5),
                      m=m @ RY(-a))
        elif roll < 0.38 and not snow:
            # a cluster of pale mushrooms
            for _ in range(rng.randint(3, 7)):
                mx, mz = rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3)
                st = rng.uniform(0.04, 0.12)
                cap = rng.uniform(0.03, 0.07)
                b.cylinder(0.012, 0.012, st, 5, L.BONE, (0.9, 0.86, 0.78), m=m @ T(mx, 0, mz))
                b.cylinder(cap, 0.005, cap * 0.7, 7, L.SKIN, rng.choice(((0.85, 0.78, 0.65), (0.6, 0.3, 0.2), (0.9, 0.9, 0.85))),
                           m=m @ T(mx, st, mz), cap=True)
        elif roll < 0.62:
            # fallen branches
            for _ in range(rng.randint(1, 3)):
                ln = rng.uniform(0.6, 1.6)
                mm = m @ T(rng.uniform(-0.4, 0.4), 0.04, rng.uniform(-0.4, 0.4)) @ RY(rng.random() * 6) @ RZ(math.pi / 2) @ T(0, -ln / 2, 0)
                b.cylinder(0.035, 0.02, ln, 5, L.BARK, (0.6, 0.55, 0.5), m=mm)
                if rng.random() < 0.6:
                    b.cylinder(0.02, 0.01, ln * 0.4, 4, L.BARK, (0.6, 0.55, 0.5), m=mm @ T(0, ln * 0.5, 0) @ RZ(0.7))
        elif roll < 0.82 and not snow:
            # a fern: fronds fanning out from the middle
            col = (0.35, 0.45, 0.22) if rng.random() < 0.7 else (0.5, 0.38, 0.18)
            for k in range(rng.randint(5, 8)):
                a = k * 1.1 + rng.random() * 0.5
                ln = rng.uniform(0.35, 0.6)
                mm = m @ RY(a) @ RX(-(1.05 + rng.uniform(-0.15, 0.15)))
                pts = [_tp(mm, q) for q in ((-0.07, 0, 0), (0.07, 0, 0), (0.02, ln, 0), (-0.02, ln, 0))]
                b.quad(*pts, L.LEAVES, col)
                b.quad(pts[1], pts[0], pts[3], pts[2], L.LEAVES, col)
        else:
            # a heap of dead leaves / a rock with moss
            if snow or rng.random() < 0.5:
                s = rng.uniform(0.25, 0.6)
                b.box((0, s * 0.2, 0), (s * 1.4, s * 0.6, s), L.CONCRETE, (0.5, 0.5, 0.48), m=m @ RX(rng.uniform(-0.2, 0.2)))
                b.box((0, s * 0.51, 0), (s * 1.0, 0.03, s * 0.7), L.GRASS, (0.5, 0.7, 0.4) if not snow else (1.9, 1.95, 2.1), m=m)
            else:
                b.cylinder(0.6, 0.15, 0.14, 8, L.LEAVES, (0.55, 0.38, 0.2), m=m @ S(1.0, 1.0, rng.uniform(0.6, 1.0)), cap=True)

