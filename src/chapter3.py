"""Chapter 3: the cave, the mine, and the Elk.

Two grid levels (the upper mine with the cave mouth, and the lower mine you
reach by elevator), the snowy cliff outside the cave mouth, knee-deep snow
cover for the earlier maps, and the Elk's hunting AI.

Cells are 2 m. Kinds:
  '#' rock      '.' cavern (huge, the Elk fits)      'M' cave mouth tunnel (Elk fits)
  ',' mineshaft (narrow and timbered: the Elk is too big to follow you in)
  'E' elevator  'X' the old adit out of the mine
"""
import math
import random
import heapq
import numpy as np

from engine import MeshBuilder, T, S, RX, RY, RZ
from textures import L, EMIS

C = 2.0
ELK_KINDS = '.M'


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


class Level:
    def __init__(self, cols, rows, ox, oz, base_y, seed):
        self.cols, self.rows = cols, rows
        self.ox, self.oz, self.y0 = ox, oz, base_y
        self.g = [['#'] * cols for _ in range(rows)]
        self.rng = random.Random(seed)
        self.lights = []          # dicts: pos, rad, col, powered (only lit once the generator runs)
        self.levers = []          # dicts: pos, yaw, pulled, progress, angle
        self.bulbs = []           # emissive bulb positions that light up with the generator
        self.crystals = []
        self.boxes = []           # extra solid props (x0, z0, x1, z1)
        self.elevator = None      # (c, r)
        self.exit = None          # (c, r)

    # ---------------------------------------------------------------- grid basics
    def carve(self, c0, r0, c1, r1, ch):
        for r in range(min(r0, r1), max(r0, r1) + 1):
            for c in range(min(c0, c1), max(c0, c1) + 1):
                self.g[r][c] = ch

    def grow_map(self, add_cols, add_rows, seed, barrier='', keep_out=(), corridor_kinds='..,', factor=1.5):
        """More floor (1.5x): caverns and shafts grown into the rock around the hand-made map."""
        from gridgrow import grow, pad
        pad(self.g, add_cols, add_rows)
        self.cols += add_cols
        self.rows += add_rows
        self.grown = grow(self.g, random.Random(seed), factor, passable='.,MEXRGH', connect_to='.,', room_kinds='.',
                          corridor_kinds=corridor_kinds, barrier=barrier, keep_out=keep_out,
                          bounds=(1, 1, self.cols - 2, self.rows - 2), room_w=(3, 9), room_h=(3, 8), tries=40000)
        return self.grown

    def kind(self, c, r):
        if 0 <= r < self.rows and 0 <= c < self.cols:
            return self.g[r][c]
        return '#'

    def cell_of(self, x, z):
        return int(math.floor((x - self.ox) / C)), int(math.floor((z - self.oz) / C))

    def center(self, c, r):
        return self.ox + (c + 0.5) * C, self.oz + (r + 0.5) * C

    def finish(self):
        """Ceilings per cell: towering caverns, low timbered shafts."""
        self.ceil = np.zeros((self.rows, self.cols))
        for r in range(self.rows):
            for c in range(self.cols):
                k = self.g[r][c]
                if k == '.':
                    self.ceil[r, c] = self.y0 + 7.6 + 0.9 * math.sin(c * 1.3 + r * 0.7) + 0.5 * math.cos(c * 0.4 - r * 1.1)
                elif k == 'M':
                    self.ceil[r, c] = self.y0 + 6.5
                elif k == 'E':
                    self.ceil[r, c] = self.y0 + 9.0
                else:
                    self.ceil[r, c] = self.y0 + 2.5

    def floor_at(self, x, z):
        return self.y0

    def open_cell(self, c, r, elk=False):
        k = self.kind(c, r)
        if k == '#':
            return False
        if elk and k not in ELK_KINDS:
            return False
        return True

    def cell_blocked(self, c, r, elk):
        if r < 0 and self.has_outside:
            return False            # the snowy slope outside the cave mouth
        return not self.open_cell(c, r, elk)

    has_outside = False
    planks = ()

    def collide(self, x, z, rad, elk=False):
        for _ in range(3):
            c0, r0 = self.cell_of(x - rad, z - rad)
            c1, r1 = self.cell_of(x + rad, z + rad)
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    if self.cell_blocked(c, r, elk):
                        x0 = self.ox + c * C
                        z0 = self.oz + r * C
                        nx = clamp(x, x0, x0 + C)
                        nz = clamp(z, z0, z0 + C)
                        dx, dz = x - nx, z - nz
                        d2 = dx * dx + dz * dz
                        if d2 < rad * rad:
                            if d2 > 1e-10:
                                d = math.sqrt(d2)
                                x += dx / d * (rad - d)
                                z += dz / d * (rad - d)
                            else:
                                opts = [(x - x0, -1, 0), (x0 + C - x, 1, 0), (z - z0, 0, -1), (z0 + C - z, 0, 1)]
                                dm, sx, sz = min(opts)
                                x += sx * (dm + rad)
                                z += sz * (dm + rad)
            boxes = self.boxes
            if self.planks:
                boxes = boxes + [pl['box'] for pl in self.planks if not pl['broken']]
            for bx0, bz0, bx1, bz1 in boxes:
                nx = clamp(x, bx0, bx1)
                nz = clamp(z, bz0, bz1)
                dx, dz = x - nx, z - nz
                d2 = dx * dx + dz * dz
                if 1e-10 < d2 < rad * rad:
                    d = math.sqrt(d2)
                    x += dx / d * (rad - d)
                    z += dz / d * (rad - d)
            if self.has_outside and z < self.oz:
                # outside the mouth: a strip of snowy ground in front of the cliff
                x = clamp(x, self.ox + 6, self.ox + self.cols * C - 6)
                z = max(z, self.oz - 70)
        return x, z

    def los(self, x0, z0, x1, z1):
        dx, dz = x1 - x0, z1 - z0
        d = math.hypot(dx, dz)
        n = int(d / 0.4) + 1
        for i in range(1, n):
            t = i / n
            c, r = self.cell_of(x0 + dx * t, z0 + dz * t)
            if r < 0 and self.has_outside:
                continue
            if self.kind(c, r) == '#':
                return False
        return True

    def astar(self, start, goal, elk=True, max_nodes=5000):
        if start == goal:
            return [goal]
        openq = [(0, start)]
        came = {start: None}
        cost = {start: 0}
        n = 0
        while openq:
            _, cur = heapq.heappop(openq)
            if cur == goal:
                break
            n += 1
            if n > max_nodes:
                return None
            c, r = cur
            for dc, dr in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nb = (c + dc, r + dr)
                if not self.open_cell(nb[0], nb[1], elk):
                    continue
                nc = cost[cur] + 1
                if nb not in cost or nc < cost[nb]:
                    cost[nb] = nc
                    came[nb] = cur
                    heapq.heappush(openq, (nc + abs(nb[0] - goal[0]) + abs(nb[1] - goal[1]), nb))
        if goal not in came:
            return None
        path = []
        cur = goal
        while cur is not None:
            path.append(cur)
            cur = came[cur]
        path.reverse()
        return path

    def nearest_elk_cell(self, c, r):
        """The closest cell the Elk can stand in -- e.g. the mouth of the shaft you are hiding in."""
        seen = {(c, r)}
        q = [(c, r)]
        while q:
            cur = q.pop(0)
            if self.open_cell(cur[0], cur[1], elk=True):
                return cur
            for dc, dr in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nb = (cur[0] + dc, cur[1] + dr)
                if nb not in seen and self.kind(*nb) != '#':
                    seen.add(nb)
                    q.append(nb)
        return None

    def elk_cells(self):
        return [(c, r) for r in range(self.rows) for c in range(self.cols) if self.g[r][c] == '.']

    # ---------------------------------------------------------------- geometry
    def build_mesh(self, b):
        rock = (0.62, 0.56, 0.5)
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
                narrow = k in ',EX'
                b.quad_world((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1),
                             L.WOOD if k == 'E' else L.MUD, (0.75, 0.72, 0.68) if narrow else (0.62, 0.6, 0.58), 0.4)
                b.quad_world((x0, ce, z0), (x1, ce, z0), (x1, ce, z1), (x0, ce, z1), L.CONCRETE, (0.42, 0.38, 0.34), 0.3)
                for dc, dr, side in ((0, -1, 'S'), (0, 1, 'N'), (-1, 0, 'W'), (1, 0, 'E')):
                    nc, nr = c + dc, r + dr
                    if nr < 0 and self.has_outside:
                        continue
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
                        b.quad_world((ax, y0, az), (bx, y0, bz), (bx, ce, bz), (ax, ce, az), L.CONCRETE, rock, 0.3, axis=axis)
                    else:
                        nce = float(self.ceil[nr, nc])
                        if nce > ce + 0.01:
                            b.quad_world((ax, ce, az), (bx, ce, bz), (bx, nce, bz), (ax, nce, az), L.CONCRETE, rock, 0.3, axis=axis)
                if k == ',':
                    self._timber(b, c, r, x0, z0, ce)
                elif k == '.':
                    self._cavern_dressing(b, c, r, x0, z0, ce)

    def _run_dir(self, c, r):
        ns = self.kind(c, r + 1) != '#' or self.kind(c, r - 1) != '#'
        ew = self.kind(c + 1, r) != '#' or self.kind(c - 1, r) != '#'
        return 'z' if (ns and not ew) or (ns and ew and self.rng.random() < 0.5) else 'x'

    def _timber(self, b, c, r, x0, z0, ce):
        """Timber frames, rails, and the odd hanging work light."""
        y0 = self.y0
        wood = (0.7, 0.55, 0.4)
        d = self._run_dir(c, r)
        cx, cz = x0 + C / 2, z0 + C / 2
        if d == 'z':
            for sx in (-0.85, 0.85):
                b.box((cx + sx, (y0 + ce) / 2, cz), (0.18, ce - y0, 0.18), L.WOOD, wood)
            b.box((cx, ce - 0.1, cz), (1.9, 0.18, 0.2), L.WOOD, wood)
            for sx in (-0.35, 0.35):
                b.box((cx + sx, y0 + 0.04, cz), (0.06, 0.08, C), L.METAL, (0.6, 0.55, 0.5))
            for k in range(3):
                b.box((cx, y0 + 0.02, z0 + 0.35 + k * 0.65), (0.95, 0.05, 0.14), L.WOOD, (0.5, 0.42, 0.35))
        else:
            for sz in (-0.85, 0.85):
                b.box((cx, (y0 + ce) / 2, cz + sz), (0.18, ce - y0, 0.18), L.WOOD, wood)
            b.box((cx, ce - 0.1, cz), (0.2, 0.18, 1.9), L.WOOD, wood)
            for sz in (-0.35, 0.35):
                b.box((cx, y0 + 0.04, cz + sz), (C, 0.08, 0.06), L.METAL, (0.6, 0.55, 0.5))
            for k in range(3):
                b.box((x0 + 0.35 + k * 0.65, y0 + 0.02, cz), (0.14, 0.05, 0.95), L.WOOD, (0.5, 0.42, 0.35))
        if (c * 7 + r * 3) % 4 == 0:
            self.bulb(b, cx, ce - 0.35, cz, ce)

    def bulb(self, b, x, y, z, ce, rad=7.0):
        b.box((x, (y + ce) / 2, z), (0.02, ce - y, 0.02), L.BLACK)
        b.box((x, y + 0.07, z), (0.12, 0.05, 0.12), L.METAL)
        self.bulbs.append((x, y - 0.02, z))
        self.lights.append({'pos': (x, y - 0.15, z), 'rad': rad, 'col': (1.0, 0.62, 0.3), 'powered': True})

    def _cavern_dressing(self, b, c, r, x0, z0, ce):
        rng = self.rng
        y0 = self.y0
        # stalactites and stalagmites
        if rng.random() < 0.55:
            for _ in range(rng.randint(1, 3)):
                x, z = x0 + rng.uniform(0.2, 1.8), z0 + rng.uniform(0.2, 1.8)
                ln = rng.uniform(0.6, 2.4)
                b.cylinder(0.0, rng.uniform(0.12, 0.35), ln, 6, L.CONCRETE, (0.55, 0.5, 0.45), m=T(x, ce - ln, z))
        if rng.random() < 0.18:
            x, z = x0 + rng.uniform(0.4, 1.6), z0 + rng.uniform(0.4, 1.6)
            b.cylinder(rng.uniform(0.2, 0.45), 0.0, rng.uniform(0.6, 1.8), 6, L.CONCRETE, (0.6, 0.55, 0.5), m=T(x, y0, z))
        # boulders heaped against the walls
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if self.kind(c + dc, r + dr) == '#' and rng.random() < 0.45:
                x = x0 + C / 2 + dc * 0.75 + rng.uniform(-0.4, 0.4)
                z = z0 + C / 2 + dr * 0.75 + rng.uniform(-0.4, 0.4)
                sz = rng.uniform(0.6, 1.5)
                m = T(x, y0, z) @ RY(rng.random() * 6) @ RX(rng.uniform(-0.3, 0.3))
                b.box((0, sz * 0.3, 0), (sz * 1.2, sz * 0.9, sz), L.CONCRETE, (0.5, 0.46, 0.42), m=m)

    def wall_point(self, c, r, side, y, off=0.3):
        cx, cz = self.center(c, r)
        if side == 'N':
            return (cx, y, cz + C / 2 - off), (0, 0, -1)
        if side == 'S':
            return (cx, y, cz - C / 2 + off), (0, 0, 1)
        if side == 'W':
            return (cx - C / 2 + off, y, cz), (1, 0, 0)
        return (cx + C / 2 - off, y, cz), (-1, 0, 0)

    def lever_spot(self, c, r, side):
        p, n = self.wall_point(c, r, side, self.y0 + 1.15, off=0.22)
        return p, math.atan2(n[0], n[2])

    def add_lever(self, b, c, r, side):
        """A lever on a wall. Its housing is drawn on its own (see lever_box_mesh), so a new
        game can move it somewhere else."""
        p, yaw = self.lever_spot(c, r, side)
        self.levers.append({'pos': p, 'yaw': yaw, 'pulled': False, 'progress': 0.0, 'angle': -0.8})

    def wall_spots(self, kinds='.', rows=None, cols=None):
        """Every (c, r, side) where a lever could hang: a floor cell next to rock."""
        out = []
        for r in range(self.rows):
            if rows and not (rows[0] <= r <= rows[1]):
                continue
            for c in range(self.cols):
                if cols and not (cols[0] <= c <= cols[1]):
                    continue
                if self.g[r][c] not in kinds:
                    continue
                for side, (dc, dr) in (('N', (0, 1)), ('S', (0, -1)), ('E', (1, 0)), ('W', (-1, 0))):
                    if self.kind(c + dc, r + dr) == '#':
                        out.append((c, r, side))
        return out


# ---------------------------------------------------------------------- the two levels
def build_upper():
    lv = Level(48, 43, -29.0, 0.0, 0.0, seed=303)
    lv.has_outside = True
    lv.carve(13, 0, 14, 4, 'M')              # the cave mouth
    lv.carve(8, 5, 20, 10, '.')              # entrance cavern
    lv.carve(3, 8, 7, 8, ',')                # west mineshaft
    lv.carve(3, 8, 3, 17, ',')
    lv.carve(1, 18, 7, 22, '.')              # west cavern
    lv.carve(21, 7, 25, 8, '.')              # big passage east
    lv.carve(24, 9, 25, 11, '.')
    lv.carve(22, 12, 28, 17, '.')            # east cavern
    lv.carve(14, 11, 14, 16, ',')            # mineshaft north
    lv.carve(12, 17, 16, 19, ',')            # the mine office
    lv.carve(17, 18, 17, 18, 'E')            # the elevator
    lv.carve(14, 20, 14, 21, ',')
    lv.carve(9, 22, 21, 26, '.')             # crystal cavern
    lv.carve(7, 21, 8, 22, '.')              # west cavern <-> crystal cavern
    lv.carve(21, 17, 22, 21, '.')            # east cavern <-> crystal cavern
    # further in: the deep east cavern, the northeast cavern, the great hall
    lv.carve(29, 14, 32, 15, '.')
    lv.carve(33, 6, 43, 20, '.')             # deep east cavern
    lv.carve(26, 8, 32, 8, ',')              # mineshaft from the big passage
    lv.carve(38, 21, 38, 25, ',')            # mineshaft north
    lv.carve(34, 26, 44, 33, '.')            # northeast cavern
    lv.carve(31, 30, 33, 31, '.')
    lv.carve(6, 31, 30, 39, '.')             # the great hall
    for c, r in ((10, 34), (16, 36), (22, 33), (26, 37), (12, 38)):
        lv.g[r][c] = '#'                     # rock pillars
    lv.carve(17, 27, 18, 30, '.')            # crystal cavern <-> great hall
    lv.carve(3, 23, 3, 30, ',')              # mineshaft from the west cavern
    lv.carve(3, 31, 5, 31, ',')
    lv.carve(14, 40, 24, 40, ',')            # a long gallery off the great hall
    lv.elevator = (17, 18)
    keep = {(c, r) for r in range(0, 12) for c in range(6, 22)} | {(c, r) for r in range(15, 22) for c in range(10, 20)}
    lv.grow_map(36, 30, seed=3031, keep_out=keep)
    lv.finish()
    lv.spawn = lv.center(14, 6)              # where you lie down
    lv.safe = lv.center(14, 18)              # the office: respawn point
    return lv


LOW_SHIFT = 10       # rows the old lower mine moved north to make room for the rail yard


def build_lower():
    SH = LOW_SHIFT
    lv = Level(40, 52, -31.0, 0.0, -60.0, seed=404)
    lv.carve(15, 1, 15, 1, 'E')              # elevator, bottom of the shaft
    lv.carve(15, 2, 15, 3, ',')
    # ---- the rail yard, before the big cavern
    lv.carve(11, 4, 19, 7, '.')              # the yard: the cart waits at the head of the rails
    lv.carve(6, 5, 10, 5, ',')               # west shaft
    lv.carve(1, 2, 5, 8, '.')                # the pump cavern
    lv.carve(20, 5, 26, 6, '.')              # east tunnel
    lv.carve(27, 1, 33, 8, '.')              # the east gallery: the power lever
    lv.carve(15, 8, 15, SH + 6, 'R')          # the rail tunnel, boarded up
    # ---- the mine as it was, ten rows on
    lv.carve(10, SH + 7, 20, SH + 12, '.')     # where the Goat Man lies
    lv.carve(4, SH + 9, 9, SH + 10, '.')       # west tunnel
    lv.carve(4, SH + 11, 5, SH + 15, '.')
    lv.carve(2, SH + 16, 9, SH + 21, '.')      # west cavern
    lv.carve(21, SH + 9, 26, SH + 10, '.')     # east tunnel
    lv.carve(25, SH + 11, 26, SH + 16, '.')
    lv.carve(18, SH + 17, 27, SH + 21, '.')    # east cavern
    lv.carve(10, SH + 19, 17, SH + 20, '.')    # passage between them
    lv.carve(15, SH + 13, 15, SH + 18, ',')    # a mineshaft shortcut
    lv.carve(22, SH + 22, 23, SH + 27, '.')    # north from the east cavern
    lv.carve(12, SH + 28, 34, SH + 35, '.')    # the far cavern
    for c, r in ((16, 31), (22, 33), (28, 30), (31, 34)):
        lv.g[r + SH][c] = '#'
    lv.carve(5, SH + 22, 5, SH + 31, ',')      # mineshaft from the west cavern
    lv.carve(6, SH + 31, 11, SH + 31, ',')
    lv.carve(27, SH + 11, 33, SH + 12, '.')    # the long east tunnel
    lv.carve(32, SH + 13, 33, SH + 27, '.')
    lv.carve(35, SH + 30, 37, SH + 30, ',')    # a dead-end shaft to hide in
    lv.carve(20, SH + 36, 20, SH + 39, ',')    # the old adit
    lv.carve(20, SH + 40, 20, SH + 40, 'X')    # ...and out
    lv.elevator = (15, 1)
    lv.exit = (20, SH + 40)
    keep = {(c, r) for r in range(0, SH + 9) for c in range(12, 19)} | {(c, r) for r in range(SH + 35, SH + 42) for c in range(17, 24)}
    lv.grow_map(34, 34, seed=4041, barrier='R', keep_out=keep)
    lv.finish()
    lv.spawn = lv.center(15, 2)
    lv.safe = lv.center(15, 3)
    lv.goat_cell = (15, SH + 10)
    lv.elk_spawn = (26, SH + 20)
    # the minecart runs from the yard up the rail tunnel into the Goat Man's cavern
    cx, _ = lv.center(15, 8)
    lv.rail = (cx, lv.oz + 8 * C + 0.4, lv.oz + (SH + 8) * C + 0.6)        # x, z start, z end
    lv.planks = []
    for r in (11, 14):
        z = lv.oz + r * C + 1.0
        lv.planks.append({'z': z, 'broken': False, 'box': (cx - 1.0, z - 0.15, cx + 1.0, z + 0.15)})
    return lv


def decorate(lv, b, seed):
    """Mine junk along the walls and rock hanging from the roof -- clear of the elevator, the rails,
    and anything that already stands there."""
    import decor
    busy = list(lv.boxes)
    rail = getattr(lv, 'rail', None)
    lift = lv.center(*lv.elevator) if lv.elevator else None

    def skip(c, r):
        x, z = lv.center(c, r)
        if lift and math.hypot(x - lift[0], z - lift[1]) < 4.5:
            return True
        if rail and abs(x - rail[0]) < 3.2 and rail[1] - 4 < z < rail[2] + 4:
            return True
        if getattr(lv, 'safe', None) and math.hypot(x - lv.safe[0], z - lv.safe[1]) < 3.0:
            return True
        return any(bx0 - 1.6 < x < bx1 + 1.6 and bz0 - 1.6 < z < bz1 + 1.6 for bx0, bz0, bx1, bz1 in busy)

    decor.dress_level(lv, b, 'mine', seed, skip=skip)


def dress_upper(lv, b):
    rng = lv.rng
    lv.build_mesh(b)
    y0 = lv.y0
    lv.add_lever(b, 1, 20, 'W')             # west cavern
    lv.add_lever(b, 43, 9, 'E')             # deep east cavern
    lv.add_lever(b, 8, 39, 'N')             # the great hall
    lv.add_lever(b, 44, 30, 'E')            # the northeast cavern
    # crystal cavern: pale glowing crystals, the only light before the generator runs
    for _ in range(26):
        c, r = rng.randint(9, 21), rng.randint(22, 26)
        x, z = lv.center(c, r)
        x += rng.uniform(-0.8, 0.8)
        z += rng.uniform(-0.8, 0.8)
        for k in range(rng.randint(2, 4)):
            h = rng.uniform(0.3, 1.3)
            m = T(x + rng.uniform(-0.25, 0.25), y0, z + rng.uniform(-0.25, 0.25)) @ RX(rng.uniform(-0.5, 0.5)) @ RZ(rng.uniform(-0.5, 0.5))
            b.box((0, h / 2, 0), (0.12, h, 0.12), L.GLOW + EMIS, (0.25, 0.42, 0.5), m=m)
        lv.crystals.append((x, y0 + 0.6, z))
    for i, (x, y, z) in enumerate(lv.crystals[::5]):
        lv.lights.append({'pos': (x, y + 0.5, z), 'rad': 7.0, 'col': (0.12, 0.25, 0.32), 'powered': False})
    # the mine office: desk, generator, crates, a map on the wall
    cx, cz = lv.center(13, 18)
    b.box((cx, y0 + 0.75, cz), (1.4, 0.06, 0.7), L.WOOD)
    for ox, oz in ((-0.62, -0.28), (0.62, -0.28), (-0.62, 0.28), (0.62, 0.28)):
        b.box((cx + ox, y0 + 0.37, cz + oz), (0.06, 0.74, 0.06), L.WOOD)
    b.facing_quad((cx - 0.3, y0 + 1.6, lv.oz + 20 * C - 0.02), (0, 0, -1), 0.9, 0.6, L.PAPER, (0.85, 0.8, 0.7))
    gx, gz = lv.center(16, 17)
    b.box((gx, y0 + 0.5, gz), (1.2, 1.0, 0.8), L.METAL, (0.45, 0.5, 0.42))
    b.cylinder(0.08, 0.08, 1.6, 8, L.METAL, m=T(gx + 0.4, y0 + 1.0, gz))
    lv.boxes.append((gx - 0.6, gz - 0.4, gx + 0.6, gz + 0.4))
    lv.generator = (gx, y0 + 1.1, gz)
    for (c, r) in ((12, 19), (16, 19)):
        x, z = lv.center(c, r)
        b.box((x, y0 + 0.4, z), (0.8, 0.8, 0.8), L.WOOD, (0.7, 0.65, 0.55))
        lv.boxes.append((x - 0.4, z - 0.4, x + 0.4, z + 0.4))
    # an ore cart left in the west mineshaft
    x, z = lv.center(3, 12)
    b.box((x, y0 + 0.55, z), (0.8, 0.6, 1.2), L.METAL, (0.5, 0.42, 0.35))
    for sz in (-0.4, 0.4):
        for sx in (-0.36, 0.36):
            b.cylinder(0.15, 0.15, 0.06, 8, L.BLACK, m=T(x + sx, y0 + 0.17, z + sz) @ RZ(math.pi / 2))
    # work lights strung through the caverns (dark until the generator runs)
    for (c, r) in ((14, 7), (10, 9), (18, 6), (24, 14), (26, 16), (4, 20), (12, 24), (19, 24), (23, 8),
                   (36, 9), (41, 17), (38, 29), (43, 32), (9, 33), (19, 35), (28, 38), (24, 31)):
        x, z = lv.center(c, r)
        lv.bulb(b, x, y0 + 4.0, z, float(lv.ceil[r, c]), rad=11.0)
    # bones and old clothes the Elk dragged in, near the mouth
    for _ in range(14):
        x, z = lv.center(rng.randint(10, 18), rng.randint(5, 7))
        m = T(x + rng.uniform(-0.8, 0.8), y0 + 0.04, z + rng.uniform(-0.8, 0.8)) @ RY(rng.random() * 6)
        b.box((0, 0, 0), (rng.uniform(0.2, 0.5), 0.05, 0.05), L.BONE, (0.85, 0.8, 0.75), m=m)
    _grown_lights(lv, b)
    _outside(lv, b)


def dress_lower(lv, b):
    rng = lv.rng
    lv.build_mesh(b)
    y0 = lv.y0
    SH = LOW_SHIFT
    # ---- the rail yard: rails, sleepers and timber frames up the boarded tunnel
    cx = lv.rail[0]
    z0, z1 = lv.oz + 6 * C, lv.rail[2] + 1.5
    for sx in (-0.42, 0.42):
        b.box((cx + sx, y0 + 0.05, (z0 + z1) / 2), (0.07, 0.1, z1 - z0), L.METAL, (0.62, 0.56, 0.5))
    z = z0 + 0.3
    while z < z1:
        b.box((cx, y0 + 0.02, z), (1.2, 0.05, 0.16), L.WOOD, (0.5, 0.42, 0.35))
        z += 0.6
    for r in range(8, SH + 7):
        zc = lv.oz + (r + 0.5) * C
        for sx in (-0.88, 0.88):
            b.box((cx + sx, y0 + 1.25, zc), (0.18, 2.5, 0.18), L.WOOD, (0.7, 0.55, 0.4))
        b.box((cx, y0 + 2.4, zc), (1.95, 0.18, 0.2), L.WOOD, (0.7, 0.55, 0.4))
    # a buffer stop at the head of the rails, and a sign
    b.box((cx, y0 + 0.35, z0 + 0.2), (1.3, 0.3, 0.3), L.WOOD, (0.6, 0.3, 0.2))
    b.facing_quad((cx - 1.6, y0 + 1.7, lv.oz + 8 * C - 0.05), (0, 0, -1), 0.9, 0.6, L.SIGN, (0.85, 0.82, 0.7))
    # the pump cavern: what's left of a miner, and a long-dead pump
    px, pz = lv.center(3, 4)
    m = T(px, y0 + 0.02, pz) @ RY(0.8)
    b.box((0, 0.1, 0), (0.42, 0.2, 1.3), L.CLOTH, (0.35, 0.4, 0.5), m=m)
    b.box((0, 0.12, 0.8), (0.22, 0.22, 0.26), L.BONE, (0.85, 0.8, 0.75), m=m)
    b.box((0.05, 0.3, 0.95), (0.3, 0.12, 0.3), L.METAL, (0.85, 0.7, 0.2), m=m)       # his hard hat
    x, z = lv.center(2, 7)
    b.box((x, y0 + 0.6, z), (1.4, 1.2, 1.0), L.METAL, (0.45, 0.42, 0.38))
    lv.boxes.append((x - 0.7, z - 0.5, x + 0.7, z + 0.5))
    # the east gallery: the power lever, wired to a junction box over the rails
    lv.add_lever(b, 33, 4, 'E')
    for (c, r) in ((29, 2), (31, 7), (28, 6)):
        x, z = lv.center(c, r)
        b.box((x, y0 + 0.45, z), (0.9, 0.9, 0.9), L.WOOD, (0.65, 0.6, 0.5))
        lv.boxes.append((x - 0.45, z - 0.45, x + 0.45, z + 0.45))
    b.box((cx + 1.1, y0 + 1.6, lv.oz + 7 * C + 1.0), (0.4, 0.5, 0.2), L.METAL, (0.5, 0.48, 0.45))
    for (c, r) in ((15, 5), (3, 5), (30, 4), (23, 5), (12, 6)):
        x, z = lv.center(c, r)
        lv.bulb(b, x, y0 + 4.0, z, float(lv.ceil[r, c]), rad=9.0)
    for _ in range(10):
        x, z = lv.center(rng.randint(11, 19), rng.randint(4, 7))
        m = T(x + rng.uniform(-0.8, 0.8), y0 + 0.04, z + rng.uniform(-0.8, 0.8)) @ RY(rng.random() * 6)
        b.box((0, 0, 0), (rng.uniform(0.2, 0.5), 0.05, 0.05), L.BONE, (0.85, 0.8, 0.75), m=m)
    # blood pooled around the Goat Man, and dragged off toward the east
    gx, gz = lv.center(*lv.goat_cell)
    for _ in range(9):
        x, z = gx + rng.uniform(-1.6, 1.6), gz + rng.uniform(-1.6, 1.6)
        s = rng.uniform(0.8, 1.8)
        b.quad((x - s, y0 + 0.02, z - s), (x + s, y0 + 0.02, z - s), (x + s, y0 + 0.02, z + s), (x - s, y0 + 0.02, z + s),
               L.BLOOD, (1, 1, 1), uvs=((0, 0), (1, 0), (1, 1), (0, 1)))
    for i in range(8):
        x, z = gx + 2.0 + i * 1.3, gz - 1.0 + 0.2 * math.sin(i)
        b.quad((x - 0.4, y0 + 0.02, z - 0.6), (x + 0.4, y0 + 0.02, z - 0.6), (x + 0.4, y0 + 0.02, z + 0.6),
               (x - 0.4, y0 + 0.02, z + 0.6), L.BLOOD, (0.8, 0.8, 0.8), uvs=((0, 0), (1, 0), (1, 1), (0, 1)))
    for _ in range(26):
        m = T(gx + rng.uniform(-2.5, 2.5), y0 + 0.05, gz + rng.uniform(-2.5, 2.5)) @ RY(rng.random() * 6)
        b.box((0, 0, 0), (rng.uniform(0.15, 0.6), 0.06, 0.06), L.BONE, (0.85, 0.75, 0.7), m=m)
    # a few work lights still burning down here, and the grey light at the end of the adit
    for (c, r) in ((15, 4), (12, 9), (18, 11), (6, 10), (5, 18), (14, 20), (22, 19), (26, 13),
                   (23, 25), (15, 30), (27, 33), (33, 29), (30, 12), (33, 20), (20, 38), (5, 27)):
        r += SH
        x, z = lv.center(c, r)
        lv.bulb(b, x, y0 + (1.95 if lv.kind(c, r) in ',R' else 4.0), z, float(lv.ceil[r, c]), rad=9.0)
    ex, ez = lv.center(*lv.exit)
    b.facing_quad((ex, y0 + 1.1, ez + C / 2 - 0.05), (0, 0, -1), 1.8, 2.2, L.GLOW + EMIS, (0.55, 0.6, 0.7))
    lv.lights.append({'pos': (ex, y0 + 1.5, ez), 'rad': 9.0, 'col': (0.35, 0.4, 0.5), 'powered': False})
    # old crates and an ore cart
    _grown_lights(lv, b)
    for (c, r) in ((11, 8), (19, 12), (3, 17), (26, 20)):
        x, z = lv.center(c, r + SH)
        b.box((x, y0 + 0.45, z), (0.9, 0.9, 0.9), L.WOOD, (0.65, 0.6, 0.5))
        lv.boxes.append((x - 0.45, z - 0.45, x + 0.45, z + 0.45))


def _grown_lights(lv, b):
    rng = random.Random(lv.cols * 7 + lv.rows)
    for (c0, r0, c1, r1, _k) in getattr(lv, 'grown', ()):
        if rng.random() < 0.4:
            c, r = (c0 + c1) // 2, (r0 + r1) // 2
            x, z = lv.center(c, r)
            lv.bulb(b, x, lv.y0 + 4.0, z, float(lv.ceil[r, c]), rad=10.0)


def _outside(lv, b):
    """The snowy hillside in front of the cave mouth: a cliff, deep snow, pines."""
    rng = random.Random(77)
    y0 = lv.y0
    zc = lv.oz
    mx0 = lv.ox + 13 * C
    mx1 = lv.ox + 15 * C
    xl, xr = lv.ox + 4, lv.ox + lv.cols * C - 4
    snow = (2.0, 2.05, 2.25)
    # snow ground, gently rolling
    xs = np.arange(xl - 20, xr + 20.01, 2.0)
    zs = np.arange(zc - 80, zc + 0.01, 2.0)
    X, Z = np.meshgrid(xs, zs)
    H = y0 + 0.25 * np.sin(X * 0.3) * np.cos(Z * 0.25) * np.clip((zc - Z - 3) / 6, 0, 1)
    N = np.zeros(H.shape + (3,))
    N[..., 1] = 1.0
    V = np.zeros(H.shape + (12,), np.float32)
    V[..., 0], V[..., 1], V[..., 2] = X, H, Z
    V[..., 3:6] = N
    V[..., 6], V[..., 7] = X * 0.3, Z * 0.3
    V[..., 8:11] = snow
    V[..., 11] = L.CONCRETE
    nz, nx = H.shape
    j, i = np.mgrid[0:nz - 1, 0:nx - 1]
    tris = np.stack([V[j, i], V[j, i + 1], V[j + 1, i + 1], V[j, i], V[j + 1, i + 1], V[j + 1, i]], axis=2)
    b.add_array(tris.reshape(-1, 12))
    # the cliff face, with the mouth cut into it
    rockc = (0.55, 0.52, 0.5)
    b.box(((xl - 20 + mx0) / 2, y0 + 9, zc - 0.5), (mx0 - xl + 20, 18, 1.0), L.CONCRETE, rockc)
    b.box(((mx1 + xr + 20) / 2, y0 + 9, zc - 0.5), (xr + 20 - mx1, 18, 1.0), L.CONCRETE, rockc)
    b.box(((mx0 + mx1) / 2, y0 + 6.5 + 5.75, zc - 0.5), (mx1 - mx0, 11.5, 1.0), L.CONCRETE, rockc)
    for _ in range(40):
        x = rng.uniform(xl - 18, xr + 18)
        if mx0 - 1 < x < mx1 + 1:
            continue
        sz = rng.uniform(1.0, 3.5)
        m = T(x, y0 + rng.uniform(0, 14), zc - 1.0) @ RY(rng.random()) @ RZ(rng.uniform(-0.4, 0.4))
        b.box((0, 0, 0), (sz * 1.4, sz, sz), L.CONCRETE, (0.5, 0.48, 0.46), m=m)
        b.box((0, sz * 0.52, 0), (sz * 1.3, 0.12, sz * 0.9), L.CONCRETE, snow, m=m)
    # snow piled in the mouth
    b.cylinder(1.6, 0.4, 0.6, 9, L.CONCRETE, snow, m=T(mx0 + 0.5, y0, zc + 0.6), cap=True)
    # snow-laden pines, clear of the path straight out from the mouth
    for _ in range(140):
        x = rng.uniform(xl - 18, xr + 18)
        z = rng.uniform(zc - 78, zc - 5)
        if abs(x - (mx0 + mx1) / 2) < 7 and z > zc - 60:
            continue
        ht = rng.uniform(9, 15)
        b.cylinder(0.3, 0.1, ht, 6, L.BARK, (0.8, 0.8, 0.8), m=T(x, y0 - 0.2, z))
        for k in range(3):
            y = ht * (0.32 + 0.22 * k)
            rad = (2.6 - 0.7 * k) * rng.uniform(0.85, 1.1)
            b.cylinder(rad, 0.0, 3.4 - 0.5 * k, 7, L.NEEDLES, (1.0, 1.05, 1.05), m=T(x, y0 + y, z))
            b.cylinder(rad * 0.85, 0.0, (3.4 - 0.5 * k) * 0.55, 7, L.CONCRETE, (1.9, 1.95, 2.15), m=T(x, y0 + y + 1.2, z))


# ---------------------------------------------------------------------- deep snow over the old maps
def snow_cover(hfunc, x0, x1, z0, z1, step, lift, min_h=None):
    """A white blanket a little above a terrain: knee-deep snow."""
    b = MeshBuilder()
    xs = np.arange(x0, x1 + 0.01, step)
    zs = np.arange(z0, z1 + 0.01, step)
    X, Z = np.meshgrid(xs, zs)
    H = hfunc(X, Z)
    keep = np.ones_like(H, bool) if min_h is None else (H > min_h)
    Hs = H + lift + 0.12 * np.sin(X * 0.7) * np.cos(Z * 0.6)
    gx = np.gradient(Hs, step, axis=1)
    gz = np.gradient(Hs, step, axis=0)
    N = np.stack([-gx, np.ones_like(H), -gz], -1)
    N /= np.linalg.norm(N, axis=-1, keepdims=True)
    V = np.zeros(H.shape + (12,), np.float32)
    V[..., 0], V[..., 1], V[..., 2] = X, Hs, Z
    V[..., 3:6] = N
    V[..., 6], V[..., 7] = X * 0.3, Z * 0.3
    V[..., 8:11] = (2.0, 2.05, 2.25)
    V[..., 11] = L.CONCRETE
    nz, nx = H.shape
    j, i = np.mgrid[0:nz - 1, 0:nx - 1]
    ok = keep[j, i] & keep[j, i + 1] & keep[j + 1, i] & keep[j + 1, i + 1]
    j, i = j[ok], i[ok]
    tris = np.stack([V[j, i], V[j, i + 1], V[j + 1, i + 1], V[j, i], V[j + 1, i + 1], V[j + 1, i]], axis=1)
    b.add_array(tris.reshape(-1, 12))
    return b.array()


# ---------------------------------------------------------------------- small meshes
def lever_handle_mesh():
    b = MeshBuilder()
    b.box((0, 0.22, 0), (0.06, 0.45, 0.06), L.METAL, (0.55, 0.55, 0.55))
    b.box((0, 0.46, 0), (0.14, 0.1, 0.1), L.BLACK)
    return b.array()


def lever_box_mesh():
    """The housing a lever handle sits in (drawn at the lever's position and facing)."""
    b = MeshBuilder()
    b.box((0, 0, -0.12), (0.4, 0.7, 0.1), L.METAL, (0.5, 0.48, 0.45))
    b.box((0, 0.42, -0.1), (0.5, 0.08, 0.14), L.METAL, (0.85, 0.7, 0.2))       # yellow warning bar
    b.box((0.14, 1.2, -0.15), (0.04, 2.0, 0.04), L.BLACK)                      # a cable up the wall
    return b.array()


def shaft_mesh(depth=70.0):
    """The elevator shaft under the upper mine: rock walls, timber braces, guide rails, cables.
    Top at y = 0 (place it at the level's floor); open at the top."""
    b = MeshBuilder()
    rng = random.Random(9)
    hw = C / 2
    rock = (0.5, 0.46, 0.42)
    for (ax, az), (bx, bz) in (((-hw, -hw), (hw, -hw)), ((hw, -hw), (hw, hw)), ((hw, hw), (-hw, hw)), ((-hw, hw), (-hw, -hw))):
        y = 0.0
        while y > -depth:
            b.quad_world((ax, y - 3.0, az), (bx, y - 3.0, bz), (bx, y, bz), (ax, y, az), L.CONCRETE, rock, 0.4,
                         axis='x' if ax == bx else 'z')
            y -= 3.0
    b.quad_world((-hw, -depth, -hw), (hw, -depth, -hw), (hw, -depth, hw), (-hw, -depth, hw), L.MUD, (0.3, 0.28, 0.26), 0.5)
    for k in range(int(depth / 3.0)):
        y = -1.5 - k * 3.0
        wood = (0.6 + rng.uniform(-0.05, 0.05), 0.48, 0.34)
        for sz in (-1, 1):
            b.box((0, y, sz * (hw - 0.09)), (C, 0.2, 0.16), L.WOOD, wood)
            b.box((sz * (hw - 0.09), y, 0), (0.16, 0.2, C), L.WOOD, wood)
        if k % 4 == 1:
            b.box((hw - 0.15, y + 0.5, 0.4), (0.1, 0.1, 0.1), L.GLOW + EMIS, (1.0, 0.6, 0.3))
    for sx in (-1, 1):
        b.box((sx * (hw - 0.12), -depth / 2, -hw + 0.2), (0.08, depth, 0.1), L.METAL, (0.5, 0.45, 0.4))
    for sx in (-0.3, 0.3):
        b.box((sx, -depth / 2, 0.0), (0.03, depth, 0.03), L.METAL, (0.35, 0.33, 0.3))
    return b.array()


def cart_mesh():
    """The ore cart you ride up the rail tunnel."""
    b = MeshBuilder()
    rust = (0.5, 0.42, 0.35)
    b.box((0, 0.42, 0), (1.05, 0.08, 1.5), L.METAL, rust)
    for sx in (-0.5, 0.5):
        b.box((sx, 0.72, 0), (0.06, 0.6, 1.5), L.METAL, rust)
    for sz in (-0.72, 0.72):
        b.box((0, 0.72, sz), (1.05, 0.6, 0.06), L.METAL, rust)
    b.box((0, 1.02, 0.72), (1.1, 0.06, 0.1), L.METAL, (0.35, 0.3, 0.28))
    for sz in (-0.5, 0.5):
        for sx in (-0.42, 0.42):
            b.cylinder(0.17, 0.17, 0.08, 8, L.BLACK, m=T(sx, 0.18, sz) @ RZ(math.pi / 2) @ T(0, -0.04, 0))
    b.box((0, 0.25, 0.8), (0.4, 0.2, 0.12), L.METAL, (0.35, 0.33, 0.3))              # the motor
    b.box((0.35, 1.1, -0.6), (0.08, 0.5, 0.08), L.METAL, (0.85, 0.7, 0.2))           # the throttle lever
    return b.array()


def plank_mesh():
    """Boards nailed across the rail tunnel."""
    b = MeshBuilder()
    for k, (y, a) in enumerate(((0.45, 0.05), (1.05, -0.08), (1.65, 0.04), (2.1, -0.03))):
        b.box((0, y, 0), (2.05, 0.24, 0.08), L.WOOD, (0.62 + 0.05 * (k % 2), 0.5, 0.36), m=RZ(a))
    b.box((0, 1.2, -0.06), (0.22, 2.3, 0.06), L.WOOD, (0.5, 0.4, 0.3), m=RZ(0.6))
    b.facing_quad((0.3, 1.35, 0.05), (0, 0, 1), 0.7, 0.45, L.SIGN, (0.9, 0.85, 0.7))
    return b.array()


def cage_mesh():
    b = MeshBuilder()
    st = (0.45, 0.42, 0.4)
    b.box((0, 0.05, 0), (1.8, 0.1, 1.8), L.GRATE, (0.7, 0.7, 0.7))
    for sx in (-0.88, 0.88):
        for sz in (-0.88, 0.88):
            b.box((sx, 1.25, sz), (0.08, 2.5, 0.08), L.METAL, st)
    for y in (1.0, 2.45):
        for s in (-0.88, 0.88):
            b.box((s, y, 0), (0.05, 0.05, 1.8), L.METAL, st)
            b.box((0, y, s), (1.8, 0.05, 0.05), L.METAL, st)
    b.box((0, 2.5, 0), (1.8, 0.06, 1.8), L.GRATE, (0.6, 0.6, 0.6))
    b.box((0, 2.6, 0), (0.1, 0.2, 0.1), L.METAL)
    return b.array()


# ---------------------------------------------------------------------- the Elk, hunting
class ElkHunter:
    """Hunts the caverns by LIGHT and MOVEMENT, like the Goat Man -- but it
    cannot fit into the timbered mineshafts. Hide in one and it waits at the
    opening, staring in, before it gives up and goes."""
    # it sees a long way, even in the dark, even when you hold still --
    # but it is slow: you can always out-walk it to a mineshaft
    LIGHT_RANGE = 60.0
    RUN_RANGE = 48.0
    WALK_RANGE = 40.0
    CREEP_RANGE = 32.0
    STILL_RANGE = 26.0
    CHASE_SPEED = 2.45
    SPEEDS = {'enter': 2.4, 'investigate': 2.2, 'leave': 2.0, 'roam': 1.8}
    KILL_DIST = 1.9
    CLOSE_RANGE = 0.0

    def __init__(self, lv, x, z):
        self.lv = lv
        self.x, self.z = x, z
        self.y = lv.y0
        self.yaw = 0.0
        self.state = 'roam'
        self.path = []
        self.target = None
        self.timer = 0.0
        self.sense_t = 0.0
        self.seen_t = 9.0
        self.last_seen = None
        self.grace = 0.0
        self.phase = 0.0
        self.amt = 0.0
        self.step = 0.0
        self.stuck = 0.0
        self.repath = 0.0
        self.search_yaw = 0.0
        self.events = []
        self.rng = random.Random()

    def go_to(self, tx, tz):
        lv = self.lv
        goal = lv.cell_of(tx, tz)
        if not lv.open_cell(*goal, elk=True):
            goal = lv.nearest_elk_cell(*goal)
            if goal is None:
                self.path = []
                return
        start = lv.cell_of(self.x, self.z)
        if not lv.open_cell(*start, elk=True):
            start = lv.nearest_elk_cell(*start) or start
        p = lv.astar(start, goal, elk=True)
        self.path = [lv.center(c, r) for c, r in (p[1:] if p else [])]
        if lv.open_cell(*lv.cell_of(tx, tz), elk=True) and self.path:
            self.path[-1] = (tx, tz)

    def hear(self, x, z, radius):
        if self.grace > 0 or self.state in ('chase', 'search', 'enter'):
            return
        if math.hypot(x - self.x, z - self.z) < radius:
            self.state = 'investigate'
            self.timer = 0.0
            self.go_to(x, z)

    def update(self, dt, player, lantern_on):
        lv = self.lv
        self.grace = max(0.0, self.grace - dt)
        px, pz = player.x, player.z
        dx, dz = px - self.x, pz - self.z
        dist = math.hypot(dx, dz)
        pspeed = math.hypot(getattr(player, 'vx', 0.0), getattr(player, 'vz', 0.0))
        moving = pspeed > 0.35
        if lantern_on:
            reach, wide = self.LIGHT_RANGE, True
        elif not moving:
            reach, wide = self.STILL_RANGE, False
        elif player.crouch > 0.5:
            reach, wide = self.CREEP_RANGE, False
        elif getattr(player, 'sprinting', False):
            reach, wide = self.RUN_RANGE, True
        else:
            reach, wide = self.WALK_RANGE, False
        self.sense_t -= dt
        reach = max(reach, self.CLOSE_RANGE)
        in_shaft = not lv.open_cell(*lv.cell_of(px, pz), elk=True)
        if in_shaft and self.STILL_RANGE > 0:
            reach = 0.0          # it knows it can't get you in there
        if self.sense_t <= 0 and self.grace <= 0 and self.state != 'enter':
            self.sense_t = 0.15
            fx, fz = math.sin(self.yaw), math.cos(self.yaw)
            facing = (fx * dx + fz * dz) / max(dist, 1e-4)
            if dist < reach and (wide or facing > 0.1 or dist < 6 or self.state in ('chase', 'search')) \
                    and lv.los(self.x, self.z, px, pz):
                if self.state != 'chase':
                    self.events.append('roar')
                self.state = 'chase'
                self.seen_t = 0.0
                self.last_seen = (px, pz)
        speed = 0.0
        st = self.state
        target = None
        pc = lv.cell_of(px, pz)
        hidden = not lv.open_cell(*pc, elk=True)       # you are in a mineshaft it can't fit into
        if st == 'enter':
            speed = self.SPEEDS['enter']
            if not self.path:
                self.state = 'roam'
                self.timer = 2.0
        elif st == 'chase':
            speed = self.CHASE_SPEED
            self.seen_t += dt
            if hidden:
                # it can't follow you in: go to the opening and stare in
                self.repath -= dt
                if self.repath <= 0:
                    self.repath = 0.5
                    self.go_to(px, pz)
                if not self.path or dist < 3.2:
                    self.state = 'search'
                    self.timer = 0.0
                    self.search_yaw = math.atan2(dx, dz)
                    self.events.append('lost')
            else:
                if self.seen_t < 0.3 and lv.los(self.x, self.z, px, pz):
                    target = (px, pz)
                    self.path = []
                elif self.seen_t < 0.7:
                    self.repath -= dt
                    if self.repath <= 0:
                        self.repath = 0.5
                        self.go_to(px, pz)
                else:
                    self.state = 'search'
                    self.timer = 0.0
                    self.path = []
                    self.search_yaw = math.atan2(self.last_seen[0] - self.x, self.last_seen[1] - self.z) \
                        if self.last_seen else self.yaw
                    self.events.append('lost')
                if dist < self.KILL_DIST and self.seen_t < 0.6:
                    self.events.append('kill')
        elif st == 'search':
            self.timer += dt
            want = self.search_yaw if self.timer < 2.8 else \
                self.search_yaw + 1.2 * math.sin((self.timer - 2.8) * 1.5) + 0.4 * math.sin(self.timer * 3.7)
            d = (want - self.yaw + math.pi) % (2 * math.pi) - math.pi
            self.yaw += d * min(1.0, dt * 4)
            if self.timer > 7.2:
                cells = [c for c in lv.elk_cells() if math.hypot(lv.center(*c)[0] - px, lv.center(*c)[1] - pz) > 26]
                if cells:
                    self.go_to(*lv.center(*self.rng.choice(cells)))
                self.state = 'leave'
                self.events.append('leave')
        elif st == 'investigate':
            speed = self.SPEEDS['investigate']
            if not self.path:
                speed = 0.0
                self.timer += dt
                self.yaw += math.sin(self.timer * 1.6) * dt * 1.4
                if self.timer > 4.0:
                    self.state = 'roam'
                    self.timer = 1.0
        elif st == 'leave':
            speed = self.SPEEDS['leave']
            if not self.path:
                self.state = 'roam'
                self.timer = self.rng.uniform(6, 11)
        else:   # roam
            speed = self.SPEEDS['roam']
            if not self.path:
                speed = 0.0
                self.timer -= dt
                if self.timer <= 0:
                    cells = lv.elk_cells()
                    near = [c for c in cells if abs(lv.center(*c)[0] - px) + abs(lv.center(*c)[1] - pz) < 24]
                    pick = self.rng.choice(near if (near and self.rng.random() < 0.55) else cells)
                    self.go_to(*lv.center(*pick))
                    self.timer = self.rng.uniform(1.5, 4.0)
        if target is None and self.path:
            while len(self.path) > 1 and lv.los(self.x, self.z, *self.path[1]) and \
                    math.hypot(self.path[1][0] - self.x, self.path[1][1] - self.z) < 7:
                self.path.pop(0)
            target = self.path[0]
            if math.hypot(target[0] - self.x, target[1] - self.z) < 0.6:
                self.path.pop(0)
                target = self.path[0] if self.path else None
        moved = 0.0
        if target is not None and speed > 0:
            mx, mz = target[0] - self.x, target[1] - self.z
            md = math.hypot(mx, mz)
            if md > 1e-3:
                st_ = min(md, speed * dt)
                outside = self.z < lv.oz and lv.has_outside
                if outside:
                    nx, nz = self.x + mx / md * st_, self.z + mz / md * st_
                else:
                    nx, nz = lv.collide(self.x + mx / md * st_, self.z + mz / md * st_, 0.75, elk=True)
                moved = math.hypot(nx - self.x, nz - self.z)
                self.x, self.z = nx, nz
                a = math.atan2(mx, mz)
                d = (a - self.yaw + math.pi) % (2 * math.pi) - math.pi
                self.yaw += d * min(1.0, dt * (5 if st == 'chase' else 2.5))
        if speed > 0 and moved < speed * dt * 0.2:
            self.stuck += dt
            if self.stuck > 1.5:
                self.stuck = 0.0
                self.path = []
                self.repath = 0.0
                if st == 'roam':
                    self.timer = 0.0
        else:
            self.stuck = 0.0
        self.amt += (min(1.0, moved / max(dt, 1e-4) / 2.4) - self.amt) * min(1.0, dt * 6)
        self.phase += moved * 1.2
        self.step += moved
        if self.step > 1.8:
            self.step = 0.0
            self.events.append('step')
