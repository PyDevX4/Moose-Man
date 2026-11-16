"""The Moose Man: model, animation and AI.  Also small dynamic meshes (valve, herd heads)."""
import math
import random

from engine import MeshBuilder, T, S, RX, RY, RZ
from textures import L, EMIS
from world import cell_of, cell_center, ROWS, COLS, OZ


def unit_cube(layer, col=(1, 1, 1)):
    b = MeshBuilder()
    b.box((0, 0, 0), (1, 1, 1), layer, col, uvscale=1.0)
    return b.array()


def moose_meshes():
    return {
        'fur': unit_cube(L.FUR),
        'bone': unit_cube(L.BONE, (0.95, 0.92, 0.85)),
        'black': unit_cube(L.BLACK),
        'eye': unit_cube(L.GLOW + EMIS, (0.9, 0.85, 0.6)),
        'skin': unit_cube(L.SKIN, (0.35, 0.3, 0.3)),
    }


def valve_mesh():
    b = MeshBuilder()
    # stem from wall
    b.cylinder(0.05, 0.05, 0.36, 8, L.METAL, m=RX(-math.pi / 2))
    b.box((0, 0, -0.32), (0.3, 0.3, 0.06), L.METAL, (0.7, 0.7, 0.7))
    return b.array()


def wheel_mesh():
    b = MeshBuilder()
    segs = 10
    r = 0.33
    rc = (0.85, 0.25, 0.15)
    for i in range(segs):
        a = i / segs * 2 * math.pi
        m = RZ(a) @ T(0, r, 0)
        b.box((0, 0, 0), (2 * math.pi * r / segs + 0.02, 0.05, 0.05), L.METAL, rc, m=m)
    for i in range(4):
        m = RZ(i * math.pi / 4)
        b.box((0, 0, 0), (0.04, 2 * r, 0.03), L.METAL, rc, m=m)
    b.box((0, 0, 0), (0.1, 0.1, 0.1), L.METAL, (0.6, 0.6, 0.6))
    return b.array()


def herd_head_mesh():
    b = MeshBuilder()
    b.box((0, 0.13, 0), (0.2, 0.25, 0.22), L.SKIN, (0.9, 0.9, 0.9))
    b.box((-0.05, 0.16, 0.111), (0.045, 0.035, 0.01), L.BLACK)
    b.box((0.05, 0.16, 0.111), (0.045, 0.035, 0.01), L.BLACK)
    b.box((0, 0.07, 0.111), (0.07, 0.02, 0.01), L.BLACK)
    for s in (-1, 1):
        m = T(s * 0.07, 0.24, 0) @ RZ(-s * 0.45)
        b.box((0, 0.25, 0), (0.035, 0.5, 0.035), L.BARK, (0.8, 0.8, 0.8), m=m)
        m2 = m @ T(0, 0.3, 0) @ RZ(-s * 0.7)
        b.box((0, 0.13, 0), (0.025, 0.26, 0.025), L.BARK, (0.8, 0.8, 0.8), m=m2)
        m3 = m @ T(0, 0.42, 0) @ RZ(s * 0.5)
        b.box((0, 0.1, 0), (0.02, 0.2, 0.02), L.BARK, (0.8, 0.8, 0.8), m=m3)
        b.box((s * 0.02, 0.24, 0), (0.06, 0.03, 0.24), L.CLOTH, (0.5, 0.45, 0.4))
    return b.array()


def pose_moose(x, y, z, yaw, walk_phase, walk_amt, hunch=0.45, roll=0.0, head_yaw=0.0,
               head_pitch=0.0, scale=1.0, reach=0.0, jaw=0.0):
    parts = []
    add = parts.append
    M0 = T(x, y, z) @ RY(yaw) @ S(scale)
    H = 1.42
    for side in (-1, 1):
        ph = walk_phase + (0.0 if side < 0 else math.pi)
        swing = math.sin(ph) * 0.55 * walk_amt
        hip = M0 @ T(side * 0.15, H, 0) @ RX(-0.3 - swing)
        add(('fur', hip @ T(0, -0.35, 0) @ S(0.14, 0.74, 0.15)))
        knee = hip @ T(0, -0.7, 0) @ RX(0.75 + 0.4 * walk_amt * max(0.0, math.cos(ph)))
        add(('fur', knee @ T(0, -0.37, 0) @ S(0.1, 0.76, 0.1)))
        ankle = knee @ T(0, -0.74, 0) @ RX(-0.45)
        add(('black', ankle @ T(0, -0.06, 0.04) @ S(0.13, 0.14, 0.2)))
    torso = M0 @ T(0, H, 0) @ RX(hunch)
    add(('fur', torso @ T(0, 0.47, 0) @ S(0.42, 0.95, 0.26)))
    add(('fur', torso @ T(0, 0.02, 0) @ S(0.36, 0.2, 0.24)))
    for k in range(5):
        add(('bone', torso @ T(0, 0.42 + k * 0.1, 0.135) @ S(0.38 - k * 0.02, 0.025, 0.03)))
    for k in range(6):
        add(('bone', torso @ T(0, 0.15 + k * 0.15, -0.14) @ S(0.05, 0.06, 0.05)))
    for side in (-1, 1):
        ph = walk_phase + (math.pi if side < 0 else 0.0)
        aswing = math.sin(ph) * 0.25 * walk_amt
        sh = torso @ T(side * 0.27, 0.9, 0) @ RX(-hunch - aswing - reach) @ RZ(side * 0.1)
        add(('fur', sh @ T(0, -0.36, 0) @ S(0.1, 0.74, 0.1)))
        el = sh @ T(0, -0.72, 0) @ RX(-0.25 - 0.2 * walk_amt - reach * 0.3)
        add(('fur', el @ T(0, -0.4, 0) @ S(0.08, 0.8, 0.08)))
        hand = el @ T(0, -0.8, 0)
        add(('skin', hand @ T(0, -0.06, 0) @ S(0.12, 0.13, 0.05)))
        for f in (-1, 0, 1):
            fm = hand @ T(f * 0.04, -0.12, 0) @ RZ(f * 0.12) @ RX(-0.25) @ T(0, -0.17, 0)
            add(('bone', fm @ S(0.025, 0.34, 0.025)))
    neck = torso @ T(0, 0.95, 0.03) @ RX(0.55)
    add(('fur', neck @ T(0, 0.16, 0) @ S(0.13, 0.36, 0.13)))
    head = neck @ T(0, 0.32, 0) @ RX(-(hunch + 0.55) + head_pitch) @ RY(head_yaw) @ RZ(roll)
    add(('bone', head @ T(0, 0.08, 0) @ S(0.28, 0.27, 0.32)))
    add(('bone', head @ T(0, 0.0, 0.3) @ RX(0.28) @ S(0.19, 0.19, 0.5)))
    add(('black', head @ T(0, -0.06, 0.53) @ RX(0.28) @ S(0.12, 0.07, 0.06)))
    add(('bone', head @ T(0, -0.1, 0.12) @ RX(0.45 + jaw) @ T(0, 0, 0.2) @ S(0.15, 0.04, 0.4)))
    for k in range(4):
        add(('bone', head @ T(0, -0.1, 0.12) @ RX(0.45 + jaw) @ T(-0.045 + k * 0.03, 0.035, 0.25 + k * 0.02) @ S(0.015, 0.05, 0.015)))
    for side in (-1, 1):
        add(('black', head @ T(side * 0.13, 0.13, 0.1) @ S(0.07, 0.08, 0.09)))
        add(('eye', head @ T(side * 0.16, 0.13, 0.12) @ S(0.025, 0.025, 0.025)))
        base = head @ T(side * 0.12, 0.2, -0.03) @ RZ(-side * 1.1)
        add(('bone', base @ T(0, 0.22, 0) @ S(0.06, 0.44, 0.06)))
        palm = base @ T(0, 0.42, 0) @ RZ(side * 0.75)
        add(('bone', palm @ T(0, 0.31, 0) @ S(0.045, 0.62, 0.44)))
        for k in range(5):
            tm = palm @ T(0, 0.6, -0.18 + k * 0.09) @ RX(-0.35 + k * 0.17) @ T(0, 0.11, 0)
            add(('bone', tm @ S(0.03, 0.24, 0.03)))
        tm = palm @ T(0, 0.1, 0.2) @ RX(0.9) @ T(0, 0.12, 0)
        add(('bone', tm @ S(0.03, 0.25, 0.03)))
    return parts, head


class Moose:
    """AI for the thing in the sewer."""

    def __init__(self, world):
        self.w = world
        self.state = 'inactive'
        self.x = 0.0
        self.z = 0.0
        self.y = -5.0
        self.yaw = 0.0
        self.path = []
        self.timer = 0.0
        self.walk_phase = 0.0
        self.walk_amt = 0.0
        self.roll = 0.0
        self.roll_target = 0.0
        self.twitch_t = 0.0
        self.head_yaw = 0.0
        self.last_seen = None
        self.lost_t = 0.0
        self.sense_t = 0.0
        self.repath_t = 0.0
        self.grace = 0.0
        self.step_acc = 0.0
        self.speed = 0.0
        self.sees = False
        self.hunt = False
        self.events = []
        self.reach = 0.0
        self.jaw = 0.0
        self.stuck_t = 0.0
        self.prev = (0.0, 0.0)
        self.cells = None

    def place_cell(self, c, r):
        self.x, self.z = cell_center(c, r)
        self.y = self.w.floor_at(self.x, self.z) or -5.0
        self.path = []

    @property
    def active(self):
        return self.state not in ('inactive',)

    def emit(self, ev):
        self.events.append(ev)

    def path_to(self, tx, tz):
        start = cell_of(self.x, self.z)
        goal = cell_of(tx, tz)
        if not (0 <= goal[1] < ROWS and 0 <= goal[0] < COLS):
            self.path = []
            return False
        p = self.w.astar(start, goal)
        if p is None:
            self.path = []
            return False
        self.path = [cell_center(c, r) for c, r in p[1:]]
        if not self.path:
            self.path = [(tx, tz)]
        else:
            self.path[-1] = (tx, tz) if self.w.in_grid(tx, tz) else self.path[-1]
        return True

    def random_target(self, px, pz):
        if self.cells is None:
            self.cells = self.w.sewer_cells()
        if random.random() < 0.55:
            near = [c for c in self.cells if abs(cell_center(*c)[0] - px) + abs(cell_center(*c)[1] - pz) < 26]
            if near:
                return cell_center(*random.choice(near))
        return cell_center(*random.choice(self.cells))

    def hear(self, x, z, radius):
        if self.state in ('inactive', 'intro', 'chase') or self.grace > 0:
            return
        d = math.hypot(x - self.x, z - self.z)
        if d < radius:
            self.state = 'investigate'
            self.timer = 0.0
            self.path_to(x, z)

    def start_chase(self, px, pz):
        if self.state != 'chase':
            self.emit('chase_start')
        self.state = 'chase'
        self.last_seen = (px, pz)
        self.lost_t = 0.0

    def update(self, dt, player, flash_on):
        if self.state == 'inactive':
            return
        self.grace = max(0.0, self.grace - dt)
        px, pz = player.x, player.z
        dx, dz = px - self.x, pz - self.z
        dist = math.hypot(dx, dz)
        # ---- senses
        self.sense_t -= dt
        if self.sense_t <= 0:
            self.sense_t = 0.15
            self.sees = False
            if self.grace <= 0 and player.y > -9 and self.w.in_grid(px, pz) and abs(player.y - self.y) < 3.5:
                los = dist < 32 and self.w.los(self.x, self.z, px, pz)
                if los:
                    fx, fz = math.sin(self.yaw), math.cos(self.yaw)
                    cosang = (fx * dx + fz * dz) / max(dist, 1e-4)
                    vision = 22.0 if flash_on else 9.0
                    if player.crouch > 0.5:
                        vision *= 0.6
                    in_fov = cosang > 0.25 or dist < 4.0
                    beam = False
                    if flash_on and dist < 20:
                        bx, bz = -dx / dist, -dz / dist
                        beam = (player.fx * bx + player.fz * bz) > 0.93
                    if (in_fov and dist < vision) or beam or dist < 2.5:
                        self.sees = True
            if self.sees and self.state not in ('intro_leave',):
                self.start_chase(px, pz)
        # ---- states
        speed = 0.0
        target = None
        st = self.state
        if st == 'intro':
            self.yaw = self._turn(self.yaw, math.atan2(dx, dz), dt * 2)
            self.timer -= dt
            if dist < 9 and self.grace <= 0:
                self.start_chase(px, pz)
            elif self.timer <= 0:
                self.state = 'intro_leave'
                self.path_to(*cell_center(20, 30))
        elif st == 'intro_leave':
            speed = 1.7
            if not self.path:
                self.state = 'roam'
                self.timer = 1.0
        elif st == 'roam':
            speed = 1.5 if not self.hunt else 2.6
            if self.hunt:
                self.repath_t -= dt
                if self.repath_t <= 0:
                    self.repath_t = 2.5
                    self.path_to(px, pz)
            if not self.path:
                self.timer -= dt
                speed = 0.0
                if self.timer <= 0:
                    tx, tz = self.random_target(px, pz)
                    self.path_to(tx, tz)
                    self.timer = random.uniform(1.5, 4.0)
        elif st == 'investigate':
            speed = 2.5
            if not self.path:
                speed = 0.0
                self.timer += dt
                self.yaw += math.sin(self.timer * 1.7) * dt * 1.5
                if self.timer > 3.5:
                    self.state = 'roam'
                    self.timer = 1.0
        elif st == 'chase':
            speed = 4.25
            can_see = self.w.los(self.x, self.z, px, pz) and self.w.in_grid(px, pz)
            if can_see:
                self.last_seen = (px, pz)
                self.lost_t = 0.0
                target = (px, pz)
                self.path = []
            else:
                self.lost_t += dt
                self.repath_t -= dt
                if self.repath_t <= 0 or not self.path:
                    self.repath_t = 0.6
                    if self.last_seen:
                        self.path_to(*self.last_seen)
                if self.lost_t > 5.0 or (not self.path and self.lost_t > 1.0):
                    self.state = 'investigate'
                    self.timer = 0.0
                    if self.last_seen:
                        self.path_to(*self.last_seen)
            if dist < 1.05 and abs(player.y - self.y) < 2.0:
                self.emit('kill')
        # ---- movement
        if target is None and self.path:
            # skip ahead when possible
            while len(self.path) > 1 and self.w.los(self.x, self.z, *self.path[1]):
                ax, az = self.path[1]
                if math.hypot(ax - self.x, az - self.z) > 6:
                    break
                self.path.pop(0)
            target = self.path[0]
            if math.hypot(target[0] - self.x, target[1] - self.z) < 0.45:
                self.path.pop(0)
                target = self.path[0] if self.path else None
        moved = 0.0
        if target is not None and speed > 0:
            tx, tz = target
            mx, mz = tx - self.x, tz - self.z
            md = math.hypot(mx, mz)
            if md > 1e-4:
                step = min(md, speed * dt)
                nx = self.x + mx / md * step
                nz = self.z + mz / md * step
                nx, nz, _ = self.w.collide(nx, nz, 0.38, self.y, forest=False)
                moved = math.hypot(nx - self.x, nz - self.z)
                self.x, self.z = nx, nz
                self.yaw = self._turn(self.yaw, math.atan2(mx, mz), dt * (7 if st == 'chase' else 3.5))
        # stuck detection
        if speed > 0 and moved < speed * dt * 0.2:
            self.stuck_t += dt
            if self.stuck_t > 1.5:
                self.stuck_t = 0
                self.path = []
                self.repath_t = 0
                if st == 'roam':
                    self.timer = 0
        else:
            self.stuck_t = 0
        fl = self.w.floor_at(self.x, self.z)
        if fl is not None:
            self.y += (fl - self.y) * min(1.0, dt * 10)
        self.speed = moved / max(dt, 1e-4)
        self.walk_amt += (min(1.0, self.speed / 2.5) - self.walk_amt) * min(1.0, dt * 6)
        self.walk_phase += moved * 2.1
        self.step_acc += moved
        if self.step_acc > 1.25:
            self.step_acc = 0.0
            self.emit('step')
        # ---- twitchy head
        self.twitch_t -= dt
        if self.twitch_t <= 0:
            if random.random() < 0.5:
                self.roll_target = random.uniform(-0.7, 0.7)
            else:
                self.roll_target = 0.0
            self.twitch_t = random.uniform(0.15, 1.8) if st != 'chase' else random.uniform(0.05, 0.4)
        self.roll += (self.roll_target - self.roll) * min(1.0, dt * 25)
        want_reach = 0.9 if st == 'chase' and dist < 6 else 0.0
        self.reach += (want_reach - self.reach) * min(1.0, dt * 4)
        self.jaw = 0.25 + 0.2 * math.sin(self.walk_phase * 3) if st == 'chase' else 0.05

    @staticmethod
    def _turn(a, b, k):
        d = (b - a + math.pi) % (2 * math.pi) - math.pi
        return a + d * min(1.0, k)

    def ceiling_scale(self):
        c, r = cell_of(self.x, self.z)
        if 0 <= r < ROWS and 0 <= c < COLS:
            h = self.w.ceil[r, c] - self.w.floor[r, c]
            if h < 3.2:
                return max(0.72, (h - 0.15) / 2.95)
        return 1.0

    def parts(self):
        hunch = 0.45 if self.state != 'chase' else 0.75
        return pose_moose(self.x, self.y, self.z, self.yaw, self.walk_phase, self.walk_amt,
                          hunch=hunch, roll=self.roll, scale=self.ceiling_scale(), reach=self.reach, jaw=self.jaw)[0]
