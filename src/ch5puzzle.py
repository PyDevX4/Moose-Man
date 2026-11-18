"""Chapter 5 before the fight, for the Game class: the passcode, the machines,
the big door, the dark hall, the key, the booth, and the button that lets him out.
Mixed into game.Game (before Ch5Mixin)."""
import math
import random

import pygame

from engine import Mesh, T, S, RX, RY
import chapter4 as C4
import chapter5 as C5
import factory5 as F5


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


KEYPAD = [['1', '2', '3'], ['4', '5', '6'], ['7', '8', '9'], ['<', '0', 'OK']]


class Ch5PuzzleMixin:
    # ================================================================== setup
    def init_ch5_puzzle(self, prog):
        from gridgrow import zones_of
        from extras import pick_spread    # noqa: F401  (used in randomize_ch5)
        ctx = self.ctx
        self.m_door5 = Mesh(ctx, prog, F5.door_mesh(2.0, 4.2))
        self.m_bigdoor = Mesh(ctx, prog, F5.big_door_mesh())
        self.m_paper = Mesh(ctx, prog, F5.paper_mesh())
        self.m_switch = Mesh(ctx, prog, F5.switch_mesh())
        self.m_lamp_on = Mesh(ctx, prog, F5.lamp_mesh(True))
        self.m_lamp_off = Mesh(ctx, prog, F5.lamp_mesh(False))
        self.m_gate_e = Mesh(ctx, prog, C4.gate_mesh(8.0, 9.0, True))
        self.m_bdoor = Mesh(ctx, prog, F5.door_mesh(2.2, 2.6))
        fac = self.w5.fac
        z = zones_of(fac.g, '.DB', 'DB')
        za, zb = z.get((50, 27)), z.get((15, 28))
        self.spots_paper = [(c, r) for (c, r) in fac.floor_cells() if z.get((c, r)) == za and not (r == 27 and c >= 52)]
        self.spots_switch = [s for s in fac.wall_spots('.') if z.get((s[0], s[1])) == zb]
        self.c5_code = '0000'
        self.c5_papers = []
        self.c5_switches = []
        self.key5_shelf = 0
        self.key5_pos = (0.0, 0.0, 0.0)
        self.reset_ch5_puzzle()

    def reset_ch5_puzzle(self):
        w = getattr(self, 'w5', None)
        if w is not None:
            w.fac.door_open = 0.0
            w.fac.big_open = 0.0
            w.booth_open = 0.0
            w.east_gate = 0.0
        self.c5_digits = set()        # which digits of the code you've found
        self.door5_opening = False
        self.big5_opening = False
        self.booth5_opening = False
        self.key5 = False
        self.button5 = False
        self.hall_lit = 0.0
        self.keypad_open = False
        self.keypad_buf = ''
        self.keypad_flash = 0.0
        self.keypad_bad = 0.0
        for s in getattr(self, 'c5_switches', []):
            s.update(on=False, progress=0.0, angle=0.8)

    def randomize_ch5(self, rng):
        from extras import pick_spread
        fac = self.w5.fac
        self.c5_code = ''.join(str(rng.randrange(10)) for _ in range(4))
        # four scraps of paper in the small rooms, one digit each
        picks = pick_spread(rng, self.spots_paper, 4, 11.0, lambda s: fac.center(*s))
        order = list(range(4))
        rng.shuffle(order)
        self.c5_papers = []
        for i, (c, r) in zip(order, picks):
            x, z = fac.center(c, r)
            self.c5_papers.append({'digit': i, 'pos': (x + rng.uniform(-0.3, 0.3), 0.02, z + rng.uniform(-0.3, 0.3)),
                                   'rot': rng.random() * 6})
        # four switches on the machine floor, two for each machine
        picks = pick_spread(rng, self.spots_switch, 4, 24.0, lambda s: fac.center(s[0], s[1]))
        self.c5_switches = []
        for k, (c, r, side) in enumerate(picks):
            p, yaw = fac.lever_spot(c, r, side)
            self.c5_switches.append({'pos': p, 'yaw': yaw, 'machine': k // 2, 'on': False, 'progress': 0.0, 'angle': 0.8})
        # the key: on one shelf in the dark hall
        self.key5_shelf = rng.randrange(len(C5.SHELVES))
        x, z, yaw = C5.SHELVES[self.key5_shelf]
        lx = rng.uniform(-0.8, 0.8)
        y = rng.choice((0.89, 1.59))
        self.key5_pos = (x + math.cos(yaw) * lx, y, z - math.sin(yaw) * lx)

    # ================================================================== state of things
    def machine_on(self, m):
        return all(s['on'] for s in self.c5_switches if s['machine'] == m)

    def machines_on(self):
        return sum(1 for m in (0, 1) if self.machine_on(m))

    def code_shown(self):
        return ' '.join(self.c5_code[i] if i in self.c5_digits else '_' for i in range(4))

    def paper_text(self, i):
        return ' '.join(self.c5_code[i] if k == i else '_' for k in range(4))

    # ================================================================== shared actions
    def act_digit5(self, a, frm):
        i = a['i']
        if i not in self.c5_digits:
            self.c5_digits.add(i)
            if frm is not None:
                self.message("%s found a digit: %s" % (self.who(frm), self.paper_text(i)), 4)
        self.set_objective("Find the four digits of the door code.  CODE  %s" % self.code_shown())

    def act_door5(self, a, frm):
        if self.door5_opening:
            return
        self.door5_opening = True
        dx, dz = self.w5.fac.center(*F5.DOOR_CELL)
        self.audio.play3d('gate', dx, dz, 50, 1.0)
        self.audio.play3d('clunk', dx, dz, 30, 0.8)
        self.message("The lock clacks over. The steel door grinds up." if frm is None else
                     "%s got the door open." % self.who(frm), 4)
        self.set_objective("Get the two big machines running. Each one needs two switches thrown.")

    def act_switch5(self, a, frm):
        s = self.c5_switches[a['i']]
        if s['on']:
            return
        s['on'] = True
        s['progress'] = 1.0
        m = s['machine']
        x, _, z = s['pos']
        self.audio.play3d('clunk', x, z, 40, 1.0)
        if self.machine_on(m):
            mx, mz = self.w5.fac.machines[m]['pos']
            self.audio.play3d('gen_start', mx, mz, 80, 1.0)
            n = self.machines_on()
            self.message("Machine %d groans into life. (%d/2)" % (m + 1, n), 4)
            if n >= 2:
                self.big5_opening = True
                self.audio.play('gate', 1.0)
                self.message("Both machines are running. Somewhere ahead, a huge door starts to lift.", 5)
                self.set_objective("Go through the big door.")
        else:
            self.message(("A switch for machine %d. It needs one more." % (m + 1)) if frm is None else
                         "%s threw a switch for machine %d." % (self.who(frm), m + 1), 3.5)

    def act_key5(self, a, frm):
        if self.key5:
            return
        self.key5 = True
        self.audio.play('wood_pick', 0.6)
        self.message("A key on a tag: ADMIN." if frm is None else "%s found the admin key." % self.who(frm), 4)
        self.set_objective("Unlock the admin booth in the corner.")

    def act_booth5(self, a, frm):
        if self.booth5_opening:
            return
        self.booth5_opening = True
        self.audio.play3d('door_open', C5.BOOTH_DOOR[0], C5.BOOTH_DOOR[1], 30, 1.0)
        self.set_objective("Press the button.")

    def press_button5(self):
        if self.button5:
            return
        self.button5 = True
        p = self.player
        if self.mp_on():
            self.mp_act('go', name='beastcs', x=round(p.x, 2), z=round(p.z, 2), yaw=round(p.yaw, 3))
        else:
            self.start_beast_cs()

    # ================================================================== focus and E
    def ch5_puzzle_focus(self):
        p = self.player
        ex, ey, ez = p.eye()
        f = p.fwd()
        w = self.w5
        cands = []
        for i, pa in enumerate(self.c5_papers):
            cands.append(('paper5', i, pa['pos'], 2.2))
        if not self.door5_opening:
            cands.append(('keypad5', 0, w.fac.keypad, 2.2))
        for i, s in enumerate(self.c5_switches):
            if not s['on']:
                cands.append(('switch5', i, s['pos'], 2.3))
        if not self.key5:
            cands.append(('key5', 0, self.key5_pos, 2.2))
        if not self.booth5_opening:
            cands.append(('booth5', 0, (C5.BOOTH_DOOR[0], 1.3, C5.BOOTH_DOOR[1]), 2.4))
        elif not self.button5:
            cands.append(('button5', 0, C5.BUTTON, 2.6))
        best, bestd = None, -1
        for kind, key, pos, rng in cands:
            dx, dy, dz = pos[0] - ex, pos[1] - ey, pos[2] - ez
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if 1e-3 < d < rng:
                dot = (dx * f[0] + dy * f[1] + dz * f[2]) / d
                if dot > (0.55 if d < 1.3 else 0.8) and dot > bestd:
                    best, bestd = (kind, key), dot
        return best

    def ch5_puzzle_interact(self, kind, key):
        if kind == 'paper5':
            i = self.c5_papers[key]['digit']
            self.audio.play('paper', 0.7)
            self.message("A scrap of paper, in marker:   %s" % self.paper_text(i), 6)
            self.mp_act('digit5', i=i)
        elif kind == 'keypad5':
            self.keypad_open = True
            self.keypad_buf = ''
            self.block_input = True
            self.set_mouse(False)
            self.audio.play('click', 0.5)
        elif kind == 'key5':
            self.mp_act('key5')
        elif kind == 'booth5':
            if self.key5:
                self.mp_act('booth5')
            else:
                self.message("ADMIN. Locked.", 2.5)
                if 'booth_hint' not in self.flags:
                    self.flags.add('booth_hint')
                    self.set_objective("Find the key to the admin booth. Check the shelves.")
        elif kind == 'button5':
            self.audio.play('clunk', 1.0)
            self.press_button5()
        return kind in ('paper5', 'keypad5', 'key5', 'booth5', 'button5')

    def ch5_label(self, kind, key):
        if kind == 'paper5':
            return "[E] Read the paper", 0.0
        if kind == 'keypad5':
            return "[E] Keypad", 0.0
        if kind == 'switch5':
            s = self.c5_switches[key]
            return "[E] Throw the switch  (machine %d)" % (s['machine'] + 1), s['progress']
        if kind == 'key5':
            return "[E] Take the key", 0.0
        if kind == 'booth5':
            return ("[E] Unlock the door" if self.key5 else "ADMIN  -  locked"), 0.0
        if kind == 'button5':
            return "[E] Press the button", 0.0
        return None, 0.0

    # ================================================================== the keypad
    def keypad_rects(self):
        cx, cy = self.UW // 2, self.UH // 2
        out = []
        for r, row in enumerate(KEYPAD):
            for c, k in enumerate(row):
                out.append((k, pygame.Rect(cx - 105 + c * 72, cy - 40 + r * 58, 66, 52)))
        return out

    def keypad_close(self):
        self.keypad_open = False
        self.block_input = False
        if self.state == 'play':
            self.set_mouse(True)

    def keypad_press(self, k):
        self.audio.play('click', 0.45)
        if k == '<':
            self.keypad_buf = self.keypad_buf[:-1]
        elif k == 'OK':
            if self.keypad_buf == self.c5_code:
                self.keypad_close()
                self.mp_act('door5')
            else:
                self.keypad_bad = 0.6
                self.keypad_buf = ''
                self.audio.play('impact', 0.4)
        elif len(self.keypad_buf) < 4:
            self.keypad_buf += k
            if len(self.keypad_buf) == 4 and self.keypad_buf == self.c5_code:
                self.keypad_press('OK')

    def keypad_event(self, ev):
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self.keypad_close()
            elif ev.key == pygame.K_BACKSPACE:
                self.keypad_press('<')
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.keypad_press('OK')
            elif ev.unicode and ev.unicode.isdigit():
                self.keypad_press(ev.unicode)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            ux, uy = self.ui_mouse()
            hit = False
            for k, rc in self.keypad_rects():
                if rc.collidepoint(ux, uy):
                    self.keypad_press(k)
                    hit = True
            if not hit:
                panel = pygame.Rect(self.UW // 2 - 130, self.UH // 2 - 130, 260, 320)
                if not panel.collidepoint(ux, uy):
                    self.keypad_close()

    def draw_keypad(self):
        ui = self.ui
        cx, cy = self.UW // 2, self.UH // 2
        panel = pygame.Rect(cx - 130, cy - 130, 260, 320)
        pygame.draw.rect(ui, (20, 22, 24, 235), panel)
        pygame.draw.rect(ui, (90, 95, 100, 255), panel, 2)
        disp = pygame.Rect(cx - 105, cy - 112, 210, 52)
        bad = self.keypad_bad > 0
        pygame.draw.rect(ui, (60, 8, 6, 255) if bad else (8, 28, 12, 255), disp)
        txt = ' '.join((self.keypad_buf + '____')[:4])
        self.blit_text(txt, self.f_big if hasattr(self, 'f_big') else self.f_hud, (240, 80, 60) if bad else (90, 240, 120),
                       (disp.centerx, disp.y + 2), 'midtop', shadow=False)
        for k, rc in self.keypad_rects():
            pygame.draw.rect(ui, (60, 62, 66, 255), rc)
            pygame.draw.rect(ui, (120, 124, 128, 255), rc, 1)
            self.blit_text(k, self.f_hud, (230, 230, 225), rc.center, 'center', shadow=False)
        self.blit_text("type or tap the code  -  ESC to step back", self.f_small, (160, 155, 150), (cx, panel.bottom + 8), 'midtop')
        if self.c5_digits:
            self.blit_text("you found:  %s" % self.code_shown(), self.f_small, (200, 190, 150), (cx, panel.bottom + 26), 'midtop')

    # ================================================================== every frame, before the fight
    def update_ch5_puzzle(self, dt, keys):
        w = self.w5
        fac = w.fac
        self.keypad_bad = max(0.0, self.keypad_bad - dt)
        if self.door5_opening and fac.door_open < 1.0:
            fac.door_open = min(1.0, fac.door_open + dt / 2.0)
        if self.big5_opening and fac.big_open < 1.0:
            fac.big_open = min(1.0, fac.big_open + dt / 7.0)
            self.shake = max(getattr(self, 'shake', 0.0), 0.15)
        if self.booth5_opening and w.booth_open < 1.0:
            w.booth_open = min(1.0, w.booth_open + dt / 1.2)
        # switches: one press throws them (pull_lever_press); here they swing down
        for s in self.c5_switches:
            if s['on']:
                s['angle'] += (2.371 - s['angle']) * min(1.0, dt * 8)
        # first time into the hall: dark, and very quiet
        p = self.player
        if w.region(p.x, p.z) == 'hall' and 'hall5' not in self.flags:
            self.flags.add('hall5')
            self.message("The factory floor. Pitch black. Something's been eating in here.", 5)
            self.set_objective("Look around. There's a booth in the far corner.")
        # the machines hum once they run
        for m, mach in enumerate(fac.machines):
            if self.machine_on(m):
                self.audio.loop3d('gen_hum', mach['pos'][0], mach['pos'][1], 30, 0.7)
                break
        else:
            self.audio.loop('gen_hum', 0.0)

    # ================================================================== drawing the pieces
    def draw_ch5_dyn(self, r):
        w = self.w5
        fac = w.fac
        dx, dz = fac.center(*F5.DOOR_CELL)
        r.draw(self.m_door5, model=T(dx, fac.door_open * 4.0, dz))
        r.draw(self.m_bigdoor, model=T(-C5.HALL_X, fac.big_open * 9.6, sum(F5.BIG_Z) / 2))
        for pa in self.c5_papers:
            r.draw(self.m_paper, model=T(*pa['pos']) @ RY(pa['rot']))
        for s in self.c5_switches:
            M = T(*s['pos']) @ RY(s['yaw'])
            r.draw(self.m_switch, model=M)
            r.draw(self.m_lever, model=M @ RX(s['angle']) @ S(1.4, 1.4, 1.4))
        for m, mach in enumerate(fac.machines):
            on = self.machine_on(m)
            lx, ly, lz = mach['lamp']
            r.draw(self.m_lamp_on if on else self.m_lamp_off, model=T(lx, ly, lz))
        if not self.key5:
            r.draw(self.m_key, model=T(*self.key5_pos) @ RY(0.9))
        bx, bz = C5.BOOTH_DOOR
        r.draw(self.m_bdoor, model=T(bx, 0.0, bz + w.booth_open * 2.0))
        r.draw(self.m_gate_e, model=T(C5.HALL_X - 0.3, w.east_gate * 8.6, C5.EAST_DOOR[1]) @ RY(math.pi / 2))

    def ch5_puzzle_lights(self):
        """The machines' lamps, once they're running."""
        out = []
        for m, mach in enumerate(self.w5.fac.machines):
            if self.machine_on(m):
                x, y, z = mach['lamp']
                out.append(((x, y + 0.5, z + 1.0), 10.0, (0.4, 1.0, 0.45)))
        return out

    def ch5_status(self):
        if self.c5_phase != 'drain':
            return None
        if not self.door5_opening:
            return "CODE   %s" % self.code_shown()
        if self.machines_on() < 2:
            n = sum(1 for s in self.c5_switches if s['on'])
            return "SWITCHES %d/4    MACHINES %d/2" % (n, self.machines_on())
        if not self.key5:
            return "FIND THE KEY"
        return "THE BOOTH"
