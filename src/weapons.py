"""Guns, for every chapter. Mixed into game.Game.

Whatever gun is in your hands fires on [Left mouse]. Nothing but The Beast and
the Herd can be killed: a hit on the Moose Man, the Goat Man or the Elk stuns
it, then it goes off somewhere else and forgets about you for a while.
"""
import math
import random

import pygame

import inventory as INV


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def ray_sphere(o, d, c, r):
    ox, oy, oz = o[0] - c[0], o[1] - c[1], o[2] - c[2]
    b = ox * d[0] + oy * d[1] + oz * d[2]
    cc = ox * ox + oy * oy + oz * oz - r * r
    disc = b * b - cc
    if disc < 0:
        return None
    t = -b - math.sqrt(disc)
    return t if t > 0 else None


class Decoy:
    """Where a scared monster thinks you are: somewhere else entirely."""
    pid = None

    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z
        self.vx = self.vz = 0.0
        self.crouch = 1.0
        self.sprinting = False
        self.fx, self.fz = 0.0, 1.0
        self.smooth_y = y
        self.yaw = self.pitch = 0.0


class WeaponsMixin:
    # ---- the gun in your hands
    def fire_weapon(self):
        g = self.held_gun()
        if g is None or self.state != 'play' or getattr(self, 'inv_open', False):
            return False
        if g == 'shotgun' and self.chapter == 5:
            self.fire_shotgun()
        elif g == 'rifle' and self.chapter == 2:
            self.fire_rifle()
        else:
            self.fire_generic(g)
        return True

    def fire_generic(self, g):
        if getattr(self, 'gun_cd', 0.0) > 0:
            return
        if g == 'revolver':
            if getattr(self, 'rev_reload_t', -1.0) >= 0:
                return
            if getattr(self, 'rev_ammo', INV.REV_ROUNDS) <= 0:
                self.audio.play('click', 0.7)
                self.reload_weapon()
                return
            self.rev_ammo = getattr(self, 'rev_ammo', INV.REV_ROUNDS) - 1
            self.gun_cd = 0.42
            self.audio.play('revolver', 0.8)
        else:
            self.gun_cd = 1.4 if g == 'rifle' else 0.9
            self.audio.play('rifle_shot' if g == 'rifle' else 'rifle', 0.85)
        self.muzzle_t = 0.07
        self.muzzle_gun = g
        self.gun_kick = 1.0
        self.shake = max(getattr(self, 'shake', 0.0), 0.15 if g == 'revolver' else 0.25)
        p = self.player
        eye = p.eye()
        f = p.fwd()
        if self.chapter == 5:
            dmg = {'revolver': 7.0, 'rifle': 16.0, 'shotgun': 1.25}[g]
            n = 9 if g == 'shotgun' else 1
            self.shoot_rays5(eye, f, p.yaw, n, dmg, 0.06 if g == 'shotgun' else 0.004)
            return
        if self.chapter == 2:
            if self.rifle_hits_monster(eye, f):
                self.hitmark_t = 0.18
            return
        if self.gun_hits_monster(eye, f):
            self.hitmark_t = 0.18

    def reload_weapon(self):
        g = self.held_gun()
        if g == 'shotgun' and self.chapter == 5:
            self.start_reload()
        elif g == 'revolver' and getattr(self, 'rev_ammo', INV.REV_ROUNDS) < INV.REV_ROUNDS \
                and getattr(self, 'rev_reload_t', -1.0) < 0:
            self.rev_reload_t = 0.0
            self.audio.play('bolt', 0.5)

    def weapons_tick(self, dt):
        self.gun_cd = max(0.0, getattr(self, 'gun_cd', 0.0) - dt)
        self.gun_kick = max(0.0, getattr(self, 'gun_kick', 0.0) - dt * 6)
        self.hitmark_t = max(0.0, getattr(self, 'hitmark_t', 0.0) - dt)
        if self.chapter not in (2, 5):
            self.muzzle_t = max(0.0, getattr(self, 'muzzle_t', 0.0) - dt)
        if getattr(self, 'rev_reload_t', -1.0) >= 0:
            self.rev_reload_t += dt
            if self.rev_reload_t >= 1.6:
                self.rev_reload_t = -1.0
                self.rev_ammo = INV.REV_ROUNDS
                self.audio.play('click', 0.6)
        if getattr(self, 'inv_msg_t', 0) > 0:
            self.inv_msg_t -= dt

    # ---- what a bullet does to the things you can't kill
    def monster_targets(self):
        """(attr, obj, [(centre, radius)]) for everything in this chapter a bullet can stun."""
        out = []
        ch = self.chapter
        py = self.player.y

        def body(attr, x, y, z, low, lr, high, hr):
            out.append((attr, [((x, y + low, z), lr), ((x, y + high, z), hr)]))
        if ch == 1:
            m = getattr(self, 'moose', None)
            if m is not None and getattr(m, 'active', True):
                body('moose', m.x, getattr(m, 'y', py), m.z, 1.3, 0.6, 2.2, 0.45)
            c = getattr(self, 'chaser', None)
            if c and getattr(self, 'escape', False):
                body('chaser', c['x'], c.get('y', py), c['z'], 1.4, 0.6, 2.2, 0.4)
        elif ch == 3:
            e = getattr(self, 'elk', None)
            if e is not None:
                body('elk', e.x, getattr(e, 'y', py), e.z, 0.9, 1.0, 1.7, 0.6)
        elif ch == 4:
            m = getattr(self, 'moose4', None)
            if m is not None:
                body('moose4', m.x, getattr(m, 'y', py), m.z, 1.6, 0.9, 3.0, 0.6)
        return out

    def gun_hits_monster(self, eye, f):
        best = None
        for attr, spheres in self.monster_targets():
            for ctr, rad in spheres:
                t = ray_sphere(eye, f, ctr, rad)
                if t is not None and t < 80 and (best is None or t < best[0]):
                    best = (t, attr, ctr)
        if best is None:
            return False
        t, attr, ctr = best
        self.stun_monster(attr)
        self.spawn_blood(ctr[0], ctr[1], ctr[2], 14, vel=(f[0] * 2, 1.5, f[2] * 2), spread=1.0)
        snd = {'elk': 'elk_bugle', 'goat': 'goat_roar', 'moose4': 'moose_roar'}.get(attr, 'call_near')
        self.audio.play3d(snd, ctr[0], ctr[2], 80, 0.8)
        self.message("It staggers -- and backs off.", 2.0)
        return True

    def stun_monster(self, attr):
        p = self.player
        if self.mp_sim():
            self.act_stun({'m': attr, 'x': round(p.x, 2), 'z': round(p.z, 2)}, None)
        else:
            self.mp_tell('stun', m=attr, x=round(p.x, 2), z=round(p.z, 2))

    def act_stun(self, a, frm):
        """Frozen for a moment, then it goes the other way and forgets you for a while."""
        attr = a['m']
        self.mon_stun[attr] = self.time + INV.STUN_T
        obj = getattr(self, attr, None)
        if obj is None:
            return
        get = obj.get if isinstance(obj, dict) else (lambda n: getattr(obj, n, None))
        mx, mz = get('x') or 0.0, get('z') or 0.0
        sx, sz = a.get('x', self.player.x), a.get('z', self.player.z)
        dx, dz = mx - sx, mz - sz
        d = math.hypot(dx, dz) or 1.0
        self.mon_scare = getattr(self, 'mon_scare', {})
        self.mon_scare[attr] = (self.time + INV.STUN_T + INV.SCARE_T, mx + dx / d * 40.0, mz + dz / d * 40.0)
        if self.mp_sim() and not isinstance(obj, dict):
            try:
                self.send_away(obj, sx, sz)
            except Exception:
                pass

    def send_away(self, obj, sx, sz):
        """After the stun it walks off somewhere well away from whoever shot it."""
        name = type(obj).__name__
        rng = random.Random()
        if name == 'Moose':
            import world as W
            w = obj.w
            cells = [(c, r) for r in range(W.ROWS) for c in range(W.COLS) if w.g[r][c] == '.'
                     and math.hypot(W.cell_center(c, r)[0] - sx, W.cell_center(c, r)[1] - sz) > 25]
            if cells and obj.state not in ('inactive',):
                obj.path_to(*W.cell_center(*rng.choice(cells)))
                obj.state = 'intro_leave'
        elif hasattr(obj, 'go_to') and hasattr(obj, 'lv'):
            lv = obj.lv
            cells = [c for c in lv.elk_cells() if math.hypot(lv.center(*c)[0] - sx, lv.center(*c)[1] - sz) > 26]
            if cells:
                obj.go_to(*lv.center(*rng.choice(cells)))
                obj.state = 'leave'
                obj.timer = 0.0
        elif name == 'GoatHunter':
            import chapter2 as C2
            away = math.atan2(obj.x - sx, obj.z - sz)
            obj.target = (clamp(obj.x + math.sin(away) * 38, -C2.HALF + 8, C2.HALF - 8),
                          clamp(obj.z + math.cos(away) * 38, -C2.HALF + 8, C2.HALF - 8))
            obj.state = 'leave'
            obj.timer = 0.0

    def scared_target(self, attr):
        sc = getattr(self, 'mon_scare', {}).get(attr)
        if sc is None or self.time >= sc[0]:
            return None
        return Decoy(sc[1], self.player.y, sc[2])

    # ---- the HUD
    def draw_weapon_hud(self):
        g = self.held_gun()
        if g == 'revolver':
            n = getattr(self, 'rev_ammo', INV.REV_ROUNDS)
            for i in range(INV.REV_ROUNDS):
                x = self.UW - 30 - i * 14
                c = (200, 170, 60, 240) if i < n else (70, 60, 50, 140)
                pygame.draw.circle(self.ui, c, (x, self.UH - 96), 5)
            if getattr(self, 'rev_reload_t', -1.0) >= 0:
                self.blit_text("RELOADING", self.f_small, (200, 190, 180), (self.UW - 26, self.UH - 128), 'topright')
            elif n == 0:
                self.blit_text("[R] RELOAD", self.f_small, (220, 80, 60), (self.UW - 26, self.UH - 128), 'topright')
        if self.chapter != 5 and getattr(self, 'hitmark_t', 0) > 0:
            cx, cy = self.UW // 2, self.UH // 2
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                pygame.draw.line(self.ui, (240, 230, 220, 230), (cx + sx * 6, cy + sy * 6), (cx + sx * 12, cy + sy * 12), 2)
