"""Chapter 5, before the fight: the factory floors between the drain and the hall.

The drain opens (halfway down, through its west wall) into a run of small
factory rooms. Four scraps of paper hidden in them each give one digit of the
code for a steel door. Past the door is the machine floor -- big, with rooms
grown off it -- where two machines each need two switches thrown before the
huge door into the hall will lift. No monsters back here.

The factory is a grid (like the mine) west and south of the hall:
cell (c, r) spans x = OX + 2c .. +2, z = OZ + 2r .. +2.
"""
import random

import chapter3 as C3
from engine import MeshBuilder, T
from textures import L, EMIS

C = 2.0
OX, OZ = -120.0, -24.0
COLS, ROWS = 59, 82
DOOR_CELL = (26, 28)                       # the passcode door
BIG_ROWS = (60, 63)                        # the huge door into the hall: col 39 (and the hall wall at x = -40)
BIG_Z = (OZ + BIG_ROWS[0] * C, OZ + (BIG_ROWS[1] + 1) * C)       # z 96 .. 104
TUN_OPEN = (OZ + 27 * C, OZ + 28 * C)      # the opening in the drain's west wall: z 30 .. 32
M1_ROOM = (3, 38, 17, 50)
M2_ROOM = (27, 56, 38, 68)
SMALL_ROOMS = [(46, 24, 51, 30), (45, 12, 53, 18), (55, 11, 58, 18), (36, 24, 41, 31), (36, 12, 41, 19),
               (27, 25, 32, 32), (45, 3, 51, 8), (28, 4, 35, 10)]


def inside(rect, c, r):
    return rect[0] <= c <= rect[2] and rect[1] <= r <= rect[3]


class FactoryLevel(C3.Level):
    def __init__(self):
        super().__init__(COLS, ROWS, OX, OZ, 0.0, seed=5151)
        self.door_open = 0.0          # the passcode door
        self.big_open = 0.0           # the huge door into the hall
        self.lights5 = []             # (pos, rad, col, kind) in World5's format
        self.carve_all()

    def carve_all(self):
        cv = self.carve
        # ---- the small rooms off the drain
        cv(52, 27, 58, 27, '.')               # in from the drain
        for rm in SMALL_ROOMS:
            cv(*rm, '.')
        cv(48, 19, 48, 23, '.')
        cv(54, 14, 54, 14, '.')
        cv(42, 27, 45, 27, '.')
        cv(42, 15, 44, 15, '.')
        cv(33, 28, 35, 28, '.')
        cv(48, 9, 48, 11, '.')
        cv(36, 7, 44, 7, '.')
        cv(DOOR_CELL[0], DOOR_CELL[1], DOOR_CELL[0], DOOR_CELL[1], 'D')
        # ---- the machine floor
        cv(20, 28, 25, 28, '.')
        cv(12, 24, 20, 32, '.')               # the hub
        cv(16, 33, 16, 37, '.')
        cv(*M1_ROOM, '.')
        cv(18, 44, 30, 44, '.')
        cv(30, 45, 30, 55, '.')
        cv(*M2_ROOM, '.')
        cv(39, BIG_ROWS[0], 39, BIG_ROWS[1], 'B')
        # ...and a lot more of it, grown out of the walls (never joining the small rooms but by the door)
        from gridgrow import grow
        keep = {(c, r) for r in range(0, 35) for c in range(25, COLS)}
        keep |= {(c, r) for r in range(34, ROWS) for c in range(39, COLS)}      # the hall's side of the wall
        before = sum(1 for row in self.g for k in row if k != '#')
        self.grown = grow(self.g, random.Random(5252), factor=2.3, passable='.DB', connect_to='.', room_kinds='.',
                          barrier='D', bounds=(1, 1, 38, ROWS - 2), keep_out=keep, room_w=(3, 9), room_h=(3, 8),
                          tries=30000)
        self.finish()
        self.grown_floor = sum(1 for row in self.g for k in row if k != '#') - before

    def finish(self):
        import numpy as np
        self.ceil = np.zeros((self.rows, self.cols))
        for r in range(self.rows):
            for c in range(self.cols):
                k = self.g[r][c]
                if inside(M1_ROOM, c, r) or inside(M2_ROOM, c, r) or k == 'B' or inside((12, 24, 20, 32), c, r):
                    h = 9.0
                elif any(inside(rm, c, r) for rm in SMALL_ROOMS) or k == '.':
                    h = 4.2
                else:
                    h = 3.4
                self.ceil[r, c] = h

    # ---- rules: the two doors
    def open_cell(self, c, r, elk=False):
        k = self.kind(c, r)
        if k == '#':
            if c == COLS and r == 27:
                return True               # the hole through into the drain
            # the strip of the hall wall the big door is in: open once it's up
            return c == 40 and BIG_ROWS[0] <= r <= BIG_ROWS[1] and self.big_open > 0.8
        if k == 'D':
            return self.door_open > 0.8
        if k == 'B':
            return self.big_open > 0.8
        return True

    def cell_blocked(self, c, r, elk):
        return not self.open_cell(c, r, elk)

    def floor_cells(self, zone_of=None):
        return [(c, r) for r in range(self.rows) for c in range(self.cols) if self.g[r][c] == '.']

    # ---- geometry: a dead factory, not a cave
    def build_mesh(self, b):
        rng = random.Random(5353)
        for r in range(self.rows):
            for c in range(self.cols):
                k = self.g[r][c]
                if k == '#':
                    continue
                x0, z0 = self.ox + c * C, self.oz + r * C
                x1, z1 = x0 + C, z0 + C
                ce = float(self.ceil[r, c])
                b.quad_world((x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1), L.CONCRETE, (0.5, 0.48, 0.45), 0.5)
                b.quad_world((x0, ce, z0), (x1, ce, z0), (x1, ce, z1), (x0, ce, z1), L.METAL, (0.28, 0.27, 0.26), 0.5)
                for dc, dr, side in ((0, -1, 'S'), (0, 1, 'N'), (-1, 0, 'W'), (1, 0, 'E')):
                    nc, nr = c + dc, r + dr
                    e = {'S': ((x0, z0), (x1, z0)), 'N': ((x1, z1), (x0, z1)), 'W': ((x0, z1), (x0, z0)),
                         'E': ((x1, z0), (x1, z1))}[side]
                    (ax, az), (bx, bz) = e
                    axis = 'x' if side in 'EW' else 'z'
                    nk = self.kind(nc, nr)
                    if nk == '#':
                        if k == 'B' and side == 'E':
                            continue          # the hall is through there
                        if c == COLS - 1 and side == 'E' and r == 27:
                            continue          # the hole into the drain
                        wall = L.BRICK if (c + r) % 7 else L.METAL
                        b.quad_world((ax, 0, az), (bx, 0, bz), (bx, ce, bz), (ax, ce, az), wall, (0.62, 0.55, 0.5), 0.5, axis=axis)
                        # a pipe run along some walls
                        if (c * 3 + r * 5) % 11 == 0:
                            mx, mz = (ax + bx) / 2, (az + bz) / 2
                            nx, nz = -dc * 0.25, -dr * 0.25
                            b.box((mx + nx, ce - 0.6, mz + nz), (C if axis == 'z' else 0.2, 0.2, C if axis == 'x' else 0.2),
                                  L.METAL, (0.5, 0.45, 0.4))
                    else:
                        nce = float(self.ceil[nr, nc])
                        if nce > ce + 0.01:
                            b.quad_world((ax, ce, az), (bx, ce, bz), (bx, nce, bz), (ax, nce, az), L.METAL, (0.3, 0.29, 0.28), 0.5, axis=axis)
                # junk on the floor: crates, drums, paper
                if k == '.' and rng.random() < 0.05:
                    cx, cz = x0 + 1.0 + rng.uniform(-0.4, 0.4), z0 + 1.0 + rng.uniform(-0.4, 0.4)
                    if rng.random() < 0.5:
                        s = rng.uniform(0.6, 0.9)
                        b.box((cx, s / 2, cz), (s, s, s), L.WOOD, (0.7, 0.62, 0.5), m=None)
                    else:
                        b.cylinder(0.32, 0.32, 0.9, 10, L.METAL, rng.choice(((0.5, 0.2, 0.15), (0.25, 0.32, 0.4), (0.5, 0.45, 0.2))),
                                   m=T(cx, 0, cz), cap=True)
                    self.boxes.append((cx - 0.4, cz - 0.4, cx + 0.4, cz + 0.4))
        # the hole into the drain: a short connector
        z0, z1 = TUN_OPEN
        b.quad_world((-2.0, 0, z0), (-1.3, 0, z0), (-1.3, 0, z1), (-2.0, 0, z1), L.CONCRETE, (0.5, 0.48, 0.45), 0.5)
        b.quad_world((-2.0, 2.5, z0), (-1.3, 2.5, z0), (-1.3, 2.5, z1), (-2.0, 2.5, z1), L.CONCRETE, (0.4, 0.4, 0.4), 0.5)
        for zz in (z0, z1):
            b.quad_world((-2.0, 0, zz), (-1.3, 0, zz), (-1.3, 2.5, zz), (-2.0, 2.5, zz), L.CONCRETE, (0.55, 0.55, 0.52), 0.5)
        b.facing_quad((-2.4, 1.6, z0 - 0.0 + 1.0), (1, 0, 0), 0.8, 0.5, L.SIGN, (0.9, 0.85, 0.7))
        # the two machines: big presses with a lamp each that lights when it has power
        self.machines = []
        for rm in (M1_ROOM, M2_ROOM):
            mc, mr = (rm[0] + rm[2]) / 2.0, (rm[1] + rm[3]) / 2.0
            x, z = self.ox + (mc + 0.5) * C, self.oz + (mr + 0.5) * C
            b.box((x, 2.5, z), (6.0, 5.0, 4.0), L.METAL, (0.4, 0.4, 0.36))
            b.box((x, 5.6, z), (4.0, 1.2, 3.0), L.METAL, (0.5, 0.42, 0.2))
            b.box((x, 6.8, z), (1.0, 1.4, 1.0), L.METAL, (0.35, 0.33, 0.3))
            for sx in (-1, 1):
                b.cylinder(0.5, 0.5, 6.0, 10, L.METAL, (0.3, 0.3, 0.3), m=T(x + sx * 3.6, 0, z))
                b.box((x + sx * 2.0, 0.6, z + 2.05), (1.4, 0.3, 0.1), L.METAL, (0.85, 0.68, 0.12))
            b.facing_quad((x, 3.6, z + 2.02), (0, 0, 1), 2.4, 0.9, L.SIGN, (0.85, 0.8, 0.7))
            self.boxes.append((x - 3.6, z - 2.2, x + 3.6, z + 2.2))
            self.machines.append({'pos': (x, z), 'lamp': (x, 5.4, z + 2.1), 'on': False})
        # light: dim work lamps in some rooms, most of it dark
        self.lights5 = []
        lit = list(SMALL_ROOMS) + [M1_ROOM, M2_ROOM, (12, 24, 20, 32)] + [g[:4] for g in self.grown]
        for i, rm in enumerate(lit):
            if i >= len(SMALL_ROOMS) + 3 and rng.random() > 0.4:
                continue
            mc, mr = (rm[0] + rm[2]) // 2, (rm[1] + rm[3]) // 2
            x, z = self.center(mc, mr)
            ce = float(self.ceil[mr, mc])
            b.box((x, ce - 0.3, z), (0.6, 0.15, 0.6), L.METAL, (0.3, 0.3, 0.3))
            b.box((x, ce - 0.4, z), (0.4, 0.06, 0.4), L.GLOW + EMIS, (1.0, 0.75, 0.45))
            col = (0.95, 0.7, 0.4) if rng.random() < 0.7 else (0.5, 0.6, 0.7)
            self.lights5.append(((x, ce - 0.8, z), 9.0 if ce < 5 else 16.0, col, 'fac'))
        # the passcode door's frame and keypad
        dx, dz = self.center(*DOOR_CELL)
        for sz in (-1, 1):
            b.box((dx, 2.1, dz + sz * 1.05), (0.4, 4.2, 0.12), L.METAL, (0.45, 0.4, 0.35))
        b.box((dx + 1.02, 1.3, dz + 1.25), (0.08, 0.36, 0.26), L.METAL, (0.25, 0.25, 0.27))
        b.box((dx + 1.07, 1.36, dz + 1.25), (0.02, 0.1, 0.18), L.GLOW + EMIS, (0.3, 0.9, 0.4))
        self.keypad = (dx + 1.1, 1.3, dz + 1.25)


def door_mesh(w, h):
    """A heavy steel door panel, centred on x = 0, standing on y = 0, thin in x."""
    b = MeshBuilder()
    b.box((0, h / 2, 0), (0.16, h, w), L.METAL, (0.42, 0.4, 0.38))
    for k in range(4):
        b.box((0.09, 0.4 + k * (h - 0.8) / 3, 0), (0.04, 0.14, w - 0.2), L.METAL, (0.3, 0.28, 0.26))
    b.box((0.1, h / 2, w / 2 - 0.25), (0.06, 0.5, 0.08), L.METAL, (0.7, 0.68, 0.6))
    return b.array()


def big_door_mesh():
    """The huge door into the hall: 8 m wide, 10 m tall, in hazard stripes."""
    b = MeshBuilder()
    w, h = 8.0, 10.0
    b.box((0, h / 2, 0), (0.5, h, w), L.METAL, (0.4, 0.38, 0.35))
    for k in range(9):
        b.box((0.27, 0.6 + k * 1.1, 0), (0.06, 0.45, w), L.METAL, (0.85, 0.68, 0.12) if k % 2 == 0 else (0.15, 0.15, 0.15))
    for sz in (-1, 1):
        b.box((0.28, h / 2, sz * (w / 2 - 0.3)), (0.08, h, 0.4), L.METAL, (0.3, 0.3, 0.3))
    return b.array()


def paper_mesh():
    b = MeshBuilder()
    b.quad((-0.12, 0.012, -0.16), (0.12, 0.012, -0.16), (0.12, 0.012, 0.16), (-0.12, 0.012, 0.16), L.PAPER, (1.0, 0.98, 0.9),
           uvs=((0, 0), (1, 0), (1, 1), (0, 1)))
    return b.array()


def switch_mesh():
    """A big breaker switch box on the wall (the handle is the lever mesh)."""
    b = MeshBuilder()
    b.box((0, 0, -0.12), (0.55, 0.8, 0.14), L.METAL, (0.35, 0.4, 0.36))
    b.box((0, 0.48, -0.1), (0.6, 0.1, 0.16), L.METAL, (0.85, 0.68, 0.12))
    return b.array()


def lamp_mesh(on):
    b = MeshBuilder()
    b.box((0, 0, 0), (0.5, 0.5, 0.2), L.GLOW + EMIS if on else L.METAL, (0.3, 1.0, 0.35) if on else (0.25, 0.08, 0.06))
    return b.array()


def shelf_mesh():
    """A tall steel shelving unit with junk on it, facing +z, 2.4 wide."""
    b = MeshBuilder()
    rng = random.Random(77)
    for sx in (-1.15, 1.15):
        for sz in (-0.27, 0.27):
            b.box((sx, 1.1, sz), (0.06, 2.2, 0.06), L.METAL, (0.4, 0.38, 0.36))
    for y in (0.15, 0.85, 1.55, 2.2):
        b.box((0, y, 0), (2.36, 0.04, 0.6), L.METAL, (0.45, 0.43, 0.4))
        for _ in range(3):
            x = rng.uniform(-0.9, 0.9)
            s = rng.uniform(0.2, 0.45)
            if y < 2.1:
                b.box((x, y + 0.02 + s / 2, rng.uniform(-0.12, 0.1)), (s, s, s * 1.2), L.WOOD if rng.random() < 0.6 else L.METAL,
                      (0.6, 0.55, 0.45))
    return b.array()


def booth_mesh(x0, z0, x1, z1):
    """The admin booth in the corner of the hall: walls with a window, a desk, monitors, the button."""
    b = MeshBuilder()
    h = 3.2
    wall = (0.5, 0.48, 0.46)
    b.quad_world((x0, 0.01, z0), (x1, 0.01, z0), (x1, 0.01, z1), (x0, 0.01, z1), L.WOOD, (0.55, 0.45, 0.35), 0.5)
    b.box(((x0 + x1) / 2, h, (z0 + z1) / 2), (x1 - x0, 0.15, z1 - z0), L.METAL, (0.3, 0.3, 0.3))
    # north wall with a long window, west wall with the door gap at z 46.4 .. 48.6
    b.box(((x0 + x1) / 2, 0.55, z1), (x1 - x0, 1.1, 0.2), L.CONCRETE, wall)
    b.box(((x0 + x1) / 2, h - 0.35, z1), (x1 - x0, 0.7, 0.2), L.CONCRETE, wall)
    for k in range(5):
        b.box((x0 + (k + 0.5) * (x1 - x0) / 5, 1.75, z1), (0.12, 1.3, 0.2), L.METAL, (0.3, 0.3, 0.3))
    b.box((x0, h / 2, (z0 + 46.4) / 2), (0.2, h, 46.4 - z0), L.CONCRETE, wall)
    b.box((x0, h / 2, (48.6 + z1) / 2), (0.2, h, z1 - 48.6), L.CONCRETE, wall)
    b.box((x0, h - 0.3, 47.5), (0.2, 0.6, 2.2), L.CONCRETE, wall)
    b.facing_quad((x0 - 0.12, 2.5, 47.5), (-1, 0, 0), 1.2, 0.4, L.SIGN, (0.9, 0.85, 0.7))
    # desk, monitors, the button on the east wall
    b.box((x1 - 1.2, 0.75, (z0 + z1) / 2), (1.0, 0.08, 3.6), L.WOOD, (0.5, 0.42, 0.32))
    for k in range(3):
        mz = (z0 + z1) / 2 - 1.2 + k * 1.2
        b.box((x1 - 1.5, 1.1, mz), (0.4, 0.5, 0.6), L.METAL, (0.2, 0.2, 0.22))
        b.box((x1 - 1.72, 1.1, mz), (0.02, 0.38, 0.48), L.GLOW + EMIS, (0.15, 0.35, 0.25))
    b.box((x1 - 0.08, 1.3, 47.5), (0.1, 0.6, 0.6), L.METAL, (0.3, 0.3, 0.32))
    b.box((x1 - 0.16, 1.3, 47.5), (0.08, 0.22, 0.22), L.GLOW + EMIS, (1.0, 0.1, 0.05))
    b.facing_quad((x1 - 0.14, 1.75, 47.5), (-1, 0, 0), 0.7, 0.25, L.SIGN, (0.9, 0.3, 0.2))
    return b.array()
