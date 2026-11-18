"""Chapter 4 for the Game class: the floor gives way, the deep sewer, the
generators, the two gates and the fuses. Mixed into game.Game."""
import math
import random

import numpy as np
import pygame

from engine import Mesh, T, S, RX, RY, RZ
from textures import L, EMIS
from moose import pose_moose, unit_cube
import world as W
import chapter4 as C4
import lore


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def sm(t, a, b):
    k = clamp((t - a) / (b - a), 0, 1)
    return k * k * (3 - 2 * k)


def hole_mesh(depth=26.0):
    """The hole he smashes through the sewer floor: jagged rock all the way down, bent rebar
    at the top, chunks hanging off the sides, and a black gap in the floor seen from above."""
    from engine import MeshBuilder, RZ
    from textures import L
    import random as _r
    rng = _r.Random(44)
    b = MeshBuilder()
    y = 0.0
    k = 0
    while y > -depth:
        seg = rng.uniform(1.6, 2.6)
        r0 = 1.7 + rng.uniform(-0.3, 0.5) + 0.25 * k
        r1 = 1.7 + rng.uniform(-0.3, 0.5) + 0.25 * (k + 1)
        b.cylinder(min(r0, 3.4), min(r1, 3.4), seg, 9, L.CONCRETE, (0.42, 0.38, 0.34), m=T(0, y - seg, 0) @ RY(rng.random() * 6))
        y -= seg
        k += 1
    for _ in range(26):
        a = rng.random() * 6.28
        rr = rng.uniform(1.4, 2.6)
        yy = rng.uniform(-depth + 2, -0.4)
        s = rng.uniform(0.3, 0.9)
        b.box((math.cos(a) * rr, yy, math.sin(a) * rr), (s, s * 0.7, s), L.CONCRETE, (0.36, 0.33, 0.3),
              m=None)
    for _ in range(12):
        a = rng.random() * 6.28
        ln = rng.uniform(0.6, 1.4)
        m = T(math.cos(a) * 1.8, -0.15, math.sin(a) * 1.8) @ RY(-a) @ RZ(rng.uniform(0.6, 1.4))
        b.box((0, -ln / 2, 0), (0.04, ln, 0.04), L.METAL, (0.45, 0.32, 0.25), m=m)
    b.cylinder(1.75, 1.75, 0.02, 12, L.BLACK, (0.0, 0.0, 0.0), m=T(0, 0.015, 0), cap=True)
    return b.array()


def look(cam, tgt):
    f = (tgt[0] - cam[0], tgt[1] - cam[1], tgt[2] - cam[2])
    ln = math.sqrt(sum(v * v for v in f)) or 1.0
    return tuple(v / ln for v in f)


SEWER_ENV = {'ambient': (0.012, 0.013, 0.012), 'mooncol': (0.0, 0.0, 0.0), 'moondir': (0.3, -0.8, 0.5),
             'fog': (0.004, 0.006, 0.005), 'fogdens': 0.042}
HALL_ENV = {'ambient': (0.02, 0.019, 0.017), 'mooncol': (0.0, 0.0, 0.0), 'moondir': (0.3, -0.8, 0.5),
            'fog': (0.012, 0.011, 0.009), 'fogdens': 0.026}

# the Ch1 gallery, where it happens
GAL_X, GAL_Z = 8.0, 93.4          # you stop just inside the gallery
MOOSE_STOP_X = 11.9


class Ch4Mixin:
    # ------------------------------------------------------------------ setup
    def init_ch4(self, prog):
        self.lv4, data = C4.build()
        self.m_ch4 = Mesh(self.ctx, prog, data)
        self.m_gate1 = Mesh(self.ctx, prog, C4.gate_mesh(8.0, C4.GATE1_H, False))
        self.m_gate2 = Mesh(self.ctx, prog, C4.gate_mesh(12.0, C4.GATE2_H, True))
        self.m_fuse = Mesh(self.ctx, prog, C4.fuse_mesh())
        self.m_hole4 = Mesh(self.ctx, prog, hole_mesh())
        self.m_genlamp_on = Mesh(self.ctx, prog, unit_cube(L.GLOW + EMIS, (0.2, 1.0, 0.25)))
        self.m_genlamp_off = Mesh(self.ctx, prog, unit_cube(L.GLOW + EMIS, (0.5, 0.04, 0.02)))
        self.m_moose['dust'] = Mesh(self.ctx, prog, unit_cube(L.CONCRETE, (0.55, 0.53, 0.5)))

    def reset_ch4(self):
        lv = getattr(self, 'lv4', None)
        self.moose4 = None
        self.fuses_carried = 0
        self.fuses_in = 0
        self.in_hall = False
        self.debris = []
        self.shake = 0.0
        self.smash_sfx = []
        self.ending_next = None
        if lv is None:
            return
        for g in lv.gates.values():
            g.update(open=0.0, opening=False)
        for gen in lv.generators:
            gen.update(running=False, progress=0.0)
        for f in lv.fuses:
            f['taken'] = False
        lv.reset_reach()

    def gens_running(self):
        return sum(1 for g in self.lv4.generators if g['running'])

    # ------------------------------------------------------------------ the opening
    def start_ch4(self):
        """CHAPTER FOUR: back in the storm drain. He isn't dead."""
        self.new_game()
        self.chapter = 4
        self.progress['ch4'] = True
        self.set_resume(4, 'start')
        self.state = 'ch4open'
        self.c4_t = 0.0
        self.c4_fired = set()
        self.msgs = []
        self.debris = []
        self.set_mouse(False)
        self.audio.stop_all()
        self.audio.stop_loops()
        self.clock_t = (3 * 86400 + 5 * 3600 + 2 * 60) - (23 * 3600 + 58 * 60 + 7)

    def c4_fire(self, name, at):
        if self.c4_t >= at and name not in self.c4_fired:
            self.c4_fired.add(name)
            return True
        return False

    def burst_debris(self, x, y, z, n, up=4.0, spread=3.0, size=(0.08, 0.35)):
        for _ in range(n):
            a = random.random() * 2 * math.pi
            v = random.uniform(0.5, 1.0) * spread
            self.debris.append([x, y, z, math.cos(a) * v, random.uniform(0.4, 1.0) * up, math.sin(a) * v,
                                random.uniform(*size), random.random() * 6, random.uniform(-6, 6)])

    def update_debris(self, dt, floor):
        for d in self.debris:
            d[4] -= 9.8 * dt
            d[0] += d[3] * dt
            d[1] += d[4] * dt
            d[2] += d[5] * dt
            d[7] += d[8] * dt
            if floor is not None and d[1] < floor + d[6] / 2:
                d[1] = floor + d[6] / 2
                d[3] *= 0.5
                d[5] *= 0.5
                d[4] = abs(d[4]) * 0.2 if abs(d[4]) > 1.0 else 0.0
                d[8] *= 0.6
        self.debris = self.debris[-260:]

    def debris_extras(self):
        m = self.m_moose['dust']
        return [(m, T(d[0], d[1], d[2]) @ RY(d[7]) @ RX(d[7] * 0.7) @ S(d[6], d[6] * 0.6, d[6] * 0.8)) for d in self.debris]

    def update_ch4open(self, dt):
        self.c4_t += dt
        self.clock_t += dt
        t = self.c4_t
        A = self.audio
        A.loop('sewer_amb', 0.55 if 3.5 < t < 23.6 else (0.4 if t > 26.5 else 0.0))
        A.loop('winter_amb', 0.35 * clamp(1 - (t - 3.5) / 3.0, 0, 1) if t > 3.5 else 0.0)
        for at, text, dur in lore.CH4_OPEN_LINES:
            if self.c4_fire('l%.1f' % at, at):
                self.message(text, dur)
        for i in range(12):
            if self.c4_fire('st%d' % i, 3.8 + i * 0.45):
                A.play_rand('step_water' if i % 3 == 0 else 'step_conc', 3, 0.45)
        if self.c4_fire('thump', 9.4):
            A.play('mstep', 0.9, pan=0.6)
        for i in range(7):
            if self.c4_fire('ms%d' % i, 10.6 + i * 0.55):
                A.play('mstep', 0.5 + i * 0.07, pan=0.3)
        if self.c4_fire('call', 12.0):
            A.play('call_near', 0.6, pan=0.2)
        for at in (15.0, 16.6, 18.1):
            if self.c4_fire('crack%.1f' % at, at):
                A.play('crack', 1.0)
                self.shake = max(self.shake, 0.25)
        if self.c4_fire('heart', 15.2):
            A.play('heart', 0.8)
        if self.c4_fire('roar', 19.4):
            A.play('moose_roar', 1.0)
            A.play('stinger', 0.8)
            self.shake = max(self.shake, 0.6)
        if self.c4_fire('slam', 21.55):
            A.play('smash', 1.0)
            self.shake = 1.6
            self.burst_debris(GAL_X + 2.0, W.SEWER_FLOOR + 0.1, GAL_Z + 0.4, 60, up=6.0, spread=4.0)
        if self.c4_fire('give', 22.3):
            A.play('impact', 1.0)
            A.play('smash', 0.7)
            self.shake = 1.0
            for _ in range(40):
                self.debris.append([GAL_X + random.uniform(-2.5, 3.5), W.SEWER_FLOOR - random.uniform(0, 0.4),
                                    GAL_Z + random.uniform(-1.5, 2.5), 0.0, random.uniform(-1.0, 0.5), 0.0,
                                    random.uniform(0.3, 1.1), random.random() * 6, random.uniform(-2, 2)])
        if self.c4_fire('ring', 23.7):
            self.debris = []
            A.stop_all()
            A.play('static', 0.25)
        if self.c4_fire('land', 26.5):
            lv = self.lv4
            for _ in range(30):
                self.debris.append([lv.ox + random.uniform(41, 47), lv.y0 + random.uniform(6, 14),
                                    lv.oz + random.uniform(7, 13), 0, 0, 0, random.uniform(0.03, 0.1), random.random() * 6, 1.0])
        if self.c4_fire('getup', 29.6):
            A.play('crack', 0.6)
        if self.c4_fire('growl', 31.0):
            A.play('moose_roar', 0.55)
        for i in range(6):
            if self.c4_fire('run%d' % i, 31.8 + i * 0.32):
                A.play('mstep', 0.8 - i * 0.12, pan=0.5)
        self.shake = max(0.0, self.shake - dt * 1.6)
        floor = W.SEWER_FLOOR if t < 22.3 else (None if t < 26.5 else self.lv4.y0)
        self.update_debris(dt, floor)
        for m in self.msgs:
            m[1] -= dt
        self.msgs = [m for m in self.msgs if m[1] > 0]
        f = 1.0 if t < 3.5 else clamp(1 - (t - 3.5) / 0.8, 0, 1)
        f = max(f, clamp((t - 23.0) / 0.6, 0, 1) * clamp((26.9 - t) / 0.6, 0, 1))
        f = max(f, clamp((t - 33.8) / 0.7, 0, 1))
        self.fade = f
        if t > 34.6:
            self.fade = 0.0
            self.debris = []
            self.begin_ch4('start')

    def ch4open_moose(self, t):
        """The Moose Man during the opening: walks in, changes, raises both hands, slams."""
        x = 26.0 + (MOOSE_STOP_X - 26.0) * sm(t, 10.4, 14.6)
        z = GAL_Z + 1.4
        walking = 10.4 < t < 14.6
        shift = sm(t, 15.0, 19.6)
        jit = 0.0
        if 14.8 < t < 19.8:
            jit = 1.0 - abs(shift - 0.5) * 1.2
        rnd = random.Random(int(t * 14))
        kw = dict(hunch=0.5 + 0.25 * shift, shift=shift, t=self.time,
                  roll=rnd.uniform(-0.6, 0.6) * jit, head_yaw=rnd.uniform(-0.7, 0.7) * jit,
                  tilt=rnd.uniform(-0.12, 0.12) * jit, jaw=0.2 + 0.6 * jit + 0.5 * sm(t, 19.2, 19.6) * (1 - sm(t, 20.6, 21.0)))
        yaw = -math.pi / 2           # facing you, back toward the west
        # both hands up... and down
        up = sm(t, 20.0, 21.2) * 2.35
        down = sm(t, 21.25, 21.55)
        arms = up * (1 - down) + 0.25 * down
        kw['hunch'] = kw['hunch'] - 0.3 * sm(t, 20.0, 21.2) * (1 - down) + 0.7 * down
        kw['arms_up'] = arms
        kw['reach'] = 0.2 * down
        y = W.SEWER_FLOOR
        if t > 22.3:
            fall = (t - 22.3) ** 2 * 4.9
            y -= fall
            kw['tilt'] = kw.get('tilt', 0.0) + 0.3 * (t - 22.3)
        phase = (t - 10.4) * 4.2 if walking else 0.0
        return pose_moose(x, y, z, yaw, phase, 1.0 if walking else 0.0, **kw)[0]

    def render_ch4open(self):
        t = self.c4_t
        bars = True
        if t < 3.5:
            self.r.fbo.use()
            self.r.fbo.clear(0, 0, 0, 1)
            a = int(255 * clamp((t - 0.3) / 0.8, 0, 1) * clamp((3.4 - t) / 0.6, 0, 1))
            self.blit_text("CHAPTER FOUR", self.f_big, (210, 205, 198), (self.UW // 2, self.UH // 2 - 40), 'midtop', alpha=a)
            bars = False
        elif t < 23.6:
            sh = self.shake
            if t < 9.0:
                # down the drain, into the junction and up to the gallery
                k = sm(t, 3.5, 9.0)
                z = 76.0 + (GAL_Z - 76.0) * k
                x = GAL_X + 0.25 * math.sin(t * 1.3) * (1 - k)
                fl = self.world.floor_at(x, z)
                fl = W.SEWER_FLOOR if fl is None else fl
                cam = (x, fl + 1.58 + 0.04 * math.sin(t * 8.5), z)
                fwd = look(cam, (x, fl + 1.2, z + 6.0))
            else:
                yaw = (math.pi / 2) * sm(t, 9.6, 10.8)
                pitch = -0.05 + 0.28 * sm(t, 13.6, 15.0) + 0.15 * sm(t, 20.0, 21.0) - 0.45 * sm(t, 21.3, 21.8)
                cy = W.SEWER_FLOOR + 1.58 - 0.25 * sm(t, 14.0, 15.5)
                if t > 22.3:
                    ft = t - 22.3
                    cy -= ft * ft * 4.9
                    pitch -= 0.4 * ft
                cam = (GAL_X, cy, GAL_Z)
                fwd = (math.sin(yaw) * math.cos(pitch), math.sin(pitch), math.cos(yaw) * math.cos(pitch))
            cam = (cam[0] + random.uniform(-1, 1) * 0.05 * sh, cam[1] + random.uniform(-1, 1) * 0.05 * sh,
                   cam[2] + random.uniform(-1, 1) * 0.05 * sh)
            roll = 0.0 if t < 22.3 else 0.5 * (t - 22.3)
            up = (math.sin(roll) * 0.0 + 0.0, 1.0, 0.0)
            if roll:
                # roll the view about where you're looking
                rx, rz = -fwd[2], fwd[0]
                ln = math.hypot(rx, rz) or 1.0
                up = (rx / ln * math.sin(roll), math.cos(roll), rz / ln * math.sin(roll))
            parts = [self.ch4open_moose(t)] if t > 10.3 else []
            flash = 1.0 if not (21.6 < t < 21.8) else 0.1
            fpos = (cam[0] + 0.15, cam[1] - 0.15, cam[2])
            extras = self.debris_extras()
            if t > 21.5:
                # the floor gives way: a broken hole down through the rock, not the bottom of the world
                extras = extras + [(self.m_hole4, T(GAL_X, W.SEWER_FLOOR, GAL_Z))]
            self.draw_world(cam, fwd, flash, fpos, fwd, parts, up=up, extras=extras)
        elif t < 26.5:
            self.r.fbo.use()
            self.r.fbo.clear(0, 0, 0, 1)
        else:
            lv = self.lv4
            cx, cz = lv.center(21, 5)
            cam = (cx - 1.2, lv.y0 + 0.95 + 0.6 * sm(t, 33.0, 34.0), cz + 0.8)
            hx, hz = lv.ox + 44.0, lv.oz + 9.5
            mx0, mz0 = lv.center(23, 3)
            if t < 28.3:
                fwd = look(cam, (cx + 0.6, lv.y0 + 9.0, cz - 0.6))
            else:
                k = sm(t, 28.3, 29.4)
                a = look(cam, (cx + 0.6, lv.y0 + 9.0, cz - 0.6))
                b_ = look(cam, (mx0, lv.y0 + 0.6 + 1.8 * sm(t, 29.6, 31.0), mz0))
                fwd = tuple(a[i] + (b_[i] - a[i]) * k for i in range(3))
                if t > 31.6:
                    k2 = sm(t, 31.6, 33.0)
                    c_ = look(cam, (lv.ox + 60.0, lv.y0 + 1.5, lv.oz + 10.0))
                    fwd = tuple(fwd[i] + (c_[i] - fwd[i]) * k2 for i in range(3))
            # him: lying in the rubble, getting up, looking at you, running off east
            lie = 1.0 - sm(t, 29.6, 31.0)
            if t < 31.6:
                mx, mz = mx0, mz0
                yaw = math.atan2(cam[0] - mx, cam[2] - mz) + (1 - sm(t, 30.5, 31.2)) * 1.2
                parts = pose_moose(mx, lv.y0 + 0.15, mz, yaw, 0.0, 0.0, hunch=0.6, lie=lie, shift=1.0, t=self.time,
                                   jaw=0.6 * sm(t, 31.0, 31.3) * (1 - sm(t, 31.4, 31.7)))[0]
            else:
                k = (t - 31.6)
                path = [(mx0, mz0), (lv.ox + 52.0, lv.oz + 9.5), (lv.ox + 80.0, lv.oz + 9.5)]
                d = k * 6.0
                seg = 0
                l0 = math.hypot(path[1][0] - path[0][0], path[1][1] - path[0][1])
                if d < l0:
                    f_ = d / l0
                    mx = path[0][0] + (path[1][0] - path[0][0]) * f_
                    mz = path[0][1] + (path[1][1] - path[0][1]) * f_
                    yaw = math.atan2(path[1][0] - path[0][0], path[1][1] - path[0][1])
                else:
                    mx = path[1][0] + (d - l0)
                    mz = path[1][1]
                    yaw = math.pi / 2
                parts = pose_moose(mx, lv.y0, mz, yaw, d * 1.6, 1.0, hunch=0.75, shift=1.0, reach=0.3, t=self.time)[0]
            light = [((hx - 0.5, lv.y0 + 7.5, hz - 1.0), 16.0, (0.75, 0.78, 0.9)),
                     ((mx0 + 0.5, lv.y0 + 3.0, mz0 + 1.0), 7.0, (0.5, 0.5, 0.55)),
                     ((cam[0] + 0.3, lv.y0 + 0.5, cam[2] + 0.6), 6.0, self.lantern_col())]
            self.draw_world4(cam, fwd, light, parts=[parts], extras=self.debris_extras())
        if bars:
            y = self.UH - 120
            for m in reversed(self.msgs):
                txt, tl, td = m
                al = int(clamp(tl / 0.8, 0, 1) * clamp((td - tl) / 0.3, 0, 1) * 255)
                self.blit_text(txt, self.f_msg, (225, 215, 200), (self.UW // 2, y), 'midtop', alpha=al)
                y -= 30
            bar = int(self.UH * 0.11)
            pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, 0, self.UW, bar))
            pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, self.UH - bar, self.UW, bar))

    def ch4open_post(self):
        t = self.c4_t
        g = 0.0
        if 14.8 < t < 19.8:
            g = 0.35 + 0.5 * (random.random() < 0.25)
        if 21.5 < t < 21.9 or 22.3 < t < 22.5:
            g = 1.2
        red = 0.45 if 21.5 < t < 21.8 else 0.0
        return self.post_params({'fear': 0.25 if t > 10 else 0.05, 'glitch': g, 'red': red})

    # ------------------------------------------------------------------ gameplay
    def begin_ch4(self, where='start'):
        self.chapter = 4
        self.state = 'play'
        lv = self.lv4
        self.lv = lv
        self.flash_on = True
        self.fear = 0.0
        self.red = 0.0
        self.glitch = 0.0
        self.heart_t = 0.0
        self.debris = []
        p = self.player
        if where == 'start':
            sx, sz = lv.center(21, 5)
            p.reset(sx, lv.y0, sz, math.pi / 2)
            m = C4.MooseHunter(lv, lv.ox + 54.0, lv.oz + 9.5)
            m.state = 'leave'
            m.go_to(*lv.center(39, 6))
            m.grace = 10.0
            self.moose4 = m
            self.set_objective("Turn on the three backup generators. (0/3)")
            self.message("Three generators. The big gate needs power.", 4)
        else:
            sx, sz = lv.center(21, 21)
            p.reset(sx, lv.y0, sz, 0.0)
            ex, ez = lv.center(39, 5)
            m = C4.MooseHunter(lv, ex, ez)
            m.grace = 10.0
            self.moose4 = m
            self.in_hall = True
            self.set_objective("Find five fuses for the second gate. (0/5)")
        self.set_mouse(True)

    def continue_ch4_hall(self):
        lv = self.lv4
        self.chapter = 4
        for g in lv.generators:
            g.update(running=True, progress=1.0)
        lv.gates['G'].update(open=1.0, opening=True)
        lv.reset_reach()
        self.begin_ch4('hall')

    def respawn_ch4(self):
        lv = self.lv
        p = self.player
        sx, sz = lv.safe_hall if self.in_hall else lv.safe
        p.reset(sx, lv.y0, sz, 0.0)
        cand = [c for c in [(c, r) for r in range(lv.rows) for c in range(lv.cols) if lv.g[r][c] == '.']
                if math.hypot(lv.center(*c)[0] - sx, lv.center(*c)[1] - sz) > 32]
        lv.seed_cell = lv.cell_of(sx, sz)
        reach = set(lv.elk_cells()) if lv.open_cell(*lv.seed_cell, elk=True) else None
        good = [c for c in cand if reach is None or c in reach] or cand
        ex, ez = lv.center(*random.choice(good))
        self.moose4 = C4.MooseHunter(lv, ex, ez)
        self.moose4.grace = 8.0
        lv.reset_reach()
        self.flash_on = True
        self.fear = 0.0
        self.red = 0.0
        self.glitch = 0.0
        self.msgs = []
        self.message("You wake in the pipe. The fuses are still in your pocket.", 4) if self.fuses_carried else \
            self.message("You wake in the pipe. He's somewhere out there.", 4)
        self.state = 'play'
        self.set_mouse(True)

    def update_ch4(self, dt):
        p = self.player
        lv = self.lv
        self.clock_t += dt
        keys = self.keys()
        fx, fz = math.sin(p.yaw), math.cos(p.yaw)
        rx, rz = -math.cos(p.yaw), math.sin(p.yaw)
        p.fx, p.fz = fx, fz
        mv = (1 if keys[pygame.K_w] or keys[pygame.K_UP] else 0) - (1 if keys[pygame.K_s] or keys[pygame.K_DOWN] else 0)
        ms = (1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0) - (1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0)
        dx = fx * mv + rx * ms
        dz = fz * mv + rz * ms
        ln = math.hypot(dx, dz)
        if ln > 0:
            dx /= ln
            dz /= ln
        crouch = keys[pygame.K_LCTRL] or keys[pygame.K_c] or keys[pygame.K_RCTRL]
        p.crouch += ((1.0 if crouch else 0.0) - p.crouch) * min(1.0, dt * 8)
        sprint = (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) and ln > 0 and mv >= 0 and not crouch and not p.exhausted
        p.sprinting = sprint
        speed = 1.35 if crouch else (5.1 if sprint else 2.7)
        wet = lv.in_water(p.x, p.z)
        if wet:
            speed *= 0.8
        if sprint:
            p.stamina -= 21 * dt
            if p.stamina <= 0:
                p.stamina = 0
                p.exhausted = True
                self.message("You can't breathe. You have to stop.", 2.5)
        else:
            p.stamina = min(100.0, p.stamina + 13 * dt)
            if p.exhausted and p.stamina > 40:
                p.exhausted = False
        acc = min(1.0, dt * 10)
        p.vx += (dx * speed - p.vx) * acc
        p.vz += (dz * speed - p.vz) * acc
        nx, nz = lv.collide(p.x + p.vx * dt, p.z + p.vz * dt, 0.3, elk=False)
        moved = math.hypot(nx - p.x, nz - p.z)
        p.x, p.z = nx, nz
        p.y = lv.y0
        p.smooth_y += (p.y - p.smooth_y) * min(1.0, dt * 12)
        sp = moved / max(dt, 1e-4)
        p.bob_amt += (min(1.0, sp / 2.7) - p.bob_amt) * min(1.0, dt * 8)
        p.bob += moved * (2.0 if not sprint else 1.7)
        p.step_acc += moved
        stride = 0.55 if crouch else (1.0 if sprint else 0.78)
        if p.step_acc > stride:
            p.step_acc = 0.0
            vol = 0.25 if crouch else (0.85 if sprint else 0.5)
            if wet:
                self.audio.play_rand('step_water', 3, vol * 1.2)
                rad = 5.0 if crouch else (24 if sprint else 12)
            else:
                self.audio.play_rand('step_conc', 4, vol)
                rad = 2.5 if crouch else (18 if sprint else 8)
            if self.moose4:
                self.moose4.hear(p.x, p.z, rad)
        f = p.fwd()
        a = min(1.0, dt * 16)
        self.flash_dir = tuple(self.flash_dir[i] + (f[i] - self.flash_dir[i]) * a for i in range(3))
        self.flicker_t = max(0.0, self.flicker_t - dt)
        self.audio.set_listener(p.x, p.z, p.yaw)
        self.audio.loop('sewer_amb', 0.6)
        for k in ('winter_amb', 'forest_amb', 'title_amb'):
            self.audio.loop(k, 0.0)
        # generators: hold E on the starter cord
        pulling = False
        best = None
        for i, gen in enumerate(lv.generators):
            if gen['running']:
                d = math.hypot(gen['pos'][0] - p.x, gen['pos'][2] - p.z)
                if best is None or d < best[0]:
                    best = (d, gen)
                continue
            if self.focus == ('generator', i) and keys[pygame.K_e]:
                pulling = True
                gen['progress'] += dt / 2.2
                self.gen_noise_t = getattr(self, 'gen_noise_t', 0.0) - dt
                if self.gen_noise_t <= 0:
                    self.gen_noise_t = 0.55
                    self.audio.play('creak', 0.25)
                    if self.moose4:
                        self.moose4.hear(gen['pos'][0], gen['pos'][2], 32.0)
                if gen['progress'] >= 1.0:
                    pulling = False
                    self.mp_act('gen', i=i)
            elif not gen['running'] and gen['progress'] > 0 and self.focus != ('generator', i):
                gen['progress'] = max(0.0, gen['progress'] - dt * 0.6)     # the engine dies if you let go
        self.audio.loop('creak', 0.0)
        if best is not None:
            self.audio.loop3d('gen_hum', best[1]['base'][0], best[1]['base'][2], 26, 0.9)
        else:
            self.audio.loop('gen_hum', 0.0)
        # the gates
        for k, g in lv.gates.items():
            if g['opening'] and g['open'] < 1.0:
                was = g['open']
                g['open'] = min(1.0, g['open'] + dt / (5.5 if k == 'G' else 6.5))
                if was <= 0.7 < g['open']:
                    lv.reset_reach()
                if g['open'] >= 1.0:
                    self.audio.play('clunk', 0.8)
                    self.shake = 0.3
        # into the hall: checkpoint
        if not self.in_hall and lv.cell_of(p.x, p.z)[1] >= 20 and lv.gates['G']['open'] >= 1.0:
            self.in_hall = True
            self.set_resume(4, 'hall')
            self.message("It's enormous. Another gate at the far end -- even bigger.", 5)
            self.set_objective("Find five fuses for the second gate. They'll be in the sewers off the hall.")
        # through the second gate
        if self.mp_gather('exit4', lv.gates['H']['open'] >= 0.7 and lv.cell_of(p.x, p.z)[1] >= 40):
            self.start_exit4()
            return
        self.update_moose4(dt)
        if self.state != 'play':
            return
        self.focus = self.find_focus_ch4()
        self.obj_t = max(0.0, self.obj_t - dt)
        self.glitch += (0.0 - self.glitch) * min(1.0, dt * 20)
        self.shake = max(0.0, self.shake - dt * 2)

    def gen_done(self, i):
        lv = self.lv4
        gen = lv.generators[i]
        if gen['running']:
            return
        gen['running'] = True
        gen['progress'] = 1.0
        self.audio.play('gen_start', 1.0)
        if self.moose4 and self.mp_sim():
            self.moose4.hear(gen['pos'][0], gen['pos'][2], 45.0)
        n = self.gens_running()
        if n < 3:
            self.message("It coughs, and catches. The lamps on its circuit flicker on. (%d/3)" % n, 4)
            self.set_objective("Turn on the three backup generators. (%d/3)" % n)
        else:
            self.message("The last one catches. Somewhere ahead, the big gate starts to grind open.", 5)
            self.set_objective("The gate past the north tunnel is open. Go through.")
            lv.gates['G']['opening'] = True
            gx = (C4.gate_span(lv, 'G')[0] + C4.gate_span(lv, 'G')[1]) / 2
            self.audio.play3d('gate', gx, C4.gate_z(lv, 'G'), 90, 1.0)
            if self.moose4:
                self.audio.play3d('moose_roar', self.moose4.x, self.moose4.z, 90, 0.9)

    def fuses_added(self, n, x, z):
        lv = self.lv4
        if lv.gates['H']['opening']:
            return
        self.fuses_in = min(5, self.fuses_in + n)
        self.audio.play('fuse', 1.0)
        if self.fuses_in < 5:
            self.message("They click in. (%d/5)" % self.fuses_in, 3)
            self.set_objective("Find five fuses for the second gate. (%d/5)" % (self.fuses_in + self.fuses_carried))
        else:
            lv.gates['H']['opening'] = True
            gx = sum(C4.gate_span(lv, 'H')) / 2
            self.audio.play3d('gate', gx, C4.gate_z(lv, 'H'), 120, 1.0)
            self.message("The last fuse buzzes. The gate shudders and starts to lift.", 5)
            self.set_objective("GO. Get through the gate.")
            m = self.moose4
            if m is not None:
                # he heard that
                self.audio.play3d('moose_roar', m.x, m.z, 120, 1.0)
                if self.mp_sim():
                    m.grace = 0.0
                    m.state = 'investigate'
                    m.go_to(x, z)

    def update_moose4(self, dt):
        m = self.moose4
        p = self.player
        for s_ in self.smash_sfx:
            s_[0] -= dt
            if s_[0] <= 0:
                self.audio.play3d('smash', s_[1], s_[2], 40, 0.8)
                d = math.hypot(s_[1] - p.x, s_[2] - p.z)
                self.shake = max(self.shake, clamp(1.2 - d / 6, 0.2, 1.0))
                self.burst_debris(s_[1], self.lv.y0 + 1.8, s_[2], 10, up=2.0, spread=2.0, size=(0.04, 0.15))
        self.smash_sfx = [s_ for s_ in self.smash_sfx if s_[0] > 0]
        self.update_debris(dt, self.lv.y0)
        if m is None:
            self.fear += (0.0 - self.fear) * min(1.0, dt * 2)
            self.audio.loop('breath', 0)
            return
        tgt, lit = self.mp_ai_target(m, 'moose4')
        if self.mp_sim() and not self.mp_frozen('moose4') and not self.stunned('moose4'):
            m.update(dt, tgt, lit)
        for ev in self.mp_events('moose4', m):
            if ev == 'step':
                self.audio.play3d('mstep', m.x, m.z, 50, 1.0)
            elif ev == 'roar':
                self.audio.play3d('moose_roar', m.x, m.z, 80, 1.0)
                if self.mp_is_target('moose4'):
                    self.audio.play('stinger', 0.5)
            elif ev == 'smash':
                fx, fz = math.sin(m.yaw), math.cos(m.yaw)
                self.smash_sfx.append([0.55, m.x + fx * 1.6, m.z + fz * 1.6])
                if 'm4_smash' not in self.flags and self.mp_is_target('moose4'):
                    self.flags.add('m4_smash')
                    self.message("He can't get in. Stay still. Stay dark.", 4)
            elif ev == 'lost':
                if 'm4_lost' not in self.flags and self.mp_is_target('moose4'):
                    self.flags.add('m4_lost')
                    self.message("Don't move. Don't make a light.", 4)
            elif ev == 'leave':
                if 'm4_leave' not in self.flags and self.mp_is_target('moose4'):
                    self.flags.add('m4_leave')
                    self.message("He's moving on.", 3)
            elif ev == 'kill':
                self.mp_caught(tgt, 'moose4')
        m.events = []
        d = math.hypot(m.x - p.x, m.z - p.z)
        tf = clamp(1 - d / 26, 0, 1)
        mine = self.mp_is_target('moose4')
        if m.state == 'chase' and mine:
            tf = max(tf, 0.65)
        elif m.state == 'search' and mine:
            tf = max(tf, 0.75)
        self.fear += (tf - self.fear) * min(1.0, dt * 3)
        self.audio.loop3d('breath', m.x, m.z, 24, 1.0)
        if self.fear > 0.15:
            self.heart_t -= dt
            if self.heart_t <= 0:
                self.heart_t = 1.05 - 0.6 * self.fear
                self.audio.play('heart', 0.25 + 0.6 * self.fear)
        if self.fear > 0.4 and random.random() < dt * self.fear * 2.5:
            self.flicker_t = random.uniform(0.04, 0.2)

    def find_focus_ch4(self):
        p = self.player
        lv = self.lv
        ex, ey, ez = p.eye()
        f = p.fwd()
        cands = []
        for i, g in enumerate(lv.generators):
            if not g['running']:
                cands.append(('generator', i, g['pos'], 2.4))
        for i, fu in enumerate(lv.fuses):
            if not fu['taken']:
                cands.append(('fuse', i, fu['pos'], 2.3))
        if lv.fusebox:
            cands.append(('fusebox', 0, lv.fusebox['pos'], 2.4))
        best, bestd = None, -1
        for kind, key, pos, rng in cands:
            dx, dy, dz = pos[0] - ex, pos[1] - ey, pos[2] - ez
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if d < rng and d > 1e-3:
                dot = (dx * f[0] + dy * f[1] + dz * f[2]) / d
                if dot > (0.55 if d < 1.3 else 0.75) and dot > bestd:
                    best, bestd = (kind, key), dot
        return best

    def interact_ch4(self):
        if not self.focus:
            return
        kind, key = self.focus
        lv = self.lv
        if kind == 'fuse':
            fu = lv.fuses[key]
            fu['taken'] = True
            self.mp_tell('fuse_take', i=key)
            self.fuses_carried += 1
            self.audio.play('wood_pick', 0.5)
            have = self.fuses_carried + self.fuses_in
            self.message("A fuse. (%d/5)" % have, 3)
            self.set_objective(("Take the fuses to the box beside the second gate. (%d/5)" % have) if have >= 5
                               else "Find five fuses for the second gate. (%d/5)" % have)
        elif kind == 'fusebox':
            if lv.gates['H']['opening']:
                return
            if self.fuses_carried <= 0:
                self.message("The fuse box. %d of 5 slots filled." % self.fuses_in, 3)
                return
            n = self.fuses_carried
            self.fuses_carried = 0
            self.mp_act('fuse_in', n=n, x=round(self.player.x, 2), z=round(self.player.z, 2))
        elif kind == 'generator':
            pass            # held, not pressed

    # ------------------------------------------------------------------ through the second gate
    def start_exit4(self):
        self.state = 'exit4'
        self.x4_t = 0.0
        self.x4_fired = set()
        self.set_mouse(False)
        self.audio.loop('breath', 0)
        self.audio.loop('creak', 0)
        p = self.player
        self.x4_from = (p.x, p.z, p.yaw)

    def update_exit4(self, dt):
        self.x4_t += dt
        t = self.x4_t
        A = self.audio
        lv = self.lv4
        A.loop('sewer_amb', 0.5 * clamp(1 - (t - 7.0) / 1.5, 0, 1))
        A.loop('gen_hum', 0.0)
        g = lv.gates['H']
        if t > 1.2:
            g['open'] = max(0.0, 1.0 - (t - 1.2) ** 2 * 1.4)
        if 'slam' not in self.x4_fired and g['open'] <= 0.0 and t > 1.2:
            self.x4_fired.add('slam')
            A.play('smash', 1.0)
            self.shake = 1.0
        if 'roar' not in self.x4_fired and t > 3.8:
            self.x4_fired.add('roar')
            A.play('moose_roar', 0.9)
        if 'msg' not in self.x4_fired and t > 2.4:
            self.x4_fired.add('msg')
            self.message("He doesn't follow. He just watches.", 4)
        for i in range(5):
            if ('st%d' % i) not in self.x4_fired and t > 0.1 + i * 0.4 and i < 4:
                self.x4_fired.add('st%d' % i)
                A.play('mstep', 0.4 + 0.15 * i)
        self.shake = max(0.0, self.shake - dt * 1.5)
        for m in self.msgs:
            m[1] -= dt
        self.msgs = [m for m in self.msgs if m[1] > 0]
        self.fade = clamp((t - 7.0) / 1.4, 0, 1)
        if t > 8.6:
            self.fade = 0.0
            lv.gates['H']['open'] = 0.0
            self.progress['ch5'] = True
            self.progress.pop('resume', None)
            self.save_prog()
            self.ending_pages = lore.CH4_ENDING
            self.start_ending()
            self.ending_next = self.start_ch5

    def render_exit4(self):
        t = self.x4_t
        lv = self.lv4
        gz = C4.gate_z(lv, 'H')
        gx = sum(C4.gate_span(lv, 'H')) / 2
        px, pz, pyaw = self.x4_from
        k = sm(t, 0.0, 1.4)
        x = px + (gx - px) * k * 0.6
        z = pz + 2.4 * k
        # turn around to face the gate
        yaw = pyaw + ((math.pi - pyaw + math.pi) % (2 * math.pi) - math.pi) * sm(t, 0.2, 1.4)
        sh = self.shake
        cam = (x + random.uniform(-1, 1) * 0.04 * sh, lv.y0 + 1.6 + random.uniform(-1, 1) * 0.04 * sh, z)
        fwd = (math.sin(yaw) * 0.98, 0.12 * sm(t, 1.4, 4.0), math.cos(yaw) * 0.98)
        # he comes up to the bars and grips them, and looks at you
        a = sm(t, 1.0, 3.2)
        mx = gx + 1.5
        mz = gz - 14.0 + (14.0 - 1.4) * a
        walking = 1.0 < t < 3.2
        parts = pose_moose(mx, lv.y0, mz, 0.0, t * 6.0, 1.0 if walking else 0.0, hunch=0.55 - 0.25 * sm(t, 3.2, 3.8),
                           shift=1.0, arms_up=1.3 * sm(t, 3.0, 3.6), jaw=0.9 * sm(t, 3.8, 4.1) * (1 - sm(t, 5.6, 6.2)),
                           head_pitch=-0.2, t=self.time)[0]
        lp = self.held_lantern_pos(cam, yaw, 0.0)
        lights = [((lp[0], lp[1] + 0.2, lp[2]), 10.0, self.lantern_col())]
        self.draw_world4(cam, fwd, lights, parts=[parts], hold=(True, yaw, 0.0))
        y = self.UH - 120
        for m in reversed(self.msgs):
            txt, tl, td = m
            al = int(clamp(tl / 0.8, 0, 1) * clamp((td - tl) / 0.3, 0, 1) * 255)
            self.blit_text(txt, self.f_msg, (225, 215, 200), (self.UW // 2, y), 'midtop', alpha=al)
            y -= 30
        bar = int(self.UH * 0.11)
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, 0, self.UW, bar))
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, self.UH - bar, self.UW, bar))

    # ------------------------------------------------------------------ drawing
    def light_on(self, L_):
        g = L_['gen']
        lv = self.lv4
        if g is None:
            return True
        if g == 'all':
            return self.gens_running() >= 3
        if g == 'hall':
            return lv.gates['G']['opening']
        return lv.generators[g]['running']

    def draw_world4(self, cam, fwd, lights, parts=(), extras=(), hold=None, fov=None):
        r = self.r
        lv = self.lv4
        all_lights = self.mp_lights() + list(lights)
        parts = list(parts) + self.mp_parts(cam, fwd)
        cand = []
        for i, L_ in enumerate(lv.lights):
            if not self.light_on(L_):
                continue
            x, y, z = L_['pos']
            d = math.hypot(x - cam[0], z - cam[2])
            if d < L_['rad'] + 26:
                k = 1.9 * (0.86 + 0.14 * math.sin(self.time * 11 + i * 1.7))
                if L_['gen'] == 'hall' and lv.gates['G']['open'] < 1.0:
                    k *= 1.0 if math.sin(self.time * 23 + i * 5) > -0.2 else 0.1      # flickering on
                c = L_['col']
                cand.append((d, ((x, y, z), L_['rad'], (c[0] * k, c[1] * k, c[2] * k))))
        for gen in lv.generators:
            if gen['running']:
                x, y, z = gen['lamp']
                d = math.hypot(x - cam[0], z - cam[2])
                cand.append((d + 4, ((x, y + 0.2, z), 3.0, (0.15, 0.6, 0.18))))
        cand.sort(key=lambda o: o[0])
        all_lights += [c[1] for c in cand]
        hall = cam[2] > lv.oz + 39.0
        env = HALL_ENV if (hall and lv.gates['G']['opening']) else SEWER_ENV
        r.begin(cam, fwd, fov or self.settings['fov'], env, self.time, 0.0, cam, fwd, all_lights[:8])
        r.draw(self.m_ch4)
        for (x, y, z, g) in lv.bulbs:
            if self.light_on({'gen': g}):
                r.draw(self.m_bulb, model=T(x, y, z) @ S(0.09, 0.14, 0.09))
        for gen in lv.generators:
            x, y, z = gen['lamp']
            vib = 0.004 * math.sin(self.time * 90) if gen['running'] else 0.0
            r.draw(self.m_genlamp_on if gen['running'] else self.m_genlamp_off, model=T(x, y + vib, z) @ S(0.07, 0.07, 0.07))
        for which, mesh, h in (('G', self.m_gate1, C4.GATE1_H), ('H', self.m_gate2, C4.GATE2_H)):
            x0, x1 = C4.gate_span(lv, which)
            o = lv.gates[which]['open']
            shake = 0.01 * math.sin(self.time * 60) if 0 < o < 1 else 0.0
            r.draw(mesh, model=T((x0 + x1) / 2 + shake, lv.y0 + o * (h - 0.4), C4.gate_z(lv, which)))
        for fu in lv.fuses:
            if not fu['taken']:
                r.draw(self.m_fuse, model=T(*fu['pos']) @ RY(fu['yaw']))
        if lv.fusebox:
            p, yaw = lv.fusebox['pos'], lv.fusebox['yaw']
            for k in range(self.fuses_in):
                M = T(*p) @ RY(yaw) @ T(-0.44 + k * 0.22, 0.05, 0.07) @ RZ(math.pi / 2)
                r.draw(self.m_fuse, model=M)
        for mesh, M in extras:
            r.draw(mesh, model=M)
        for pl in parts:
            for key, M in pl:
                r.draw(self.m_moose[key], model=M)
        if hold and hold[0]:
            _, yaw, pitch = hold
            lp = self.held_lantern_pos(cam, yaw, pitch)
            M = T(*lp) @ RY(yaw) @ RZ(0.05 * math.sin(self.time * 2.1))
            if self.lantern_hand():
                r.draw(self.m_lantern, model=M)
                r.draw(self.m_lantern_lit if (self.flash_on or self.state != 'play') else self.m_lantern_off, model=M)
            self.draw_hand_items(r, cam, yaw, pitch)

    def moose4_parts(self):
        m = self.moose4
        chasing = m.state in ('chase', 'search')
        k = m.smash_t
        if k < 0.45:
            arms = 2.3 * sm(k, 0.0, 0.45)
        elif k < 0.6:
            arms = 2.3 - 2.0 * sm(k, 0.45, 0.6)
        else:
            arms = 0.3 * (1 - sm(k, 0.6, 1.1))
        hy = 0.0
        if m.state == 'search' and m.timer > 3.0:
            hy = 0.6 * math.sin(m.timer * 1.3)
        return pose_moose(m.x, m.y, m.z, m.yaw, m.phase * 1.7, m.amt, hunch=0.55 + (0.2 if chasing else 0.0),
                          reach=0.35 if m.state == 'chase' else 0.1, jaw=0.7 if chasing else 0.15,
                          head_yaw=hy, shift=1.0, arms_up=arms, t=self.time)[0]

    def moose4_face_parts(self, cam, yaw, dist):
        kw = dict(hunch=0.5, roll=random.uniform(-0.25, 0.25), jaw=0.85 + random.uniform(0, 0.25), reach=1.0,
                  head_pitch=-0.25, shift=1.0, t=self.time)
        _, head = pose_moose(0, 0, 0, yaw + math.pi, 0.0, 0.0, **kw)
        hx, hy, hz = float(head[0, 3]), float(head[1, 3]), float(head[2, 3])
        tx = cam[0] + math.sin(yaw) * dist
        tz = cam[2] + math.cos(yaw) * dist
        return pose_moose(tx - hx, cam[1] + 0.1 - hy, tz - hz, yaw + math.pi, 0.0, 0.0, **kw)[0]

    def render_ch4_scene(self):
        p = self.player
        cam = p.eye()
        sh = self.shake
        if sh > 0:
            cam = (cam[0] + random.uniform(-1, 1) * 0.04 * sh, cam[1] + random.uniform(-1, 1) * 0.04 * sh, cam[2])
        fwd = p.fwd()
        lp = self.held_lantern_pos(cam, p.yaw, p.pitch)
        lit = self.flash_on and self.flicker_t <= 0
        lights = [((lp[0], lp[1] + 0.2, lp[2]), 10.0, self.lantern_col())] if lit else []
        parts = [self.moose4_parts()] if self.moose4 is not None and not self.mp_hidden('moose4') else []
        self.draw_world4(cam, fwd, lights, parts=parts, extras=self.debris_extras(), hold=(True, p.yaw, p.pitch))

    def render_scare_ch4(self, cam, yaw, fwd, k):
        parts = [self.moose4_face_parts(cam, yaw, 1.9 - min(k, 1.0) * 0.5)]
        lp = (cam[0] + math.sin(yaw) * 0.4, cam[1] - 0.35, cam[2] + math.cos(yaw) * 0.4)
        self.draw_world4(cam, fwd, [(lp, 6.0, (1.5, 0.9, 0.45))], parts=parts)

    def hud_ch4(self):
        lv = self.lv4
        if not lv.gates['G']['opening']:
            return "GENERATORS %d/3" % self.gens_running()
        if not self.in_hall:
            return "THE GATE IS OPEN"
        if lv.gates['H']['opening']:
            return "THE SECOND GATE IS OPENING  -  GO"
        return "FUSES  inserted %d/5   carrying %d" % (self.fuses_in, self.fuses_carried)

    def focus_label_ch4(self, kind, key):
        if kind == 'generator':
            return "[Hold E] Pull the starter cord", self.lv4.generators[key]['progress']
        if kind == 'fuse':
            return "[E] Take the fuse", 0.0
        if kind == 'fusebox':
            if self.lv4.gates['H']['opening']:
                return "The fuse box (5/5)", 0.0
            if self.fuses_carried:
                return "[E] Put the fuses in (%d)" % self.fuses_carried, 0.0
            return "The fuse box (%d/5)" % self.fuses_in, 0.0
        return None, 0.0
