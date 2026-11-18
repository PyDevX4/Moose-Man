"""The end of Chapter Three: the Elk catches you at the mouth of the old adit.

It picks you up. You shoot it in the head with the rifle; it drops you, clutches its
head and swats you across the cavern, and the rifle goes with you. It comes over.
You empty the revolver into it and it doesn't even flinch -- it takes the gun out of
your hand and crushes it. It rears up to bring both hands down on you, and you get
up and run: down the adit and into the old cage at the end, and up.

You lose both guns here. Mixed into game.Game.
"""
import math
import random

import pygame

from engine import T, S, RX, RY, RZ
from elk import pose_elk
import chapter3 as C3


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def sm(t, a, b):
    k = clamp((t - a) / (b - a), 0.0, 1.0)
    return k * k * (3 - 2 * k)


def lerp(a, b, k):
    return a + (b - a) * k


def lerp_t(a, b, k):
    return tuple(a[i] + (b[i] - a[i]) * k for i in range(len(a)))


def norm(v):
    ln = math.sqrt(sum(x * x for x in v)) or 1.0
    return tuple(x / ln for x in v)


def look(cam, tgt):
    return norm((tgt[0] - cam[0], tgt[1] - cam[1], tgt[2] - cam[2]))


# arm poses (swing, splay, elbow out, elbow bend), solved for where the hands need to be
REST = (-0.45, 0.55, 0.9, -0.25)
HOLD = (-1.631, -0.126, 0.008, -0.144)       # right hand: you, up in front of its face (pitch 0.9)
HEAD = (-0.842, -1.007, 0.406, -2.263)      # right hand clutching its head (pitch 0.9)
SWAT_A = (0.666, 1.088, -0.133, -1.339)     # left hand drawn back...
SWAT_B = (-0.594, -0.639, 0.006, -0.078)    # ...and swept across
REACH = (-0.03, 0.287, 1.008, -0.894)       # left hand down to the revolver (pitch 1.2)
CRUSH_L = (-0.541, -0.113, 0.84, -1.491)    # both hands together in front of its muzzle
CRUSH_R = (-0.569, -0.124, 0.863, -1.509)
UP = (-1.508, -0.003, 0.666, -1.923)        # both hands high over its head (pitch 0.5)
SLAM = (-0.656, -0.017, 0.006, -0.086)      # ...and down on the floor (pitch 1.1)

SHOTS = (9.0, 9.4, 9.8, 10.2, 10.6, 11.0)
END = 23.0


class Ch3EscapeMixin:
    def start_elkgrab(self):
        self.state = 'elkgrab'
        self.eg_t = 0.0
        self.eg_fired = set()
        self.eg_bits = []
        self.debris = []
        self.msgs = []
        self.shake = 0.0
        self.set_mouse(False)
        self.inv_open = False
        A = self.audio
        A.loop('breath', 0)
        A.loop('creak', 0)
        lv = self.lv_low
        C = C3.C
        SH = C3.LOW_SHIFT
        ax = lv.center(20, SH + 36)[0]
        mz = lv.oz + (SH + 36) * C                   # the mouth of the adit
        ex, ez = lv.center(*lv.exit)
        y0 = lv.y0
        self.eg = {
            'y0': y0, 'ax': ax, 'mz': mz, 'ex': ex, 'ez': ez,
            'run0': (ax + 0.4, mz - 7.4),
            'G': (ax, mz - 2.6),                      # where it catches you
            'E0': (ax - 7.6, mz - 4.6),               # where it comes from
            'E': (ax - 5.35, mz - 2.7),              # where it holds you up
            'L': (ax + 2.5, mz - 1.9),                # where you land
            'gun': (ax + 5.6, mz - 0.2),              # where the rifle lands
        }
        g = self.eg
        lx, lz = g['L']
        # it walks over to you, and stops with you at its feet
        g['EW'] = (lx - 5.4, lz - 0.2)
        g['EC'] = (lx - 4.0, lz - 0.1)
        g['EM'] = (ax, mz - 4.6)                      # at the mouth of the adit, too big to follow

    def at_adit_mouth(self):
        """Right at the mouth of the old adit (or already in it): where it catches you."""
        lv = self.lv
        if lv is not self.lv_low:
            return False
        p = self.player
        c, r = lv.cell_of(p.x, p.z)
        SH = C3.LOW_SHIFT
        return 17 <= c <= 23 and r >= SH + 35

    def eg_fire(self, name, at):
        if name not in self.eg_fired and self.eg_t >= at:
            self.eg_fired.add(name)
            return True
        return False

    # ------------------------------------------------------------------ what happens when
    def eg_elk(self, t):
        """(x, z, yaw, y, kwargs) for the Elk at time t."""
        g = self.eg
        y = g['y0']
        kw = dict(jaw=0.5, split=0.5, head_pitch=0.35, pitch=1.2, phase=0.0, amt=0.0, t=self.time)
        R = REST
        Lf = REST
        if t < 0.95:
            k = sm(t, 0.0, 0.95)
            x, z = lerp_t(g['E0'], g['E'], k)
            kw.update(phase=t * 9.0, amt=1.0 - k, jaw=0.9, split=0.9)
            R = lerp_t(REST, HOLD, sm(t, 0.55, 0.95))
        elif t < 4.6:
            x, z = g['E']
            kw['pitch'] = lerp(1.2, 0.9, sm(t, 0.95, 1.7))
            R = HOLD
            kw.update(jaw=0.45 + 0.35 * sm(t, 1.8, 2.6), split=0.4 + 0.5 * sm(t, 1.8, 2.6), head_pitch=-0.3)
            if t > 3.2:
                # the shot: its head snaps back, it lets go and clutches its face
                kick = math.exp(-(t - 3.2) * 4.0)
                kw['head_pitch'] = -0.3 + 0.65 * sm(t, 3.2, 4.0) - 0.9 * kick
                kw['head_roll'] = 0.4 * kick
                kw.update(jaw=1.2, split=1.0)
                R = lerp_t(HOLD, HEAD, sm(t, 3.45, 4.0))
            Lf = lerp_t(REST, SWAT_A, sm(t, 3.9, 4.35))
            Lf = lerp_t(Lf, SWAT_B, sm(t, 4.35, 4.62))
        elif t < 11.6:
            # it comes over, holding its head; the revolver doesn't slow it down
            if t < 5.2:
                x, z = g['E']
                Lf = lerp_t(SWAT_B, REST, sm(t, 4.62, 5.2))
                k = 0.0
            elif t < 8.6:
                k = sm(t, 5.2, 8.6)
                x, z = lerp_t(g['E'], g['EW'], k)
                kw.update(phase=(t - 5.2) * 3.0, amt=0.7)
            else:
                k = sm(t, 8.6, 11.6)
                x, z = lerp_t(g['EW'], g['EC'], k)
                kw.update(phase=(t - 5.2) * 3.0, amt=0.45 * (1 - sm(t, 11.0, 11.6)))
            hold_head = 1.0 - sm(t, 8.4, 9.2)
            kw['pitch'] = lerp(1.2, 0.95, hold_head)
            R = lerp_t(REST, HEAD, hold_head)
            kw.update(jaw=0.7, split=0.7, head_pitch=0.35 + 0.2 * (1 - hold_head))
            for s in SHOTS:
                if s <= t < s + 0.25:
                    kw['head_roll'] = 0.06 * math.sin((t - s) * 40)
        elif t < 15.9:
            x, z = g['EC']
            Lf = lerp_t(REST, REACH, sm(t, 11.6, 12.25))
            Lf = lerp_t(Lf, CRUSH_L, sm(t, 12.35, 12.95))
            R = lerp_t(REST, CRUSH_R, sm(t, 12.5, 12.95))
            kw.update(head_pitch=0.55 - 0.25 * sm(t, 12.3, 12.9), jaw=0.5, split=0.6)
            if t > 13.7:
                # up on its hind legs, both hands high
                k = sm(t, 13.7, 15.0)
                kw['pitch'] = lerp(1.2, 0.5, k)
                Lf = lerp_t(CRUSH_L, UP, k)
                R = lerp_t(CRUSH_R, UP, k)
                kw.update(jaw=0.5 + 0.8 * sm(t, 14.4, 14.7), split=1.0, head_pitch=0.3)
        elif t < 16.6:
            x, z = g['EC']
            k = sm(t, 15.9, 16.2)
            kw['pitch'] = lerp(0.5, 1.1, k)
            Lf = lerp_t(UP, SLAM, k)
            R = Lf
            kw.update(jaw=1.2, split=1.0, head_pitch=0.3)
        else:
            # after you, to the mouth of the adit; it can't fit
            k = sm(t, 16.6, 18.6)
            x, z = lerp_t(g['EC'], g['EM'], k)
            kw.update(phase=(t - 16.6) * 6.0, amt=1.0 - sm(t, 18.2, 18.8), jaw=1.0, split=1.0)
            kw['pitch'] = lerp(1.1, 1.3, sm(t, 18.0, 18.8))
            R = Lf = REST
            y -= 0.8 * sm(t, 18.0, 18.8)
            kw['head_pitch'] = 0.35 + 0.35 * sm(t, 18.0, 18.8)
            if t > 19.2:
                kw['jaw'] = 1.25 + 0.1 * math.sin(t * 30)
                kw['head_roll'] = 0.15 * math.sin(t * 2.0)
        if t < 16.6:
            yaw = math.atan2(g['G'][0] - x, g['G'][1] - z) if t < 4.7 else math.atan2(g['L'][0] - x, g['L'][1] - z)
        else:
            yaw = 0.0 if t > 18.4 else math.atan2(g['EM'][0] - x + 1e-4, g['EM'][1] - z + 0.5)
        kw['arms'] = {1: R, -1: Lf}
        return x, z, yaw, y, kw

    def eg_pose(self, t):
        x, z, yaw, y, kw = self.eg_elk(t)
        hands = {}
        parts, head = pose_elk(x, y, z, yaw, hands=hands, **kw)
        hp = head @ (0.0, 0.1, 0.35, 1.0)
        return parts, hands, (float(hp[0]), float(hp[1]), float(hp[2]))

    def eg_camera(self, t, hands, headp):
        """(cam, fwd, roll) -- your eyes, through all of it."""
        g = self.eg
        y0 = g['y0']
        gx, gz = g['G']
        lx, lz = g['L']
        roll = 0.0
        if t < 0.95:
            # running for the adit
            k = clamp(t / 0.95, 0, 1)
            x, z = lerp_t(g['run0'], (gx, gz), k)
            cam = (x, y0 + 1.6 + 0.06 * math.sin(t * 19), z)
            fwd = look(cam, (g['ax'], y0 + 1.3, g['mz'] + 4.0))
            if t > 0.75:
                # it has you: yanked sideways
                fwd = norm(lerp_t(fwd, look(cam, headp), sm(t, 0.75, 0.95)))
            return cam, fwd, 0.25 * sm(t, 0.75, 0.95)
        hand = hands[1][:3, 3]
        held = (float(hand[0]), float(hand[1]) + 0.12, float(hand[2]) + 0.15)
        if t < 3.5:
            k = sm(t, 0.95, 1.5)
            c0 = (gx, y0 + 1.6, gz)
            cam = lerp_t(c0, held, k)
            sq = 0.04 * math.sin(t * 23) * (1 - sm(t, 1.5, 2.2))
            cam = (cam[0], cam[1] + sq, cam[2])
            return cam, look(cam, headp), 0.25 * (1 - sm(t, 1.0, 2.0))
        if t < 4.62:
            # dropped
            ft = t - 3.5
            fy = max(y0 + 0.4, held[1] - 4.9 * ft * ft) if ft > 0.05 else held[1]
            k = sm(t, 3.5, 3.85)
            cam = (lerp(held[0], gx, k), fy, lerp(held[2], gz, k))
            roll = 0.35 * sm(t, 3.6, 3.9)
            return cam, look(cam, headp), roll
        if t < 5.3:
            # swatted clean across the cavern
            k = sm(t, 4.62, 5.3)
            hop = 1.1 * math.sin(math.pi * k)
            cam = (lerp(gx, lx, k), y0 + 0.4 + hop, lerp(gz, lz, k))
            spin = 5.2 * k
            fwd = (math.sin(spin + 1.2), -0.2, math.cos(spin + 1.2))
            return cam, norm(fwd), 0.35 + 1.4 * math.sin(math.pi * k) + 0.3 * k
        if t < 15.4:
            # on the floor
            breath = 0.015 * math.sin(t * 5.5)
            cam = (lx, y0 + 0.38 + breath, lz)
            roll = lerp(0.65, 0.12, sm(t, 5.3, 7.5))
            tgt = headp
            if 8.6 < t < 11.8:
                tgt = (headp[0], lerp(headp[1], headp[1] - 1.2, 0.5), headp[2])
            fwd = look(cam, tgt)
            if t < 6.0:
                fwd = norm(lerp_t((0.4, -0.3, 0.9), fwd, sm(t, 5.3, 6.0)))
            return cam, fwd, roll
        # up, and running
        mouth = (g['ax'], g['mz'] - 0.2)
        cage = (g['ex'], g['ez'] - 0.2)
        if t < 16.3:
            k = sm(t, 15.4, 16.1)
            cam = (lx, y0 + lerp(0.38, 1.6, k), lz)
            a = look(cam, headp)
            b = look(cam, (mouth[0], y0 + 1.3, mouth[1] + 4))
            return cam, norm(lerp_t(a, b, sm(t, 15.6, 16.2))), 0.12 * (1 - k)
        if t < 18.7:
            d1 = math.hypot(mouth[0] - lx, mouth[1] - lz)
            d2 = math.hypot(cage[0] - mouth[0], cage[1] - mouth[1])
            k = clamp((t - 16.3) / 2.4, 0, 1)
            k = k * (2 - k) * 0.5 + k * 0.5
            d = k * (d1 + d2)
            if d < d1:
                x, z = lerp_t((lx, lz), mouth, d / d1)
            else:
                x, z = lerp_t(mouth, cage, (d - d1) / d2)
            cam = (x, y0 + 1.55 + 0.07 * math.sin(t * 17), z)
            return cam, look(cam, (g['ax'], y0 + 1.3, g['ez'] + 3)), 0.04 * math.sin(t * 8.5)
        # in the cage, turned round: up
        rise = max(0.0, t - 19.5) ** 1.6 * 0.8
        cam = (cage[0], y0 + 1.6 + rise + 0.02 * math.sin(t * 13), cage[1] + 0.3)
        turn = math.pi * sm(t, 18.7, 19.4)
        b = look(cam, (g['ax'], y0 + 1.0, g['mz'] - 2.0))
        if turn < math.pi:
            return cam, norm((math.sin(turn) * 0.6, b[1] * turn / math.pi, math.cos(turn))), 0.0
        return cam, b, 0.0

    # ------------------------------------------------------------------ update
    def update_elkgrab(self, dt):
        self.eg_t += dt
        t = self.eg_t
        A = self.audio
        g = self.eg
        A.loop('sewer_amb', 0.45)
        A.loop('winter_amb', 0.0)
        A.loop('creak', 0.7 if 19.5 < t < 22.6 else 0.0)
        A.loop('breath', 0.8 if 5.0 < t < 16.0 else 0.0)
        for i in range(4):
            if self.eg_fire('st%d' % i, i * 0.22):
                A.play_rand('step_conc', 4, 0.8)
        if self.eg_fire('lunge', 0.5):
            A.play('elk_bugle', 1.0)
            A.play('stinger', 0.8)
        if self.eg_fire('grab', 0.9):
            A.play('impact', 0.8)
            self.shake = 0.8
        if self.eg_fire('heart', 1.4):
            A.play('heart', 0.8)
        if self.eg_fire('bolt', 2.0):
            A.play('bolt', 0.7)
        if self.eg_fire('shot', 3.2):
            A.play('rifle_shot', 1.0)
            self.shake = 1.0
            self.eg_flash = 0.08
            _, _, hp = self.eg_pose(t)
            self.eg_blood(hp, 40, spread=2.4, up=2.0)
        if self.eg_fire('scream', 3.35):
            A.play('elk_bugle', 1.0)
        if self.eg_fire('drop', 3.75):
            A.play('impact', 0.7)
            self.shake = 0.6
        if self.eg_fire('swat', 4.62):
            A.play('impact', 1.0)
            A.play('smash', 0.5)
            self.shake = 1.4
        if self.eg_fire('land', 5.25):
            A.play('impact', 0.8)
            self.shake = 0.8
        if self.eg_fire('gunland', 5.5):
            A.play('clunk', 0.5)
        for i in range(10):
            if self.eg_fire('w%d' % i, 5.4 + i * 0.36):
                A.play('mstep', 0.55 + 0.04 * i)
        for i, s in enumerate(SHOTS):
            if self.eg_fire('rv%d' % i, s):
                A.play('revolver', 0.8)
                self.shake = max(self.shake, 0.35)
                self.eg_flash = 0.06
                x, z, yaw, y, _ = self.eg_elk(t)
                hx = x + math.sin(yaw) * (1.9 + 0.3 * (i % 3))
                hz = z + math.cos(yaw) * (1.9 + 0.3 * (i % 3))
                self.eg_blood((hx + random.uniform(-0.3, 0.3), y + 2.5 + random.uniform(-0.3, 0.6), hz), 8, spread=0.8, up=1.0)
        if self.eg_fire('empty', 11.35):
            A.play('click', 0.8)
        if self.eg_fire('empty2', 11.7):
            A.play('click', 0.7)
        if self.eg_fire('take', 12.3):
            A.play('impact', 0.5)
        if self.eg_fire('crush', 13.05):
            A.play('crack', 1.0)
            A.play('snap', 0.8)
            parts, hands, _ = self.eg_pose(t)
            p = hands[-1][:3, 3]
            for _ in range(14):
                self.eg_bits.append([float(p[0]), float(p[1]), float(p[2]), random.uniform(-1, 1), random.uniform(0, 1.5),
                                     random.uniform(-1, 1), random.uniform(0.02, 0.06), 'black', False])
        if self.eg_fire('crack2', 13.4):
            A.play('crack', 0.7)
        if self.eg_fire('rear', 14.4):
            A.play('elk_bugle', 1.0)
            A.play('stinger', 0.6)
        if self.eg_fire('run', 15.5):
            self.message("Get up. GET UP.", 1.6)
        if self.eg_fire('slam', 16.2):
            A.play('smash', 1.0)
            A.play('impact', 1.0)
            self.shake = 1.8
            x, z, yaw, y, _ = self.eg_elk(t)
            self.burst_debris(x + math.sin(yaw) * 4.2, g['y0'] + 0.1, z + math.cos(yaw) * 4.2, 60, up=5.0, spread=3.5)
        for i in range(9):
            if self.eg_fire('rs%d' % i, 16.4 + i * 0.27):
                A.play_rand('step_conc', 4, 0.85)
        for i in range(5):
            if self.eg_fire('ew%d' % i, 16.7 + i * 0.4):
                A.play('mstep', 0.9)
        if self.eg_fire('mouth', 18.5):
            A.play('impact', 0.9)
            self.shake = 0.9
            self.burst_debris(g['ax'], g['y0'] + 2.4, g['mz'] - 0.2, 30, up=1.0, spread=1.5, size=(0.05, 0.2))
        if self.eg_fire('cage', 18.9):
            A.play('clunk', 1.0)
        if self.eg_fire('roar_end', 19.2):
            A.play('elk_bugle', 1.0)
        if self.eg_fire('lift', 19.5):
            A.play('clunk', 0.8)
        self.eg_flash = max(0.0, getattr(self, 'eg_flash', 0.0) - dt)
        self.shake = max(0.0, self.shake - dt * 1.8)
        # drips off its head while it comes for you
        if 4.0 < t < 11.6 and random.random() < dt * 9:
            _, _, hp = self.eg_pose(t)
            self.eg_blood(hp, 1, spread=0.1, up=0.0)
        self.update_debris(dt, g['y0'])
        y0 = g['y0']
        for b in self.eg_bits:
            if b[8]:
                continue
            b[4] -= 9.8 * dt
            b[0] += b[3] * dt
            b[1] += b[4] * dt
            b[2] += b[5] * dt
            if b[1] <= y0 + 0.02:
                b[1] = y0 + 0.02
                b[8] = True
        self.eg_bits = self.eg_bits[-300:]
        for m in self.msgs:
            m[1] -= dt
        self.msgs = [m for m in self.msgs if m[1] > 0]
        self.lv_low.exit_cage_y = y0 + max(0.0, t - 19.5) ** 1.6 * 0.8
        self.fade = max(clamp(1 - t / 0.25, 0, 1), clamp((t - 22.0) / 0.8, 0, 1))
        if t > END:
            self.fade = 1.0
            self.lv_low.exit_cage_y = None
            self.debris = []
            self.eg_bits = []
            self.inv_lose('rifle', 'revolver')
            self.start_exit3()

    def eg_blood(self, p, n, spread=1.0, up=1.5):
        for _ in range(n):
            self.eg_bits.append([p[0] + random.uniform(-0.1, 0.1), p[1], p[2] + random.uniform(-0.1, 0.1),
                                 random.uniform(-1, 1) * spread, random.uniform(0, 1) * up, random.uniform(-1, 1) * spread,
                                 random.uniform(0.025, 0.07), 'blood', False])

    # ------------------------------------------------------------------ drawing
    def eg_view_item(self, mesh, cam, fwd, side, fwd_d, down, kick=0.0):
        yaw = math.atan2(fwd[0], fwd[2])
        pitch = math.asin(clamp(fwd[1], -1, 1))
        p = self.held_pos(cam, yaw, pitch, side, fwd_d, down)
        return (mesh, T(*p) @ RY(yaw) @ RX(-pitch - kick))

    def render_elkgrab(self):
        t = self.eg_t
        g = self.eg
        lv = self.lv_low
        y0 = g['y0']
        parts, hands, headp = self.eg_pose(t)
        cam, fwd, roll = self.eg_camera(t, hands, headp)
        sh = self.shake
        if sh > 0:
            cam = tuple(c + random.uniform(-1, 1) * 0.05 * sh for c in cam)
        rx, rz = -fwd[2], fwd[0]
        ln = math.hypot(rx, rz) or 1.0
        up = (rx / ln * math.sin(roll), math.cos(roll), rz / ln * math.sin(roll))
        extras = list(self.debris_extras())
        flash = getattr(self, 'eg_flash', 0.0) > 0
        # the rifle: up at its face, the shot, then gone across the floor
        if 1.8 < t < 4.62:
            raise_ = sm(t, 1.8, 2.7) * (1 - sm(t, 3.5, 3.9))
            kick = 0.35 * math.exp(-(t - 3.2) * 8) if t > 3.2 else 0.0
            m, M = self.eg_view_item(self.m_rifle, cam, fwd, 0.9, 0.42, 0.24 + 0.55 * (1 - raise_), kick)
            extras.append((m, M))
            if flash and t < 3.4:
                extras.append((self.m_flash, M @ T(0, 0.025, 0.95)))
        elif t >= 4.62:
            k = sm(t, 4.62, 5.5)
            gx, gz = g['G']
            px, pz = g['gun']
            y = y0 + 0.06 + 1.6 * math.sin(math.pi * k) * (1 - k * 0.3)
            spin = 9.0 * k
            extras.append((self.m_rifle, T(lerp(gx, px, k), y, lerp(gz, pz, k)) @ RY(spin + 0.8) @ RZ(math.pi / 2 * k)
                           @ RX(0.3 * math.sin(spin))))
        # the revolver: emptied into it, taken, crushed
        if 8.6 < t < 12.3:
            raise_ = sm(t, 8.6, 9.0)
            kick = 0.0
            for s in SHOTS:
                if s <= t < s + 0.2:
                    kick = 0.45 * (1 - (t - s) / 0.2)
            m, M = self.eg_view_item(self.m_revolver, cam, fwd, 1, 0.42, 0.22 + 0.5 * (1 - raise_), kick)
            if t > 12.0:
                H = hands[-1]
                M = M * (1 - sm(t, 12.0, 12.3)) + (H @ RX(-1.2) @ S(1 / 1.19)) * sm(t, 12.0, 12.3)
            extras.append((m, M))
            if flash and 8.9 < t < 11.2:
                extras.append((self.m_flash, M @ T(0, 0.08, 0.3) @ S(0.5)))
        elif 12.3 <= t < 13.6:
            c = sm(t, 13.0, 13.4)
            H = hands[-1]
            extras.append((self.m_revolver, H @ RX(-1.2) @ RZ(0.8 * c) @ S(1 / 1.19 * (1 + 0.3 * c), 1 / 1.19 * (1 - 0.75 * c),
                                                                          1 / 1.19 * (1 - 0.4 * c))))
        bp = []
        for b in self.eg_bits:
            s = b[6]
            if b[8]:
                bp.append((b[7], T(b[0], b[1], b[2]) @ S(s * 2.4, 0.006, s * 2.0)))
            else:
                bp.append((b[7], T(b[0], b[1], b[2]) @ S(s, s * 1.6, s)))
        lights = [((cam[0] + 0.25, cam[1] - 0.35, cam[2] + 0.1), 7.0, self.lantern_col()),
                  ((g['ex'], y0 + 2.2, g['ez'] - 0.4), 7.0, (0.75, 0.6, 0.4)),
                  ((lerp(cam[0], headp[0], 0.5), headp[1] - 0.5, lerp(cam[2], headp[2], 0.5)), 9.0, (0.5, 0.42, 0.34))]
        if t < 3.5 or (8.6 < t < 12.3):
            if flash:
                lights.insert(0, ((cam[0] + fwd[0], cam[1] + fwd[1], cam[2] + fwd[2]), 14.0, (2.0, 1.6, 1.0)))
        self.draw_world3(lv, cam, fwd, lights, parts=[parts, bp], extras=extras, up=up)
        y = self.UH - 120
        for m in reversed(self.msgs):
            txt, tl, td = m
            al = int(clamp(tl / 0.4, 0, 1) * clamp((td - tl) / 0.3, 0, 1) * 255)
            self.blit_text(txt, self.f_msg, (225, 215, 200), (self.UW // 2, y), 'midtop', alpha=al)
            y -= 30
        bar = int(self.UH * 0.11)
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, 0, self.UW, bar))
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, self.UH - bar, self.UW, bar))

    def elkgrab_post(self):
        t = self.eg_t
        g = 0.0
        if 3.2 < t < 3.45 or 4.62 < t < 4.85 or 16.2 < t < 16.4:
            g = 1.0
        red = 0.5 if 4.62 < t < 5.0 else (0.12 if 5.0 < t < 15.4 else 0.0)
        return self.post_params({'fear': 0.6 if 0.5 < t < 18.7 else 0.2, 'glitch': g, 'red': red})
