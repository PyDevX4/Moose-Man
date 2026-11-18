"""The end of the game, and the very start of it. Mixed into game.Game.

  * drive0  - the opening: your truck on Route 9, then up the logging track to the trailhead,
              engine off, out of the cab. Then Chapter One starts where you're standing.
  * run6    - out of the factory gate (after exit5): running through the Chapter Two woods at
              dawn. You look back -- nothing. You look forward -- the Herd, and the one with the
              shotgun on you. JOIN THEM or FIGHT.
  * join6   - the BAD ENDING: he lowers the gun and knocks you out; you wake up in the herd
              room under the forest; two antlers go into your head and you become one of them.
  * fight   - state 'play', chapter 5, c5_phase 'finale': the Herdsman (mini boss, health bar)
              and the rest of the Herd, in the snow. Kill him.
  * truck6  - the GOOD ENDING: back down the trail to the truck, it starts on the second try,
              and you back out of Hollins Woods.
"""
import math
import random

import pygame

from engine import Mesh, T, S, RX, RY, RZ
import chapter2 as C2
import world as W
import herd5 as H5
import truck as TR
import lore


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def sm(t, a, b):
    k = clamp((t - a) / (b - a), 0, 1)
    return k * k * (3 - 2 * k)


def look(cam, tgt):
    f = (tgt[0] - cam[0], tgt[1] - cam[1], tgt[2] - cam[2])
    ln = math.sqrt(sum(v * v for v in f)) or 1.0
    return tuple(v / ln for v in f)


def lerp(a, b, k):
    return a + (b - a) * k


TRUCK_POS = (0.0, -55.6)          # Chapter One: on the trail, just south of where you start (W.START)
DAWN2 = {'ambient': (0.24, 0.24, 0.27), 'mooncol': (0.55, 0.42, 0.34), 'moondir': (0.25, -0.45, -0.85),
         'fog': (0.5, 0.48, 0.52), 'fogdens': 0.024}
DAWN1 = {'ambient': (0.2, 0.2, 0.23), 'mooncol': (0.5, 0.4, 0.33), 'fog': (0.42, 0.4, 0.44), 'fogdens': 0.03}
SEWER_ROOM = (27.2, 115.0)         # Chapter One's herd room, where you wake up
LEADER_SEED = 41
SHELLS = 6
ARENA_R = 38.0


def ground2(x, z):
    return float(C2.terrain_h2(x, z))


def truck_world(tx, ty, tz, yaw, local):
    """A point on the truck (its local frame) in the world."""
    lx, ly, lz = local
    c, s = math.cos(yaw), math.sin(yaw)
    return (tx + lx * c + lz * s, ty + ly, tz - lx * s + lz * c)


def herdsman_scale():
    return 0.92 + 0.16 * random.Random(LEADER_SEED).random()


def herd_hands(x, y, z, yaw, reach, t, seed=LEADER_SEED):
    """Where a herd figure's hands are (pose_herd's arms, worked out the same way)."""
    h = 0.92 + 0.16 * random.Random(seed).random()
    B = T(x, y, z) @ RY(yaw) @ S(h, h, h)
    jerk = 0.12 * (math.sin(t * 11 + seed) > 0.93) + 0.05 * math.sin(t * 3.1 + seed)
    hunch = 0.22 + 0.25 * reach + jerk
    Tt = B @ T(0, 0.85, 0) @ RX(hunch)
    out = []
    for sx in (-1, 1):
        A = Tt @ T(sx * 0.23, 0.6, 0) @ RX(-reach * 1.45) @ RZ(sx * 0.08)
        hm = A @ T(0, -0.64, 0)
        out.append((float(hm[0, 3]), float(hm[1, 3]), float(hm[2, 3])))
    return out


def aim_at(base, tip):
    """A matrix putting an antler's base at `base`, its beam (+y) pointing at `tip`."""
    dx, dy, dz = tip[0] - base[0], tip[1] - base[1], tip[2] - base[2]
    hl = math.hypot(dx, dz)
    return T(*base) @ RY(math.atan2(dx, dz)) @ RX(math.atan2(hl, dy))


# ---------------------------------------------------------------------- the woods, for the Herd
class Arena:
    """What herd5.Herd5 needs from a world: collide() and region(), here the snow round the fight."""

    def __init__(self, w2, cx, cz, rad):
        self.w2, self.cx, self.cz, self.rad = w2, cx, cz, rad

    def collide(self, x, z, rad):
        return self.w2.collide(x, z, rad, x, z)

    def region(self, x, z):
        return 'hall' if math.hypot(x - self.cx, z - self.cz) < self.rad else 'out'


class _NoGrid:
    def cell_of(self, x, z):
        return 0, 0

    def kind(self, c, r):
        return '#'


class Herd6(H5.Herd5):
    """The Herd on the hillside: same as the factory's, but standing on uneven ground."""

    def __init__(self, arena, seed=66):
        super().__init__(None, n=0, seed=seed, world=arena)
        self.fac = _NoGrid()          # herd5 asks the factory grid for wander spots; out here there is none

    def stand(self, x, z, yaw):
        self.add(x, z)
        i = self.n - 1
        st = list(self.st)
        st[i] = H5.WANDER
        self.st = tuple(st)
        yaws = list(self.yaws)
        yaws[i] = round(yaw, 3)
        self.yaws = tuple(yaws)
        self._d['rise'][i] = 1.0
        self._d['yaw'][i] = yaw
        self._ai['t'][i] = 99.0
        self.events = []

    def wake(self):
        self.st = tuple(H5.CHASE if s != H5.DEAD else s for s in self.st)

    def parts(self, t):
        self._fit()
        d = self._d
        out = []
        for i in range(min(self.n, len(self.xs))):
            x, z = d['x'][i], d['z'][i]
            out.append(H5.pose_herd(x, z, d['yaw'][i], d['walk'][i], d['amt'][i], d['reach'][i] * (1 - d['swing'][i]),
                                    d['fall'][i], t, seed=i * 7 + 3, swing=d['swing'][i], flinch=d['flinch'][i],
                                    y=ground2(x, z)))
        return out

    def hit_spheres(self, i):
        x, z = self._d['x'][i], self._d['z'][i]
        g = ground2(x, z)
        return [((x, g + 1.72, z), 0.2, 2.0), ((x, g + 1.15, z), 0.32, 1.0), ((x, g + 0.5, z), 0.28, 0.8)]


# ---------------------------------------------------------------------- the Herdsman
class Herdsman:
    """The one with the shotgun. Keeps his distance, circles, and every few seconds levels the gun
    on you for most of a second before he fires: keep moving sideways and he misses."""
    MAX_HP = 55.0
    AIM_T = 0.85

    def __init__(self, x, z, yaw):
        self.x, self.z, self.yaw = x, z, yaw
        self.hp = self.MAX_HP
        self.state = 'stand'          # stand, move, aim, stagger, dead
        self.t = 0.0
        self.cool = 2.0
        self.strafe = 1
        self.strafe_t = 2.0
        self.aim_pt = None
        self.walk = 0.0
        self.amt = 0.0
        self.gun_up = 1.0             # 0 at the hip .. 1 levelled at you
        self.fall = 0.0
        self.hurt_t = 0.0
        self.recoil = 0.0
        self.flash_t = 0.0
        self.events = []

    @property
    def dead(self):
        return self.state == 'dead'

    def y(self):
        return ground2(self.x, self.z)

    def damage(self, amt):
        if self.dead:
            return
        self.hp = max(0.0, self.hp - amt)
        self.hurt_t = 0.15
        if self.hp <= 0:
            self.state = 'dead'
            self.t = 0.0
            self.events.append(('die',))
        elif amt >= 8.0 and self.state != 'aim':
            self.state = 'stagger'
            self.t = 0.45

    def update(self, dt, px, pz, collide):
        self.hurt_t = max(0.0, self.hurt_t - dt)
        self.recoil = max(0.0, self.recoil - dt * 3)
        self.flash_t = max(0.0, self.flash_t - dt)
        if self.dead:
            self.fall = min(1.0, self.fall + dt / 0.8)
            self.amt += (0.0 - self.amt) * min(1.0, dt * 6)
            return
        dx, dz = px - self.x, pz - self.z
        d = math.hypot(dx, dz) or 1e-3
        want = math.atan2(dx, dz)
        mx = mz = 0.0
        speed = 0.0
        if self.state == 'stagger':
            self.t -= dt
            if self.t <= 0:
                self.state = 'move'
            self.gun_up += (0.3 - self.gun_up) * min(1.0, dt * 8)
        elif self.state == 'aim':
            self.t -= dt
            ax, az = self.aim_pt
            k = min(1.0, dt * 1.6)          # he tracks you, but lags behind
            self.aim_pt = (ax + (px - ax) * k, az + (pz - az) * k)
            want = math.atan2(self.aim_pt[0] - self.x, self.aim_pt[1] - self.z)
            self.gun_up += (1.0 - self.gun_up) * min(1.0, dt * 10)
            if self.t <= 0:
                self.events.append(('fire', self.aim_pt[0], self.aim_pt[1]))
                self.state = 'move'
                self.cool = random.uniform(2.0, 3.1)
                self.recoil = 1.0
                self.flash_t = 0.08
        else:
            self.state = 'move'
            self.cool -= dt
            self.strafe_t -= dt
            if self.strafe_t <= 0:
                self.strafe = -self.strafe
                self.strafe_t = random.uniform(1.5, 3.5)
            ux, uz = dx / d, dz / d
            if d > 13.0:
                mx, mz = ux, uz
            elif d < 7.0:
                mx, mz = -ux, -uz
            else:
                mx, mz = uz * self.strafe, -ux * self.strafe
            speed = 2.1
            self.gun_up += (0.55 - self.gun_up) * min(1.0, dt * 5)
            if self.cool <= 0 and d < 30.0:
                self.state = 'aim'
                self.t = self.AIM_T
                self.aim_pt = (px, pz)
                self.events.append(('aim',))
        dy = (want - self.yaw + math.pi) % (2 * math.pi) - math.pi
        self.yaw += dy * min(1.0, dt * 7)
        moved = 0.0
        if speed > 0:
            nx, nz = collide(self.x + mx * speed * dt, self.z + mz * speed * dt)
            moved = math.hypot(nx - self.x, nz - self.z)
            self.x, self.z = nx, nz
        self.walk += moved * 4.2
        self.amt += (min(1.0, moved / max(dt, 1e-4) / 1.5) - self.amt) * min(1.0, dt * 6)

    def gun_matrix(self, t=0.0):
        """The shotgun in his hands: at the hip (gun_up 0) up to levelled at you (1); on the ground once he's down."""
        y = self.y()
        if self.dead:
            fx, fz = math.sin(self.yaw), math.cos(self.yaw)
            return T(self.x - fz * 0.7, y + 0.06, self.z + fx * 0.7) @ RY(self.yaw + 1.1) @ RZ(math.pi / 2)
        h = herdsman_scale()
        k = self.gun_up
        lift = (1.38 * k + 1.0 * (1 - k)) * h
        fwd = (0.38 * k + 0.22 * (1 - k)) * h - 0.12 * self.recoil
        side = (0.06 * k + 0.24 * (1 - k)) * h
        pitch = 0.95 * (1 - k) - 0.35 * self.recoil
        return T(self.x, y, self.z) @ RY(self.yaw) @ T(-side, lift, fwd) @ RX(pitch)

    def muzzle(self):
        M = self.gun_matrix() @ T(0, 0.025, 0.88)
        return float(M[0, 3]), float(M[1, 3]), float(M[2, 3])

    def parts(self, t):
        return H5.pose_herd(self.x, self.z, self.yaw, self.walk, self.amt, 0.3 + 0.7 * self.gun_up if not self.dead else 0.0,
                            self.fall, t, seed=LEADER_SEED, swing=0.0, flinch=1.0 if self.hurt_t > 0 else 0.0, y=self.y())

    def hit_spheres(self):
        g = self.y()
        return [((self.x, g + 1.75, self.z), 0.22, 2.0), ((self.x, g + 1.15, self.z), 0.38, 1.0),
                ((self.x, g + 0.5, self.z), 0.3, 0.8)]


# ---------------------------------------------------------------------- the mixin
class FinaleMixin:
    def init_finale(self, prog):
        self.m_truck = Mesh(self.ctx, prog, TR.body_mesh())
        self.m_truck_door = Mesh(self.ctx, prog, TR.door_mesh())
        self.m_truck_on = Mesh(self.ctx, prog, TR.lights_mesh(True))
        self.m_truck_off = Mesh(self.ctx, prog, TR.lights_mesh(False))
        self.m_antler = Mesh(self.ctx, prog, TR.antler_mesh())
        x, z = TRUCK_POS
        self.world.forest_boxes.append((x - TR.BOX[0], z - TR.BOX[1], x + TR.BOX[0], z + TR.BOX[1]))
        self.reset_truck()
        self.f6 = None

    def reset_truck(self):
        x, z = TRUCK_POS
        self.truck = {'x': x, 'z': z, 'yaw': 0.0, 'door': 0.0, 'lights': False}

    # ------------------------------------------------------------------ the truck in Chapter One
    def truck_ground(self):
        return float(W.terrain_h(self.truck['x'], self.truck['z']))

    def truck_matrix(self):
        tr = self.truck
        return T(tr['x'], self.truck_ground(), tr['z']) @ RY(tr['yaw'])

    def truck_extras(self):
        tr = self.truck
        M = self.truck_matrix()
        out = [(self.m_truck, M), (self.m_truck_on if tr['lights'] else self.m_truck_off, M),
               (self.m_truck_door, M @ T(*TR.DOOR_HINGE) @ RY(-1.15 * tr['door']))]
        return out

    def truck_lights(self):
        tr = self.truck
        if not tr['lights']:
            return []
        y0 = self.truck_ground()
        out = []
        for lx in (0.6, -0.6):
            out.append((truck_world(tr['x'], y0, tr['z'], tr['yaw'], (lx, 1.0, 4.5)), 9.0, (1.7, 1.6, 1.3)))
        out.append((truck_world(tr['x'], y0, tr['z'], tr['yaw'], (0.0, 1.2, 10.0)), 13.0, (1.2, 1.1, 0.9)))
        out.append((truck_world(tr['x'], y0, tr['z'], tr['yaw'], (0.0, 1.0, -3.2)), 3.0, (0.9, 0.05, 0.03)))
        return out

    def truck_seat(self):
        tr = self.truck
        return truck_world(tr['x'], self.truck_ground(), tr['z'], tr['yaw'], TR.SEAT_EYE)

    def draw_ch1_view(self, cam, fwd, env=None, lights=(), parts=(), extras=(), fov=None, up=(0.0, 1.0, 0.0)):
        ex = list(lights) + self.truck_lights()
        self.draw_world(cam, fwd, 0.0, cam, fwd, list(parts), fov=fov, up=up, extra_lights=ex[:8], env=env,
                        extras=list(extras))

    # ------------------------------------------------------------------ the opening drive
    def start_drive0(self):
        self.state = 'drive0'
        self.d0_t = 0.0
        self.d0_fired = set()
        self.set_mouse(False)
        self.reset_truck()
        self.truck['lights'] = True
        self.fade = 1.0

    def d0_fire(self, name, at):
        if name not in self.d0_fired and self.d0_t >= at:
            self.d0_fired.add(name)
            return True
        return False

    def update_drive0(self, dt):
        self.d0_t += dt
        t = self.d0_t
        A = self.audio
        tr = self.truck
        A.loop('forest_amb', 0.35 * sm(t, 5.0, 8.0))
        A.loop('title_amb', 0.0)
        if t < 5.2:
            if self.d0_fire('car', 0.4):
                A.play('car', 0.9, pan=0.3)
            self.fade = max(1.0 - t / 0.8, sm(t, 4.4, 5.2))
        else:
            A.loop('gen_hum', 0.22 if t < 11.6 else 0.0)
            if self.d0_fire('off', 11.6):
                A.play('clunk', 0.6)
            if self.d0_fire('lights', 12.1):
                A.play('click', 0.6)
                tr['lights'] = False
            if self.d0_fire('door', 12.4):
                A.play('door_open', 0.8)
            if self.d0_fire('shut', 15.3):
                A.play('door_close', 0.8)
            tr['door'] = sm(t, 12.4, 13.0) * (1 - sm(t, 15.3, 15.7))
            for i in range(6):
                if self.d0_fire('st%d' % i, 14.6 + i * 0.42):
                    A.play_rand('step_grass', 4, 0.4)
            self.fade = clamp(1.0 - (t - 5.2) / 0.8, 0, 1)
        for m in self.msgs:
            m[1] -= dt
        self.msgs = [m for m in self.msgs if m[1] > 0]
        if t > 17.0:
            self.end_drive0()

    def end_drive0(self):
        self.audio.loop('gen_hum', 0.0)
        self.reset_truck()
        self.fade = 0.0
        p = self.player
        x, z = W.START
        p.reset(x, float(W.terrain_h(x, z)), z, 0.0)
        self.start_play()

    def render_drive0(self):
        t = self.d0_t
        tr = self.truck
        if t < 5.2:
            # Route 9: the truck goes by in the dark
            tr['x'], tr['z'], tr['yaw'] = W.ROAD_MID - 1.7, -60.0 + 13.0 * t, 0.0
            cam = (W.ROAD_X0 - 4.0, 1.3, -18.0)
            fwd = look(cam, (tr['x'], 1.0, tr['z'] + 1.0))
            self.draw_ch1_view(cam, fwd)
        elif t < 12.2:
            # up the logging track to the trailhead, in the cab
            k = sm(t, 5.2, 11.4)
            tr['x'], tr['yaw'] = TRUCK_POS[0], 0.0
            tr['z'] = lerp(TRUCK_POS[1] - 7.4, TRUCK_POS[1], 1 - (1 - k) ** 2)
            cam = self.truck_seat()
            bump = 0.025 * math.sin(t * 9.0) * (1 - k)
            cam = (cam[0], cam[1] + bump, cam[2])
            fwd = (0.0, -0.05, 1.0)
            self.draw_ch1_view(cam, look((0, 0, 0), fwd))
        else:
            # out of the cab, and up the trail a few steps
            tr['x'], tr['z'], tr['yaw'] = TRUCK_POS[0], TRUCK_POS[1], 0.0
            seat = self.truck_seat()
            g = float(W.terrain_h(1.6, TRUCK_POS[1] + 0.3))
            out = (1.6, g + 1.62, TRUCK_POS[1] + 0.3)
            sx, sz = W.START
            end = (sx, float(W.terrain_h(sx, sz)) + 1.62, sz)
            k1 = sm(t, 13.0, 14.5)
            k2 = sm(t, 14.6, 17.0)
            cam = tuple(lerp(lerp(seat[i], out[i], k1), end[i], k2) for i in range(3))
            yaw = math.pi / 2 * sm(t, 12.2, 12.8) * (1 - sm(t, 14.3, 15.2))
            pitch = -0.1 * (1 - k2)
            cp = math.cos(pitch)
            fwd = (math.sin(yaw) * cp, math.sin(pitch), math.cos(yaw) * cp)
            # your lantern, lit once you're out of the cab
            lit = sm(t, 12.6, 13.2)
            lamp = [((cam[0] + fwd[0] * 0.4, cam[1] - 0.4, cam[2] + fwd[2] * 0.4), 10.0,
                     tuple(c * lit for c in self.lantern_col()))] if lit > 0 else []
            self.draw_ch1_view(cam, fwd, lights=lamp)
        if 6.0 < t < 10.5:
            a = int(255 * sm(t, 6.0, 7.0) * (1 - sm(t, 9.5, 10.5)))
            self.blit_text("Hollins Woods  -  11:54 PM", self.f_hud, (200, 190, 175), (self.UW // 2, self.UH - 110), 'midtop', alpha=a)

    # ------------------------------------------------------------------ out of the factory: the woods
    def find_run_line(self):
        """A straight run through the Chapter Two woods: clear of trees and water, with room ahead for the Herd."""
        w2 = self.w2
        rng = random.Random(77)
        half = C2.HALF - 30
        for _ in range(6000):
            cx, cz = rng.uniform(-half, half), rng.uniform(-half, half)
            if math.hypot(cx, cz) < 45:
                continue
            a = rng.random() * 2 * math.pi
            dx, dz = math.sin(a), math.cos(a)
            hs = []
            ok = True
            for s in range(-26, 15):
                x, z = cx + dx * s, cz + dz * s
                hgt = ground2(x, z)
                if hgt < C2.WL + 0.6 or w2.near_tree(x, z, 1.5):
                    ok = False
                    break
                hs.append(hgt)
            if not ok or max(hs) - min(hs) > 3.0:
                continue
            spots = self.herd_spots(cx, cz, a)
            if len(spots) < 7:
                continue
            return cx, cz, a
        return 0.0, 40.0, 0.0

    def herd_spots(self, ex, ez, a):
        """Where they stand, in a half ring in front of you (and him in the middle)."""
        w2 = self.w2
        out = []
        for k, ang in enumerate((-78, -58, -38, -20, 20, 38, 58, 78)):
            for rr in (7.5, 8.5, 6.6, 9.5):
                b = a + math.radians(ang)
                x, z = ex + math.sin(b) * rr, ez + math.cos(b) * rr
                if ground2(x, z) > C2.WL + 0.5 and not w2.near_tree(x, z, 0.9):
                    out.append((x, z))
                    break
        return out

    def setup_woods(self):
        ex, ez, a = self.find_run_line()
        dx, dz = math.sin(a), math.cos(a)
        f6 = {'E': (ex, ez), 'a': a, 'L': (ex + dx * 6.5, ez + dz * 6.5)}
        self.f6 = f6
        self.place_herd()

    def place_herd(self):
        f6 = self.f6
        ex, ez = f6['E']
        lx, lz = f6['L']
        f6['arena'] = Arena(self.w2, ex, ez, ARENA_R + 6)
        h = Herd6(f6['arena'])
        for (x, z) in self.herd_spots(ex, ez, f6['a']):
            h.stand(x, z, math.atan2(ex - x, ez - z))
        f6['herd'] = h
        f6['boss'] = Herdsman(lx, lz, math.atan2(ex - lx, ez - lz))
        f6['won_t'] = -1.0

    def start_run6(self):
        self.state = 'run6'
        self.r6_t = 0.0
        self.r6_fired = set()
        self.r6_choice = None          # once it's up: 0 join, 1 fight
        self.r6_sel = 1
        self.set_mouse(False)
        self.audio.stop_all()
        self.setup_woods()
        self.f6['boss'].gun_up = 0.3
        self.set_resume(5, 'finale')

    def r6_fire(self, name, at):
        if name not in self.r6_fired and self.r6_t >= at:
            self.r6_fired.add(name)
            return True
        return False

    def update_run6(self, dt):
        self.r6_t += dt
        t = self.r6_t
        A = self.audio
        f6 = self.f6
        A.loop('winter_amb', 0.55)
        A.loop('breath', 0.55 if t < 4.0 else 0.75)
        for k_ in ('forest_amb', 'title_amb', 'sewer_amb', 'gen_hum', 'creak'):
            A.loop(k_, 0.0)
        for i in range(12):
            if self.r6_fire('st%d' % i, 0.2 + i * 0.36) and t < 4.6:
                A.play_rand('step_snow', 4, 0.7)
        if self.r6_fire('stinger', 4.15):
            A.play('stinger', 0.9)
            A.play('snap', 0.7)
            self.glitch = 1.0
        if self.r6_fire('heart', 4.6):
            A.play('heart', 0.8)
        if self.r6_fire('pump', 5.5):
            A.play('bolt', 0.9)
        boss = f6['boss']
        boss.gun_up = 0.3 + 0.7 * sm(t, 4.6, 5.4)
        f6['herd'].animate(dt)
        self.glitch += (0.0 - self.glitch) * min(1.0, dt * 6)
        self.fade = clamp(1.0 - t / 0.9, 0, 1)
        if t > 6.2 and self.r6_choice is None:
            self.r6_choice = True
            self.set_mouse(False)

    def choice_rects(self):
        cx, y = self.UW // 2, self.UH - 150
        return [pygame.Rect(cx - 250, y, 220, 56), pygame.Rect(cx + 30, y, 220, 56)]

    def run6_event(self, ev):
        if not self.r6_choice:
            return
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_1, pygame.K_j):
                self.choose6(0)
            elif ev.key in (pygame.K_2, pygame.K_f):
                self.choose6(1)
            elif ev.key in (pygame.K_LEFT, pygame.K_a):
                self.r6_sel = 0
            elif ev.key in (pygame.K_RIGHT, pygame.K_d):
                self.r6_sel = 1
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_e):
                self.choose6(self.r6_sel)
        elif ev.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            ux, uy = self.ui_mouse()
            for i, rc in enumerate(self.choice_rects()):
                if rc.collidepoint(ux, uy):
                    self.r6_sel = i
                    if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                        self.choose6(i)

    def choose6(self, i):
        self.audio.play('click', 0.6)
        if i == 0:
            self.start_join6()
        else:
            self.start_fight6()

    def r6_camera(self):
        t = self.r6_t
        f6 = self.f6
        ex, ez = f6['E']
        a = f6['a']
        dx, dz = math.sin(a), math.cos(a)
        if t < 4.4:
            s = -22.0 + 4.6 * t
        else:
            u = min(t - 4.4, 0.8)
            s = -1.76 + 4.6 * u - 0.5 * 5.75 * u * u
        s = min(s, 0.0)
        x, z = ex + dx * s, ez + dz * s
        run = 1.0 - sm(t, 4.3, 5.2)
        y = ground2(x, z) + 1.6 + 0.05 * math.sin(t * 14.0) * run + 0.02 * math.sin(t * 2.2) * (1 - run)
        back = sm(t, 2.2, 2.75) * (1 - sm(t, 3.55, 4.1))
        yaw = a + math.pi * back + 0.03 * math.sin(t * 7.0) * run
        pitch = -0.05 - 0.1 * back + 0.04 * math.sin(t * 1.3) * (1 - run)
        cp = math.cos(pitch)
        fwd = (math.sin(yaw) * cp, math.sin(pitch), math.cos(yaw) * cp)
        roll = 0.03 * math.sin(t * 7.0) * run
        return (x, y, z), fwd, yaw, roll

    def render_run6(self):
        t = self.r6_t
        f6 = self.f6
        cam, fwd, yaw, roll = self.r6_camera()
        right = (-math.cos(yaw), 0.0, math.sin(yaw))
        up = (right[0] * math.sin(roll), math.cos(roll), right[2] * math.sin(roll))
        parts, extras = [], []
        if t > 3.0:
            parts = f6['herd'].parts(self.time)
            boss = f6['boss']
            parts.append(boss.parts(self.time))
            extras.append((self.m_shotgun, boss.gun_matrix()))
        self.draw_world2(cam, fwd, [], parts=parts, env=DAWN2, snowcover=True, extras=extras, up=up, blizzard=0.25)
        if self.r6_choice:
            self.draw_choice6()

    def draw_choice6(self):
        ui = self.ui
        a = int(255 * sm(self.r6_t, 6.2, 7.0))
        self.blit_text("He wants you to come with them.", self.f_msg, (215, 205, 190), (self.UW // 2, self.UH - 210), 'midtop', alpha=a)
        for i, (rc, name) in enumerate(zip(self.choice_rects(), ("JOIN THEM", "FIGHT"))):
            sel = i == self.r6_sel
            pygame.draw.rect(ui, (60, 8, 6, int(0.8 * a)) if sel else (0, 0, 0, int(0.6 * a)), rc)
            pygame.draw.rect(ui, (200, 45, 32, a) if sel else (120, 110, 100, a), rc, 2)
            self.blit_text(name, self.f_menu, (230, 60, 45) if sel else (200, 192, 182), rc.center, 'center', alpha=a)
        self.blit_text("[1] / [2]   or click", self.f_small, (130, 122, 115), (self.UW // 2, self.UH - 82), 'midtop', alpha=a)

    def run6_post(self):
        return self.post_params({'fear': 0.5 if self.r6_t > 4.0 else 0.2, 'red': 0.0})

    # ------------------------------------------------------------------ JOIN THEM: the bad ending
    def start_join6(self):
        self.state = 'join6'
        self.j6_t = 0.0
        self.j6_fired = set()
        self.r6_choice = None
        self.set_mouse(False)
        self.blood = []
        boss = self.f6['boss']
        cam, _f, _y, _r = self.r6_camera()
        self.j6_cam = cam
        self.j6_from = (boss.x, boss.z)
        # the room you wake up in, and who's standing in it by the end
        x, z = SEWER_ROOM
        self.j6_stand = [(x + 2.6, z + 1.6), (x - 1.8, z + 2.6), (x + 1.2, z + 3.4), (x + 3.4, z - 0.6), (x - 2.4, z + 0.6)]

    def j6_fire(self, name, at):
        if name not in self.j6_fired and self.j6_t >= at:
            self.j6_fired.add(name)
            return True
        return False

    def update_join6(self, dt):
        self.j6_t += dt
        t = self.j6_t
        A = self.audio
        boss = self.f6['boss']
        if t < 3.0:
            ex, ez = self.f6['E']
            fx, fz = self.j6_from
            k = sm(t, 0.3, 2.5)
            nx, nz = lerp(fx, ex, k * 0.8), lerp(fz, ez, k * 0.8)
            boss.walk += math.hypot(nx - boss.x, nz - boss.z) * 4.2
            boss.amt = 1.0 if 0.3 < t < 2.5 else 0.0
            boss.x, boss.z = nx, nz
            boss.gun_up = 1.0 - sm(t, 0.0, 1.0) + 0.9 * sm(t, 2.35, 2.6)
            A.loop('winter_amb', 0.5)
            A.loop('breath', 0.8)
            self.f6['herd'].animate(dt)
        if self.j6_fire('down', 0.2):
            A.play('bolt', 0.6)
        if self.j6_fire('hit', 2.7):
            A.play('impact', 1.0)
            A.play('smash', 0.8)
            self.shake = 1.0
        if self.j6_fire('quiet', 3.0):
            A.stop_loops()
        for i, at in enumerate((4.2, 5.4, 6.4, 7.3)):
            if self.j6_fire('hb%d' % i, at):
                A.play('heart', 0.5 + 0.1 * i)
        if t > 6.5:
            A.loop('sewer_amb', 0.4)
            A.loop('breath', 0.4 if t < 12.6 else 0.0)
        if self.j6_fire('whisper', 8.5):
            A.play('whisper', 0.6)
        if self.j6_fire('stab', 12.6):
            A.play('crack', 1.0)
            A.play('smash', 1.0)
            A.play('screech', 0.6)
            self.shake = 1.4
        if self.j6_fire('snap', 15.0):
            A.play('snap', 0.9)
        if self.j6_fire('stinger', 17.6):
            A.play('stinger', 0.8)
        self.shake = max(0.0, getattr(self, 'shake', 0.0) - dt * 1.5)
        # black after the blow; back in, under the forest; out at the end
        self.fade = max(sm(t, 2.75, 3.1) * (1 - sm(t, 6.5, 8.2)), sm(t, 20.0, 22.0))
        if 12.6 < t < 13.4:
            self.fade = max(self.fade, 0.85)
        if t > 22.5:
            self.fade = 0.0
            self.progress['ch5_done'] = True
            self.progress['ending_bad'] = True
            self.progress.pop('resume', None)
            self.save_prog()
            self.ending_pages = lore.BAD_ENDING
            self.start_ending()

    def j6_view(self):
        """Where you are and what you see, in the herd room (after 6.5 s)."""
        t = self.j6_t
        x, z = SEWER_ROOM
        F = W.SEWER_FLOOR
        rise = sm(t, 14.5, 17.5)
        cam = (x, F + lerp(0.32, 1.62, rise), z)
        bx, bz = x, z + lerp(1.15, 1.6, rise) - 0.35 * sm(t, 11.6, 12.5) * (1 - rise)
        head = (bx, F + 1.75, bz)
        tgt = (lerp(head[0], x, rise), lerp(head[1], cam[1] - 0.05, rise), lerp(head[2], z + 4.0, rise))
        fwd = look(cam, tgt)
        return cam, fwd, (bx, bz)

    def render_join6(self):
        t = self.j6_t
        boss = self.f6['boss']
        if t < 3.1:
            cam = self.j6_cam
            sh = getattr(self, 'shake', 0.0)
            fall = sm(t, 2.7, 3.1)
            cam = (cam[0], cam[1] - 0.8 * fall + random.uniform(-0.04, 0.04) * sh, cam[2])
            fwd = look(cam, (boss.x, boss.y() + 1.5 - 1.2 * fall, boss.z))
            yaw = math.atan2(fwd[0], fwd[2])
            right = (-math.cos(yaw), 0.0, math.sin(yaw))
            roll = 0.9 * fall
            up = (right[0] * math.sin(roll), math.cos(roll), right[2] * math.sin(roll))
            parts = self.f6['herd'].parts(self.time) + [boss.parts(self.time)]
            self.draw_world2(cam, fwd, [], parts=parts, env=DAWN2, snowcover=True,
                             extras=[(self.m_shotgun, boss.gun_matrix())], up=up)
            return
        if t < 6.5:
            self.r.fbo.use()
            self.r.fbo.clear(0, 0, 0, 1)
            return
        cam, fwd, (bx, bz) = self.j6_view()
        F = W.SEWER_FLOOR
        sh = getattr(self, 'shake', 0.0)
        if sh > 0:
            cam = (cam[0] + random.uniform(-1, 1) * 0.03 * sh, cam[1] + random.uniform(-1, 1) * 0.03 * sh, cam[2])
        rise = sm(t, 14.5, 17.5)
        # him: standing over you with the antlers, leaning in, then back with the others
        reach = 0.75 + 0.25 * sm(t, 11.6, 12.4) - 0.6 * sm(t, 13.4, 15.0)
        yaw = math.atan2(cam[0] - bx, cam[2] - bz)
        parts = [H5.pose_herd(bx, bz, yaw, 0.0, 0.0, reach, 0.0, self.time, seed=LEADER_SEED, y=F)]
        extras = []
        if t < 12.65:
            hands = herd_hands(bx, F, bz, yaw, reach, self.time)
            right = (-math.cos(yaw), 0.0, math.sin(yaw))
            for k, hp in enumerate(hands):
                sx = -1 if k == 0 else 1
                aimp = (cam[0] + right[0] * sx * 0.12, cam[1] + 0.12, cam[2] + right[2] * sx * 0.12)
                stab = sm(t, 12.2, 12.6)
                base = tuple(lerp(hp[i], aimp[i] + (hp[i] - aimp[i]) * 0.35, stab) for i in range(3))
                extras.append((self.m_antler, aim_at(base, aimp) @ RX(math.pi)))
        # the others, standing now, turned to look at you
        if t > 15.5:
            for i, (sx_, sz_) in enumerate(self.j6_stand):
                yw = math.atan2(cam[0] - sx_, cam[2] - sz_)
                parts.append(H5.pose_herd(sx_, sz_, yw, 0.0, 0.0, 0.1, 0.0, self.time, seed=i * 7 + 3, y=F))
        # your own antlers, just in the top of your view
        if t > 13.4:
            fx, fy, fz = fwd
            hl = math.hypot(fx, fz) or 1.0
            rx, rz = -fz / hl, fx / hl
            jerk = 0.08 * (math.sin(self.time * 11) > 0.9)
            for sx in (-1, 1):
                base = (cam[0] + rx * sx * 0.14 + fx * 0.12, cam[1] + 0.2, cam[2] + rz * sx * 0.14 + fz * 0.12)
                tip = (base[0] + rx * sx * 0.35 + fx * 0.3, base[1] + 0.55 + jerk, base[2] + rz * sx * 0.35 + fz * 0.3)
                extras.append((self.m_antler, aim_at(base, tip)))
        roll = (0.25 * math.sin(self.time * 1.7) + 0.4 * (math.sin(self.time * 17) > 0.95)) * sm(t, 13.4, 16.0)
        yawc = math.atan2(fwd[0], fwd[2])
        right = (-math.cos(yawc), 0.0, math.sin(yawc))
        up = (right[0] * math.sin(roll), math.cos(roll), right[2] * math.sin(roll))
        lamp = ((bx, F + 2.6, bz), 9.0, (1.5, 0.75, 0.45))
        fov = self.settings['fov'] + 18 * sm(t, 13.4, 16.0)
        fill = ((cam[0], cam[1] + 0.6, cam[2] + 0.4), 4.0, (0.5, 0.35, 0.3))
        self.draw_world(cam, fwd, 0.0, cam, fwd, parts, fov=fov, up=up, extra_lights=[lamp, fill], extras=extras)

    def join6_post(self):
        t = self.j6_t
        g = 0.0
        red = 0.0
        if t > 6.5:
            g = 0.35 * (1 - sm(t, 7.0, 10.0))
            if t > 12.6:
                red = 1.0 if t < 13.4 else 0.45 + 0.15 * math.sin(self.time * 3)
                g = 0.5 * (1 - sm(t, 12.6, 14.0)) + 0.35 * (math.sin(self.time * 13) > 0.85)
        return self.post_params({'fear': 0.6, 'glitch': g, 'red': red})

    # ------------------------------------------------------------------ FIGHT: the Herdsman
    def start_fight6(self, respawn=False):
        if self.f6 is None:
            self.setup_woods()
        else:
            self.place_herd()
        f6 = self.f6
        self.chapter = 5
        self.c5_phase = 'finale'
        self.state = 'play'
        self.r6_choice = None
        self.beast = None
        self.herd5 = None
        self.herdb = None
        self.proj = []
        self.markers = []
        self.blood = []
        self.debris = []
        self.msgs = []
        self.hp5 = 100.0
        self.shells = SHELLS
        self.pump_t = 0.0
        self.reload_t = -1.0
        self.hurt_src = None
        self.fear = self.red = self.glitch = 0.0
        self.give('shotgun')
        if not self.holding('shotgun'):
            self.inv_put_hands('shotgun', None, force=True)
        ex, ez = f6['E']
        p = self.player
        p.reset(ex, ground2(ex, ez), ez, f6['a'])
        f6['herd'].wake()
        f6['boss'].state = 'move'
        f6['boss'].cool = 2.5
        self.fade_in5 = 1.4
        self.fade = 1.0
        self.set_objective("Kill the one with the gun.  [Left mouse] fire   [R] reload")
        if respawn:
            self.message("Get up. He's still out there.", 3)
        else:
            self.message("No.", 2.5)
        self.set_resume(5, 'finale')
        self.set_mouse(True)

    def arena_clamp(self, x, z):
        ex, ez = self.f6['E']
        dx, dz = x - ex, z - ez
        d = math.hypot(dx, dz)
        if d > ARENA_R:
            x, z = ex + dx / d * ARENA_R, ez + dz / d * ARENA_R
        return x, z

    def update_finale(self, dt):
        import pygame as pg
        p = self.player
        f6 = self.f6
        w2 = self.w2
        herd, boss = f6['herd'], f6['boss']
        self.clock_t += dt
        keys = self.keys()
        fx, fz = math.sin(p.yaw), math.cos(p.yaw)
        rx, rz = -math.cos(p.yaw), math.sin(p.yaw)
        p.fx, p.fz = fx, fz
        mv = (1 if keys[pg.K_w] or keys[pg.K_UP] else 0) - (1 if keys[pg.K_s] or keys[pg.K_DOWN] else 0)
        ms = (1 if keys[pg.K_d] or keys[pg.K_RIGHT] else 0) - (1 if keys[pg.K_a] or keys[pg.K_LEFT] else 0)
        dx = fx * mv + rx * ms
        dz = fz * mv + rz * ms
        ln = math.hypot(dx, dz)
        if ln > 0:
            dx /= ln
            dz /= ln
        crouch = keys[pg.K_LCTRL] or keys[pg.K_c] or keys[pg.K_RCTRL]
        p.crouch += ((1.0 if crouch else 0.0) - p.crouch) * min(1.0, dt * 8)
        sprint = (keys[pg.K_LSHIFT] or keys[pg.K_RSHIFT]) and ln > 0 and mv >= 0 and not crouch and not p.exhausted
        p.sprinting = sprint
        speed = 1.35 if crouch else (5.1 if sprint else 2.7)
        if sprint:
            p.stamina -= 18 * dt
            if p.stamina <= 0:
                p.stamina = 0
                p.exhausted = True
                self.message("You can't breathe.", 2.0)
        else:
            p.stamina = min(100.0, p.stamina + 15 * dt)
            if p.exhausted and p.stamina > 40:
                p.exhausted = False
        acc = min(1.0, dt * 10)
        p.vx += (dx * speed - p.vx) * acc
        p.vz += (dz * speed - p.vz) * acc
        nx, nz = w2.collide(p.x + p.vx * dt, p.z + p.vz * dt, 0.3, p.x, p.z)
        nx, nz = herd.push_out(nx, nz)
        if not boss.dead:
            ddx, ddz = nx - boss.x, nz - boss.z
            d = math.hypot(ddx, ddz)
            if 1e-4 < d < 0.7:
                nx, nz = boss.x + ddx / d * 0.7, boss.z + ddz / d * 0.7
        nx, nz = self.arena_clamp(nx, nz)
        moved = math.hypot(nx - p.x, nz - p.z)
        p.x, p.z = nx, nz
        p.y = ground2(p.x, p.z)
        p.smooth_y += (p.y - p.smooth_y) * min(1.0, dt * 12)
        sp = moved / max(dt, 1e-4)
        p.bob_amt += (min(1.0, sp / 2.7) - p.bob_amt) * min(1.0, dt * 8)
        p.bob += moved * (2.0 if not sprint else 1.7)
        p.step_acc += moved
        stride = 0.55 if crouch else (1.0 if sprint else 0.78)
        if p.step_acc > stride:
            p.step_acc = 0.0
            self.audio.play_rand('step_snow', 4, 0.25 if crouch else (0.85 if sprint else 0.5))
        f = p.fwd()
        a_ = min(1.0, dt * 16)
        self.flash_dir = tuple(self.flash_dir[i] + (f[i] - self.flash_dir[i]) * a_ for i in range(3))
        self.audio.set_listener(p.x, p.z, p.yaw)
        A = self.audio
        A.loop('winter_amb', 0.5)
        for k_ in ('forest_amb', 'title_amb', 'gen_hum', 'creak', 'sewer_amb'):
            A.loop(k_, 0.0)
        # the gun
        self.pump_t = max(0.0, self.pump_t - dt)
        if 0 < self.pump_t < 0.5 and not getattr(self, '_pumped', False):
            self._pumped = True
            A.play('bolt', 0.5)
        if self.pump_t <= 0:
            self._pumped = False
        self.muzzle_t = max(0.0, self.muzzle_t - dt)
        self.kick = max(0.0, self.kick - dt * 5)
        self.hitmark_t = max(0.0, self.hitmark_t - dt)
        if self.reload_t >= 0 and self.pump_t <= 0:
            self.reload_t -= dt
            if self.reload_t < 0:
                self.shells += 1
                A.play('click', 0.6)
                self.reload_t = 0.5 if self.shells < SHELLS else -1.0
        elif self.has_shotgun and self.shells == 0 and self.pump_t <= 0 and self.reload_t < 0:
            self.start_reload()
        # health
        self.hurt_flash = max(0.0, self.hurt_flash - dt * 1.5)
        self.regen_t -= dt
        if self.regen_t <= 0 and self.hp5 < 100:
            self.hp5 = min(100.0, self.hp5 + 6.0 * dt)
        self.red = max(self.hurt_flash * 0.8, (1 - self.hp5 / 100.0) * 0.35)
        self.shake = max(0.0, getattr(self, 'shake', 0.0) - dt * 2)
        if self.fade_in5 > 0:
            self.fade_in5 -= dt
            self.fade = clamp(self.fade_in5 / 1.2, 0, 1)
        # them
        won = f6['won_t'] >= 0
        if not won:
            herd.update(dt, [(p.x, p.z)] if self.state == 'play' else [])
        herd.animate(dt)
        evs = herd.events
        herd.events = []
        for ev in evs:
            kind, i = ev[0], int(ev[1])
            if i >= len(herd._d['x']):
                continue
            hx, hz = herd._d['x'][i], herd._d['z'][i]
            if kind == 'hit':
                A.play3d('smash', hx, hz, 18, 0.5)
                if self.state == 'play' and math.hypot(p.x - ev[2], p.z - ev[3]) < 1.25:
                    self.hurt5(H5.DAMAGE, 'herd')
            elif kind == 'wind':
                A.play3d('snort', hx, hz, 14, 0.5)
            elif kind == 'alert':
                A.play3d('snap', hx, hz, 26, 0.9)
            elif kind == 'die':
                A.play3d('tackle', hx, hz, 30, 0.8)
                self.spawn_blood(hx, ground2(hx, hz) + 1.0, hz, 14, spread=2.0)
            elif kind == 'flinch':
                A.play3d('snap', hx, hz, 20, 0.4)
        if self.state != 'play':
            return
        boss.update(dt, p.x, p.z, lambda x, z: self.arena_clamp(*w2.collide(x, z, 0.4, x, z)))
        bevs = boss.events
        boss.events = []
        for ev in bevs:
            if ev[0] == 'aim':
                A.play3d('bolt', boss.x, boss.z, 40, 1.0)
            elif ev[0] == 'fire':
                self.herdsman_fires(ev[1], ev[2])
                if self.state != 'play':
                    return
            elif ev[0] == 'die':
                A.play3d('tackle', boss.x, boss.z, 60, 1.0)
                A.play('stinger', 0.7)
                self.spawn_blood(boss.x, boss.y() + 1.3, boss.z, 24, spread=2.2)
                f6['won_t'] = 0.0
                self.message("He's down.", 3)
        near = min((math.hypot(herd._d['x'][i] - p.x, herd._d['z'][i] - p.z) for i in range(herd.n) if herd.alive(i)
                    and herd.st[i] in (H5.CHASE, H5.WIND, H5.RECOVER)), default=99.0)
        A.loop('breath', clamp(1.0 - near / 10.0, 0.0, 0.7))
        if won:
            f6['won_t'] += dt
            wt = f6['won_t']
            if wt > 1.0 and not f6.get('herd_down'):
                # whatever was holding them up went with him
                f6['herd_down'] = True
                for i in range(herd.n):
                    if herd.alive(i):
                        herd.damage(i, 999.0)
            if wt > 2.4 and not f6.get('told'):
                f6['told'] = True
                self.message("They're all down. The truck -- get back to the truck.", 4)
                self.set_objective("Get back to the truck.")
            if wt > 5.0:
                self.fade = clamp((wt - 5.0) / 1.2, 0, 1)
            if wt > 6.4:
                self.start_truck6()
                return
        self.update_blood(dt)
        self.focus = None
        self.obj_t = max(0.0, self.obj_t - dt)
        self.glitch += (0.0 - self.glitch) * min(1.0, dt * 20)

    def herdsman_fires(self, ax, az):
        boss = self.f6['boss']
        p = self.player
        self.audio.play3d('rifle', boss.x, boss.z, 140, 1.0)
        dx, dz = ax - boss.x, az - boss.z
        ln = math.hypot(dx, dz) or 1.0
        ux, uz = dx / ln, dz / ln
        rx, rz = p.x - boss.x, p.z - boss.z
        along = rx * ux + rz * uz
        lateral = abs(rx * uz - rz * ux)
        if 0 < along < 34 and lateral < 0.7 + 0.035 * along:
            self.hurt5(clamp(42.0 - along * 1.6, 10.0, 34.0), 'herdsman')
        else:
            self.audio.play('snap', 0.5)          # buckshot through the branches past you

    def shoot_rays6(self, cam, f, yaw, n, dmg, spread):
        f6 = self.f6
        herd, boss = f6['herd'], f6['boss']
        herd._fit()
        herd.hear(cam[0], cam[2], 30.0)
        right = (-math.cos(yaw), 0.0, math.sin(yaw))
        up = (right[1] * f[2] - right[2] * f[1], right[2] * f[0] - right[0] * f[2], right[0] * f[1] - right[1] * f[0])
        herd_dmg = {}
        total = 0.0
        hit = False
        import chapter5 as C5
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            rr = spread * math.sqrt(random.random())
            d = tuple(f[j] + (right[j] * math.cos(a) + up[j] * math.sin(a)) * rr for j in range(3))
            ln = math.sqrt(sum(v * v for v in d))
            d = tuple(v / ln for v in d)
            best = None
            for i in range(herd.n):
                if not herd.alive(i) or math.hypot(herd._d['x'][i] - cam[0], herd._d['z'][i] - cam[2]) > 45:
                    continue
                for c, rad, mult in herd.hit_spheres(i):
                    tt = C5.ray_sphere(cam, d, c, rad)
                    if tt is not None and (best is None or tt < best[0]):
                        best = (tt, i, mult)
            if not boss.dead:
                for c, rad, mult in boss.hit_spheres():
                    tt = C5.ray_sphere(cam, d, c, rad)
                    if tt is not None and (best is None or tt < best[0]):
                        best = (tt, 'boss', mult)
            if best is None:
                continue
            dist, who, mult = best
            hx, hy, hz = cam[0] + d[0] * dist, cam[1] + d[1] * dist, cam[2] + d[2] * dist
            fall = clamp(1.0 - (dist - 8.0) / 22.0, 0.3, 1.0) if n > 1 else 1.0
            if who == 'boss':
                total += dmg * mult * fall
            else:
                herd_dmg[who] = herd_dmg.get(who, 0.0) + dmg * mult * fall
            self.spawn_blood(hx, hy, hz, 3, vel=(d[0] * 3, 1.2, d[2] * 3), spread=1.6, size=(0.04, 0.1))
            hit = True
        for i, amt in herd_dmg.items():
            herd.damage(i, amt)
        if total > 0:
            boss.damage(total)
            self.audio.play3d('tackle', boss.x, boss.z, 60, 0.5)
        if hit:
            self.hitmark_t = 0.18
        return hit

    def render_finale(self):
        p = self.player
        f6 = self.f6
        cam = p.eye()
        sh = getattr(self, 'shake', 0.0)
        if sh > 0:
            cam = (cam[0] + random.uniform(-1, 1) * 0.05 * sh, cam[1] + random.uniform(-1, 1) * 0.05 * sh, cam[2])
        fwd = p.fwd()
        herd, boss = f6['herd'], f6['boss']
        parts = [pp for i, pp in enumerate(herd.parts(self.time))
                 if math.hypot(herd._d['x'][i] - p.x, herd._d['z'][i] - p.z) < 60]
        parts.append(boss.parts(self.time))
        extras = [(self.m_shotgun, boss.gun_matrix())]
        lights = []
        if boss.flash_t > 0:
            mz = boss.muzzle()
            extras.append((self.m_flash, boss.gun_matrix() @ T(0, 0.025, 0.88) @ S(1.6)))
            lights.append((mz, 12.0, (3.0, 2.0, 1.0)))
        if self.muzzle_t > 0:
            lights.append(((cam[0] + fwd[0], cam[1], cam[2] + fwd[2]), 12.0, (3.0, 2.0, 1.0)))
        self.draw_world2(cam, fwd, lights, parts=parts, env=DAWN2, snowcover=True, extras=extras,
                         hold=(True, p.yaw, p.pitch), blizzard=0.25)
        self.draw_shotgun_vm(cam, fwd, p.yaw, p.pitch)

    def draw_shotgun_vm(self, cam, fwd, yaw, pitch):
        if not self.holding('shotgun'):
            return
        r = self.r
        right = (-math.cos(yaw), 0.0, math.sin(yaw))
        f = fwd
        upv = (right[1] * f[2] - right[2] * f[1], right[2] * f[0] - right[0] * f[2], right[0] * f[1] - right[1] * f[0])
        kick = self.kick
        rl = sm(self.reload_t, 0.55, 0.0) if self.reload_t >= 0 else 0.0
        pos = tuple(cam[i] + right[i] * 0.21 + f[i] * (0.42 - 0.07 * kick) - upv[i] * (0.23 + 0.06 * rl) for i in range(3))
        G = T(*pos) @ RY(yaw) @ RX(-pitch - 0.12 * kick + 0.35 * rl) @ RZ(-0.3 * rl)
        r.draw(self.m_shotgun, model=G)
        pk = self.pump_t
        slide = 0.11 * (math.sin(clamp((0.75 - pk) / 0.4, 0, 1) * math.pi) if 0 < pk < 0.75 else 0.0)
        r.draw(self.m_pump, model=G @ T(0, 0, 0.42 - slide))
        if self.muzzle_t > 0:
            r.draw(self.m_flash, model=G @ T(0, 0.025, 0.88) @ RZ(random.random() * 6) @ S(1.0 + random.random()))

    def render_scare_finale(self, cam, yaw, fwd, k):
        d = 1.25 - min(k, 1.0) * 0.3
        x, z = cam[0] + math.sin(yaw) * d, cam[2] + math.cos(yaw) * d
        seed = LEADER_SEED if getattr(self, 'hurt_src', None) == 'herdsman' else 11
        parts = H5.pose_herd(x, z, yaw + math.pi, 0.0, 0.0, 0.7, 0.0, self.time * 3, seed=seed, swing=0.3, y=cam[1] - 1.72)
        self.draw_world2(cam, fwd, [], parts=[parts], env=DAWN2, snowcover=True)

    def draw_hud_finale(self):
        cx, cy = self.UW // 2, self.UH // 2
        boss = self.f6['boss']
        if not boss.dead:
            w = int(self.UW * 0.5)
            x0 = cx - w // 2
            self.blit_text("THE HERDSMAN", self.f_hud, (200, 40, 30), (cx, 18), 'midtop')
            pygame.draw.rect(self.ui, (0, 0, 0, 190), (x0 - 2, 42, w + 4, 14))
            fill = int(w * boss.hp / boss.MAX_HP)
            col = (230, 230, 230, 240) if boss.hurt_t > 0 else (160, 18, 12, 240)
            pygame.draw.rect(self.ui, col, (x0, 44, fill, 10))
            if boss.state == 'aim':
                self.blit_text("HE'S AIMING -- MOVE", self.f_small, (230, 200, 60), (cx, 60), 'midtop')
        pygame.draw.rect(self.ui, (0, 0, 0, 170), (24, self.UH - 96, 204, 14))
        pygame.draw.rect(self.ui, (200, 50, 40, 230) if self.hp5 < 35 else (210, 200, 185, 220),
                         (26, self.UH - 94, int(200 * self.hp5 / 100), 10))
        self.blit_text("HEALTH", self.f_small, (200, 190, 180), (26, self.UH - 116))
        if self.holding('shotgun'):
            for i in range(SHELLS):
                x = self.UW - 30 - i * 16
                c = (200, 40, 30, 240) if i < self.shells else (60, 50, 50, 140)
                pygame.draw.rect(self.ui, c, (x, self.UH - 104, 10, 22))
                pygame.draw.rect(self.ui, (200, 170, 60, 240) if i < self.shells else (70, 60, 50, 140),
                                 (x, self.UH - 88, 10, 6))
            if self.reload_t >= 0:
                self.blit_text("RELOADING", self.f_small, (200, 190, 180), (self.UW - 26, self.UH - 128), 'topright')
            elif self.shells == 0:
                self.blit_text("[R] RELOAD", self.f_small, (220, 80, 60), (self.UW - 26, self.UH - 128), 'topright')
        if self.hitmark_t > 0:
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                pygame.draw.line(self.ui, (240, 230, 220, 230), (cx + sx * 6, cy + sy * 6), (cx + sx * 12, cy + sy * 12), 2)
        if self.obj_t > 0:
            a = int(clamp(self.obj_t / 1.0, 0, 1) * 255)
            self.blit_text(self.objective, self.f_small, (160, 152, 142), (26, 76), alpha=a)

    # ------------------------------------------------------------------ the good ending: the truck
    def start_truck6(self):
        self.state = 'truck6'
        self.t6_t = 0.0
        self.t6_fired = set()
        self.set_mouse(False)
        self.audio.stop_all()
        self.audio.stop_loops()
        self.reset_truck()
        self.fade = 1.0
        self.progress.pop('resume', None)

    def t6_fire(self, name, at):
        if name not in self.t6_fired and self.t6_t >= at:
            self.t6_fired.add(name)
            return True
        return False

    def update_truck6(self, dt):
        self.t6_t += dt
        t = self.t6_t
        A = self.audio
        tr = self.truck
        A.loop('forest_amb', 0.3)
        A.loop('breath', 0.6 if t < 7.0 else 0.0)
        for i in range(13):
            if self.t6_fire('st%d' % i, 0.3 + i * 0.36) and t < 5.0:
                A.play_rand('step_grass', 4, 0.6)
        if self.t6_fire('open', 5.0):
            A.play('door_open', 0.8)
        if self.t6_fire('shut', 6.6):
            A.play('door_close', 0.9)
        if self.t6_fire('key1', 7.3):
            A.play('click', 0.7)
        if self.t6_fire('fail', 7.6):
            A.play('clunk', 0.7)
            A.play('gen_start', 0.35)
        if self.t6_fire('key2', 8.8):
            A.play('click', 0.7)
        if self.t6_fire('start', 9.2):
            A.play('gen_start', 0.9)
            tr['lights'] = True
        if self.t6_fire('car', 10.8):
            A.play('car', 0.8)
        A.loop('gen_hum', 0.3 if 9.2 < t < 15.0 else 0.0)
        tr['door'] = sm(t, 5.0, 5.6) * (1 - sm(t, 6.6, 6.9))
        if t > 10.2:
            k = sm(t, 10.6, 15.5)
            tr['z'] = TRUCK_POS[1] - 7.6 * k
        self.fade = max(clamp(1.0 - t / 0.9, 0, 1), sm(t, 14.6, 16.2))
        if t > 16.6:
            self.fade = 0.0
            self.audio.loop('gen_hum', 0.0)
            self.reset_truck()
            self.progress['ch5_done'] = True
            self.progress['ending_good'] = True
            self.progress.pop('resume', None)
            self.save_prog()
            self.ending_pages = lore.GOOD_ENDING
            self.start_ending()

    def render_truck6(self):
        t = self.t6_t
        tr = self.truck
        g0 = self.truck_ground()
        door = truck_world(tr['x'], g0, tr['z'], tr['yaw'], (1.6, 1.62, 0.2))
        if t < 6.6:
            # down the trail, to the driver's door, and in
            sx, sz = 0.0, -36.0
            k = sm(t, 0.0, 5.0)
            x = lerp(sx, door[0], k)
            z = lerp(sz, door[2], k)
            y = float(W.terrain_h(x, z)) + 1.6 + 0.05 * math.sin(t * 13) * (1 - k)
            cam = (x, y, z)
            seat = self.truck_seat()
            k2 = sm(t, 5.6, 6.6)
            cam = tuple(lerp(cam[i], seat[i], k2) for i in range(3))
            yaw = lerp(math.pi, -math.pi / 2, sm(t, 4.4, 5.6))
            yaw = lerp(yaw, 0.0, k2) if k2 > 0 else yaw
            pitch = -0.1
            cp = math.cos(pitch)
            fwd = (math.sin(yaw) * cp, math.sin(pitch), math.cos(yaw) * cp)
            self.draw_ch1_view(cam, fwd, env=DAWN1)
        elif t < 10.2:
            # behind the wheel. Come on.
            cam = self.truck_seat()
            jit = 0.012 * math.sin(t * 40) if 7.6 < t < 8.0 or t > 9.2 else 0.0
            cam = (cam[0], cam[1] + jit, cam[2])
            self.draw_ch1_view(cam, look((0, 0, 0), (0.0, -0.05, 1.0)), env=DAWN1)
        else:
            # from up the trail: the truck backs out of the woods
            cam = (0.4, float(W.terrain_h(0.4, -46.5)) + 1.5, -46.5)
            fwd = look(cam, (tr['x'], g0 + 1.0, tr['z']))
            self.draw_ch1_view(cam, fwd, env=DAWN1)
