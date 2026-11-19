"""The longer chapters (1.17). Mixed into game.Game.

Chapter One:   the ladder gate opens onto a long tunnel and a drop shaft. The catwalk
               across it has a gap: find a long plank somewhere in the sewers, lay it
               over, and walk it -- slowly, keeping your balance with [A] and [D].
               The ladder up is on the far side.
Chapter Three: the cart's power lever snaps off. Find the generator it was wired to.
               The rails now end in the Herd's caves: they are asleep on their feet.
               Find dynamite, wire and a detonator, pack the charge into the wall,
               run the wire back, set the detonator down, and blow a way through to
               the old mine (and the Goat Man).
Chapter Four:  the three generators are somewhere different every game, and they are
               dry. Find the gas can.
"""
import math
import random

import pygame

from engine import Mesh, MeshBuilder, T, S, RX, RY, RZ
from textures import L, EMIS
from moose import unit_cube
import world as W
import chapter3 as C3
import chapter4 as C4
import herd5 as H5
import shaft as SH

SLEEP = 9                 # a Herd state of our own: standing asleep where they were left
BAL_SPEED = 0.85          # how fast you can walk the plank
WIRE_SAFE = 14.0          # how far from the charge the detonator has to be
BLAST_KILL = 9.0
C3_ITEMS = ('dynamite', 'wire', 'detonator')
ITEM_NAMES = {'dynamite': "DYNAMITE", 'wire': "WIRE", 'detonator': "DETONATOR"}


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def ray_sphere(o, d, c, r):
    ox, oy, oz = o[0] - c[0], o[1] - c[1], o[2] - c[2]
    b = ox * d[0] + oy * d[1] + oz * d[2]
    cq = ox * ox + oy * oy + oz * oz - r * r
    disc = b * b - cq
    if disc < 0:
        return None
    t = -b - math.sqrt(disc)
    return t if t > 0 else None


def pick_spread(rng, cands, n, min_d, pos):
    cands = list(cands)
    rng.shuffle(cands)
    out = []
    for s in cands:
        p = pos(s)
        if all(math.hypot(p[0] - pos(o)[0], p[1] - pos(o)[1]) >= min_d for o in out):
            out.append(s)
        if len(out) >= n:
            break
    while len(out) < n and cands:
        out.append(rng.choice(cands))
    return out


# ---------------------------------------------------------------------- meshes
def dynamite_mesh():
    b = MeshBuilder()
    for k, (x, y) in enumerate(((-0.05, 0.04), (0.05, 0.04), (0.0, 0.12))):
        b.cylinder(0.045, 0.045, 0.32, 8, L.CLOTH, (0.75, 0.12, 0.08), m=T(x, y, -0.16) @ RX(math.pi / 2))
    b.box((0, 0.08, 0), (0.2, 0.16, 0.05), L.CLOTH, (0.2, 0.2, 0.22))                       # tape
    b.box((0, 0.13, 0.19), (0.01, 0.01, 0.1), L.BLACK)                                       # fuse wire
    return b.array()


def spool_mesh():
    b = MeshBuilder()
    m = RZ(math.pi / 2)
    b.cylinder(0.2, 0.2, 0.03, 12, L.WOOD, (0.6, 0.45, 0.3), m=T(-0.14, 0.2, 0) @ m)
    b.cylinder(0.2, 0.2, 0.03, 12, L.WOOD, (0.6, 0.45, 0.3), m=T(0.14 + 0.03, 0.2, 0) @ m)
    b.cylinder(0.13, 0.13, 0.28, 12, L.CLOTH, (0.12, 0.12, 0.12), m=T(-0.12, 0.2, 0) @ m)
    return b.array()


def detonator_mesh():
    b = MeshBuilder()
    b.box((0, 0.13, 0), (0.32, 0.26, 0.26), L.WOOD, (0.55, 0.35, 0.2))
    b.box((0, 0.27, 0), (0.34, 0.03, 0.28), L.METAL, (0.3, 0.3, 0.3))
    b.box((0.1, 0.18, 0.135), (0.08, 0.05, 0.01), L.SIGN, (0.9, 0.8, 0.6))
    for x in (-0.1, 0.1):
        b.cylinder(0.018, 0.018, 0.04, 6, L.METAL, (0.75, 0.6, 0.2), m=T(x, 0.27, -0.1))
    return b.array()


def plunger_mesh():
    b = MeshBuilder()
    b.box((0, 0.17, 0), (0.035, 0.34, 0.035), L.METAL, (0.55, 0.55, 0.55))
    b.box((0, 0.34, 0), (0.3, 0.04, 0.04), L.WOOD, (0.4, 0.25, 0.15))
    return b.array()


def rockplug_mesh():
    """The wall at the end of the drift: rock, cracked, with loose stones at its foot."""
    rng = random.Random(31)
    b = MeshBuilder()
    rock = (0.58, 0.53, 0.48)
    b.box((0, 1.25, 0), (2.0, 2.5, 2.0), L.CONCRETE, rock)
    for _ in range(18):
        s = rng.uniform(0.2, 0.55)
        x = rng.uniform(-0.9, 0.9)
        z = rng.choice((-1.05, 1.05))
        m = T(x, rng.uniform(0.0, 2.3), z) @ RY(rng.random() * 6) @ RX(rng.uniform(-0.5, 0.5))
        b.box((0, 0, 0), (s, s * 0.8, s * 0.6), L.CONCRETE, (0.5, 0.46, 0.42), m=m)
    for _ in range(10):
        s = rng.uniform(0.15, 0.4)
        z = rng.choice((-1.0, 1.0)) * rng.uniform(1.1, 1.8)
        b.box((rng.uniform(-0.8, 0.8), s * 0.4, z), (s, s * 0.8, s), L.CONCRETE, (0.52, 0.48, 0.44),
              m=RY(rng.random() * 6))
    # a crack, and something scratched in the rock on the Herd's side
    b.box((0.1, 1.2, -1.01), (0.04, 1.8, 0.02), L.BLACK, m=RZ(0.25))
    b.facing_quad((-0.3, 1.5, -1.03), (0, 0, -1), 0.7, 0.7, L.TALLY, (0.8, 0.75, 0.7))
    return b.array()


def rubble_mesh():
    rng = random.Random(32)
    b = MeshBuilder()
    for _ in range(46):
        s = rng.uniform(0.12, 0.42)
        a = rng.random() * 6.28
        rr = rng.uniform(0.0, 2.4)
        m = T(math.cos(a) * rr * 0.45, s * 0.2, math.sin(a) * rr) @ RY(rng.random() * 6) @ RX(rng.uniform(-0.6, 0.6))
        b.box((0, 0, 0), (s, s * 0.7, s * 0.8), L.CONCRETE, (0.5, 0.46, 0.42), m=m)
    return b.array()


# ---------------------------------------------------------------------- the Herd, asleep in the mine
class Herd3(H5.Herd5):
    """The Herd in Chapter Three's caves. They stand asleep (SLEEP) until something wakes them,
    and never leave their caves (`lv.herd_cells`)."""

    def __init__(self, lv, homes=(), seed=3):
        self.lv = lv
        super().__init__(lv, n=0, seed=seed)
        if homes:
            self.populate(homes)

    def populate(self, homes):
        n = len(homes)
        rng = self._ai['rng']
        self.xs = tuple(round(h[0], 2) for h in homes)
        self.zs = tuple(round(h[1], 2) for h in homes)
        self.yaws = tuple(round(h[2], 2) for h in homes)
        self.hps = tuple(H5.MAX_HP for _ in range(n))
        self.st = tuple(SLEEP for _ in range(n))
        self._ai = {'t': [0.0] * n, 'path': [[] for _ in range(n)], 'repath': [rng.random() for _ in range(n)],
                    'lost': [0.0] * n, 'goal': [None] * n, 'rng': rng}
        self.n = n
        self._fit()
        self._d['rise'] = [1.0] * n
        self._d['yaw'] = list(self.yaws)

    def walkable(self, x, z):
        c, r = self.lv.cell_of(x, z)
        return (c, r) in self.lv.herd_cells

    def _path(self, i, x, z, tx, tz):
        lv = self.lv
        a, g = lv.cell_of(x, z), lv.cell_of(tx, tz)
        cells = lv.herd_cells
        if g not in cells or a not in cells:
            return []
        lv.open_cell = lambda c, r, elk=False: (c, r) in cells
        try:
            p = lv.astar(a, g, elk=False, max_nodes=2500)
        finally:
            del lv.open_cell
        return [lv.center(c, r) for (c, r) in (p or [])[1:]]

    def wake(self, i):
        if self.st[i] != SLEEP:
            return
        st = list(self.st)
        st[i] = H5.CHASE
        self.st = tuple(st)
        self._ai['lost'][i] = 0.0
        self._ai['path'][i] = []
        self.events.append(('alert', i))

    def hear(self, x, z, radius):
        for i in range(self.n):
            if self.st[i] == SLEEP and math.hypot(self.xs[i] - x, self.zs[i] - z) < radius:
                self.wake(i)
        super().hear(x, z, radius)

    def asleep(self, i):
        return i < len(self.st) and self.st[i] == SLEEP

    def parts(self, t):
        self._fit()
        d = self._d
        y0 = self.lv.y0
        out = []
        for i in range(min(self.n, len(self.xs))):
            out.append(H5.pose_herd(d['x'][i], d['z'][i], d['yaw'][i], d['walk'][i], d['amt'][i],
                                    d['reach'][i] * (1 - d['swing'][i]), d['fall'][i], t, seed=i * 7 + 3,
                                    swing=d['swing'][i], flinch=d['flinch'][i],
                                    y=y0 - 1.9 * (1.0 - d['rise'][i]) ** 1.5))
        return out

    def hit_spheres(self, i):
        x, z = self._d['x'][i], self._d['z'][i]
        y0 = self.lv.y0
        return [((x, y0 + 1.72, z), 0.2, 2.0), ((x, y0 + 1.15, z), 0.32, 1.0), ((x, y0 + 0.5, z), 0.28, 0.8)]


# ---------------------------------------------------------------------- the mixin
class Puzzles2Mixin:
    def init_puzzles2(self, prog):
        self.m_plank1 = Mesh(self.ctx, prog, SH.plank_mesh())
        self.m_gen = Mesh(self.ctx, prog, C4.generator_mesh())
        self.m_jug = Mesh(self.ctx, prog, C4.jug_mesh())
        self.m_dyn = Mesh(self.ctx, prog, dynamite_mesh())
        self.m_spool = Mesh(self.ctx, prog, spool_mesh())
        self.m_det = Mesh(self.ctx, prog, detonator_mesh())
        self.m_plunger = Mesh(self.ctx, prog, plunger_mesh())
        self.m_rockplug = Mesh(self.ctx, prog, rockplug_mesh())
        self.m_rubble = Mesh(self.ctx, prog, rubble_mesh())
        self.m_wire = Mesh(self.ctx, prog, unit_cube(L.BLACK, (0.05, 0.05, 0.05)))
        self.m_genlamp_off3 = Mesh(self.ctx, prog, unit_cube(L.GLOW + EMIS, (0.5, 0.04, 0.02)))
        self.m_genlamp_on3 = Mesh(self.ctx, prog, unit_cube(L.GLOW + EMIS, (0.2, 1.0, 0.25)))
        self.find_spots_p2()
        self.plank1_pos = (0.0, -5.0, 0.0, 0.0)
        self.c3gen = {'running': False, 'progress': 0.0, 'pos': (0, 0, 0), 'base': (0, 0, 0), 'yaw': 0.0,
                      'lamp': (0, 0, 0), 'box': (0, 0, 0, 0)}
        self.c3item_pos = {k: (0.0, 0.0, 0.0) for k in C3_ITEMS}
        self.herd3_homes = []
        self.reset_p2()

    def my_pid(self):
        return self.mp.pid if self.mp_on() else 0

    # ================================================================== where things can go
    def find_spots_p2(self):
        from gridgrow import zones_of
        w = self.world
        z1 = zones_of(w.g, '.~tWSX', 'WS')
        pre, post = z1.get((9, 18)), z1.get((8, 50))
        self.spots_plank1 = []
        for r in range(W.ROWS):
            for c in range(W.COLS):
                if w.g[r][c] != '.' or z1.get((c, r)) != post:      # past the drained chamber, with the key
                    continue
                if w.basin[r, c]:
                    continue
                if all(w.kind(c + dc, r) == '.' for dc in (-2, -1, 1, 2)) and all(w.kind(c, r + dr) == '.' for dr in (-1, 1)):
                    if all(abs(float(w.floor[r, c + dc]) - float(w.floor[r, c])) < 0.05 for dc in (-2, -1, 1, 2)):
                        self.spots_plank1.append((c, r))

    def randomize_p2(self, seed):
        cc = W.cell_center
        w = self.world
        # chapter 1: the plank, well away from the key
        rng = random.Random(seed * 10 + 6)
        kp = w.key_pos or (0.0, 0.0, 0.0)
        cands = [s for s in self.spots_plank1 if math.hypot(cc(*s)[0] - kp[0], cc(*s)[1] - kp[2]) > 20] or self.spots_plank1
        if cands:
            c, r = rng.choice(cands)
            x, z = cc(c, r)
            self.plank1_pos = (x, float(w.floor[r, c]) + 0.01, z + rng.uniform(-0.3, 0.3), rng.uniform(-0.12, 0.12))
        # chapter 3: the generator in the yard (well away from the lever), the three pieces, and the Herd
        rng = random.Random(seed * 10 + 7)
        lv = self.lv_low
        lever = lv.levers[0]['pos'] if lv.levers else (0, 0, 0)
        gs = [s for s in lv.gen_spots if math.hypot(lv.center(s[0], s[1])[0] - lever[0], lv.center(s[0], s[1])[1] - lever[2]) > 14] \
            or lv.gen_spots
        if gs:
            c, r, side = rng.choice(gs)
            g = C4.SewerLevel.place_generator(lv, dict(self.c3gen), c, r, side)
            self.c3gen.update(g)
            lv.dyn_boxes = [g['box']]
        picks = pick_spread(rng, lv.item_cells, 3, 12.0, lambda s: lv.center(*s))
        for k, (c, r) in zip(C3_ITEMS, picks):
            x, z = lv.center(c, r)
            self.c3item_pos[k] = (x + rng.uniform(-0.4, 0.4), lv.y0 + 0.02, z + rng.uniform(-0.4, 0.4), rng.random() * 6)
        ex, ez = lv.rail[0], lv.rail[2]
        herd = [(c, r) for (c, r) in lv.herd_cells if lv.g[r][c] == '.'
                and math.hypot(lv.center(c, r)[0] - ex, lv.center(c, r)[1] - ez) > 7.5]
        homes = pick_spread(rng, herd, 10, 6.0, lambda s: lv.center(*s))
        self.herd3_homes = [(lv.center(c, r)[0] + rng.uniform(-0.5, 0.5), lv.center(c, r)[1] + rng.uniform(-0.5, 0.5),
                             rng.uniform(-math.pi, math.pi)) for (c, r) in homes]
        # chapter 4: three generators, and the gas can
        rng = random.Random(seed * 10 + 8)
        lv4 = self.lv4
        picks = pick_spread(rng, lv4.gen_spots, 3, 18.0, lambda s: lv4.center(s[0], s[1]))
        for gen, (c, r, side) in zip(lv4.generators, picks):
            lv4.place_generator(gen, c, r, side)
        lv4.dyn_boxes = [g['box'] for g in lv4.generators if 'box' in g]
        if lv4.jug_spots:
            c, r = rng.choice(lv4.jug_spots)
            x, z = lv4.center(c, r)
            lv4.jug = {'pos': (x + rng.uniform(-0.4, 0.4), lv4.y0, z + rng.uniform(-0.4, 0.4)), 'yaw': rng.random() * 6,
                       'taken': False}

    def reset_p2(self):
        # chapter 1
        self.plank1 = {'st': 'ground', 'by': None}
        self.world.plank_down = False
        self.bal = None
        self.falling = False
        self.shaft_seen = False
        self.gap_msg_t = 0.0
        self.death_note = None
        # chapter 3
        if hasattr(self, 'c3gen'):
            self.c3gen.update(running=False, progress=0.0)
        self.lever_broken = False
        self.c3_have = set()
        self.c3_stage = 0             # 0 nothing, 1 the charge is packed, 2 wired, 3 the detonator is down, 4 blown
        self.wire_pts = []
        self.wire_by = None
        self.det_pos = None
        self.plunge_t = -1.0
        self.herd3 = None
        self.c3_hp = 100.0
        self.c3_hurt_t = 0.0
        self.through = False
        self.gen3_noise = 0.0
        lv = getattr(self, 'lv_low', None)
        if lv is not None:
            lv.blasted = False
            for lev in lv.levers:
                lev['broken'] = False
            if hasattr(lv, 'safe0'):
                lv.safe = lv.safe0
            else:
                lv.safe0 = lv.safe
        # chapter 4
        self.jug_left = 0
        self.gas_msg_t = 0.0
        lv4 = getattr(self, 'lv4', None)
        if lv4 is not None:
            for g in lv4.generators:
                g.update(running=False, progress=0.0, fuel=False, fill=0.0)
            if lv4.jug:
                lv4.jug['taken'] = False

    def die_quiet(self, title, sub, sound='impact'):
        """Dead without a monster in your face: a fall, a blast."""
        if self.state != 'play':
            return
        if self.mp_on():
            self.message(title.capitalize() + ". " + sub, 4)
            self.respawn()
            return
        self.audio.stop_all()
        self.audio.stop_loops()
        self.audio.play(sound, 1.0)
        self.death_note = (title, sub)
        self.state = 'dead'
        self.dead_t = 0.0
        self.set_mouse(False)

    def p2_on_respawn(self):
        self.bal = None
        self.falling = False
        if self.plank1['st'] == 'carried' and self.plank1['by'] == self.my_pid():
            self.mp_act('plank1', st='ground')
        if self.c3_stage == 2 and self.wire_by == self.my_pid():
            self.mp_act('c3stage', st=1)          # the wire comes back off the charge with you
        self.c3_hp = 100.0
        if self.chapter == 3 and getattr(self, 'herd3', None) is not None and self.mp_sim() and self.c3_stage < 4:
            self.make_herd3()                       # they go back to where they stood, asleep

    # ================================================================== chapter 1: the plank
    def carrying_plank(self):
        return self.plank1['st'] == 'carried' and self.plank1['by'] == self.my_pid()

    def p2_c1_cands(self):
        out = []
        pk = self.plank1
        if pk['st'] == 'ground':
            x, y, z, yaw = self.plank1_pos
            for k in (-2.4, -1.2, 0.0, 1.2, 2.4):
                out.append(('plank1', 0, (x + math.cos(yaw) * k, y + 0.1, z - math.sin(yaw) * k)))
        w = self.world
        if self.carrying_plank() and hasattr(w, 'gap_x'):
            gx0, _ = w.gap_x
            out.append(('plankgap', 0, (gx0, W.CAT_Y + 0.2, w.cat_z)))
        return out

    def p2_interact_c1(self, kind):
        if kind == 'plank1':
            if self.plank1['st'] == 'ground':
                self.mp_act('plank1', st='carried', by=self.my_pid())
            return True
        if kind == 'plankgap':
            if self.carrying_plank():
                self.mp_act('plank1', st='down')
            return True
        return False

    def act_plank1(self, a, frm):
        st = a['st']
        pk = self.plank1
        if st == 'carried':
            if pk['st'] != 'ground':
                return
            pk.update(st='carried', by=a.get('by'))
            self.audio.play('wood_pick', 0.8 if frm is None else 0.4)
            if frm is None:
                self.message("A long plank. Heavy -- you can't run with it.", 4)
                if self.shaft_seen:
                    self.set_objective("Take the plank to the gap in the catwalk.")
            else:
                self.message("%s picked up the plank." % self.who(frm), 3)
        elif st == 'ground':
            pk.update(st='ground', by=None)
        elif st == 'down':
            pk.update(st='down', by=None)
            self.world.plank_down = True
            gx = sum(self.world.gap_x) / 2
            self.audio.play3d('wood_drop', gx, self.world.cat_z, 40, 1.0)
            self.audio.play3d('clunk', gx, self.world.cat_z, 40, 0.6)
            self.message("It reaches. Just.", 3)
            self.set_objective("Walk the plank. Slowly. [A] and [D] keep your balance.")

    def c1_speed(self, speed):
        return min(speed, 2.0) if self.carrying_plank() else speed

    def c1_shaft_move(self, p, nx, nz, dt, keys):
        """Railings along the catwalk, the gap, and the plank."""
        w = self.world
        if not hasattr(w, 'shaft_box'):
            return nx, nz
        x0, z0, x1, z1 = w.shaft_box
        if self.fly_keys_blocked():
            # flying (admin noclip / freecam): no catwalk, no plank, no falling
            if self.falling or self.bal:
                self.falling = False
                self.bal = None
                self.fade = 0.0
            return nx, nz
        if self.falling:
            return p.x, p.z
        if not (x0 - 0.4 < nx < x1 + 0.4 and z0 < nz < z1):
            self.bal = None
            return nx, nz
        if W.CAT_Y - 3.0 < p.y < W.CAT_Y - 0.7:
            self.start_fall()          # only in the shaft, and only just off the catwalk
            return p.x, p.z
        if p.y <= W.CAT_Y - 3.0:
            return nx, nz              # already down there (an admin flew you): just walk about
        zc = w.cat_z
        gx0, gx1 = w.gap_x
        if not self.shaft_seen and nx > x0 - 0.2:
            self.shaft_seen = True
            self.message("A drop shaft. Water pouring down into the dark from every side.", 4.5)
            if not w.plank_down:
                self.message("The middle of the catwalk has fallen in.", 4)
                self.set_objective("Find something to bridge the gap -- a long plank, somewhere in the sewers.")
        if gx0 - 0.05 < nx < gx1 + 0.05 and w.plank_down:
            return self.balance_step(p, nx, nz, dt, keys)
        self.bal = None
        if not w.plank_down:
            if p.x <= gx0 and nx > gx0 - 0.3:
                nx = gx0 - 0.3
                self.gap_msg_t -= dt
                if self.gap_msg_t <= 0:
                    self.gap_msg_t = 6.0
                    self.message("It's a long way down.", 2.5)
            elif p.x >= gx1 and nx < gx1 + 0.3:
                nx = gx1 + 0.3
        if x0 - 0.4 < nx < x1 + 0.4:
            nz = clamp(nz, zc - 0.4, zc + 0.4)
        return nx, nz

    def balance_step(self, p, nx, nz, dt, keys):
        b = self.bal
        w = self.world
        zc = w.cat_z
        if b is None:
            b = self.bal = {'lean': 0.0, 'v': 0.0, 'push': 0.0, 'pt': 0.0}
            if 'plank_tip' not in self.flags:
                self.flags.add('plank_tip')
                self.message("[A] and [D] -- keep your balance.", 3.5)
        ms = (1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0) - (1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0)
        rz = math.sin(p.yaw)
        b['pt'] -= dt
        if b['pt'] <= 0:
            b['pt'] = random.uniform(0.5, 1.3)
            b['push'] = random.uniform(-1.0, 1.0) * random.uniform(0.5, 1.0)
            if random.random() < 0.3:
                self.audio.play('creak', 0.35)
        step = clamp(nx - p.x, -BAL_SPEED * dt, BAL_SPEED * dt)
        moving = abs(step) > 1e-4
        b['v'] += (b['lean'] * 2.2 + b['push'] * (1.3 if moving else 0.8) + ms * rz * 3.4) * dt
        b['v'] *= max(0.0, 1.0 - 1.8 * dt)
        b['lean'] += b['v'] * dt
        if abs(b['lean']) >= 1.0:
            side = 1.0 if b['lean'] > 0 else -1.0
            self.start_fall()
            return p.x, zc + side * 0.95
        return p.x + step, zc + b['lean'] * 0.26

    def start_fall(self):
        if self.falling:
            return
        self.falling = True
        self.bal = None
        self.player.vy = 0.0
        self.audio.play('creak', 0.8)
        self.audio.play('stinger', 0.7)
        self.message("No--", 2)

    def p2_update_c1(self, dt):
        p = self.player
        if self.falling and not self.fly_keys_blocked():
            self.fade = clamp((W.CAT_Y - 4.0 - p.y) / 12.0, 0.0, 1.0)
            if p.y < W.CAT_Y - 16.0:
                self.fade = 0.0
                self.falling = False
                self.die_quiet("YOU FELL", "it was a long way down.")
        w = self.world
        if hasattr(w, 'gap_x') and w.plank_down and p.x > w.gap_x[1] + 1.0 and 'crossed' not in self.flags \
                and abs(p.z - w.cat_z) < 2:
            self.flags.add('crossed')
            self.message("Across. There's a ladder at the end of the tunnel.", 4)
            self.set_objective("Climb the ladder.")

    def view_up(self):
        b = self.bal
        if not b:
            return (0.0, 1.0, 0.0)
        p = self.player
        rx, rz = -math.cos(p.yaw), math.sin(p.yaw)
        a = 0.3 * b['lean'] * rz
        return (math.sin(a) * rx, math.cos(a), math.sin(a) * rz)

    def draw_p2_c1(self, r, cam):
        w = self.world
        pk = self.plank1
        if pk['st'] == 'ground':
            x, y, z, yaw = self.plank1_pos
            r.draw(self.m_plank1, model=T(x, y, z) @ RY(yaw))
        elif pk['st'] == 'down' and hasattr(w, 'gap_x'):
            r.draw(self.m_plank1, model=T(sum(w.gap_x) / 2, W.CAT_Y, w.cat_z))
        elif self.carrying_plank() and self.state == 'play':
            p = self.player
            M = T(*cam) @ RY(p.yaw) @ T(-0.42, -0.55, 1.5) @ RY(-math.pi / 2 - 0.08) @ RZ(0.05)
            r.draw(self.m_plank1, model=M)

    # ================================================================== chapter 3
    def make_herd3(self):
        self.herd3 = Herd3(self.lv_low, self.herd3_homes, seed=getattr(self, 'run_seed', 3))

    def lever_snapped(self, frm):
        """The cart's power lever: it comes off in your hand."""
        lv = self.lv_low
        lev = lv.levers[0]
        lev['broken'] = True
        lev['pulled'] = True
        self.lever_broken = True
        self.audio.play('snap', 1.0)
        self.audio.play('clunk', 0.6)
        if self.cart_power:
            return
        if frm is None:
            self.message("The handle snaps clean off. It was rusted through.", 4)
        else:
            self.message("%s pulled the lever -- and it snapped off." % self.who(frm), 4)
        self.message("Its cable runs off into the dark. There's a generator down here somewhere.", 5)
        self.set_objective("The lever broke. Find the generator it was meant to start.")

    def act_c3gen(self, a, frm):
        g = self.c3gen
        if g['running']:
            return
        g.update(running=True, progress=1.0)
        self.audio.play3d('gen_start', g['base'][0], g['base'][2], 50, 1.0)
        self.cart_power = True
        self.message("It coughs, and catches. Back by the rails, the minecart's motor whines.", 5)
        self.set_objective("Get in the minecart. Hold [W] to drive it through the boards.")

    def act_c3item(self, a, frm):
        k = a['k']
        if k in self.c3_have:
            return
        self.c3_have.add(k)
        self.audio.play('wood_pick', 0.7 if frm is None else 0.35)
        words = {'dynamite': "Dynamite. A bundle of it, sweating in its paper.",
                 'wire': "A spool of blasting wire.",
                 'detonator': "A detonator. A plunger box, the old kind."}[k]
        n = len(self.c3_have)
        if frm is None:
            self.message("%s (%d/3)" % (words, n), 4)
        else:
            self.message("%s found the %s. (%d/3)" % (self.who(frm), k, n), 3.5)
        if n < 3:
            self.set_objective("Find dynamite, wire and a detonator. Don't wake them. (%d/3)" % n)
        else:
            self.set_objective("Pack the dynamite into the rock at the end of the old drift.")

    def act_c3stage(self, a, frm):
        st = a['st']
        lv = self.lv_low
        bx, bz = self.charge_spot()
        if st == 1:
            self.c3_stage = 1
            self.wire_pts = []
            self.wire_by = None
            if a.get('packed'):
                self.audio.play3d('wood_drop', bx, bz, 20, 0.6)
                self.message("You pack the sticks into a crack in the rock.", 3.5)
                self.set_objective("Wire up the charge." if 'wire' in self.c3_have else "Find the wire and the detonator.")
        elif st == 2:
            self.c3_stage = 2
            self.wire_by = a.get('by')
            self.wire_pts = [(bx, bz)]
            self.audio.play3d('click', bx, bz, 20, 0.8)
            if frm is None:
                self.message("The wire's on. Now walk it back -- a long way back.", 4)
                self.set_objective("Back off at least %d m, and set the detonator down." % int(WIRE_SAFE))
        elif st == 3:
            self.c3_stage = 3
            self.det_pos = (a['x'], lv.y0, a['z'], a['yaw'])
            self.wire_pts.append((a['x'], a['z']))
            self.audio.play('clunk', 0.5)
            self.set_objective("Push the plunger.")

    def act_c3wpt(self, a, frm):
        if frm is not None and self.c3_stage == 2:
            self.wire_pts.append((a['x'], a['z']))

    def charge_spot(self):
        lv = self.lv_low
        bx, _ = lv.center(*C3.BLAST)
        return bx, lv.oz + C3.BLAST[1] * C3.C - 0.02

    def act_c3blast(self, a, frm):
        lv = self.lv_low
        if lv.blasted:
            return
        lv.blasted = True
        lv.reset_reach() if hasattr(lv, 'reset_reach') else None
        self.c3_stage = 4
        bx, bz = lv.center(*C3.BLAST)
        self.plunge_t = 0.0
        A = self.audio
        A.play('smash', 1.0)
        A.play('impact', 1.0)
        A.play('crack', 0.9)
        self.shake = max(getattr(self, 'shake', 0.0), 1.4)
        self.blast_flash = 1.0
        self.burst_debris(bx, lv.y0 + 1.2, bz - 1.5, 40, up=4.0, spread=3.5, size=(0.08, 0.6))
        p = self.player
        if self.mp_sim() and self.herd3 is not None:
            self.herd3.hear(bx, bz, 200.0)
        if self.elk is not None and self.mp_sim():
            self.elk.hear(bx, bz, 60.0)
        if self.state == 'play' and math.hypot(p.x - bx, p.z - bz) < BLAST_KILL:
            self.die_quiet("TOO CLOSE", "you were standing right next to it.", sound='smash')
            return
        self.message("The whole mountain jumps. Dust everywhere -- and a hole in the wall.", 4.5)
        self.message("And behind you, in the dark, they're waking up.", 4.5)
        self.set_objective("RUN. Through the hole.")

    def ch3_items_cands(self):
        """(kind, key, pos, reach) the Herd's caves offer."""
        out = []
        lv = self.lv_low
        if self.lv is not lv or not self.cart_done:
            return out
        for k in C3_ITEMS:
            if k not in self.c3_have:
                x, y, z, _ = self.c3item_pos[k]
                out.append(('c3item', C3_ITEMS.index(k), (x, y + 0.15, z), 2.3))
        bx, bz = self.charge_spot()
        if self.c3_stage < 2:
            out.append(('c3charge', 0, (bx, lv.y0 + 1.1, bz - 0.1), 2.4))
        if self.c3_stage == 3 and self.det_pos:
            x, y, z, _ = self.det_pos
            out.append(('c3plunge', 0, (x, y + 0.4, z), 2.2))
        return out

    def p2_focus_ch3(self):
        lv = self.lv
        p = self.player
        if lv is self.lv_low and not self.c3gen['running']:
            gx, gy, gz = self.c3gen['pos']
            ex, ey, ez = p.eye()
            f = p.fwd()
            dx, dy, dz = gx - ex, gy - ey, gz - ez
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if 1e-3 < d < 2.4 and (dx * f[0] + dy * f[1] + dz * f[2]) / d > 0.6:
                return ('c3gen', 0)
        best, bestd = None, -1
        ex, ey, ez = p.eye()
        f = p.fwd()
        for kind, key, pos, rng in self.ch3_items_cands():
            dx, dy, dz = pos[0] - ex, pos[1] - ey, pos[2] - ez
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if 1e-3 < d < rng:
                dot = (dx * f[0] + dy * f[1] + dz * f[2]) / d
                if dot > (0.55 if d < 1.3 else 0.75) and dot > bestd:
                    best, bestd = (kind, key), dot
        if best:
            return best
        if self.c3_stage == 2 and self.wire_by == self.my_pid() and 'detonator' in self.c3_have and lv is self.lv_low:
            return ('c3det', 0)
        return None

    def p2_interact_ch3(self, kind, key):
        lv = self.lv_low
        p = self.player
        if kind == 'c3item':
            self.mp_act('c3item', k=C3_ITEMS[key])
        elif kind == 'c3charge':
            if self.c3_stage == 0:
                if 'dynamite' in self.c3_have:
                    self.mp_act('c3stage', st=1, packed=True)
                else:
                    self.message("Loose, cracked rock. Something could blow through it -- with the right thing.", 3.5)
            elif self.c3_stage == 1:
                if 'wire' in self.c3_have:
                    self.mp_act('c3stage', st=2, by=self.my_pid())
                else:
                    self.message("The charge is packed. It needs a wire, and a detonator.", 3)
        elif kind == 'c3det':
            bx, bz = self.charge_spot()
            if math.hypot(p.x - bx, p.z - bz) < WIRE_SAFE:
                self.message("Too close. Further back.", 2)
                return
            self.mp_act('c3stage', st=3, x=round(p.x + math.sin(p.yaw) * 0.6, 2), z=round(p.z + math.cos(p.yaw) * 0.6, 2),
                        yaw=round(p.yaw, 2))
        elif kind == 'c3plunge':
            if self.c3_stage == 3:
                self.mp_act('c3blast')
        elif kind == 'c3gen':
            pass               # held, not pressed

    def p2_label_ch3(self, kind, key):
        p = self.player
        if kind == 'c3gen':
            return "[Hold E] Pull the starter cord", self.c3gen['progress']
        if kind == 'c3item':
            return "[E] Take the %s" % C3_ITEMS[key], 0.0
        if kind == 'c3charge':
            if self.c3_stage == 0:
                return ("[E] Pack the dynamite into the rock" if 'dynamite' in self.c3_have else "Loose rock"), 0.0
            return ("[E] Wire up the charge" if 'wire' in self.c3_have else "The charge (it needs wire)"), 0.0
        if kind == 'c3det':
            bx, bz = self.charge_spot()
            d = math.hypot(p.x - bx, p.z - bz)
            if d < WIRE_SAFE:
                return "Too close to the charge (%d m) -- back off to %d m" % (int(d), int(WIRE_SAFE)), 0.0
            return "[E] Set the detonator down here", 0.0
        if kind == 'c3plunge':
            return "[E] Push the plunger", 0.0
        return None, 0.0

    def p2_update_ch3(self, dt, keys):
        lv = self.lv
        p = self.player
        if lv is not self.lv_low:
            return
        # the generator: hold E on the cord
        g = self.c3gen
        if not g['running']:
            if self.focus == ('c3gen', 0) and keys[pygame.K_e]:
                g['progress'] += dt / 2.2
                self.gen3_noise -= dt
                if self.gen3_noise <= 0:
                    self.gen3_noise = 0.55
                    self.audio.play('creak', 0.25)
                if g['progress'] >= 1.0:
                    self.mp_act('c3gen')
            elif g['progress'] > 0:
                g['progress'] = max(0.0, g['progress'] - dt * 0.6)
        else:
            self.audio.loop3d('gen_hum', g['base'][0], g['base'][2], 24, 0.7)
        # the wire, paid out behind whoever carries it
        if self.c3_stage == 2 and self.wire_by == self.my_pid() and self.wire_pts:
            lx, lz = self.wire_pts[-1]
            if math.hypot(p.x - lx, p.z - lz) > 0.9:
                self.mp_act('c3wpt_local', x=round(p.x, 2), z=round(p.z, 2))
        # the Herd
        if self.cart_done and self.herd3 is None and self.mp_sim():
            self.make_herd3()
        if self.herd3 is not None:
            self.update_herd3(dt)
        # through the hole: the old mine
        if lv.blasted and not self.through and lv.cell_of(p.x, p.z)[1] > C3.BLAST[1]:
            self.through = True
            lv.safe = lv.center(C3.BLAST[0], C3.BLAST[1] + 3)
            self.set_objective("Keep going. Find a way out of the mine.")
        self.blast_flash = max(0.0, getattr(self, 'blast_flash', 0.0) - dt * 2.5)
        if self.plunge_t >= 0:
            self.plunge_t += dt
        # hurt: it comes back slowly
        self.c3_hurt_t = max(0.0, self.c3_hurt_t - dt)
        if self.c3_hurt_t <= 0:
            self.c3_hp = min(100.0, self.c3_hp + 6 * dt)
        self.red = max(getattr(self, 'red', 0.0) - dt * 0.8, (100 - self.c3_hp) / 160.0)

    def act_c3wpt_local(self, a, frm):
        if self.c3_stage == 2:
            self.wire_pts.append((a['x'], a['z']))

    def update_herd3(self, dt):
        h = self.herd3
        p = self.player
        lv = self.lv_low
        if self.mp_sim():
            tg = []
            others = []
            if self.local_alive() and self.state == 'play' and self.lv is lv:
                tg.append((p.x, p.z))
                others.append((p.x, p.z, p.sprinting, math.hypot(p.vx, p.vz), p.crouch))
            if self.mp_on():
                for q in self.mp.peers.values():
                    if q.alive and not self.being_killed(q.pid):
                        tg.append((q.x, q.z))
                        others.append((q.x, q.z, False, 1.0, 0.0))
            # asleep on their feet: get too close, or run near them, and they wake
            yaws = list(h.yaws)
            for i in range(h.n):
                if not h.asleep(i):
                    continue
                for (qx, qz, spr, sp, cr) in others:
                    d = math.hypot(qx - h.xs[i], qz - h.zs[i])
                    if d < 1.7 or (spr and d < 9.0) or (sp > 0.5 and cr < 0.5 and d < 3.6):
                        h.wake(i)
                        break
                    if d < 7.0:
                        want = math.atan2(qx - h.xs[i], qz - h.zs[i])
                        dy = (want - yaws[i] + math.pi) % (2 * math.pi) - math.pi
                        yaws[i] += dy * min(1.0, dt * 0.25)          # their heads follow you
            h.yaws = tuple(round(y, 3) for y in yaws)
            # one wakes, the ones nearby wake too
            for ev in list(h.events):
                if ev[0] == 'alert':
                    i = int(ev[1])
                    for j in range(h.n):
                        if h.asleep(j) and math.hypot(h.xs[j] - h.xs[i], h.zs[j] - h.zs[i]) < 8.0:
                            h.wake(j)
            h.update(dt, tg)
        h.animate(dt)
        evs = self.mp_events('herd3', h)
        h.events = []
        for ev in evs:
            kind, i = ev[0], int(ev[1])
            if i >= len(h._d['x']):
                continue
            x, z = h._d['x'][i], h._d['z'][i]
            if kind == 'hit':
                self.audio.play3d('smash', x, z, 18, 0.5)
                if self.state == 'play' and math.hypot(p.x - ev[2], p.z - ev[3]) < 1.25:
                    self.c3_hurt(55.0)
            elif kind == 'wind':
                self.audio.play3d('snort', x, z, 14, 0.5)
            elif kind == 'alert':
                self.audio.play3d('snap', x, z, 26, 0.9)
                if 'herd3_woke' not in self.flags and not self.lv_low.blasted:
                    self.flags.add('herd3_woke')
                    self.message("One of them is awake.", 3)
                if math.hypot(p.x - x, p.z - z) < 12:
                    self.glitch = max(self.glitch, 0.35)
            elif kind == 'die':
                self.audio.play3d('tackle', x, z, 30, 0.8)
                self.spawn_blood(x, lv.y0 + 1.0, z, 14, spread=2.0)
            elif kind == 'flinch':
                self.audio.play3d('snap', x, z, 20, 0.4)
        near = min((math.hypot(h._d['x'][i] - p.x, h._d['z'][i] - p.z) for i in range(h.n) if h.alive(i)
                    and h.st[i] in (H5.CHASE, H5.WIND, H5.RECOVER)), default=99.0)
        if self.elk is None:
            self.audio.loop('breath', clamp(1.0 - near / 10.0, 0.0, 0.7))

    def c3_hurt(self, amt):
        self.c3_hp -= amt
        self.c3_hurt_t = 4.0
        self.red = 1.0
        self.shake = max(getattr(self, 'shake', 0.0), 0.5)
        self.audio.play('impact', 0.8)
        if self.c3_hp <= 0:
            self.c3_hp = 100.0
            self.audio.play('screech', 0.8)
            self.die_quiet("THE HERD", "you should have let them sleep.", sound='tackle')

    def herd3_push(self, x, z):
        h = getattr(self, 'herd3', None)
        if h is None or self.lv is not self.lv_low:
            return x, z
        return h.push_out(x, z)

    def shoot_herd3(self, eye, f):
        """A shot in the Herd's caves: it wakes everything near it, and may hit one."""
        h = getattr(self, 'herd3', None)
        if h is None or self.lv is not self.lv_low:
            return False
        if self.mp_sim():
            h.hear(eye[0], eye[2], 30.0)
        else:
            self.mp_tell('hear', m='herd3', x=round(eye[0], 2), z=round(eye[2], 2), r=30.0)
        best = None
        for i in range(h.n):
            if not h.alive(i):
                continue
            for c, rad, mult in h.hit_spheres(i):
                t = ray_sphere(eye, f, c, rad)
                if t is not None and t < 60 and (best is None or t < best[0]):
                    best = (t, i, mult, c)
        if best is None:
            return False
        t, i, mult, c = best
        amt = round(9.0 * mult, 2)
        if self.mp_sim():
            h.damage(i, amt)
        else:
            self.mp_tell('herd_dmg', h='herd3', i=i, amt=amt)
        self.spawn_blood(c[0], c[1], c[2], 12, vel=(f[0] * 2, 1.5, f[2] * 2), spread=1.0)
        return True

    def herd3_parts(self):
        h = getattr(self, 'herd3', None)
        if h is None or self.lv is not self.lv_low:
            return []
        return h.parts(self.time)

    def draw_p2_c3(self, r, lv):
        if lv is not self.lv_low:
            return
        y0 = lv.y0
        g = self.c3gen
        r.draw(self.m_gen, model=T(*g['base']) @ RY(g['yaw']))
        x, y, z = g['lamp']
        r.draw(self.m_genlamp_on3 if g['running'] else self.m_genlamp_off3, model=T(x, y, z) @ S(0.07, 0.07, 0.07))
        for lev in lv.levers:
            if lev.get('broken'):
                px, py, pz = lev['pos']
                r.draw(self.m_lever, model=T(px + math.sin(lev['yaw']) * 0.5, y0 + 0.04, pz + math.cos(lev['yaw']) * 0.5)
                       @ RY(lev['yaw'] + 0.7) @ RX(math.pi / 2))
        for k in C3_ITEMS:
            if k in self.c3_have:
                continue
            x, y, z, yaw = self.c3item_pos[k]
            M = T(x, y, z) @ RY(yaw)
            if k == 'dynamite':
                r.draw(self.m_dyn, model=M)
            elif k == 'wire':
                r.draw(self.m_spool, model=M)
            else:
                r.draw(self.m_det, model=M)
                r.draw(self.m_plunger, model=M @ T(0, 0.27, 0))
        bx, bz = lv.center(*C3.BLAST)
        if not lv.blasted:
            r.draw(self.m_rockplug, model=T(bx, y0, bz))
        else:
            r.draw(self.m_rubble, model=T(bx, y0, bz))
        cx, cz = self.charge_spot()
        if 1 <= self.c3_stage <= 3:
            r.draw(self.m_dyn, model=T(cx, y0 + 0.9, cz - 0.05) @ RY(math.pi) @ RX(-0.3))
        # the wire along the floor (and up to your hand while you pay it out)
        pts = list(self.wire_pts)
        if self.c3_stage == 2 and self.wire_by == self.my_pid() and self.state == 'play':
            p = self.player
            pts.append((p.x, p.z))
        prev = None
        for i, (x, z) in enumerate(pts):
            yy = y0 + (0.9 if i == 0 else 0.03)
            if prev is not None:
                px_, py_, pz_ = prev
                dx, dy, dz = x - px_, yy - py_, z - pz_
                ln = math.sqrt(dx * dx + dy * dy + dz * dz)
                if ln > 1e-3:
                    M = T((x + px_) / 2, (yy + py_) / 2, (z + pz_) / 2) @ RY(math.atan2(dx, dz)) @ \
                        RX(-math.atan2(dy, math.hypot(dx, dz))) @ S(0.025, 0.025, ln)
                    r.draw(self.m_wire, model=M)
            prev = (x, yy, z)
        if self.det_pos:
            x, y, z, yaw = self.det_pos
            M = T(x, y, z) @ RY(yaw)
            r.draw(self.m_det, model=M)
            down = 0.0 if self.plunge_t < 0 else min(1.0, self.plunge_t / 0.15)
            r.draw(self.m_plunger, model=M @ T(0, 0.27 - 0.2 * down, 0))

    def ch3_status(self):
        if not self.cart_done:
            if self.cart_power:
                return "THE MINECART HAS POWER"
            if self.lever_broken:
                return "THE LEVER BROKE  -  FIND THE GENERATOR"
            return "FIND POWER FOR THE MINECART"
        if self.c3_stage < 4:
            return "   ".join("%s %s" % (ITEM_NAMES[k], "- got it" if k in self.c3_have else "- ?") for k in C3_ITEMS)
        return "FIND A WAY OUT" if self.through else "RUN"

    # ================================================================== chapter 4: gas
    def act_jug4(self, a, frm):
        lv = self.lv4
        if not lv.jug or lv.jug['taken']:
            return
        lv.jug['taken'] = True
        self.jug_left = 3
        self.audio.play('wood_pick', 0.7 if frm is None else 0.35)
        if frm is None:
            self.message("A can of gasoline. Enough for three of them, if you're careful.", 4)
        else:
            self.message("%s found the gas." % self.who(frm), 3)
        self.set_objective("Fill and start the three backup generators. (%d/3)" % self.gens_running())

    def act_genfuel(self, a, frm):
        gen = self.lv4.generators[a['i']]
        if gen['fuel']:
            return
        gen['fuel'] = True
        gen['fill'] = 1.0
        self.jug_left = max(0, self.jug_left - 1)
        self.audio.play3d('drain', gen['base'][0], gen['base'][2], 16, 0.5)
        if frm is None:
            self.message("Gas in. Now the cord. (%d left in the can)" % self.jug_left, 3)

    def gen_fuel_tick(self, i, gen, keys, dt):
        """Holding E on a dry generator: pour the gas in. Returns True while it's dry."""
        if gen['fuel']:
            return False
        if self.focus == ('generator', i) and keys[pygame.K_e]:
            if self.jug_left > 0:
                gen['fill'] += dt / 1.5
                if gen['fill'] >= 1.0:
                    self.mp_act('genfuel', i=i)
            else:
                self.gas_msg_t -= dt
                if self.gas_msg_t <= 0:
                    self.gas_msg_t = 4.0
                    self.message("It's bone dry. It needs gas.", 3)
                    if not (self.lv4.jug and self.lv4.jug['taken']):
                        self.set_objective("The generators are dry. Find some gas.")
        elif gen['fill'] > 0 and gen['fill'] < 1.0 and self.focus != ('generator', i):
            gen['fill'] = 0.0
        return True

    def ch4_label_gen(self, key):
        gen = self.lv4.generators[key]
        if not gen['fuel']:
            if self.jug_left > 0:
                return "[Hold E] Pour in the gas", gen['fill']
            return "Dry. It needs gas.", 0.0
        return "[Hold E] Pull the starter cord", gen['progress']

    def draw_p2_c4(self, r):
        lv = self.lv4
        for gen in lv.generators:
            if 'base' in gen:
                r.draw(self.m_gen, model=T(*gen['base']) @ RY(gen['yaw']))
        if lv.jug and not lv.jug['taken']:
            x, y, z = lv.jug['pos']
            r.draw(self.m_jug, model=T(x, y, z) @ RY(lv.jug['yaw']))

    # ================================================================== the HUD
    def draw_p2_hud(self):
        if self.chapter == 1 and self.state == 'play':
            if self.bal is not None:
                cx = self.UW // 2
                y = self.UH - 92
                w = 220
                pygame.draw.rect(self.ui, (0, 0, 0, 150), (cx - w // 2, y, w, 10))
                pygame.draw.rect(self.ui, (200, 60, 50, 200), (cx - w // 2, y, 18, 10))
                pygame.draw.rect(self.ui, (200, 60, 50, 200), (cx + w // 2 - 18, y, 18, 10))
                p = self.player
                k = clamp(self.bal['lean'] * math.sin(p.yaw), -1, 1)
                mx = int(cx + k * (w // 2 - 4))
                pygame.draw.rect(self.ui, (235, 230, 220), (mx - 3, y - 4, 6, 18))
                self.blit_text("[A]  BALANCE  [D]", self.f_small, (215, 205, 190), (cx, y + 16), 'midtop')
            elif self.carrying_plank():
                self.blit_text("CARRYING THE PLANK", self.f_small, (215, 205, 190), (26, 96))
        if self.chapter == 3 and self.state == 'play' and getattr(self, 'blast_flash', 0.0) > 0:
            s = pygame.Surface((self.UW, self.UH), pygame.SRCALPHA)
            s.fill((255, 230, 200, int(200 * self.blast_flash)))
            self.ui.blit(s, (0, 0))

    def p2_markers(self, ch):
        """For the admin overlay."""
        out = []
        if ch == 1:
            if self.plank1['st'] == 'ground':
                out.append((self.plank1_pos[:3], 'PLANK'))
        elif ch == 3 and self.lv is self.lv_low:
            if not self.c3gen['running']:
                out.append((self.c3gen['pos'], 'GENERATOR'))
            for k in C3_ITEMS:
                if k not in self.c3_have:
                    out.append((self.c3item_pos[k][:3], ITEM_NAMES[k]))
            bx, bz = self.charge_spot()
            out.append(((bx, self.lv_low.y0 + 1.2, bz), 'THE WALL'))
        elif ch == 4:
            if self.lv4.jug and not self.lv4.jug['taken']:
                out.append((self.lv4.jug['pos'], 'GAS'))
        return out
