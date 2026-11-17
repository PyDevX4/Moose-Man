"""Level data: forest, storm drain, sewer grid, collisions, geometry, props."""
import math
import random
import heapq
import numpy as np

from engine import MeshBuilder, T, S, RX, RY, RZ, pipe
from textures import L, EMIS

C = 2.0
OX = -11.0
OZ = 48.0
COLS = 92
ROWS = 112
STEP = 0.66
SEWER_FLOOR = -5.0

PATH_PTS = [(0, -62), (0, -48), (4, -30), (-3, -15), (5, 0), (2, 15), (-4, 28), (0, 40), (0, 47.5)]
CAMPFIRE = (9.0, 8.0)
# the two flood-gate release levers out in the woods (x, z, yaw the handle faces)
C1_LEVERS = [(-23.0, 24.0, math.pi / 2), (21.0, -9.0, -math.pi / 2)]
KEYGATE = (19, 48)                  # the ladder shaft cell; its gate is on the south edge
START = (0.0, -50.0)

# ---- the escape: a manhole in the eastern woods, and Route 9 beyond it
MANHOLE = (26.0, 18.0)
ROAD_X0, ROAD_X1 = 48.5, 55.5      # asphalt edges (the road runs north-south)
ROAD_MID = (ROAD_X0 + ROAD_X1) / 2
STREETLIGHT = (57.2, 18.0)
ESCAPE_Z = (6.0, 30.0)             # how far north/south the player may wander while escaping


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def cell_center(c, r):
    return (OX + (c + 0.5) * C, OZ + (r + 0.5) * C)


def cell_of(x, z):
    return int(math.floor((x - OX) / C)), int(math.floor((z - OZ) / C))


def terrain_h(x, z):
    h = (0.45 * np.sin(x * 0.13 + 1.3) * np.cos(z * 0.11) + 0.3 * np.sin(x * 0.31 + z * 0.17)
         + 0.18 * np.cos(x * 0.53 - z * 0.41) + 0.6 * np.sin(x * 0.05) * np.sin(z * 0.045 + 0.7))
    d = np.hypot(x, z - 48.0)
    k = np.clip((d - 3.0) / 10.0, 0, 1)
    k = k * k * (3 - 2 * k)
    # the road bed is graded flat
    kr = np.clip((np.abs(x - ROAD_MID) - 5.0) / 5.0, 0, 1)
    kr = kr * kr * (3 - 2 * kr)
    return h * k * kr


def keep_clear(x, z, margin):
    """Where nothing may grow: the road corridor and the manhole clearing."""
    if ROAD_X0 - 5.5 - margin < x < ROAD_X1 + 5.5 + margin:
        return True
    return math.hypot(x - MANHOLE[0], z - MANHOLE[1]) < 4.0 + margin


def path_dist(x, z):
    x = np.asarray(x, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)
    best = np.full(np.broadcast(x, z).shape, 1e9)
    for (ax, az), (bx, bz) in zip(PATH_PTS[:-1], PATH_PTS[1:]):
        vx, vz = bx - ax, bz - az
        L2 = vx * vx + vz * vz
        t = np.clip(((x - ax) * vx + (z - az) * vz) / L2, 0, 1)
        px, pz = ax + t * vx, az + t * vz
        best = np.minimum(best, np.hypot(x - px, z - pz))
    return best


ROOMS = {
    'tunnel': (5, 0, 16, 16),
    'junction': (7, 17, 11, 20),
    'gallery': (2, 21, 37, 26),
    'cistern': (1, 27, 10, 36),
    'pump': (26, 13, 34, 21),
    'office': (13, 17, 17, 21),
    'backroom': (18, 17, 22, 19),
    'holding': (15, 31, 25, 37),
    'holding_hall': (20, 27, 20, 30),
    'nest': (32, 27, 38, 35),
    'chamber': (6, 38, 32, 48),
    'filter': (36, 11, 44, 18),
    'storage': (40, 28, 46, 36),
    'works': (2, 48, 44, 52),
    'lockers': (2, 53, 7, 59),
    'genroom': (10, 53, 15, 60),
    'cells': (18, 53, 23, 58),
    'shrine': (26, 53, 31, 62),
    'records': (34, 53, 40, 59),
    'cages': (42, 53, 46, 60),
    'tank': (8, 61, 32, 66),
}


class World:
    def __init__(self):
        self.build_grid()
        self.trees = []
        self.tree_hash = {}
        self.forest_boxes = [(-70.0, 46.5, -6.5, 80.0), (6.5, 46.5, 70.0, 80.0)]
        self.notes = {}
        self.valves = []
        self.lights = []
        self.herd = []
        self.drip_points = []
        self.drained = False
        self.water_level = -5.3
        self.water_target = -5.3
        self.ladder_pos = None
        self.c1_levers = []
        self.grate_open = 0.0           # the flood grate over the drain: 0 shut .. 1 up
        self.keygate_open = 0.0         # the gate in front of the ladder
        self.key_pos = None
        self.x_limit = 54.0          # widened to reach the road during the escape

    # ------------------------------------------------------------------ grid
    def build_grid(self):
        g = [['#'] * COLS for _ in range(ROWS)]

        def carve(c0, r0, c1, r1, ch='.'):
            for r in range(min(r0, r1), max(r0, r1) + 1):
                for c in range(min(c0, c1), max(c0, c1) + 1):
                    g[r][c] = ch

        carve(5, 0, 5, 6, 't')
        carve(5, 6, 16, 6, 't')
        carve(16, 6, 16, 12, 't')
        carve(9, 12, 16, 12, 't')
        carve(9, 12, 9, 16, 't')
        carve(7, 17, 11, 20)          # junction
        carve(9, 21, 9, 21)
        carve(2, 22, 37, 26)          # gallery
        carve(2, 24, 37, 24, '~')
        for c in (9, 20, 31):
            g[24][c] = '.'
        carve(3, 27, 3, 27)
        carve(1, 28, 10, 36)          # cistern
        for c in (3, 6, 9):
            for r in (30, 33):
                g[r][c] = '#'
        carve(30, 17, 30, 21)
        carve(26, 13, 34, 16)         # pump room
        carve(15, 21, 15, 21)
        carve(13, 17, 17, 20)         # office
        carve(18, 18, 18, 18)
        carve(19, 17, 22, 19)         # back room
        carve(20, 27, 20, 30)
        carve(15, 31, 25, 37)         # holding room
        carve(36, 27, 36, 28)
        carve(32, 29, 38, 35)         # nest
        carve(12, 27, 12, 38)         # corridor to chamber
        carve(6, 39, 32, 40)          # chamber south walkway
        carve(6, 41, 32, 45, 'W')     # basin
        carve(6, 46, 32, 47)          # chamber north walkway
        for c in (18, 19, 20):
            for r in (41, 42, 44, 45):
                g[r][c] = 'S'
        carve(19, 48, 19, 48, 'X')
        # ---- east of the pump room: the filter room
        carve(35, 14, 35, 14)
        carve(36, 11, 44, 18)
        for (c, r) in ((38, 13), (42, 13), (38, 16), (42, 16)):
            g[r][c] = '#'
        # ---- past the nest: flooded storage
        carve(39, 29, 39, 29)
        carve(40, 28, 46, 36)
        # ---- north of Chamber C (only reachable once it's drained): the old works
        carve(8, 48, 8, 50)
        carve(30, 48, 30, 50)
        carve(2, 51, 44, 52)            # the long hall
        for door, room in (((4, 53), (2, 54, 7, 59)), ((12, 53), (10, 54, 15, 60)), ((20, 53), (18, 54, 23, 58)),
                           ((28, 53), (26, 54, 31, 60)), ((37, 53), (34, 54, 40, 59)), ((44, 53), (42, 54, 46, 60))):
            carve(door[0], door[1], door[0], door[1])
            carve(*room)
        for (c, r) in ((13, 57), (36, 56), (38, 56)):
            g[r][c] = '#'
        carve(12, 61, 12, 62)
        carve(28, 61, 28, 62)
        carve(8, 63, 32, 66)            # the settling tank
        for c in (14, 20, 26):
            g[64][c] = '#'
        # ---- and half as much again: rooms and tunnels grown out of the rock around it all.
        # The flooded basin is a barrier, so nothing new is a way round draining it.
        from gridgrow import grow
        keep = {(c, r) for r in range(0, 21) for c in range(0, 20)}            # the storm drain and junction
        keep |= {(c, r) for r in range(44, 52) for c in range(16, 24)}         # around the ladder shaft
        self.grown = grow(g, random.Random(4417), factor=1.5, passable='.~tWSX', connect_to='.',
                          room_kinds='.', barrier='WS', bounds=(1, 1, COLS - 2, ROWS - 2), room_w=(3, 9),
                          room_h=(3, 8), keep_out=keep, tries=40000)
        self.g = g

        fl = np.full((ROWS, COLS), SEWER_FLOOR)
        ce = np.full((ROWS, COLS), -1.0)
        self.stairs = {}
        self.basin = np.zeros((ROWS, COLS), bool)
        for r in range(ROWS):
            for c in range(COLS):
                k = g[r][c]
                if k == '~':
                    fl[r, c] = -5.6
                elif k in 'WS':
                    fl[r, c] = -8.0
                    self.basin[r, c] = True
        for (c0, r0, c1, r1), h in (((2, 22, 37, 26), 0.0), ((15, 31, 25, 37), -1.6), ((6, 39, 32, 47), 1.0)):
            ce[r0:r1 + 1, c0:c1 + 1] = h
        ce[48, 19] = 6.0
        for c in (18, 19, 20):
            self.stairs[(c, 41)] = (-5.0, -6.5)
            self.stairs[(c, 42)] = (-6.5, -8.0)
            self.stairs[(c, 44)] = (-8.0, -6.5)
            self.stairs[(c, 45)] = (-6.5, -5.0)
        for (c, r), (hs, hn) in self.stairs.items():
            fl[r, c] = min(hs, hn)
        # tunnel heights from BFS distance
        dist = {(5, 0): 0}
        q = [(5, 0)]
        while q:
            c, r = q.pop(0)
            for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nc, nr = c + dc, r + dr
                if 0 <= nr < ROWS and 0 <= nc < COLS and g[nr][nc] == 't' and (nc, nr) not in dist:
                    dist[(nc, nr)] = dist[(c, r)] + 1
                    q.append((nc, nr))
        dmax = max(dist.values())
        self.tunnel_dist = dist
        for (c, r), d in dist.items():
            fl[r, c] = SEWER_FLOOR * (d // 2) / (dmax // 2)
            ce[r, c] = fl[r, c] + 2.4
        self.floor = fl
        self.ceil = ce

    def kind(self, c, r):
        if 0 <= r < ROWS and 0 <= c < COLS:
            return self.g[r][c]
        return '#'

    def floor_cell(self, c, r, z):
        st = self.stairs.get((c, r))
        if st:
            t = clamp((z - OZ) / C - r, 0.0, 1.0)
            return st[0] + (st[1] - st[0]) * t
        return float(self.floor[r, c])

    def edge_floor(self, c, r, side):
        st = self.stairs.get((c, r))
        if st:
            if side == 'S':
                return st[0]
            if side == 'N':
                return st[1]
            return min(st)
        return float(self.floor[r, c])

    def floor_at(self, x, z):
        c, r = cell_of(x, z)
        if 0 <= r < ROWS and 0 <= c < COLS and self.g[r][c] != '#':
            return self.floor_cell(c, r, z)
        return None

    def ground_at(self, x, z):
        v = self.floor_at(x, z)
        if v is None and z < OZ:
            return float(terrain_h(x, z))
        return v

    def in_grid(self, x, z):
        c, r = cell_of(x, z)
        return 0 <= r < ROWS and 0 <= c < COLS and self.g[r][c] != '#'

    def room_of(self, x, z):
        c, r = cell_of(x, z)
        if r < 0:
            return 'forest'
        for name, (c0, r0, c1, r1) in ROOMS.items():
            if c0 <= c <= c1 and r0 <= r <= r1 and self.kind(c, r) != '#':
                return name
        return 'sewer'

    def water_depth_block(self, c, r):
        return self.basin[r, c] and not self.drained

    def cell_blocked(self, c, r, y, px, pz):
        if r < 0:
            return False
        if r >= ROWS or c < 0 or c >= COLS:
            return True
        if self.g[r][c] == '#':
            return True
        if self.basin[r, c] and not self.drained:
            return True
        z0 = OZ + r * C
        cz = clamp(pz, z0, z0 + C)
        return self.floor_cell(c, r, cz) > y + STEP

    def collide(self, x, z, rad, y, forest=True):
        hit_water = False
        for _ in range(3):
            c0, r0 = cell_of(x - rad, z - rad)
            c1, r1 = cell_of(x + rad, z + rad)
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    if self.cell_blocked(c, r, y, x, z):
                        if 0 <= r < ROWS and 0 <= c < COLS and self.basin[r, c] and not self.drained:
                            hit_water = True
                        x0 = OX + c * C
                        z0 = OZ + r * C
                        nx = clamp(x, x0, x0 + C)
                        nz = clamp(z, z0, z0 + C)
                        dx, dz = x - nx, z - nz
                        d2 = dx * dx + dz * dz
                        if d2 < rad * rad:
                            if d2 > 1e-10:
                                d = math.sqrt(d2)
                                push = rad - d
                                x += dx / d * push
                                z += dz / d * push
                            else:
                                # inside: push out the nearest side
                                opts = [(x - x0, -1, 0), (x0 + C - x, 1, 0), (z - z0, 0, -1), (z0 + C - z, 0, 1)]
                                dmin, sx, sz = min(opts)
                                x += sx * (dmin + rad)
                                z += sz * (dmin + rad)
            if forest and z < OZ + 1.0:
                for bx0, bz0, bx1, bz1 in self.forest_boxes:
                    nx = clamp(x, bx0, bx1)
                    nz = clamp(z, bz0, bz1)
                    dx, dz = x - nx, z - nz
                    d2 = dx * dx + dz * dz
                    if d2 < rad * rad:
                        if d2 > 1e-10:
                            d = math.sqrt(d2)
                            x += dx / d * (rad - d)
                            z += dz / d * (rad - d)
                        else:
                            z = bz0 - rad
                hx, hz = int(x // 4), int(z // 4)
                for i in (hx - 1, hx, hx + 1):
                    for j in (hz - 1, hz, hz + 1):
                        for tx, tz, tr in self.tree_hash.get((i, j), ()):
                            dx, dz = x - tx, z - tz
                            d = math.hypot(dx, dz)
                            mn = tr + rad
                            if d < mn and d > 1e-6:
                                x += dx / d * (mn - d)
                                z += dz / d * (mn - d)
                x = clamp(x, -54.0, self.x_limit)
                z = max(z, -60.0)
        return x, z, hit_water

    def los(self, x0, z0, x1, z1):
        dx, dz = x1 - x0, z1 - z0
        d = math.hypot(dx, dz)
        n = int(d / 0.35) + 1
        for i in range(1, n):
            t = i / n
            c, r = cell_of(x0 + dx * t, z0 + dz * t)
            if r < 0:
                continue
            if self.kind(c, r) == '#':
                return False
        return True

    def passable(self, a, b, side):
        c, r = b
        if self.kind(c, r) == '#':
            return False
        if self.basin[r, c] and not self.drained:
            return False
        opp = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}[side]
        if (a in self.stairs and side in 'EW') or (b in self.stairs and side in 'EW'):
            return False
        return abs(self.edge_floor(a[0], a[1], side) - self.edge_floor(c, r, opp)) <= 0.7

    def astar(self, start, goal, max_nodes=14000):
        if start == goal:
            return [goal]
        if self.kind(*goal) == '#':
            return None
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
            for dc, dr, side in ((0, 1, 'N'), (0, -1, 'S'), (1, 0, 'E'), (-1, 0, 'W')):
                nb = (c + dc, r + dr)
                if not (0 <= nb[0] < COLS and 0 <= nb[1] < ROWS):
                    continue
                if not self.passable(cur, nb, side):
                    continue
                nc = cost[cur] + 1
                if nb not in cost or nc < cost[nb]:
                    cost[nb] = nc
                    came[nb] = cur
                    h = abs(nb[0] - goal[0]) + abs(nb[1] - goal[1])
                    heapq.heappush(openq, (nc + h, nb))
        if goal not in came:
            return None
        path = []
        cur = goal
        while cur is not None:
            path.append(cur)
            cur = came[cur]
        path.reverse()
        return path

    def sewer_cells(self):
        out = []
        for r in range(17, ROWS):
            for c in range(COLS):
                k = self.g[r][c]
                if k in '.~' and not self.basin[r, c]:
                    out.append((c, r))
        return out

    # ------------------------------------------------------------------ forest
    def add_tree(self, x, z, r):
        self.trees.append((x, z, r))
        self.tree_hash.setdefault((int(x // 4), int(z // 4)), []).append((x, z, r))

    def near_tree(self, x, z, mind):
        hx, hz = int(x // 4), int(z // 4)
        for i in (hx - 1, hx, hx + 1):
            for j in (hz - 1, hz, hz + 1):
                for tx, tz, tr in self.tree_hash.get((i, j), ()):
                    if math.hypot(x - tx, z - tz) < mind:
                        return True
        return False

    def build_forest(self):
        b = MeshBuilder()
        rng = random.Random(2003)

        # terrain (vectorised)
        xs = np.arange(-64, 65, 1.0)
        zs = np.arange(-64, 48.01, 1.0)
        self._terrain_grid(b, xs, zs, lambda X, Z: terrain_h(X, Z), path_tint=True)
        # hill behind the culvert
        xs2 = np.arange(-64, 65, 2.0)
        zs2 = np.arange(48, 92.01, 2.0)

        def hill(X, Z):
            return 4.5 + (Z - 48) * 0.28 + 0.6 * np.sin(X * 0.21) * np.cos(Z * 0.17) * np.clip((Z - 48) / 4, 0, 1)
        self._terrain_grid(b, xs2, zs2, hill, path_tint=False, tint=(0.8, 0.8, 0.8))
        # embankment slopes
        for side in (-1, 1):
            x = 6.5
            while x < 64:
                xa, xb = side * x, side * (x + 1)
                ha, hb = float(terrain_h(xa, 46.5)), float(terrain_h(xb, 46.5))
                b.quad((xa, ha - 0.1, 46.5), (xb, hb - 0.1, 46.5), (xb, 4.5, 48.0), (xa, 4.5, 48.0), L.GRASS, (0.75, 0.7, 0.65))
                x += 1
        # culvert headwall
        conc = (0.85, 0.85, 0.82)
        b.box((-3.75, 2.0, 47.9), (5.5, 5.0, 0.2), L.CONCRETE, conc)
        b.box((3.75, 2.0, 47.9), (5.5, 5.0, 0.2), L.CONCRETE, conc)
        b.box((0.0, 3.45, 47.9), (2.0, 2.1, 0.2), L.CONCRETE, conc)
        b.box((0.0, 4.65, 47.9), (14.0, 0.35, 0.8), L.CONCRETE, conc)
        b.box((-6.7, 2.0, 47.15), (0.4, 5.0, 1.7), L.CONCRETE, conc)
        b.box((6.7, 2.0, 47.15), (0.4, 5.0, 1.7), L.CONCRETE, conc)
        b.box((0.0, -0.05, 47.3), (2.6, 0.12, 1.2), L.CONCRETE, (0.6, 0.6, 0.58))
        # the flood grate's guide rails (the grate itself is drawn separately: it lifts)
        for gx in (-1.04, 1.04):
            b.box((gx, 1.2, 47.72), (0.1, 2.5, 0.14), L.METAL, (0.5, 0.48, 0.45))
        b.facing_quad((-2.4, 1.5, 47.78), (0, 0, -1), 0.9, 0.6, L.SIGN, (0.85, 0.82, 0.7))
        # the release levers: on concrete posts, each with a red lamp so you can find them.
        # The posts are drawn on their own (c1_post_mesh) so a new game can move them.
        for lx, lz, yaw in C1_LEVERS:
            light = {'pos': (lx, 1.8, lz), 'rad': 5.0, 'col': (0.9, 0.1, 0.06), 'flicker': 'soft'}
            self.lights.append(light)
            lev = {'pos': (lx, 1.1, lz), 'yaw': yaw, 'pulled': False, 'progress': 0.0, 'angle': -0.8, 'light': light}
            self.c1_levers.append(lev)
            self.place_c1_lever(lev, lx, lz, yaw)
        self.forest_boxes.append((-6.9, 46.3, -6.5, 48.0))
        self.forest_boxes.append((6.5, 46.3, 6.9, 48.0))

        # special trees
        self.add_tree(2.6, -22.0, 0.33)
        self._pine(b, 2.6, -22.0, 0.33, 13.0, rng)
        self.add_tree(-5.6, 21.0, 0.35)
        self._dead_tree(b, -5.6, 21.0, 0.35, 9.0, rng, hang_branch=True)

        tries = 0
        while len(self.trees) < 440 and tries < 30000:
            tries += 1
            x = rng.uniform(-60, 64)
            z = rng.uniform(-63, 46)
            if float(path_dist(x, z)) < 2.7:
                continue
            if math.hypot(x - START[0], z - START[1]) < 5:
                continue
            if math.hypot(x - CAMPFIRE[0], z - CAMPFIRE[1]) < 6:
                continue
            if z > 39 and abs(x) < 10:
                continue
            if keep_clear(x, z, 0.0):
                continue
            if self.near_tree(x, z, 2.0):
                continue
            r = rng.uniform(0.18, 0.42)
            h = rng.uniform(9, 17)
            self.add_tree(x, z, r)
            if rng.random() < 0.72:
                self._pine(b, x, z, r, h, rng)
            else:
                self._dead_tree(b, x, z, r, h * 0.7, rng)
        # trees on the hill (no collision needed)
        for _ in range(110):
            x = rng.uniform(-60, 60)
            z = rng.uniform(50, 85)
            if abs(x) < 4 and z < 54:
                continue
            h0 = float(hill(x, z))
            self._pine(b, x, z, rng.uniform(0.2, 0.4), rng.uniform(9, 16), rng, base=h0 - 0.2)

        # bushes and rocks
        for _ in range(160):
            x = rng.uniform(-56, 56)
            z = rng.uniform(-62, 45)
            if float(path_dist(x, z)) < 1.8 or math.hypot(x - CAMPFIRE[0], z - CAMPFIRE[1]) < 4 or keep_clear(x, z, 1.0):
                continue
            h0 = float(terrain_h(x, z))
            rr = rng.uniform(0.5, 1.1)
            b.cylinder(rr, 0.05, rr * 1.3, 6, L.LEAVES, (0.9, 0.9, 0.9), m=T(x, h0 - 0.1, z) @ RY(rng.random() * 6))
        for _ in range(45):
            x = rng.uniform(-56, 56)
            z = rng.uniform(-62, 45)
            if float(path_dist(x, z)) < 2.0 or keep_clear(x, z, 1.5):
                continue
            h0 = float(terrain_h(x, z))
            sz = rng.uniform(0.4, 1.4)
            m = T(x, h0, z) @ RY(rng.random() * 6) @ RX(rng.uniform(-0.3, 0.3)) @ RZ(rng.uniform(-0.3, 0.3))
            b.box((0, sz * 0.2, 0), (sz * 1.3, sz * 0.8, sz), L.CONCRETE, (0.55, 0.55, 0.52), m=m)
            if sz > 0.9:
                self.add_tree(x, z, sz * 0.6)
        # fallen logs
        for _ in range(14):
            x = rng.uniform(-50, 50)
            z = rng.uniform(-58, 40)
            if float(path_dist(x, z)) < 4 or keep_clear(x, z, 4.0):
                continue
            h0 = float(terrain_h(x, z))
            a = rng.random() * 6.28
            ln = rng.uniform(3, 6)
            b.cylinder(0.25, 0.22, ln, 7, L.BARK, (0.7, 0.7, 0.7), m=T(x, h0 + 0.15, z) @ RY(a) @ RX(math.pi / 2) @ T(0, -ln / 2, 0))
            for k in range(-2, 3):
                self.add_tree(x + math.sin(a) * k * ln / 5, z + math.cos(a) * k * ln / 5, 0.3)

        self._campfire(b, rng)
        # the forest floor: stumps, mushrooms, ferns, branches, leaf piles
        import decor
        drng = random.Random(6101)
        spots = []
        for _ in range(900):
            x, z = drng.uniform(-60, 60), drng.uniform(-60, 44)
            if float(path_dist(x, z)) < 2.5 or self.near_tree(x, z, 0.9) or math.hypot(x, z - 48) < 10:
                continue
            if math.hypot(x - START[0], z - START[1]) < 4:
                continue
            spots.append((x, z))
            if len(spots) >= 420:
                break
        decor.forest_floor(b, spots, lambda x, z: float(terrain_h(x, z)), drng)
        self._forest_notes(b)
        self._deer(b)
        self._road(b)
        # drag marks to the culvert
        for i in range(10):
            z = 37.5 + i * 1.0
            x = 0.25 * math.sin(i * 0.9)
            h0 = float(terrain_h(x, z)) + 0.03
            b.quad((x - 0.35, h0, z), (x + 0.35, h0, z), (x + 0.35, h0, z + 1.1), (x - 0.35, h0, z + 1.1), L.BLOOD, (0.8, 0.8, 0.8),
                   uvs=((0, 0), (1, 0), (1, 1), (0, 1)))
        self.forest_data = b.array()

        mb = MeshBuilder()
        d = np.array([-0.35, 0.45, 1.0])
        d = d / np.linalg.norm(d)
        mc = d * 110.0
        mb.facing_quad(tuple(mc), tuple(-d), 9.0, 9.0, L.MOON + EMIS, (0.75, 0.78, 0.85))
        self.moon_data = mb.array()
        self.moon_dir = tuple(-d)

    def _terrain_grid(self, b, xs, zs, hfunc, path_tint=True, tint=(1, 1, 1)):
        X, Z = np.meshgrid(xs, zs)
        H = hfunc(X, Z)
        dx = xs[1] - xs[0]
        dz = zs[1] - zs[0]
        gx = np.gradient(H, dx, axis=1)
        gz = np.gradient(H, dz, axis=0)
        N = np.stack([-gx, np.ones_like(H), -gz], -1)
        N /= np.linalg.norm(N, axis=-1, keepdims=True)
        col = np.ones(H.shape + (3,)) * np.array(tint)
        if path_tint:
            pd = path_dist(X, Z)
            t = np.clip(1.6 - pd / 1.1, 0, 1)[..., None]
            col = col * (1 - t) + np.array((1.45, 1.1, 0.8)) * t
        V = np.zeros(H.shape + (12,), np.float32)
        V[..., 0] = X
        V[..., 1] = H
        V[..., 2] = Z
        V[..., 3:6] = N
        V[..., 6] = X * 0.25
        V[..., 7] = Z * 0.25
        V[..., 8:11] = col
        V[..., 11] = L.GRASS
        nz, nx = H.shape
        j, i = np.mgrid[0:nz - 1, 0:nx - 1]
        v00 = V[j, i]
        v10 = V[j, i + 1]
        v11 = V[j + 1, i + 1]
        v01 = V[j + 1, i]
        tris = np.stack([v00, v10, v11, v00, v11, v01], axis=2).reshape(-1, 12)
        b.add_array(tris)

    def _pine(self, b, x, z, r, h, rng, base=None):
        h0 = float(terrain_h(x, z)) - 0.2 if base is None else base
        m = T(x, h0, z)
        b.cylinder(r, r * 0.3, h, 7, L.BARK, (0.9, 0.9, 0.9), m=m)
        layers = 4
        for k in range(layers):
            y = h * (0.32 + 0.17 * k)
            rad = (2.6 - 0.5 * k) * rng.uniform(0.8, 1.15)
            ch = 3.2 - 0.3 * k
            sh = rng.uniform(0.75, 1.0)
            b.cylinder(rad, 0.0, ch, 8, L.NEEDLES, (sh, sh, sh), m=T(x, h0 + y, z) @ RY(rng.random() * 6.28))
        # a few dead low branches
        for _ in range(3):
            a = rng.random() * 6.28
            y = rng.uniform(1.5, h * 0.3)
            mm = T(x, h0 + y, z) @ RY(a) @ RZ(-1.2) @ T(0, 0.6, 0)
            b.box((0, 0, 0), (0.05, 1.2, 0.05), L.BARK, (0.8, 0.8, 0.8), m=mm)

    def _dead_tree(self, b, x, z, r, h, rng, hang_branch=False):
        h0 = float(terrain_h(x, z)) - 0.2
        b.cylinder(r, r * 0.25, h, 7, L.BARK, (0.75, 0.75, 0.75), m=T(x, h0, z))
        for _ in range(6):
            a = rng.random() * 6.28
            y = rng.uniform(h * 0.35, h * 0.9)
            ln = rng.uniform(1.0, 2.8)
            mm = T(x, h0 + y, z) @ RY(a) @ RZ(-rng.uniform(0.6, 1.2)) @ T(0, ln / 2, 0)
            b.box((0, 0, 0), (0.09, ln, 0.09), L.BARK, (0.7, 0.7, 0.7), m=mm)
        if hang_branch:
            b.box((x + 1.4, h0 + 3.6, z), (2.8, 0.14, 0.14), L.BARK, (0.7, 0.7, 0.7))

    def _campfire(self, b, rng):
        cx, cz = CAMPFIRE
        h0 = float(terrain_h(cx, cz))
        for i in range(9):
            a = i / 9 * 6.28
            b.box((cx + math.cos(a) * 0.75, h0 + 0.08, cz + math.sin(a) * 0.75), (0.28, 0.2, 0.22), L.CONCRETE, (0.5, 0.5, 0.5))
        for i in range(4):
            m = T(cx, h0 + 0.12, cz) @ RY(i * 0.8) @ RX(math.pi / 2) @ T(0, -0.55, 0)
            b.cylinder(0.07, 0.06, 1.1, 6, L.BARK, (0.25, 0.22, 0.2), m=m)
        for i in range(7):
            b.box((cx + rng.uniform(-0.3, 0.3), h0 + 0.05, cz + rng.uniform(-0.3, 0.3)), (0.08, 0.05, 0.08), L.GLOW + EMIS, (0.6, 0.12, 0.02))
        self.lights.append({'pos': (cx, h0 + 0.4, cz), 'rad': 5.0, 'col': (0.55, 0.16, 0.04), 'flicker': 'fire'})
        # abandoned backpack + flashlight
        b.box((cx + 1.6, h0 + 0.22, cz + 0.9), (0.4, 0.45, 0.25), L.CLOTH, (0.5, 0.6, 0.9), m=None)
        b.box((cx - 1.4, h0 + 0.06, cz + 1.2), (0.06, 0.06, 0.22), L.METAL, (0.4, 0.4, 0.4))
        # collapsed tent
        tx, tz = cx + 3.2, cz + 2.0
        th = float(terrain_h(tx, tz))
        b.quad((tx - 1.0, th, tz - 1.2), (tx - 1.0, th, tz + 1.2), (tx + 0.1, th + 0.9, tz + 1.2), (tx + 0.1, th + 0.9, tz - 1.2), L.CLOTH, (0.45, 0.6, 0.4))
        b.quad((tx + 1.0, th, tz - 1.2), (tx + 1.0, th, tz + 1.2), (tx + 0.1, th + 0.25, tz + 1.2), (tx + 0.4, th + 0.2, tz - 1.2), L.CLOTH, (0.45, 0.6, 0.4))
        b.box((tx + 0.1, th + 0.45, tz - 1.25), (0.04, 0.9, 0.04), L.METAL)
        self.add_tree(tx, tz, 1.1)
        self.add_tree(cx, cz, 0.6)
        # blood on the tent
        b.facing_quad((tx - 0.45, th + 0.47, tz - 1.21), (0, 0, -1), 0.8, 0.8, L.BLOOD)
        # the notebook page
        px, pz = cx + 0.9, cz - 1.0
        ph = float(terrain_h(px, pz)) + 0.03
        b.quad((px - 0.11, ph, pz - 0.14), (px + 0.11, ph, pz - 0.14), (px + 0.11, ph, pz + 0.14), (px - 0.11, ph, pz + 0.14), L.PAPER,
               uvs=((0, 0), (1, 0), (1, 1), (0, 1)))
        self.notes['notebook'] = {'pos': (px, ph + 0.05, pz), 'read': False}

    def _forest_notes(self, b):
        # flyer on the special tree, facing the path (-x)
        b.facing_quad((2.6 - 0.335, 1.6, -22.0), (-1, 0, 0), 0.42, 0.55, L.FLYER)
        self.notes['flyer'] = {'pos': (2.2, 1.6, -22.0), 'read': False}
        # county sign
        sx, sz = -3.2, 44.0
        h0 = float(terrain_h(sx, sz))
        b.box((sx - 0.55, h0 + 1.0, sz + 0.05), (0.08, 2.0, 0.08), L.WOOD)
        b.box((sx + 0.55, h0 + 1.0, sz + 0.05), (0.08, 2.0, 0.08), L.WOOD)
        b.box((sx, h0 + 1.55, sz + 0.06), (1.35, 1.0, 0.04), L.METAL)
        b.facing_quad((sx, h0 + 1.55, sz + 0.03), (0, 0, -1), 1.3, 0.95, L.SIGN)
        self.notes['sign'] = {'pos': (sx, h0 + 1.5, sz), 'read': False}

    def _road(self, b):
        """Route 9: two lanes of old asphalt, a sodium streetlight, and the
        manhole the player climbs out of."""
        z0, z1 = -64.0, 46.0
        y = 0.03
        asphalt = (0.42, 0.42, 0.45)
        z = z0
        while z < z1:
            zb = min(z1, z + 4.0)
            b.quad((ROAD_X0, y, z), (ROAD_X1, y, z), (ROAD_X1, y, zb), (ROAD_X0, y, zb), L.CONCRETE, asphalt,
                   uvs=((0, z * 0.3), (2.1, z * 0.3), (2.1, zb * 0.3), (0, zb * 0.3)))
            # gravel shoulders
            for xa, xb in ((ROAD_X0 - 1.2, ROAD_X0), (ROAD_X1, ROAD_X1 + 1.2)):
                b.quad((xa, y - 0.01, z), (xb, y - 0.01, z), (xb, y - 0.01, zb), (xa, y - 0.01, zb), L.MUD, (1.2, 1.15, 1.05),
                       uvs=((0, z * 0.5), (0.6, z * 0.5), (0.6, zb * 0.5), (0, zb * 0.5)))
            # faded edge lines
            for xe in (ROAD_X0 + 0.25, ROAD_X1 - 0.25):
                b.quad((xe - 0.06, y + 0.005, z), (xe + 0.06, y + 0.005, z), (xe + 0.06, y + 0.005, zb), (xe - 0.06, y + 0.005, zb),
                       L.GLOW, (0.45, 0.45, 0.42))
            z = zb
        # dashed yellow centre line
        z = z0
        while z < z1:
            for xo in (-0.09, 0.09):
                xm = ROAD_MID + xo
                b.quad((xm - 0.05, y + 0.006, z), (xm + 0.05, y + 0.006, z), (xm + 0.05, y + 0.006, z + 3.0),
                       (xm - 0.05, y + 0.006, z + 3.0), L.GLOW, (0.55, 0.42, 0.08))
            z += 6.0
        # sodium streetlight on the far shoulder, arm reaching over the road
        sx, sz = STREETLIGHT
        b.box((sx, 3.5, sz), (0.16, 7.0, 0.16), L.METAL, (0.6, 0.6, 0.6))
        b.box((sx - 1.2, 6.95, sz), (2.4, 0.1, 0.1), L.METAL, (0.6, 0.6, 0.6))
        b.box((sx - 2.3, 6.85, sz), (0.6, 0.12, 0.3), L.METAL, (0.5, 0.5, 0.5))
        b.box((sx - 2.3, 6.77, sz), (0.45, 0.04, 0.22), L.GLOW + EMIS, (1.0, 0.62, 0.25))
        self.lights.append({'pos': (sx - 2.3, 6.5, sz), 'rad': 17.0, 'col': (0.9, 0.48, 0.15), 'flicker': 'soft'})
        # mile marker
        b.box((ROAD_X1 + 0.8, 0.6, sz - 6.0), (0.06, 1.2, 0.06), L.METAL)
        b.box((ROAD_X1 + 0.8, 1.1, sz - 6.0), (0.04, 0.4, 0.25), L.GLOW, (0.2, 0.35, 0.2))
        # manhole: concrete collar, black hole, cover dragged aside
        mx, mz = MANHOLE
        h0 = float(terrain_h(mx, mz))
        b.cylinder(0.8, 0.75, 0.25, 12, L.CONCRETE, (0.6, 0.6, 0.58), m=T(mx, h0 - 0.1, mz), cap=False)
        b.cylinder(0.62, 0.62, 0.001, 12, L.BLACK, m=T(mx, h0 + 0.13, mz), cap=True)
        b.cylinder(0.6, 0.6, 0.05, 12, L.METAL, (0.7, 0.7, 0.7), m=T(mx + 1.3, h0 + 0.01, mz + 0.4) @ RZ(0.08), cap=True)
        # drag marks leading away from the hole
        for i in range(5):
            px_ = mx + 1.0 + i * 0.9
            b.quad((px_, h0 + 0.03, mz - 0.3), (px_ + 0.9, h0 + 0.03, mz - 0.3), (px_ + 0.9, h0 + 0.03, mz + 0.3),
                   (px_, h0 + 0.03, mz + 0.3), L.BLOOD, (0.6, 0.6, 0.6), uvs=((0, 0), (1, 0), (1, 1), (0, 1)))

    def _deer(self, b):
        x, z = -4.2, 21.0
        h0 = float(terrain_h(x, z))
        top = h0 - 0.2 + 3.6
        b.box((x, top - 0.45, z), (0.03, 0.9, 0.03), L.CLOTH, (0.6, 0.55, 0.4))
        body_top = top - 0.9
        sk = (0.55, 0.3, 0.27)
        m = T(x, body_top, z) @ RZ(0.08)
        b.box((0, -0.6, 0), (0.42, 1.2, 0.36), L.SKIN, sk, m=m)
        b.box((0, -0.6, 0.17), (0.2, 0.9, 0.05), L.BLOOD, (1, 1, 1), m=m)
        for sx in (-0.13, 0.13):
            b.box((sx, 0.25, 0), (0.06, 0.6, 0.06), L.SKIN, sk, m=m)
            b.box((sx, -1.45, 0.05), (0.06, 0.55, 0.06), L.SKIN, sk, m=m @ RX(0.3))
        b.box((0, -1.4, 0.1), (0.16, 0.3, 0.18), L.SKIN, sk, m=m)
        b.box((0, -1.7, 0.14), (0.1, 0.3, 0.12), L.SKIN, sk, m=m)
        b.quad((x - 0.5, h0 + 0.03, z - 0.5), (x + 0.5, h0 + 0.03, z - 0.5), (x + 0.5, h0 + 0.03, z + 0.5), (x - 0.5, h0 + 0.03, z + 0.5),
               L.BLOOD, uvs=((0, 0), (1, 0), (1, 1), (0, 1)))

    # ------------------------------------------------------------------ sewer geometry
    def build_sewer(self):
        b = MeshBuilder()
        g = self.g
        for r in range(ROWS):
            for c in range(COLS):
                k = g[r][c]
                if k == '#':
                    continue
                x0 = OX + c * C
                x1 = x0 + C
                z0 = OZ + r * C
                z1 = z0 + C
                fl = float(self.floor[r, c])
                ce = float(self.ceil[r, c])
                tunnel = k == 't'
                wall_l = L.CONCRETE if tunnel else L.BRICK
                wcol = (0.75, 0.75, 0.72) if tunnel else (1, 1, 1)
                st = self.stairs.get((c, r))
                if st:
                    hs, hn = st
                    n = 5
                    for i in range(n):
                        za = z0 + i * C / n
                        zb = za + C / n
                        h = hs + (hn - hs) * (i + 1) / n
                        b.box(((x0 + x1) / 2, (h - 8.0) / 2, (za + zb) / 2), (C, h + 8.0, zb - za), L.CONCRETE, (0.7, 0.7, 0.68))
                else:
                    b.quad_world((x0, fl, z0), (x1, fl, z0), (x1, fl, z1), (x0, fl, z1), L.MUD, (1, 1, 1), 0.5)
                b.quad_world((x0, ce, z0), (x1, ce, z0), (x1, ce, z1), (x0, ce, z1), L.CONCRETE if (tunnel or k == 'X') else L.BRICK,
                             (0.6, 0.6, 0.6), 0.5)
                for dc, dr, side in ((0, -1, 'S'), (0, 1, 'N'), (-1, 0, 'W'), (1, 0, 'E')):
                    nc, nr = c + dc, r + dr
                    if nr < 0:
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
                    myf = self.edge_floor(c, r, side)
                    nk = self.kind(nc, nr)
                    if nk == '#':
                        lo = -8.0 if self.basin[r, c] else myf
                        axis = 'x' if side in 'EW' else 'z'
                        b.quad_world((ax, lo, az), (bx, lo, bz), (bx, ce, bz), (ax, ce, az), wall_l, wcol, 0.5, axis=axis)
                    else:
                        axis = 'x' if side in 'EW' else 'z'
                        if not st:
                            opp = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}[side]
                            nf = self.edge_floor(nc, nr, opp)
                            if (nc, nr) in self.stairs and side in 'EW':
                                nf = -8.0
                            if myf > nf + 0.01:
                                b.quad_world((ax, nf, az), (bx, nf, bz), (bx, myf, bz), (ax, myf, az), L.CONCRETE, (0.7, 0.7, 0.68), 0.5, axis=axis)
                        nce = float(self.ceil[nr, nc])
                        if nce > ce + 0.01:
                            b.quad_world((ax, ce, az), (bx, ce, bz), (bx, nce, bz), (ax, nce, az), wall_l, wcol, 0.5, axis=axis)
                # water surfaces
                if tunnel:
                    cn = self.kind(c, r + 1) == 't' or self.kind(c, r - 1) == 't' or r == 0
                    ce_ = self.kind(c + 1, r) == 't' or self.kind(c - 1, r) == 't'
                    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
                    if cn:
                        b.quad_world((cx - 0.45, fl + 0.02, z0), (cx + 0.45, fl + 0.02, z0), (cx + 0.45, fl + 0.02, z1), (cx - 0.45, fl + 0.02, z1), L.WATER, (1, 1, 1), 0.5)
                    if ce_:
                        b.quad_world((x0, fl + 0.021, cz - 0.45), (x1, fl + 0.021, cz - 0.45), (x1, fl + 0.021, cz + 0.45), (x0, fl + 0.021, cz + 0.45), L.WATER, (1, 1, 1), 0.5)
                elif k == '~':
                    w = -5.25
                    b.quad_world((x0, w, z0), (x1, w, z0), (x1, w, z1), (x0, w, z1), L.WATER, (1, 1, 1), 0.5)
        self._sewer_props(b)
        self._decor(b)
        self.sewer_data = b.array()

        # basin water (dynamic): unit-height quad at y=0, translated by water level
        wb = MeshBuilder()
        x0, z0 = OX + 6 * C, OZ + 41 * C
        x1, z1 = OX + 33 * C, OZ + 46 * C
        wb.quad_world((x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1), L.WATER, (0.9, 1.0, 0.9), 0.35)
        self.basin_water_data = wb.array()

    # helpers
    def wall_point(self, c, r, side, along=0.0, y=0.0, off=0.02):
        cx, cz = cell_center(c, r)
        if side == 'N':
            return (cx - along, y, cz + C / 2 - off), (0, 0, -1)
        if side == 'S':
            return (cx + along, y, cz - C / 2 + off), (0, 0, 1)
        if side == 'W':
            return (cx - C / 2 + off, y, cz - along), (1, 0, 0)
        return (cx + C / 2 - off, y, cz + along), (-1, 0, 0)

    def decal(self, b, c, r, side, layer, w, h, y, along=0.0, colr=(1, 1, 1)):
        p, n = self.wall_point(c, r, side, along, y)
        b.facing_quad(p, n, w, h, layer, colr)

    def floor_decal(self, b, x, z, w, d, layer, y=None, colr=(1, 1, 1), rot=0.0):
        if y is None:
            y = self.floor_at(x, z)
        y += 0.015
        ca, sa = math.cos(rot), math.sin(rot)
        pts = []
        for px, pz in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)):
            pts.append((x + px * ca - pz * sa, y, z + px * sa + pz * ca))
        b.quad(*pts, layer, colr, uvs=((0, 0), (1, 0), (1, 1), (0, 1)))

    def note_on_floor(self, b, nid, x, z, y=None, rot=0.3):
        if y is None:
            y = self.floor_at(x, z)
        self.floor_decal(b, x, z, 0.22, 0.3, L.PAPER, y=y, rot=rot)
        self.notes[nid] = {'pos': (x, y + 0.05, z), 'read': False}

    def bulb(self, b, x, y, z, ceil, colr=(1.0, 0.55, 0.25), rad=9.0, flicker='soft'):
        b.box((x, (y + ceil) / 2, z), (0.02, ceil - y, 0.02), L.BLACK)
        b.box((x, y + 0.08, z), (0.14, 0.06, 0.14), L.METAL)
        b.box((x, y - 0.02, z), (0.08, 0.1, 0.08), L.GLOW + EMIS, (1.0, 0.8, 0.55))
        self.lights.append({'pos': (x, y - 0.15, z), 'rad': rad, 'col': colr, 'flicker': flicker})

    def crate(self, b, x, z, s=0.8, y=None, rot=0.0):
        if y is None:
            y = self.floor_at(x, z)
        b.box((0, s / 2, 0), (s, s, s), L.WOOD, (0.8, 0.8, 0.8), m=T(x, y, z) @ RY(rot))
        h = s * 0.62
        self.extra_boxes.append((x - h, z - h, x + h, z + h))

    def bones(self, b, x, z, n, rng, spread=0.8, y=None):
        if y is None:
            y = self.floor_at(x, z)
        for _ in range(n):
            m = T(x + rng.uniform(-spread, spread), y + 0.04, z + rng.uniform(-spread, spread)) @ RY(rng.random() * 6.28) @ RZ(rng.uniform(-0.3, 0.3))
            ln = rng.uniform(0.15, 0.55)
            b.box((0, 0, 0), (ln, 0.05, 0.05), L.BONE, (0.9, 0.85, 0.8), m=m)
            if rng.random() < 0.15:
                b.box((0, 0.06, 0), (0.18, 0.16, 0.2), L.BONE, (0.85, 0.8, 0.75), m=m)

    def sneaker(self, b, x, z, rot, colr=(0.8, 0.8, 0.8)):
        y = self.floor_at(x, z)
        m = T(x, y, z) @ RY(rot)
        b.box((0, 0.04, 0), (0.1, 0.08, 0.27), L.CLOTH, colr, m=m)
        b.box((0, 0.1, -0.06), (0.09, 0.07, 0.12), L.CLOTH, colr, m=m)
        b.box((0, 0.012, 0), (0.105, 0.025, 0.28), L.PAPER, (1, 1, 1), m=m)

    def valve(self, c, r, side):
        p, n = self.wall_point(c, r, side, 0.0, SEWER_FLOOR + 1.25, off=0.32)
        yaw = math.atan2(n[0], n[2])
        self.valves.append({'pos': p, 'yaw': yaw, 'done': False, 'progress': 0.0, 'angle': 0.0, 'cell': (c, r), 'side': side})

    def herd_figure(self, b, x, z, yaw, h, layer, rng):
        y = self.floor_at(x, z)
        m = T(x, y, z) @ RY(yaw)
        leg = 0.8 * h
        b.box((-0.09, leg / 2, 0), (0.12, leg, 0.13), layer, (0.7, 0.7, 0.7), m=m)
        b.box((0.09, leg / 2, 0), (0.12, leg, 0.13), layer, (0.7, 0.7, 0.7), m=m)
        tor = 0.62 * h
        b.box((0, leg + tor / 2, 0), (0.36 * h, tor, 0.2), layer, (1, 1, 1), m=m)
        for s in (-1, 1):
            am = m @ T(s * 0.21 * h, leg + tor - 0.04, 0) @ RZ(s * 0.06)
            b.box((0, -0.33 * h, 0), (0.08, 0.66 * h, 0.09), L.SKIN, (0.85, 0.85, 0.85), m=am)
        b.box((0, leg + tor + 0.06, 0), (0.08, 0.12, 0.08), L.SKIN, (0.8, 0.8, 0.8), m=m)
        hp = m @ T(0, leg + tor + 0.1, 0)
        head_pos = (float(hp[0, 3]), float(hp[1, 3]), float(hp[2, 3]))
        self.extra_boxes.append((x - 0.22, z - 0.22, x + 0.22, z + 0.22))
        self.herd.append({'pos': head_pos, 'yaw': yaw, 'base': yaw, 'scale': h})
        # shadowy blood under some
        if rng.random() < 0.5:
            self.floor_decal(b, x, z, 0.8, 0.8, L.BLOOD, rot=rng.random() * 6)

    def _sewer_props(self, b):
        rng = random.Random(1989)
        cc = cell_center
        # --- tunnel dressing
        self.decal(b, 5, 3, 'W', L.G_UNDER, 1.8, 1.8, float(self.floor[3, 5]) + 1.3)
        self.decal(b, 16, 9, 'E', L.TALLY, 1.6, 1.6, float(self.floor[9, 16]) + 1.2)
        self.decal(b, 9, 14, 'W', L.HAND, 0.5, 0.5, float(self.floor[14, 9]) + 1.3, along=0.4)
        self.decal(b, 9, 14, 'W', L.HAND, 0.5, 0.5, float(self.floor[14, 9]) + 0.9, along=-0.3)
        self.decal(b, 9, 15, 'E', L.HAND, 0.5, 0.5, float(self.floor[15, 9]) + 1.1, along=0.2)
        for r in range(1, 6):
            x, z = cc(5, r)
            self.floor_decal(b, x + rng.uniform(-0.2, 0.2), z, 0.6, 1.6, L.BLOOD, rot=rng.uniform(-0.2, 0.2), colr=(0.7, 0.7, 0.7))
        for r in range(0, 4):
            x, z = cc(5, r)
            for _ in range(10):
                self.floor_decal(b, x + rng.uniform(-0.9, 0.9), z + rng.uniform(-0.9, 0.9), 0.2, 0.25, L.LEAVES, rot=rng.random() * 6)
        # roots hanging from the ceiling near the entrance
        for r in range(0, 3):
            x, z = cc(5, r)
            ce = float(self.ceil[r, 5])
            for _ in range(5):
                ln = rng.uniform(0.3, 1.1)
                b.box((x + rng.uniform(-0.8, 0.8), ce - ln / 2, z + rng.uniform(-0.9, 0.9)), (0.03, ln, 0.03), L.BARK, (0.6, 0.6, 0.6))
        x, z = cc(16, 9)
        self.note_on_floor(b, 'pwlog', x - 0.4, z + 0.3)
        self.sneaker(b, *cc(12, 6), 1.2, (0.7, 0.1, 0.1))
        self.drip_points += [cc(5, 4), cc(10, 6), cc(16, 10), cc(12, 12), cc(9, 15)]

        # --- junction
        x, z = cc(9, 18)
        self.bulb(b, x, -2.0, z, -1.0, flicker='bad')
        jx, jz = cc(11, 20)
        self.crate(b, jx + 0.2, jz + 0.3, 0.8)
        self.note_on_floor(b, 'memo', jx + 0.2, jz + 0.3, y=SEWER_FLOOR + 0.81, rot=0.2)
        self.crate(b, *cc(7, 20), 0.9, rot=0.4)
        self.crate(b, cc(7, 20)[0], cc(7, 20)[1], 0.6, y=SEWER_FLOOR + 0.9, rot=1.0)
        pipe(b, (OX + 7 * C + 0.15, -1.6, OZ + 17 * C), (OX + 7 * C + 0.15, -1.6, OZ + 21 * C), 0.12, L.METAL)
        self.floor_decal(b, *cc(9, 19), 1.4, 1.4, L.BLOOD, rot=0.5)
        self.drip_points += [cc(8, 18)]

        # --- gallery
        for c in (5, 20, 33):
            x, z = cc(c, 23 if c != 20 else 25)
            self.bulb(b, x, -1.6, z, 0.0, flicker='soft' if c != 33 else 'bad')
        for zz in (OZ + 22 * C + 0.18, OZ + 27 * C - 0.18):
            pipe(b, (OX + 2 * C, -1.2, zz), (OX + 38 * C, -1.2, zz), 0.18, L.METAL)
            pipe(b, (OX + 2 * C, -0.6, zz), (OX + 38 * C, -0.6, zz), 0.1, L.METAL)
        for c in range(4, 37, 5):
            x, z = cc(c, 24)
            b.box((x, -5.0 + 0.02, z - 1.0 - 0.05), (C, 0.04, 0.1), L.METAL, (0.6, 0.6, 0.6))
            b.box((x, -5.0 + 0.02, z + 1.0 + 0.05), (C, 0.04, 0.1), L.METAL, (0.6, 0.6, 0.6))
        # sneakers in a neat row (disturbing)
        for i in range(6):
            x, z = cc(24 + i, 26)
            self.sneaker(b, x - 0.12, z + 0.6, 0.0, ((0.9, 0.9, 0.9), (0.2, 0.3, 0.7), (0.7, 0.1, 0.1))[i % 3])
            self.sneaker(b, x + 0.12, z + 0.6, 0.0, ((0.9, 0.9, 0.9), (0.2, 0.3, 0.7), (0.7, 0.1, 0.1))[i % 3])
        self.decal(b, 26, 26, 'N', L.TALLY, 1.6, 1.6, -3.4)
        self.decal(b, 13, 22, 'S', L.HAND, 0.5, 0.5, -3.8, along=0.3)
        self.decal(b, 14, 22, 'S', L.HAND, 0.5, 0.5, -4.2, along=-0.2)
        self.floor_decal(b, *cc(17, 23), 1.6, 1.6, L.BLOOD)
        for c in (6, 15, 27, 35):
            self.drip_points.append(cc(c, 24))

        # --- cistern
        self.valve(1, 36, 'W')
        x, z = cc(9, 35)
        self.note_on_floor(b, 'journal2', x, z)
        self.bones(b, *cc(2, 34), 18, rng)
        self.floor_decal(b, *cc(5, 31), 2.0, 2.0, L.WATER)
        self.floor_decal(b, *cc(7, 35), 1.8, 1.8, L.WATER)
        self.decal(b, 1, 28, 'W', L.HAND, 0.5, 0.5, -3.7)
        self.drip_points += [cc(4, 31), cc(8, 34)]
        # dead bulb
        x, z = cc(5, 32)
        b.box((x, -1.4, z), (0.02, 0.8, 0.02), L.BLACK)
        b.box((x, -1.85, z), (0.1, 0.1, 0.1), L.METAL)

        # --- pump room
        self.valve(34, 13, 'E')
        x, z = cc(30, 15)
        self.bulb(b, x, -2.0, z, -1.0)
        for c in (28, 32):
            px, pz = cc(c, 14)
            pipe(b, (px - 1.2, -4.1, pz), (px + 1.2, -4.1, pz), 0.55, L.METAL, (0.8, 0.8, 0.8), 10)
            b.box((px, -4.75, pz), (2.4, 0.5, 1.3), L.METAL, (0.6, 0.6, 0.6))
            pipe(b, (px, -3.6, pz), (px, -1.0, pz), 0.18, L.METAL)
        self.add_block(27, 14)
        self.add_block(28, 14)
        self.add_block(29, 14)
        self.add_block(31, 14)
        self.add_block(32, 14)
        self.add_block(33, 14)
        bx, bz = cc(27, 16)
        b.box((bx, -4.55, bz + 0.4), (1.8, 0.08, 0.7), L.WOOD)
        self.add_block_rect(bx - 0.9, bz + 0.05, bx + 0.9, bz + 0.75)
        for ox_ in (-0.8, 0.8):
            b.box((bx + ox_, -4.8, bz + 0.4), (0.08, 0.45, 0.6), L.WOOD)
        self.note_on_floor(b, 'journal1', bx, bz + 0.4, y=-4.5, rot=-0.4)
        self.bones(b, *cc(33, 16), 10, rng, 0.5)

        # --- office
        x, z = cc(15, 18)
        self.bulb(b, x, -2.0, z, -1.0, flicker='bad')
        dx, dz = cc(14, 19)
        b.box((dx, -4.6, dz), (1.6, 0.06, 0.8), L.WOOD)
        self.add_block_rect(dx - 0.8, dz - 0.4, dx + 0.8, dz + 0.4)
        for ox_, oz_ in ((-0.7, -0.33), (0.7, -0.33), (-0.7, 0.33), (0.7, 0.33)):
            b.box((dx + ox_, -4.82, dz + oz_), (0.06, 0.38, 0.06), L.METAL)
        self.note_on_floor(b, 'report', dx + 0.2, dz, y=-4.57, rot=0.1)
        cx_, cz_ = cc(17, 17)
        b.box((cx_ + 0.4, -4.1, cz_ - 0.5), (0.6, 1.8, 0.6), L.METAL, (0.7, 0.75, 0.7))
        self.add_block_rect(cx_ + 0.1, cz_ - 0.8, cx_ + 0.7, cz_ - 0.2)
        b.box((dx, -4.75, dz + 0.9), (0.45, 0.06, 0.45), L.METAL)
        for i in range(8):
            self.floor_decal(b, dx + rng.uniform(-1.5, 2.5), dz + rng.uniform(-1.5, 1.5), 0.22, 0.3, L.PAPER, rot=rng.random() * 6)
        self.decal(b, 13, 17, 'W', L.PAPER, 0.5, 0.6, -3.4, colr=(0.9, 0.9, 0.9))
        self.decal(b, 17, 20, 'N', L.G_DONTLOOK, 1.7, 1.7, -3.2)
        # back room
        self.valve(22, 17, 'E')
        self.bones(b, *cc(20, 19), 8, rng, 0.6)
        self.decal(b, 21, 19, 'N', L.HAND, 0.5, 0.5, -3.6)

        # --- holding room (the herd)
        x, z = cc(20, 34)
        self.bulb(b, x, -2.4, z, -1.6, colr=(0.55, 0.12, 0.08), rad=8.0, flicker='bad')
        self.valve(20, 37, 'N')
        figs = [
            (OX + 15 * C + 0.5, 113.0, -math.pi / 2), (OX + 15 * C + 0.5, 117.0, -math.pi / 2), (OX + 15 * C + 0.5, 121.0, -math.pi / 2),
            (OX + 26 * C - 0.5, 113.0, math.pi / 2), (OX + 26 * C - 0.5, 117.5, math.pi / 2), (OX + 26 * C - 0.5, 121.5, math.pi / 2),
            (23.0, OZ + 38 * C - 0.5, 0.0), (25.5, OZ + 38 * C - 0.5, 0.0), (35.0, OZ + 38 * C - 0.5, 0.0), (38.5, OZ + 38 * C - 0.5, 0.0),
        ]
        for fx, fz, fy in figs:
            self.herd_figure(b, fx, fz, fy, rng.uniform(1.25, 1.75), L.CLOTH, rng)
        # Kyle: red hoodie, centre of the room, facing the door
        self.herd_figure(b, 30.0, 117.0, math.pi, 1.45, L.REDCLOTH, rng)
        self.note_on_floor(b, 'kyle', *cc(16, 32))
        self.decal(b, 19, 31, 'S', L.G_DONTLOOK, 1.8, 1.8, -3.0)
        self.decal(b, 25, 35, 'E', L.TALLY, 1.6, 1.6, -3.4)
        for _ in range(12):
            self.floor_decal(b, rng.uniform(OX + 15 * C + 0.5, OX + 26 * C - 0.5), rng.uniform(OZ + 31 * C + 0.5, OZ + 38 * C - 0.5),
                             0.4, 0.4, L.BARK, rot=rng.random() * 6)

        # --- nest (east overflow)
        self.valve(38, 35, 'E')
        self.note_on_floor(b, 'journal3', *cc(33, 34))
        for (c, r) in ((34, 31), (36, 33), (33, 30), (37, 30), (35, 34)):
            self.bones(b, *cc(c, r), 22, rng, 0.9)
        for i in range(6):
            x, z = cc(34 + (i % 3), 32 + i // 3)
            m = T(x, -4.92, z) @ RY(rng.random() * 6)
            b.box((0, 0, 0), (1.6, 0.16, 1.2), L.FUR, (1, 1, 1), m=m)
        for (c, r) in ((35, 32), (36, 31), (33, 33)):
            self.floor_decal(b, *cc(c, r), 1.9, 1.9, L.BLOOD, rot=rng.random() * 6)
        for i in range(4):
            x, z = cc(32 + i, 29)
            m = T(x, -4.9, z + 0.3) @ RY(rng.random() * 6) @ RZ(0.3)
            b.box((0.3, 0, 0), (0.6, 0.05, 0.05), L.BONE, (0.9, 0.9, 0.85), m=m)
            b.box((0.65, 0.1, 0), (0.05, 0.4, 0.35), L.BONE, (0.9, 0.9, 0.85), m=m)
        self.decal(b, 38, 31, 'E', L.HAND, 0.5, 0.5, -3.8)
        self.decal(b, 38, 32, 'E', L.HAND, 0.5, 0.5, -4.1, along=0.4)
        self.decal(b, 32, 33, 'W', L.G_UNDER, 1.8, 1.8, -3.2)
        # the white bull's skull
        sx, sz = cc(36, 35)
        m = T(sx, -4.85, sz + 0.4) @ RY(2.6)
        b.box((0, 0.1, 0), (0.35, 0.3, 0.4), L.BONE, (1.1, 1.1, 1.1), m=m)
        b.box((0, 0.05, 0.4), (0.22, 0.2, 0.5), L.BONE, (1.1, 1.1, 1.1), m=m)
        b.box((-0.12, 0.16, 0.12), (0.07, 0.07, 0.07), L.BLACK, m=m)
        b.box((0.12, 0.16, 0.12), (0.07, 0.07, 0.07), L.BLACK, m=m)
        self.drip_points += [cc(35, 30), cc(34, 34)]

        # --- corridor to chamber
        self.decal(b, 12, 33, 'W', L.HAND, 0.5, 0.5, -3.9)
        self.decal(b, 12, 36, 'E', L.TALLY, 1.6, 1.6, -3.3)
        self.drip_points.append(cc(12, 30))

        # --- chamber C
        for (c, r) in ((9, 39), (28, 46)):
            x, z = cc(c, r)
            self.bulb(b, x, -1.0, z, 1.0, rad=11.0, flicker='soft')
        self.note_on_floor(b, 'jamie', *cc(8, 40))
        # railings
        for zz in (OZ + 41 * C - 0.08, OZ + 46 * C + 0.08):
            for xa, xb in ((OX + 6 * C, OX + 18 * C), (OX + 21 * C, OX + 33 * C)):
                b.box(((xa + xb) / 2, -4.0, zz), (xb - xa, 0.06, 0.06), L.METAL)
                b.box(((xa + xb) / 2, -4.5, zz), (xb - xa, 0.04, 0.04), L.METAL)
                x = xa + 0.1
                while x < xb:
                    b.box((x, -4.5, zz), (0.06, 1.0, 0.06), L.METAL)
                    x += 1.5
        # pale things at the bottom of the basin (revealed when drained)
        for _ in range(9):
            x = rng.uniform(OX + 7 * C, OX + 32 * C)
            z = rng.uniform(OZ + 42.5 * C, OZ + 44.5 * C)
            if abs(x - (OX + 19.5 * C)) < 3.2:
                continue
            m = T(x, -7.9, z) @ RY(rng.random() * 6)
            b.box((0, 0, 0), (0.45, 0.2, 1.4), L.SKIN, (0.85, 0.85, 0.8), m=m)
            b.box((0, 0.02, 0.85), (0.22, 0.2, 0.26), L.SKIN, (0.85, 0.85, 0.8), m=m)
            b.box((0.2, 0.15, 0.9), (0.03, 0.45, 0.03), L.BARK, m=m @ RZ(-0.5))
        self.bones(b, OX + 12 * C, OZ + 43.5 * C, 30, rng, 2.5, y=-8.0)
        self.bones(b, OX + 27 * C, OZ + 43 * C, 30, rng, 2.5, y=-8.0)
        # Jamie
        jx, jz = OX + 23.5 * C, OZ + 43.5 * C
        m = T(jx, -7.92, jz) @ RY(0.7)
        b.box((0, 0, 0), (0.36, 0.18, 1.1), L.CLOTH, (0.4, 0.5, 0.8), m=m)
        b.box((0, 0.03, 0.68), (0.2, 0.2, 0.23), L.SKIN, (0.8, 0.8, 0.75), m=m)
        for s in (-1, 1):
            b.box((s * 0.3, 0, 0.1), (0.08, 0.08, 0.6), L.SKIN, (0.8, 0.8, 0.75), m=m @ RY(s * 0.4))
        # exit shaft & ladder
        lx, lz = cc(19, 48)
        for s in (-0.25, 0.25):
            b.box((lx + s, 0.5, lz + 0.85), (0.06, 11.0, 0.06), L.METAL)
        y = -4.7
        while y < 6.0:
            b.box((lx, y, lz + 0.85), (0.5, 0.04, 0.04), L.METAL)
            y += 0.35
        self.lights.append({'pos': (lx, 4.0, lz), 'rad': 10.0, 'col': (0.25, 0.3, 0.45), 'flicker': 'none'})
        b.box((lx, 5.95, lz), (1.0, 0.05, 1.0), L.GRATE, (0.8, 0.8, 0.8))
        self.ladder_pos = (lx, -3.6, lz + 0.6)
        self.decal(b, 17, 47, 'N', L.G_ONEMORE, 2.0, 2.0, -2.8)
        self._north_props(b, rng)
        self.decal(b, 21, 47, 'N', L.HAND, 0.5, 0.5, -3.7)
        self.decal(b, 21, 47, 'N', L.HAND, 0.5, 0.5, -3.3, along=0.5)
        self.drip_points += [cc(10, 42), cc(25, 44), cc(15, 46)]

    def _north_props(self, b, rng):
        """The rooms added later: the filter room, flooded storage, and the old works past the chamber."""
        cc = cell_center
        # ---- the ladder gate's frame
        gx, gz = OX + KEYGATE[0] * C, OZ + KEYGATE[1] * C
        for sx in (gx - 0.06, gx + C + 0.06):
            b.box((sx, -3.2, gz), (0.16, 3.6, 0.2), L.METAL, (0.45, 0.4, 0.35))
        b.box((gx + C / 2, -1.35, gz), (C + 0.3, 0.2, 0.22), L.METAL, (0.45, 0.4, 0.35))
        # ---- filter room
        x, z = cc(40, 14)
        self.bulb(b, x, -2.0, z, -1.0, flicker='bad')
        for (c, r) in ((38, 13), (42, 13), (38, 16), (42, 16)):
            tx, tz = cc(c, r)
            pipe(b, (tx, -5.0, tz), (tx, -1.0, tz), 0.85, L.METAL, (0.55, 0.6, 0.58), 12)
            pipe(b, (tx, -1.6, tz), (tx + (1.0 if c < 40 else -1.0) * 2.0, -1.6, tz), 0.15, L.METAL)
        self.bones(b, *cc(44, 17), 12, rng, 0.6)
        self.decal(b, 44, 12, 'E', L.TALLY, 1.6, 1.6, -3.4)
        self.decal(b, 36, 18, 'W', L.HAND, 0.5, 0.5, -3.8)
        self.drip_points += [cc(40, 12), cc(43, 17)]
        # ---- flooded storage
        for (c, r) in ((41, 29), (45, 30), (42, 34), (45, 35), (44, 32)):
            x, z = cc(c, r)
            self.crate(b, x, z, rng.uniform(0.7, 1.0), rot=rng.random())
            if rng.random() < 0.6:
                self.crate(b, x, z, 0.6, y=SEWER_FLOOR + 0.85, rot=rng.random())
        for (c, r) in ((43, 31), (41, 33), (44, 35)):
            self.floor_decal(b, *cc(c, r), 2.2, 2.2, L.WATER)
        x, z = cc(43, 32)
        self.bulb(b, x, -2.0, z, -1.0, colr=(0.6, 0.65, 0.8), rad=8.0, flicker='bad')
        self.sneaker(b, *cc(46, 36), 2.0, (0.2, 0.3, 0.7))
        self.drip_points += [cc(42, 30), cc(45, 34)]
        # ---- the works: the long hall
        for c in (6, 19, 33, 42):
            x, z = cc(c, 51)
            self.bulb(b, x, -2.0, z, -1.0, flicker='soft' if c != 33 else 'bad')
        for zz in (OZ + 51 * C + 0.15, OZ + 53 * C - 0.15):
            pipe(b, (OX + 2 * C, -1.5, zz), (OX + 45 * C, -1.5, zz), 0.16, L.METAL)
        self.decal(b, 15, 52, 'N', L.G_DONTLOOK, 1.7, 1.7, -3.2)
        self.decal(b, 9, 51, 'S', L.HAND, 0.5, 0.5, -3.7)
        self.floor_decal(b, *cc(24, 52), 1.6, 1.6, L.BLOOD, rot=0.7)
        for c in range(4, 44, 7):
            self.drip_points.append(cc(c, 52))
        # lockers
        for r in range(54, 60):
            x, z = cc(2, r)
            b.box((x - 0.55, -4.1, z), (0.6, 1.8, 0.9), L.METAL, (0.5, 0.58, 0.55))
            self.add_block_rect(x - 0.9, z - 0.45, x - 0.25, z + 0.45)
        self.bones(b, *cc(6, 58), 10, rng, 0.6)
        self.decal(b, 7, 56, 'E', L.TALLY, 1.6, 1.6, -3.4)
        # the dead generator room
        x, z = cc(12, 56)
        b.box((x, -4.4, z), (2.2, 1.2, 1.2), L.METAL, (0.45, 0.48, 0.4))
        self.add_block_rect(x - 1.1, z - 0.6, x + 1.1, z + 0.6)
        pipe(b, (x + 0.8, -3.8, z), (x + 0.8, -1.0, z), 0.14, L.METAL)
        x, z = cc(14, 59)
        self.bulb(b, x, -2.0, z, -1.0, flicker='bad')
        # the cells: chains and shoes
        for c in (18, 20, 22):
            x, z = cc(c, 58)
            for k in range(3):
                b.box((x + (k - 1) * 0.3, -2.4, z + 0.8), (0.03, 2.6, 0.03), L.METAL, (0.6, 0.6, 0.6))
            self.sneaker(b, x, z, rng.random() * 6, ((0.9, 0.9, 0.9), (0.7, 0.1, 0.1), (0.2, 0.3, 0.7))[c % 3])
        self.floor_decal(b, *cc(21, 56), 1.8, 1.8, L.BLOOD)
        self.decal(b, 23, 55, 'E', L.G_UNDER, 1.8, 1.8, -3.2)
        # the shrine: three of them standing, facing a wall of antlers
        for c in (27, 29, 31):
            self.herd_figure(b, *cc(c, 58), 0.0, rng.uniform(1.3, 1.6), L.CLOTH, rng)
        for k in range(6):
            x, z = cc(26 + k, 60)
            m = T(x, -2.6 + 0.3 * math.sin(k), z + 0.85) @ RZ(rng.uniform(-0.5, 0.5))
            b.box((0, 0, 0), (0.06, 0.9, 0.06), L.BONE, (0.85, 0.8, 0.7), m=m)
            b.box((0.2, 0.35, 0), (0.4, 0.05, 0.05), L.BONE, (0.85, 0.8, 0.7), m=m)
        x, z = cc(28, 56)
        self.bulb(b, x, -2.2, z, -1.0, colr=(0.55, 0.12, 0.08), rad=8.0, flicker='bad')
        # records office
        x, z = cc(35, 58)
        b.box((x, -4.6, z), (1.6, 0.06, 0.8), L.WOOD)
        self.add_block_rect(x - 0.8, z - 0.4, x + 0.8, z + 0.4)
        for i in range(14):
            self.floor_decal(b, x + rng.uniform(-1.0, 4.5), z + rng.uniform(-1.5, 1.0), 0.22, 0.3, L.PAPER, rot=rng.random() * 6)
        x, z = cc(39, 54)
        self.bulb(b, x, -2.0, z, -1.0, flicker='soft')
        # cages
        for r in (55, 58):
            for c in (43, 45):
                x, z = cc(c, r)
                for k in range(5):
                    b.box((x - 0.8 + k * 0.4, -4.0, z - 0.8), (0.04, 2.0, 0.04), L.METAL, (0.5, 0.5, 0.5))
                    b.box((x - 0.8, -4.0, z - 0.8 + k * 0.4), (0.04, 2.0, 0.04), L.METAL, (0.5, 0.5, 0.5))
                self.bones(b, x, z, 8, rng, 0.5)
        # the settling tank: the key is on what's left of a city worker at the far west end
        for c in (11, 23, 30):
            x, z = cc(c, 64)
            self.bulb(b, x, -2.0, z, -1.0, colr=(0.5, 0.6, 0.55), rad=8.0, flicker='bad' if c != 11 else 'soft')
        for c in range(9, 32, 4):
            self.floor_decal(b, *cc(c, 65), 2.0, 2.0, L.WATER)
        kx, kz = cc(9, 65)
        m = T(kx + 0.3, SEWER_FLOOR + 0.02, kz) @ RY(1.1)
        b.box((0, 0.1, 0), (0.42, 0.2, 1.3), L.CLOTH, (0.85, 0.45, 0.1), m=m)        # orange coveralls
        b.box((0, 0.12, 0.8), (0.22, 0.22, 0.26), L.BONE, (0.85, 0.8, 0.75), m=m)
        for s in (-1, 1):
            b.box((s * 0.3, 0.06, 0.15), (0.08, 0.08, 0.6), L.BONE, (0.85, 0.8, 0.75), m=m @ RY(s * 0.5))
        self.floor_decal(b, kx + 0.3, kz, 1.8, 1.8, L.BLOOD)
        self.key_pos = (kx - 0.35, SEWER_FLOOR + 0.06, kz + 0.2)
        self.decal(b, 8, 65, 'W', L.G_ONEMORE, 2.0, 2.0, -3.0)
        self.drip_points += [cc(12, 64), cc(22, 63), cc(29, 65)]
        self._grown_props(b)

    def _grown_props(self, b):
        """Dress the grown rooms: some lit, most dark, all of them lived in by something."""
        rng = random.Random(5519)
        cc = cell_center
        for (c0, r0, c1, r1, _k) in getattr(self, 'grown', ()):
            mc, mr = (c0 + c1) // 2, (r0 + r1) // 2
            x, z = cc(mc, mr)
            if rng.random() < 0.45:
                self.bulb(b, x, -2.0, z, -1.0, flicker=rng.choice(('soft', 'bad', 'bad')),
                          colr=rng.choice(((1.0, 0.55, 0.25), (0.6, 0.65, 0.8), (0.55, 0.12, 0.08))), rad=8.0)
            for _ in range(rng.randint(0, 3)):
                c, r = rng.randint(c0, c1), rng.randint(r0, r1)
                roll = rng.random()
                px, pz = cc(c, r)
                if roll < 0.3:
                    self.bones(b, px, pz, rng.randint(6, 16), rng, 0.6)
                elif roll < 0.5:
                    self.floor_decal(b, px, pz, rng.uniform(1.0, 2.0), rng.uniform(1.0, 2.0), L.BLOOD, rot=rng.random() * 6)
                elif roll < 0.7:
                    self.floor_decal(b, px, pz, 2.0, 2.0, L.WATER)
                elif roll < 0.85 and c1 - c0 >= 3 and r1 - r0 >= 3:
                    self.crate(b, px, pz, rng.uniform(0.6, 0.95), rot=rng.random())
                else:
                    self.sneaker(b, px, pz, rng.random() * 6, ((0.9, 0.9, 0.9), (0.7, 0.1, 0.1), (0.2, 0.3, 0.7))[rng.randrange(3)])
            # a mark on a wall now and then
            if rng.random() < 0.35:
                side = rng.choice('NSEW')
                c, r = (rng.randint(c0, c1), r1) if side == 'N' else (rng.randint(c0, c1), r0) if side == 'S' else                     (c1, rng.randint(r0, r1)) if side == 'E' else (c0, rng.randint(r0, r1))
                nc, nr = c + {'N': 0, 'S': 0, 'E': 1, 'W': -1}[side], r + {'N': 1, 'S': -1, 'E': 0, 'W': 0}[side]
                if self.kind(nc, nr) == '#':
                    self.decal(b, c, r, side, rng.choice((L.HAND, L.TALLY, L.G_UNDER, L.G_DONTLOOK)),
                               1.4 if rng.random() < 0.5 else 0.5, 1.4, -3.4)
            self.drip_points.append((x, z))

    def _decor(self, b):
        """Pipes, junk, barrels and chains along the sewer walls (decor.py), kept off the stairs,
        the basin, the ladder and anything that already stands there."""
        import decor
        busy = list(self.extra_boxes)

        def skip(c, r):
            if self.basin[r, c] or (c, r) in self.stairs:
                return True
            x, z = cell_center(c, r)
            if self.ladder_pos is not None and math.hypot(x - self.ladder_pos[0], z - self.ladder_pos[2]) < 4.0:
                return True
            return any(bx0 - 1.6 < x < bx1 + 1.6 and bz0 - 1.6 < z < bz1 + 1.6 for bx0, bz0, bx1, bz1 in busy)

        cells = [(c, r) for r in range(ROWS) for c in range(COLS) if self.g[r][c] == '.']
        decor.dress_grid(b, cells, self.kind, cell_center, lambda c, r: float(self.floor[r, c]),
                         lambda c, r: float(self.ceil[r, c]), 'sewer', 6102, cell=C, boxes=self.extra_boxes, skip=skip)

    def add_block(self, c, r):
        pass  # pumps sit on the floor; collision handled by extra boxes below

    def add_block_rect(self, x0, z0, x1, z1):
        self.extra_boxes.append((x0, z0, x1, z1))

    extra_boxes = []

    def place_c1_lever(self, lev, x, z, yaw):
        h0 = float(terrain_h(x, z))
        m = T(x, h0, z) @ RY(yaw)
        pm = m @ T(0, 1.1, 0.12)
        lev['pos'] = (float(pm[0, 3]), float(pm[1, 3]), float(pm[2, 3]))
        lev['yaw'] = yaw
        lev['base'] = (x, h0, z)
        lp = m @ T(0, 1.75, 0.3)
        lev['light']['pos'] = (float(lp[0, 3]), float(lp[1, 3]), float(lp[2, 3]))

    def dyn_boxes(self):
        out = []
        for lev in self.c1_levers:
            bx, _, bz = lev.get('base', lev['pos'])
            out.append((bx - 0.32, bz - 0.32, bx + 0.32, bz + 0.32))
        if self.grate_open < 0.8:
            out.append((-1.1, 47.55, 1.1, 48.1))
        if self.keygate_open < 0.8:
            x0, z0 = OX + KEYGATE[0] * C, OZ + KEYGATE[1] * C
            out.append((x0 - 0.1, z0 - 0.15, x0 + C + 0.1, z0 + 0.15))
        return out

    def collide_extra(self, x, z, rad):
        for bx0, bz0, bx1, bz1 in self.extra_boxes + self.dyn_boxes():
            nx = clamp(x, bx0, bx1)
            nz = clamp(z, bz0, bz1)
            dx, dz = x - nx, z - nz
            d2 = dx * dx + dz * dz
            if 1e-10 < d2 < rad * rad:
                d = math.sqrt(d2)
                x += dx / d * (rad - d)
                z += dz / d * (rad - d)
        return x, z

    def build(self):
        self.extra_boxes = []
        # pump bodies
        for c in (28, 32):
            px, pz = cell_center(c, 14)
            self.extra_boxes.append((px - 1.2, pz - 0.65, px + 1.2, pz + 0.65))
        self.build_forest()
        self.build_sewer()

    def set_valves_done(self, n):
        self.water_target = -5.3 - 0.3 * n if n < 5 else -8.6
