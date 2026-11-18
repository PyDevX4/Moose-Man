"""The drop shaft: a huge brick room in the sewers, three storeys tall, with pipes
pouring water down into it and tunnels going off at the bottom.

Chapter One crosses it high up, on a catwalk with a section fallen out (you lay a
plank over the gap). Chapter Four comes in at the bottom of the same shaft, and
the plank is still up there.

Everything here is in world coordinates; the callers say where the shaft is.
"""
import math
import random

from engine import MeshBuilder, T, RX, RY, RZ
from textures import L, EMIS

PLANK_LEN = 6.8
CAT_HALF = 0.62          # half the catwalk's width (the railings stand just outside it)


def plank_mesh():
    """The long plank: along local +x, centred, lying flat (top at y = 0.07)."""
    b = MeshBuilder()
    b.box((0, 0.035, 0), (PLANK_LEN, 0.07, 0.36), L.WOOD, (0.72, 0.6, 0.45))
    for x in (-2.6, -0.4, 1.9):
        b.box((x, 0.072, 0), (0.05, 0.01, 0.34), L.WOOD, (0.45, 0.36, 0.26))      # old paint marks
    return b.array()


def catwalk(b, x0, x1, y, zc, gx0, gx1, top):
    """A grated catwalk along x from wall to wall at height y, with the section gx0..gx1 fallen out.
    Hanger rods go up to the roof (top)."""
    metal = (0.42, 0.4, 0.38)
    rust = (0.5, 0.33, 0.22)
    for a, c in ((x0, gx0), (gx1, x1)):
        ln = c - a
        mid = (a + c) / 2
        b.box((mid, y - 0.03, zc), (ln, 0.06, CAT_HALF * 2), L.GRATE, (0.7, 0.68, 0.64))
        for sz in (-1, 1):
            b.box((mid, y - 0.12, zc + sz * CAT_HALF), (ln, 0.22, 0.08), L.METAL, metal)       # side beams
            b.box((mid, y + 1.02, zc + sz * (CAT_HALF + 0.04)), (ln, 0.06, 0.06), L.METAL, metal)   # handrail
            b.box((mid, y + 0.52, zc + sz * (CAT_HALF + 0.04)), (ln, 0.04, 0.04), L.METAL, metal)   # knee rail
        x = a + 0.05
        while x <= c:
            for sz in (-1, 1):
                b.box((x, y + 0.5, zc + sz * (CAT_HALF + 0.04)), (0.06, 1.05, 0.06), L.METAL, metal)
            x += 1.5
        # hangers up to the roof
        x = a + 1.0
        while x < c - 0.5:
            for sz in (-1, 1):
                b.box((x, (y + top) / 2, zc + sz * (CAT_HALF + 0.1)), (0.04, top - y, 0.04), L.METAL, rust)
            x += 4.0
    # the broken ends: bent grating hanging down into the dark, a snapped rail
    for edge, s in ((gx0, 1), (gx1, -1)):
        m = T(edge, y - 0.05, zc) @ RZ(-s * 1.0)
        b.box((s * 0.55, 0, 0.1), (1.1, 0.05, CAT_HALF * 1.6), L.GRATE, (0.6, 0.55, 0.5), m=m)
        b.box((s * 0.4, 0, -CAT_HALF), (0.8, 0.18, 0.07), L.METAL, rust, m=m)
        m2 = T(edge, y + 1.02, zc + CAT_HALF + 0.04) @ RZ(-s * 0.6)
        b.box((s * 0.35, 0, 0), (0.7, 0.06, 0.06), L.METAL, rust, m=m2)
        b.box((edge + s * 0.06, y - 0.12, zc), (0.12, 0.24, CAT_HALF * 2 + 0.1), L.METAL, rust)


def opening(b, cx, cz, y, w, h, normal, deep=0.0):
    """A black tunnel mouth on a wall, with a concrete frame. normal points into the room."""
    nx, nz = normal
    px, pz = cx + nx * 0.03, cz + nz * 0.03
    b.facing_quad((px, y + h / 2, pz), (nx, 0, nz), w, h, L.BLACK, (0, 0, 0))
    fx, fz = -nz, nx          # along the wall
    col = (0.45, 0.44, 0.42)
    for s in (-1, 1):
        b.box((cx + fx * s * (w / 2 + 0.12) + nx * 0.1, y + h / 2, cz + fz * s * (w / 2 + 0.12) + nz * 0.1),
              (0.24 if fx else 0.2, h, 0.2 if fx else 0.24), L.CONCRETE, col)
    b.box((cx + nx * 0.1, y + h + 0.12, cz + nz * 0.1), (w + 0.5 if fx else 0.2, 0.24, 0.2 if fx else w + 0.5), L.CONCRETE, col)
    if deep:
        # a lip to stand on: a ledge sticking out under it
        b.box((cx + nx * deep / 2, y - 0.1, cz + nz * deep / 2), (w + 0.6 if fx else deep, 0.2, deep if fx else w + 0.6),
              L.CONCRETE, col)


def outfall(b, cx, cz, y, normal, bottom, rad=0.55, flow=True):
    """A big pipe sticking out of the wall, pouring water down to `bottom`."""
    nx, nz = normal
    yaw = math.atan2(nx, nz)
    m = T(cx, y, cz) @ RY(yaw) @ RX(math.pi / 2)
    b.cylinder(rad, rad, 0.9, 12, L.CONCRETE, (0.4, 0.4, 0.38), m=m)
    b.cylinder(rad * 0.8, rad * 0.8, 0.92, 12, L.BLACK, (0, 0, 0), m=m)
    b.facing_quad((cx + nx * 0.02, y - 2.0, cz + nz * 0.02), (nx, 0, nz), rad * 2.4, 3.6, L.MUD, (0.3, 0.27, 0.22))
    if flow:
        top = y - rad * 0.5
        h = top - bottom
        for k in range(3):
            off = 0.85 + k * 0.05
            b.facing_quad((cx + nx * off, bottom + h / 2, cz + nz * off), (nx, 0, nz), rad * (1.3 - 0.25 * k), h,
                          L.WATER, (0.75, 0.8, 0.85))


def dress(b, x0, z0, x1, z1, floor_y, top, cat_y, zc, gx0, gx1, entrances, rng, plank=False):
    """Pipes, waterfalls, tunnel mouths and a pool at the bottom.
    entrances: [(side, along)] -- real ways in at catwalk height (no fake openings drawn there).
    Returns [(x, y, z, kind)] light positions: 'cat' up by the catwalk, 'low' down at the bottom."""
    lights = []
    catwalk(b, x0, x1, cat_y, zc, gx0, gx1, top)
    if plank:
        # the plank you laid over the gap, still there
        b.add_array(_plank_at((gx0 + gx1) / 2, cat_y + 0.0, zc))
    # the pool at the bottom, and its foam where the water lands
    b.quad_world((x0, floor_y + 0.35, z0), (x1, floor_y + 0.35, z0), (x1, floor_y + 0.35, z1), (x0, floor_y + 0.35, z1),
                 L.WATER, (0.55, 0.62, 0.6), 0.3)
    # outfalls high on the long walls, pouring down
    w = x1 - x0
    d = z1 - z0
    for (cx, cz, nrm, y) in ((x0 + w * 0.22, z1, (0, -1), cat_y + 3.2), (x0 + w * 0.7, z1, (0, -1), cat_y - 4.5),
                             (x0 + w * 0.45, z0, (0, 1), cat_y + 1.5), (x0 + w * 0.85, z0, (0, 1), cat_y - 9.0),
                             (x0, z0 + d * 0.25, (1, 0), cat_y - 2.5), (x1, z0 + d * 0.78, (-1, 0), cat_y + 2.2)):
        outfall(b, cx, cz, y, nrm, floor_y + 0.35, rad=rng.uniform(0.45, 0.75))
    # vertical pipes running the full height of the walls
    for k in range(9):
        side = rng.randrange(4)
        if side < 2:
            x = rng.uniform(x0 + 1, x1 - 1)
            z = z0 + 0.3 if side == 0 else z1 - 0.3
        else:
            z = rng.uniform(z0 + 1, z1 - 1)
            x = x0 + 0.3 if side == 2 else x1 - 0.3
        if abs(z - zc) < 2.0:
            continue
        r_ = rng.uniform(0.12, 0.3)
        b.cylinder(r_, r_, top - floor_y, 8, L.METAL, (0.38, 0.36, 0.33), m=T(x, floor_y, z))
        y = floor_y + 2.0
        while y < top:
            b.cylinder(r_ + 0.05, r_ + 0.05, 0.12, 8, L.METAL, (0.3, 0.28, 0.26), m=T(x, y, z))
            y += 3.0
    # tunnels at the bottom
    lows = [((x0 + x1) / 2 - w * 0.2, z1, (0, -1)), ((x0 + x1) / 2 + w * 0.25, z0, (0, 1)),
            (x1, z0 + d * 0.3, (-1, 0)), (x0, z0 + d * 0.7, (1, 0))]
    for (cx, cz, nrm) in lows:
        opening(b, cx, cz, floor_y + 0.35, 2.6, 3.0, nrm)
        lights.append((cx + nrm[0] * 2.0, floor_y + 2.8, cz + nrm[1] * 2.0, 'low'))
    # more ways in higher up, on ledges: nobody has been along them in years
    for (cx, cz, nrm, y) in ((x0 + w * 0.35, z0, (0, 1), cat_y + 0.0), (x0 + w * 0.6, z1, (0, -1), cat_y - 6.0),
                             (x1, z0 + d * 0.2, (-1, 0), cat_y - 11.0)):
        opening(b, cx, cz, y, 2.0, 2.6, nrm, deep=1.2)
    # a red stencil on the wall by the catwalk
    b.facing_quad((x0 + 0.04, cat_y + 2.2, zc - 2.2), (1, 0, 0), 1.6, 0.5, L.SIGN, (0.8, 0.3, 0.2))
    lights.append(((gx0 + gx1) / 2, cat_y + 3.4, zc, 'cat'))
    lights.append((x0 + 3.0, cat_y + 2.6, zc, 'cat'))
    lights.append((x1 - 3.0, cat_y + 2.6, zc, 'cat'))
    return lights


def _plank_at(x, y, z):
    import numpy as np
    arr = np.array(plank_mesh(), np.float32).reshape(-1, 12).copy()
    arr[:, 0] += x
    arr[:, 1] += y
    arr[:, 2] += z
    return arr
