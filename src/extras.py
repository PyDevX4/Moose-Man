"""Puzzles added after the chapters shipped.

Chapter 1: two flood-gate levers in the woods open the storm drain; past the
           drained chamber, a key in the old works opens the ladder gate.
Chapter 2: stack the wood, light the stove, take the rifle AND the knife.
           The Goat Man stays out there until you start butchering.
           A rifle hit stuns a monster for a second.
Chapter 3: four levers up top; down below, power the minecart and ride it
           through the boarded tunnel (hold W).
"""
import math
import random

import pygame

from engine import Mesh, MeshBuilder, T, RX, RY
from textures import L, EMIS
import world as W
import chapter2 as C2
import chapter3 as C3
import chapter4 as C4

CART_END_PAD = 0.2


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def key_mesh():
    b = MeshBuilder()
    brass = (1.0, 0.78, 0.3)
    b.box((0, 0.02, 0), (0.06, 0.03, 0.26), L.METAL, brass)
    b.box((0, 0.02, -0.15), (0.12, 0.03, 0.1), L.METAL, brass)
    b.box((0.03, 0.02, 0.1), (0.05, 0.03, 0.04), L.METAL, brass)
    b.box((0.03, 0.02, 0.06), (0.05, 0.03, 0.03), L.METAL, brass)
    b.box((0, 0.045, -0.15), (0.05, 0.01, 0.05), L.GLOW + EMIS, (0.8, 0.65, 0.3))
    return b.array()


def ray_sphere(o, d, c, r):
    ox, oy, oz = o[0] - c[0], o[1] - c[1], o[2] - c[2]
    bb = ox * d[0] + oy * d[1] + oz * d[2]
    cc = ox * ox + oy * oy + oz * oz - r * r
    disc = bb * bb - cc
    if disc < 0:
        return None
    t = -bb - math.sqrt(disc)
    return t if t > 0 else None


class ExtrasMixin:
    # ================================================================== setup
    def init_extras(self, prog):
        self.m_grate1 = Mesh(self.ctx, prog, C4.gate_mesh(2.0, 2.4, False))
        self.m_keygate = Mesh(self.ctx, prog, C4.gate_mesh(2.0, 3.4, False))
        self.m_key = Mesh(self.ctx, prog, key_mesh())
        self.m_cart = Mesh(self.ctx, prog, C3.cart_mesh())
        self.m_plank = Mesh(self.ctx, prog, C3.plank_mesh())
        self.mon_stun = {}
        self.reset_extras()

    def reset_extras(self):
        w = self.world
        w.grate_open = 0.0
        w.keygate_open = 0.0
        for lev in w.c1_levers:
            lev.update(pulled=False, progress=0.0, angle=-0.8)
        self.key_taken = False
        self.c1_lever_t = 0.0
        # chapter 2
        self.fire_lit = False
        self.has_knife = False
        # chapter 3
        self.cart_power = False
        self.c3_riding = False
        self.cart_s = 0.0
        self.cart_v = 0.0
        self.cart_send_t = 0.0
        self.cart_done = False
        lv = getattr(self, 'lv_low', None)
        if lv is not None:
            for pl in lv.planks:
                pl['broken'] = False
        self.mon_stun = {}

    def stunned(self, attr):
        return self.time < self.mon_stun.get(attr, -1.0)

    def act_stun(self, a, frm):
        self.mon_stun[a['m']] = self.time + 1.0

    # ================================================================== chapter 1
    def c1_levers_pulled(self):
        return sum(1 for lev in self.world.c1_levers if lev['pulled'])

    def update_c1_extras(self, dt, keys):
        w = self.world
        p = self.player
        pulling = False
        for i, lev in enumerate(w.c1_levers):
            if lev['pulled']:
                lev['angle'] += (0.8 - lev['angle']) * min(1.0, dt * 8)
                continue
            if self.focus == ('c1lever', i) and keys[pygame.K_e]:
                pulling = True
                lev['progress'] += dt / 1.6
                lev['angle'] = -0.8 + lev['progress']
                if lev['progress'] >= 1.0:
                    self.mp_act('c1lever', i=i)
            elif lev['progress'] > 0 and self.focus != ('c1lever', i):
                lev['progress'] = max(0.0, lev['progress'] - dt * 0.8)
                lev['angle'] = -0.8 + lev['progress']
        if pulling:
            self.audio.loop('creak', 0.6)
        # the grate lifts once both are down
        if self.c1_levers_pulled() >= len(w.c1_levers) and w.grate_open < 1.0:
            w.grate_open = min(1.0, w.grate_open + dt / 3.5)
        # walking up to the shut grate
        if w.grate_open < 0.8 and p.z > 44.0 and abs(p.x) < 4.0 and 'grate' not in self.flags:
            self.flags.add('grate')
            self.message("A flood grate, locked over the drain.", 4)
            self.message("The sign: FLOOD CONTROL. RELEASE LEVERS IN THE WOODS.", 6)
            self.set_objective("Find the two flood-gate release levers in the woods. Look for the red lamps. (%d/2)"
                               % self.c1_levers_pulled())
        # the ladder gate
        if w.keygate_open > 0.0 and w.keygate_open < 1.0:
            w.keygate_open = min(1.0, w.keygate_open + dt / 2.0)
        lx, lz = self.keygate_spot()
        if w.keygate_open < 0.8 and math.hypot(p.x - lx, p.z - lz) < 3.0 and 'keygate' not in self.flags \
                and (w.drained or self.valves_done >= 5):
            self.flags.add('keygate')
            if not self.key_taken:
                self.message("A gate in front of the ladder, chained and padlocked.", 4.5)
                self.set_objective("Find the key to the ladder gate. Search the old works past the chamber.")

    def keygate_spot(self):
        gx, gz = W.OX + W.KEYGATE[0] * W.C + W.C / 2, W.OZ + W.KEYGATE[1] * W.C
        return gx, gz - 0.6

    def act_c1lever(self, a, frm):
        lev = self.world.c1_levers[a['i']]
        if lev['pulled']:
            return
        lev['pulled'] = True
        lev['progress'] = 1.0
        self.audio.play('clunk', 0.9 if frm is None else 0.5)
        n = self.c1_levers_pulled()
        if n < 2:
            self.message(("The lever drops with a bang. Somewhere a chain rattles. (%d/2)" % n) if frm is None else
                         ("%s pulled a release lever. (%d/2)" % (self.who(frm), n)), 4)
            self.set_objective("Find the two flood-gate release levers in the woods. Look for the red lamps. (%d/2)" % n)
        else:
            self.audio.play('gate', 0.6)
            self.message("Far off toward the creek, metal grinds. The flood grate is going up.", 5)
            self.set_objective("The drain is open. Follow the trail north to the creek.")

    def act_c1key(self, a, frm):
        if self.key_taken:
            return
        self.key_taken = True
        self.audio.play('wood_pick', 0.6)
        if frm is None:
            self.message("A brass key on a ring, stamped GATE 9. It was in his pocket.", 4.5)
        else:
            self.message("%s found the key." % self.who(frm), 4)
        self.set_objective("Take the key to the gate in front of the service ladder.")

    def act_c1gate(self, a, frm):
        w = self.world
        if w.keygate_open > 0:
            return
        w.keygate_open = 0.01
        lx, lz = self.keygate_spot()
        self.audio.play3d('gate', lx, lz, 60, 1.0)
        self.audio.play3d('clunk', lx, lz, 30, 0.8)
        if self.moose.active and self.mp_sim():
            self.moose.hear(lx, lz, 60.0)
        self.message("The padlock gives. The gate scrapes up.", 4)
        self.set_objective("Climb the service ladder.")

    def c1_focus_cands(self):
        w = self.world
        out = []
        for i, lev in enumerate(w.c1_levers):
            if not lev['pulled']:
                out.append(('c1lever', i, lev['pos']))
        if w.key_pos and not self.key_taken:
            out.append(('c1key', 0, w.key_pos))
        if w.keygate_open <= 0.0:
            gx, gz = self.keygate_spot()
            out.append(('keygate', 0, (gx, W.SEWER_FLOOR + 1.3, gz + 0.5)))
        return out

    def interact_c1(self, kind):
        if kind == 'c1key':
            self.mp_act('c1key')
            return True
        if kind == 'keygate':
            if self.key_taken:
                self.mp_act('c1gate')
            else:
                self.message("Locked. Chained shut with a padlock.", 2.5)
            return True
        return False

    def draw_c1_dyn(self, r, cam):
        w = self.world
        if cam[2] < 70:
            for lev in w.c1_levers:
                r.draw(self.m_lever, model=T(*lev['pos']) @ RY(lev['yaw']) @ RX(lev['angle']))
            r.draw(self.m_grate1, model=T(0.0, 2.4 * w.grate_open, 47.72))
        if cam[2] > 120:
            gx, gz = self.keygate_spot()
            r.draw(self.m_keygate, model=T(gx, W.SEWER_FLOOR + 3.0 * w.keygate_open, gz + 0.6))
            if w.key_pos and not self.key_taken:
                r.draw(self.m_key, model=T(*w.key_pos) @ RY(0.7))

    def c1_label(self, kind, key):
        if kind == 'c1lever':
            return "[Hold E] Pull the release lever", self.world.c1_levers[key]['progress']
        if kind == 'c1key':
            return "[E] Take the key", 0.0
        if kind == 'keygate':
            return ("[E] Unlock the gate" if self.key_taken else "Locked"), 0.0
        return None, 0.0

    # ================================================================== chapter 2
    def ch2_goat_phase(self):
        return self.ch2_phase in ('wood', 'fire', 'rifle', 'hunt')

    def stove_spot(self):
        return 0.6, -1.5

    def knife_spot(self):
        return 1.75, -1.25

    def ch2_extra_focus(self):
        p = self.player
        ph = self.ch2_phase
        sx, sz = self.stove_spot()
        if ph == 'fire' and math.hypot(p.x - sx, p.z - sz) < 1.6:
            return ('stove', 0)
        kx, kz = self.knife_spot()
        if ph in ('rifle', 'hunt') and not self.has_knife and math.hypot(p.x - kx, p.z - kz) < 1.5:
            return ('knife', 0)
        return None

    def act_stove(self, a, frm):
        if self.fire_lit:
            return
        self.fire_lit = True
        self.ch2_phase = 'rifle'
        self.audio.play('match', 0.9)
        self.message(("The kindling catches. The stove roars." if frm is None else
                      "%s got the stove going." % self.who(frm)), 4)
        self.set_objective("Take the rifle from the rack and the knife from the table.")

    def take_knife(self):
        self.has_knife = True
        self.audio.play('wood_pick', 0.6)
        self.message("A hunting knife. Sharp.", 3)
        self.check_armed()

    def check_armed(self):
        if self.has_rifle and self.has_knife and self.ch2_phase == 'rifle':
            self.mp_act('armed')
        elif self.has_rifle and not self.has_knife:
            self.set_objective("Take the knife from the table too.")
        elif self.has_knife and not self.has_rifle:
            self.set_objective("Take the rifle from the rack too.")

    def act_armed(self, a, frm):
        if self.ch2_phase != 'rifle':
            return
        self.ch2_phase = 'hunt'
        self.deer = C2.Deer(self.w2, random.Random())
        if frm is not None:
            self.message("%s is ready to hunt. Take a rifle and a knife." % self.who(frm), 4)
        self.set_objective("Hunt a deer. One's been grazing straight out in front of the cabin.  "
                           "[Right mouse] aim  [Left mouse] fire")

    def stove_lights(self):
        if self.chapter != 2 or not self.fire_lit:
            return []
        Y = C2.CABIN_Y
        k = 0.8 + 0.2 * math.sin(self.time * 9) * math.sin(self.time * 5.3 + 1.7)
        sx, sz = self.stove_spot()
        return [((sx, Y + 0.6, sz + 0.45), 6.0, (1.6 * k, 0.7 * k, 0.2 * k))]

    def rifle_hits_monster(self, eye, f):
        """A rifle round into the Goat Man (or the Moose Man on the run home) stuns him for a second."""
        cands = []
        gt = self.goat
        if gt is not None and self.ch2_goat_phase():
            fx, fz = math.sin(gt.yaw), math.cos(gt.yaw)
            cands.append(('goat', [((gt.x, gt.y + 1.3, gt.z), 0.75), ((gt.x + fx * 0.5, gt.y + 2.3, gt.z + fz * 0.5), 0.45)]))
        c = self.chaser2
        if c is not None and self.ch2_phase == 'run':
            cands.append(('chaser2', [((c['x'], c['y'] + 1.4, c['z']), 0.6), ((c['x'], c['y'] + 2.2, c['z']), 0.4)]))
        best = None
        for attr, spheres in cands:
            for ctr, rad in spheres:
                t = ray_sphere(eye, f, ctr, rad)
                if t is not None and t < 120 and (best is None or t < best[0]):
                    best = (t, attr, ctr)
        if best is None:
            return False
        t, attr, ctr = best
        if self.mp_sim():
            self.mon_stun[attr] = self.time + 1.0
        else:
            self.mp_tell('stun', m=attr)
        self.spawn_blood(ctr[0], ctr[1], ctr[2], 16, vel=(f[0] * 2, 1.5, f[2] * 2), spread=1.0)
        self.audio.play3d('goat_roar' if attr == 'goat' else 'call_near', ctr[0], ctr[2], 80, 0.8)
        self.message("It staggers.", 1.5)
        return True

    # ================================================================== chapter 3
    def cart_pos(self):
        lv = self.lv_low
        x, z0, _ = lv.rail
        return x, z0 + self.cart_s

    def cart_len(self):
        _, z0, z1 = self.lv_low.rail
        return z1 - z0

    def ch3_extra_focus(self):
        lv = self.lv
        if lv is not self.lv_low or self.c3_riding or self.cart_done:
            return None
        p = self.player
        cx, cz = self.cart_pos()
        if math.hypot(p.x - cx, p.z - cz) < 1.9:
            return ('cart', 0)
        return None

    def ch3_low_lever_done(self):
        self.cart_power = True
        self.audio.play('drain', 0.5)
        self.message("A motor coughs somewhere back in the yard. The minecart has power.", 5)
        self.set_objective("Get in the minecart. Hold [W] to drive it through the boards.")

    def interact_cart(self):
        if not self.cart_power:
            self.message("The minecart. Its motor is dead -- there must be power somewhere down here.", 3.5)
            self.set_objective("Find a way to power the minecart.")
            return
        if self.mp_on():
            self.message("Everyone has to get in.", 2.5)
            return
        self.start_cart()

    def start_cart(self):
        self.c3_riding = True
        self.cart_v = 0.0
        self.audio.play('clunk', 0.8)
        self.message("Hold [W]. Don't stop.", 3)

    def act_cart(self, a, frm):
        if a['s'] > self.cart_s:
            self.cart_s, self.cart_v = a['s'], a['v']

    def act_plank(self, a, frm):
        pl = self.lv_low.planks[a['i']]
        if pl['broken']:
            return
        pl['broken'] = True
        cx = self.lv_low.rail[0]
        self.audio.play3d('smash', cx, pl['z'], 40, 1.0)
        self.shake = max(getattr(self, 'shake', 0.0), 0.7)
        self.burst_debris(cx, self.lv_low.y0 + 1.2, pl['z'], 26, up=3.0, spread=2.5, size=(0.08, 0.5))

    def update_cart(self, dt, keys):
        """Riding: W drives forward, S rolls it back."""
        p = self.player
        lv = self.lv_low
        fwd = keys[pygame.K_w] or keys[pygame.K_UP]
        back = keys[pygame.K_s] or keys[pygame.K_DOWN]
        if fwd:
            self.cart_v = min(4.2, self.cart_v + 2.4 * dt)
        elif back:
            self.cart_v = max(-1.5, self.cart_v - 2.4 * dt)
        else:
            self.cart_v *= max(0.0, 1.0 - dt * 0.9)
        s = self.cart_s + self.cart_v * dt
        _, z0, _ = lv.rail
        for i, pl in enumerate(lv.planks):
            if pl['broken']:
                continue
            front = pl['z'] - z0 - 0.95
            if s > front and self.cart_s <= front + 0.01:
                if self.cart_v > 1.4:
                    self.mp_act('plank', i=i)
                    self.cart_v *= 0.55
                else:
                    s = front
                    if self.cart_v > 0.3:
                        self.audio.play('impact', 0.5)
                    self.cart_v = 0.0
                    self.message("Back up and hit it harder.", 2)
        self.cart_s = clamp(s, 0.0, self.cart_len())
        self.audio.loop('creak', clamp(abs(self.cart_v) / 3.0, 0, 0.8))
        self.shake = max(getattr(self, 'shake', 0.0) * (1 - dt * 2), clamp(abs(self.cart_v) / 4.2, 0, 1) * 0.12)
        self.cart_send_t -= dt
        if self.mp_on() and self.cart_send_t <= 0:
            self.cart_send_t = 0.25
            self.mp_tell('cart', s=round(self.cart_s, 2), v=round(self.cart_v, 2))
        # you're in the cart
        cx, cz = self.cart_pos()
        slot = self.mp.slot if self.mp_on() else 0
        p.x = cx + (-0.22 if slot % 2 == 0 else 0.22)
        p.z = cz + (-0.3 if slot < 2 else 0.3)
        p.vx, p.vz = 0.0, self.cart_v
        p.y = lv.y0 + 0.35
        p.smooth_y = p.y
        p.bob_amt = 0.0
        if self.cart_s >= self.cart_len() - CART_END_PAD:
            self.cart_v = 0.0
            self.c3_riding = False
            self.cart_done = True
            self.audio.loop('creak', 0.0)
            self.audio.play('clunk', 1.0)
            p.x = cx + 1.3
            p.y = lv.y0
            p.smooth_y = p.y
            self.message("The cart slams into the buffers. A huge cavern. Something big is lying in the middle of it.", 5)
            self.set_objective("Keep going. Find a way out of the mine.")
        self.update_debris(dt, lv.y0)

    def draw_c3_dyn(self, r, lv):
        if lv is not self.lv_low:
            return
        cx, cz = self.cart_pos()
        r.draw(self.m_cart, model=T(cx, lv.y0, cz))
        for pl in lv.planks:
            if not pl['broken']:
                r.draw(self.m_plank, model=T(lv.rail[0], lv.y0, pl['z']))
        for mesh, M in self.debris_extras():
            r.draw(mesh, model=M)
