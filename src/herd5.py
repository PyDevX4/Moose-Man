"""Chapter 5: the Herd, possessed.

The people he took and stood in his rooms. Down in the factory they move again:
antlers wired to their heads, eyes burning the same red as his, walking you down
in a slow, jerking shamble. One good blast from the shotgun puts one down.

The host runs them (like every monster); everyone else gets their positions and
states and animates them. Each machine works out its own hits.

States (st): 0 wander, 1 chase, 2 swing wind-up, 3 recover, 4 dead, 5 flinch.
"""
import math
import random

from engine import MeshBuilder, T, S, RX, RY, RZ
from textures import L, EMIS
from moose import unit_cube

WANDER, CHASE, WIND, RECOVER, DEAD, FLINCH = range(6)
MAX_HP = 8.0
SPEED_CHASE = 2.25          # you walk at 2.7: walk away and you keep your distance, just
SPEED_WANDER = 0.75
SEE = 15.0
REACH = 1.35
HIT_RANGE = 1.75
DAMAGE = 20.0
WIND_T = 0.55
RECOVER_T = 0.95
FLINCH_T = 0.35


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


# ---------------------------------------------------------------------- meshes
def possessed_head_mesh():
    """The herd head (pale, antlers wired on), with his eyes in it now and a wet mouth."""
    b = MeshBuilder()
    b.box((0, 0.13, 0), (0.2, 0.25, 0.22), L.SKIN, (0.78, 0.74, 0.72))
    for s in (-1, 1):
        b.box((s * 0.05, 0.16, 0.111), (0.05, 0.04, 0.012), L.BLACK)
        b.box((s * 0.05, 0.16, 0.116), (0.026, 0.022, 0.01), L.GLOW + EMIS, (1.0, 0.12, 0.05))
    b.box((0, 0.065, 0.111), (0.09, 0.045, 0.012), L.BLACK)
    b.box((0, 0.04, 0.112), (0.06, 0.04, 0.01), L.BLOOD, (0.8, 0.3, 0.3))
    for s in (-1, 1):
        m = T(s * 0.07, 0.24, 0) @ RZ(-s * 0.45)
        b.box((0, 0.25, 0), (0.035, 0.5, 0.035), L.BARK, (0.8, 0.8, 0.8), m=m)
        m2 = m @ T(0, 0.3, 0) @ RZ(-s * 0.7)
        b.box((0, 0.13, 0), (0.025, 0.26, 0.025), L.BARK, (0.8, 0.8, 0.8), m=m2)
        m3 = m @ T(0, 0.42, 0) @ RZ(s * 0.5)
        b.box((0, 0.1, 0), (0.02, 0.2, 0.02), L.BARK, (0.8, 0.8, 0.8), m=m3)
        b.box((s * 0.02, 0.24, 0), (0.06, 0.03, 0.24), L.METAL, (0.4, 0.38, 0.36))     # the wire
    return b.array()


def herd_meshes():
    return {
        'h_cloth': unit_cube(L.CLOTH, (0.5, 0.48, 0.45)),
        'h_cloth2': unit_cube(L.CLOTH, (0.35, 0.38, 0.45)),
        'h_skin': unit_cube(L.SKIN, (0.78, 0.74, 0.72)),
        'h_head': possessed_head_mesh(),
    }


def pose_herd(x, z, yaw, walk=0.0, amt=0.0, reach=0.0, fall=0.0, t=0.0, seed=0, swing=0.0, flinch=0.0):
    """One of them, as (mesh key, matrix) parts. fall: 0 standing .. 1 on its back."""
    rng = random.Random(seed)
    h = 0.92 + 0.16 * rng.random()
    cloth = 'h_cloth' if seed % 2 else 'h_cloth2'
    out = []
    add = out.append
    fall_e = fall * fall * (3 - 2 * fall)
    B = T(x, 0.12 * fall_e, z) @ RY(yaw) @ RX(-fall_e * math.pi / 2) @ S(h, h, h)
    sw = math.sin(walk) * 0.55 * amt * (1 - fall)
    # legs
    for sx, ph in ((-1, 1.0), (1, -1.0)):
        a = sw * ph
        if fall > 0:
            a = 0.25 * sx * fall
        add((cloth, B @ T(sx * 0.1, 0.85, 0) @ RX(a) @ T(0, -0.425, 0) @ S(0.13, 0.85, 0.14)))
    # a possessed lurch: the torso jerks and leans in
    jerk = 0.12 * (math.sin(t * 11 + seed) > 0.93) + 0.05 * math.sin(t * 3.1 + seed)
    hunch = 0.22 + 0.25 * reach + jerk - 0.5 * flinch
    Tt = B @ T(0, 0.85, 0) @ RX(hunch * (1 - fall)) @ RZ(0.05 * math.sin(walk * 0.5) * amt)
    add((cloth, Tt @ T(0, 0.32, 0) @ S(0.38, 0.64, 0.22)))
    # arms: hanging and swinging, coming up to grab, then down hard on a swing
    for sx in (-1, 1):
        lift = reach * 1.45 + swing * (-1.2 if sx > 0 else -0.9)
        a = -lift + 0.3 * sw * sx
        if fall > 0:
            a = -2.6 * fall
        A = Tt @ T(sx * 0.23, 0.6, 0) @ RX(a) @ RZ(sx * (0.08 + 0.4 * fall))
        add(('h_skin', A @ T(0, -0.32, 0) @ S(0.08, 0.64, 0.09)))
    add(('h_skin', Tt @ T(0, 0.67, 0) @ S(0.08, 0.1, 0.08)))
    tilt = 0.35 * (1 if seed % 3 else -1) + 0.4 * (math.sin(t * 17 + seed * 2) > 0.95)
    add(('h_head', Tt @ T(0, 0.7, 0.02) @ RZ(tilt * (1 - 0.5 * fall)) @ RX(0.2 - 0.6 * reach)))
    return out


# ---------------------------------------------------------------------- the sim
class Herd5:
    """All of them at once, so co-op can send them as a handful of short tuples."""

    def __init__(self, fac, n=8, seed=5):
        self.fac = fac
        self.n = n
        rng = random.Random(seed)
        ex, ez = fac.center(57, 27)
        cells = [(c, r) for (c, r) in fac.floor_cells() if fac.g[r][c] == '.'
                 and math.hypot(fac.center(c, r)[0] - ex, fac.center(c, r)[1] - ez) > 22]
        picks = []
        rng.shuffle(cells)
        for cell in cells:
            x, z = fac.center(*cell)
            if all(math.hypot(x - px, z - pz) > 16 for px, pz in picks):
                picks.append((x, z))
            if len(picks) >= n:
                break
        while len(picks) < n:
            picks.append(fac.center(*rng.choice(cells)))
        self.xs = tuple(round(p[0], 2) for p in picks)
        self.zs = tuple(round(p[1], 2) for p in picks)
        self.yaws = tuple(round(rng.random() * 6.28, 2) for _ in range(n))
        self.hps = tuple(MAX_HP for _ in range(n))
        self.st = tuple(WANDER for _ in range(n))
        self.events = []
        # host only (dicts and lists of lists: never sent)
        self._ai = {'t': [0.0] * n, 'path': [[] for _ in range(n)], 'repath': [rng.random() for _ in range(n)],
                    'lost': [0.0] * n, 'goal': [None] * n, 'rng': rng}
        # everyone: what's drawn
        self._d = {'x': list(self.xs), 'z': list(self.zs), 'yaw': list(self.yaws), 'walk': [0.0] * n,
                   'amt': [0.0] * n, 'fall': [0.0] * n, 'reach': [0.0] * n, 'swing': [0.0] * n, 'flinch': [0.0] * n}

    def alive(self, i):
        return i < len(self.st) and self.st[i] != DEAD

    def count_alive(self):
        return sum(1 for s in self.st if s != DEAD)

    # ---- the host
    def hear(self, x, z, radius):
        """A gunshot: every one of them in earshot comes."""
        st = list(self.st)
        for i in range(self.n):
            if st[i] == WANDER and math.hypot(self.xs[i] - x, self.zs[i] - z) < radius:
                st[i] = CHASE
                self._ai['lost'][i] = 0.0
                self._ai['path'][i] = []
                self._ai['repath'][i] = 0.0
        self.st = tuple(st)

    def damage(self, i, amt):
        if not (0 <= i < self.n) or self.st[i] == DEAD:
            return
        hps = list(self.hps)
        st = list(self.st)
        hps[i] = round(max(0.0, hps[i] - amt), 2)
        if hps[i] <= 0:
            st[i] = DEAD
            self.events.append(('die', i))
        else:
            st[i] = FLINCH
            self._ai['t'][i] = FLINCH_T
            self.events.append(('flinch', i))
        self.hps, self.st = tuple(hps), tuple(st)

    def walkable(self, x, z):
        c, r = self.fac.cell_of(x, z)
        return self.fac.kind(c, r) == '.'

    def _path(self, i, x, z, tx, tz):
        fac = self.fac
        a, g = fac.cell_of(x, z), fac.cell_of(tx, tz)
        if fac.kind(*g) != '.':
            return []
        fac.open_cell = lambda c, r, elk=False: fac.kind(c, r) == '.'
        try:
            p = fac.astar(a, g, elk=False, max_nodes=2500)
        finally:
            del fac.open_cell
        return [fac.center(c, r) for (c, r) in (p or [])[1:]]

    def update(self, dt, targets):
        """targets: [(x, z)] of everyone it could go for (alive, in the factory).
        Events pile up until the game has read them (it clears them)."""
        ai = self._ai
        rng = ai['rng']
        xs, zs, yaws, st = list(self.xs), list(self.zs), list(self.yaws), list(self.st)
        for i in range(self.n):
            s = st[i]
            if s == DEAD:
                continue
            x, z = xs[i], zs[i]
            best = None
            for (tx, tz) in targets:
                d = math.hypot(tx - x, tz - z)
                if best is None or d < best[0]:
                    best = (d, tx, tz)
            sees = best is not None and (best[0] < 4.0 or (best[0] < SEE and self.fac.los(x, z, best[1], best[2])))
            ai['t'][i] -= dt
            speed = 0.0
            goal = None
            if s == FLINCH:
                if ai['t'][i] <= 0:
                    s = CHASE if best else WANDER
            elif s == WIND:
                if ai['t'][i] <= 0:
                    hx, hz = x + math.sin(yaws[i]) * 0.9, z + math.cos(yaws[i]) * 0.9
                    self.events.append(('hit', i, round(hx, 2), round(hz, 2)))
                    s = RECOVER
                    ai['t'][i] = RECOVER_T
            elif s == RECOVER:
                if ai['t'][i] <= 0:
                    s = CHASE
            elif s == WANDER:
                if sees:
                    s = CHASE
                    ai['lost'][i] = 0.0
                    self.events.append(('alert', i))
                else:
                    if not ai['path'][i] or ai['t'][i] <= 0:
                        c, r = self.fac.cell_of(x, z)
                        for _ in range(12):
                            gc, gr = c + rng.randint(-8, 8), r + rng.randint(-8, 8)
                            if self.fac.kind(gc, gr) == '.':
                                ai['path'][i] = self._path(i, x, z, *self.fac.center(gc, gr))
                                break
                        ai['t'][i] = rng.uniform(5.0, 11.0)
                    speed = SPEED_WANDER
            if s == CHASE:
                if best is None:
                    s = WANDER
                else:
                    ai['lost'][i] = 0.0 if sees else ai['lost'][i] + dt
                    if ai['lost'][i] > 7.0:
                        s = WANDER
                        ai['path'][i] = []
                    elif best[0] < REACH:
                        s = WIND
                        ai['t'][i] = WIND_T
                        yaws[i] = math.atan2(best[1] - x, best[2] - z)
                        self.events.append(('wind', i))
                    else:
                        speed = SPEED_CHASE * (0.8 + 0.35 * max(0.0, math.sin(ai['repath'][i] * 40 + x)))
                        if sees and best[0] < 7.0:
                            goal = (best[1], best[2])
                            ai['path'][i] = []
                        else:
                            ai['repath'][i] -= dt
                            if ai['repath'][i] <= 0 or not ai['path'][i]:
                                ai['repath'][i] = 0.7
                                ai['path'][i] = self._path(i, x, z, best[1], best[2])
            if speed > 0:
                if goal is None and ai['path'][i]:
                    gx, gz = ai['path'][i][0]
                    if math.hypot(gx - x, gz - z) < 0.4:
                        ai['path'][i].pop(0)
                    goal = (gx, gz)
                if goal is not None:
                    dx, dz = goal[0] - x, goal[1] - z
                    d = math.hypot(dx, dz)
                    if d > 1e-3:
                        want = math.atan2(dx, dz)
                        dy = (want - yaws[i] + math.pi) % (2 * math.pi) - math.pi
                        yaws[i] += dy * min(1.0, dt * 6)
                        step = min(d, speed * dt)
                        nx, nz = x + dx / d * step, z + dz / d * step
                        nx, nz = self.fac.collide(nx, nz, 0.3)
                        if self.walkable(nx, nz):
                            x, z = nx, nz
            # keep apart
            for j in range(self.n):
                if j != i and st[j] != DEAD:
                    dx, dz = x - xs[j], z - zs[j]
                    d = math.hypot(dx, dz)
                    if 1e-4 < d < 0.75:
                        px, pz = x + dx / d * (0.75 - d) * 0.5, z + dz / d * (0.75 - d) * 0.5
                        if self.walkable(px, pz):
                            x, z = px, pz
            xs[i], zs[i], st[i] = round(x, 2), round(z, 2), s
        self.xs, self.zs, self.st = tuple(xs), tuple(zs), tuple(st)
        self.yaws = tuple(round((y + math.pi) % (2 * math.pi) - math.pi, 3) for y in yaws)

    def push_out(self, x, z, rad=0.3):
        """Keep a player out of their bodies."""
        self._fit()
        for i in range(self.n):
            if self.st[i] == DEAD:
                continue
            dx, dz = x - self._d['x'][i], z - self._d['z'][i]
            d = math.hypot(dx, dz)
            if 1e-4 < d < rad + 0.32:
                x = self._d['x'][i] + dx / d * (rad + 0.32)
                z = self._d['z'][i] + dz / d * (rad + 0.32)
        return x, z

    # ---- everyone: smooth and animate
    def _fit(self):
        """A client's copy grows (or shrinks) to however many the host has."""
        d = self._d
        n = min(len(self.xs), len(self.zs), len(self.yaws), len(self.st), len(self.hps))
        for key, lst in d.items():
            del lst[n:]
            while len(lst) < n:
                lst.append(self.xs[len(lst)] if key == 'x' else self.zs[len(lst)] if key == 'z' else 0.0)
        self.n = n

    def animate(self, dt):
        self._fit()
        d = self._d
        k = min(1.0, dt * 12)
        for i in range(self.n):
            if i >= len(self.xs):
                break
            ox, oz = d['x'][i], d['z'][i]
            if math.hypot(self.xs[i] - ox, self.zs[i] - oz) > 4:
                d['x'][i], d['z'][i] = self.xs[i], self.zs[i]
            else:
                d['x'][i] += (self.xs[i] - ox) * k
                d['z'][i] += (self.zs[i] - oz) * k
            dy = (self.yaws[i] - d['yaw'][i] + math.pi) % (2 * math.pi) - math.pi
            d['yaw'][i] += dy * k
            moved = math.hypot(d['x'][i] - ox, d['z'][i] - oz)
            d['walk'][i] += moved * 4.2
            d['amt'][i] += (min(1.0, moved / max(dt, 1e-4) / 1.5) - d['amt'][i]) * min(1.0, dt * 6)
            s = self.st[i]
            d['fall'][i] = min(1.0, d['fall'][i] + dt / 0.7) if s == DEAD else 0.0
            d['reach'][i] += ((1.0 if s in (CHASE, WIND) else 0.0) - d['reach'][i]) * min(1.0, dt * 4)
            d['swing'][i] += ((1.0 if s == WIND else 0.0) - d['swing'][i]) * min(1.0, dt * (10 if s == WIND else 5))
            d['flinch'][i] += ((1.0 if s == FLINCH else 0.0) - d['flinch'][i]) * min(1.0, dt * 14)

    def parts(self, t):
        self._fit()
        d = self._d
        out = []
        for i in range(min(self.n, len(self.xs))):
            out.append(pose_herd(d['x'][i], d['z'][i], d['yaw'][i], d['walk'][i], d['amt'][i], d['reach'][i] * (1 - d['swing'][i]),
                                 d['fall'][i], t, seed=i * 7 + 3, swing=d['swing'][i], flinch=d['flinch'][i]))
        return out

    def hit_spheres(self, i):
        """(centre, radius, damage multiplier) for shooting."""
        x, z = self._d['x'][i], self._d['z'][i]
        return [((x, 1.72, z), 0.2, 2.0), ((x, 1.15, z), 0.32, 1.0), ((x, 0.5, z), 0.28, 0.8)]
