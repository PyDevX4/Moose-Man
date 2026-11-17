"""Chapter 5 for the Game class: the drain, the shotgun, The Beast, the gate.
Mixed into game.Game."""
import math
import random

import pygame

from engine import Mesh, T, S, RX, RY, RZ
from moose import pose_moose
import chapter4 as C4
import chapter5 as C5
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


SHELLS = 6
TUNNEL_ENV = {'ambient': (0.012, 0.011, 0.011), 'mooncol': (0.0, 0.0, 0.0), 'moondir': (0.3, -0.8, 0.5),
              'fog': (0.004, 0.004, 0.004), 'fogdens': 0.05}
FACTORY_ENV = {'ambient': (0.07, 0.058, 0.048), 'mooncol': (0.09, 0.075, 0.06), 'moondir': (0.2, -0.9, 0.3),
               'fog': (0.03, 0.022, 0.016), 'fogdens': 0.013}
DAWN_ENV = {'ambient': (0.32, 0.3, 0.32), 'mooncol': (0.6, 0.45, 0.35), 'moondir': (0.1, -0.5, -0.8),
            'fog': (0.6, 0.55, 0.56), 'fogdens': 0.012}

CS_LINES = [
    (1.2, "What is this place.", 2.6),
    (5.0, "He's dragging something.", 2.8),
    (9.6, "The Elk. The Goat Man.", 2.8),
    (13.4, "What is he doing to them", 3.0),
]


def mix_env(a, b, k):
    return {key: (tuple(a[key][i] + (b[key][i] - a[key][i]) * k for i in range(3)) if isinstance(a[key], tuple)
                  else a[key] + (b[key] - a[key]) * k) for key in a}


class Ch5Mixin:
    # ------------------------------------------------------------------ setup
    def init_ch5(self, prog):
        self.w5 = C5.World5()
        self.m_ch5 = Mesh(self.ctx, prog, self.w5.build())
        self.m_gate5 = Mesh(self.ctx, prog, C4.gate_mesh(C5.GATE_HW * 2, C5.GATE_H, True))
        self.m_grate5 = Mesh(self.ctx, prog, C4.gate_mesh(C5.TUN_HW * 2, C5.TUN_H, False))
        self.m_shotgun = Mesh(self.ctx, prog, C5.shotgun_mesh())
        self.m_pump = Mesh(self.ctx, prog, C5.pump_mesh())
        self.m_flash = Mesh(self.ctx, prog, C5.flash_mesh())
        self.m_marker = Mesh(self.ctx, prog, C5.marker_mesh())

    def reset_ch5(self):
        self.has_shotgun = False
        self.shells = SHELLS
        self.pump_t = 0.0
        self.reload_t = -1.0
        self.muzzle_t = 0.0
        self.kick = 0.0
        self.hp5 = 100.0
        self.regen_t = 0.0
        self.hurt_flash = 0.0
        self.hitmark_t = 0.0
        self.beast = None
        self.proj = []
        self.markers = []
        self.c5_phase = 'drain'
        self.won_t = -1.0
        self.charge_hit = False
        self.fade_in5 = 0.0
        w = getattr(self, 'w5', None)
        if w is not None:
            w.gate_open = 0.0
            w.sealed = False

    # ------------------------------------------------------------------ start: a card, then the drain
    def start_ch5(self):
        self.new_game()
        self.chapter = 5
        self.progress['ch5'] = True
        self.set_resume(5, 'start')
        self.state = 'card5'
        self.card_t = 0.0
        self.set_mouse(False)
        self.audio.stop_all()
        self.audio.stop_loops()

    def update_card5(self, dt):
        self.card_t += dt
        self.audio.loop('sewer_amb', 0.3 * clamp((self.card_t - 2.5) / 1.5, 0, 1))
        if self.card_t > 4.0:
            self.begin_ch5('start')

    def draw_card5(self):
        t = self.card_t
        a = int(255 * clamp((t - 0.3) / 0.8, 0, 1) * clamp((3.8 - t) / 0.6, 0, 1))
        self.blit_text("CHAPTER FIVE", self.f_big, (210, 205, 198), (self.UW // 2, self.UH // 2 - 40), 'midtop', alpha=a)

    def begin_ch5(self, where='start'):
        self.chapter = 5
        self.state = 'play'
        w = self.w5
        p = self.player
        self.flash_on = True
        self.fear = self.red = self.glitch = 0.0
        self.blood = []
        self.debris = []
        self.proj = []
        self.markers = []
        self.hp5 = 100.0
        self.shells = SHELLS
        self.pump_t = 0.0
        self.reload_t = -1.0
        if where == 'start':
            p.reset(0.0, 0.0, 2.2, 0.0)
            self.c5_phase = 'drain'
            w.sealed = False
            self.fade_in5 = 1.4
            self.set_objective("Keep going.")
            self.message("Another drain. Smaller. It goes on a long way.", 4)
        else:
            self.has_shotgun = True
            w.sealed = True
            w.gate_open = 0.0
            p.reset(0.0, 0.0, 49.0, 0.0)
            self.c5_phase = 'boss'
            self.won_t = -1.0
            self.beast = C5.Beast(C5.BEAST_HOME[0], C5.BEAST_HOME[1], math.pi)
            self.beast.cool = 3.0
            if self.mp_on():
                # tougher with more of you
                self.beast.MAX_HP = self.beast.hp = C5.Beast.MAX_HP * (1.0 + 0.55 * (self.mp_count() - 1))
            self.set_objective("Kill it.  [Left mouse] fire   [R] reload")
        self.set_mouse(True)

    def respawn_ch5(self):
        self.msgs = []
        self.begin_ch5('boss' if self.c5_phase in ('boss', 'won') else 'start')
        if self.c5_phase == 'boss':
            self.message("Get up. It's still here.", 3)

    # ------------------------------------------------------------------ the cutscene: The Beast
    def start_beast_cs(self):
        self.state = 'beastcs'
        self.bc_t = 0.0
        self.bc_fired = set()
        self.has_shotgun = True
        self.set_mouse(False)
        self.audio.loop('breath', 0)
        p = self.player
        self.bc_cam0 = (p.x, p.z, p.yaw, p.pitch)

    def bc_fire(self, name, at):
        if self.bc_t >= at and name not in self.bc_fired:
            self.bc_fired.add(name)
            return True
        return False

    def update_beast_cs(self, dt):
        self.bc_t += dt
        t = self.bc_t
        A = self.audio
        A.loop('sewer_amb', 0.5)
        for at, text, dur in CS_LINES:
            if self.bc_fire('l%.1f' % at, at):
                self.message(text, dur)
        if self.bc_fire('grate', 0.6):
            self.w5.sealed = True
            A.play('smash', 0.9)
            self.shake = 0.6
        for i in range(12):
            if self.bc_fire('ms%d' % i, 1.6 + i * 0.62):
                A.play3d('mstep', 40 - i * 3.3, 88, 70, 1.0)
                A.play3d('wood_drop', 44 - i * 3.3, 89, 60, 0.4)
        if self.bc_fire('roar1', 11.0):
            A.play('moose_roar', 0.9)
        for at in (13.0, 14.6, 16.1, 17.6, 18.8):
            if self.bc_fire('cr%.1f' % at, at):
                A.play('crack', 1.0)
                A.play('screech', 0.25)
                self.shake = max(self.shake, 0.5)
                bx, bz = C5.BEAST_HOME
                self.spawn_blood(bx + random.uniform(-4, 4), random.uniform(2, 7), bz + random.uniform(-3, 3), 26,
                                 vel=(0, 3.0, 0), spread=3.0, size=(0.06, 0.16))
        if self.bc_fire('big', 19.8):
            A.play('moose_roar', 1.0)
            A.play('elk_bugle', 0.9)
            A.play('goat_roar', 0.9)
            A.play('stinger', 1.0)
            self.shake = 1.4
        self.shake = max(0.0, self.shake - dt * 1.2)
        self.update_blood(dt)
        for m in self.msgs:
            m[1] -= dt
        self.msgs = [m for m in self.msgs if m[1] > 0]
        self.fade = clamp((t - 24.2) / 0.5, 0, 1) * clamp((25.6 - t) / 0.5, 0, 1)
        if t > 25.0 and 'go' not in self.bc_fired:
            self.bc_fired.add('go')
            self.set_resume(5, 'boss')
            self.begin_ch5('boss')
            self.fade_in5 = 0.6
            self.message("THE BEAST", 3)

    def beast_cs_parts(self, t):
        bx, bz = C5.BEAST_HOME
        if t < 9.0:
            # he drags them in through the east door
            k = sm(t, 1.4, 9.0)
            mx = 42.0 + (bx - 42.0) * k
            walking = 1.4 < t < 9.0
            moose = pose_moose(mx, 0, bz, -math.pi / 2, (t - 1.4) * 3.6, 1.0 if walking else 0.0, hunch=0.6,
                               shift=1.0, reach=0.4, t=self.time)[0]
            bodies, _ = C5.pose_beast(mx, bz, math.pi, merge=0.0, t=self.time, who='eg')
            return moose + bodies, None
        if t < 11.0:
            yaw = -math.pi / 2 + (-math.pi / 2) * sm(t, 9.2, 10.6)
            moose = pose_moose(bx, 0, bz, yaw, 0.0, 0.0, hunch=0.55, shift=1.0, t=self.time)[0]
            bodies, _ = C5.pose_beast(bx, bz, math.pi, merge=0.0, t=self.time, who='eg')
            return moose + bodies, None
        k = sm(t, 12.5, 19.5)
        roar = sm(t, 11.0, 11.5) * (1 - sm(t, 12.0, 12.5)) + sm(t, 19.8, 20.3) * (1 - sm(t, 22.5, 23.5))
        jit = 1.0 if 12.5 < t < 19.6 else 0.0
        parts, info = C5.pose_beast(bx, bz, math.pi, merge=k, roar=roar, jitter=jit, t=self.time, slam=1.2 * sm(t, 12.0, 13.0) * (1 - k))
        return parts, info

    def render_beast_cs(self):
        t = self.bc_t
        px, pz, pyaw, ppitch = self.bc_cam0
        bx, bz = C5.BEAST_HOME
        sh = self.shake
        cam = (px + random.uniform(-1, 1) * 0.05 * sh, 1.6 + random.uniform(-1, 1) * 0.05 * sh, pz)
        if t < 9.0:
            k = sm(t, 1.4, 9.0)
            mx = 42.0 + (bx - 42.0) * k
            tgt = (0.0, 2.0, 80.0) if t < 2.5 else (mx, 2.4, bz)
            if t < 4.0:
                a = look(cam, (0.0, 2.0, 80.0))
                b_ = look(cam, (mx, 2.4, bz))
                kk = sm(t, 2.5, 4.0)
                fwd = tuple(a[i] + (b_[i] - a[i]) * kk for i in range(3))
            else:
                fwd = look(cam, tgt)
        else:
            k = sm(t, 12.5, 19.5)
            fwd = look(cam, (bx, 2.4 + 5.0 * k, bz))
        if t < 1.0:
            # first: turn round at the grate slamming shut behind you
            fwd0 = (math.sin(pyaw) * math.cos(ppitch), math.sin(ppitch), math.cos(pyaw) * math.cos(ppitch))
            fwd = tuple(fwd0[i] + (fwd[i] - fwd0[i]) * sm(t, 0.0, 1.0) for i in range(3))
        parts, _ = self.beast_cs_parts(t)
        mx_ = 42.0 + (bx - 42.0) * sm(t, 1.4, 9.0)
        self.spot5 = [(mx_ + 2.0, bz - 3.0)]
        lp = self.held_lantern_pos(cam, math.atan2(fwd[0], fwd[2]), 0.0)
        self.draw_world5(cam, fwd, [((lp[0], lp[1] + 0.2, lp[2]), 9.0, self.lantern_col())], parts=[parts])
        self.spot5 = []
        if t > 20.8:
            a = int(255 * clamp((t - 20.8) / 0.8, 0, 1) * clamp((24.4 - t) / 0.6, 0, 1))
            self.blit_text("THE BEAST", self.f_title, (180, 20, 15), (self.UW // 2, self.UH // 2 - 90), 'midtop', alpha=a)
        y = self.UH - 120
        for m in reversed(self.msgs):
            txt, tl, td = m
            al = int(clamp(tl / 0.8, 0, 1) * clamp((td - tl) / 0.3, 0, 1) * 255)
            self.blit_text(txt, self.f_msg, (225, 215, 200), (self.UW // 2, y), 'midtop', alpha=al)
            y -= 30
        bar = int(self.UH * 0.11)
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, 0, self.UW, bar))
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, self.UH - bar, self.UW, bar))

    def beast_cs_post(self):
        t = self.bc_t
        g = 0.0
        if 12.5 < t < 19.6:
            g = 0.3 + (0.9 if random.random() < 0.2 else 0.0)
        if 19.5 < t < 19.9:
            g = 1.4
        return self.post_params({'fear': 0.35 if t > 9 else 0.1, 'glitch': g, 'red': 0.4 if 19.6 < t < 20.0 else 0.0})

    # ------------------------------------------------------------------ play
    def hurt5(self, amount, src=None):
        if self.state != 'play' or self.hp5 <= 0:
            return
        self.hp5 -= amount
        self.hurt_flash = min(1.0, 0.35 + amount / 50.0)
        self.regen_t = 5.0
        self.shake = max(self.shake, 0.5 + amount / 60.0)
        self.audio.play('impact', 0.8)
        self.audio.play('heart', 0.7)
        p = self.player
        self.spawn_blood(p.x, 1.2, p.z, 10, spread=1.2)
        if self.hp5 <= 0:
            self.hp5 = 0.0
            self.kill()

    def fire_shotgun(self):
        if not self.has_shotgun or self.state != 'play' or self.pump_t > 0:
            return
        if self.shells <= 0:
            self.audio.play('click', 0.7)
            self.start_reload()
            return
        self.reload_t = -1.0
        self.shells -= 1
        self.pump_t = 0.9
        self.muzzle_t = 0.07
        self.kick = 1.0
        self.shake = max(self.shake, 0.25)
        self.audio.play('rifle', 0.85)
        p = self.player
        cam = p.eye()
        f = p.fwd()
        b = self.beast
        hit_any = False
        if b is not None and not b.dead:
            _, info = b.parts(self.time)
            right = (-math.cos(p.yaw), 0.0, math.sin(p.yaw))
            up = (right[1] * f[2] - right[2] * f[1], right[2] * f[0] - right[0] * f[2], right[0] * f[1] - right[1] * f[0])
            total = 0.0
            for i in range(9):
                a = random.uniform(0, 2 * math.pi)
                rr = 0.06 * math.sqrt(random.random())
                d = tuple(f[j] + (right[j] * math.cos(a) + up[j] * math.sin(a)) * rr for j in range(3))
                ln = math.sqrt(sum(v * v for v in d))
                d = tuple(v / ln for v in d)
                best = None
                for hc in info['heads']:
                    tt = C5.ray_sphere(cam, d, hc, 1.25)
                    if tt is not None and (best is None or tt < best[0]):
                        best = (tt, 2.6)
                for c, r in info['body']:
                    tt = C5.ray_sphere(cam, d, c, r)
                    if tt is not None and (best is None or tt < best[0] - 0.3):
                        best = (tt, 1.0)
                if best is None:
                    continue
                dist, mult = best
                fall = clamp(1.0 - (dist - 14.0) / 34.0, 0.25, 1.0)
                total += 1.25 * mult * fall
                hp = tuple(cam[j] + d[j] * dist for j in range(3))
                self.spawn_blood(hp[0], hp[1], hp[2], 3, vel=(-d[0] * 2, 1.5, -d[2] * 2), spread=1.8, size=(0.05, 0.12))
                hit_any = True
            if total > 0:
                if self.mp_sim():
                    b.damage(total)
                else:
                    self.mp_tell('beast_dmg', amt=round(total, 2))
                self.audio.play3d('tackle', b.x, b.z, 80, 0.5)
        if hit_any:
            self.hitmark_t = 0.18

    def start_reload(self):
        if self.shells < SHELLS and self.reload_t < 0:
            self.reload_t = 0.55

    def update_ch5(self, dt):
        p = self.player
        w = self.w5
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
        nx, nz = w.collide(p.x + p.vx * dt, p.z + p.vz * dt, 0.3)
        b = self.beast
        if b is not None and not (b.state == 'dead' and b.fall >= 1.0):
            # you can't walk through it
            ddx, ddz = nx - b.x, nz - b.z
            d = math.hypot(ddx, ddz)
            if 1e-4 < d < 3.6:
                nx, nz = w.collide(b.x + ddx / d * 3.6, b.z + ddz / d * 3.6, 0.3)
        moved = math.hypot(nx - p.x, nz - p.z)
        p.x, p.z = nx, nz
        p.y = clamp((p.z - C5.HALL_Z1 - 4) * 0.12, 0, 6) if p.z > C5.HALL_Z1 else 0.0
        p.smooth_y += (p.y - p.smooth_y) * min(1.0, dt * 12)
        sp = moved / max(dt, 1e-4)
        p.bob_amt += (min(1.0, sp / 2.7) - p.bob_amt) * min(1.0, dt * 8)
        p.bob += moved * (2.0 if not sprint else 1.7)
        p.step_acc += moved
        stride = 0.55 if crouch else (1.0 if sprint else 0.78)
        if p.step_acc > stride:
            p.step_acc = 0.0
            vol = 0.25 if crouch else (0.85 if sprint else 0.5)
            if p.z > C5.HALL_Z1:
                self.audio.play_rand('step_snow', 4, vol)
            elif w.in_tunnel(p.z) and abs(p.x) < 0.4:
                self.audio.play_rand('step_water', 3, vol)
            else:
                self.audio.play_rand('step_conc', 4, vol)
        f = p.fwd()
        a = min(1.0, dt * 16)
        self.flash_dir = tuple(self.flash_dir[i] + (f[i] - self.flash_dir[i]) * a for i in range(3))
        self.flicker_t = max(0.0, self.flicker_t - dt)
        self.audio.set_listener(p.x, p.z, p.yaw)
        self.audio.loop('sewer_amb', 0.55 if p.z < C5.HALL_Z1 else 0.0)
        self.audio.loop('winter_amb', clamp((p.z - C5.HALL_Z1 + 10) / 20, 0, 1) * w.gate_open * 0.8)
        for k_ in ('forest_amb', 'title_amb', 'gen_hum', 'creak'):
            self.audio.loop(k_, 0.0)
        # the gun
        self.pump_t = max(0.0, self.pump_t - dt)
        if 0 < self.pump_t < 0.5 and not getattr(self, '_pumped', False):
            self._pumped = True
            self.audio.play('bolt', 0.5)
        if self.pump_t <= 0:
            self._pumped = False
        self.muzzle_t = max(0.0, self.muzzle_t - dt)
        self.kick = max(0.0, self.kick - dt * 5)
        self.hitmark_t = max(0.0, self.hitmark_t - dt)
        if self.reload_t >= 0 and self.pump_t <= 0:
            self.reload_t -= dt
            if self.reload_t < 0:
                self.shells += 1
                self.audio.play('click', 0.6)
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
        # the drain
        if self.c5_phase == 'drain':
            if not self.has_shotgun and self.focus == ('shotgun', 0) and keys[pygame.K_e]:
                pass
            if self.mp_gather('factory', p.z > C5.TUN_Z1 + 1.8):
                self.start_beast_cs()
                return
        elif self.c5_phase == 'boss':
            self.update_beast(dt)
            if self.state != 'play':
                return
        elif self.c5_phase == 'won':
            self.won_t += dt
            if self.won_t > 2.5:
                if w.gate_open == 0.0:
                    gx = 0.0
                    self.audio.play3d('gate', gx, C5.HALL_Z1, 140, 1.0)
                    self.message("The gate. It's opening. There's light behind it.", 5)
                    self.set_objective("Get out.")
                w.gate_open = min(1.0, w.gate_open + dt / 7.0)
            if self.mp_gather('exit5', p.z > C5.HALL_Z1 + 7.0):
                self.start_exit5()
                return
            self.update_debris(dt, 0.0)
        self.update_blood(dt)
        self.focus = self.find_focus_ch5()
        self.obj_t = max(0.0, self.obj_t - dt)
        self.glitch += (0.0 - self.glitch) * min(1.0, dt * 20)

    def update_beast(self, dt):
        b = self.beast
        p = self.player
        w = self.w5
        tgt = self.mp_ai_target(b, 'beast')[0]
        if self.mp_sim():
            b.update(dt, tgt.x, tgt.z, tgt.vx, tgt.vz, w)
            self.resolve_beast_events(b, tgt)
        for ev in self.mp_events('beast', b):
            kind = ev[0]
            if kind == 'step':
                d = math.hypot(b.x - p.x, b.z - p.z)
                self.audio.play3d('mstep', b.x, b.z, 90, 1.0)
                self.shake = max(self.shake, clamp(0.6 - d / 40, 0.0, 0.6))
            elif kind == 'slam':
                # it brings its hands down wherever you are, inside its reach
                sx, sz = ev[1], ev[2]
                self.audio.play3d('smash', sx, sz, 90, 1.0)
                d = math.hypot(p.x - sx, p.z - sz)
                self.shake = max(self.shake, clamp(1.4 - d / 25, 0.3, 1.4))
                self.burst_debris(sx, 0.2, sz, 40, up=6.0, spread=5.0, size=(0.1, 0.45))
                if d < 5.2:
                    self.hurt5(40 * (1 - d / 10.0))
            elif kind == 'throw':
                hx, hy, hz, tx, tz, tof = ev[1:7]
                vy = (0.0 - hy + 0.5 * 12.0 * tof * tof) / tof
                self.proj.append([hx, hy, hz, (tx - hx) / tof, vy, (tz - hz) / tof, random.random() * 6])
                self.markers.append([tx, tz, tof, 2.6, 'land'])
                self.audio.play3d('goat_roar', b.x, b.z, 80, 0.6)
            elif kind in ('roar_short', 'charge'):
                self.audio.play3d('moose_roar', b.x, b.z, 120, 0.9 if kind == 'charge' else 0.6)
                self.charge_hit = False
            elif kind == 'wall':
                self.audio.play3d('smash', b.x, b.z, 100, 1.0)
                self.shake = max(self.shake, 1.0)
                self.burst_debris(b.x + math.sin(b.yaw) * 4, 2.0, b.z + math.cos(b.yaw) * 4, 30, up=4.0, spread=4.0)
                if 'stun_tip' not in self.flags:
                    self.flags.add('stun_tip')
                    self.message("It ran into the wall. It's stunned -- shoot it NOW.", 4)
            elif kind == 'roar':
                self.audio.play('moose_roar', 1.0)
                self.audio.play('elk_bugle', 0.7)
                self.shake = max(self.shake, 0.8)
                for (x, z, dl) in ev[1]:
                    self.markers.append([x, z, dl, 2.4, 'rock'])
                if 'rain_tip' not in self.flags:
                    self.flags.add('rain_tip')
                    self.message("The roof is coming down -- get out from under the red!", 3.5)
            elif kind == 'enrage':
                self.message("It's bleeding. It's angry now.", 3)
                self.audio.play('stinger', 0.8)
            elif kind == 'die':
                self.audio.play('moose_roar', 1.0)
                self.audio.play('elk_bugle', 1.0)
                self.audio.play('goat_roar', 1.0)
                self.message("It's going down.", 3)
                self.markers = []
            elif kind == 'crash':
                self.audio.play('smash', 1.0)
                self.audio.play('impact', 1.0)
                self.shake = 1.6
                self.burst_debris(b.x - math.cos(b.yaw) * 4, 0.5, b.z + math.sin(b.yaw) * 4, 60, up=6.0, spread=6.0)
                for _ in range(5):
                    self.spawn_blood(b.x + random.uniform(-5, 5), random.uniform(1, 5), b.z + random.uniform(-5, 5), 30,
                                     spread=3.0, size=(0.08, 0.2))
        b.events = []
        if b.state == 'dead' and self.c5_phase == 'boss':
            self.c5_phase = 'won'
            self.won_t = 0.0
            self.progress.pop('resume', None)
            self.save_prog()
            self.message("It's dead. It's finally dead.", 4)
            return
        # the charge
        d = math.hypot(b.x - p.x, b.z - p.z)
        if b.state == 'charge' and d < 4.6 and not self.charge_hit:
            self.charge_hit = True
            cx, cz = b.charge_dir
            p.vx += cx * 9.0 + (p.x - b.x) / max(d, 0.1) * 6.0
            p.vz += cz * 9.0 + (p.z - b.z) / max(d, 0.1) * 6.0
            self.hurt5(42)
            if self.state != 'play':
                return
        # things it threw, and the roof
        for pr in self.proj:
            pr[4] -= 12.0 * dt
            pr[0] += pr[3] * dt
            pr[1] += pr[4] * dt
            pr[2] += pr[5] * dt
            pr[6] += dt * 8
        landed = [pr for pr in self.proj if pr[1] <= 0.2]
        self.proj = [pr for pr in self.proj if pr[1] > 0.2]
        for pr in landed:
            self.audio.play3d('impact', pr[0], pr[2], 50, 0.9)
            self.spawn_blood(pr[0], 0.3, pr[2], 24, spread=3.0, size=(0.06, 0.16))
            if math.hypot(p.x - pr[0], p.z - pr[2]) < 2.6:
                self.hurt5(22)
                if self.state != 'play':
                    return
        keep = []
        for m in self.markers:
            m[2] -= dt
            if m[2] <= 0:
                if m[4] == 'rock':
                    self.audio.play3d('smash', m[0], m[1], 60, 0.7)
                    self.burst_debris(m[0], 0.3, m[1], 14, up=3.0, spread=3.0, size=(0.15, 0.6))
                    if math.hypot(p.x - m[0], p.z - m[1]) < m[3]:
                        self.hurt5(26)
                        if self.state != 'play':
                            return
            else:
                keep.append(m)
        self.markers = keep
        self.update_debris(dt, 0.0)
        tf = clamp(1 - d / 40, 0.3, 1.0)
        self.fear += (tf - self.fear) * min(1.0, dt * 2)

    def resolve_beast_events(self, b, tgt):
        """Pin each attack to a place in the world, aimed at whoever it's after,
        so everyone's machine sees it land in the same spot."""
        w = self.w5
        out = []
        info = None
        for ev in b.events:
            kind = ev[0]
            if kind == 'slam':
                fx_, fz_ = math.sin(b.yaw), math.cos(b.yaw)
                along = clamp((tgt.x - b.x) * fx_ + (tgt.z - b.z) * fz_, 3.5, 9.5)
                ev = ('slam', round(b.x + fx_ * along, 2), round(b.z + fz_ * along, 2))
            elif kind == 'throw':
                if info is None:
                    _, info = b.parts(self.time)
                hx, hy, hz = info['goat_hand']
                dist = math.hypot(tgt.x - hx, tgt.z - hz)
                tof = clamp(dist / 15.0, 0.9, 2.3)
                tx, tz = tgt.x + tgt.vx * tof * 0.7, tgt.z + tgt.vz * tof * 0.7
                tx, tz = w.collide(tx, tz, 0.5)
                ev = ('throw', round(hx, 2), round(hy, 2), round(hz, 2), round(tx, 2), round(tz, 2), round(tof, 3))
            elif kind == 'roar':
                pts = []
                people = [(tgt.x, tgt.z)]
                if self.mp_on():
                    people = [(self.player.x, self.player.z)] if self.local_alive() else []
                    people += [(q.x, q.z) for q in self.mp.peers.values() if q.alive]
                    people = people or [(tgt.x, tgt.z)]
                for (px, pz) in people:
                    pts.append((round(px, 2), round(pz, 2), round(1.9 + random.uniform(0, 0.6), 2)))
                    for _ in range(6 if len(people) == 1 else 3):
                        a = random.random() * 2 * math.pi
                        r = random.uniform(3.0, 11.0)
                        x, z = w.collide(px + math.cos(a) * r, pz + math.sin(a) * r, 1.0)
                        pts.append((round(x, 2), round(z, 2), round(1.9 + random.uniform(0, 0.6), 2)))
                ev = ('roar', pts)
            out.append(ev)
        b.events = out

    def find_focus_ch5(self):
        if self.has_shotgun:
            return None
        p = self.player
        ex, ey, ez = p.eye()
        f = p.fwd()
        sx, sy, sz = C5.SHOTGUN_POS
        dx, dy, dz = sx - ex, sy - ey, sz - ez
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d < 2.4 and (dx * f[0] + dy * f[1] + dz * f[2]) / max(d, 1e-4) > 0.6:
            return ('shotgun', 0)
        return None

    def interact_ch5(self):
        if self.focus == ('shotgun', 0) and not self.has_shotgun:
            self.has_shotgun = True
            self.shells = SHELLS
            self.audio.play('bolt', 0.8)
            self.message("A shotgun. Loaded. Somebody came down here before you.", 4.5)
            self.set_objective("Keep going.  [Left mouse] fire   [R] reload")

    # ------------------------------------------------------------------ out
    def start_exit5(self):
        self.state = 'exit5'
        self.x5_t = 0.0
        self.set_mouse(False)
        p = self.player
        self.x5_from = (p.x, p.z)
        self.message("Daylight.", 3)

    def update_exit5(self, dt):
        self.x5_t += dt
        t = self.x5_t
        self.audio.loop('winter_amb', 0.8)
        if int(t / 0.42) != int((t - dt) / 0.42) and t < 5.5:
            self.audio.play_rand('step_snow', 4, 0.6)
        for m in self.msgs:
            m[1] -= dt
        self.msgs = [m for m in self.msgs if m[1] > 0]
        self.fade = clamp((t - 5.0) / 1.6, 0, 1)
        if t > 6.8:
            self.fade = 0.0
            self.progress['ch5_done'] = True
            self.progress.pop('resume', None)
            self.save_prog()
            self.ending_pages = lore.CH5_ENDING
            self.start_ending()

    def render_exit5(self):
        t = self.x5_t
        x0, z0 = self.x5_from
        z = z0 + 9.0 * sm(t, 0.0, 6.0)
        y = clamp((z - C5.HALL_Z1 - 4) * 0.12, 0, 6)
        cam = (x0 * (1 - sm(t, 0, 3)), y + 1.6 + 0.04 * math.sin(t * 8), z)
        fwd = look(cam, (0.0, y + 2.4 + 2.0 * sm(t, 1.0, 5.0), z + 20))
        self.draw_world5(cam, fwd, [], parts=[self.beast.parts(self.time)[0]] if self.beast else [])
        y_ = self.UH - 120
        for m in reversed(self.msgs):
            txt, tl, td = m
            al = int(clamp(tl / 0.8, 0, 1) * clamp((td - tl) / 0.3, 0, 1) * 255)
            self.blit_text(txt, self.f_msg, (225, 215, 200), (self.UW // 2, y_), 'midtop', alpha=al)
            y_ -= 30

    # ------------------------------------------------------------------ drawing
    def draw_world5(self, cam, fwd, lights, parts=(), extras=(), hold=None, fov=None):
        r = self.r
        w = self.w5
        dyn = self.mp_lights() + list(lights)
        parts = list(parts) + self.mp_parts(cam, fwd)
        if self.muzzle_t > 0:
            dyn.insert(0, ((cam[0] + fwd[0] * 1.0, cam[1], cam[2] + fwd[2] * 1.0), 14.0, (3.0, 2.0, 1.0)))
        if w.gate_open > 0:
            dyn.insert(0, ((0.0, 9.0, C5.HALL_Z1 + 3.0), 20.0 + 40.0 * w.gate_open,
                           tuple(c * (0.3 + 1.5 * w.gate_open) for c in (0.75, 0.72, 0.8))))
        for pl_pos in getattr(self, 'spot5', []):
            # a work lamp's worth of light on the thing, so you can see what you're fighting
            dyn.append(((pl_pos[0], 13.0, pl_pos[1]), 26.0, (1.5, 1.05, 0.7)))
        cand = []
        for (pos, rad, col, kind) in w.lights:
            d = math.hypot(pos[0] - cam[0], pos[2] - cam[2])
            if kind == 'tunnel' and cam[2] > C5.TUN_Z1 + 6:
                continue
            if kind != 'tunnel' and cam[2] < C5.TUN_Z1 - 10:
                continue
            k = 1.0
            if kind == 'fire':
                k = 0.8 + 0.2 * math.sin(self.time * 9 + pos[0]) * math.sin(self.time * 5.3 + pos[2])
            elif kind == 'red':
                k = 0.6 + 0.4 * (math.sin(self.time * 4) > 0)
            elif kind == 'lamp':
                k = 1.0 if math.sin(self.time * 17 + pos[2]) > -0.97 else 0.3
            cand.append((d - (25 if kind == 'lamp' else 0), (pos, rad, tuple(c * k * 1.6 for c in col))))
        cand.sort(key=lambda o: o[0])
        all_lights = (dyn + [c[1] for c in cand])[:8]
        if cam[2] < C5.TUN_Z1 - 2:
            env = TUNNEL_ENV
        else:
            env = FACTORY_ENV
            out = clamp((cam[2] - C5.HALL_Z1 + 6) / 14.0, 0, 1) * w.gate_open
            if out > 0:
                env = mix_env(FACTORY_ENV, DAWN_ENV, out)
        r.begin(cam, fwd, fov or self.settings['fov'], env, self.time, 0.0, cam, fwd, all_lights, far=200.0)
        r.draw(self.m_ch5)
        r.draw(self.m_gate5, model=T(0.0, w.gate_open * (C5.GATE_H - 0.6), C5.HALL_Z1 - 0.4))
        if w.sealed:
            r.draw(self.m_grate5, model=T(0.0, 0.0, C5.TUN_Z1 + 0.15))
        if not self.has_shotgun:
            sx, sy, sz = C5.SHOTGUN_POS
            r.draw(self.m_shotgun, model=T(sx, 0.06, sz) @ RY(0.4) @ RZ(math.pi / 2))
        for m in self.markers:
            pulse = 0.75 + 0.25 * math.sin(self.time * 18)
            s = m[3] * (0.6 + 0.4 * pulse) if m[4] == 'rock' else m[3] * 0.8
            r.draw(self.m_marker, model=T(m[0], 0.0, m[1]) @ S(s, 1, s))
            if m[4] == 'rock' and m[2] < 0.6:
                y = 0.3 + m[2] / 0.6 * 25.0
                r.draw(self.m_moose['dust'], model=T(m[0], y, m[1]) @ RY(m[2] * 7) @ S(1.6, 1.1, 1.4))
        for pr in self.proj:
            r.draw(self.m_moose['gore'], model=T(pr[0], pr[1], pr[2]) @ RX(pr[6]) @ RY(pr[6] * 0.7) @ S(0.7, 0.55, 0.6))
            r.draw(self.m_moose['bone'], model=T(pr[0], pr[1], pr[2]) @ RZ(pr[6]) @ S(0.15, 0.9, 0.15))
        for mesh, M in list(extras) + self.debris_extras():
            r.draw(mesh, model=M)
        for pl in parts:
            for key, M in pl:
                r.draw(self.m_moose[key], model=M)
        for b in self.blood:
            key = b[9] if len(b) > 9 else 'blood'
            if b[7]:
                s = b[6] * 2.4
                r.draw(self.m_moose[key], model=T(b[0], b[1] - 0.005 + b[8], b[2]) @ S(s, 0.006, s * 0.8))
            else:
                s = b[6]
                r.draw(self.m_moose[key], model=T(b[0], b[1], b[2]) @ S(s, s * 1.6, s))
        if hold:
            yaw, pitch = hold
            lp = self.held_lantern_pos(cam, yaw, pitch)
            M = T(*lp) @ RY(yaw) @ RZ(0.05 * math.sin(self.time * 2.1))
            r.draw(self.m_lantern, model=M)
            r.draw(self.m_lantern_lit if self.flash_on else self.m_lantern_off, model=M)
            if self.has_shotgun:
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

    def render_ch5_scene(self):
        p = self.player
        cam = p.eye()
        sh = getattr(self, 'shake', 0.0)
        if sh > 0:
            cam = (cam[0] + random.uniform(-1, 1) * 0.05 * sh, cam[1] + random.uniform(-1, 1) * 0.05 * sh, cam[2])
        fwd = p.fwd()
        lp = self.held_lantern_pos(cam, p.yaw, p.pitch)
        lit = self.flash_on and self.flicker_t <= 0
        lights = [((lp[0], lp[1] + 0.2, lp[2]), 10.0, self.lantern_col())] if lit else []
        parts = [self.beast.parts(self.time)[0]] if self.beast is not None else []
        self.spot5 = [(self.beast.x - math.sin(self.beast.yaw) * 2.0, self.beast.z - math.cos(self.beast.yaw) * 2.0)]             if self.beast is not None else []
        self.draw_world5(cam, fwd, lights, parts=parts, hold=(p.yaw, p.pitch))
        self.spot5 = []

    def render_scare_ch5(self, cam, yaw, fwd, k):
        parts = [self.moose4_face_parts(cam, yaw, 1.9 - min(k, 1.0) * 0.5)]
        lp = (cam[0] + math.sin(yaw) * 0.4, cam[1] - 0.35, cam[2] + math.cos(yaw) * 0.4)
        self.draw_world5(cam, fwd, [(lp, 6.0, (1.5, 0.9, 0.45))], parts=parts)

    def draw_hud_ch5(self):
        cx, cy = self.UW // 2, self.UH // 2
        b = self.beast
        if b is not None and self.c5_phase == 'boss':
            w = int(self.UW * 0.5)
            x0 = cx - w // 2
            self.blit_text("THE BEAST", self.f_hud, (200, 40, 30), (cx, 18), 'midtop')
            pygame.draw.rect(self.ui, (0, 0, 0, 190), (x0 - 2, 42, w + 4, 14))
            fill = int(w * b.hp / b.MAX_HP)
            col = (230, 230, 230, 240) if b.hurt_t > 0 else (160, 18, 12, 240)
            pygame.draw.rect(self.ui, col, (x0, 44, fill, 10))
            if b.state == 'stun':
                self.blit_text("STUNNED", self.f_small, (230, 200, 60), (cx, 60), 'midtop')
        if self.c5_phase in ('boss', 'won') or self.hp5 < 100:
            pygame.draw.rect(self.ui, (0, 0, 0, 170), (24, self.UH - 96, 204, 14))
            pygame.draw.rect(self.ui, (200, 50, 40, 230) if self.hp5 < 35 else (210, 200, 185, 220),
                             (26, self.UH - 94, int(200 * self.hp5 / 100), 10))
            self.blit_text("HEALTH", self.f_small, (200, 190, 180), (26, self.UH - 116))
        if self.has_shotgun:
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
        if self.c5_phase != 'boss':
            self.blit_text(self.objective if self.obj_t > 0 else "", self.f_small, (160, 152, 142), (26, 56))
        elif self.obj_t > 0:
            a = int(clamp(self.obj_t / 1.0, 0, 1) * 255)
            self.blit_text(self.objective, self.f_small, (160, 152, 142), (26, 76), alpha=a)
