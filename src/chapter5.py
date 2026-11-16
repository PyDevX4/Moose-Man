"""Chapter 5: the drain, the shotgun, the factory, and The Beast.

A narrow storm drain (a dead hunter and his shotgun halfway down) opens into
an enormous derelict factory. The Moose Man drags in the Elk and the Goat
Man, takes them into himself, and becomes The Beast: the Elk's crawling white
body, the Moose Man rising out of its hump, the Goat Man grown out of its
flank. Kill it and the great north gate opens onto daylight.

World units are metres; the floor is y = 0 everywhere.
"""
import math
import random

import numpy as np

from engine import MeshBuilder, T, S, RX, RY, RZ
from textures import L, EMIS
from elk import pose_elk
from moose import pose_moose, pose_goat

TUN_HW = 1.3            # storm drain half-width
TUN_H = 2.5
TUN_Z1 = 44.0           # where the drain opens into the factory
HALL_X = 40.0
HALL_Z0, HALL_Z1 = 44.0, 124.0
HALL_H = 30.0
GATE_HW = 8.0
GATE_H = 18.0
SHOTGUN_POS = (0.45, 0.32, 21.0)
EAST_DOOR = (HALL_X, 88.0)
BEAST_HOME = (0.0, 88.0)

# ---------------------------------------------------------------------- the beast's build
ES = 2.8                # the Elk body, scaled up
MS = 1.7                # the Moose Man on top
GS = 1.55               # the Goat Man on the flank
MOOSE_BASE = (0.0, 7.7, 4.2)
GOAT_BASE = (-2.3, 6.4, 3.0)


def lerp(a, b, k):
    return a + (b - a) * k


def lerp3(a, b, k):
    return tuple(a[i] + (b[i] - a[i]) * k for i in range(3))


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def _xf(A, parts):
    return [(key, A @ M) for key, M in parts]


def pose_beast(x, z, yaw, phase=0.0, amt=0.0, slam=0.0, throw=0.0, jaw=0.3, roar=0.0, head_pitch=0.0,
               fall=0.0, t=0.0, merge=1.0, jitter=0.0, who='emg'):
    """Returns (parts, info) where info has world-space hit spheres and head positions.

    merge 0..1 runs the cutscene: three separate bodies (the Moose Man standing,
    the Elk and the Goat Man dead on the floor) pulled together into one.
    fall 0..1 topples it onto its side when it dies.
    """
    k = merge
    rnd = random.Random(int(t * 15))
    jx = lambda s: rnd.uniform(-s, s) * jitter
    R = T(x, 0.0, z) @ RY(yaw) @ T(0, 0.9 * fall, 0) @ RZ(-fall * 1.35)
    parts = []
    # ---- the Elk: dead on its side -> the base of the thing, huge, crawling
    lift = math.sin(k * math.pi) * 2.5
    ep = lerp3((-5.5, 0.7, -3.0), (0.0, 0.0, 0.0), k)
    Ae = T(ep[0], ep[1] + lift, ep[2]) @ RY(lerp(0.5, 0.0, k) + jx(0.3)) @ RZ(lerp(math.pi / 2 * 0.95, 0.0, k) + jx(0.25)) \
        @ S(lerp(1.19, ES, k))
    eparts, ehead = pose_elk(0, 0, 0, 0, phase=phase, amt=amt * k, jaw=lerp(0.1, jaw + 0.5 * roar, k),
                             split=lerp(0.1, 0.6 + 0.4 * roar, k), head_pitch=head_pitch, t=t, scale=1.0)
    if 'e' in who:
        parts += _xf(R @ Ae, eparts)
    # ---- the Moose Man: standing -> his upper half rising out of the hump
    mp = lerp3((0.0, 0.0, 0.0), MOOSE_BASE, k)
    Am = T(mp[0], mp[1], mp[2]) @ RX(lerp(0.0, -0.15, k) + jx(0.2)) @ RZ(jx(0.2)) @ S(lerp(1.0, MS, k)) @ T(0, -1.86 * k, 0)
    mparts, mhead = pose_moose(0, 0, 0, 0, 0.0, 0.0, hunch=lerp(0.55, 0.25, k) + 0.4 * slam * (slam < 0),
                               shift=1.0, arms_up=max(0.0, slam) + 0.6 * roar, reach=0.3 * (k > 0.6),
                               jaw=0.3 + 0.8 * roar + jx(0.3), head_pitch=-0.15 * roar, roll=jx(0.5), t=t,
                               legs=k < 0.6)
    if 'm' in who:
        parts += _xf(R @ Am, mparts)
    # ---- the Goat Man: dead on his back -> grown out of the left flank
    gp = lerp3((-4.5, 0.0, 3.0), GOAT_BASE, k)
    Ag = T(gp[0], gp[1] + lift * 0.6, gp[2]) @ RY(lerp(0.9, -0.4, k)) @ RZ(lerp(0.0, 0.55, k) + jx(0.3)) \
        @ S(lerp(1.0, GS, k)) @ T(0, -1.8 * k, 0)
    gparts, ghead = pose_goat(0, 0, 0, 0, hunch=0.2, arms=throw, jaw=0.4 + 0.8 * roar + jx(0.4),
                              head_pitch=0.2 * roar, roll=jx(0.4), lie=1.0 - k, bloody=True, t=t, legs=k < 0.6)
    if 'g' in who:
        parts += _xf(R @ Ag, gparts)
    # where things are, for the shotgun and the throws
    W = lambda A, p: tuple(float(v) for v in (A @ np.array([p[0], p[1], p[2], 1.0]))[:3])
    info = {
        'heads': [W(R @ Ae @ ehead, (0, 0.1, 0.3)), W(R @ Am @ mhead, (0, 0.1, 0.1)), W(R @ Ag @ ghead, (0, 0.1, 0.1))],
        'body': [(W(R @ Ae, (0, 2.3, 0.9)), 2.9), (W(R @ Ae, (0, 2.7, 1.7)), 2.4), (W(R @ Ae, (0, 1.3, -0.4)), 2.0),
                 (W(R @ Am, (0, 2.5, 0)), 1.5), (W(R @ Ag, (0, 2.5, 0)), 1.3)],
        'goat_hand': W(R @ Ag, (-0.6, 0.6, 0.6)),
        'slam_point': W(R, (0.0, 0.0, 9.5)),
    }
    return parts, info


# ---------------------------------------------------------------------- the beast, fighting
class Beast:
    MAX_HP = 320.0

    def __init__(self, x, z, yaw):
        self.x, self.z, self.yaw = x, z, yaw
        self.hp = self.MAX_HP
        self.state = 'walk'
        self.timer = 0.0
        self.cool = 2.5
        self.phase = 0.0
        self.amt = 0.0
        self.slam = 0.0
        self.throw = 0.0
        self.roar = 0.0
        self.fall = 0.0
        self.head_pitch = 0.0
        self.charge_dir = (0.0, 1.0)
        self.step = 0.0
        self.events = []
        self.enraged = False
        self.rain_t = 8.0
        self.hurt_t = 0.0
        self.rng = random.Random()
        self.did = None

    @property
    def dead(self):
        return self.state in ('dying', 'dead')

    def damage(self, amount):
        if self.dead:
            return
        if self.state == 'stun':
            amount *= 1.6
        self.hp = max(0.0, self.hp - amount)
        self.hurt_t = 0.15
        if self.hp <= 0:
            self.state = 'dying'
            self.timer = 0.0
            self.events.append(('die',))
        elif not self.enraged and self.hp < self.MAX_HP * 0.5:
            self.enraged = True
            self.state = 'roar'
            self.timer = 0.0
            self.events.append(('enrage',))

    def _turn_to(self, a, rate, dt):
        d = (a - self.yaw + math.pi) % (2 * math.pi) - math.pi
        self.yaw += clamp(d, -rate * dt, rate * dt)
        return abs(d)

    def update(self, dt, px, pz, pvx, pvz, world):
        self.hurt_t = max(0.0, self.hurt_t - dt)
        dx, dz = px - self.x, pz - self.z
        dist = math.hypot(dx, dz)
        want = math.atan2(dx, dz)
        fast = 1.3 if self.enraged else 1.0
        st = self.state
        self.timer += dt
        speed = 0.0
        k_slam, k_throw, k_roar = 0.0, 0.0, 0.0
        if st == 'dying':
            self.fall = min(1.0, self.timer / 2.2) ** 2
            self.roar = max(0.0, 1.0 - self.timer)
            if self.timer > 2.2 and self.did != 'crash':
                self.did = 'crash'
                self.events.append(('crash',))
            if self.timer > 3.0:
                self.state = 'dead'
            self.amt *= 0.9
            return
        if st == 'dead':
            return
        if st == 'walk':
            off = self._turn_to(want, 0.9 * fast, dt)
            if dist > 8.0 and off < 1.2:
                speed = 1.5 * fast
            self.cool -= dt
            if self.enraged:
                self.rain_t -= dt
                if self.rain_t <= 0:
                    self.rain_t = self.rng.uniform(9, 13)
                    self.state, self.timer = 'roar', 0.0
            if self.cool <= 0 and self.state == 'walk':
                if dist < 11.0 and off < 0.7:
                    self.state, self.timer = 'slam', 0.0
                elif 12.0 < dist < 40.0 and off < 0.35 and self.rng.random() < (0.5 if self.enraged else 0.35):
                    self.state, self.timer = 'charge_wind', 0.0
                    self.events.append(('roar_short',))
                elif dist > 9.0:
                    self.state, self.timer = 'throw', 0.0
                else:
                    self.cool = 0.4
        elif st == 'slam':
            self._turn_to(want, 0.5, dt)
            wind = 1.35 / fast
            if self.timer < wind:
                k_slam = 2.4 * (self.timer / wind) ** 0.7
            elif self.timer < wind + 0.22:
                k_slam = 2.4 - 2.8 * (self.timer - wind) / 0.22
                if self.did != 'slam' and self.timer > wind + 0.15:
                    self.did = 'slam'
                    self.events.append(('slam',))
            elif self.timer < wind + 1.4:
                k_slam = -0.4 * (1 - (self.timer - wind - 0.22) / 1.2)
            else:
                self._done(2.0)
        elif st == 'charge_wind':
            self._turn_to(want, 1.6, dt)
            k_roar = min(1.0, self.timer * 2)
            self.head_pitch = 0.5 * min(1.0, self.timer)
            if self.timer > 1.1 / fast:
                self.state, self.timer = 'charge', 0.0
                self.charge_dir = (math.sin(self.yaw), math.cos(self.yaw))
                self.events.append(('charge',))
        elif st == 'charge':
            speed = 11.0 * fast
            self.head_pitch = 0.5
            nx, nz = self.x + self.charge_dir[0] * speed * dt, self.z + self.charge_dir[1] * speed * dt
            cx, cz = world.collide(nx, nz, 3.4, big=True)
            if math.hypot(cx - nx, cz - nz) > 0.05 or self.timer > 3.2:
                self.x, self.z = cx, cz
                if self.timer <= 3.2:
                    self.state, self.timer = 'stun', 0.0
                    self.events.append(('wall',))
                else:
                    self._done(1.5)
                self.amt = 0.0
                return
            moved = speed * dt
            self.x, self.z = nx, nz
            self.amt = 1.0
            self.phase += moved * 0.5
            self.step += moved
            if self.step > 3.2:
                self.step = 0.0
                self.events.append(('step',))
            return
        elif st == 'stun':
            self.head_pitch = 0.9 * (1 - self.timer / 3.0)
            k_roar = 0.4
            if self.timer > 3.0:
                self.head_pitch = 0.0
                self._done(1.0)
        elif st == 'throw':
            self._turn_to(want, 1.2, dt)
            if self.timer < 0.8:
                k_throw = 1.6 * self.timer / 0.8
            elif self.timer < 1.0:
                k_throw = 1.6 - 2.4 * (self.timer - 0.8) / 0.2
                if self.did != 'throw':
                    self.did = 'throw'
                    self.events.append(('throw',))
            elif self.timer < 1.6:
                k_throw = -0.8 * (1 - (self.timer - 1.0) / 0.6)
            else:
                if self.enraged and self.did == 'throw' and self.rng.random() < 0.5:
                    self.timer, self.did = 0.0, 'throw2'       # and again
                else:
                    self._done(1.6)
        elif st == 'roar':
            k_roar = min(1.0, self.timer * 2.5) * (1 - clamp((self.timer - 1.8) / 0.4, 0, 1))
            if self.did != 'roar':
                self.did = 'roar'
                self.events.append(('roar',))
            if self.timer > 2.2:
                self._done(1.0)
        # ease the animated values
        a = min(1.0, dt * 14)
        self.slam += (k_slam - self.slam) * a
        self.throw += (k_throw - self.throw) * a
        self.roar += (k_roar - self.roar) * min(1.0, dt * 8)
        if self.state != 'charge_wind' and self.state != 'stun' and self.state != 'charge':
            self.head_pitch *= max(0.0, 1 - dt * 3)
        if speed > 0:
            fx, fz = math.sin(self.yaw), math.cos(self.yaw)
            nx, nz = world.collide(self.x + fx * speed * dt, self.z + fz * speed * dt, 3.4, big=True)
            moved = math.hypot(nx - self.x, nz - self.z)
            self.x, self.z = nx, nz
        else:
            moved = 0.0
        self.amt += (min(1.0, moved / max(dt, 1e-4) / 1.5) - self.amt) * min(1.0, dt * 4)
        self.phase += moved * 0.55
        self.step += moved
        if self.step > 2.6:
            self.step = 0.0
            self.events.append(('step',))

    def _done(self, cool):
        self.state = 'walk'
        self.timer = 0.0
        self.did = None
        self.cool = cool / (1.35 if self.enraged else 1.0)

    def parts(self, t, extra_jit=0.0):
        return pose_beast(self.x, self.z, self.yaw, self.phase, self.amt, slam=self.slam, throw=self.throw,
                          jaw=0.35 + (0.4 if self.state in ('charge', 'charge_wind') else 0.0), roar=self.roar,
                          head_pitch=self.head_pitch, fall=self.fall, t=t, jitter=extra_jit + (0.15 if self.hurt_t > 0 else 0.0))


# ---------------------------------------------------------------------- the world
class World5:
    def __init__(self):
        self.lights = []          # (pos, rad, col, kind)
        self.circles = []         # (x, z, r) solid round things: boilers, columns
        self.boxes = []           # (x0, z0, x1, z1)
        self.gate_open = 0.0
        self.sealed = False       # the grate behind you, once it has seen you

    # ---- collision
    def collide(self, x, z, rad, big=False):
        for _ in range(2):
            if z < TUN_Z1 and not self.sealed and not big:
                x = clamp(x, -TUN_HW + rad, TUN_HW - rad)
                z = max(z, 0.6 + rad)
            else:
                if z < HALL_Z0 + rad:
                    if self.sealed or big or abs(x) > TUN_HW - rad:
                        z = HALL_Z0 + rad
                if z >= HALL_Z0 + rad - 0.001:
                    x = clamp(x, -HALL_X + rad, HALL_X - rad)
                gate_through = self.gate_open > 0.75 and abs(x) < GATE_HW - rad and not big
                if not gate_through:
                    z = min(z, HALL_Z1 - rad)
                elif z > HALL_Z1 - rad:
                    x = clamp(x, -GATE_HW + rad, GATE_HW - rad)
            for cx, cz, r in self.circles:
                dx, dz = x - cx, z - cz
                d = math.hypot(dx, dz)
                if d < r + rad and d > 1e-6:
                    x = cx + dx / d * (r + rad)
                    z = cz + dz / d * (r + rad)
            for x0, z0, x1, z1 in self.boxes:
                nx, nz = clamp(x, x0, x1), clamp(z, z0, z1)
                dx, dz = x - nx, z - nz
                d2 = dx * dx + dz * dz
                if d2 < rad * rad:
                    if d2 > 1e-10:
                        d = math.sqrt(d2)
                        x += dx / d * (rad - d)
                        z += dz / d * (rad - d)
                    else:
                        opts = [(x - x0, -1, 0), (x1 - x, 1, 0), (z - z0, 0, -1), (z1 - z, 0, 1)]
                        dm, sx, sz = min(opts)
                        x += sx * (dm + rad)
                        z += sz * (dm + rad)
        return x, z

    def in_tunnel(self, z):
        return z < TUN_Z1

    # ---- geometry
    def build(self):
        b = MeshBuilder()
        rng = random.Random(505)
        self._tunnel(b, rng)
        self._hall(b, rng)
        self._outside(b, rng)
        return b.array()

    def _tunnel(self, b, rng):
        hw, h = TUN_HW, TUN_H
        z0, z1 = 0.0, TUN_Z1
        conc = (0.62, 0.62, 0.6)
        b.quad_world((-hw, 0, z0), (hw, 0, z0), (hw, 0, z1), (-hw, 0, z1), L.MUD, (0.75, 0.73, 0.7), 0.5)
        b.quad_world((-0.35, 0.012, z0), (0.35, 0.012, z0), (0.35, 0.012, z1), (-0.35, 0.012, z1), L.WATER, (0.6, 0.62, 0.55), 0.5)
        b.quad_world((-hw, h, z0), (hw, h, z0), (hw, h, z1), (-hw, h, z1), L.CONCRETE, (0.45, 0.45, 0.44), 0.5)
        for sx in (-hw, hw):
            b.quad_world((sx, 0, z0), (sx, 0, z1), (sx, h, z1), (sx, h, z0), L.CONCRETE, conc, 0.5, axis='x')
        # bevelled corners so it reads as a pipe, and ring joints every 2.5 m
        for sx in (-1, 1):
            b.box((sx * (hw - 0.2), h - 0.2, (z0 + z1) / 2), (0.5, 0.5, z1 - z0), L.CONCRETE, (0.5, 0.5, 0.48), m=None)
            b.box((sx * (hw - 0.15), 0.15, (z0 + z1) / 2), (0.35, 0.3, z1 - z0), L.CONCRETE, (0.55, 0.55, 0.52))
        for k in range(int((z1 - z0) / 2.5)):
            z = z0 + 1.0 + k * 2.5
            for sx in (-1, 1):
                b.box((sx * (hw - 0.05), h / 2, z), (0.12, h, 0.25), L.CONCRETE, (0.48, 0.48, 0.46))
            b.box((0, h - 0.05, z), (hw * 2, 0.12, 0.25), L.CONCRETE, (0.48, 0.48, 0.46))
        # the back end: a rusted grate, nothing but black behind it
        b.facing_quad((0, h / 2, z0 + 0.02), (0, 0, 1), hw * 2, h, L.GRATE, (0.5, 0.45, 0.4))
        # the hunter who got this far: orange vest, skull, his pack
        hx, hz = SHOTGUN_POS[0] - 0.1, SHOTGUN_POS[2] + 0.3
        b.box((hx - 0.2, 0.18, hz), (0.5, 0.3, 0.75), L.REDCLOTH, (1.1, 0.55, 0.2))          # vest on the ribs
        b.box((hx - 0.2, 0.12, hz + 0.6), (0.45, 0.2, 0.5), L.CLOTH, (0.35, 0.35, 0.3))       # legs
        b.box((hx - 0.2, 0.12, hz + 1.1), (0.4, 0.18, 0.45), L.CLOTH, (0.3, 0.3, 0.28))
        b.box((hx - 0.25, 0.15, hz - 0.55), (0.24, 0.24, 0.27), L.BONE, (0.85, 0.8, 0.7))     # skull
        b.box((hx - 0.25, 0.1, hz - 0.43), (0.14, 0.08, 0.06), L.BLACK)
        b.box((hx - 0.85, 0.25, hz - 0.1), (0.4, 0.5, 0.6), L.CLOTH, (0.3, 0.38, 0.25))       # pack
        for k in range(6):
            b.box((hx - 0.2, 0.33, hz - 0.2 + k * 0.08), (0.42, 0.025, 0.03), L.BONE, (0.8, 0.75, 0.65))
        b.quad((hx - 0.9, 0.013, hz - 0.8), (hx + 0.5, 0.013, hz - 0.8), (hx + 0.5, 0.013, hz + 1.4), (hx - 0.9, 0.013, hz + 1.4),
               L.BLOOD, (0.45, 0.4, 0.4), uvs=((0, 0), (1, 0), (1, 1), (0, 1)))
        # a few red lamps someone strung down here
        for z in (8.0, 30.0, 41.0):
            b.box((0.9, h - 0.25, z), (0.12, 0.12, 0.12), L.GLOW + EMIS, (0.9, 0.12, 0.05))
            self.lights.append(((0.9, h - 0.4, z), 5.5, (0.7, 0.08, 0.04), 'tunnel'))

    def _hall(self, b, rng):
        X, Z0, Z1, H = HALL_X, HALL_Z0, HALL_Z1, HALL_H
        brick = (0.62, 0.55, 0.5)
        # floor in big stained slabs
        b.quad_world((-X, 0, Z0), (X, 0, Z0), (X, 0, Z1), (-X, 0, Z1), L.CONCRETE, (0.5, 0.48, 0.45), 0.25)
        for _ in range(40):
            x, z = rng.uniform(-X + 3, X - 3), rng.uniform(Z0 + 3, Z1 - 3)
            s = rng.uniform(1.5, 5.0)
            b.quad((x - s, 0.01, z - s), (x + s, 0.01, z - s), (x + s, 0.01, z + s), (x - s, 0.01, z + s),
                   L.MUD, (0.35, 0.3, 0.25), uvs=((0, 0), (1, 0), (1, 1), (0, 1)))
        b.quad_world((-X, H, Z0), (X, H, Z0), (X, H, Z1), (-X, H, Z1), L.METAL, (0.25, 0.24, 0.23), 0.12)
        # walls: south (with the drain mouth), north (with the gate), east (with the door), west
        def wall_z(z, x0, x1, holes, nz):
            pts = [x0] + sum(([a, b_] for a, b_, _ in holes), []) + [x1]
            for i in range(0, len(pts), 2):
                if pts[i + 1] > pts[i]:
                    b.quad_world((pts[i], 0, z), (pts[i + 1], 0, z), (pts[i + 1], H, z), (pts[i], H, z), L.BRICK, brick, 0.25)
            for a, b_, hh in holes:
                b.quad_world((a, hh, z), (b_, hh, z), (b_, H, z), (a, H, z), L.BRICK, brick, 0.25)
        wall_z(Z0, -X, X, [(-TUN_HW, TUN_HW, TUN_H)], 1)
        wall_z(Z1, -X, X, [(-GATE_HW, GATE_HW, GATE_H)], -1)
        dz0, dz1 = EAST_DOOR[1] - 4.0, EAST_DOOR[1] + 4.0
        for zz0, zz1 in ((Z0, dz0), (dz1, Z1)):
            b.quad_world((X, 0, zz0), (X, 0, zz1), (X, H, zz1), (X, H, zz0), L.BRICK, brick, 0.25, axis='x')
        b.quad_world((X, 9.0, dz0), (X, 9.0, dz1), (X, H, dz1), (X, H, dz0), L.BRICK, brick, 0.25, axis='x')
        b.box((X + 3.0, 4.5, EAST_DOOR[1]), (6.0, 9.0, 8.0), L.BLACK)                 # nothing but dark past the door
        b.quad_world((-X, 0, Z0), (-X, 0, Z1), (-X, H, Z1), (-X, H, Z0), L.BRICK, brick, 0.25, axis='x')
        # the drain mouth's frame, and the gate's
        for sx in (-1, 1):
            b.box((sx * (GATE_HW + 0.6), GATE_H / 2, Z1 - 0.4), (1.2, GATE_H, 1.6), L.METAL, (0.4, 0.34, 0.3))
            for k in range(6):
                b.box((sx * (GATE_HW + 0.6), 0.6 + k * 1.2, Z1 - 0.4), (1.25, 0.55, 1.65), L.METAL, (0.85, 0.68, 0.12))
        b.box((0, GATE_H + 0.7, Z1 - 0.4), (GATE_HW * 2 + 2.4, 1.4, 1.6), L.METAL, (0.4, 0.34, 0.3))
        b.facing_quad((0, GATE_H + 2.6, Z1 - 0.05), (0, 0, -1), 9.0, 1.6, L.SIGN, (0.9, 0.8, 0.6))
        b.box((0, TUN_H + 0.3, Z0 + 0.2), (TUN_HW * 2 + 0.8, 0.6, 0.5), L.METAL, (0.35, 0.32, 0.3))
        # steel columns and roof trusses
        for x in (-24.0, 24.0):
            for z in (64.0, 84.0, 104.0):
                b.box((x, H / 2, z), (1.2, H, 1.2), L.METAL, (0.38, 0.35, 0.32))
                b.box((x, 0.4, z), (2.0, 0.8, 2.0), L.CONCRETE, (0.5, 0.48, 0.45))
                self.circles.append((x, z, 1.0))
        for z in range(52, 124, 12):
            b.box((0, H - 1.0, float(z)), (2 * X, 1.2, 0.6), L.METAL, (0.3, 0.28, 0.26))
            for k in range(-3, 4):
                b.box((k * 11.0, H - 2.5, float(z)), (0.3, 2.5, 0.4), L.METAL, (0.3, 0.28, 0.26), m=None)
        # boilers in the corners
        for x, z in ((-32.0, 56.0), (32.0, 56.0), (-32.0, 112.0), (32.0, 112.0)):
            b.cylinder(4.0, 4.0, 15.0, 16, L.METAL, (0.42, 0.36, 0.3), m=T(x, 0, z), cap=True)
            for k in range(5):
                b.cylinder(4.1, 4.1, 0.25, 16, L.METAL, (0.3, 0.27, 0.24), m=T(x, 1.0 + k * 3.2, z))
            b.cylinder(0.6, 0.6, 15.0, 8, L.METAL, (0.33, 0.3, 0.27), m=T(x, 15.0, z))
            # a furnace door glowing at the bottom
            nx = 1.0 if x < 0 else -1.0
            b.facing_quad((x + nx * 4.02, 1.4, z), (nx, 0, 0), 1.6, 1.3, L.GLOW + EMIS, (1.0, 0.3, 0.05))
            self.lights.append(((x + nx * 5.2, 1.6, z), 11.0, (1.2, 0.35, 0.08), 'fire'))
            self.circles.append((x, z, 4.2))
        # machinery: presses, a conveyor, vats of something hot
        for (x, z, w, d, h) in ((16.0, 70.0, 6.0, 4.0, 7.0), (-16.0, 74.0, 5.0, 5.0, 5.0), (-28.0, 88.0, 4.0, 9.0, 3.5),
                                (30.0, 96.0, 5.0, 4.0, 6.0)):
            b.box((x, h / 2, z), (w, h, d), L.METAL, (0.4, 0.38, 0.33))
            b.box((x, h + 0.3, z), (w * 0.6, 0.6, d * 0.6), L.METAL, (0.5, 0.42, 0.2))
            b.box((x, 1.0, z + d / 2 + 0.02), (w * 0.8, 0.25, 0.04), L.METAL, (0.85, 0.68, 0.12))
            self.boxes.append((x - w / 2, z - d / 2, x + w / 2, z + d / 2))
        b.box((-13.0, 0.6, 102.0), (16.0, 1.2, 2.2), L.METAL, (0.35, 0.33, 0.3))         # conveyor
        for k in range(16):
            b.cylinder(0.12, 0.12, 2.2, 6, L.METAL, (0.5, 0.5, 0.5), m=T(-20.5 + k, 1.2, 101.0) @ RX(math.pi / 2))
        self.boxes.append((-21.0, 100.9, -5.0, 103.1))
        for x in (-12.0, 12.0):
            b.cylinder(2.6, 2.6, 3.0, 14, L.METAL, (0.35, 0.3, 0.27), m=T(x, 0, 116.0))
            b.cylinder(2.3, 2.3, 0.05, 14, L.GLOW + EMIS, (1.0, 0.35, 0.06), m=T(x, 2.92, 116.0))
            self.lights.append(((x, 4.0, 116.0), 10.0, (1.1, 0.35, 0.08), 'fire'))
            self.circles.append((x, 116.0, 2.8))
        # catwalks along the walls, with chains and hooks hanging from the roof
        for sx in (-1, 1):
            x = sx * (X - 1.6)
            b.box((x, 10.0, (Z0 + Z1) / 2), (3.2, 0.2, Z1 - Z0 - 2), L.GRATE, (0.6, 0.6, 0.6))
            b.box((x - sx * 1.55, 11.0, (Z0 + Z1) / 2), (0.08, 0.08, Z1 - Z0 - 2), L.METAL, (0.5, 0.45, 0.2))
            for z in range(48, 124, 6):
                b.box((x - sx * 1.55, 10.5, float(z)), (0.08, 1.0, 0.08), L.METAL, (0.5, 0.45, 0.2))
        for _ in range(22):
            x, z = rng.uniform(-30, 30), rng.uniform(52, 118)
            ln = rng.uniform(6, 20)
            b.box((x, H - ln / 2, z), (0.08, ln, 0.08), L.METAL, (0.45, 0.42, 0.4))
            if rng.random() < 0.45:
                # something skinned on the hook
                b.box((x, H - ln - 0.9, z), (0.45, 1.6, 0.35), L.SKIN, (0.45, 0.06, 0.05))
                b.box((x, H - ln - 1.9, z), (0.25, 0.6, 0.2), L.BONE, (0.75, 0.7, 0.6))
        # bones everywhere it has eaten
        for _ in range(140):
            x, z = rng.uniform(-30, 30), rng.uniform(60, 116)
            m = T(x, 0.04, z) @ RY(rng.random() * 6)
            b.box((0, 0, 0), (rng.uniform(0.2, 0.7), 0.06, 0.06), L.BONE, (0.85, 0.8, 0.72), m=m)
        # the herd: skulls nailed up along the south wall
        for k in range(14):
            x = -30 + k * 4.6
            if abs(x) < 3:
                continue
            b.box((x, 6.0 + (k % 3) * 1.4, Z0 + 0.2), (0.5, 0.45, 0.4), L.BONE, (0.8, 0.75, 0.65))
        # high lamps
        for x in (-26.0, 0.0, 26.0):
            for z in (58.0, 82.0, 106.0):
                b.box((x, 21.5, z), (0.03, 7.0, 0.03), L.BLACK)
                b.box((x, 18.0, z), (1.2, 0.3, 1.2), L.METAL, (0.3, 0.3, 0.3))
                b.box((x, 17.8, z), (0.7, 0.12, 0.7), L.GLOW + EMIS, (1.0, 0.65, 0.3))
                self.lights.append(((x, 15.5, z), 46.0, (1.35, 0.85, 0.42), 'lamp'))
        for x in (-6.0, 6.0):
            self.lights.append(((x, 6.0, Z1 - 2.0), 9.0, (0.9, 0.06, 0.03), 'red'))
            b.box((x, 6.6, Z1 - 0.3), (0.3, 0.3, 0.3), L.GLOW + EMIS, (1.0, 0.1, 0.05))

    def _outside(self, b, rng):
        """Past the gate: a slope of snow, pines, and the dawn."""
        z0 = HALL_Z1
        xs = np.arange(-40, 40.01, 2.0)
        zs = np.arange(z0, z0 + 70.01, 2.0)
        Xg, Zg = np.meshgrid(xs, zs)
        Hh = 0.02 + np.clip((Zg - z0 - 4) * 0.12, 0, 6) + 0.3 * np.sin(Xg * 0.3) * np.cos(Zg * 0.2) * (Zg > z0 + 6)
        V = np.zeros(Hh.shape + (12,), np.float32)
        V[..., 0], V[..., 1], V[..., 2] = Xg, Hh, Zg
        V[..., 4] = 1.0
        V[..., 6], V[..., 7] = Xg * 0.3, Zg * 0.3
        V[..., 8:11] = (1.9, 1.95, 2.1)
        V[..., 11] = L.CONCRETE
        nz, nx = Hh.shape
        j, i = np.mgrid[0:nz - 1, 0:nx - 1]
        tris = np.stack([V[j, i], V[j, i + 1], V[j + 1, i + 1], V[j, i], V[j + 1, i + 1], V[j + 1, i]], axis=2)
        b.add_array(tris.reshape(-1, 12))
        for _ in range(70):
            x = rng.uniform(-40, 40)
            z = rng.uniform(z0 + 12, z0 + 68)
            if abs(x) < 6 and z < z0 + 40:
                continue
            g = float(np.clip((z - z0 - 4) * 0.12, 0, 6))
            ht = rng.uniform(9, 15)
            b.cylinder(0.3, 0.1, ht, 6, L.BARK, (0.6, 0.6, 0.6), m=T(x, g - 0.2, z))
            for k in range(3):
                y = ht * (0.32 + 0.22 * k)
                rad = (2.6 - 0.7 * k) * rng.uniform(0.85, 1.1)
                b.cylinder(rad, 0.0, 3.4 - 0.5 * k, 7, L.NEEDLES, (0.9, 0.95, 0.95), m=T(x, g + y, z))
        # the sky: pale, after the longest night
        b.facing_quad((0, 30, z0 + 72), (0, 0, -1), 200, 70, L.GLOW + EMIS, (0.55, 0.52, 0.55))
        b.facing_quad((0, 8, z0 + 71.5), (0, 0, -1), 200, 14, L.GLOW + EMIS, (0.95, 0.62, 0.42))


# ---------------------------------------------------------------------- small meshes
def shotgun_mesh():
    """Pump shotgun, pointing down +z. Origin at the grip."""
    b = MeshBuilder()
    dark = (0.22, 0.22, 0.24)
    wood = (0.55, 0.35, 0.2)
    b.box((0, 0.0, 0.12), (0.06, 0.08, 0.32), L.METAL, dark)                  # receiver
    b.cylinder(0.018, 0.018, 0.62, 8, L.METAL, dark, m=T(0, 0.025, 0.25) @ RX(math.pi / 2))      # barrel
    b.cylinder(0.016, 0.016, 0.5, 8, L.METAL, dark, m=T(0, -0.012, 0.25) @ RX(math.pi / 2))      # magazine tube
    b.box((0, 0.045, 0.86), (0.012, 0.02, 0.012), L.METAL, (0.7, 0.7, 0.7))   # bead sight
    b.box((0, -0.05, -0.06), (0.04, 0.1, 0.06), L.WOOD, wood)                 # grip
    b.box((0, -0.04, -0.25), (0.05, 0.1, 0.34), L.WOOD, wood, m=RX(-0.12))    # stock
    return b.array()


def pump_mesh():
    b = MeshBuilder()
    b.box((0, -0.012, 0), (0.05, 0.05, 0.2), L.WOOD, (0.5, 0.32, 0.18))
    for k in range(5):
        b.box((0, -0.012, -0.08 + k * 0.04), (0.054, 0.054, 0.012), L.WOOD, (0.35, 0.22, 0.12))
    return b.array()


def flash_mesh():
    b = MeshBuilder()
    for a in range(3):
        b.box((0, 0, 0.12), (0.06, 0.06, 0.26), L.GLOW + EMIS, (1.6, 1.0, 0.4), m=RZ(a * 1.05) @ RX(0.0))
        b.box((0, 0, 0.06), (0.18, 0.02, 0.1), L.GLOW + EMIS, (1.4, 0.8, 0.3), m=RZ(a * 1.05))
    return b.array()


def marker_mesh():
    b = MeshBuilder()
    b.quad((-1, 0.03, -1), (1, 0.03, -1), (1, 0.03, 1), (-1, 0.03, 1), L.GLOW + EMIS, (0.9, 0.08, 0.04),
           uvs=((0, 0), (1, 0), (1, 1), (0, 1)))
    return b.array()


def shell_box_mesh():
    b = MeshBuilder()
    b.box((0, 0.06, 0), (0.22, 0.12, 0.14), L.SIGN, (0.8, 0.2, 0.12))
    return b.array()


def ray_sphere(o, d, c, r):
    """Distance along unit ray o + t*d to the sphere, or None."""
    ox, oy, oz = o[0] - c[0], o[1] - c[1], o[2] - c[2]
    bq = ox * d[0] + oy * d[1] + oz * d[2]
    cq = ox * ox + oy * oy + oz * oz - r * r
    disc = bq * bq - cq
    if disc < 0:
        return None
    t = -bq - math.sqrt(disc)
    if t < 0:
        t = -bq + math.sqrt(disc)
    return t if t >= 0 else None
