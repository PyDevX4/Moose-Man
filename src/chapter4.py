"""Chapter 4: the deep sewer.

The Moose Man smashes you both through the floor of the old overflow system
into a far bigger one underneath. Three backup generators power the first big
gate; behind it is a huge hall, the side sewers around it, five fuses, and a
second gate, even bigger.

Cells are 2 m. Kinds:
  '#' wall        '.' tunnel / chamber / the hall (he fits)
  ',' overflow pipe (low and narrow: he is too big now to follow you in)
  'G' the first gate     'H' the second, bigger gate     'X' the dark past it
"""
import math
import random

from engine import T, S, RX, RY, RZ, MeshBuilder
from textures import L, EMIS
import chapter3 as C3

C = C3.C

HALL = (9, 20, 36, 36)
LANDING = (18, 2, 25, 7)
HOLE = (20, 3, 23, 6)           # where the floor of the sewer above came through
ROOMS6 = [(2, 2, 7, 9), (36, 2, 41, 9), (34, 12, 40, 17), (2, 20, 6, 24), (2, 34, 7, 39),
          (39, 21, 44, 26), (38, 33, 45, 38), (10, 39, 16, 43)]
ANTE = (16, 14, 27, 17)
# the first section, made bigger: the bottom of the drop shaft from Chapter One, and rooms past it
SHAFT4 = (48, 1, 59, 12)
SHAFT4_TOP = 26.0           # above the floor
SHAFT4_CAT = 20.0           # where the catwalk crosses, way up
SHAFT4_CAT_ROW = 6
SHAFT4_GAP = (53, 55)
BOILER = (64, 4, 70, 12)
NORTH4 = (50, 18, 57, 23)
GATE1_H = 6.5
GATE2_H = 11.0


def inside(rect, c, r):
    c0, r0, c1, r1 = rect
    return c0 <= c <= c1 and r0 <= r <= r1


class SewerLevel(C3.Level):
    """The chapter 3 grid level, re-dressed as a sewer, with two gates."""

    def __init__(self):
        super().__init__(72, 46, -47.0, 0.0, -30.0, seed=4404)
        self.gates = {'G': {'open': 0.0, 'opening': False}, 'H': {'open': 0.0, 'opening': False}}
        self.generators = []      # dicts: pos, yaw, running, progress, fuel, base, lamp (placed per game)
        self.gen_spots = []       # where they can go
        self.jug_spots = []       # where the gas can can be
        self.jug = None           # the gas can: dict pos, taken
        self.fuses = []           # dicts: pos, taken
        self.fusebox = None       # dict: pos, yaw
        self.water = []           # (x0, z0, x1, z1) shallow water you splash through
        self.seed_cell = None
        self._reach = None
        self.build_grid()

    # ---------------------------------------------------------------- layout
    def build_grid(self):
        cv = self.carve
        # where you land, and the generator tunnels around it
        cv(*LANDING, '.')
        cv(8, 4, 17, 5, '.')                 # west tunnel
        cv(2, 2, 7, 9, '.')                  # west chamber (generator 1)
        cv(26, 4, 35, 5, '.')                # east tunnel
        cv(36, 2, 41, 9, '.')                # east chamber (generator 2)
        cv(21, 8, 22, 13, '.')               # north tunnel
        cv(*ANTE, '.')                       # the antechamber in front of the first gate
        cv(28, 15, 33, 15, '.')
        cv(34, 12, 40, 17, '.')              # pump room (generator 3)
        cv(38, 10, 38, 11, '.')              # pump room <-> east chamber
        # overflow pipes only you fit through
        cv(5, 10, 5, 15, ',')
        cv(6, 15, 15, 15, ',')
        cv(26, 7, 35, 7, ',')
        cv(23, 10, 25, 11, ',')              # a maintenance crawlspace off the north tunnel
        # the first gate
        cv(20, 18, 23, 19, 'G')
        # the hall
        cv(*HALL, '.')
        for c in (13, 18, 27, 32):
            for r in (24, 28, 32):
                self.g[r][c] = '#'           # columns holding the roof up
        # the second gate, and the dark behind it
        cv(20, 37, 25, 38, 'H')
        cv(20, 39, 25, 44, 'X')
        # the side sewers around the hall, where the fuses are
        cv(2, 20, 6, 24, '.')
        cv(7, 22, 8, 23, '.')
        cv(4, 25, 4, 33, ',')
        cv(2, 34, 7, 39, '.')
        cv(8, 35, 8, 36, '.')
        cv(39, 21, 44, 26, '.')
        cv(37, 23, 38, 24, '.')
        cv(41, 27, 42, 32, '.')
        cv(38, 33, 45, 38, '.')
        cv(37, 34, 37, 34, ',')
        cv(10, 39, 16, 43, '.')
        cv(12, 37, 13, 38, '.')
        cv(29, 37, 32, 38, ',')              # a crawlspace off the hall
        # the first section goes on east, past the east chamber: the drop shaft, and more
        cv(42, 6, 47, 6, '.')
        cv(*SHAFT4, '.')
        cv(60, 9, 63, 9, '.')
        cv(*BOILER, '.')                      # the old boiler room
        cv(53, 13, 53, 17, '.')
        cv(*NORTH4, '.')                      # a settling room
        cv(66, 13, 66, 16, ',')
        cv(62, 17, 67, 22, '.')               # the pump gallery
        cv(58, 20, 61, 20, ',')
        # three times as much sewer, grown around it; the two gates still split it into sections
        keep = {(c, r) for r in range(0, 12) for c in range(16, 27)} | {(c, r) for r in range(14, 21) for c in range(17, 27)}             | {(c, r) for r in range(35, 46) for c in range(18, 28)}
        keep |= {(c, r) for r in range(0, 14) for c in range(47, 61)}
        self.grow_map(9, 30, seed=4142, barrier='GH', keep_out=keep, corridor_kinds='...,')
        self.finish()
        self.spawn = self.center(21, 4)
        self.safe = self.center(24, 10)      # section 1 respawn: the crawlspace
        self.safe_hall = self.center(31, 38)
        self.gate1_front = self.center(21, 16)

    def finish(self):
        import numpy as np
        self.ceil = np.zeros((self.rows, self.cols))
        y0 = self.y0
        for r in range(self.rows):
            for c in range(self.cols):
                k = self.g[r][c]
                if k == '.':
                    if inside(HALL, c, r):
                        h = 15.0 + 0.6 * math.sin(c * 0.5) * math.cos(r * 0.4)
                    elif inside(SHAFT4, c, r):
                        h = SHAFT4_TOP
                    elif inside(BOILER, c, r) or inside(NORTH4, c, r):
                        h = 6.0
                    elif inside(LANDING, c, r):
                        h = 9.0
                    elif inside(ANTE, c, r):
                        h = 8.0
                    elif any(inside(R, c, r) for R in ROOMS6):
                        h = 6.0
                    else:
                        h = 4.8
                elif k == ',':
                    h = 2.2
                elif k == 'G':
                    h = GATE1_H
                elif k in 'HX':
                    h = GATE2_H
                else:
                    h = 2.5
                self.ceil[r, c] = y0 + h

    # ---------------------------------------------------------------- rules
    def open_cell(self, c, r, elk=False):
        k = self.kind(c, r)
        if k == '#':
            return False
        if k in 'GH':
            return self.gates[k]['open'] > 0.7
        if elk and k not in '.GH':
            return False
        return True

    def cell_blocked(self, c, r, elk):
        return not self.open_cell(c, r, elk)

    def reset_reach(self):
        self._reach = None

    def elk_cells(self):
        """Cells he can get to from where he is (the gates cut the map in pieces)."""
        if self._reach is None or self._reach[0] != self.seed_cell:
            out = []
            seed = self.seed_cell
            if seed is not None and self.open_cell(*seed, elk=True):
                seen = {seed}
                q = [seed]
                while q:
                    cur = q.pop()
                    if self.kind(*cur) == '.':
                        out.append(cur)
                    for dc, dr in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                        nb = (cur[0] + dc, cur[1] + dr)
                        if nb not in seen and self.open_cell(*nb, elk=True):
                            seen.add(nb)
                            q.append(nb)
            if not out:
                out = [(c, r) for r in range(self.rows) for c in range(self.cols) if self.g[r][c] == '.']
            self._reach = (seed, out)
        return self._reach[1]

    def in_water(self, x, z):
        for x0, z0, x1, z1 in self.water:
            if x0 <= x <= x1 and z0 <= z <= z1:
                return True
        return False

    # ---------------------------------------------------------------- geometry
    def build_mesh(self, b):
        y0 = self.y0
        for r in range(self.rows):
            for c in range(self.cols):
                k = self.g[r][c]
                if k == '#':
                    continue
                x0 = self.ox + c * C
                z0 = self.oz + r * C
                x1, z1 = x0 + C, z0 + C
                ce = float(self.ceil[r, c])
                pipe = k == ','
                hall = inside(HALL, c, r)
                floor_l = L.CONCRETE if (hall or k in 'GHX') else L.MUD
                b.quad_world((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), floor_l,
                             (0.55, 0.55, 0.52) if hall else (0.75, 0.74, 0.7), 0.5)
                if not inside(HOLE, c, r):
                    b.quad_world((x0, ce, z0), (x1, ce, z0), (x1, ce, z1), (x0, ce, z1), L.CONCRETE,
                                 (0.4, 0.4, 0.4), 0.4)
                wall_l = L.CONCRETE if pipe else L.BRICK
                wcol = (0.6, 0.6, 0.58) if pipe else ((0.6, 0.55, 0.5) if hall else (0.85, 0.8, 0.75))
                for dc, dr, side in ((0, -1, 'S'), (0, 1, 'N'), (-1, 0, 'W'), (1, 0, 'E')):
                    nc, nr = c + dc, r + dr
                    if side == 'S':
                        e = ((x0, z0), (x1, z0))
                    elif side == 'N':
                        e = ((x1, z1), (x0, z1))
                    elif side == 'W':
                        e = ((x0, z1), (x0, z0))
                    else:
                        e = ((x1, z0), (x1, z1))
                    (ax, az), (bx, bz) = e
                    axis = 'x' if side in 'EW' else 'z'
                    nk = self.kind(nc, nr)
                    if nk == '#':
                        b.quad_world((ax, y0, az), (bx, y0, bz), (bx, ce, bz), (ax, ce, az), wall_l, wcol, 0.5, axis=axis)
                        # a stained band of old waterline along the bottom of the brick
                        if not pipe:
                            ox_, oz_ = {'S': (0, 0.012), 'N': (0, -0.012), 'W': (0.012, 0), 'E': (-0.012, 0)}[side]
                            b.quad_world((ax + ox_, y0, az + oz_), (bx + ox_, y0, bz + oz_), (bx + ox_, y0 + 0.9, bz + oz_),
                                         (ax + ox_, y0 + 0.9, az + oz_), L.MUD, (0.5, 0.45, 0.38), 0.5, axis=axis)
                    else:
                        nce = float(self.ceil[nr, nc])
                        if nce > ce + 0.01:
                            b.quad_world((ax, ce, az), (bx, ce, bz), (bx, nce, bz), (ax, nce, az), wall_l, wcol, 0.5, axis=axis)
                if pipe:
                    self._pipe_ribs(b, c, r, x0, z0, ce)

    def _pipe_ribs(self, b, c, r, x0, z0, ce):
        """Concrete ring joints and a trickle of black water down the middle."""
        y0 = self.y0
        d = self._run_dir(c, r)
        cx, cz = x0 + C / 2, z0 + C / 2
        col = (0.5, 0.5, 0.48)
        if d == 'z':
            for sx in (-0.92, 0.92):
                b.box((cx + sx, (y0 + ce) / 2, cz), (0.16, ce - y0, 0.22), L.CONCRETE, col)
            b.box((cx, ce - 0.08, cz), (2.0, 0.16, 0.22), L.CONCRETE, col)
            b.quad_world((cx - 0.3, y0 + 0.015, z0), (cx + 0.3, y0 + 0.015, z0), (cx + 0.3, y0 + 0.015, z0 + C),
                         (cx - 0.3, y0 + 0.015, z0 + C), L.WATER, (0.6, 0.6, 0.55), 0.5)
        else:
            for sz in (-0.92, 0.92):
                b.box((cx, (y0 + ce) / 2, cz + sz), (0.22, ce - y0, 0.16), L.CONCRETE, col)
            b.box((cx, ce - 0.08, cz), (0.22, 0.16, 2.0), L.CONCRETE, col)
            b.quad_world((x0, y0 + 0.015, cz - 0.3), (x0 + C, y0 + 0.015, cz - 0.3), (x0 + C, y0 + 0.015, cz + 0.3),
                         (x0, y0 + 0.015, cz + 0.3), L.WATER, (0.6, 0.6, 0.55), 0.5)

    def lamp(self, b, x, y, z, ce, gen, rad=10.0, col=(1.0, 0.62, 0.3)):
        """A caged work lamp on a cable, lit by generator `gen` (None: always, 'hall': the hall circuit)."""
        b.box((x, (y + ce) / 2, z), (0.025, ce - y, 0.025), L.BLACK)
        b.box((x, y + 0.08, z), (0.18, 0.06, 0.18), L.METAL)
        self.bulbs.append((x, y - 0.02, z, gen))
        self.lights.append({'pos': (x, y - 0.2, z), 'rad': rad, 'col': col, 'gen': gen})

    def place_generator(self, gen, c, r, side):
        """Stand a generator against the wall at (c, r, side)."""
        p, n = self.wall_point(c, r, side, self.y0, off=0.75)
        yaw = math.atan2(n[0], n[2])
        handle = (p[0] + math.sin(yaw) * 0.56 - math.cos(yaw) * 0.3, self.y0 + 0.75, p[2] + math.cos(yaw) * 0.56 + math.sin(yaw) * 0.3)
        lamp = (p[0] + math.sin(yaw) * 0.47 + math.cos(yaw) * 0.55, self.y0 + 1.15, p[2] + math.cos(yaw) * 0.47 - math.sin(yaw) * 0.55)
        gen.update(pos=handle, base=p, yaw=yaw, lamp=lamp, box=(p[0] - 0.85, p[2] - 0.85, p[0] + 0.85, p[2] + 0.85))
        return gen

    def add_generator(self, b, c, r, side):
        p, n = self.wall_point(c, r, side, self.y0, off=0.75)
        yaw = math.atan2(n[0], n[2])
        m = T(*p) @ RY(yaw)
        b.box((0, 0.12, 0), (1.7, 0.24, 1.1), L.METAL, (0.3, 0.3, 0.28), m=m)          # skid
        b.box((0, 0.75, 0), (1.5, 1.0, 0.9), L.METAL, (0.55, 0.5, 0.22), m=m)          # yellow housing
        b.box((0, 1.33, 0), (1.3, 0.16, 0.7), L.METAL, (0.35, 0.33, 0.3), m=m)
        b.box((-0.45, 1.5, -0.1), (0.5, 0.25, 0.45), L.METAL, (0.5, 0.15, 0.1), m=m)    # fuel tank
        b.cylinder(0.06, 0.06, 2.6, 8, L.METAL, (0.3, 0.3, 0.3), m=m @ T(0.55, 1.2, -0.3))  # exhaust up the wall
        b.box((0.3, 0.9, 0.46), (0.4, 0.3, 0.03), L.SIGN, (0.9, 0.85, 0.75), m=m)       # stencilled panel
        b.box((-0.3, 0.75, 0.47), (0.08, 0.08, 0.06), L.BLACK, m=m)                    # cord housing
        bx0, bz0 = p[0] - 0.85, p[2] - 0.85
        self.boxes.append((bx0, bz0, p[0] + 0.85, p[2] + 0.85))
        handle = (p[0] + math.sin(yaw) * 0.56 - math.cos(yaw) * 0.3, self.y0 + 0.75, p[2] + math.cos(yaw) * 0.56 + math.sin(yaw) * 0.3)
        lamp = (p[0] + math.sin(yaw) * 0.47 + math.cos(yaw) * 0.55, self.y0 + 1.15, p[2] + math.cos(yaw) * 0.47 - math.sin(yaw) * 0.55)
        self.generators.append({'pos': handle, 'base': p, 'yaw': yaw, 'running': False, 'progress': 0.0, 'lamp': lamp})

    def add_fuse(self, c, r, dx=0.0, dz=0.0, y=None):
        x, z = self.center(c, r)
        self.fuses.append({'pos': (x + dx, (self.y0 + 0.05) if y is None else y, z + dz), 'taken': False,
                           'yaw': self.rng.random() * 6})


def generator_mesh():
    """A backup generator in its own frame (front toward +z), sitting on the floor."""
    b = MeshBuilder()
    b.box((0, 0.12, 0), (1.7, 0.24, 1.1), L.METAL, (0.3, 0.3, 0.28))          # skid
    b.box((0, 0.75, 0), (1.5, 1.0, 0.9), L.METAL, (0.55, 0.5, 0.22))          # yellow housing
    b.box((0, 1.33, 0), (1.3, 0.16, 0.7), L.METAL, (0.35, 0.33, 0.3))
    b.box((-0.45, 1.5, -0.1), (0.5, 0.25, 0.45), L.METAL, (0.5, 0.15, 0.1))    # fuel tank
    b.cylinder(0.06, 0.06, 0.05, 8, L.METAL, (0.2, 0.2, 0.2), m=T(-0.45, 1.62, -0.1))   # its cap
    b.cylinder(0.06, 0.06, 2.6, 8, L.METAL, (0.3, 0.3, 0.3), m=T(0.55, 1.2, -0.3))  # exhaust
    b.box((0.3, 0.9, 0.46), (0.4, 0.3, 0.03), L.SIGN, (0.9, 0.85, 0.75))       # stencilled panel
    b.box((-0.3, 0.75, 0.47), (0.08, 0.08, 0.06), L.BLACK)                    # cord housing
    return b.array()


def jug_mesh():
    """A red jerry can of gasoline."""
    b = MeshBuilder()
    b.box((0, 0.22, 0), (0.18, 0.44, 0.34), L.METAL, (0.7, 0.1, 0.07))
    b.box((0, 0.47, -0.05), (0.06, 0.05, 0.2), L.METAL, (0.25, 0.25, 0.25))   # handle
    b.cylinder(0.035, 0.035, 0.1, 8, L.METAL, (0.75, 0.65, 0.2), m=T(0, 0.43, 0.12) @ RX(0.5))
    return b.array()


# ---------------------------------------------------------------------- dressing
def build():
    lv = SewerLevel()
    b = MeshBuilder()
    dress(lv, b)
    decorate(lv, b)
    return lv, b.array()


def decorate(lv, b):
    """Junk, pipes and chains, kept off the landing (the fall), the gates and the generators."""
    import decor
    busy = list(lv.boxes)
    keep = {(s[0], s[1]) for s in lv.gen_spots} | set(lv.jug_spots)

    def skip(c, r):
        if any((c + dc, r + dr) in keep for dc in (-1, 0, 1) for dr in (-1, 0, 1)):
            return True
        if inside(LANDING, c, r) or inside(ANTE, c, r):
            return True
        if any(lv.kind(c + dc, r + dr) in 'GHX' for dc in (-2, -1, 0, 1, 2) for dr in (-2, -1, 0, 1, 2)):
            return True
        x, z = lv.center(c, r)
        return any(bx0 - 1.6 < x < bx1 + 1.6 and bz0 - 1.6 < z < bz1 + 1.6 for bx0, bz0, bx1, bz1 in busy)

    decor.dress_level(lv, b, 'deep', 6401, skip=skip)


def dress(lv, b):
    rng = lv.rng
    lv.build_mesh(b)
    grng = random.Random(4243)
    for (c0, r0, c1, r1, _k) in getattr(lv, 'grown', ()):
        if grng.random() < 0.35:
            x, z = lv.center((c0 + c1) // 2, (r0 + r1) // 2)
            lv.lights.append({'pos': (x, lv.y0 + 3.6, z), 'rad': 9.0, 'col': grng.choice(((0.9, 0.55, 0.3), (0.45, 0.55, 0.5))),
                              'gen': None})
    y0 = lv.y0
    # ---- the landing: a mound of broken floor slabs under the hole
    hx0, hz0 = lv.ox + HOLE[0] * C, lv.oz + HOLE[1] * C
    hx1, hz1 = lv.ox + (HOLE[2] + 1) * C, lv.oz + (HOLE[3] + 1) * C
    ce = y0 + 9.0
    for _ in range(46):
        x, z = rng.uniform(hx0 - 1.5, hx1 + 1.5), rng.uniform(hz0 - 1.0, hz1 + 1.0)
        s = rng.uniform(0.4, 1.6)
        m = T(x, y0 + rng.uniform(0.0, 0.25), z) @ RY(rng.random() * 6) @ RX(rng.uniform(-0.6, 0.6)) @ RZ(rng.uniform(-0.6, 0.6))
        b.box((0, s * 0.15, 0), (s, s * 0.3, s * rng.uniform(0.5, 1.0)), L.CONCRETE, (0.6, 0.58, 0.55), m=m)
        if rng.random() < 0.4:
            # rebar sticking out of the slab
            b.box((0, s * 0.4, 0), (0.03, s * 0.9, 0.03), L.METAL, (0.45, 0.3, 0.22), m=m @ RZ(rng.uniform(-0.8, 0.8)))
    # the jagged edge of the hole, and the shaft of the old floor above
    for i in range(18):
        a = i / 18 * 2 * math.pi
        cx, cz = (hx0 + hx1) / 2, (hz0 + hz1) / 2
        x, z = cx + math.cos(a) * 4.4, cz + math.sin(a) * 4.4
        b.box((x, ce - 0.2, z), (rng.uniform(0.8, 1.8), rng.uniform(0.3, 0.9), rng.uniform(0.8, 1.6)), L.CONCRETE,
              (0.5, 0.48, 0.45), m=None)
    for side in ((hx0, hz0, hx1, hz0), (hx1, hz0, hx1, hz1), (hx1, hz1, hx0, hz1), (hx0, hz1, hx0, hz0)):
        ax, az, bx, bz = side
        b.quad_world((ax, ce, az), (bx, ce, bz), (bx, ce + 14, bz), (ax, ce + 14, az), L.CONCRETE, (0.35, 0.34, 0.33), 0.5,
                     axis='x' if ax == bx else 'z')
    lv.lights.append({'pos': ((hx0 + hx1) / 2, ce - 1.5, (hz0 + hz1) / 2), 'rad': 14.0, 'col': (0.3, 0.32, 0.38), 'gen': None})
    # ---- a sludge channel down the middle of the hall, and puddles
    hx_0, hz_0 = lv.ox + HALL[0] * C, lv.oz + 27 * C
    hx_1, hz_1 = lv.ox + (HALL[2] + 1) * C, lv.oz + 30 * C
    b.quad_world((hx_0, y0 + 0.03, hz_0), (hx_1, y0 + 0.03, hz_0), (hx_1, y0 + 0.03, hz_1), (hx_0, y0 + 0.03, hz_1),
                 L.WATER, (0.55, 0.6, 0.5), 0.3)
    lv.water.append((hx_0, hz_0, hx_1, hz_1))
    for (c0, r0, c1, r1) in ((8, 4, 17, 5), (26, 4, 35, 5), (21, 8, 22, 13), (41, 27, 42, 32)):
        x0, z0 = lv.ox + c0 * C, lv.oz + r0 * C
        x1, z1 = lv.ox + (c1 + 1) * C, lv.oz + (r1 + 1) * C
        if c1 - c0 > r1 - r0:
            z0, z1 = (z0 + z1) / 2 - 0.9, (z0 + z1) / 2 + 0.9
        else:
            x0, x1 = (x0 + x1) / 2 - 0.9, (x0 + x1) / 2 + 0.9
        b.quad_world((x0, y0 + 0.03, z0), (x1, y0 + 0.03, z0), (x1, y0 + 0.03, z1), (x0, y0 + 0.03, z1), L.WATER, (0.6, 0.62, 0.55), 0.4)
        lv.water.append((x0, z0, x1, z1))
    # ---- the hall's columns: capitals and bases, and outfall pipes high on the walls
    for c in (13, 18, 27, 32):
        for r in (24, 28, 32):
            x, z = lv.center(c, r)
            b.box((x, y0 + 0.4, z), (2.5, 0.8, 2.5), L.CONCRETE, (0.5, 0.48, 0.45))
            b.box((x, y0 + 14.0, z), (2.7, 1.2, 2.7), L.CONCRETE, (0.45, 0.43, 0.4))
            b.box((x, y0 + 7.0, z), (2.08, 0.6, 2.08), L.MUD, (0.5, 0.45, 0.38))       # flood line
    for zc in (22, 26, 30, 34):
        for xw, nx in ((lv.ox + HALL[0] * C + 0.2, 1), (lv.ox + (HALL[2] + 1) * C - 0.2, -1)):
            z = lv.oz + zc * C
            b.cylinder(0.9, 0.9, 0.6, 12, L.CONCRETE, (0.35, 0.35, 0.33), m=T(xw, y0 + 9.0, z) @ RZ(math.pi / 2 * nx))
            b.cylinder(0.7, 0.7, 0.62, 12, L.BLACK, m=T(xw, y0 + 9.0, z) @ RZ(math.pi / 2 * nx))
            # black streaks running down from them
            b.facing_quad((xw + nx * 0.05, y0 + 4.6, z), (nx, 0, 0), 1.0, 8.5, L.MUD, (0.25, 0.22, 0.18))
    # ---- the first gate: a frame of riveted girders
    _gate_frame(b, lv, 20, 23, 19, GATE1_H, 0.7)
    _gate_frame(b, lv, 20, 25, 38, GATE2_H, 1.1)
    # the dark beyond the second gate: nothing but a draught, and something painted on the wall
    ex, ez = lv.center(22, 43)
    b.facing_quad((ex + 1.0, y0 + 3.0, lv.oz + 45 * C - 0.05), (0, 0, -1), 5.0, 2.6, L.G_DONTLOOK, (0.7, 0.2, 0.15))
    # ---- generators and their lamps
    # (the three generators are placed per game: see pick_spots and extras.randomize_puzzles)
    lv.generators = [{'running': False, 'progress': 0.0, 'fuel': False, 'fill': 0.0} for _ in range(3)]
    for gi, cells in enumerate((((4, 3), (4, 8), (12, 4), (16, 5)),
                                ((38, 3), (38, 8), (30, 4), (27, 5)),
                                ((36, 14), (31, 15), (38, 11), (21, 11)))):
        for (c, r) in cells:
            x, z = lv.center(c, r)
            lv.lamp(b, x, float(lv.ceil[r, c]) - 1.2, z, float(lv.ceil[r, c]), gi, rad=10.0)
    # the landing and the antechamber light up once everything is running
    for (c, r) in ((19, 3), (24, 6), (18, 15), (25, 15), (21, 17), (22, 9)):
        x, z = lv.center(c, r)
        lv.lamp(b, x, float(lv.ceil[r, c]) - 1.6, z, float(lv.ceil[r, c]), 'all', rad=11.0)
    # the hall: big sodium lamps, dark until the gate opens
    for (c, r) in ((11, 22), (22, 22), (34, 22), (15, 30), (23, 26), (30, 30), (11, 35), (22, 34), (34, 35),
                   (4, 22), (5, 37), (42, 23), (41, 36), (13, 41), (41, 30)):
        x, z = lv.center(c, r)
        top = float(lv.ceil[r, c])
        lv.lamp(b, x, top - (6.0 if inside(HALL, c, r) else 1.5), z, top, 'hall',
                rad=16.0 if inside(HALL, c, r) else 10.0, col=(1.0, 0.55, 0.22))
    # a few red emergency lamps that never went out
    for (c, r) in ((18, 7), (2, 9), (41, 2), (27, 14)):
        x, z = lv.center(c, r)
        lv.lamp(b, x, float(lv.ceil[r, c]) - 0.6, z, float(lv.ceil[r, c]), None, rad=6.0, col=(0.6, 0.05, 0.03))
    # ---- the fuse box beside the second gate
    p, n = lv.wall_point(18, 36, 'N', y0 + 1.5, off=0.12)
    yaw = math.atan2(n[0], n[2])
    m = T(*p) @ RY(yaw)
    b.box((0, 0, -0.06), (1.3, 1.4, 0.14), L.METAL, (0.4, 0.42, 0.4), m=m)
    b.box((0, 0.82, -0.04), (1.35, 0.14, 0.12), L.METAL, (0.85, 0.7, 0.2), m=m)
    b.box((0, -0.55, 0.02), (1.1, 0.12, 0.04), L.SIGN, (0.9, 0.85, 0.75), m=m)
    for k in range(5):
        b.box((-0.44 + k * 0.22, 0.05, 0.02), (0.12, 0.6, 0.04), L.BLACK, m=m)
    b.box((0.55, 3.0, -0.08), (0.08, 3.6, 0.08), L.BLACK, m=m)               # conduit up toward the gate motors
    lv.fusebox = {'pos': p, 'yaw': yaw, 'n': n}
    # ---- five fuses, out in the side sewers
    lv.add_fuse(3, 21, 0.3, 0.2)            # west room
    lv.add_fuse(6, 38, 0.2, 0.5)            # northwest room
    lv.add_fuse(44, 25, -0.3, 0.0)          # east room
    lv.add_fuse(44, 37, -0.4, 0.3)          # northeast room
    lv.add_fuse(11, 43, 0.4, -0.4)          # north room, past the hall
    # each fuse sits on something: a crate, a shelf, a dead man's hand
    for f in lv.fuses:
        x, _, z = f['pos']
        b.box((x, y0 + 0.4, z), (0.8, 0.8, 0.8), L.WOOD, (0.6, 0.55, 0.45))
        lv.boxes.append((x - 0.4, z - 0.4, x + 0.4, z + 0.4))
        f['pos'] = (x, y0 + 0.86, z)
    # ---- clutter: bones, the herd's leftovers, old crates, a few cleaning carts
    for _ in range(40):
        c, r = rng.choice([(rng.randint(9, 36), rng.randint(20, 36)), (rng.randint(18, 25), rng.randint(2, 7)),
                           (rng.randint(2, 7), rng.randint(34, 39))])
        if lv.kind(c, r) != '.':
            continue
        x, z = lv.center(c, r)
        m = T(x + rng.uniform(-0.8, 0.8), y0 + 0.04, z + rng.uniform(-0.8, 0.8)) @ RY(rng.random() * 6)
        b.box((0, 0, 0), (rng.uniform(0.2, 0.55), 0.05, 0.05), L.BONE, (0.85, 0.8, 0.72), m=m)
    for (c, r) in ((3, 3), (40, 8), (35, 13), (16, 14), (27, 17), (10, 21), (35, 21), (3, 36), (44, 34), (15, 42)):
        x, z = lv.center(c, r)
        b.box((x, y0 + 0.45, z), (0.9, 0.9, 0.9), L.WOOD, (0.55, 0.5, 0.42))
        lv.boxes.append((x - 0.45, z - 0.45, x + 0.45, z + 0.45))
    # scratched into the brick: a tally, and the old graffiti
    _dress_shaft(lv, b)
    pick_spots(lv)
    for (c, r, side, layer) in ((7, 6, 'E', L.TALLY), (36, 8, 'W', L.G_UNDER), (16, 16, 'W', L.G_ONEMORE),
                                (9, 30, 'W', L.HAND), (36, 26, 'E', L.TALLY), (22, 12, 'E', L.G_DONTLOOK)):
        p, n = lv.wall_point(c, r, side, y0 + 1.7, off=0.02)
        b.facing_quad(p, n, 1.6, 1.2, layer, (0.9, 0.85, 0.8))


def _dress_shaft(lv, b):
    """The bottom of the drop shaft. Way up there: the catwalk from Chapter One, and your plank."""
    import shaft
    y0 = lv.y0
    c0, r0, c1, r1 = SHAFT4
    x0, z0 = lv.ox + c0 * C, lv.oz + r0 * C
    x1, z1 = lv.ox + (c1 + 1) * C, lv.oz + (r1 + 1) * C
    zc = lv.center(0, SHAFT4_CAT_ROW)[1]
    gx0, gx1 = lv.ox + SHAFT4_GAP[0] * C, lv.ox + (SHAFT4_GAP[1] + 1) * C
    lights = shaft.dress(b, x0, z0, x1, z1, y0, y0 + SHAFT4_TOP, y0 + SHAFT4_CAT, zc, gx0, gx1, (),
                         random.Random(5859), plank=True)
    for (x, y, z, kind) in lights:
        if kind == 'cat':
            lv.lamp(b, x, y, z, y0 + SHAFT4_TOP, None, rad=20.0, col=(0.75, 0.8, 0.95))
        else:
            lv.lights.append({'pos': (x, y, z), 'rad': 10.0, 'col': (0.6, 0.22, 0.12), 'gen': None})
    lv.water.append((x0, z0, x1, z1))


def pick_spots(lv):
    """Where the generators and the gas can may go, each game: anywhere in the first section."""
    from gridgrow import zones_of
    z = zones_of(lv.g, '.,', 'GH')
    sec = z.get((21, 4))
    rng = random.Random(4545)

    def busy(x, zz, m=1.6):
        return any(bx0 - m < x < bx1 + m and bz0 - m < zz < bz1 + m for bx0, bz0, bx1, bz1 in lv.boxes)

    def bad(c, r):
        return (z.get((c, r)) != sec or inside(LANDING, c, r) or inside(ANTE, c, r) or inside(SHAFT4, c, r)
                or any(lv.kind(c + dc, r + dr) in 'GH' for dc in (-2, -1, 0, 1, 2) for dr in (-2, -1, 0, 1, 2)))
    gens = []
    for (c, r, side) in lv.wall_spots('.'):
        if bad(c, r):
            continue
        dc, dr = {'N': (0, 1), 'S': (0, -1), 'E': (1, 0), 'W': (-1, 0)}[side]
        if lv.kind(c - dc, r - dr) == '#' or busy(*lv.center(c, r)):
            continue
        gens.append((c, r, side))
    rng.shuffle(gens)
    for s in gens:
        x, zz = lv.center(s[0], s[1])
        if all(math.hypot(x - lv.center(o[0], o[1])[0], zz - lv.center(o[0], o[1])[1]) > 9 for o in lv.gen_spots):
            lv.gen_spots.append(s)
        if len(lv.gen_spots) >= 14:
            break
    cells = [(c, r) for r in range(lv.rows) for c in range(lv.cols)
             if lv.g[r][c] == '.' and not bad(c, r) and not busy(*lv.center(c, r), m=1.0)
             and all(lv.kind(c + dc, r + dr) != '#' for dc in (-1, 0, 1) for dr in (-1, 0, 1))]
    rng.shuffle(cells)
    for cell in cells:
        x, zz = lv.center(*cell)
        if all(math.hypot(x - lv.center(*o)[0], zz - lv.center(*o)[1]) > 10 for o in lv.jug_spots):
            lv.jug_spots.append(cell)
        if len(lv.jug_spots) >= 10:
            break


def _gate_frame(b, lv, c0, c1, r, h, thick):
    """Girders around a gate opening on the north edge of row r."""
    y0 = lv.y0
    x0 = lv.ox + c0 * C
    x1 = lv.ox + (c1 + 1) * C
    z = lv.oz + r * C
    col = (0.45, 0.38, 0.32)
    for x in (x0 + thick / 2, x1 - thick / 2):
        b.box((x, y0 + h / 2, z), (thick, h, thick * 1.4), L.METAL, col)
    b.box(((x0 + x1) / 2, y0 + h - thick / 2, z), (x1 - x0, thick, thick * 1.4), L.METAL, col)
    # yellow and black hazard paint on the posts
    for x in (x0 + thick / 2, x1 - thick / 2):
        for k in range(4):
            b.box((x, y0 + 0.3 + k * 0.6, z), (thick + 0.02, 0.28, thick * 1.4 + 0.02), L.METAL, (0.85, 0.7, 0.15))


def gate_z(lv, which):
    return lv.oz + (19 if which == 'G' else 38) * C


def gate_span(lv, which):
    c0, c1 = (20, 23) if which == 'G' else (20, 25)
    return lv.ox + c0 * C, lv.ox + (c1 + 1) * C


# ---------------------------------------------------------------------- dynamic meshes
def gate_mesh(width, height, heavy):
    b = MeshBuilder()
    bar = 0.18 if heavy else 0.11
    step = 0.42 if heavy else 0.34
    n = int(width / step)
    col = (0.42, 0.36, 0.3)
    for i in range(n + 1):
        x = -width / 2 + i * width / n
        b.box((x, height / 2, 0), (bar, height, bar), L.METAL, col)
        b.box((x, -0.15, 0), (bar * 0.7, 0.3, bar * 0.7), L.METAL, (0.55, 0.5, 0.45))   # spikes along the bottom
    for k in range(int(height / 1.4) + 1):
        b.box((0, 0.25 + k * 1.4, 0), (width, 0.16 if heavy else 0.1, 0.12 if heavy else 0.08), L.METAL, col)
    if heavy:
        # riveted plate over the bottom third
        b.box((0, height * 0.17, -0.05), (width, height * 0.34, 0.06), L.METAL, (0.35, 0.33, 0.3))
        for k in range(10):
            b.box((-width / 2 + 0.6 + k * (width - 1.2) / 9, height * 0.3, -0.09), (0.12, 0.12, 0.04), L.METAL, (0.6, 0.58, 0.55))
        b.box((0, height * 0.17, -0.09), (width * 0.4, 0.5, 0.02), L.SIGN, (0.9, 0.85, 0.7))
    return b.array()


def fuse_mesh():
    b = MeshBuilder()
    b.cylinder(0.05, 0.05, 0.22, 10, L.BONE, (0.95, 0.92, 0.85), m=RZ(math.pi / 2) @ T(0, -0.11, 0))
    for sx in (-0.13, 0.13):
        b.cylinder(0.06, 0.06, 0.05, 10, L.METAL, (1.0, 0.65, 0.35), m=T(sx, 0, 0) @ RZ(math.pi / 2) @ T(0, -0.025, 0))
    b.box((0, 0.052, 0), (0.08, 0.01, 0.05), L.SIGN, (0.9, 0.3, 0.2))
    return b.array()


def cord_mesh():
    b = MeshBuilder()
    b.box((0, 0, 0.05), (0.14, 0.04, 0.04), L.BLACK)
    return b.array()


# ---------------------------------------------------------------------- the Moose Man, hunting
class MooseHunter(C3.ElkHunter):
    """The Moose Man after the change. Hunts light and movement like the
    others, faster, and too big now for the overflow pipes -- hide in one
    and he tears at the opening, then stands there breathing, then goes."""
    # a light from far off; moving in the dark from not quite as far; dark and
    # still he can't see you -- unless he's close, and then you run. He moves
    # at your walking pace.
    LIGHT_RANGE = 34.0
    RUN_RANGE = 26.0
    WALK_RANGE = 18.0
    CREEP_RANGE = 8.0
    STILL_RANGE = 0.0
    CLOSE_RANGE = 3.5
    CHASE_SPEED = 2.7
    SPEEDS = {'enter': 2.4, 'investigate': 2.4, 'leave': 2.0, 'roam': 1.8}
    KILL_DIST = 2.0

    def __init__(self, lv, x, z):
        super().__init__(lv, x, z)
        self.smash_t = 9.0          # time since he last hit something
        self.smashes = 0
        self.prev_state = 'roam'

    def update(self, dt, player, lantern_on):
        lv = self.lv
        lv.seed_cell = lv.cell_of(self.x, self.z)
        if not lv.open_cell(*lv.seed_cell, elk=True):
            lv.seed_cell = lv.nearest_elk_cell(*lv.seed_cell)
        super().update(dt, player, lantern_on)
        self.smash_t += dt
        if self.state == 'search' and self.prev_state != 'search':
            self.smashes = 0
        hidden = not lv.open_cell(*lv.cell_of(player.x, player.z), elk=True)
        d = math.hypot(player.x - self.x, player.z - self.z)
        if self.state == 'search' and hidden and d < 5.0 and self.timer < 4.5 and self.smashes < 3 and self.smash_t > 1.3:
            self.smash_t = 0.0
            self.smashes += 1
            self.events.append('smash')
        self.prev_state = self.state
