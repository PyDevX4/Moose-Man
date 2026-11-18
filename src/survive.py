"""SURVIVE: game modes with no story. Mixed into game.Game.

CABIN DEFENSE: the Chapter Two cabin in a blizzard, midnight to 6 AM (twelve real minutes).
Keep the stove fed or freeze. Every so often the Moose Man, the Goat Man or the Elk comes out
of the trees and tries to break in through the door or the window: shoot it enough and it runs
back into the storm. Catch you outside and it chases you down.

It runs as Chapter Two with ch2_phase 'defense', so walking, the door, the rifle and the
scope are Chapter Two's own; this file adds the night, the fire, the cold and the attackers."""
import math
import random

import pygame

from engine import T, S, RY, RX
import chapter2 as C2
from moose import pose_moose, pose_goat
from elk import pose_elk


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


NIGHT_REAL = 720.0                 # real seconds from midnight to 6 AM
NIGHT_GAME = 6 * 3600.0
FUEL_BURN = 100.0 / 150.0          # a full stove lasts two and a half minutes
LOG_FUEL = 30.0
CARRY_MAX = 4
BOX_LOGS = 4                       # in the box by the stove at midnight
PORCH_LOGS = 8                     # stacked on the porch
KINDS = {
    #          hits  walk  chase  bash seconds  call
    'moose': dict(hp=3, walk=2.3, chase=4.4, bash=11.0, call='call_far', name="The Moose Man"),
    'goat': dict(hp=2, walk=2.6, chase=4.7, bash=9.0, call='goat_roar', name="The Goat Man"),
    'elk': dict(hp=4, walk=2.0, chase=4.0, bash=7.5, call='elk_bugle', name="The Elk"),
}
DEAD_TEXT = {
    'moose': ("THE MOOSE MAN", "he got in."),
    'goat': ("THE GOAT MAN", "he got in."),
    'elk': ("THE ELK", "it got in."),
    'cold': ("YOU FROZE", "the fire went out."),
}
DAWN_ENV = {'ambient': (0.2, 0.2, 0.24), 'mooncol': (0.45, 0.36, 0.3), 'moondir': (0.25, -0.45, -0.85),
            'fog': (0.42, 0.41, 0.46), 'fogdens': 0.035}
NIGHT_ENV = {'ambient': (0.05, 0.055, 0.07), 'mooncol': (0.05, 0.055, 0.07), 'moondir': (0.3, -0.8, 0.5),
             'fog': (0.05, 0.055, 0.065), 'fogdens': 0.07}


def inside_cabin(x, z, m=0.0):
    return abs(x) < C2.CABIN_HX - m and abs(z) < C2.CABIN_HZ - m


def ray_sphere(o, d, c, r):
    ox, oy, oz = o[0] - c[0], o[1] - c[1], o[2] - c[2]
    b = ox * d[0] + oy * d[1] + oz * d[2]
    cq = ox * ox + oy * oy + oz * oz - r * r
    disc = b * b - cq
    if disc < 0:
        return None
    t = -b - math.sqrt(disc)
    return t if t > 0 else None


# ---------------------------------------------------------------------- one of them, coming for the cabin
class Intruder:
    def __init__(self, kind, x, z, target):
        k = KINDS[kind]
        self.kind = kind
        self.x, self.z = x, z
        self.yaw = math.atan2(-x, -z)
        self.hp = k['hp']
        self.state = 'approach'        # approach, bash, chase, breach, flee
        self.target = target           # 'door' or 'window'
        self.walk = 0.0
        self.amt = 0.0
        self.flinch = 0.0
        self.stuck_t = 0.0
        self.side_t = 0.0
        self.side = 1
        self.bash_t = 0.0
        self.gone = False
        self.events = []

    def y(self):
        return float(C2.terrain_h2(self.x, self.z))

    def spot(self):
        """Where it stands to break in."""
        off = {'moose': 1.7, 'goat': 1.8, 'elk': 2.4}[self.kind]      # far enough that nothing pokes through the wall
        if self.target == 'window':
            return -C2.CABIN_HX - off, C2.WINDOW_Z
        return 0.0, C2.CABIN_HZ + off

    def move_to(self, dt, tx, tz, speed, w2):
        dx, dz = tx - self.x, tz - self.z
        d = math.hypot(dx, dz)
        if d < 0.05:
            self.amt += (0.0 - self.amt) * min(1.0, dt * 6)
            return d
        ux, uz = dx / d, dz / d
        if self.side_t > 0:
            # going round something
            self.side_t -= dt
            ux, uz = ux * 0.4 + uz * self.side, uz * 0.4 - ux * self.side
            n = math.hypot(ux, uz)
            ux, uz = ux / n, uz / n
        step = min(d, speed * dt)
        nx, nz = w2.collide(self.x + ux * step, self.z + uz * step, 0.55, self.x, self.z)
        if inside_cabin(nx, nz, -0.5):
            nx, nz = self.x, self.z            # never through the walls
        moved = math.hypot(nx - self.x, nz - self.z)
        if moved < step * 0.3 and d > 1.0:
            self.stuck_t += dt
            if self.stuck_t > 0.6:
                self.stuck_t = 0.0
                self.side = random.choice((-1, 1))
                self.side_t = 1.2
        else:
            self.stuck_t = 0.0
        self.x, self.z = nx, nz
        want = math.atan2(dx, dz)
        dy = (want - self.yaw + math.pi) % (2 * math.pi) - math.pi
        self.yaw += dy * min(1.0, dt * 5)
        self.walk += moved * (1.6 if self.kind != 'elk' else 1.1)
        self.amt += (min(1.0, moved / max(dt, 1e-4) / 2.0) - self.amt) * min(1.0, dt * 6)
        return d

    def parts(self, t):
        x, y, z = self.x, self.y(), self.z
        hostile = self.state in ('chase', 'bash', 'breach')
        jit = 0.15 * self.flinch
        if self.kind == 'moose':
            reach = 0.9 if self.state == 'bash' else (0.7 if hostile else 0.2)
            if self.state == 'bash':
                reach += 0.3 * math.sin(t * 9)
            return pose_moose(x, y, z, self.yaw + jit, self.walk, self.amt, hunch=0.75 if hostile else 0.5,
                              reach=reach, jaw=0.45 if hostile else 0.1, t=t)
        if self.kind == 'goat':
            arms = 0.55 if hostile else 0.15
            if self.state == 'bash':
                arms = 0.7 + 0.3 * math.sin(t * 8)
            return pose_goat(x, y, z, self.yaw + jit, walk_phase=self.walk, walk_amt=self.amt,
                             hunch=0.85 if hostile else 0.5, arms=arms, jaw=0.65 if hostile else 0.2,
                             bloody=True, t=t)
        jaw = 0.8 if hostile else 0.4
        pitch = 1.2 - (0.35 * (0.5 + 0.5 * math.sin(t * 6)) if self.state == 'bash' else 0.0)
        return pose_elk(x, y, z, self.yaw + jit, phase=self.walk, amt=self.amt, jaw=jaw, t=t, pitch=pitch)

    def hit_spheres(self, t):
        parts, head = self.parts(t)
        hx, hy, hz = float(head[0, 3]), float(head[1, 3]), float(head[2, 3])
        y = self.y()
        big = 1.0 if self.kind == 'elk' else 0.6
        body = ((self.x + hx) / 2, (y + 0.9 + hy) / 2, (self.z + hz) / 2)
        return [((hx, hy, hz), 0.42 * (1.3 if self.kind == 'elk' else 1.0), 2),
                (body, big, 1), ((self.x, y + 1.0, self.z), big * 0.9, 1)]


# ---------------------------------------------------------------------- the mixin
class SurviveMixin:
    # ------------------------------------------------------------------ the menu
    def survive_items(self):
        best = self.progress.get('survive_cabin', 0)
        if best >= NIGHT_GAME:
            tag = "   (survived)"
        elif best > 0:
            tag = "   (best: %s)" % self.night_clock(best)
        else:
            tag = ""
        return ["CABIN DEFENSE" + tag, "BACK"]

    def survive_action(self, i):
        self.audio.play('click', 0.5)
        if i == 0:
            self.start_defense()
        else:
            self.state = 'title'
            self.menu_sel = 2

    def survive_event(self, ev):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.state = 'title'
            self.menu_sel = 2
            return
        self.menu_event(ev, self.survive_items(), self.survive_action)

    def draw_survive_ui(self):
        self.draw_menu(self.survive_items(), "SURVIVE")
        y0 = int(self.UH * 0.56) + 46 * 2 + 20
        if self.menu_sel == 0:
            for k, ln in enumerate((
                    "The cabin, in a blizzard. Midnight to 6 AM.",
                    "Keep the stove going or freeze. Drive them off with the rifle.",
                    "If they see you outside, they come for you.")):
                self.blit_text(ln, self.f_small, (160, 152, 142), (80, y0 + k * 22))

    # ------------------------------------------------------------------ CABIN DEFENSE
    def night_clock(self, secs):
        m = int(secs // 60)
        h, mm = divmod(m, 60)
        return "%d:%02d AM" % (12 if h == 0 else h, mm)

    def defense_on(self):
        return getattr(self, 'survive', None) == 'cabin' and self.chapter == 2

    def start_defense(self):
        self.new_game()
        self.survive = 'cabin'
        self.chapter = 2
        self.ch2_phase = 'defense'
        self.state = 'play'
        self.goat = None
        self.deer = None
        self.chaser2 = None
        w2 = self.w2
        w2.door_open = False
        self.door_angle = 0.0
        self.window_broken = False
        self.stacked = PORCH_LOGS            # the porch woodpile (drawn from this count)
        self.carried = 0
        self.wood_taken = set()
        self.wood_carried = []
        self.fire_lit = True
        self.has_knife = False
        self.storm = 1.0
        self.ch2_t = 0.0
        self.aim = 0.0
        self.fire_cd = 0.0
        self.muzzle_t = 0.0
        self.blood = []
        self.msgs = []
        self.fear = self.red = self.glitch = 0.0
        d = self.dfn = {
            't': 0.0, 'fuel': 100.0, 'box': BOX_LOGS, 'warm': 100.0, 'door_hp': 100.0, 'win_hp': 100.0,
            'door_broken': False, 'intruders': [], 'spawn_t': 25.0, 'driven': 0, 'killer': None,
            'cold_msg': 0.0, 'won': False, 'first': True,
        }
        # the kit: the rifle in both hands, the headlamp on, the lantern in the bag
        from inventory import BAG
        self.__dict__['inv'] = {'left': None, 'right': None, 'head': 'headlamp', 'bag': [None] * BAG}
        self.give('lantern')
        self.inv_put_hands('rifle', None, force=True)
        self.__dict__['inv_chapter'] = 2
        self.flash_on = True
        p = self.player
        p.reset(0.4, C2.CABIN_Y + 0.05, -0.4, 0.0)
        self.fade = 1.0
        self.def_fade = 1.2
        self.set_objective("Keep the fire going. Survive until 6 AM.")
        self.message("Midnight. The storm is right on top of the cabin.", 5)
        self.set_mouse(True)
        self.audio.stop_all()
        self.audio.stop_loops()
        d['tick'] = d['t']

    def defense_game_secs(self):
        return self.dfn['t'] / NIGHT_REAL * NIGHT_GAME

    def update_defense(self, dt):
        """Called from update_ch2 each frame, after Chapter Two has moved you about."""
        d = self.dfn
        p = self.player
        A = self.audio
        d['t'] += dt
        gs = self.defense_game_secs()
        self.clock_t = (24 * 3600 - (23 * 3600 + 58 * 60 + 7)) + gs
        night = d['t'] / NIGHT_REAL
        self.storm = 1.0 - 0.6 * clamp((night - 0.85) / 0.15, 0, 1)
        A.loop('winter_amb', 0.75 * self.storm + 0.15)
        if self.def_fade > 0:
            self.def_fade -= dt
            self.fade = clamp(self.def_fade / 1.0, 0, 1)
        # the fire
        if d['fuel'] > 0:
            d['fuel'] = max(0.0, d['fuel'] - FUEL_BURN * dt)
            if d['fuel'] <= 0:
                self.message("The fire's gone out.", 4)
                A.play('wood_drop', 0.4)
        self.fire_lit = d['fuel'] > 0
        sx, sz = self.stove_spot()
        self.hitmark_t = max(0.0, getattr(self, 'hitmark_t', 0.0) - dt)
        # you: warm by the fire, cold everywhere else
        inside = inside_cabin(p.x, p.z)
        if inside and d['fuel'] > 0:
            d['warm'] = min(100.0, d['warm'] + (6.0 if math.hypot(p.x - sx, p.z - sz) < 2.6 else 3.0) * dt)
        elif inside:
            d['warm'] -= 0.35 * dt
        else:
            d['warm'] -= 0.9 * dt
        d['cold_msg'] = max(0.0, d['cold_msg'] - dt)
        if d['warm'] < 30 and d['cold_msg'] <= 0:
            d['cold_msg'] = 20.0
            self.message("You can't feel your hands. Get to the fire.", 4)
        if d['warm'] <= 0:
            self.defense_die('cold')
            return
        self.fear = clamp((40 - d['warm']) / 40.0, 0, 1) * 0.5
        # the door and the window mend while nobody's at them
        bashing = {i.target for i in d['intruders'] if i.state == 'bash'}
        if 'door' not in bashing:
            d['door_hp'] = min(100.0, d['door_hp'] + 4.0 * dt)
            if d['door_broken'] and d['door_hp'] > 40:
                d['door_broken'] = False
                self.message("You jam the door back into its frame.", 3)
        if 'window' not in bashing:
            d['win_hp'] = min(100.0, d['win_hp'] + 4.0 * dt)
        if d['door_broken']:
            self.w2.door_open = True
        # them
        self.update_intruders(dt)
        if self.state != 'play':
            return
        if gs >= NIGHT_GAME and not d['won']:
            self.defense_win()

    # ---- them
    def spawn_intruder(self):
        d = self.dfn
        w2 = self.w2
        kind = random.choice(('moose', 'goat', 'elk'))
        for _ in range(200):
            a = random.random() * 2 * math.pi
            r = random.uniform(55.0, 70.0)
            x, z = math.sin(a) * r, math.cos(a) * r
            if float(C2.terrain_h2(x, z)) > C2.WL + 0.5 and not w2.near_tree(x, z, 1.5) \
                    and abs(x) < C2.HALF - 6 and abs(z) < C2.HALF - 6:
                break
        target = 'door' if random.random() < 0.6 else 'window'
        if target == 'window' and self.window_broken:
            target = 'door'
        it = Intruder(kind, x, z, target)
        d['intruders'].append(it)
        self.audio.play3d(KINDS[kind]['call'], x, z, 160.0, 1.0)
        if d['first']:
            d['first'] = False
            self.message("Something's coming out of the trees.", 4)

    def update_intruders(self, dt):
        d = self.dfn
        p = self.player
        A = self.audio
        w2 = self.w2
        night = d['t'] / NIGHT_REAL
        active = [i for i in d['intruders'] if i.state != 'flee']
        most = 1 if night < 0.35 else (2 if night < 0.8 else 3)
        d['spawn_t'] -= dt
        if d['spawn_t'] <= 0 and night < 0.97:
            if len(active) < most:
                self.spawn_intruder()
            d['spawn_t'] = random.uniform(48, 75) * (1.0 - 0.45 * night)
        inside = inside_cabin(p.x, p.z)
        crouch = p.crouch > 0.5
        for it in list(d['intruders']):
            k = KINDS[it.kind]
            it.flinch = max(0.0, it.flinch - dt * 4)
            dist = math.hypot(p.x - it.x, p.z - it.z)
            # can it see you?
            see = 32.0 if self.flash_on else 22.0
            if crouch:
                see *= 0.6
            if it.state in ('approach', 'bash') and not inside and (dist < see or dist < 6.0):
                it.state = 'chase'
                A.play3d(k['call'], it.x, it.z, 90.0, 1.0)
                if dist < 25:
                    A.play('stinger', 0.6)
            if it.state == 'approach':
                sx, sz = it.spot()
                if it.move_to(dt, sx, sz, k['walk'], w2) < 0.4:
                    it.state = 'bash'
                    it.bash_t = 0.0
            elif it.state == 'bash':
                sx, sz = it.spot()
                it.move_to(dt, sx, sz, 1.0, w2)
                want = math.atan2(-it.x, -it.z) if it.target == 'door' else math.atan2(C2.CABIN_HX, 0.0)
                if it.target == 'door':
                    want = math.atan2(0.0 - it.x, (C2.CABIN_HZ - 0.5) - it.z)
                else:
                    want = math.atan2((-C2.CABIN_HX + 0.5) - it.x, C2.WINDOW_Z - it.z)
                it.yaw += ((want - it.yaw + math.pi) % (2 * math.pi) - math.pi) * min(1.0, dt * 6)
                it.bash_t -= dt
                key = 'door_hp' if it.target == 'door' else 'win_hp'
                if it.target == 'door' and self.w2.door_open:
                    d[key] = 0.0                  # you left it open
                d[key] -= 100.0 / k['bash'] * dt
                if it.bash_t <= 0:
                    it.bash_t = random.uniform(0.8, 1.3)
                    A.play3d('impact', it.x, it.z, 40.0, 1.0)
                    A.play3d('smash' if random.random() < 0.3 else 'clunk', it.x, it.z, 30.0, 0.6)
                    if inside:
                        self.shake = max(getattr(self, 'shake', 0.0), 0.35)
                if d[key] <= 0:
                    d[key] = 0.0
                    if it.target == 'window' and not self.window_broken:
                        self.window_broken = True
                        A.play('glass', 1.0)
                    if it.target == 'door':
                        d['door_broken'] = True
                        self.w2.door_open = True
                        A.play('smash', 1.0)
                    it.state = 'breach'
            elif it.state == 'breach':
                # through the gap: if you're in there, that's it
                if inside:
                    self.defense_die(it.kind)
                    return
                it.state = 'chase'
            elif it.state == 'chase':
                if inside and not (it.target == 'door' and self.w2.door_open and dist < 3.0):
                    # you got back in: it goes for the way in
                    it.target = 'door' if not self.window_broken or random.random() < 0.5 else 'window'
                    it.state = 'approach'
                else:
                    it.move_to(dt, p.x, p.z, k['chase'], w2)
                    if dist < 1.3:
                        self.defense_die(it.kind)
                        return
            elif it.state == 'flee':
                ax, az = it.x * 3.0, it.z * 3.0
                if abs(ax) + abs(az) < 1:
                    ax, az = 60.0, 60.0
                it.move_to(dt, ax, az, 5.5, w2)
                if math.hypot(it.x, it.z) > 60:
                    it.gone = True
            # a door open to it with you inside
            if it.state in ('approach', 'chase', 'bash') and it.target == 'door' and self.w2.door_open and inside:
                sx, sz = it.spot()
                if math.hypot(it.x - sx, it.z - sz) < 1.0:
                    self.defense_die(it.kind)
                    return
        d['intruders'] = [i for i in d['intruders'] if not i.gone]
        near = min((math.hypot(i.x - p.x, i.z - p.z) for i in d['intruders'] if i.state != 'flee'), default=99.0)
        A.loop('breath', clamp(1.0 - near / 25.0, 0.0, 0.7))

    def defense_shot(self, eye, f):
        """A rifle round: through the window or the open door if you're inside, into whatever it meets."""
        d = self.dfn
        if inside_cabin(eye[0], eye[2]) and not self.shot_gets_out(eye, f):
            self.audio.play('impact', 0.5)
            return False
        best = None
        for it in d['intruders']:
            if it.state == 'flee':
                continue
            for c, r, mult in it.hit_spheres(self.time):
                tt = ray_sphere(eye, f, c, r)
                if tt is not None and tt < 250 and (best is None or tt < best[0]):
                    best = (tt, it, mult)
        if best is None:
            return False
        tt, it, mult = best
        hx, hy, hz = eye[0] + f[0] * tt, eye[1] + f[1] * tt, eye[2] + f[2] * tt
        self.spawn_blood(hx, hy, hz, 12, vel=(f[0] * 2, 1.5, f[2] * 2), spread=1.2)
        self.hitmark_t = 0.18
        it.hp -= mult
        it.flinch = 1.0
        k = KINDS[it.kind]
        if it.hp <= 0:
            it.state = 'flee'
            d['driven'] += 1
            self.audio.play3d(k['call'], it.x, it.z, 120.0, 1.0)
            self.message("%s runs back into the storm." % k['name'], 3.5)
        else:
            self.audio.play3d('snort' if it.kind != 'goat' else 'goat_roar', it.x, it.z, 80.0, 0.6)
            if it.state == 'approach' and math.hypot(it.x, it.z) > 12:
                it.state = 'approach'
        return True

    def shot_gets_out(self, eye, f):
        """From inside: does the line leave through the open door or the window?"""
        hx, hz = C2.CABIN_HX, C2.CABIN_HZ
        best = None
        for axis, val in (('x', hx), ('x', -hx), ('z', hz), ('z', -hz)):
            comp = f[0] if axis == 'x' else f[2]
            o = eye[0] if axis == 'x' else eye[2]
            if abs(comp) < 1e-6:
                continue
            t = (val - o) / comp
            if t > 0 and (best is None or t < best[0]):
                best = (t, axis, val)
        if best is None:
            return False
        t, axis, val = best
        x, y, z = eye[0] + f[0] * t, eye[1] + f[1] * t, eye[2] + f[2] * t
        Y = C2.CABIN_Y
        if axis == 'z' and val > 0:
            return self.w2.door_open and -0.55 < x < 0.55 and y < Y + 2.05
        if axis == 'x' and val < 0:
            return abs(z - C2.WINDOW_Z) < 0.45 and abs(y - C2.WINDOW_Y) < 0.3
        return False

    def defense_die(self, why):
        d = self.dfn
        if self.state != 'play':
            return
        d['killer'] = why
        self.save_defense_best()
        if why == 'cold':
            self.state = 'dead'
            self.dead_t = 0.0
            self.set_mouse(False)
            self.audio.stop_all()
            self.audio.stop_loops()
            self.audio.play('heart', 0.8)
            return
        self.hurt_src = why
        self.kill()

    def save_defense_best(self):
        gs = min(self.defense_game_secs(), NIGHT_GAME)
        if gs > self.progress.get('survive_cabin', 0):
            self.progress['survive_cabin'] = round(gs)
            try:
                self.save_prog()
            except Exception:
                pass

    def defense_win(self):
        d = self.dfn
        d['won'] = True
        self.save_defense_best()
        self.ending_pages = [
            [
                "6:00 AM",
                "",
                "The sun comes up over the snow, and the wind drops.",
                "Whatever was out there goes back into the trees.",
                "",
                "You drove them off %d time%s." % (d['driven'], '' if d['driven'] == 1 else 's'),
            ],
            [
                "YOU SURVIVED",
                "",
                "CABIN DEFENSE",
            ],
        ]
        self.ending_next = self.back_to_survive
        self.start_ending()

    def back_to_survive(self):
        self.to_title()
        self.state = 'survive'
        self.menu_sel = 0

    def respawn_defense(self):
        self.start_defense()

    def defense_dead_text(self):
        title, sub = DEAD_TEXT.get(self.dfn.get('killer') or 'moose', DEAD_TEXT['moose'])
        return title, "%s  You lasted until %s." % (sub, self.night_clock(min(self.defense_game_secs(), NIGHT_GAME)))

    # ---- your hands: the fire and the wood
    def defense_focus(self):
        d = self.dfn
        p = self.player
        sx, sz = self.stove_spot()
        if math.hypot(p.x - sx, p.z - sz) < 1.6:
            return ('dstove', 0)
        hz = C2.CABIN_HZ
        if math.hypot(p.x - 0.0, p.z - hz) < 1.9 and not d['door_broken']:
            return ('door', 0)
        wx, wz = C2.WOODPILE
        if self.stacked > 0 and math.hypot(p.x - wx, p.z - wz) < 1.6:
            return ('dpile', 0)
        if self.carried < CARRY_MAX:
            for i, (x, y, z, _r) in enumerate(self.w2.wood_spots):
                if i not in self.wood_taken and math.hypot(p.x - x, p.z - z) < 1.6:
                    return ('dwood', i)
        return None

    def defense_label(self, kind, key):
        d = self.dfn
        if kind == 'dstove':
            if self.carried > 0:
                return "[E] Put a log on the fire  (carrying %d)" % self.carried
            if d['box'] > 0:
                return "[E] Put a log on the fire  (%d in the box)" % d['box']
            return "No wood. There's more on the porch and out in the trees."
        if kind == 'dpile':
            return "[E] Take firewood  (%d on the pile)" % self.stacked
        if kind == 'dwood':
            return "[E] Take the firewood"
        return None

    def defense_interact(self):
        d = self.dfn
        if not self.focus:
            return
        kind, key = self.focus
        A = self.audio
        if kind == 'door':
            self.interact_more_ch2('door')
        elif kind == 'dstove':
            if self.carried <= 0 and d['box'] <= 0:
                self.message("No wood left in here.", 2.5)
                return
            if d['fuel'] > 100 - LOG_FUEL * 0.5:
                self.message("It's burning fine. Save the wood.", 2)
                return
            if self.carried > 0:
                self.carried -= 1
            else:
                d['box'] -= 1
            was = d['fuel']
            d['fuel'] = min(100.0, d['fuel'] + LOG_FUEL)
            A.play('wood_drop', 0.7)
            if was <= 0:
                A.play('match', 0.9)
                self.message("The fire catches again.", 3)
        elif kind == 'dpile':
            n = min(CARRY_MAX - self.carried, self.stacked)
            if n <= 0:
                self.message("You can't carry any more.", 2)
                return
            self.stacked -= n
            self.carried += n
            A.play('wood_pick', 0.8)
            self.message("Firewood. (carrying %d)" % self.carried, 2.5)
        elif kind == 'dwood':
            self.wood_taken.add(key)
            self.carried += 1
            A.play('wood_pick', 0.8)
            self.message("Firewood. (carrying %d)" % self.carried, 2.5)

    # ---- drawing
    def defense_parts(self):
        out = []
        p = self.player
        for it in self.dfn['intruders']:
            if math.hypot(it.x - p.x, it.z - p.z) < 120:
                out.append(it.parts(self.time)[0])
        return out

    def defense_env(self):
        night = self.dfn['t'] / NIGHT_REAL
        k = clamp((night - 0.82) / 0.18, 0, 1)
        return {key: (tuple(NIGHT_ENV[key][i] + (DAWN_ENV[key][i] - NIGHT_ENV[key][i]) * k for i in range(3))
                      if isinstance(NIGHT_ENV[key], tuple) else NIGHT_ENV[key] + (DAWN_ENV[key] - NIGHT_ENV[key]) * k)
                for key in NIGHT_ENV}

    def defense_extras(self):
        """The logs left in the box by the stove."""
        out = []
        sx, sz = self.stove_spot()
        for k in range(self.dfn['box']):
            out.append((self.m_log, T(sx - 0.5 + (k % 2) * 0.16 - 0.08, C2.CABIN_Y + 0.12 + (k // 2) * 0.15, sz + 0.1) @ RY(1.57)))
        return out

    def draw_defense_hud(self):
        d = self.dfn
        ui = self.ui
        gs = min(self.defense_game_secs(), NIGHT_GAME)
        self.blit_text(self.night_clock(gs), self.f_hud, (225, 215, 200), (self.UW // 2, 14), 'midtop')
        # the night going by
        w = 220
        x0 = self.UW // 2 - w // 2
        pygame.draw.rect(ui, (0, 0, 0, 150), (x0, 44, w, 6))
        pygame.draw.rect(ui, (200, 170, 110, 220), (x0, 44, int(w * gs / NIGHT_GAME), 6))
        bars = (("FIRE", d['fuel'], (230, 120, 40)), ("WARMTH", d['warm'], (120, 170, 230)))
        for k, (name, v, col) in enumerate(bars):
            y = self.UH - 150 - k * 34
            self.blit_text(name, self.f_small, (200, 190, 180), (26, y - 18))
            pygame.draw.rect(ui, (0, 0, 0, 170), (24, y, 204, 12))
            c = (200, 50, 40) if v < 25 else col
            pygame.draw.rect(ui, c + (230,), (26, y + 2, int(200 * clamp(v, 0, 100) / 100), 8))
        self.blit_text("WOOD  carrying %d   box %d   porch %d" % (self.carried, d['box'], self.stacked),
                       self.f_small, (215, 205, 190), (26, 56))
        for name, key in (("DOOR", 'door_hp'), ("WINDOW", 'win_hp')):
            if d[key] < 99 and any(i.state == 'bash' and (i.target == 'door') == (key == 'door_hp') for i in d['intruders']):
                y = 70 if key == 'door_hp' else 90
                self.blit_text(name, self.f_small, (230, 90, 70), (self.UW // 2 - 150, y))
                pygame.draw.rect(ui, (0, 0, 0, 170), (self.UW // 2 - 80, y + 3, 204, 10))
                pygame.draw.rect(ui, (200, 50, 40, 230), (self.UW // 2 - 78, y + 5, int(200 * d[key] / 100), 6))
        if getattr(self, 'hitmark_t', 0) > 0:
            cx, cy = self.UW // 2, self.UH // 2
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                pygame.draw.line(ui, (240, 230, 220, 230), (cx + sx * 6, cy + sy * 6), (cx + sx * 12, cy + sy * 12), 2)

    def render_scare_defense(self, cam, yaw, fwd, k):
        why = self.dfn.get('killer')
        lp = (cam[0] + math.sin(yaw) * 0.4, cam[1] - 0.35, cam[2] + math.cos(yaw) * 0.4)
        if why == 'goat':
            parts = [self.goat_face_parts(cam, yaw, 2.0 - min(k, 1.0) * 0.55)]
        elif why == 'elk':
            parts = [self.elk_face_parts(cam, yaw, 2.2 - min(k, 1.0) * 0.6)]
        else:
            parts = [self.face_parts(cam, fwd, yaw, 1.75 - min(k, 1.0) * 0.45)]
        self.draw_world2(cam, fwd, [(lp, 6.0, (1.5, 0.9, 0.45))], parts=parts, env=self.defense_env())
