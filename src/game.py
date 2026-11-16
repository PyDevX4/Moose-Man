"""MOOSE MAN - main game loop, states, UI."""
import os
import sys
import json
import math
import random
import time
import threading

import numpy as np
import pygame
import moderngl

from engine import Renderer, Mesh, T, S, RX, RY, RZ
from textures import make_textures, L
import world as W
from world import World, cell_of, cell_center, clamp
from moose import Moose, pose_moose, moose_meshes, valve_mesh, wheel_mesh, herd_head_mesh
from audio import Audio
import lore
import updater
from version import VERSION

TITLE = "Moose Man"

DEFAULTS = {
    'sensitivity': 1.0, 'invert_y': False, 'fov': 75, 'brightness': 1.0, 'volume': 80,
    'res': '480p', 'grain': True, 'vhs': True, 'display': 'Windowed Fullscreen', 'show_fps': False,
    'auto_update': True,
}

SETTINGS_ITEMS = [
    ('sensitivity', 'Mouse Sensitivity', 'float', (0.2, 3.0, 0.1)),
    ('invert_y', 'Invert Mouse Y', 'bool', None),
    ('fov', 'Field of View', 'int', (60, 100, 5)),
    ('brightness', 'Brightness', 'float', (0.6, 2.0, 0.1)),
    ('volume', 'Master Volume', 'int', (0, 100, 10)),
    ('res', 'Render Resolution', 'choice', ['360p', '480p', '720p', 'Native']),
    ('grain', 'Film Grain', 'bool', None),
    ('vhs', 'Camcorder Effects', 'bool', None),
    ('display', 'Display Mode (restart)', 'choice', ['Windowed Fullscreen', 'Borderless', 'Fullscreen', 'Windowed']),
    ('show_fps', 'Show FPS', 'bool', None),
    ('auto_update', 'Auto Update', 'bool', None),
]


def settings_path():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    d = os.path.join(base, 'MooseMan')
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return os.path.join(d, 'settings.json')


def work_area_window():
    """Client size/position for a normal titled window that fills the desktop work area."""
    try:
        import ctypes
        from ctypes import wintypes
        rc = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rc), 0)  # SPI_GETWORKAREA
        gm = ctypes.windll.user32.GetSystemMetrics
        pad = gm(92)
        bx = gm(32) + pad
        by = gm(33) + pad
        cap = gm(4)
        w = rc.right - rc.left - 2 * bx
        h = rc.bottom - rc.top - cap - 2 * by
        if w > 320 and h > 240:
            return (w, h), (rc.left + bx, rc.top + cap + by)
    except Exception:
        pass
    return None


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(settings_path(), 'r') as f:
            s.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except Exception:
        pass
    return s


def save_settings(s):
    try:
        with open(settings_path(), 'w') as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass


def font(names, size, bold=False):
    try:
        f = pygame.font.SysFont(names, size, bold=bold)
        return f
    except Exception:
        return pygame.font.Font(None, size)


def wrap(text, fnt, width):
    lines = []
    for para in text.split('\n'):
        if not para.strip():
            lines.append('')
            continue
        words = para.split(' ')
        cur = ''
        for w in words:
            t = (cur + ' ' + w) if cur else w
            if fnt.size(t)[0] <= width:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


class Player:
    def __init__(self):
        self.reset(0, 0, 0, 0)

    def reset(self, x, y, z, yaw):
        self.x, self.y, self.z = x, y, z
        self.yaw = yaw
        self.pitch = 0.0
        self.vx = self.vz = 0.0
        self.vy = 0.0
        self.smooth_y = y
        self.crouch = 0.0
        self.stamina = 100.0
        self.exhausted = False
        self.bob = 0.0
        self.bob_amt = 0.0
        self.step_acc = 0.0
        self.sprinting = False
        self.fx, self.fz = math.sin(yaw), math.cos(yaw)

    def eye(self):
        by = math.sin(self.bob * 2.0) * 0.04 * self.bob_amt
        return (self.x, self.smooth_y + 1.62 - 0.62 * self.crouch + by, self.z)

    def fwd(self):
        cp = math.cos(self.pitch)
        return (math.sin(self.yaw) * cp, math.sin(self.pitch), math.cos(self.yaw) * cp)


class Game:
    def __init__(self, autotest=None):
        self.autotest = autotest
        self.settings = load_settings()
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
        pygame.mixer.pre_init(22050, -16, 2, 512)
        pygame.init()
        pygame.display.set_caption(TITLE)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
        info = pygame.display.Info()
        flags = pygame.OPENGL | pygame.DOUBLEBUF
        mode = 'Windowed' if autotest else self.settings.get('display', 'Windowed Fullscreen')
        dw, dh = info.current_w, info.current_h
        size = (min(1280, dw - 80), min(720, dh - 120))
        os.environ['SDL_VIDEO_CENTERED'] = '1'
        if mode == 'Fullscreen':
            size = (dw, dh)
            flags |= pygame.FULLSCREEN
        elif mode == 'Borderless':
            size = (dw, dh)
            os.environ.pop('SDL_VIDEO_CENTERED', None)
            os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
            flags |= pygame.NOFRAME
        elif mode == 'Windowed Fullscreen':
            wa = work_area_window()
            if wa:
                size, pos = wa
                os.environ.pop('SDL_VIDEO_CENTERED', None)
                os.environ['SDL_VIDEO_WINDOW_POS'] = '%d,%d' % pos
        try:
            self.screen = pygame.display.set_mode(size, flags, vsync=1)
        except Exception:
            self.screen = pygame.display.set_mode(size, flags)
        self.win_w, self.win_h = self.screen.get_size()
        self.ctx = moderngl.create_context()
        self.clock = pygame.time.Clock()

        self.f_hud = font("consolas,lucidaconsole,couriernew", 18, True)
        self.f_small = font("consolas,lucidaconsole,couriernew", 14, True)
        self.f_med = font("timesnewroman,georgia,serif", 26)
        self.f_menu = font("timesnewroman,georgia,serif", 30)
        self.f_title = font("timesnewroman,georgia,serif", 92, True)
        self.f_big = font("timesnewroman,georgia,serif", 56, True)
        self.f_typed = font("couriernew,consolas", 15, True)
        self.f_hand = font("inkfree,segoeprint,comicsansms", 18, True)
        self.f_msg = font("georgia,timesnewroman,serif", 21, False)
        self.f_msg.set_italic(True)

        tex = make_textures()
        self.r = Renderer(self.ctx, self.win_w, self.win_h, tex)
        self.r.set_resolution(self.settings['res'])
        self.ui = pygame.Surface((self.r.ui_w, self.r.ui_h), pygame.SRCALPHA)
        self.UW, self.UH = self.r.ui_w, self.r.ui_h

        self.loading_screen("summoning the woods...")
        self.world = World()
        self.world.build()
        prog = self.r.prog
        self.m_forest = Mesh(self.ctx, prog, self.world.forest_data)
        self.m_sewer = Mesh(self.ctx, prog, self.world.sewer_data)
        self.m_moon = Mesh(self.ctx, prog, self.world.moon_data)
        self.m_basin = Mesh(self.ctx, prog, self.world.basin_water_data)
        self.m_valve = Mesh(self.ctx, prog, valve_mesh())
        self.m_wheel = Mesh(self.ctx, prog, wheel_mesh())
        self.m_herd = Mesh(self.ctx, prog, herd_head_mesh())
        self.m_moose = {k: Mesh(self.ctx, prog, v) for k, v in moose_meshes().items()}
        self.loading_screen("listening for hooves...")
        self.audio = Audio(self.settings['volume'] / 100.0)

        self.player = Player()
        self.moose = Moose(self.world)
        self.state = 'title'
        self.menu_sel = 0
        self.settings_sel = 0
        self.settings_return = 'title'
        self.time = 0.0
        self.msgs = []
        self.post = {}
        self.fear = 0.0
        self.glitch = 0.0
        self.red = 0.0
        self.fade = 0.0
        self.running = True
        self.title_t = 0.0
        self.new_game()
        self.state = 'title'
        self.set_mouse(False)
        # updates: the check runs on its own thread and may never come back
        self.new_build = None        # an updater.Update once one is offered
        self.update_state = ""       # "", "working", "failed"
        self.update_got = 0.0
        self.quit_now = False        # set once the swap script has been started
        if not autotest:
            updater.tidy()
            updater.check_async(self._update_found)

    # ------------------------------------------------------------------ helpers
    def loading_screen(self, text):
        self.ui.fill((0, 0, 0, 255))
        img = self.f_med.render(text, True, (150, 140, 130))
        self.ui.blit(img, ((self.UW - img.get_width()) // 2, self.UH // 2))
        self.r.fbo.use()
        self.r.fbo.clear(0, 0, 0, 1)
        self.r.finish(pygame.image.tobytes(self.ui, 'RGBA'), 0, {'bright': 1})
        pygame.display.flip()
        pygame.event.pump()

    def set_mouse(self, grab):
        pygame.event.set_grab(grab)
        pygame.mouse.set_visible(not grab)
        if grab:
            pygame.mouse.get_rel()

    def message(self, text, dur=4.5):
        self.msgs = [m for m in self.msgs if m[0] != text]
        self.msgs.append([text, dur, dur])
        if len(self.msgs) > 3:
            self.msgs.pop(0)

    def set_objective(self, text):
        self.objective = text
        self.obj_t = 7.0

    def new_game(self):
        w = self.world
        for v in w.valves:
            v['done'] = False
            v['progress'] = 0.0
            v['angle'] = 0.0
        for n in w.notes.values():
            n['read'] = False
        for h in w.herd:
            h['yaw'] = h['base']
        w.drained = False
        w.set_valves_done(0)
        w.water_level = w.water_target
        p = self.player
        x, z = W.START
        p.reset(x, float(W.terrain_h(x, z)), z, 0.0)
        self.moose = Moose(self.world)
        self.flags = set()
        self.clock_t = 0.0
        self.app = None
        self.app_done = set()
        self.objective = "Find the Moose Man."
        self.obj_t = 8.0
        self.flash_on = True
        self.flash_dir = p.fwd()
        self.flicker_t = 0.0
        self.focus = None
        self.cricket_mute = 0.0
        self.heart_t = 0.0
        self.drip_t = 1.0
        self.whisper_t = random.uniform(35, 60)
        self.call_t = random.uniform(50, 80)
        self.phantom_t = random.uniform(70, 120)
        self.phantom = 0.0
        self.water_msg_t = 0.0
        self.valves_done = 0
        self.checkpoint = None
        self.scare_t = 0.0
        self.dead_t = 0.0
        self.note_id = None
        self.ending_page = 0
        self.ending_t = 0.0
        self.drain_t = 0.0
        self.msgs = []
        self.fear = 0.0

    def respawn(self):
        p = self.player
        x, z = cell_center(9, 18)
        p.reset(x, W.SEWER_FLOOR, z, 0.0)
        self.moose = Moose(self.world)
        self.moose.place_cell(35, 32)
        self.moose.state = 'roam'
        self.moose.grace = 8.0
        self.moose.timer = 3.0
        if self.valves_done >= 5:
            self.moose.hunt = True
        self.flash_on = True
        self.fear = 0.0
        self.red = 0.0
        self.glitch = 0.0
        self.message("You wake up in the dark. Your head is pounding.", 5)
        self.state = 'play'
        self.set_mouse(True)

    # ------------------------------------------------------------------ main loop
    def run(self):
        if self.autotest:
            return self.run_autotest()
        while self.running and not self.quit_now:
            dt = min(self.clock.tick(240) / 1000.0, 0.05)
            self.time += dt
            for ev in pygame.event.get():
                self.handle_event(ev)
            self.update(dt)
            self.render()
            pygame.display.flip()
        save_settings(self.settings)
        pygame.quit()

    # ------------------------------------------------------------------ events
    def ui_mouse(self):
        mx, my = pygame.mouse.get_pos()
        return mx * self.UW / self.win_w, my * self.UH / self.win_h

    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            self.running = False
            return
        st = self.state
        if ev.type in (pygame.WINDOWFOCUSLOST,) and st == 'play':
            self.pause()
            return
        if st == 'title':
            self.menu_event(ev, self.title_items(), self.title_action)
        elif st == 'update':
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.state = 'title'
                self.menu_sel = 0
                return
            self.menu_event(ev, self.update_items(), self.update_action)
        elif st == 'pause':
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.resume()
                return
            self.menu_event(ev, ['RESUME', 'SETTINGS', 'QUIT TO TITLE'], self.pause_action)
        elif st == 'settings':
            self.settings_event(ev)
        elif st == 'intro':
            if (ev.type == pygame.KEYDOWN or ev.type == pygame.MOUSEBUTTONDOWN) and self.intro_t > 2.5:
                self.start_play()
        elif st == 'play':
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    self.pause()
                elif ev.key == pygame.K_f:
                    self.flash_on = not self.flash_on
                    self.audio.play('click', 0.6)
                elif ev.key == pygame.K_TAB:
                    self.obj_t = 6.0
                elif ev.key == pygame.K_e:
                    self.interact_press()
            elif ev.type == pygame.MOUSEMOTION:
                sens = 0.0022 * self.settings['sensitivity']
                p = self.player
                p.yaw -= ev.rel[0] * sens
                dy = ev.rel[1] * sens * (-1 if self.settings['invert_y'] else 1)
                p.pitch = clamp(p.pitch - dy, -1.45, 1.45)
        elif st == 'note':
            if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_e, pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.state = 'play'
                self.audio.play('paper', 0.5)
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                self.state = 'play'
        elif st == 'dead':
            if ev.type == pygame.KEYDOWN and self.dead_t > 1.5:
                if ev.key == pygame.K_ESCAPE:
                    self.to_title()
                elif ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                    self.respawn()
        elif st == 'ending':
            if (ev.type == pygame.KEYDOWN or ev.type == pygame.MOUSEBUTTONDOWN) and self.ending_t > 3.0:
                self.ending_page += 1
                self.ending_t = 0.0
                if self.ending_page >= len(lore.ENDING_PAGES):
                    self.to_title()

    def menu_rects(self, items, y0):
        rects = []
        for i, it in enumerate(items):
            w, h = self.f_menu.size(it)
            x = 80
            y = y0 + i * 46
            rects.append(pygame.Rect(x - 10, y - 4, w + 40, h + 8))
        return rects

    def menu_event(self, ev, items, action):
        y0 = int(self.UH * 0.56)
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_UP, pygame.K_w):
                self.menu_sel = (self.menu_sel - 1) % len(items)
            elif ev.key in (pygame.K_DOWN, pygame.K_s):
                self.menu_sel = (self.menu_sel + 1) % len(items)
            elif ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                action(self.menu_sel)
        elif ev.type == pygame.MOUSEMOTION:
            ux, uy = self.ui_mouse()
            for i, rc in enumerate(self.menu_rects(items, y0)):
                if rc.collidepoint(ux, uy):
                    self.menu_sel = i
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            ux, uy = self.ui_mouse()
            for i, rc in enumerate(self.menu_rects(items, y0)):
                if rc.collidepoint(ux, uy):
                    self.menu_sel = i
                    action(i)

    def title_items(self):
        items = ['BEGIN', 'SETTINGS', 'QUIT']
        if self.new_build and self.update_state != 'working':
            items.append('UPDATE TO %s' % self.new_build.version)
        return items

    def update_items(self):
        if self.update_state == 'working':
            return ['NOT NOW']
        return ['UPDATE AND RESTART', 'NOT NOW']

    def update_action(self, i):
        self.audio.play('click', 0.5)
        items = self.update_items()
        if items[i] == 'UPDATE AND RESTART':
            self.start_download()
        else:
            self.state = 'title'
            self.menu_sel = 0

    def _update_found(self, found):
        """Called from the check thread; only sets fields."""
        self.new_build = found
        if found and self.settings.get('auto_update', True) and updater.CAN_INSTALL:
            self.start_download()

    def start_download(self):
        if not self.new_build or self.update_state == 'working':
            return
        self.update_state = 'working'
        self.update_got = 0.0

        def run():
            def progress(got, total):
                self.update_got = (got / float(total)) if total else 0.0
            staged = updater.download(self.new_build, progress)
            if not staged:
                self.update_state = 'failed'
                return
            save_settings(self.settings)
            if updater.install(staged):
                self.quit_now = True      # the batch file takes it from here
            else:
                self.update_state = 'failed'

        t = threading.Thread(target=run, name='update-download')
        t.daemon = True
        t.start()

    def title_action(self, i):
        self.audio.play('click', 0.5)
        if i == 3:
            self.state = 'update'
            self.menu_sel = 0
            return
        if i == 0:
            self.new_game()
            self.state = 'intro'
            self.intro_t = 0.0
        elif i == 1:
            self.settings_return = 'title'
            self.settings_sel = 0
            self.state = 'settings'
        else:
            self.running = False

    def pause_action(self, i):
        self.audio.play('click', 0.5)
        if i == 0:
            self.resume()
        elif i == 1:
            self.settings_return = 'pause'
            self.settings_sel = 0
            self.state = 'settings'
        else:
            self.to_title()

    def pause(self):
        self.state = 'pause'
        self.menu_sel = 0
        self.set_mouse(False)
        self.audio.loop('creak', 0)
        self.audio.pause()

    def resume(self):
        self.state = 'play'
        self.set_mouse(True)
        self.audio.unpause()

    def to_title(self):
        self.audio.unpause()
        self.audio.stop_all()
        self.new_game()
        self.state = 'title'
        self.menu_sel = 0
        self.set_mouse(False)

    def start_play(self):
        self.state = 'play'
        self.set_mouse(True)
        self.message("It's almost midnight. The trail goes north, toward the creek.", 6)

    def settings_rows(self):
        rows = []
        y = 108
        for i in range(len(SETTINGS_ITEMS) + 1):
            rows.append(pygame.Rect(self.UW // 2 - 300, y + i * 32 - 4, 600, 30))
        return rows

    def change_setting(self, idx, d):
        key, label, kind, rng = SETTINGS_ITEMS[idx]
        s = self.settings
        if kind == 'bool':
            s[key] = not s[key]
        elif kind == 'float':
            lo, hi, st = rng
            s[key] = round(clamp(s[key] + d * st, lo, hi), 2)
        elif kind == 'int':
            lo, hi, st = rng
            s[key] = int(clamp(s[key] + d * st, lo, hi))
        elif kind == 'choice':
            i = rng.index(s[key]) if s[key] in rng else 0
            s[key] = rng[(i + d) % len(rng)]
        if key == 'res':
            self.r.set_resolution(s['res'])
        if key == 'volume':
            self.audio.set_master(s['volume'] / 100.0)
        self.audio.play('click', 0.4)

    def leave_settings(self):
        save_settings(self.settings)
        self.state = self.settings_return
        self.menu_sel = 1

    def settings_event(self, ev):
        n = len(SETTINGS_ITEMS)
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self.leave_settings()
            elif ev.key in (pygame.K_UP, pygame.K_w):
                self.settings_sel = (self.settings_sel - 1) % (n + 1)
            elif ev.key in (pygame.K_DOWN, pygame.K_s):
                self.settings_sel = (self.settings_sel + 1) % (n + 1)
            elif ev.key in (pygame.K_LEFT, pygame.K_a) and self.settings_sel < n:
                self.change_setting(self.settings_sel, -1)
            elif ev.key in (pygame.K_RIGHT, pygame.K_d) and self.settings_sel < n:
                self.change_setting(self.settings_sel, 1)
            elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.settings_sel == n:
                    self.leave_settings()
                else:
                    self.change_setting(self.settings_sel, 1)
        elif ev.type == pygame.MOUSEMOTION:
            ux, uy = self.ui_mouse()
            for i, rc in enumerate(self.settings_rows()):
                if rc.collidepoint(ux, uy):
                    self.settings_sel = i
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            ux, uy = self.ui_mouse()
            for i, rc in enumerate(self.settings_rows()):
                if rc.collidepoint(ux, uy):
                    self.settings_sel = i
                    if i == n:
                        if ev.button == 1:
                            self.leave_settings()
                    elif ev.button in (1, 4):
                        self.change_setting(i, 1)
                    elif ev.button in (3, 5):
                        self.change_setting(i, -1)

    # ------------------------------------------------------------------ interaction
    def find_focus(self):
        p = self.player
        ex, ey, ez = p.eye()
        f = p.fwd()
        best = None
        bestd = -1
        cands = []
        for nid, n in self.world.notes.items():
            cands.append(('note', nid, n['pos']))
        for i, v in enumerate(self.world.valves):
            if not v['done']:
                cands.append(('valve', i, v['pos']))
        if self.world.ladder_pos:
            cands.append(('ladder', 0, self.world.ladder_pos))
        for kind, key, pos in cands:
            dx, dy, dz = pos[0] - ex, pos[1] - ey, pos[2] - ez
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if d > 2.3 or d < 1e-3:
                continue
            dot = (dx * f[0] + dy * f[1] + dz * f[2]) / d
            need = 0.86 if d > 1.0 else 0.7
            if dot > need and dot > bestd:
                bestd = dot
                best = (kind, key)
        return best

    def interact_press(self):
        if not self.focus:
            return
        kind, key = self.focus
        if kind == 'note':
            self.note_id = key
            self.world.notes[key]['read'] = True
            self.state = 'note'
            self.audio.play('paper', 0.8)
            if key == 'memo' and self.valves_done < 5:
                self.set_objective("Open the five relief valves to drain Chamber C. (%d/5)" % self.valves_done)
                self.flags.add('memo')
        elif kind == 'ladder':
            if self.world.drained or self.valves_done >= 5:
                self.start_ending()
            else:
                self.message("The ladder is on the other side of the water.")

    def valve_complete(self, v):
        v['done'] = True
        self.valves_done = sum(1 for x in self.world.valves if x['done'])
        self.audio.loop('creak', 0)
        self.audio.play('clunk', 0.9)
        self.world.set_valves_done(self.valves_done)
        self.moose.hear(v['pos'][0], v['pos'][2], 40.0)
        if self.valves_done < 5:
            self.message("The valve locks open. Somewhere, water gurgles. (%d/5)" % self.valves_done)
            self.set_objective("Open the five relief valves to drain Chamber C. (%d/5)" % self.valves_done)
        else:
            self.message("A deep groan runs through the pipes. Chamber C is draining.", 6)
            self.set_objective("Chamber C is draining. Get to the service ladder.")
            self.audio.play('drain', 1.0)
            self.drain_t = 0.0
            self.flags.add('alldone')
            self.moose.hunt = True
            if self.moose.state not in ('chase', 'inactive'):
                self.moose.state = 'roam'
                self.moose.path = []
                self.moose.repath_t = 0
            self.audio.play('call_far', 1.0)

    def start_ending(self):
        self.state = 'ending'
        self.ending_page = 0
        self.ending_t = 0.0
        self.set_mouse(False)
        self.audio.stop_all()
        self.audio.stop_loops()

    def kill(self):
        if self.state != 'play':
            return
        self.state = 'scare'
        self.scare_t = 0.0
        self.audio.stop_all()
        self.audio.stop_loops()
        self.audio.play('screech', 1.0)
        self.audio.play('stinger', 1.0)

    # ------------------------------------------------------------------ update
    def update(self, dt):
        st = self.state
        if st == 'title':
            self.title_t += dt
            self.audio.loop('title_amb', 0.8)
            self.audio.loop('forest_amb', 0.35)
            self.audio.loop('sewer_amb', 0)
            self.audio.loop('breath', 0)
        elif st == 'intro':
            self.intro_t += dt
            self.audio.loop('title_amb', 0.5)
            self.audio.loop('forest_amb', 0.3)
            if self.intro_t > 22:
                self.start_play()
        elif st == 'play':
            self.update_play(dt)
        elif st == 'scare':
            self.scare_t += dt
            if self.scare_t > 1.7:
                self.state = 'dead'
                self.dead_t = 0.0
                self.set_mouse(False)
        elif st == 'dead':
            self.dead_t += dt
            self.audio.loop('title_amb', 0.6)
        elif st == 'ending':
            self.ending_t += dt
            self.audio.loop('title_amb', 0.6)
        for m in self.msgs:
            if st == 'play':
                m[1] -= dt
        self.msgs = [m for m in self.msgs if m[1] > 0]

    def update_play(self, dt):
        p = self.player
        w = self.world
        self.clock_t += dt
        keys = pygame.key.get_pressed()
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
        c, r = cell_of(p.x, p.z)
        k = w.kind(c, r) if r >= 0 else 'f'
        in_water = k == '~' and p.y < -5.3
        if in_water:
            speed *= 0.65
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
        nx = p.x + p.vx * dt
        nz = p.z + p.vz * dt
        nx, nz, hitw = w.collide(nx, nz, 0.3, p.y)
        nx, nz = w.collide_extra(nx, nz, 0.3)
        moved = math.hypot(nx - p.x, nz - p.z)
        p.x, p.z = nx, nz
        if hitw:
            self.water_msg_t -= dt
            if self.water_msg_t <= 0:
                self.water_msg_t = 7.0
                if self.valves_done >= 5:
                    self.message("It's still draining...")
                else:
                    self.message("The water is black and deep. Something pale is drifting under the surface.", 5)
                    if 'memo' not in self.flags:
                        self.set_objective("Find a way to drain the water.")
        g = w.ground_at(p.x, p.z)
        if g is None:
            g = p.y
        if g >= p.y:
            p.y = g
            p.vy = 0.0
        else:
            p.vy -= 18.0 * dt
            p.y += p.vy * dt
            if p.y <= g:
                if p.vy < -7:
                    self.audio.play_rand('step_conc', 4, 1.0)
                    self.audio.play('heart', 0.6)
                p.y = g
                p.vy = 0.0
        if p.y < p.smooth_y:
            p.smooth_y = p.y
        else:
            p.smooth_y += (p.y - p.smooth_y) * min(1.0, dt * 14)
        sp = moved / max(dt, 1e-4)
        p.bob_amt += (min(1.0, sp / 2.7) - p.bob_amt) * min(1.0, dt * 8)
        p.bob += moved * (2.0 if not sprint else 1.7)
        p.step_acc += moved
        stride = 0.55 if crouch else (1.0 if sprint else 0.78)
        if p.step_acc > stride:
            p.step_acc = 0.0
            self.footstep(k, crouch, sprint, in_water)
        # flashlight
        f = p.fwd()
        a = min(1.0, dt * 16)
        self.flash_dir = tuple(self.flash_dir[i] + (f[i] - self.flash_dir[i]) * a for i in range(3))
        self.flicker_t = max(0.0, self.flicker_t - dt)
        if self.fear > 0.35 and random.random() < dt * self.fear * 3:
            self.flicker_t = random.uniform(0.04, 0.22)

        self.audio.set_listener(p.x, p.z, p.yaw)
        self.update_events(dt)
        self.update_moose(dt)
        self.update_valves(dt, keys)
        self.update_herd(dt)
        self.update_ambience(dt)
        # water level
        if abs(w.water_level - w.water_target) > 0.001:
            rate = 0.12 if self.valves_done < 5 else 0.45
            if w.water_level > w.water_target:
                w.water_level = max(w.water_target, w.water_level - rate * dt)
            else:
                w.water_level = min(w.water_target, w.water_level + rate * dt)
        if self.valves_done >= 5 and not w.drained and w.water_level < -7.85:
            w.drained = True
            self.message("The water is gone. The stairs lead down... and up the other side.", 5)
        self.focus = self.find_focus()
        self.obj_t = max(0.0, self.obj_t - dt)
        self.phantom = max(0.0, self.phantom - dt)
        self.glitch += ((0.9 if self.phantom > 0 else 0.0) - self.glitch) * min(1.0, dt * 20)

    def footstep(self, k, crouch, sprint, in_water):
        p = self.player
        vol = 0.25 if crouch else (0.85 if sprint else 0.5)
        if k == 'f':
            self.audio.play_rand('step_grass', 4, vol)
            rad = 2.0 if crouch else (10 if sprint else 5)
        elif in_water:
            self.audio.play_rand('step_water', 3, vol * 1.2)
            rad = 5.0 if crouch else (20 if sprint else 11)
        elif k == 't' and random.random() < 0.5:
            self.audio.play_rand('step_water', 3, vol * 0.6)
            rad = 3.0 if crouch else (16 if sprint else 7)
        else:
            self.audio.play_rand('step_conc', 4, vol)
            rad = 2.5 if crouch else (16 if sprint else 7)
        self.moose.hear(p.x, p.z, rad)

    def update_valves(self, dt, keys):
        turning = False
        for i, v in enumerate(self.world.valves):
            if v['done']:
                continue
            if self.focus == ('valve', i) and keys[pygame.K_e]:
                turning = True
                v['progress'] += dt / 2.8
                v['angle'] += dt * 2.2
                self.valve_noise_t = getattr(self, 'valve_noise_t', 0) - dt
                if self.valve_noise_t <= 0:
                    self.valve_noise_t = 0.5
                    self.moose.hear(v['pos'][0], v['pos'][2], 24.0)
                if v['progress'] >= 1.0:
                    self.valve_complete(v)
                    turning = False
        self.audio.loop('creak', 0.7 if turning else 0.0)
        self.turning = turning

    def update_herd(self, dt):
        p = self.player
        if self.world.room_of(p.x, p.z) not in ('holding', 'holding_hall'):
            return
        ex, ey, ez = p.eye()
        f = p.fwd()
        lim = math.cos(math.radians(self.settings['fov'] * 0.75))
        for h in self.world.herd:
            hx, hy, hz = h['pos']
            dx, dy, dz = hx - ex, hy - ey, hz - ez
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            dot = (dx * f[0] + dy * f[1] + dz * f[2]) / max(d, 1e-4)
            want = math.atan2(p.x - hx, p.z - hz)
            if dot < lim and random.random() < dt * 0.7:
                if abs((want - h['yaw'] + math.pi) % (2 * math.pi) - math.pi) > 0.3:
                    h['yaw'] = want
                    self.audio.play3d('snap', hx, hz, 14, 0.35)

    def update_events(self, dt):
        p = self.player
        w = self.world
        fl = self.flags
        room = w.room_of(p.x, p.z)
        # ---- forest apparitions
        for i, zt in enumerate((-30.0, 2.0, 29.0)):
            if p.z > zt and i not in self.app_done and self.app is None and room == 'forest':
                self.app_done.add(i)
                self.spawn_apparition(i)
        if self.app:
            self.update_apparition(dt)
        if p.z > -6 and 'snap' not in fl:
            fl.add('snap')
            self.audio.play('snap', 0.9, pan=random.choice((-0.7, 0.7)))
            self.message("Something stepped on a branch. Close.", 3)
        if p.z > 17 and 'farcall' not in fl:
            fl.add('farcall')
            self.audio.play('call_far', 0.9, pan=0.4)
            self.cricket_mute = 6.0
        if p.z > 38 and 'whisper1' not in fl:
            fl.add('whisper1')
            self.audio.play('whisper', 0.5, pan=-0.5)
        # ---- underground
        if room == 'tunnel' and 'tunnel' not in fl:
            fl.add('tunnel')
            self.message("The drain smells like wet fur and pennies.", 4.5)
            self.set_objective("Follow the storm drain.")
        if room == 'tunnel' and 'tunnelcall' not in fl:
            c, r = cell_of(p.x, p.z)
            if w.tunnel_dist.get((c, r), 0) > 18:
                fl.add('tunnelcall')
                self.audio.play('call_far', 1.0)
                self.message("That wasn't an animal.", 3)
        if room == 'junction' and 'junction' not in fl:
            fl.add('junction')
            self.checkpoint = True
            self.message("Something has been living down here.", 4)
            self.set_objective("Find a way through the overflow system.")
        if room == 'gallery' and 'gallery' not in fl:
            fl.add('gallery')
            m = self.moose
            m.place_cell(20, 26)
            m.state = 'intro'
            m.timer = 5.0
            m.yaw = math.atan2(p.x - m.x, p.z - m.z)
            self.audio.play('stinger', 0.8)
            self.audio.play3d('call_near', m.x, m.z, 60, 0.9)
        if room == 'holding' and 'holding' not in fl:
            fl.add('holding')
            self.audio.play('whisper', 0.7, pan=0.3)
            self.message("They're all so still.", 3)
        if room == 'chamber' and 'chamber' not in fl:
            fl.add('chamber')
            if self.valves_done < 5:
                self.message("Chamber C. The water is too deep to cross.", 4)
        if room == 'nest' and 'nest' not in fl:
            fl.add('nest')
            self.message("This is where it sleeps.", 3.5)
        # ---- random sewer scares
        under = p.z > 50
        if under:
            self.drip_t -= dt
            if self.drip_t <= 0:
                self.drip_t = random.uniform(0.6, 2.2)
                pts = [d for d in w.drip_points if abs(d[0] - p.x) + abs(d[1] - p.z) < 22]
                if pts:
                    x, z = random.choice(pts)
                    self.audio.play3d('drip', x, z, 22, 0.7)
        if 'gallery' in fl:
            self.whisper_t -= dt
            if self.whisper_t <= 0:
                self.whisper_t = random.uniform(40, 80)
                self.audio.play('whisper', 0.45, pan=random.uniform(-1, 1))
            m = self.moose
            dm = math.hypot(m.x - p.x, m.z - p.z)
            self.call_t -= dt
            if self.call_t <= 0:
                self.call_t = random.uniform(45, 90)
                if dm > 18 and m.state != 'chase':
                    self.audio.play3d('call_far', m.x, m.z, 90, 0.9)
            self.phantom_t -= dt
            if self.phantom_t <= 0:
                self.phantom_t = random.uniform(70, 140)
                if m.state not in ('chase',) and dm > 14:
                    self.phantom = 0.09
                    self.audio.play('static', 0.6)

    def spawn_apparition(self, i):
        p = self.player
        if i == 2:
            x, z = 0.0, 49.0
            self.app = {'x': x, 'z': z, 'y': 0.0, 'yaw': math.pi, 't': 0.0, 'look': 0.0, 'kind': 'culvert', 'leave': 0.0, 'phase': 0.0}
            self.cricket_mute = 30.0
            return
        side = random.choice((-1, 1))
        fx, fz = math.sin(p.yaw), math.cos(p.yaw)
        x = p.x + fx * 26 + (-fz) * side * 7
        z = p.z + fz * 26 + fx * side * 7
        for _ in range(12):
            if not self.world.near_tree(x, z, 1.2):
                break
            x += random.uniform(-2, 2)
            z += random.uniform(-2, 2)
        z = min(z, 44.0)
        y = float(W.terrain_h(x, z))
        self.app = {'x': x, 'z': z, 'y': y, 'yaw': math.atan2(p.x - x, p.z - z), 't': 0.0, 'look': 0.0, 'kind': 'stand', 'leave': 0.0, 'phase': 0.0}
        self.cricket_mute = 20.0

    def update_apparition(self, dt):
        a = self.app
        p = self.player
        a['t'] += dt
        ex, ey, ez = p.eye()
        dx, dz = a['x'] - p.x, a['z'] - p.z
        d = math.hypot(dx, dz)
        f = p.fwd()
        dot = (dx * f[0] + dz * f[2]) / max(d, 1e-4)
        looking = dot > 0.95
        if looking:
            a['look'] += dt
        if a['kind'] == 'stand':
            a['yaw'] = math.atan2(p.x - a['x'], p.z - a['z'])
            if d < 13 or a['look'] > 1.3 or a['t'] > 16:
                self.vanish()
        else:
            if a['leave'] <= 0 and (d < 19 or a['look'] > 2.0):
                a['leave'] = 0.01
            if a['leave'] > 0:
                a['leave'] += dt
                a['yaw'] = Moose._turn(a['yaw'], 0.0, dt * 4)
                if a['leave'] > 0.6:
                    a['z'] += 1.4 * dt
                    a['phase'] += 1.4 * dt * 2.1
                    a['y'] = self.world.floor_at(a['x'], a['z']) or 0.0
                if a['z'] > 54 or a['leave'] > 6:
                    self.app = None
                    self.cricket_mute = 3.0
            if a['t'] > 40 and a['leave'] <= 0:
                a['leave'] = 0.01

    def vanish(self):
        self.app = None
        self.flicker_t = 0.3
        self.audio.play('static', 0.35)
        self.cricket_mute = 4.0

    def update_moose(self, dt):
        m = self.moose
        p = self.player
        if not m.active:
            self.fear += (0.0 - self.fear) * min(1.0, dt * 2)
            if self.app:
                d = math.hypot(self.app['x'] - p.x, self.app['z'] - p.z)
                self.fear = max(self.fear, clamp(1 - d / 30, 0, 0.45))
            self.audio.loop('breath', 0)
            return
        m.update(dt, p, self.flash_on and self.flicker_t <= 0)
        for ev in m.events:
            if ev == 'step':
                self.audio.play3d('mstep', m.x, m.z, 32, 1.0)
            elif ev == 'chase_start':
                self.audio.play3d('call_near', m.x, m.z, 50, 1.0)
                self.audio.play('stinger', 0.6)
            elif ev == 'kill':
                self.kill()
        m.events = []
        d = math.hypot(m.x - p.x, m.z - p.z)
        los = d < 30 and self.world.los(m.x, m.z, p.x, p.z)
        tf = clamp(1 - d / 18, 0, 1) * (1.0 if los else 0.45)
        if m.state == 'chase':
            tf = max(tf, 0.55)
        self.fear += (tf - self.fear) * min(1.0, dt * 3)
        self.audio.loop3d('breath', m.x, m.z, 16, 1.0)
        if self.fear > 0.15:
            self.heart_t -= dt
            if self.heart_t <= 0:
                self.heart_t = 1.05 - 0.6 * self.fear
                self.audio.play('heart', 0.25 + 0.6 * self.fear)

    def update_ambience(self, dt):
        p = self.player
        t = clamp((p.z - 47.0) / 8.0, 0, 1)
        self.cricket_mute = max(0.0, self.cricket_mute - dt)
        fv = 0.55 * (1 - t) * (0.2 if self.cricket_mute > 0 else 1.0)
        self.audio.loop('forest_amb', fv)
        self.audio.loop('sewer_amb', 0.6 * t)
        self.audio.loop('title_amb', 0.0)

    # ------------------------------------------------------------------ rendering
    def env(self, z):
        t = clamp((z - 47.0) / 7.0, 0, 1)
        fa = (0.045, 0.05, 0.068)
        ua = (0.016, 0.015, 0.016)
        fm = (0.11, 0.12, 0.17)
        ff = (0.012, 0.016, 0.024)
        lerp = lambda a, b: tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
        return {'ambient': lerp(fa, ua), 'mooncol': lerp(fm, (0, 0, 0)), 'moondir': self.world.moon_dir,
                'fog': lerp(ff, (0.0, 0.0, 0.0)), 'fogdens': 0.042 + 0.0 * t}

    def gather_lights(self, cx, cz):
        out = []
        t = self.time
        for i, L_ in enumerate(self.world.lights):
            x, y, z = L_['pos']
            d = math.hypot(x - cx, z - cz)
            if d > L_['rad'] + 30:
                continue
            fk = L_['flicker']
            if fk == 'soft':
                k = 0.88 + 0.12 * math.sin(t * 13 + i * 2.1)
            elif fk == 'bad':
                k = 1.0 if (math.sin(t * 7.3 + i * 3) + math.sin(t * 17.1 + i)) > -1.3 else 0.06
                k *= 0.85 + 0.15 * math.sin(t * 31 + i)
            elif fk == 'fire':
                k = 0.7 + 0.3 * math.sin(t * 9 + i) * math.sin(t * 5.3 + 1.7)
            else:
                k = 1.0
            if self.fear > 0.5 and random.random() < 0.15:
                k *= 0.2
            col = L_['col']
            k *= 1.9
            out.append((d, ((x, y, z), L_['rad'], (col[0] * k, col[1] * k, col[2] * k))))
        out.sort(key=lambda o: o[0])
        return [o[1] for o in out[:8]]

    def draw_world(self, cam, fwd, flash, flash_pos, flash_dir, moose_parts_list, fov=None):
        r = self.r
        lights = self.gather_lights(cam[0], cam[2])
        r.begin(cam, fwd, fov or self.settings['fov'], self.env(cam[2]), self.time, flash, flash_pos, flash_dir, lights)
        r.draw(self.m_forest)
        r.draw(self.m_sewer)
        if cam[2] < 60:
            r.draw(self.m_moon, nofog=True)
        wl = self.world.water_level
        if wl > -8.25:
            r.draw(self.m_basin, model=T(0, wl, 0))
        for v in self.world.valves:
            M = T(*v['pos']) @ RY(v['yaw'])
            r.draw(self.m_valve, model=M)
            r.draw(self.m_wheel, model=M @ RZ(v['angle']))
        for h in self.world.herd:
            r.draw(self.m_herd, model=T(*h['pos']) @ RY(h['yaw']) @ S(0.8 + 0.15 * h['scale']))
        for parts in moose_parts_list:
            for key, M in parts:
                r.draw(self.m_moose[key], model=M)

    def post_params(self, extra=None):
        p = {'grain': 1.0 if self.settings['grain'] else 0.0, 'vhs': 1.0 if self.settings['vhs'] else 0.0,
             'bright': self.settings['brightness'] * 1.15, 'fear': self.fear, 'red': self.red, 'glitch': self.glitch, 'fade': self.fade}
        if extra:
            p.update(extra)
        return p

    def render(self):
        self.ui.fill((0, 0, 0, 0))
        st = self.state
        post = None
        if st in ('title', 'settings', 'update') and (st != 'settings' or self.settings_return == 'title'):
            self.render_title_scene()
            post = self.post_params({'fear': 0.15, 'glitch': self.title_glitch()})
            if st == 'title':
                self.draw_title_ui()
            elif st == 'update':
                self.draw_update_ui()
            else:
                self.draw_settings_ui()
        elif st == 'intro':
            self.r.fbo.use()
            self.r.fbo.clear(0, 0, 0, 1)
            self.draw_intro_ui()
            post = self.post_params({'fear': 0.0})
        elif st in ('play', 'pause', 'note', 'settings'):
            self.render_play_scene()
            post = self.post_params()
            if st == 'play':
                self.draw_hud()
            elif st == 'note':
                self.draw_hud(minimal=True)
                self.draw_note()
            elif st == 'pause':
                self.ui.fill((0, 0, 0, 160))
                self.draw_menu(['RESUME', 'SETTINGS', 'QUIT TO TITLE'], "PAUSED")
            else:
                self.ui.fill((0, 0, 0, 190))
                self.draw_settings_ui()
        elif st == 'scare':
            self.render_scare()
            k = self.scare_t
            post = self.post_params({'fear': 1.0, 'glitch': 1.0 if k < 1.2 else 1.4, 'red': 0.5 + 0.5 * math.sin(k * 40) ** 2,
                                     'fade': clamp((k - 1.3) / 0.4, 0, 1)})
        elif st == 'dead':
            self.r.fbo.use()
            self.r.fbo.clear(0.05, 0, 0, 1)
            self.draw_dead_ui()
            post = self.post_params({'fear': 0.6, 'glitch': 0.1})
        elif st == 'ending':
            self.r.fbo.use()
            self.r.fbo.clear(0, 0, 0, 1)
            self.draw_ending_ui()
            post = self.post_params({'fear': 0.0})
        if self.settings['show_fps']:
            img = self.f_small.render("%d fps" % self.clock.get_fps(), True, (200, 200, 200))
            self.ui.blit(img, (self.UW - img.get_width() - 10, self.UH - 20))
        self.r.finish(pygame.image.tobytes(self.ui, 'RGBA'), self.time, post)

    def title_glitch(self):
        t = self.title_t % 7.0
        return 1.0 if t > 6.82 else 0.0

    def render_title_scene(self):
        t = self.title_t
        cam = (0.6 + math.sin(t * 0.13) * 0.4, float(W.terrain_h(0.6, -34)) + 1.7 + math.sin(t * 0.4) * 0.03, -34.0)
        yaw = math.sin(t * 0.07) * 0.08 + 0.05
        pitch = 0.03 + math.sin(t * 0.21) * 0.02
        fwd = (math.sin(yaw) * math.cos(pitch), math.sin(pitch), math.cos(yaw) * math.cos(pitch))
        stage = int(t // 7.0) % 4
        spots = [(-3.0, -12.0), (1.5, -18.0), (-0.8, -23.5), (0.6, -28.5)]
        x, z = spots[stage]
        y = float(W.terrain_h(x, z))
        yawm = math.atan2(cam[0] - x, cam[2] - z)
        roll = 0.5 if (t % 3.1) > 2.6 else 0.0
        parts = pose_moose(x, y, z, yawm, 0, 0, roll=roll)[0]
        light_pos = (cam[0] + 0.3, cam[1] - 0.2, cam[2])
        self.draw_world(cam, fwd, 0.55, light_pos, fwd, [parts], fov=60)

    def render_play_scene(self):
        p = self.player
        cam = p.eye()
        fwd = p.fwd()
        rx, rz = -math.cos(p.yaw), math.sin(p.yaw)
        fpos = (cam[0] + rx * 0.18, cam[1] - 0.12, cam[2] + rz * 0.18)
        flash = 0.0
        if self.flash_on:
            flash = 0.05 if self.flicker_t > 0 else 1.0
        parts = []
        m = self.moose
        if m.active:
            parts.append(m.parts())
        if self.app:
            a = self.app
            walk = 1.0 if a.get('leave', 0) > 0.6 else 0.0
            parts.append(pose_moose(a['x'], a['y'], a['z'], a['yaw'], a['phase'], walk,
                                    roll=0.6 if (self.time % 2.7) > 2.2 else 0.0)[0])
        if self.phantom > 0:
            parts.append(self.face_parts(cam, fwd, p.yaw, 0.9))
        self.draw_world(cam, fwd, flash, fpos, self.flash_dir, parts)

    def face_parts(self, cam, fwd, yaw, dist):
        roll = random.uniform(-0.35, 0.35)
        jaw = 0.6 + random.uniform(0, 0.3)
        _, head = pose_moose(0, 0, 0, yaw + math.pi, 0.0, 0.0, hunch=0.45, roll=roll, jaw=jaw, reach=1.0)
        hx, hy, hz = float(head[0, 3]), float(head[1, 3]) + 0.05, float(head[2, 3])
        tx = cam[0] + math.sin(yaw) * dist
        tz = cam[2] + math.cos(yaw) * dist
        ty = cam[1] - 0.05
        return pose_moose(tx - hx, ty - hy, tz - hz, yaw + math.pi, 0.0, 0.0, hunch=0.45,
                          roll=roll, jaw=jaw, reach=1.0)[0]

    def render_scare(self):
        p = self.player
        cam = p.eye()
        k = self.scare_t
        sh = 0.04 if k < 1.2 else 0.0
        cam = (cam[0] + random.uniform(-sh, sh), cam[1] + random.uniform(-sh, sh), cam[2])
        yaw = p.yaw + random.uniform(-0.03, 0.03)
        fwd = (math.sin(yaw), 0.0, math.cos(yaw))
        parts = [self.face_parts(cam, fwd, yaw, 1.15 - min(k, 1.0) * 0.35)]
        fpos = (cam[0], cam[1] - 0.25, cam[2])
        self.draw_world(cam, fwd, 0.55, fpos, fwd, parts)

    # ------------------------------------------------------------------ UI drawing
    def blit_text(self, txt, fnt, color, pos, anchor='topleft', alpha=255, shadow=True):
        img = fnt.render(txt, True, color)
        if alpha < 255:
            img.set_alpha(alpha)
        rc = img.get_rect(**{anchor: pos})
        if shadow:
            sh = fnt.render(txt, True, (0, 0, 0))
            if alpha < 255:
                sh.set_alpha(alpha)
            self.ui.blit(sh, rc.move(2, 2))
        self.ui.blit(img, rc)
        return rc

    def draw_title_ui(self):
        t = self.title_t
        cx = self.UW // 2
        jit = random.uniform(-2, 2) if random.random() < 0.08 else 0
        for i in range(3):
            off = (random.uniform(-3, 3), random.uniform(-2, 2)) if random.random() < 0.3 else (0, 0)
            img = self.f_title.render("MOOSE MAN", True, (120, 0, 0))
            img.set_alpha(70)
            self.ui.blit(img, img.get_rect(midtop=(cx + off[0] + jit, 70 + off[1])))
        self.blit_text("MOOSE MAN", self.f_title, (205, 195, 180), (cx + jit, 70), 'midtop')
        self.blit_text("HOLLINS WOODS  -  OCTOBER 31, 2003", self.f_hud, (150, 140, 130), (cx, 180), 'midtop')
        self.draw_menu(self.title_items(), None)
        self.blit_text("headphones recommended. play in the dark.", self.f_small, (110, 105, 100), (cx, self.UH - 30), 'midtop')
        self.blit_text("v" + VERSION, self.f_small, (110, 105, 100), (cx, 204), 'midtop')
        if self.new_build and self.update_state == 'working':
            self.draw_update_bar(80, int(self.UH * 0.56) + 3 * 46 + 8)
        elif self.update_state == 'failed':
            self.blit_text("update failed -- try again, or download it from github.com/%s/releases" % updater.repo_path(),
                           self.f_small, (200, 90, 80), (80, int(self.UH * 0.56) + 4 * 46 + 4))
        self.draw_osd(title=True)

    def draw_update_bar(self, x, y):
        w = 300
        pygame.draw.rect(self.ui, (40, 36, 38, 220), (x, y, w, 12))
        pygame.draw.rect(self.ui, (196, 50, 40, 255), (x, y, int(w * self.update_got), 12))
        pygame.draw.rect(self.ui, (12, 11, 12, 255), (x, y, w, 12), 2)
        self.blit_text("updating to %s  -  %d%%" % (self.new_build.version, int(self.update_got * 100)),
                       self.f_small, (190, 160, 150), (x, y + 18))

    def draw_update_ui(self):
        self.ui.fill((0, 0, 0, 200))
        cx = self.UW // 2
        b = self.new_build
        self.blit_text("UPDATE AVAILABLE", self.f_big, (200, 40, 30), (cx, 40), 'midtop')
        if b:
            self.blit_text("you have %s  -  %s is out" % (VERSION, b.version), self.f_hud, (180, 170, 160), (cx, 108), 'midtop')
            y = 140
            for raw in (b.notes or "").split("\n")[:6]:
                self.blit_text(raw[:80], self.f_small, (160, 150, 140), (cx, y), 'midtop')
                y += 22
        if not updater.CAN_INSTALL:
            self.blit_text("download it from github.com/%s/releases" % updater.repo_path(), self.f_small,
                           (180, 170, 160), (cx, 270), 'midtop')
        if self.update_state == 'working' and b:
            self.draw_update_bar(cx - 150, 272)
        elif self.update_state == 'failed':
            self.blit_text("that did not work -- try again, or grab it from github.com/%s/releases" % updater.repo_path(),
                           self.f_small, (206, 96, 84), (cx, 272), 'midtop')
        self.draw_menu(self.update_items(), None)

    def draw_menu(self, items, header):
        y0 = int(self.UH * 0.56)
        if header:
            self.blit_text(header, self.f_big, (200, 190, 180), (80, y0 - 90))
        for i, it in enumerate(items):
            sel = i == self.menu_sel
            col = (210, 40, 30) if sel else (170, 165, 155)
            x = 80 + (12 if sel else 0)
            if sel and random.random() < 0.05:
                x += random.randint(-3, 3)
            self.blit_text(("> " if sel else "  ") + it, self.f_menu, col, (x - 20, y0 + i * 46))

    def draw_settings_ui(self):
        self.ui.fill((0, 0, 0, 170))
        self.blit_text("SETTINGS", self.f_big, (200, 190, 180), (self.UW // 2, 40), 'midtop')
        rows = self.settings_rows()
        for i, (key, label, kind, rng) in enumerate(SETTINGS_ITEMS):
            rc = rows[i]
            sel = i == self.settings_sel
            if sel:
                pygame.draw.rect(self.ui, (80, 10, 10, 150), rc)
            v = self.settings[key]
            if kind == 'bool':
                vs = "ON" if v else "OFF"
            elif kind == 'float':
                vs = "%.1f" % v
            elif kind == 'int':
                vs = ("%d%%" % v) if key == 'volume' else str(v)
            else:
                vs = str(v)
            col = (230, 220, 210) if sel else (160, 155, 150)
            self.blit_text(label, self.f_hud, col, (rc.x + 14, rc.y + 6))
            self.blit_text("<  %s  >" % vs if sel else vs, self.f_hud, col, (rc.right - 14, rc.y + 6), 'topright')
        rc = rows[-1]
        sel = self.settings_sel == len(SETTINGS_ITEMS)
        if sel:
            pygame.draw.rect(self.ui, (80, 10, 10, 150), rc)
        self.blit_text("BACK", self.f_hud, (230, 220, 210) if sel else (160, 155, 150), (rc.centerx, rc.y + 6), 'midtop')
        self.blit_text("arrows / mouse to change  -  left click: next  right click: previous  -  ESC: back",
                       self.f_small, (120, 115, 110), (self.UW // 2, self.UH - 34), 'midtop')

    def draw_intro_ui(self):
        t = self.intro_t
        y = 110
        for i, ln in enumerate(lore.INTRO_TEXT):
            a = int(clamp((t - i * 0.55) / 1.2, 0, 1) * 255)
            if ln and a > 0:
                fnt = self.f_hud if i < 2 else self.f_msg
                colr = (200, 60, 50) if i < 2 else (190, 185, 175)
                self.blit_text(ln, fnt, colr, (self.UW // 2, y), 'midtop', alpha=a)
            y += 30
        if t > 2.5:
            a = int(clamp((t - 2.5) / 1.5, 0, 1) * 255)
            y = self.UH - 110
            for ln in lore.CONTROLS_TEXT:
                self.blit_text(ln, self.f_small, (140, 135, 130), (self.UW // 2, y), 'midtop', alpha=a)
                y += 22
            if int(t * 2) % 2 == 0:
                self.blit_text("press any key", self.f_small, (200, 190, 180), (self.UW // 2, self.UH - 40), 'midtop', alpha=a)

    def clock_str(self):
        base = 23 * 3600 + 58 * 60 + 7
        s = int(base + self.clock_t)
        day = s // 86400
        s %= 86400
        hh, mm, ss = s // 3600, (s // 60) % 60, s % 60
        ap = "PM" if hh >= 12 else "AM"
        h12 = hh % 12 or 12
        date = "OCT.31 2003" if day == 0 else "NOV. 1 2003"
        return "%s %2d:%02d:%02d" % (ap, h12, mm, ss), date

    def draw_osd(self, title=False):
        if not self.settings['vhs']:
            return
        t = self.time
        if int(t * 1.6) % 2 == 0:
            pygame.draw.circle(self.ui, (220, 20, 20), (34, 33), 7)
        self.blit_text("REC", self.f_hud, (235, 235, 235), (48, 22))
        self.blit_text("SP", self.f_hud, (235, 235, 235), (26, self.UH - 44))
        bx = self.UW - 80
        pygame.draw.rect(self.ui, (235, 235, 235), (bx, 24, 44, 18), 2)
        pygame.draw.rect(self.ui, (235, 235, 235), (bx + 44, 29, 4, 8))
        bars = 2 if not title else 3
        for i in range(bars):
            pygame.draw.rect(self.ui, (235, 235, 235), (bx + 4 + i * 13, 28, 10, 10))
        tm, date = self.clock_str()
        if self.fear > 0.55 and random.random() < 0.5:
            tm = "".join(random.choice("0123456789?:#") if ch.isdigit() else ch for ch in tm)
            date = random.choice(["??? ?? ????", "HE IS HERE", date, "DONT LOOK"])
        self.blit_text(tm, self.f_hud, (235, 235, 235), (self.UW - 26, self.UH - 66), 'topright')
        self.blit_text(date, self.f_hud, (235, 235, 235), (self.UW - 26, self.UH - 44), 'topright')

    def draw_hud(self, minimal=False):
        self.draw_osd()
        if minimal:
            return
        p = self.player
        cx, cy = self.UW // 2, self.UH // 2
        pygame.draw.circle(self.ui, (220, 220, 220, 120), (cx, cy), 2)
        if self.focus:
            kind, key = self.focus
            if kind == 'note':
                label = "[E] Read"
            elif kind == 'valve':
                v = self.world.valves[key]
                label = "[Hold E] Turn the valve"
                if v['progress'] > 0:
                    w = 160
                    pygame.draw.rect(self.ui, (0, 0, 0, 160), (cx - w // 2, cy + 52, w, 10))
                    pygame.draw.rect(self.ui, (190, 40, 30, 230), (cx - w // 2 + 1, cy + 53, int((w - 2) * min(1, v['progress'])), 8))
            else:
                label = "[E] Climb the ladder" if self.world.drained else "The ladder"
            self.blit_text(label, self.f_hud, (230, 225, 215), (cx, cy + 24), 'midtop')
        if p.stamina < 99:
            w = 120
            a = 200 if p.exhausted else 120
            pygame.draw.rect(self.ui, (0, 0, 0, 120), (cx - w // 2, self.UH - 40, w, 5))
            pygame.draw.rect(self.ui, (200, 60, 50, a) if p.exhausted else (200, 200, 200, a),
                             (cx - w // 2, self.UH - 40, int(w * p.stamina / 100), 5))
        y = self.UH - 120
        for m in reversed(self.msgs):
            txt, tl, td = m
            a = int(clamp(tl / 0.8, 0, 1) * clamp((td - tl) / 0.3, 0, 1) * 255)
            self.blit_text(txt, self.f_msg, (225, 215, 200), (cx, y), 'midtop', alpha=a)
            y -= 30
        if self.obj_t > 0:
            a = int(clamp(self.obj_t / 1.0, 0, 1) * 255)
            self.blit_text(self.objective, self.f_small, (210, 200, 185), (26, 56), alpha=a)
            n = sum(1 for nn in self.world.notes.values() if nn['read'])
            self.blit_text("notes found: %d/%d" % (n, len(lore.NOTES)), self.f_small, (150, 145, 135), (26, 76), alpha=a)

    def draw_note(self):
        title, style, text = lore.NOTES[self.note_id]
        fnt = self.f_hand if style == 'hand' else self.f_typed
        pw = 600
        lines = wrap(text, fnt, pw - 70)
        lh = fnt.get_linesize()
        ph = min(self.UH - 40, len(lines) * lh + 90)
        while len(lines) * lh + 90 > self.UH - 40 and lh > 12:
            lh -= 1
        self.ui.fill((0, 0, 0, 150))
        rc = pygame.Rect(0, 0, pw, ph)
        rc.center = (self.UW // 2, self.UH // 2)
        paper = (205, 196, 170, 250) if style == 'typed' else (190, 182, 160, 250)
        pygame.draw.rect(self.ui, paper, rc)
        pygame.draw.rect(self.ui, (120, 100, 80, 255), rc, 2)
        stains = pygame.Surface((pw, ph), pygame.SRCALPHA)
        rr = random.Random(sum(map(ord, self.note_id)))
        for i in range(7):
            pygame.draw.circle(stains, (110, 80, 50, 28), (rr.randint(20, pw - 20), rr.randint(20, ph - 20)), rr.randint(14, 46))
        self.ui.blit(stains, rc.topleft)
        hdr = self.f_small.render(title.upper(), True, (90, 30, 20))
        self.ui.blit(hdr, (rc.x + 34, rc.y + 18))
        y = rc.y + 48
        ink = (30, 25, 35) if style == 'hand' else (25, 22, 20)
        for ln in lines:
            if y > rc.bottom - 30:
                break
            img = fnt.render(ln, True, ink)
            self.ui.blit(img, (rc.x + 34, y))
            y += lh
        self.blit_text("[E] close", self.f_small, (220, 210, 200), (self.UW // 2, rc.bottom + 6), 'midtop')

    def draw_dead_ui(self):
        t = self.dead_t
        a = int(clamp(t / 1.2, 0, 1) * 255)
        cx = self.UW // 2
        j = random.uniform(-3, 3) if random.random() < 0.1 else 0
        self.blit_text("YOU STOPPED MOVING", self.f_big, (170, 15, 10), (cx + j, self.UH // 2 - 80), 'midtop', alpha=a)
        self.blit_text("the herd has room for one more.", self.f_msg, (170, 160, 150), (cx, self.UH // 2), 'midtop', alpha=a)
        if t > 1.5:
            self.blit_text("ENTER - wake up          ESC - title", self.f_hud, (200, 190, 180), (cx, self.UH // 2 + 70), 'midtop')

    def draw_ending_ui(self):
        lines = lore.ENDING_PAGES[self.ending_page]
        t = self.ending_t
        y = self.UH // 2 - len(lines) * 15
        for i, ln in enumerate(lines):
            a = int(clamp((t - i * 0.35) / 1.2, 0, 1) * 255)
            if ln and a > 0:
                big = ln.startswith("M O O S E")
                self.blit_text(ln, self.f_big if big else self.f_msg, (190, 30, 25) if big else (200, 195, 185),
                               (self.UW // 2, y), 'midtop', alpha=a)
            y += 56 if ln.startswith("M O O S E") else 30
        if t > 3.0 and int(t * 2) % 2 == 0:
            self.blit_text("press any key", self.f_small, (150, 145, 140), (self.UW // 2, self.UH - 40), 'midtop')

    # ------------------------------------------------------------------ autotest
    def snap(self, path):
        data = self.ctx.screen.read(viewport=(0, 0, self.win_w, self.win_h), components=3)
        surf = pygame.image.frombytes(data, (self.win_w, self.win_h), 'RGB', True)
        pygame.image.save(surf, path)

    def run_autotest(self):
        out = self.autotest
        os.makedirs(out, exist_ok=True)
        log = []
        dt = 1 / 60

        def frames(n):
            for _ in range(n):
                self.time += dt
                pygame.event.pump()
                self.update(dt)
                self.render()
                pygame.display.flip()

        def put(x, z, yaw, pitch=0.0):
            p = self.player
            g = self.world.ground_at(x, z)
            p.reset(x, g if g is not None else 0.0, z, yaw)
            p.pitch = pitch

        self.state = 'title'
        frames(30)
        self.snap(os.path.join(out, '01_title.png'))
        self.state = 'settings'
        self.settings_return = 'title'
        frames(2)
        self.snap(os.path.join(out, '02_settings.png'))
        self.new_game()
        self.state = 'intro'
        self.intro_t = 0
        frames(240)
        self.snap(os.path.join(out, '03_intro.png'))
        self.state = 'play'
        shots = [
            ('04_forest_start', W.START[0], W.START[1], 0.0, 0.0),
            ('05_flyer', 0.5, -22.5, math.pi / 2 * 0.95, 0.0),
            ('06_campfire', 6.0, 5.0, 0.9, -0.25),
            ('07_headwall', 0.5, 36.0, 0.0, 0.05),
            ('08_tunnel', *cell_center(5, 2), 0.0, 0.0),
            ('09_tunnel_mid', *cell_center(10, 6), -math.pi / 2, 0.0),
            ('10_junction', *cell_center(9, 17), 0.0, 0.0),
            ('11_gallery', *cell_center(9, 23), -math.pi / 2, 0.0),
            ('12_holding', *cell_center(20, 31), 0.0, 0.0),
            ('13_chamber', *cell_center(19, 39), 0.0, -0.2),
            ('14_nest', *cell_center(34, 30), 0.3, -0.2),
            ('15_pump', *cell_center(30, 16), math.pi, -0.1),
        ]
        for name, x, z, yaw, pitch in shots:
            put(x, z, yaw, pitch)
            self.flags.update({'snap', 'farcall', 'whisper1', 'gallery', 'tunnel', 'junction', 'tunnelcall', 'holding', 'chamber', 'nest'})
            self.app_done = {0, 1, 2}
            self.app = None
            frames(20)
            self.snap(os.path.join(out, name + '.png'))
            log.append("%s ok player=(%.1f %.1f %.1f)" % (name, self.player.x, self.player.y, self.player.z))
        # apparition
        self.app_done = set()
        put(0.0, -33.0, 0.0)
        frames(5)
        self.spawn_apparition(0)
        frames(10)
        self.snap(os.path.join(out, '16_apparition.png'))
        self.app = None
        # moose close-up
        put(*cell_center(9, 23), math.pi / 2)
        m = self.moose
        m.place_cell(14, 23)
        m.state = 'roam'
        m.timer = 100
        m.grace = 100
        m.yaw = math.atan2(self.player.x - m.x, self.player.z - m.z)
        frames(20)
        self.snap(os.path.join(out, '17_moose.png'))
        # note
        self.note_id = 'journal1'
        self.state = 'note'
        frames(2)
        self.snap(os.path.join(out, '18_note.png'))
        self.note_id = 'memo'
        frames(2)
        self.snap(os.path.join(out, '18b_note_memo.png'))
        self.state = 'play'
        # drain everything
        for v in self.world.valves:
            self.valve_complete(v)
        self.world.water_level = self.world.water_target
        put(*cell_center(19, 40), 0.0, -0.35)
        frames(30)
        self.snap(os.path.join(out, '19_chamber_drained.png'))
        log.append("drained=%s level=%.2f" % (self.world.drained, self.world.water_level))
        # walk down the stairs and across
        put(*cell_center(19, 40), 0.0)
        p = self.player
        for i in range(400):
            p.vx, p.vz = 0, 0
            nx, nz, _ = self.world.collide(p.x, p.z + 0.03, 0.3, p.y)
            p.x, p.z = nx, nz
            g = self.world.ground_at(p.x, p.z)
            if g is not None:
                p.y = min(p.y, g) if g < p.y else g
        log.append("stairs walk end z=%.2f y=%.2f (ladder z=%.2f)" % (p.z, p.y, self.world.ladder_pos[2]))
        # chase simulation
        self.moose = Moose(self.world)
        m = self.moose
        m.place_cell(30, 23)
        m.state = 'roam'
        m.timer = 0
        m.start_chase(0, 0)
        put(*cell_center(8, 23), 0.0)
        self.state = 'play'
        killed = False
        for i in range(60 * 40):
            m.update(dt, self.player, True)
            if 'kill' in m.events:
                killed = True
                log.append("killed after %.1fs, moose state=%s" % (i * dt, m.state))
                break
            m.events = []
        log.append("chase sim killed=%s state=%s pos=(%.1f,%.1f)" % (killed, m.state, m.x, m.z))
        # path checks
        for a, b in (((9, 17), (1, 36)), ((9, 17), (34, 13)), ((9, 17), (22, 17)), ((9, 17), (20, 37)), ((9, 17), (38, 35)), ((9, 17), (19, 47))):
            pth = self.world.astar(a, b)
            log.append("path %s->%s: %s" % (a, b, len(pth) if pth else None))
        # scare frame
        self.state = 'play'
        self.kill()
        frames(30)
        self.snap(os.path.join(out, '20_scare.png'))
        frames(90)
        frames(80)
        self.snap(os.path.join(out, '21_dead.png'))
        self.start_ending()
        frames(200)
        self.snap(os.path.join(out, '22_ending.png'))
        with open(os.path.join(out, 'log.txt'), 'w') as f:
            f.write("\n".join(log))
        print("\n".join(log))
        pygame.quit()


def main():
    autotest = None
    if '--autotest' in sys.argv:
        i = sys.argv.index('--autotest')
        autotest = sys.argv[i + 1] if i + 1 < len(sys.argv) else 'autotest_out'
    g = Game(autotest)
    g.run()


if __name__ == '__main__':
    main()
