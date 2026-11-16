"""Chapter 2: the cabin in the snow, the firewood, and the Goat Man hunting you.

A separate map from Chapter 1, with its own terrain, rivers, lake, cabin and AI.
"""
import math
import random
import numpy as np

from engine import MeshBuilder, T, S, RX, RY, RZ
from textures import L, EMIS

WL = 0.0                      # water level (rivers and the lake)
HALF = 100.0                  # the map runs from -HALF to +HALF on both axes
LAKE = (52.0, -42.0, 28.0, 20.0)   # centre x, centre z, radius x, radius z
RIVERS = [
    [(-104, 62), (-78, 48), (-55, 56), (-36, 36), (-28, 12), (-20, -12), (4, -26), (27, -36)],
    [(22, 104), (32, 82), (20, 60), (36, 38), (52, 18), (55, -24)],
]
WOOD_NEEDED = 20
CABIN_HX, CABIN_HZ = 2.5, 2.0     # wall centre lines
DOOR_HINGE_X = -0.5
WOODPILE = (1.55, 2.9)            # on the porch, right of the door
RESPAWN = (0.0, 5.2)              # in front of the cabin, facing away from it
DOCK = (31.0, -30.0)
STAND = (-46.0, -40.0)
OUTHOUSE = (-9.0, -7.0)


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def _smooth(t):
    return t * t * (3 - 2 * t)


def river_dist(x, z):
    x = np.asarray(x, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)
    best = np.full(np.broadcast(x, z).shape, 1e9)
    for pts in RIVERS:
        for (ax, az), (bx, bz) in zip(pts[:-1], pts[1:]):
            vx, vz = bx - ax, bz - az
            L2 = vx * vx + vz * vz
            t = np.clip(((x - ax) * vx + (z - az) * vz) / L2, 0, 1)
            best = np.minimum(best, np.hypot(x - (ax + t * vx), z - (az + t * vz)))
    return best


def terrain_h2(x, z):
    x = np.asarray(x, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)
    h = (3.2 + 1.5 * np.sin(x * 0.031 + 0.5) * np.cos(z * 0.027) + 0.8 * np.sin(x * 0.071 + z * 0.052)
         + 0.35 * np.cos(x * 0.13 - z * 0.11))
    # the cabin clearing is levelled
    k = _smooth(np.clip((np.hypot(x, z) - 9.0) / 12.0, 0, 1))
    h = 3.0 * (1 - k) + h * k
    # rivers: shallow beds you can wade
    rk = _smooth(np.clip((river_dist(x, z) - 1.8) / 2.6, 0, 1))
    h = (WL - 0.55) * (1 - rk) + h * rk
    # the lake: deep in the middle
    cx, cz, rx, rz = LAKE
    q = ((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2
    lake = WL - 0.3 - 3.2 * np.clip(1 - q, 0, 1) ** 0.6
    lk = _smooth(np.clip((q - 0.92) / 0.25, 0, 1))
    h = lake * (1 - lk) + h * lk
    return h


CABIN_Y = float(terrain_h2(0.0, 0.0))


class World2:
    def __init__(self):
        self.trees = []
        self.tree_hash = {}
        self.boxes = []                 # solid (x0, z0, x1, z1)
        self.wood_spots = []            # (x, y, z, rot)
        self.lights = []
        self.porch_lamp = None

    # ------------------------------------------------------------------ queries
    def ground_at(self, x, z):
        return float(terrain_h2(x, z))

    def water_depth(self, x, z):
        return max(0.0, WL - float(terrain_h2(x, z)))

    def blocked(self, x, z):
        return self.water_depth(x, z) > 0.95

    def collide(self, x, z, rad, ox, oz):
        # deep water: slide along the shore instead of walking in
        if self.blocked(x, z):
            if not self.blocked(x, oz):
                z = oz
            elif not self.blocked(ox, z):
                x = ox
            else:
                x, z = ox, oz
        for _ in range(2):
            for bx0, bz0, bx1, bz1 in self.boxes:
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
                        opts = [(x - bx0, -1, 0), (bx1 - x, 1, 0), (z - bz0, 0, -1), (bz1 - z, 0, 1)]
                        dm, sx, sz = min(opts)
                        x += sx * (dm + rad)
                        z += sz * (dm + rad)
            hx, hz = int(x // 4), int(z // 4)
            for i in (hx - 1, hx, hx + 1):
                for j in (hz - 1, hz, hz + 1):
                    for tx, tz, tr in self.tree_hash.get((i, j), ()):
                        dx, dz = x - tx, z - tz
                        d = math.hypot(dx, dz)
                        mn = tr + rad
                        if 1e-6 < d < mn:
                            x += dx / d * (mn - d)
                            z += dz / d * (mn - d)
        x = clamp(x, -HALF + 3, HALF - 3)
        z = clamp(z, -HALF + 3, HALF - 3)
        return x, z

    def near_tree(self, x, z, mind):
        hx, hz = int(x // 4), int(z // 4)
        for i in (hx - 1, hx, hx + 1):
            for j in (hz - 1, hz, hz + 1):
                for tx, tz, tr in self.tree_hash.get((i, j), ()):
                    if math.hypot(x - tx, z - tz) < mind:
                        return True
        return False

    def add_tree(self, x, z, r):
        self.trees.append((x, z, r))
        self.tree_hash.setdefault((int(x // 4), int(z // 4)), []).append((x, z, r))

    def keep_clear(self, x, z, m=0.0):
        if math.hypot(x, z) < 11 + m:
            return True
        for px, pz, r in ((DOCK[0], DOCK[1], 6), (STAND[0], STAND[1], 4), (OUTHOUSE[0], OUTHOUSE[1], 3)):
            if math.hypot(x - px, z - pz) < r + m:
                return True
        for wx, wy, wz, _ in self.wood_spots:
            if math.hypot(x - wx, z - wz) < 2.2 + m:
                return True
        return False

    def random_land(self, rng, margin=8.0, min_h=0.45):
        for _ in range(200):
            x = rng.uniform(-HALF + margin, HALF - margin)
            z = rng.uniform(-HALF + margin, HALF - margin)
            if float(terrain_h2(x, z)) > WL + min_h:
                return x, z
        return 0.0, 10.0

    # ------------------------------------------------------------------ build
    def build(self):
        rng = random.Random(2003_11_02)
        b = MeshBuilder()
        self._terrain(b)
        # firewood first, so nothing grows on top of it
        landmark_spots = [(DOCK[0] - 3.5, DOCK[1] + 2.0), (STAND[0] + 2.5, STAND[1] + 1.5),
                          (OUTHOUSE[0] + 2.0, OUTHOUSE[1] - 1.5)]
        for x, z in landmark_spots:
            self.wood_spots.append((x, float(terrain_h2(x, z)), z, rng.random() * 6.28))
        tries = 0
        while len(self.wood_spots) < 34 and tries < 5000:
            tries += 1
            x, z = self.random_land(rng, margin=10)
            if math.hypot(x, z) < 18:
                continue
            if any(math.hypot(x - wx, z - wz) < 13 for wx, _, wz, _ in self.wood_spots):
                continue
            self.wood_spots.append((x, float(terrain_h2(x, z)), z, rng.random() * 6.28))
        # trees, thick at the edges
        n = 0
        tries = 0
        while n < 1150 and tries < 40000:
            tries += 1
            edge = rng.random() < 0.22
            if edge:
                side = rng.randrange(4)
                v = rng.uniform(-HALF, HALF)
                d = rng.uniform(HALF - 12, HALF + 4)
                x, z = [(v, d), (v, -d), (d, v), (-d, v)][side]
            else:
                x = rng.uniform(-HALF, HALF)
                z = rng.uniform(-HALF, HALF)
            h = float(terrain_h2(x, z))
            if h < WL + 0.5 or self.keep_clear(x, z):
                continue
            if self.near_tree(x, z, 2.4):
                continue
            r = rng.uniform(0.2, 0.42)
            ht = rng.uniform(9, 17)
            self.add_tree(x, z, r)
            if rng.random() < 0.82:
                self._pine(b, x, h, z, r, ht, rng)
            else:
                self._dead_tree(b, x, h, z, r, ht * 0.7, rng)
            n += 1
        # snowy rocks and fallen logs
        for _ in range(140):
            x, z = self.random_land(rng, margin=4, min_h=0.2)
            if self.keep_clear(x, z, 1.0):
                continue
            h = float(terrain_h2(x, z))
            sz = rng.uniform(0.5, 1.6)
            m = T(x, h, z) @ RY(rng.random() * 6) @ RX(rng.uniform(-0.25, 0.25))
            b.box((0, sz * 0.25, 0), (sz * 1.3, sz * 0.8, sz), L.CONCRETE, (0.55, 0.56, 0.6), m=m)
            b.box((0, sz * 0.66, 0), (sz * 1.2, 0.06, sz * 0.9), L.CONCRETE, (2.05, 2.1, 2.3), m=m)
            if sz > 1.0:
                self.add_tree(x, z, sz * 0.6)
        for _ in range(45):
            x, z = self.random_land(rng, margin=6)
            if self.keep_clear(x, z, 3.0):
                continue
            h = float(terrain_h2(x, z))
            a = rng.random() * 6.28
            ln = rng.uniform(3, 6)
            m = T(x, h + 0.2, z) @ RY(a) @ RX(math.pi / 2) @ T(0, -ln / 2, 0)
            b.cylinder(0.24, 0.21, ln, 7, L.BARK, (0.7, 0.68, 0.66), m=m)
            b.box((0, ln / 2, 0.2), (0.3, ln, 0.04), L.CONCRETE, (2.05, 2.1, 2.3), m=m)
            for k in range(-2, 3):
                self.add_tree(x + math.sin(a) * k * ln / 5, z + math.cos(a) * k * ln / 5, 0.3)
        self._cabin(b)
        self._landmarks(b, rng)
        self.static_data = b.array()

        wb = MeshBuilder()
        e = HALF + 10
        wb.quad_world((-e, WL, -e), (e, WL, -e), (e, WL, e), (-e, WL, e), L.WATER, (0.75, 0.85, 0.95), 0.3)
        self.water_data = wb.array()

    def _terrain(self, b):
        xs = np.arange(-HALF - 10, HALF + 10.01, 2.0)
        zs = np.arange(-HALF - 10, HALF + 10.01, 2.0)
        X, Z = np.meshgrid(xs, zs)
        H = terrain_h2(X, Z)
        gx = np.gradient(H, 2.0, axis=1)
        gz = np.gradient(H, 2.0, axis=0)
        N = np.stack([-gx, np.ones_like(H), -gz], -1)
        N /= np.linalg.norm(N, axis=-1, keepdims=True)
        snow = np.array((2.0, 2.06, 2.25))
        mud = np.array((0.55, 0.5, 0.45))
        t = np.clip((H - (WL + 0.05)) / 0.5, 0, 1)[..., None]
        col = mud * (1 - t) + snow * t
        V = np.zeros(H.shape + (12,), np.float32)
        V[..., 0], V[..., 1], V[..., 2] = X, H, Z
        V[..., 3:6] = N
        V[..., 6], V[..., 7] = X * 0.25, Z * 0.25
        V[..., 8:11] = col
        V[..., 11] = L.CONCRETE      # grey-white noise reads as snow far better than tinted grass
        nz, nx = H.shape
        j, i = np.mgrid[0:nz - 1, 0:nx - 1]
        tris = np.stack([V[j, i], V[j, i + 1], V[j + 1, i + 1], V[j, i], V[j + 1, i + 1], V[j + 1, i]], axis=2)
        b.add_array(tris.reshape(-1, 12))

    def _pine(self, b, x, h, z, r, ht, rng):
        m = T(x, h - 0.2, z)
        b.cylinder(r, r * 0.3, ht, 6, L.BARK, (0.85, 0.85, 0.85), m=m)
        for k in range(3):
            y = ht * (0.32 + 0.22 * k)
            rad = (2.7 - 0.7 * k) * rng.uniform(0.85, 1.12)
            ch = 3.6 - 0.5 * k
            b.cylinder(rad, 0.0, ch, 7, L.NEEDLES, (1.25, 1.35, 1.45), m=T(x, h + y, z) @ RY(rng.random() * 6.28))
            # snow sitting on the boughs
            b.cylinder(rad * 0.82, 0.0, ch * 0.55, 7, L.CONCRETE, (1.9, 1.95, 2.15),
                       m=T(x, h + y + ch * 0.38, z) @ RY(rng.random() * 6.28))

    def _dead_tree(self, b, x, h, z, r, ht, rng):
        b.cylinder(r, r * 0.25, ht, 6, L.BARK, (0.75, 0.75, 0.78), m=T(x, h - 0.2, z))
        for _ in range(5):
            a = rng.random() * 6.28
            y = rng.uniform(ht * 0.35, ht * 0.9)
            ln = rng.uniform(1.0, 2.6)
            mm = T(x, h + y, z) @ RY(a) @ RZ(-rng.uniform(0.6, 1.2)) @ T(0, ln / 2, 0)
            b.box((0, 0, 0), (0.09, ln, 0.09), L.BARK, (0.7, 0.7, 0.72), m=mm)

    def _log(self, b, a, c, r=0.16):
        """A horizontal log between two points on the same axis."""
        dx, dz = c[0] - a[0], c[2] - a[2]
        if abs(dx) >= abs(dz):
            start = a if dx > 0 else c
            m = T(*start) @ RZ(-math.pi / 2)
            ln = abs(dx)
        else:
            start = a if dz > 0 else c
            m = T(*start) @ RX(math.pi / 2)
            ln = abs(dz)
        b.cylinder(r, r, ln, 8, L.BARK, (0.78, 0.6, 0.45), m=m, cap=True)

    def _cabin(self, b):
        Y = CABIN_Y
        hx, hz = CABIN_HX, CABIN_HZ
        r = 0.16
        rows = 8
        for i in range(rows):
            y = Y + r + i * 0.3
            # back wall and the two side walls
            self._log(b, (-hx - 0.25, y, -hz), (hx + 0.25, y, -hz), r)
            self._log(b, (-hx, y + 0.15, -hz - 0.25), (-hx, y + 0.15, hz + 0.25), r)
            self._log(b, (hx, y + 0.15, -hz - 0.25), (hx, y + 0.15, hz + 0.25), r)
            # front wall, split around the door below the lintel
            if y < Y + 2.05:
                self._log(b, (-hx - 0.25, y, hz), (DOOR_HINGE_X - 0.05, y, hz), r)
                self._log(b, (0.55, y, hz), (hx + 0.25, y, hz), r)
            else:
                self._log(b, (-hx - 0.25, y, hz), (hx + 0.25, y, hz), r)
        top = Y + rows * 0.3 + 0.1
        # gable roof along x, with snow on it
        ridge = top + 1.15
        for s in (-1, 1):
            e = (hz + 0.55) * s
            b.quad((-hx - 0.45, top - 0.05, e), (hx + 0.45, top - 0.05, e), (hx + 0.45, ridge, 0.0), (-hx - 0.45, ridge, 0.0),
                   L.WOOD, (0.55, 0.5, 0.48))
            b.quad((-hx - 0.45, top + 0.06, e), (hx + 0.45, top + 0.06, e), (hx + 0.45, ridge + 0.11, 0.0),
                   (-hx - 0.45, ridge + 0.11, 0.0), L.CONCRETE, (2.05, 2.1, 2.3))
        for sx in (-hx, hx):
            b.quad((sx, top - 0.1, -hz - 0.2), (sx, top - 0.1, hz + 0.2), (sx, ridge - 0.05, 0.0), (sx, ridge - 0.05, 0.0),
                   L.WOOD, (0.6, 0.5, 0.42))
        # interior floor and ceiling boards
        b.quad((-hx, Y + 0.04, -hz), (hx, Y + 0.04, -hz), (hx, Y + 0.04, hz), (-hx, Y + 0.04, hz), L.WOOD, (0.7, 0.6, 0.5))
        # window on the left wall (glass panes both sides)
        for off in (-0.17, 0.17):
            b.facing_quad((-hx + off, Y + 1.35, -0.2), (1 if off > 0 else -1, 0, 0), 0.7, 0.55, L.METAL, (0.25, 0.3, 0.42))
        b.box((-hx, Y + 1.35, -0.2), (0.38, 0.04, 0.75), L.WOOD)
        b.box((-hx, Y + 1.35, -0.2), (0.38, 0.6, 0.04), L.WOOD)
        # stove and chimney pipe
        sx, sz = 0.6, -1.5
        b.box((sx, Y + 0.45, sz), (0.7, 0.75, 0.6), L.METAL, (0.35, 0.33, 0.33))
        b.box((sx, Y + 0.84, sz), (0.76, 0.05, 0.66), L.METAL, (0.3, 0.3, 0.3))
        b.box((sx, Y + 0.45, sz + 0.31), (0.3, 0.25, 0.02), L.BLACK)
        b.cylinder(0.09, 0.09, 4.2, 8, L.METAL, (0.4, 0.38, 0.36), m=T(sx, Y + 0.86, sz))
        b.box((sx - 0.5, Y + 0.25, sz + 0.1), (0.4, 0.4, 0.4), L.WOOD, (0.6, 0.55, 0.5))     # empty wood box
        # cot along the left wall
        cx, cz = -1.85, -0.85
        b.box((cx, Y + 0.38, cz), (0.75, 0.08, 1.9), L.WOOD, (0.7, 0.6, 0.5))
        for ox, oz in ((-0.33, -0.9), (0.33, -0.9), (-0.33, 0.9), (0.33, 0.9)):
            b.box((cx + ox, Y + 0.2, cz + oz), (0.05, 0.36, 0.05), L.WOOD)
        b.box((cx, Y + 0.47, cz + 0.1), (0.72, 0.1, 1.5), L.CLOTH, (0.6, 0.5, 0.45))
        b.box((cx, Y + 0.5, cz - 0.75), (0.5, 0.12, 0.3), L.PAPER, (0.9, 0.9, 0.85))
        # table and chair
        tx, tz = 1.6, -1.3
        b.box((tx, Y + 0.75, tz), (1.0, 0.06, 0.7), L.WOOD)
        for ox, oz in ((-0.43, -0.28), (0.43, -0.28), (-0.43, 0.28), (0.43, 0.28)):
            b.box((tx + ox, Y + 0.38, tz + oz), (0.06, 0.72, 0.06), L.WOOD)
        b.box((tx - 0.1, Y + 0.45, tz + 0.65), (0.45, 0.05, 0.45), L.WOOD)
        b.box((tx - 0.1, Y + 0.72, tz + 0.86), (0.45, 0.5, 0.05), L.WOOD)
        b.box((tx + 0.25, Y + 0.8, tz + 0.1), (0.12, 0.04, 0.08), L.PAPER, (0.9, 0.3, 0.2))   # matchbox
        # shelf with cans, a rug, a calendar
        b.box((2.2, Y + 1.5, 0.4), (0.25, 0.04, 1.0), L.WOOD)
        for k in range(4):
            b.cylinder(0.05, 0.05, 0.13, 6, L.METAL, (0.8, 0.8, 0.8), m=T(2.2, Y + 1.52, 0.05 + k * 0.22))
        b.quad((-0.9, Y + 0.05, -0.6), (0.6, Y + 0.05, -0.6), (0.6, Y + 0.05, 0.9), (-0.9, Y + 0.05, 0.9), L.REDCLOTH,
               uvs=((0, 0), (1, 0), (1, 1), (0, 1)))
        b.facing_quad((0.2, Y + 1.6, -hz + 0.18), (0, 0, 1), 0.4, 0.5, L.PAPER)
        # porch deck, steps, posts and the hanging lamp
        b.box((0.0, Y + 0.08, hz + 0.95), (2 * hx + 0.4, 0.14, 1.6), L.WOOD, (0.75, 0.65, 0.55))
        b.box((0.0, Y + 0.16, hz + 0.25), (2 * hx + 0.3, 0.02, 0.3), L.CONCRETE, (1.9, 1.95, 2.15))
        for px in (-hx, hx):
            b.box((px, Y + 1.25, hz + 1.65), (0.16, 2.5, 0.16), L.BARK, (0.8, 0.65, 0.5))
        b.box((0.0, Y + 2.5, hz + 1.65), (2 * hx + 0.3, 0.16, 0.16), L.BARK, (0.8, 0.65, 0.5))
        b.quad((-hx - 0.4, Y + 2.62, hz + 1.8), (hx + 0.4, Y + 2.62, hz + 1.8), (hx + 0.4, top + 0.05, hz + 0.55),
               (-hx - 0.4, top + 0.05, hz + 0.55), L.WOOD, (0.55, 0.5, 0.48))
        b.quad((-hx - 0.4, Y + 2.72, hz + 1.8), (hx + 0.4, Y + 2.72, hz + 1.8), (hx + 0.4, top + 0.15, hz + 0.55),
               (-hx - 0.4, top + 0.15, hz + 0.55), L.CONCRETE, (2.05, 2.1, 2.3))
        lx, lz = -hx + 0.3, hz + 1.65
        b.box((lx, Y + 2.25, lz), (0.02, 0.35, 0.02), L.BLACK)
        b.box((lx, Y + 1.98, lz), (0.16, 0.2, 0.16), L.GLOW + EMIS, (1.0, 0.7, 0.35))
        b.box((lx, Y + 2.1, lz), (0.2, 0.04, 0.2), L.METAL)
        b.box((lx, Y + 1.87, lz), (0.2, 0.04, 0.2), L.METAL)
        self.porch_lamp = (lx, Y + 1.98, lz)
        self.lights.append({'pos': (lx, Y + 1.9, lz), 'rad': 13.0, 'col': (0.95, 0.6, 0.28), 'flicker': 'fire'})
        # solid walls
        self.boxes.append((-hx - 0.25, -hz - 0.25, hx + 0.25, hz + 0.25))
        for px in (-hx, hx):
            self.boxes.append((px - 0.12, hz + 1.53, px + 0.12, hz + 1.77))

    def _landmarks(self, b, rng):
        # a dock out onto the lake
        dx, dz = DOCK
        h = float(terrain_h2(dx, dz))
        ang = math.atan2(LAKE[0] - dx, LAKE[1] - dz)
        m = T(dx, max(h, WL) + 0.35, dz) @ RY(ang)
        b.box((0, 0, 4.0), (1.8, 0.1, 9.0), L.WOOD, (0.6, 0.55, 0.5), m=m)
        b.box((0, 0.07, 4.0), (1.7, 0.03, 8.8), L.CONCRETE, (1.9, 1.95, 2.15), m=m)
        for k in range(5):
            for s in (-1, 1):
                b.box((s * 0.85, -1.0, k * 2.0 + 0.3), (0.14, 2.2, 0.14), L.BARK, m=m)
        b.box((0.4, 0.3, 7.8), (0.9, 0.5, 0.3), L.METAL, (0.5, 0.55, 0.65), m=m @ RZ(0.3))   # an overturned rowboat
        # a hunting stand
        sx, sz = STAND
        h = float(terrain_h2(sx, sz))
        for ox, oz in ((-0.9, -0.9), (0.9, -0.9), (-0.9, 0.9), (0.9, 0.9)):
            b.box((sx + ox, h + 2.2, sz + oz), (0.14, 4.4, 0.14), L.BARK)
        b.box((sx, h + 4.4, sz), (2.1, 0.1, 2.1), L.WOOD)
        b.box((sx, h + 4.4 + 0.5, sz - 1.0), (2.1, 1.0, 0.06), L.WOOD)
        b.box((sx, h + 5.6, sz), (2.3, 0.08, 2.3), L.METAL, (0.5, 0.45, 0.4))
        for k in range(8):
            b.box((sx, h + 0.4 + k * 0.5, sz + 1.0), (0.6, 0.06, 0.06), L.WOOD)
        self.boxes.append((sx - 1.0, sz - 1.0, sx + 1.0, sz + 1.0))
        # an outhouse
        ox, oz = OUTHOUSE
        h = float(terrain_h2(ox, oz))
        b.box((ox, h + 1.1, oz), (1.2, 2.2, 1.2), L.WOOD, (0.65, 0.55, 0.45))
        b.box((ox, h + 2.28, oz), (1.4, 0.12, 1.4), L.CONCRETE, (2.05, 2.1, 2.3))
        b.box((ox + 0.2, h + 1.6, oz + 0.61), (0.12, 0.12, 0.02), L.BLACK)
        self.boxes.append((ox - 0.65, oz - 0.65, ox + 0.65, oz + 0.65))


# ---------------------------------------------------------------------- small meshes
def wood_bundle_mesh():
    b = MeshBuilder()
    for i, (ox, oy) in enumerate(((-0.11, 0.1), (0.11, 0.1), (0.0, 0.28))):
        b.cylinder(0.1, 0.095, 0.85, 7, L.BARK, (0.95, 0.75, 0.55), m=T(ox, oy, -0.42) @ RX(math.pi / 2), cap=True)
    b.box((0, 0.39, 0), (0.25, 0.04, 0.7), L.CONCRETE, (2.05, 2.1, 2.3))
    b.box((0, 0.2, 0.0), (0.36, 0.03, 0.04), L.CLOTH, (0.6, 0.4, 0.3))   # twine
    return b.array()


def log_mesh():
    b = MeshBuilder()
    b.cylinder(0.085, 0.08, 0.7, 7, L.BARK, (0.95, 0.75, 0.55), m=RX(math.pi / 2) @ T(0, -0.35, 0), cap=True)
    return b.array()


def lantern_meshes():
    body = MeshBuilder()
    body.box((0, 0.02, 0), (0.17, 0.04, 0.17), L.METAL, (0.55, 0.5, 0.4))
    body.box((0, 0.27, 0), (0.15, 0.03, 0.15), L.METAL, (0.55, 0.5, 0.4))
    body.cylinder(0.05, 0.02, 0.07, 6, L.METAL, (0.55, 0.5, 0.4), m=T(0, 0.285, 0))
    for s in (-1, 1):
        body.box((s * 0.075, 0.15, 0), (0.012, 0.25, 0.012), L.METAL, (0.5, 0.45, 0.4))
    body.box((0, 0.42, 0), (0.12, 0.012, 0.012), L.METAL, (0.5, 0.45, 0.4))
    for s in (-1, 1):
        body.box((s * 0.06, 0.38, 0), (0.012, 0.08, 0.012), L.METAL, (0.5, 0.45, 0.4))
    lit = MeshBuilder()
    lit.cylinder(0.06, 0.06, 0.2, 8, L.GLOW + EMIS, (1.0, 0.72, 0.38), m=T(0, 0.04, 0), cap=True)
    off = MeshBuilder()
    off.cylinder(0.06, 0.06, 0.2, 8, L.METAL, (0.3, 0.32, 0.36), m=T(0, 0.04, 0), cap=True)
    return body.array(), lit.array(), off.array()


def door_mesh():
    b = MeshBuilder()
    for k in range(5):
        b.box((0.1 + k * 0.205, 1.0, 0), (0.2, 2.0, 0.06), L.WOOD, (0.7, 0.55, 0.42))
    for y in (0.4, 1.6):
        b.box((0.52, y, 0.04), (0.95, 0.12, 0.03), L.WOOD, (0.6, 0.48, 0.38))
    b.box((0.88, 1.0, 0.07), (0.05, 0.05, 0.06), L.METAL)
    return b.array()


def snow_mesh(n=900, seed=5):
    rng = np.random.default_rng(seed)
    b = MeshBuilder()
    for _ in range(n):
        x, y, z = rng.uniform(0, 30), rng.uniform(0, 12), rng.uniform(0, 30)
        s = rng.uniform(0.025, 0.05)
        b.box((x, y, z), (s, s, s), L.GLOW, (0.82, 0.85, 0.9))
    return b.array()


# ---------------------------------------------------------------------- the Goat Man, hunting
class GoatHunter:
    """Roams the snowy map looking for you. The lantern lets him see you from
    much further away; running is loud; crouching in the dark hides you."""

    def __init__(self, w):
        self.w = w
        self.x, self.z = -70.0, 75.0
        self.y = float(terrain_h2(self.x, self.z))
        self.yaw = 0.0
        self.state = 'roam'
        self.target = None
        self.timer = 0.0
        self.sense_t = 0.0
        self.seen_t = 0.0
        self.last_seen = None
        self.grace = 0.0
        self.phase = 0.0
        self.amt = 0.0
        self.step = 0.0
        self.stuck = 0.0
        self.events = []
        self.snap = (0.0, 0.0, 0.0)
        self.snap_t = 0.0
        self.roll = 0.0
        self.rng = random.Random()

    def place_far(self, px, pz):
        best = None
        for _ in range(40):
            x, z = self.w.random_land(self.rng, margin=12)
            d = math.hypot(x - px, z - pz)
            if best is None or d > best[0]:
                best = (d, x, z)
        _, self.x, self.z = best
        self.y = float(terrain_h2(self.x, self.z))
        self.state = 'roam'
        self.target = None

    def hear(self, x, z, radius):
        if self.grace > 0 or self.state == 'chase':
            return
        if math.hypot(x - self.x, z - self.z) < radius:
            self.state = 'investigate'
            self.target = (x, z)
            self.timer = 0.0

    def update(self, dt, player, lantern_on):
        self.grace = max(0.0, self.grace - dt)
        px, pz = player.x, player.z
        dx, dz = px - self.x, pz - self.z
        dist = math.hypot(dx, dz)
        self.sense_t -= dt
        if self.sense_t <= 0 and self.grace <= 0:
            self.sense_t = 0.2
            vision = 26.0 if lantern_on else 10.0
            if player.crouch > 0.5:
                vision *= 0.6
            fx, fz = math.sin(self.yaw), math.cos(self.yaw)
            facing = (fx * dx + fz * dz) / max(dist, 1e-4) > 0.1 or dist < 6.0
            if dist < vision and (facing or self.state == 'chase'):
                if self.state != 'chase':
                    self.events.append('roar')
                self.state = 'chase'
                self.seen_t = 0.0
                self.last_seen = (px, pz)
        speed = 0.0
        st = self.state
        if st == 'chase':
            speed = 4.1
            self.seen_t += dt
            if dist < 34 and self.seen_t < 0.25:
                self.target = (px, pz)
            if self.seen_t > 5.0 or dist > 40:
                self.state = 'investigate'
                self.target = self.last_seen
                self.timer = 0.0
            if dist < 1.45:
                self.events.append('kill')
        elif st == 'investigate':
            speed = 2.8
            if self.target is None or math.hypot(self.target[0] - self.x, self.target[1] - self.z) < 1.5:
                speed = 0.0
                self.timer += dt
                self.yaw += math.sin(self.timer * 1.6) * dt * 1.4
                if self.timer > 4.0:
                    self.state = 'roam'
                    self.target = None
        else:
            speed = 1.9
            if self.target is None or math.hypot(self.target[0] - self.x, self.target[1] - self.z) < 2.0:
                self.timer -= dt
                speed = 0.0
                if self.timer <= 0:
                    # he is looking for you: half his walks head toward where you are
                    if self.rng.random() < 0.55:
                        ang = self.rng.random() * 6.28
                        r = self.rng.uniform(8, 30)
                        tx, tz = px + math.cos(ang) * r, pz + math.sin(ang) * r
                    else:
                        tx, tz = self.w.random_land(self.rng, margin=10)
                    self.target = (clamp(tx, -HALF + 8, HALF - 8), clamp(tz, -HALF + 8, HALF - 8))
                    self.timer = self.rng.uniform(1.5, 4.0)
        moved = 0.0
        if self.target is not None and speed > 0:
            tx, tz = self.target
            mx, mz = tx - self.x, tz - self.z
            md = math.hypot(mx, mz)
            if md > 1e-3:
                step = min(md, speed * dt)
                nx, nz = self.w.collide(self.x + mx / md * step, self.z + mz / md * step, 0.6, self.x, self.z)
                moved = math.hypot(nx - self.x, nz - self.z)
                self.x, self.z = nx, nz
                a = math.atan2(mx, mz)
                d = (a - self.yaw + math.pi) % (2 * math.pi) - math.pi
                self.yaw += d * min(1.0, dt * (6 if st == 'chase' else 3))
        if speed > 0 and moved < speed * dt * 0.25:
            self.stuck += dt
            if self.stuck > 1.2:
                self.stuck = 0.0
                if st == 'chase':
                    # slide sideways around whatever is in the way
                    ang = self.yaw + self.rng.choice((-1.3, 1.3))
                    self.target = (self.x + math.sin(ang) * 6, self.z + math.cos(ang) * 6)
                    self.seen_t = 0.3
                else:
                    self.target = None
                    self.timer = 0.0
        else:
            self.stuck = 0.0
        self.y += (float(terrain_h2(self.x, self.z)) - self.y) * min(1.0, dt * 8)
        self.amt += (min(1.0, moved / max(dt, 1e-4) / 2.5) - self.amt) * min(1.0, dt * 6)
        self.phase += moved * 1.9
        self.step += moved
        if self.step > 1.5:
            self.step = 0.0
            self.events.append('step')
        self.snap_t -= dt
        if self.snap_t <= 0:
            self.snap_t = self.rng.uniform(0.07, 0.15)
            if self.rng.random() < 0.3:
                self.roll = self.rng.uniform(-0.45, 0.45)
            elif self.rng.random() < 0.5:
                self.roll = 0.0
            self.snap = (self.phase, self.amt, self.roll)
