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
from textures import make_textures, L, EMIS
import world as W
from world import World, cell_of, cell_center, clamp
from moose import Moose, pose_moose, pose_goat, car_parts, moose_meshes, valve_mesh, wheel_mesh, herd_head_mesh
from audio import Audio
import lore
import updater
from version import VERSION
import chapter2 as C2
import chapter3 as C3
from elk import pose_elk, elk_meshes
from engine import MeshBuilder
from ch4game import Ch4Mixin
from ch5game import Ch5Mixin
from coop import CoopMixin, PLAYISH

TITLE = "Moose Man"

DEFAULTS = {
    'sensitivity': 1.0, 'invert_y': False, 'fov': 75, 'brightness': 1.0, 'volume': 80,
    'res': '480p', 'grain': True, 'vhs': True, 'display': 'Windowed Fullscreen', 'show_fps': False,
    'auto_update': True, 'coop_name': '',
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


def C2_goat_parts(x, y, z, yaw, ph, amt, roll, chasing, t):
    """The Goat Man as he hunts you in Chapter 2: still bloody from the road."""
    return pose_goat(x, y, z, yaw, walk_phase=ph, walk_amt=amt, hunch=0.85 if chasing else 0.5,
                     arms=0.55 if chasing else 0.15, jaw=0.65 if chasing else 0.2, roll=roll, bloody=True, t=t)[0]


def progress_path():
    return os.path.join(os.path.dirname(settings_path()), 'progress.json')


def load_progress():
    try:
        with open(progress_path(), 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def save_progress(p):
    try:
        with open(progress_path(), 'w') as f:
            json.dump(p, f, indent=2)
    except Exception:
        pass


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


class Game(CoopMixin, Ch4Mixin, Ch5Mixin):
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
        self.loading_screen("the snow is coming...")
        # chapter 2: the cabin in the snow
        self.w2 = C2.World2()
        self.w2.build()
        self.m_ch2 = Mesh(self.ctx, prog, self.w2.static_data)
        self.m_water2 = Mesh(self.ctx, prog, self.w2.water_data)
        self.m_snow = Mesh(self.ctx, prog, C2.snow_mesh())
        self.m_wood = Mesh(self.ctx, prog, C2.wood_bundle_mesh())
        self.m_log = Mesh(self.ctx, prog, C2.log_mesh())
        lb, ll, lo = C2.lantern_meshes()
        self.m_lantern, self.m_lantern_lit, self.m_lantern_off = (Mesh(self.ctx, prog, lb), Mesh(self.ctx, prog, ll),
                                                                   Mesh(self.ctx, prog, lo))
        self.m_door = Mesh(self.ctx, prog, C2.door_mesh())
        self.m_bars = Mesh(self.ctx, prog, C2.window_bars_mesh())
        self.m_rifle = Mesh(self.ctx, prog, C2.rifle_mesh())
        self.m_knife = Mesh(self.ctx, prog, C2.knife_mesh())
        self.m_meat = Mesh(self.ctx, prog, C2.meat_mesh())
        for k, v in list(elk_meshes().items()) + list(C2.deer_meshes().items()):
            self.m_moose[k] = Mesh(self.ctx, prog, v)
        from moose import unit_cube
        self.m_moose['shard'] = Mesh(self.ctx, prog, unit_cube(L.GLOW, (0.6, 0.68, 0.75)))
        # chapter 3: the cave, the mine, the blizzard
        self.loading_screen("the mine is waiting...")
        self.lv_up = C3.build_upper()
        self.lv_low = C3.build_lower()
        bu, bl = MeshBuilder(), MeshBuilder()
        C3.dress_upper(self.lv_up, bu)
        C3.dress_lower(self.lv_low, bl)
        self.m_up = Mesh(self.ctx, prog, bu.array())
        self.m_low = Mesh(self.ctx, prog, bl.array())
        self.m_cover2 = Mesh(self.ctx, prog, C3.snow_cover(C2.terrain_h2, -C2.HALF - 10, C2.HALF + 10, -C2.HALF - 10,
                                                           C2.HALF + 10, 2.0, 0.45, min_h=C2.WL + 0.25))
        self.m_cover1 = Mesh(self.ctx, prog, C3.snow_cover(W.terrain_h, -34, 34, 4, 47, 1.5, 0.35))
        self.m_lever = Mesh(self.ctx, prog, C3.lever_handle_mesh())
        self.m_cage = Mesh(self.ctx, prog, C3.cage_mesh())
        self.m_bulb = Mesh(self.ctx, prog, unit_cube(L.GLOW + EMIS, (1.0, 0.78, 0.5)))
        # chapter 4: the deep sewer
        self.loading_screen("he is getting bigger...")
        self.init_ch4(prog)
        self.loading_screen("all three of them...")
        self.init_ch5(prog)
        self.init_coop(prog)
        self.progress = load_progress()
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
        # the escape and the road
        self.escape = False
        self.escape_t = 0.0
        self.chaser = None
        self.cars = []
        self.cs_t = 0.0
        self.cs_fired = set()
        self.blood = []
        self.world.x_limit = 54.0
        # chapter 2
        self.chapter = 1
        self.ending_pages = lore.CH2_ENDING
        self.carried = 0
        self.stacked = 0
        self.wood_taken = set()       # spots whose bundle is on you or in the pile
        self.wood_carried = []        # spots whose bundle is on you (returned if you die)
        self.goat = None
        self.storm = 0.0
        self.ch2_t = 0.0
        self.ch2_phase = 'wood'      # wood -> rifle -> hunt -> run
        self.has_rifle = False
        self.deer = None
        self.window_broken = False
        self.door_angle = 0.0
        self.w2.door_open = False
        self.aim = 0.0
        self.fire_cd = 0.0
        self.muzzle_t = 0.0
        self.chaser2 = None
        self.run_start = None
        self.has_meat = False
        # chapter 3
        self.lv = None              # the mine level you are in (upper or lower)
        self.elk = None
        self.power = False
        self.goat_found_t = -1.0
        for lv in (getattr(self, 'lv_up', None), getattr(self, 'lv_low', None)):
            if lv is not None:
                for lev in lv.levers:
                    lev.update(pulled=False, progress=0.0, angle=-0.8)
        # chapter 4
        self.reset_ch4()
        self.reset_ch5()

    def respawn(self):
        if self.mp_on():
            # the monsters and the world carry on without you: keep them as they are
            keep = {a: getattr(self, a, None) for a in ('moose', 'chaser', 'goat', 'deer', 'chaser2', 'elk',
                                                        'moose4', 'beast')}
            carried = list(self.wood_carried)
            self._respawn()
            for a, v in keep.items():
                setattr(self, a, v)
            if self.chapter == 2 and carried:
                self.mp_act('wood_back', spots=carried)
            self.block_input = False
            return
        self._respawn()

    def _respawn(self):
        if self.chapter == 2:
            self.respawn_ch2()
            return
        if self.chapter == 3:
            self.respawn_ch3()
            return
        if self.chapter == 4:
            self.respawn_ch4()
            return
        if self.chapter == 5:
            self.respawn_ch5()
            return
        if self.escape:
            self.start_escape()
            return
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
        if st in ('coop', 'coopname', 'coopjoin', 'lobby'):
            self.coop_event(ev)
            return
        if st in ('cutscene', 'daylater', 'wake', 'ch2_end', 'climb', 'butcher', 'windowcs', 'wake3', 'ride', 'exit3',
                  'ch4open', 'exit4', 'card5', 'beastcs', 'exit5'):
            return
        if st == 'play' and self.chapter == 5 and ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self.fire_shotgun()
            return
        if st == 'play' and self.chapter == 2 and ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self.fire_rifle()
            return
        if ev.type in (pygame.WINDOWFOCUSLOST,) and st == 'play':
            self.pause()
            return
        if st == 'title':
            self.menu_event(ev, self.title_items(), self.title_action)
        elif st == 'chapters':
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.state = 'title'
                self.menu_sel = 1
                return
            self.menu_event(ev, self.chapter_items(), self.chapter_action)
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
                elif ev.key == pygame.K_r and self.chapter == 5:
                    self.start_reload()
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
            if self.mp_client():
                return              # the host turns the pages
            if (ev.type == pygame.KEYDOWN or ev.type == pygame.MOUSEBUTTONDOWN) and self.ending_t > 3.0:
                self.ending_page += 1
                self.ending_t = 0.0
                self.mp_tell('page', n=self.ending_page)
                if self.mp_on():
                    self.mp_send_tick()
                if self.ending_page >= len(self.ending_pages):
                    self.ending_done()

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
        items = ['CONTINUE', 'PLAY', 'CO-OP', 'SETTINGS', 'QUIT']
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
        item = self.title_items()[i]
        if item.startswith('UPDATE'):
            self.state = 'update'
            self.menu_sel = 0
        elif item == 'CONTINUE':
            self.continue_game()
        elif item == 'PLAY':
            self.state = 'chapters'
            self.menu_sel = 0
            self.locked_t = 0.0
        elif item == 'CO-OP':
            self.coop_open()
        elif item == 'SETTINGS':
            self.settings_return = 'title'
            self.settings_sel = 0
            self.state = 'settings'
        else:
            self.running = False

    def chapter_items(self):
        ch2 = "CHAPTER 2  -  THE CABIN" if self.progress.get('ch2') else "CHAPTER 2  -  LOCKED"
        ch3 = "CHAPTER 3  -  THE CAVE" if self.progress.get('ch3') else "CHAPTER 3  -  LOCKED"
        ch4 = "CHAPTER 4  -  THE DEEP SEWER" if self.progress.get('ch4') else "CHAPTER 4  -  LOCKED"
        ch5 = "CHAPTER 5  -  THE BEAST" if self.progress.get('ch5') else "CHAPTER 5  -  LOCKED"
        return ["CHAPTER 1  -  THE WOODS", ch2, ch3, ch4, ch5, "BACK"]

    def chapter_action(self, i):
        if i == 0:
            self.audio.play('click', 0.5)
            self.start_chapter1()
        elif i == 1:
            if self.progress.get('ch2'):
                self.audio.play('click', 0.5)
                self.new_game()
                self.start_daylater()
            else:
                self.audio.play('clunk', 0.4)
                self.locked_t = 2.5
                self.locked_msg = "Chapter 2 is locked. Beat Chapter 1 first."
        elif i == 2:
            if self.progress.get('ch3'):
                self.audio.play('click', 0.5)
                self.start_ch3()
            else:
                self.audio.play('clunk', 0.4)
                self.locked_t = 2.5
                self.locked_msg = "Chapter 3 is locked. Beat Chapter 2 first."
        elif i == 3:
            if self.progress.get('ch4'):
                self.audio.play('click', 0.5)
                self.start_ch4()
            else:
                self.audio.play('clunk', 0.4)
                self.locked_t = 2.5
                self.locked_msg = "Chapter 4 is locked. Beat Chapter 3 first."
        elif i == 4:
            if self.progress.get('ch5'):
                self.audio.play('click', 0.5)
                self.start_ch5()
            else:
                self.audio.play('clunk', 0.4)
                self.locked_t = 2.5
                self.locked_msg = "Chapter 5 is locked. Beat Chapter 4 first."
        else:
            self.audio.play('click', 0.5)
            self.state = 'title'
            self.menu_sel = 1

    def draw_chapters_ui(self):
        self.ui.fill((0, 0, 0, 140))
        self.draw_menu(self.chapter_items(), "SELECT CHAPTER")
        y0 = int(self.UH * 0.56)
        for i, (key, need) in enumerate((('ch2', 1), ('ch3', 2), ('ch4', 3), ('ch5', 4)), start=1):
            if not self.progress.get(key):
                w = self.f_menu.size("> CHAPTER %d  -  LOCKED" % (i + 1))[0]
                self.blit_text("finish Chapter %d to unlock" % need, self.f_small, (130, 120, 115),
                               (80 + w + 14, y0 + 46 * i + 13))
        if self.locked_t > 0:
            a = int(255 * clamp(self.locked_t / 0.6, 0, 1))
            self.blit_text(getattr(self, 'locked_msg', ''), self.f_hud, (200, 60, 50),
                           (self.UW // 2, self.UH - 60), 'midtop', alpha=a)
        self.draw_osd(title=True)

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
        if not self.mp_on():
            self.audio.pause()

    def resume(self):
        self.state = 'play'
        self.set_mouse(True)
        self.audio.unpause()

    def to_title(self):
        if self.mp is not None and self.state != 'title':
            m, self.mp = self.mp, None
            try:
                m.net.send('bye', {})
            except Exception:
                pass
            m.net.close()
            self.block_input = False
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
        self.menu_sel = self.title_items().index('SETTINGS') if self.state == 'title' else 1

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
        if self.chapter == 2:
            self.interact_ch2()
            return
        if self.chapter == 3:
            self.interact_ch3()
            return
        if self.chapter == 4:
            self.interact_ch4()
            return
        if self.chapter == 5:
            self.interact_ch5()
            return
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
            if (self.world.drained or self.valves_done >= 5) and self.mp_on():
                self.message("Everyone has to be at the ladder.", 2.5)
            elif self.world.drained or self.valves_done >= 5:
                self.start_climb()
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

    # ================================================================== the way out
    def start_climb(self):
        """Up the service ladder: a few seconds of rungs and a shaft of moonlight."""
        self.state = 'climb'
        self.climb_t = 0.0
        self.climb_rung = 0
        self.audio.loop('creak', 0)
        self.audio.loop('breath', 0)

    def update_climb(self, dt):
        self.climb_t += dt
        rung = int(self.climb_t / 0.42)
        if rung != self.climb_rung and self.climb_t < 3.6:
            self.climb_rung = rung
            self.audio.play_rand('step_conc', 4, 0.5)
        self.fade = clamp((self.climb_t - 3.2) / 0.8, 0, 1)
        if self.climb_t > 4.2:
            self.fade = 0.0
            self.start_escape()

    def render_climb(self):
        lx, _, lz = self.world.ladder_pos
        k = min(1.0, self.climb_t / 4.0)
        y = -3.4 + 7.5 * (k * k * (3 - 2 * k)) + 0.03 * math.sin(self.climb_t * 15)
        cam = (lx, y, lz - 0.25)
        pitch = 0.25 + 0.9 * k
        fwd = (0.0, math.sin(pitch), math.cos(pitch))
        self.draw_world(cam, fwd, 1.0, (cam[0] + 0.1, cam[1] - 0.1, cam[2]), fwd, [])

    def start_escape(self):
        """Out of the manhole into the eastern woods. Route 9 is just ahead.
        He climbs out behind you a couple of seconds later."""
        w = self.world
        p = self.player
        mx, mz = W.MANHOLE
        self.escape = True
        self.escape_t = 0.0
        w.x_limit = 64.0
        p.reset(mx + 1.6, float(W.terrain_h(mx + 1.6, mz)), mz, math.pi / 2)
        self.flags.update({'snap', 'farcall', 'whisper1', 'tunnel', 'tunnelcall', 'junction', 'gallery',
                           'holding', 'chamber', 'nest'})
        self.app = None
        self.app_done = {0, 1, 2}
        self.moose = Moose(w)
        self.chaser = {'x': mx, 'z': mz, 'y': float(W.terrain_h(mx, mz)) - 2.2, 'yaw': math.pi / 2, 'phase': 0.0,
                       'amt': 0.0, 'state': 'below', 'step': 0.0, 'snap': (0.0, 0.0, 0.0), 'snap_t': 0.0, 'roll': 0.0}
        self.cars = [{'x': W.ROAD_MID + 1.8, 'z': -70.0, 'dir': 1, 'speed': 24.0, 'delay': 1.2, 'sound': False}]
        self.clock_t = 4 * 3600 + 17 * 60
        self.flash_on = True
        self.flash_dir = p.fwd()
        self.fear = 0.0
        self.red = 0.0
        self.glitch = 0.0
        self.fade = 0.0
        self.msgs = []
        self.state = 'play'
        self.set_mouse(True)
        self.audio.stop_all()
        self.message("Fresh air. Headlights flicker through the trees -- the road is right there.", 5)
        self.set_objective("Run to the road.")

    def update_cars(self, dt):
        for c in self.cars:
            if c['delay'] > 0:
                c['delay'] -= dt
                continue
            c['z'] += c['dir'] * c['speed'] * dt
            # the pass-by sound peaks 2.5 s in, so start it 2.5 s before the car is level with us
            if not c['sound']:
                eta = (self.player.z - c['z']) * c['dir'] / c['speed']
                if eta < 2.5:
                    c['sound'] = True
                    pan, _ = self.audio._pan(c['x'], self.player.z)
                    self.audio.play('car', 0.9, pan)
        self.cars = [c for c in self.cars if -90 < c['z'] < 90]

    def car_lights(self):
        out = []
        for c in self.cars:
            if c['delay'] > 0:
                continue
            out.append(((c['x'], 1.0, c['z'] + c['dir'] * 7.0), 15.0, (1.1, 1.0, 0.8)))
            out.append(((c['x'], 0.8, c['z'] - c['dir'] * 3.0), 4.0, (0.5, 0.02, 0.0)))
        return out

    def update_escape(self, dt):
        """The run to Route 9. He follows a little slower than you walk."""
        p = self.player
        self.escape_t += dt
        p.z = clamp(p.z, W.ESCAPE_Z[0], W.ESCAPE_Z[1])
        p.x = max(p.x, 20.0)
        self.update_cars(dt)
        c = self.chaser
        tgt = self.mp_ai_target(c, 'chaser')[0]
        sim = self.mp_sim() and not self.mp_frozen('chaser')
        g = float(W.terrain_h(c['x'], c['z']))
        if not sim:
            pass
        elif c['state'] == 'below':
            if self.escape_t > 2.2:
                c['state'] = 'rising'
                self.audio.play3d('call_near', c['x'], c['z'], 50, 1.0)
                self.audio.play('stinger', 0.6)
        elif c['state'] == 'rising':
            c['y'] += 1.9 * dt
            if c['y'] >= g:
                c['y'] = g
                c['state'] = 'chase'
                self.message("Don't stop walking.", 3)
        else:
            dx, dz = tgt.x - c['x'], tgt.z - c['z']
            d = math.hypot(dx, dz)
            if d > 1e-3:
                nx = c['x'] + dx / d * 2.3 * dt
                nz = c['z'] + dz / d * 2.3 * dt
                nx, nz, _ = self.world.collide(nx, nz, 0.4, c['y'], forest=True)
                moved = math.hypot(nx - c['x'], nz - c['z'])
                c['x'], c['z'] = nx, nz
                c['yaw'] = Moose._turn(c['yaw'], math.atan2(dx, dz), dt * 6)
                c['phase'] += moved * 2.1
                c['amt'] += (min(1.0, moved / max(dt, 1e-4) / 2.0) - c['amt']) * min(1.0, dt * 6)
                c['step'] += moved
                if c['step'] > 1.25:
                    c['step'] = 0.0
                    self.audio.play3d('mstep', c['x'], c['z'], 30, 1.0)
            c['y'] = float(W.terrain_h(c['x'], c['z']))
            if d < 1.0:
                self.mp_caught(tgt, 'chaser')
                if self.state != 'play':
                    return
        # stop-motion snapshot for his limbs
        c['snap_t'] = c.get('snap_t', 0.0) - dt
        if sim and c['snap_t'] <= 0:
            c['snap_t'] = random.uniform(0.07, 0.14)
            c['roll'] = random.uniform(-0.6, 0.6) if random.random() < 0.4 else 0.0
            c['snap'] = (c['phase'], c['amt'], c['roll'])
        d = math.hypot(p.x - c['x'], p.z - c['z'])
        if c['state'] != 'below':
            self.audio.loop3d('breath', c['x'], c['z'], 16, 1.0)
            self.fear += (clamp(1 - d / 14, 0, 1) - self.fear) * min(1.0, dt * 3)
            if self.fear > 0.15:
                self.heart_t -= dt
                if self.heart_t <= 0:
                    self.heart_t = 1.05 - 0.6 * self.fear
                    self.audio.play('heart', 0.25 + 0.6 * self.fear)
        if self.mp_gather('road', p.x > W.ROAD_X0 - 0.2):
            self.start_cutscene()

    def chaser_parts(self):
        c = self.chaser
        if not c or c['state'] == 'below':
            return None
        ph, amt, roll = c['snap']
        return pose_moose(c['x'], c['y'], c['z'], c['yaw'], ph, amt, hunch=0.75, roll=roll, reach=0.6,
                          jaw=0.4, t=self.time)[0]

    # ------------------------------------------------------------------ the road cutscene
    def start_cutscene(self):
        p = self.player
        self.state = 'cutscene'
        self.cs_t = 0.0
        self.cs_fired = set()
        self.cs_P = (W.ROAD_X0 - 0.3, clamp(p.z, W.ESCAPE_Z[0] + 2, W.ESCAPE_Z[1] - 2))
        self.cs_yaw0 = p.yaw
        self.blood = []
        self.cars = []
        self.msgs = []
        self.obj_t = 0.0
        self.fear = 0.6
        self.audio.loop('breath', 0)

    def cs_fire(self, name, at):
        if self.cs_t >= at and name not in self.cs_fired:
            self.cs_fired.add(name)
            return True
        return False

    def spawn_blood(self, x, y, z, n, vel=(0.0, 2.5, 0.0), spread=1.5, size=(0.025, 0.06), key='blood'):
        """A spurt of droplets (blood, or glass): [x, y, z, vx, vy, vz, size, stuck, pool_lift, mesh]."""
        for _ in range(n):
            self.blood.append([x + random.uniform(-0.08, 0.08), y, z + random.uniform(-0.08, 0.08),
                               vel[0] + random.uniform(-spread, spread),
                               vel[1] + random.uniform(-spread * 0.4, spread),
                               vel[2] + random.uniform(-spread, spread),
                               random.uniform(*size), False, random.uniform(0, 0.004), key])
        if len(self.blood) > 420:
            # keep every pool on the ground; drop the oldest airborne drops first
            self.blood = self.blood[-420:]

    def update_blood(self, dt):
        for b in self.blood:
            if b[7]:
                continue
            b[4] -= 9.8 * dt
            b[0] += b[3] * dt
            b[1] += b[4] * dt
            b[2] += b[5] * dt
            floor = (self.w2.ground_at(b[0], b[2]) + 0.04) if self.chapter == 2 else 0.04
            if self.chapter == 2 and abs(b[0]) < C2.CABIN_HX and abs(b[2]) < C2.CABIN_HZ:
                floor = C2.CABIN_Y + 0.07
            if b[1] <= floor:
                b[1] = floor
                b[7] = True

    def update_cutscene(self, dt):
        t = self.cs_t = self.cs_t + dt
        A = self.audio
        F = self.cs_fight_point()
        P = self.cs_P
        fr = self.cs_frame()
        cam = fr['cam']
        A.set_listener(cam[0], cam[2], fr['yaw'])
        # ---- blood
        self.update_blood(dt)
        Ex, Ez = self.cs_feed_point()
        if self.cs_fire('b_tackle', 4.75):
            self.spawn_blood(Ex + 1.0, 1.2, Ez + 0.3, 14, vel=(-1.5, 2.0, -0.5), spread=1.6)
        if 6.3 < t < 10.4:
            # every bite tears another spurt out of his chest, plus a steady drizzle
            if random.random() < dt * 9:
                self.spawn_blood(Ex, 0.45, Ez, 2, vel=(0.0, 1.8, -0.4), spread=1.0)
        for i in range(14):
            if self.cs_fire('b_eat%d' % i, 6.45 + i * 0.3):
                self.spawn_blood(Ex, 0.5, Ez - 0.1, 11, vel=(0.0, 3.2, -0.9), spread=1.5)
        g = fr.get('goat_root')
        if g:
            if self.cs_fire('b_hit', 17.8):
                # the car is southbound: everything goes down the road
                self.spawn_blood(g[0], 1.5, g[2], 55, vel=(0.4, 3.0, -8.5), spread=2.2, size=(0.03, 0.08))
            if 17.8 < t < 18.6 and random.random() < dt * 40:
                self.spawn_blood(g[0], g[1] + 1.2, g[2], 2, vel=(0.0, 0.8, -4.0), spread=1.0)
            if 18.6 < t < 21.0 and random.random() < dt * 3:
                self.spawn_blood(g[0], 0.5, g[2] - 1.5, 2, vel=(0.0, 0.9, 0.0), spread=0.6)
            if 21.0 < t < 26.0 and random.random() < dt * 4:
                # drips as he gets up and runs
                self.spawn_blood(g[0], 1.3, g[2], 1, vel=(0.0, -0.5, 0.0), spread=0.2)
        if self.cs_fire('turn', 0.75):
            A.play('stinger', 1.0)
            A.play('call_near', 0.9)
        if 0.8 < t < 4.6:
            A.loop('breath', 1.0)
        else:
            A.loop('breath', 0.0)
        if self.cs_fire('grab', 1.05):
            A.play('tackle', 0.5)
            A.play('heart', 1.0)
        for i, at in enumerate((1.6, 2.4, 3.1, 3.7, 4.2)):
            if self.cs_fire('hb%d' % i, at):
                A.play('heart', 0.9)
        if self.cs_fire('jaw', 3.4):
            A.play('screech', 0.35)
        if self.cs_fire('goat_in', 3.9):
            A.play('goat_roar', 1.0, pan=0.6)
        if self.cs_fire('tackle', 4.6):
            A.play('tackle', 1.0)
            A.play('impact', 0.6)
        if self.cs_fire('ground', 5.2):
            A.play('mstep', 1.0)
            A.play('static', 0.5)
        for i in range(14):
            if self.cs_fire('eat%d' % i, 6.4 + i * 0.3):
                A.play_rand('eat', 3, 0.8)
        if self.cs_fire('mooscream', 6.8):
            A.play('call_near', 0.7)
        if self.cs_fire('stand_roar', 11.0):
            A.play('goat_roar', 0.9)
        for i in range(8):
            if self.cs_fire('run%d' % i, 13.8 + i * 0.32):
                A.play_rand('step_conc', 4, 0.7)
        if self.cs_fire('carsound', 15.6):
            A.play('car', 1.0, pan=0.5)
        if self.cs_fire('hit', 17.8):
            A.play('impact', 1.0)
            A.play('goat_roar', 0.5)
        if self.cs_fire('getup', 21.0):
            A.play('mstep', 0.8)
        if self.cs_fire('runoff', 23.0):
            A.play('goat_roar', 0.6, pan=-0.6)
        for i in range(6):
            if self.cs_fire('gstep%d' % i, 23.0 + i * 0.35):
                A.play('mstep', 0.8 - i * 0.12)
        self.fade = clamp((t - 26.5) / 1.5, 0, 1)
        self.fear = 0.9 if t < 6 else (0.5 if t < 18 else 0.3)
        if t > 28.3:
            # Chapter One is over: unlock Chapter Two and go straight into it
            self.progress['ch2'] = True
            save_progress(self.progress)
            self.start_daylater()

    def cs_fight_point(self):
        """Where the Moose Man's root lands when he is slammed down."""
        P = self.cs_P
        return (P[0] - 1.8, P[1] - 3.2)

    def cs_feed_point(self):
        """His chest, once he is on his back (his body lies westward from the root)."""
        Fx, Fz = self.cs_fight_point()
        return (Fx - 2.0, Fz)

    def cs_frame(self):
        """Everything on screen at cutscene time t: camera, actors, cars, lights."""
        t = self.cs_t
        P = self.cs_P
        Fx, Fz = self.cs_fight_point()
        gnd = 0.03

        def sm(a, b):
            k = clamp((t - a) / (b - a), 0, 1)
            return k * k * (3 - 2 * k)

        def lerp(a, b, k):
            return a + (b - a) * k

        out = {'parts': [], 'lights': [], 'letterbox': True}
        # ---- the Moose Man
        mx, mz = P[0] - 1.45, P[1]
        m_yaw = math.pi / 2           # facing the player (east)
        reach = 0.2 + 1.35 * sm(0.95, 1.6)
        jaw = 0.05 + 1.25 * sm(3.3, 4.4)
        roll = 0.55 * sm(2.2, 3.3) + (0.15 * math.sin(t * 23) if t > 3.3 else 0.0)
        mx += 0.3 * sm(3.4, 4.5)
        head_pitch = -0.55 * sm(1.0, 1.8)
        m_lie = 0.0
        m_hyaw = 0.0
        my = gnd
        if t >= 4.6:
            # tackled: knocked off his feet and slammed flat on his back,
            # limbs settling into a natural bend, head lolling to one side
            k = sm(4.6, 5.15)
            mx = lerp(mx, Fx, k)
            mz = lerp(mz, Fz, k)
            my = gnd + 0.6 * math.sin(math.pi * k)
            m_lie = k
            twitch = (0.25 * math.sin(t * 17) if t < 10.5 else 0.0)
            reach = 0.15 + twitch
            jaw = (0.7 + 0.3 * math.sin(t * 9)) if t < 10.5 else 0.45
            roll = (random.uniform(-0.25, 0.25) if 6.0 < t < 9.5 else 0.0)
            head_pitch = 0.0
            m_hyaw = 0.75 * k
        moose = pose_moose(mx, my, mz, m_yaw, 0.0, 0.0, hunch=0.55, roll=roll, head_pitch=head_pitch,
                           head_yaw=m_hyaw, reach=reach, jaw=jaw, t=self.time, lie=m_lie)
        out['parts'].append(moose[0])
        head_m = moose[1]
        mhead = (float(head_m[0, 3]), float(head_m[1, 3]), float(head_m[2, 3]))
        # ---- the Goat Man
        Ex, Ez = self.cs_feed_point()          # the Moose Man's chest, once he is down
        gfx, gfz = Ex, Ez - 0.75               # where the Goat Man crouches to feed, facing you
        lane = W.ROAD_MID - 1.7
        goat = None
        if t >= 3.9:
            if t < 4.6:
                # charging in out of the trees from the north
                k = sm(3.9, 4.6)
                gx, gz = lerp(P[0] - 3.5, mx - 0.2, k), lerp(P[1] + 10.0, mz + 0.8, k)
                goat = dict(x=gx, z=gz, yaw=math.atan2(mx - gx, mz - gz), phase=t * 14, amt=1.0, hunch=0.85, arms=0.9)
            elif t < 10.5:
                # on top of him, feeding
                bob = math.sin((t - 6.2) * 6.5)
                k = sm(4.6, 5.3)
                sx, sz = P[0] - 1.35, P[1] + 0.8
                goat = dict(x=lerp(sx, gfx, k), z=lerp(sz, gfz, k), yaw=lerp(math.atan2(gfx - sx, gfz - sz), 0.0, k),
                            crouch=0.95 * k, hunch=0.85 + 0.55 * k,
                            head_pitch=(0.55 + 0.35 * bob) if t > 6.2 else 0.3, jaw=(0.6 + 0.4 * bob) if t > 6.2 else 0.8,
                            arms=0.35 + 0.1 * math.sin(t * 6.5), bloody=t > 7.0, roll=0.2 * math.sin(t * 3.1))
            elif t < 14.5:
                # stands up over the body and looks at you
                k = sm(10.5, 12.0)
                look = math.atan2(self._cs_cam_x(t) - gfx, P[1] - gfz)
                goat = dict(x=gfx, z=gfz, yaw=lerp(0.0, look, sm(11.0, 12.2)), crouch=0.95 * (1 - k),
                            hunch=lerp(1.4, 0.45, k), head_pitch=0.0, jaw=0.5 * (1 - sm(12, 13)), arms=0.2, bloody=True)
            elif t < 17.8:
                # follows you out onto the road
                k = sm(14.5, 17.8)
                gx, gz = lerp(gfx, lane, k), lerp(gfz, P[1], k)
                goat = dict(x=gx, z=gz, yaw=math.atan2(W.ROAD_X1 + 2.5 - gx, P[1] - gz), phase=t * 5, amt=0.9,
                            hunch=0.5, arms=0.25, bloody=True)
            elif t < 21.0:
                # hit: knocked down the road and onto his back -- no somersault,
                # he twists to face where he came from and goes over backwards
                k = sm(17.8, 18.6)
                walk_yaw = math.atan2(W.ROAD_X1 + 2.5 - lane, 0.0)
                gx = lane + 0.5 * k
                gz = P[1] - 7.0 * k
                gy = 0.7 * math.sin(math.pi * min(1.0, (t - 17.8) / 0.8)) if t < 18.6 else 0.0
                lie = sm(17.85, 18.55)
                twitch = 0.2 * math.sin(t * 15) if 18.6 < t < 19.6 else 0.0
                goat = dict(x=gx, z=gz, y=gy, yaw=lerp(walk_yaw, 0.0, k), lie=lie, arms=0.3 + twitch,
                            bloody=True, hunch=0.3, head_yaw=0.6 * lie)
            elif t < 23.0:
                # gets up, jerkily, and stares at you
                k = sm(21.0, 22.3)
                k = math.floor(k * 6) / 6.0
                gx, gz = lane + 0.5, P[1] - 7.0
                look = math.atan2(W.ROAD_X1 + 2.5 - gx, P[1] - gz)
                goat = dict(x=gx, z=gz, yaw=lerp(0.0, look, sm(22.0, 22.6)), lie=1.0 - k,
                            crouch=0.8 * (1 - k), hunch=0.5, arms=0.4 * (1 - k), bloody=True,
                            head_yaw=0.6 * (1 - k), roll=0.4 * sm(22.2, 22.9))
            elif t < 26.0:
                # and runs off into the trees
                k = (t - 23.0) / 3.0
                gx = lane + 0.5 - 18.0 * k
                gz = P[1] - 7.0 - 4.0 * k
                goat = dict(x=gx, z=gz, yaw=math.atan2(-18.0, -4.0), phase=t * 13, amt=1.0, hunch=0.85, arms=0.3, bloody=True)
        if goat:
            gy = goat.pop('y', float(W.terrain_h(goat['x'], goat['z'])))
            gx, gz, gyaw = goat.pop('x'), goat.pop('z'), goat.pop('yaw')
            if 'phase' in goat:
                goat['walk_phase'] = goat.pop('phase')
            if 'amt' in goat:
                goat['walk_amt'] = goat.pop('amt')
            out['parts'].append(pose_goat(gx, gy, gz, gyaw, t=self.time, **goat)[0])
            out['goat'] = (gx, gy + 2.6, gz)
            out['goat_root'] = (gx, gy, gz)
        # ---- blood
        if self.blood:
            bp = []
            for b in self.blood:
                if b[7]:
                    s = b[6] * 2.4
                    bp.append(('blood', T(b[0], 0.035 + b[8], b[2]) @ S(s, 0.006, s * 0.8)))
                else:
                    s = b[6]
                    bp.append(('blood', T(b[0], b[1], b[2]) @ S(s, s * 1.6, s)))
            out['parts'].append(bp)
        # ---- spill from the dropped flashlight, so you can see what he is doing
        if 4.6 <= t < 14.5:
            out['lights'].append(((Ex + 1.2, 1.4, Ez + 0.8), 8.0, (0.75, 0.7, 0.6)))
        # ---- the car that never stops (southbound, nearer lane)
        if 15.6 <= t < 21.5:
            cx = lane
            cz = P[1] + 26.0 - 28.0 * (t - 16.87)
            out['parts'].append(car_parts(cx, cz, -1))
            out['lights'].append(((cx, 1.0, cz - 7.0), 16.0, (1.2, 1.1, 0.9)))
            out['lights'].append(((cx, 0.8, cz + 3.0), 4.0, (0.5, 0.02, 0.0)))
        # ---- the camera
        eye = 1.62
        cam_x = self._cs_cam_x(t)
        if t < 1.0:
            yaw = lerp(self.cs_yaw0, -math.pi / 2, sm(0.0, 0.9))
            cam = (cam_x, gnd + eye, P[1])
            fwd = (math.sin(yaw), -0.02, math.cos(yaw))
            up = (0.0, 1.0, 0.0)
        elif t < 4.6:
            # lifted up to his face
            k = sm(1.0, 1.9)
            hold = (mhead[0] + 0.95, mhead[1] + 0.05, mhead[2])
            cam = (lerp(cam_x, hold[0], k), lerp(gnd + eye, hold[1], k) + 0.03 * math.sin(t * 9), lerp(P[1], hold[2], k))
            look = (mhead[0] - cam[0], mhead[1] + 0.05 - cam[1], mhead[2] - cam[2])
            ln = math.sqrt(sum(v * v for v in look))
            fwd = tuple(v / ln for v in look)
            if t > 4.2:
                fwd = (fwd[0], fwd[1], fwd[2] + 0.5 * sm(4.2, 4.6))     # glance as something comes
            up = (0.0, 1.0, 0.0)
            yaw = math.atan2(fwd[0], fwd[2])
        elif t < 12.3:
            # dropped; lying in the gravel, watching
            k = sm(4.6, 5.2)
            hold_y = (mhead[1] if t < 4.7 else 2.4)
            cy = lerp(hold_y, gnd + 0.32, k)
            cam = (cam_x + 0.1 * random.uniform(-1, 1) * (1 - k), cy, P[1] - 0.5 * k)
            target = (Ex, 0.6 + 1.2 * sm(10.5, 12.0), Ez - 0.3)
            look = (target[0] - cam[0], target[1] - cam[1], target[2] - cam[2])
            ln = math.sqrt(sum(v * v for v in look))
            fwd = tuple(v / ln for v in look)
            r = 0.55 * (1 - sm(5.6, 11.0)) + 0.08
            up = (math.sin(r), math.cos(r), 0.0)
            yaw = math.atan2(fwd[0], fwd[2])
        else:
            # get up, run across the road, turn around
            rise = sm(12.3, 13.2)
            cy = lerp(gnd + 0.32, gnd + eye, rise) + (0.05 * math.sin(t * 14) if 13.8 < t < 16.2 else 0.0)
            if t < 16.2:
                yaw = lerp(math.atan2(Ex - cam_x, Ez - 0.3 - P[1]), math.pi / 2, sm(12.6, 13.6))
            else:
                yaw = lerp(math.pi / 2, -math.pi / 2 + 0.35, sm(16.2, 17.1))
                if t > 18.0:
                    # follow the goat down the road
                    gt = out.get('goat')
                    if gt:
                        yaw = lerp(yaw, math.atan2(gt[0] - cam_x, gt[2] - P[1]), sm(18.0, 18.6))
            pz = P[1] - 0.5 * (1 - sm(12.3, 13.2))
            cam = (cam_x, cy, pz)
            pitch = -0.06
            fwd = (math.sin(yaw) * math.cos(pitch), math.sin(pitch), math.cos(yaw) * math.cos(pitch))
            up = (0.0, 1.0, 0.0)
        out.update(cam=cam, fwd=fwd, up=up, yaw=yaw)
        return out

    def _cs_cam_x(self, t):
        P = self.cs_P
        k = clamp((t - 13.6) / 2.6, 0, 1)
        return P[0] + (W.ROAD_X1 + 2.5 - P[0]) * (k * k * (3 - 2 * k))

    def render_cutscene(self):
        fr = self.cs_frame()
        cam, fwd = fr['cam'], fr['fwd']
        rx, rz = -math.cos(fr['yaw']), math.sin(fr['yaw'])
        fpos = (cam[0] + rx * 0.18, cam[1] - 0.12, cam[2] + rz * 0.18)
        # the flashlight is dropped when you fall: it lies in the gravel pointing at them
        if 4.6 <= self.cs_t < 12.3:
            Ex, Ez = self.cs_feed_point()
            fpos = (cam[0] + 0.4, 0.15, cam[2] + 0.2)
            d = (Ex - fpos[0], 0.45, Ez - 0.3 - fpos[2])
            ln = math.sqrt(sum(v * v for v in d))
            fdir = tuple(v / ln for v in d)
        else:
            fdir = fwd
        self.draw_world(cam, fwd, 1.0, fpos, fdir, fr['parts'], up=fr['up'], extra_lights=fr['lights'])
        bar = int(self.UH * 0.11)
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, 0, self.UW, bar))
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, self.UH - bar, self.UW, bar))

    # ================================================================== CHAPTER 2
    # ================================================================== saving and continuing
    RESUME_NAMES = {(1, 'start'): "Chapter 1  -  The Woods", (1, 'sewer'): "Chapter 1  -  The Sewers",
                    (2, 'start'): "Chapter 2  -  The Cabin", (2, 'wood20'): "Chapter 2  -  The Hunt",
                    (3, 'start'): "Chapter 3  -  The Cave", (3, 'lower'): "Chapter 3  -  The Deep Mine",
                    (4, 'start'): "Chapter 4  -  The Deep Sewer", (4, 'hall'): "Chapter 4  -  The Hall",
                    (5, 'start'): "Chapter 5  -  The Drain", (5, 'boss'): "Chapter 5  -  The Beast"}

    def set_resume(self, chapter, checkpoint):
        if self.mp is not None:
            return
        self.progress['resume'] = {'chapter': chapter, 'checkpoint': checkpoint}
        save_progress(self.progress)

    def resume_point(self):
        r = self.progress.get('resume')
        if isinstance(r, dict) and (r.get('chapter'), r.get('checkpoint')) in self.RESUME_NAMES:
            return r['chapter'], r['checkpoint']
        # nothing saved yet: the start of the furthest chapter you have reached
        if self.progress.get('ch5'):
            return 5, 'start'
        if self.progress.get('ch4'):
            return 4, 'start'
        return (3 if self.progress.get('ch3') else (2 if self.progress.get('ch2') else 1)), 'start'

    def continue_game(self):
        chapter, cp = self.resume_point()
        self.new_game()
        if chapter == 5 and cp == 'boss':
            self.begin_ch5('boss')
        elif chapter == 5:
            self.start_ch5()
        elif chapter == 4 and cp == 'hall':
            self.continue_ch4_hall()
        elif chapter == 4:
            self.start_ch4()
        elif chapter == 3 and cp == 'lower':
            self.continue_ch3_lower()
        elif chapter == 3:
            self.start_ch3()
        elif chapter == 2 and cp == 'wood20':
            self.continue_ch2_wood20()
        elif chapter == 2:
            self.start_daylater()
        elif cp == 'sewer':
            self.continue_ch1_sewer()
        else:
            self.start_chapter1()

    def start_chapter1(self):
        self.new_game()
        self.set_resume(1, 'start')
        self.state = 'intro'
        self.intro_t = 0.0

    def continue_ch1_sewer(self):
        """Chapter One checkpoint: at the bottom of the storm drain, in the junction room."""
        p = self.player
        x, z = cell_center(9, 18)
        p.reset(x, W.SEWER_FLOOR, z, 0.0)
        self.flags.update({'snap', 'farcall', 'whisper1', 'tunnel', 'tunnelcall', 'junction'})
        self.app_done = {0, 1, 2}
        self.app = None
        self.checkpoint = True
        self.clock_t = 11 * 60
        self.state = 'play'
        self.set_mouse(True)
        self.message("Something has been living down here.", 4)
        self.set_objective("Find a way through the overflow system.")

    def continue_ch2_wood20(self):
        """Chapter Two checkpoint: all twenty bundles stacked on the porch."""
        self.chapter = 2
        self.begin_ch2()
        self.clock_t = (2 * 86400 + 20 * 3600 + 31 * 60) - (23 * 3600 + 58 * 60 + 7)
        self.stacked = C2.WOOD_NEEDED
        self.wood_taken = set(range(len(self.w2.wood_spots)))
        self.start_rifle_phase()

    def start_daylater(self):
        """Black screen: 1 DAY LATER."""
        self.set_resume(2, 'start')
        self.state = 'daylater'
        self.daylater_t = 0.0
        self.fade = 0.0
        self.set_mouse(False)
        self.audio.stop_all()
        self.audio.stop_loops()

    def update_daylater(self, dt):
        self.daylater_t += dt
        self.audio.loop('winter_amb', 0.25 * clamp((self.daylater_t - 1.5) / 3.0, 0, 1))
        if self.daylater_t > 5.5:
            self.start_wake()

    def draw_daylater_ui(self):
        t = self.daylater_t
        a = int(255 * clamp(t / 1.2, 0, 1) * clamp((5.3 - t) / 1.0, 0, 1))
        self.blit_text("1 DAY LATER", self.f_big, (210, 205, 198), (self.UW // 2, self.UH // 2 - 40), 'midtop', alpha=a)
        a2 = int(255 * clamp((t - 1.2) / 1.2, 0, 1) * clamp((5.3 - t) / 1.0, 0, 1))
        self.blit_text("CHAPTER TWO", self.f_hud, (170, 40, 30), (self.UW // 2, self.UH // 2 + 30), 'midtop', alpha=a2)

    def start_wake(self):
        """The wake-up cutscene in the cabin."""
        self.new_game()
        self.chapter = 2
        self.state = 'wake'
        self.wake_t = 0.0
        self.wake_fired = set()
        self.clock_t = (2 * 86400 + 19 * 3600 + 46 * 60) - (23 * 3600 + 58 * 60 + 7)
        self.msgs = []
        self.set_mouse(False)

    def wake_fire(self, name, at):
        if self.wake_t >= at and name not in self.wake_fired:
            self.wake_fired.add(name)
            return True
        return False

    def update_wake(self, dt):
        self.wake_t += dt
        self.clock_t += dt
        t = self.wake_t
        A = self.audio
        A.loop('winter_amb', 0.3 if t < 9.6 else 0.6)
        if self.wake_fire('match', 5.2):
            A.play('match', 0.9)
        if self.wake_fire('open', 8.3):
            A.play('door_open', 0.8)
        if self.wake_fire('close', 12.3):
            A.play('door_close', 0.9)
        for i in range(4):
            if self.wake_fire('stepin%d' % i, 6.9 + i * 0.4):
                A.play_rand('step_conc', 4, 0.35)
        for i in range(4):
            if self.wake_fire('stepout%d' % i, 9.3 + i * 0.45):
                A.play_rand('step_snow', 4, 0.5)
        for at, text, dur in lore.CH2_WAKE_LINES:
            if self.wake_fire('line%.1f' % at, at):
                self.message(text, dur)
        for m in self.msgs:
            m[1] -= dt
        self.msgs = [m for m in self.msgs if m[1] > 0]
        self.fade = clamp(1.0 - t / 2.0, 0, 1)
        if t > 16.5:
            self.fade = 0.0
            self.begin_ch2()

    def wake_frame(self):
        """Camera, door angle and lantern state for the wake-up cutscene."""
        t = self.wake_t
        Y = C2.CABIN_Y

        def sm(a, b):
            k = clamp((t - a) / (b - a), 0, 1)
            return k * k * (3 - 2 * k)

        def lerp(a, b, k):
            return a + (b - a) * k

        lit = t >= 5.45
        held = t >= 4.6
        # keyframes: (x, y, z, yaw, pitch)
        keys = [
            (0.0, (-1.85, Y + 0.72, -1.45, 0.0, 1.3)),     # lying on the cot, staring at the ceiling
            (2.4, (-1.85, Y + 0.72, -1.45, 0.0, 1.3)),
            (3.6, (-1.75, Y + 1.15, -0.9, 1.35, -0.25)),   # sit up, look to the table
            (4.6, (-1.6, Y + 1.15, -0.9, 1.45, -0.3)),
            (6.4, (-1.6, Y + 1.2, -0.9, 1.45, -0.15)),     # strike the match, light it
            (7.0, (-1.2, Y + 1.62, -0.4, 0.4, 0.0)),       # stand up
            (8.2, (-0.05, Y + 1.62, 1.35, 0.0, -0.05)),    # walk to the door
            (8.8, (-0.05, Y + 1.62, 1.35, 0.0, -0.05)),
            (10.6, (0.0, Y + 1.66, 3.3, 0.0, 0.0)),        # out onto the porch
            (11.6, (0.0, Y + 1.66, 3.3, math.pi, 0.0)),    # turn round, pull the door shut
            (12.6, (0.0, Y + 1.66, 3.3, math.pi, 0.0)),
            (14.2, (0.0, Y + 1.66, 3.6, 2 * math.pi, -0.04)),   # turn to face the woods
            (16.5, (0.0, Y + 1.66, 3.8, 2 * math.pi, -0.04)),
        ]
        k0 = keys[0]
        for k1 in keys[1:]:
            if t <= k1[0]:
                break
            k0 = k1
        a = clamp((t - k0[0]) / max(1e-4, k1[0] - k0[0]), 0, 1)
        a = a * a * (3 - 2 * a)
        x, y, z, yaw, pitch = (lerp(k0[1][i], k1[1][i], a) for i in range(5))
        if 8.2 <= t <= 10.6:
            y += 0.03 * math.sin(t * 11)
        door = 1.45 * sm(8.3, 8.9) * (1 - sm(11.7, 12.35))
        return dict(cam=(x, y, z), yaw=yaw, pitch=pitch, lit=lit, held=held, door=door,
                    match=(5.2 <= t < 5.7))

    def render_wake(self):
        fr = self.wake_frame()
        cam = fr['cam']
        yaw, pitch = fr['yaw'], fr['pitch']
        fwd = (math.sin(yaw) * math.cos(pitch), math.sin(pitch), math.cos(yaw) * math.cos(pitch))
        lights = []
        Y = C2.CABIN_Y
        if fr['held']:
            lp = self.held_lantern_pos(cam, yaw, pitch)
        else:
            lp = (1.5, Y + 0.78, -1.3)
        if fr['lit']:
            lights.append(((lp[0], lp[1] + 0.2, lp[2]), 9.0, self.lantern_col()))
        if fr['match']:
            lights.append(((lp[0] + 0.1, lp[1] + 0.25, lp[2]), 3.0, (1.6, 0.8, 0.25)))
        # pale light through the window before the lantern is lit
        lights.append(((-2.2, Y + 1.4, -0.2), 4.5, (0.12, 0.14, 0.22)))
        self.draw_world2(cam, fwd, lights, door=fr['door'], lantern_at=(None if fr['held'] else lp),
                         lantern_lit=fr['lit'], hold=(fr['held'], yaw, pitch))
        # subtitles
        y = self.UH - 120
        for m in reversed(self.msgs):
            txt, tl, td = m
            al = int(clamp(tl / 0.8, 0, 1) * clamp((td - tl) / 0.3, 0, 1) * 255)
            self.blit_text(txt, self.f_msg, (225, 215, 200), (self.UW // 2, y), 'midtop', alpha=al)
            y -= 30
        bar = int(self.UH * 0.11)
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, 0, self.UW, bar))
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, self.UH - bar, self.UW, bar))

    def lantern_col(self):
        k = 0.88 + 0.08 * math.sin(self.time * 11) + 0.04 * math.sin(self.time * 23)
        return (1.25 * k, 0.78 * k, 0.38 * k)

    def held_lantern_pos(self, cam, yaw, pitch):
        rx, rz = -math.cos(yaw), math.sin(yaw)
        fx, fz = math.sin(yaw), math.cos(yaw)
        side = -0.36 if ((self.has_rifle or getattr(self, 'has_shotgun', False)) and self.state in ('play', 'beastcs')) else 0.36    # rifle in the right hand, lantern in the left
        return (cam[0] + rx * side + fx * 0.66, cam[1] - 0.66 + 0.18 * math.sin(pitch), cam[2] + rz * side + fz * 0.66)

    def begin_ch2(self):
        """From the porch: gameplay starts."""
        p = self.player
        rx, rz = C2.RESPAWN
        p.reset(rx, self.w2.ground_at(rx, rz), 3.8, 0.0)
        self.chapter = 2
        self.state = 'play'
        self.flash_on = True
        self.carried = 0
        self.stacked = 0
        self.wood_taken = set()
        self.wood_carried = []
        self.goat = C2.GoatHunter(self.w2)
        self.goat.place_far(rx, rz)
        self.goat.grace = 35.0
        self.storm = 0.0
        self.ch2_t = 0.0
        self.fear = 0.0
        self.heart_t = 0.0
        self.roar_t = 4.0
        self.set_objective("Gather firewood before the storm. Stack it on the porch.")
        self.set_mouse(True)

    def respawn_ch2(self):
        """Back in front of the cabin. Whatever you were carrying is gone -- the
        bundles go back where you found them. The stacked pile is safe."""
        if self.ch2_phase == 'run':
            # caught on the way home: back at the deer, meat still in your coat
            self.red = 0.0
            self.glitch = 0.0
            self.msgs = []
            self.start_run(retry=True)
            self.message("Again. Don't stop.", 3)
            return
        for spot in self.wood_carried:
            self.wood_taken.discard(spot)
        lost = self.carried
        self.wood_carried = []
        self.carried = 0
        p = self.player
        rx, rz = C2.RESPAWN
        p.reset(rx, self.w2.ground_at(rx, rz), rz, 0.0)
        self.goat = C2.GoatHunter(self.w2)
        self.goat.place_far(rx, rz)
        self.goat.grace = 10.0
        self.flash_on = True
        self.fear = 0.0
        self.red = 0.0
        self.glitch = 0.0
        self.msgs = []
        if lost:
            self.message("You wake on the porch. The wood you were carrying is gone.", 5)
        else:
            self.message("You wake on the porch, shaking.", 4)
        self.state = 'play'
        self.set_mouse(True)

    def update_ch2(self, dt):
        p = self.player
        w2 = self.w2
        self.clock_t += dt
        self.ch2_t += dt
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
        depth = w2.water_depth(p.x, p.z)
        in_water = depth > 0.08
        if in_water:
            speed *= 0.6
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
        nx, nz = w2.collide(p.x + p.vx * dt, p.z + p.vz * dt, 0.3, p.x, p.z)
        moved = math.hypot(nx - p.x, nz - p.z)
        p.x, p.z = nx, nz
        g = w2.ground_at(p.x, p.z)
        # the porch deck
        if abs(p.x) < C2.CABIN_HX + 0.2 and C2.CABIN_HZ + 0.1 < p.z < C2.CABIN_HZ + 1.75:
            g = max(g, C2.CABIN_Y + 0.15)
        p.y = g
        p.smooth_y += (p.y - p.smooth_y) * min(1.0, dt * 12)
        sp = moved / max(dt, 1e-4)
        p.bob_amt += (min(1.0, sp / 2.7) - p.bob_amt) * min(1.0, dt * 8)
        p.bob += moved * (2.0 if not sprint else 1.7)
        p.step_acc += moved
        stride = 0.55 if crouch else (1.0 if sprint else 0.78)
        if p.step_acc > stride:
            p.step_acc = 0.0
            vol = 0.25 if crouch else (0.85 if sprint else 0.5)
            if in_water:
                self.audio.play_rand('step_water', 3, vol * 1.2)
                rad = 6.0 if crouch else (22 if sprint else 12)
            else:
                self.audio.play_rand('step_snow', 4, vol)
                rad = 2.5 if crouch else (18 if sprint else 7)
            if self.goat:
                self.goat.hear(p.x, p.z, rad)
        f = p.fwd()
        a = min(1.0, dt * 16)
        self.flash_dir = tuple(self.flash_dir[i] + (f[i] - self.flash_dir[i]) * a for i in range(3))
        self.flicker_t = max(0.0, self.flicker_t - dt)
        self.audio.set_listener(p.x, p.z, p.yaw)
        # the storm is still on its way: the wind picks up as the night goes on
        self.storm = clamp(self.ch2_t / 1200.0, 0.0, 0.5)
        self.audio.loop('winter_amb', 0.45 + 0.4 * self.storm)
        self.audio.loop('forest_amb', 0.0)
        self.audio.loop('sewer_amb', 0.0)
        self.audio.loop('title_amb', 0.0)
        # the door swings
        target = 1.45 if self.w2.door_open else 0.0
        self.door_angle += (target - self.door_angle) * min(1.0, dt * 6)
        # the rifle: right mouse aims down the scope
        aiming = self.has_rifle and self.mouse_buttons()[2]
        self.aim += ((1.0 if aiming else 0.0) - self.aim) * min(1.0, dt * 10)
        self.fire_cd = max(0.0, self.fire_cd - dt)
        self.muzzle_t = max(0.0, self.muzzle_t - dt)
        if getattr(self, 'bolt_t', 0) > 0:
            self.bolt_t -= dt
            if self.bolt_t <= 0:
                self.audio.play('bolt', 0.6)
        if self.ch2_phase == 'wood':
            self.update_goat(dt)
        elif self.ch2_phase == 'hunt' and self.deer is not None:
            tgt, lit = self.mp_ai_target(self.deer, 'deer')
            if self.mp_sim():
                self.deer.update(dt, tgt, lit)
            for ev in self.mp_events('deer', self.deer):
                if ev == 'snort':
                    self.audio.play3d('snort', self.deer.x, self.deer.z, 60, 0.9)
            self.deer.events = []
        elif self.ch2_phase == 'run':
            self.update_run(dt)
        self.update_blood(dt)
        if self.state != 'play':
            return
        self.focus = self.find_focus_ch2()
        self.obj_t = max(0.0, self.obj_t - dt)
        self.glitch += (0.0 - self.glitch) * min(1.0, dt * 20)

    def update_goat(self, dt):
        gt = self.goat
        p = self.player
        if gt is None:
            return
        tgt, lit = self.mp_ai_target(gt, 'goat')
        if self.mp_sim() and not self.mp_frozen('goat'):
            gt.update(dt, tgt, lit)
        for ev in self.mp_events('goat', gt):
            if ev == 'step':
                self.audio.play3d('mstep', gt.x, gt.z, 40, 1.0)
            elif ev == 'roar':
                self.audio.play3d('goat_roar', gt.x, gt.z, 90, 1.0)
                self.audio.play('stinger', 0.6)
            elif ev == 'lost':
                self.audio.play3d('breath', gt.x, gt.z, 25, 0.9)
                if 'goat_lost' not in self.flags:
                    self.flags.add('goat_lost')
                    self.message("He hunts light and movement. Lantern off. Don't move.", 5)
            elif ev == 'leave':
                self.audio.play3d('mstep', gt.x, gt.z, 40, 0.7)
                if 'goat_leave' not in self.flags:
                    self.flags.add('goat_leave')
                    self.message("He's going.", 3)
            elif ev == 'kill':
                self.mp_caught(tgt, 'goat')
        gt.events = []
        # a distant roar now and then, so you know he is out there
        self.roar_t -= dt
        d = math.hypot(gt.x - p.x, gt.z - p.z)
        if self.roar_t <= 0:
            self.roar_t = random.uniform(40, 75)
            if gt.state != 'chase':
                self.audio.play3d('goat_roar', gt.x, gt.z, 160, 0.7)
                if 'first_roar' not in self.flags:
                    self.flags.add('first_roar')
                    self.message("Something huge is moving out in the trees.", 4)
        tf = clamp(1 - d / 22, 0, 1)
        if gt.state == 'chase':
            tf = max(tf, 0.55)
        elif gt.state == 'search':
            tf = max(tf, 0.7)      # he is standing right there, staring
        self.fear += (tf - self.fear) * min(1.0, dt * 3)
        self.audio.loop3d('breath', gt.x, gt.z, 20, 1.0)
        if self.fear > 0.15:
            self.heart_t -= dt
            if self.heart_t <= 0:
                self.heart_t = 1.05 - 0.6 * self.fear
                self.audio.play('heart', 0.25 + 0.6 * self.fear)
        if self.fear > 0.4 and random.random() < dt * self.fear * 2.5:
            self.flicker_t = random.uniform(0.04, 0.2)

    def find_focus_ch2(self):
        p = self.player
        ex, ey, ez = p.eye()
        f = p.fwd()
        best = None
        bestd = -1
        for i, (wx, wy, wz, _) in enumerate(self.w2.wood_spots):
            if i in self.wood_taken or self.ch2_phase != 'wood':
                continue
            dx, dy, dz = wx - ex, wy + 0.25 - ey, wz - ez
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if d > 2.6:
                continue
            dot = (dx * f[0] + dy * f[1] + dz * f[2]) / max(d, 1e-4)
            if (dot > 0.6 or math.hypot(dx, dz) < 1.2) and dot > bestd:
                bestd = dot
                best = ('wood', i)
        if best:
            return best
        ph = self.ch2_phase
        if ph == 'wood':
            wx, wz = C2.WOODPILE
            d = math.hypot(p.x - wx, p.z - wz)
            if (self.carried and d < 2.6) or d < 1.4:
                return ('woodpile', 0)
            return None
        hz = C2.CABIN_HZ
        if ph in ('rifle', 'hunt') and math.hypot(p.x - 0.0, p.z - hz) < 1.9:
            return ('door', 0)
        if ph in ('rifle', 'hunt') and not self.has_rifle and math.hypot(p.x - C2.RIFLE_POS[0], p.z - (-hz + 0.3)) < 1.8:
            return ('rifle', 0)
        dr = self.deer
        if ph == 'hunt' and dr is not None and dr.state == 'dead' and math.hypot(p.x - dr.x, p.z - dr.z) < 2.8:
            return ('deer', 0)
        return None

    def interact_ch2(self):
        if not self.focus:
            return
        kind, key = self.focus
        if kind in ('door', 'rifle', 'deer'):
            self.interact_more_ch2(kind)
            return
        if kind == 'wood':
            self.wood_taken.add(key)
            self.mp_tell('wood', i=key)
            self.wood_carried.append(key)
            self.carried += 1
            self.audio.play('wood_pick', 0.8)
            self.message("Firewood. (carrying %d)" % self.carried, 2.5)
        elif kind == 'woodpile':
            if self.carried == 0:
                self.message("Stacked: %d of %d. Go find more." % (self.stacked, C2.WOOD_NEEDED), 3)
                return
            n = self.carried
            self.carried = 0
            self.wood_carried = []
            self.audio.play('wood_drop', 0.9)
            self.mp_act('stack', n=n)

    def interact_more_ch2(self, kind):
        """The door, the rifle and the deer (after the firewood is in)."""
        if kind == 'door':
            self.mp_act('door', open=not self.w2.door_open)
        elif kind == 'rifle' and self.ch2_phase != 'rifle':
            # somebody else already took one down: there's another on the rack
            self.has_rifle = True
            self.audio.play('bolt', 0.8)
            self.message("Your father's .30-06.", 3)
        elif kind == 'rifle':
            self.mp_tell('rifle')
            self.has_rifle = True
            self.ch2_phase = 'hunt'
            self.audio.play('bolt', 0.8)
            self.deer = C2.Deer(self.w2, random.Random())
            self.message("Your father's .30-06. Four rounds left in the box.", 4)
            self.set_objective("Hunt a deer. One's been grazing straight out in front of the cabin.  [Right mouse] aim  [Left mouse] fire")
        elif kind == 'deer':
            if self.mp_on():
                p = self.player
                self.mp_act('go', name='butcher', x=round(p.x, 2), z=round(p.z, 2), yaw=round(p.yaw, 3))
            else:
                self.start_butcher()

    def start_rifle_phase(self):
        """20/20. The Goat Man moves off; the rifle is inside."""
        self.ch2_phase = 'rifle'
        if self.goat is not None:
            self.audio.play3d('goat_roar', self.goat.x, self.goat.z, 200, 0.6)
        self.goat = None
        self.audio.loop('breath', 0)
        self.fear = 0.0
        self.message("That's enough wood. Now you need food. The rifle is inside.", 5)
        self.set_objective("Go into the cabin and get the rifle.  [E] opens the door")
        self.set_resume(2, 'wood20')        # Chapter Two checkpoint: the woodpile is full

    def fire_rifle(self):
        if not self.has_rifle or self.fire_cd > 0 or self.state != 'play':
            return
        p = self.player
        self.fire_cd = 1.5
        self.muzzle_t = 0.07
        self.audio.play('rifle', 1.0)
        self.bolt_t = 0.55
        eye = p.eye()
        f = p.fwd()
        p.pitch = clamp(p.pitch + 0.045, -1.45, 1.45)
        dr = self.deer
        if dr is None:
            return
        hit = dr.hit_test(eye, f)
        if hit is not None and hit < 140:
            if self.mp_sim():
                dr.shot()
            else:
                self.mp_tell('deer_shot')
            self.message("Got it.", 2.5)
            self.set_objective("Go to the deer.")
            self.spawn_blood(dr.x, dr.y + 1.0, dr.z, 14, vel=(f[0] * 2, 1.5, f[2] * 2), spread=1.2)
        elif math.hypot(dr.x - p.x, dr.z - p.z) < 130:
            if self.mp_sim():
                dr.spook(p.x, p.z)
            else:
                self.mp_tell('deer_spook', x=round(p.x, 2), z=round(p.z, 2))
            self.message("Missed.", 2)

    # ------------------------------------------------------------------ butchering the deer
    def start_butcher(self):
        self.state = 'butcher'
        self.butcher_t = 0.0
        self.butcher_fired = set()
        self.set_mouse(False)
        self.msgs = []

    def butcher_fire(self, name, at):
        if self.butcher_t >= at and name not in self.butcher_fired:
            self.butcher_fired.add(name)
            return True
        return False

    def butcher_frame(self):
        dr = self.deer
        t = self.butcher_t
        # kneel at the deer's belly
        side = (math.cos(dr.yaw), -math.sin(dr.yaw))
        cam = (dr.x + side[0] * 1.05, dr.y + 0.95 - 0.05 * math.sin(t * 1.3), dr.z + side[1] * 1.05)
        tgt = (dr.x, dr.y + 0.35, dr.z)
        f = (tgt[0] - cam[0], tgt[1] - cam[1], tgt[2] - cam[2])
        ln = math.sqrt(sum(v * v for v in f))
        fwd = tuple(v / ln for v in f)
        return cam, fwd, tgt

    def update_butcher(self, dt):
        self.butcher_t += dt
        t = self.butcher_t
        dr = self.deer
        self.update_blood(dt)
        self.audio.loop('winter_amb', 0.5)
        cam, fwd, tgt = self.butcher_frame()
        if 0.8 < t < 6.0 and int(t / 0.45) != int((t - dt) / 0.45):
            self.audio.play_rand('eat', 3, 0.7)
            self.spawn_blood(tgt[0], tgt[1] + 0.1, tgt[2], 4, vel=(0.0, 1.2, 0.0), spread=0.6)
        if self.butcher_fire('meat', 6.2):
            self.audio.play('wood_pick', 0.6)
        if self.butcher_fire('wrap', 7.8):
            self.has_meat = True
            self.message("You wrap the meat in your coat.", 3.5)
        if self.butcher_fire('behind', 9.0):
            self.audio.play('call_near', 1.0, pan=0.0)
            self.audio.play('stinger', 0.8)
            self.message("Something is breathing behind you.", 3)
        for m in self.msgs:
            m[1] -= dt
        self.msgs = [m for m in self.msgs if m[1] > 0]
        if t > 10.2:
            self.start_run()

    def render_butcher(self):
        cam, fwd, tgt = self.butcher_frame()
        t = self.butcher_t
        lp = (cam[0] + fwd[0] * 0.4, cam[1] - 0.35, cam[2] + fwd[2] * 0.4)
        extras = []
        dr = self.deer
        # the knife, sawing along the belly
        if t < 6.2:
            ax, az = math.sin(dr.yaw), math.cos(dr.yaw)
            stroke = math.sin(t * 5.0) * 0.18
            kp = (tgt[0] + ax * stroke, tgt[1] + 0.22 + 0.05 * abs(math.cos(t * 5.0)), tgt[2] + az * stroke)
            extras.append((self.m_knife, T(*kp) @ RY(dr.yaw) @ RX(0.9)))
        # the meat, piled by your knee, then gone into your coat
        if 6.2 <= t < 7.8:
            for k in range(3):
                mp = (cam[0] + fwd[0] * 0.55 + (k - 1) * 0.15, tgt[1] + 0.06 + k * 0.05, cam[2] + fwd[2] * 0.55)
                extras.append((self.m_meat, T(*mp) @ RY(k * 0.7)))
        parts = [dr.parts()]
        self.draw_world2(cam, fwd, [(lp, 7.0, self.lantern_col())], parts=parts, extras=extras)
        y = self.UH - 120
        for m in reversed(self.msgs):
            txt, tl, td = m
            al = int(clamp(tl / 0.8, 0, 1) * clamp((td - tl) / 0.3, 0, 1) * 255)
            self.blit_text(txt, self.f_msg, (225, 215, 200), (self.UW // 2, y), 'midtop', alpha=al)
            y -= 30
        bar = int(self.UH * 0.11)
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, 0, self.UW, bar))
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, self.UH - bar, self.UW, bar))

    # ------------------------------------------------------------------ the run home
    def start_run(self, retry=False):
        p = self.player
        dr = self.deer
        if not retry:
            cam, fwd, tgt = self.butcher_frame()
            yaw_home = math.atan2(0.0 - dr.x, 0.0 - dr.z)
            self.run_start = (cam[0], cam[2], yaw_home)
        sx, sz, syaw = self.run_start
        p.reset(sx, self.w2.ground_at(sx, sz), sz, syaw)
        # he comes from the far side, behind you as you face home
        away = syaw + math.pi
        mx, mz = sx + math.sin(away) * 24, sz + math.cos(away) * 24
        for _ in range(20):
            if not self.w2.blocked(mx, mz):
                break
            away += 0.4
            mx, mz = sx + math.sin(away) * 24, sz + math.cos(away) * 24
        mx = clamp(mx, -C2.HALF + 4, C2.HALF - 4)
        mz = clamp(mz, -C2.HALF + 4, C2.HALF - 4)
        self.chaser2 = {'x': mx, 'z': mz, 'y': self.w2.ground_at(mx, mz), 'yaw': math.atan2(sx - mx, sz - mz),
                        'phase': 0.0, 'amt': 0.0, 'step': 0.0, 'snap': (0.0, 0.0, 0.0), 'snap_t': 0.0}
        self.ch2_phase = 'run'
        self.state = 'play'
        self.flash_on = True
        self.fear = 0.6
        self.set_mouse(True)
        self.set_objective("RUN BACK TO THE CABIN.")
        self.message("RUN.", 2.5)

    def update_run(self, dt):
        p = self.player
        c = self.chaser2
        tgt = self.mp_ai_target(c, 'chaser2')[0]
        sim = self.mp_sim() and not self.mp_frozen('chaser2')
        dx, dz = tgt.x - c['x'], tgt.z - c['z']
        d = math.hypot(dx, dz)
        if sim and d > 1e-3:
            sp = 3.35
            nx, nz = self.w2.collide(c['x'] + dx / d * sp * dt, c['z'] + dz / d * sp * dt, 0.4, c['x'], c['z'])
            moved = math.hypot(nx - c['x'], nz - c['z'])
            c['x'], c['z'] = nx, nz
            c['yaw'] = Moose._turn(c['yaw'], math.atan2(dx, dz), dt * 6)
            c['phase'] += moved * 2.1
            c['amt'] += (min(1.0, moved / max(dt, 1e-4) / 2.0) - c['amt']) * min(1.0, dt * 6)
            c['step'] += moved
            if c['step'] > 1.25:
                c['step'] = 0.0
                self.audio.play3d('mstep', c['x'], c['z'], 30, 1.0)
        c['y'] = self.w2.ground_at(c['x'], c['z'])
        c['snap_t'] = c.get('snap_t', 0.0) - dt
        if sim and c['snap_t'] <= 0:
            c['snap_t'] = random.uniform(0.07, 0.14)
            c['snap'] = (c['phase'], c['amt'], random.uniform(-0.6, 0.6) if random.random() < 0.4 else 0.0)
        self.audio.loop3d('breath', c['x'], c['z'], 18, 1.0)
        dl = math.hypot(p.x - c['x'], p.z - c['z'])
        self.fear += (clamp(1 - dl / 16, 0.35, 1) - self.fear) * min(1.0, dt * 3)
        self.heart_t -= dt
        if self.heart_t <= 0:
            self.heart_t = 1.05 - 0.6 * self.fear
            self.audio.play('heart', 0.25 + 0.6 * self.fear)
        if sim and d < 1.05:
            self.mp_caught(tgt, 'chaser2')
            if self.state != 'play':
                return
        # made it home
        if self.mp_gather('cabin', math.hypot(p.x, p.z - C2.CABIN_HZ) < 2.2 or (abs(p.x) < C2.CABIN_HX and abs(p.z) < C2.CABIN_HZ)):
            self.start_window_cs()

    # ------------------------------------------------------------------ the window
    def start_window_cs(self):
        self.state = 'windowcs'
        self.win_t = 0.0
        self.win_fired = set()
        self.w2.door_open = False
        self.door_angle = 0.0
        self.window_broken = False
        self.blood = []
        self.set_mouse(False)
        self.audio.loop('breath', 0)
        self.msgs = []
        self.audio.play('door_close', 1.0)

    def win_fire(self, name, at):
        if self.win_t >= at and name not in self.win_fired:
            self.win_fired.add(name)
            return True
        return False

    def update_window_cs(self, dt):
        self.win_t += dt
        t = self.win_t
        A = self.audio
        fr = self.window_frame()
        A.set_listener(fr['cam'][0], fr['cam'][2], -math.pi / 2)
        A.loop('winter_amb', 0.55)
        for i, at in enumerate((0.6, 1.3, 2.0, 2.7, 3.4)):
            if self.win_fire('hb%d' % i, at):
                A.play('heart', 0.7)
        if self.win_fire('face', 4.9):
            A.play('stinger', 1.0)
            A.play('breath', 0.8)
        if self.win_fire('goatroar', 6.0):
            A.play('goat_roar', 1.0, pan=0.5)
        if self.win_fire('shove', 6.9):
            A.play('tackle', 1.0)
        if self.win_fire('punch', 7.9):
            A.play('impact', 0.9)
            g = fr.get('goat_root')
            if g:
                self.spawn_blood(g[0], g[1] + 2.4, g[2], 12, vel=(0.0, 1.5, -2.0), spread=1.2)
        if self.win_fire('mooserun', 8.7):
            A.play('call_near', 0.8, pan=-0.3)
        for i in range(5):
            if self.win_fire('mstep%d' % i, 8.7 + i * 0.3):
                A.play('mstep', 0.8 - i * 0.14)
        if self.win_fire('goatroar2', 10.6):
            A.play('goat_roar', 1.0)
        if self.win_fire('smash', 11.4):
            self.window_broken = True
            A.play('glass', 1.0)
            for _ in range(3):
                self.spawn_blood(-C2.CABIN_HX + 0.1, C2.WINDOW_Y, C2.WINDOW_Z, 18, vel=(3.5, 1.0, 0.0), spread=1.4,
                                 size=(0.02, 0.05), key='shard')
        if self.win_fire('goatroar3', 12.4):
            A.play('goat_roar', 1.0)
        if self.win_fire('elk', 13.7):
            A.play('elk_bugle', 1.0, pan=0.4)
        if self.win_fire('bite', 14.4):
            A.play('impact', 1.0)
            A.play('goat_roar', 0.8)
            g = fr.get('goat_root')
            if g:
                self.spawn_blood(g[0], g[1] + 2.2, g[2], 30, vel=(0.5, 2.5, 0.0), spread=2.0, size=(0.03, 0.07))
        for i in range(8):
            if self.win_fire('estep%d' % i, 16.0 + i * 0.32):
                A.play('mstep', 0.9 - i * 0.1)
        if self.win_fire('elk2', 17.2):
            A.play('elk_bugle', 0.5, pan=-0.6)
        self.update_blood(dt)
        self.fade = clamp((t - 20.0) / 1.6, 0, 1)
        self.fear = 0.85 if 4.5 < t < 18 else 0.3
        if t > 21.8:
            # Chapter Two is done: straight on into Chapter Three
            self.fade = 0.0
            self.start_ch3()

    def window_frame(self):
        """Everything seen through the window at time t."""
        t = self.win_t
        Y = C2.CABIN_Y
        wx, wy, wz = -C2.CABIN_HX, C2.WINDOW_Y, C2.WINDOW_Z

        def sm(a, b):
            k = clamp((t - a) / (b - a), 0, 1)
            return k * k * (3 - 2 * k)

        def lerp(a, b, k):
            return a + (b - a) * k

        def lerp3(a, b, k):
            return tuple(a[i] + (b[i] - a[i]) * k for i in range(3))

        out = {'parts': []}
        # ---- camera: from the door to the window; flinch back when the glass goes; creep back after
        p0 = (0.1, Y + 1.62, 1.3)
        p1 = (-1.7, Y + 1.42, wz)
        cam = lerp3(p0, p1, sm(0.6, 2.8))
        cam = lerp3(cam, (-0.55, Y + 1.4, wz + 0.15), sm(11.4, 11.8))
        cam = lerp3(cam, (-1.6, Y + 1.45, wz), sm(18.6, 20.5))
        look = lerp3((0.1, Y + 1.5, -1.5), (wx - 1.2, wy, wz), sm(0.4, 2.2))
        if 11.4 < t < 12.0:
            cam = (cam[0] + random.uniform(-0.03, 0.03), cam[1] + random.uniform(-0.03, 0.03), cam[2])
        out['cam'] = cam
        out['look'] = look

        def align(pose_fn, target, yaw, **kw):
            _, h = pose_fn(0.0, 0.0, 0.0, yaw, **kw)
            return (target[0] - float(h[0, 3]), target[1] - float(h[1, 3]), target[2] - float(h[2, 3]))

        # ---- the Moose Man at the glass
        mkw = dict(hunch=0.9, roll=0.0, head_pitch=-0.35, reach=0.35, jaw=0.15, t=self.time)
        stare = (wx - 0.72, wy + 0.02, wz)
        R0 = align(lambda x, y, z, yaw, **kw: pose_moose(x, y, z, yaw, 0.0, 0.0, **kw), stare, math.pi / 2, **mkw)
        if 4.0 <= t < 10.2:
            if t < 6.7:
                rise = sm(4.0, 5.4)
                root = (R0[0], R0[1] - 0.9 * (1 - rise), R0[2])
                mkw['roll'] = 0.45 * sm(5.6, 6.5)
                mkw['jaw'] = 0.15 + 0.3 * sm(6.0, 6.6)
                yaw = math.pi / 2
            elif t < 8.6:
                k = sm(6.7, 7.3)
                root = (R0[0] - 0.4 * k, R0[1], R0[2] + 1.8 * k)
                yaw = lerp(math.pi / 2, math.pi, sm(6.9, 7.6))
                mkw['roll'] = 0.45 - 1.0 * k + 0.6 * sm(7.3, 7.8)
                mkw['reach'] = 0.35 + (1.7 * math.sin(math.pi * clamp((t - 7.6) / 0.5, 0, 1)) if t > 7.6 else 0.0)
                mkw['jaw'] = 0.6
            else:
                k = (t - 8.6) / 1.6
                root = (R0[0] - 0.4 - 13.0 * k, R0[1], R0[2] + 1.8 + 1.5 * k)
                yaw = -math.pi / 2 - 0.1
                mkw.update(hunch=0.75, roll=0.0, reach=0.5)
                out['parts'].append(pose_moose(root[0], root[1], root[2], yaw, t * 12, 1.0, **mkw)[0])
                root = None
            if root is not None:
                out['parts'].append(pose_moose(root[0], root[1], root[2], yaw, 0.0, 0.0, **mkw)[0])
        # ---- the Goat Man
        gkw = dict(hunch=0.95, jaw=0.6, arms=0.1, bloody=True, t=self.time, head_pitch=-0.2)
        smash_head = (wx - 0.5, wy + 0.05, wz)
        RG = align(pose_goat, smash_head, math.pi / 2, **gkw)
        groot = None
        if 5.9 <= t < 14.4:
            if t < 6.9:
                k = sm(5.9, 6.9)
                groot = (lerp(wx - 4.5, R0[0] - 0.6, k), Y, lerp(wz - 6.5, R0[2] - 0.9, k))
                gyaw = math.atan2((R0[0] - 0.6) - (wx - 4.5), (R0[2] - 0.9) - (wz - 6.5))
                g = pose_goat(groot[0], groot[1], groot[2], gyaw, walk_phase=t * 13, walk_amt=1.0, hunch=0.9,
                              arms=1.0 + 0.3 * sm(6.6, 6.9), bloody=True, t=self.time)
            elif t < 10.2:
                hit = sm(7.8, 8.2)
                base = (R0[0] - 0.6, Y, R0[2] - 0.9 - 0.9 * hit)
                gyaw = lerp(0.3, -math.pi / 2, sm(8.8, 9.6))
                groot = base
                g = pose_goat(base[0], base[1], base[2], gyaw, hunch=0.55, arms=0.4, jaw=0.5 + 0.4 * hit,
                              roll=0.5 * hit * (1 - sm(8.4, 9.0)), bloody=True, t=self.time)
            else:
                k = sm(10.2, 11.2)
                base0 = (R0[0] - 0.6, Y, R0[2] - 1.8)
                groot = lerp3(base0, RG, k)
                push = sm(11.6, 12.4)
                groot = (groot[0] + 0.4 * push, groot[1], groot[2])
                gkw2 = dict(gkw)
                gkw2['arms'] = 0.1 + 1.1 * math.sin(math.pi * clamp((t - 11.1) / 0.5, 0, 1))
                gkw2['jaw'] = 0.6 + 0.4 * push * abs(math.sin(t * 4))
                gkw2['roll'] = 0.25 * math.sin(t * 2.3) * push
                gyaw = lerp(-math.pi / 2, math.pi / 2, k)
                g = pose_goat(groot[0], groot[1], groot[2], gyaw, **gkw2)
            out['parts'].append(g[0])
            out['goat_root'] = groot
        # ---- the Elk, and the Goat Man in its jaws
        ekw = dict(head_pitch=0.65, jaw=0.9, split=1.0, t=self.time)
        if t >= 13.6:
            gpush = (RG[0] + 0.4, RG[1], RG[2])
            torso = (gpush[0] - 0.2, gpush[1] + 2.15, gpush[2])
            # it comes from behind him (the west), facing the cabin, so its body stays outside
            eyaw0 = math.pi / 2
            _, eh = pose_elk(0.0, 0.0, 0.0, eyaw0, **ekw)
            mouth_off = eh @ np.array([0.0, -0.1, 0.8, 1.0])
            if t < 14.4:
                k = sm(13.6, 14.4)
                mouth = lerp3((torso[0] - 2.2, torso[1] + 3.0, torso[2] + 0.4), torso, k)
                ekw['jaw'] = 0.9
            elif t < 16.0:
                k = sm(14.4, 15.8)
                mouth = lerp3(torso, (torso[0] - 2.0, torso[1] + 1.5, torso[2]), k)
                ekw['jaw'] = 0.35
                ekw['split'] = 0.4
            else:
                mouth = None
            if mouth is not None:
                eroot = (mouth[0] - mouth_off[0], mouth[1] - mouth_off[1], mouth[2] - mouth_off[2])
                out['parts'].append(pose_elk(eroot[0], eroot[1], eroot[2], eyaw0, **ekw)[0])
            else:
                # turning, and running off into the trees with him
                k = (t - 16.0) / 2.5
                ekw.update(head_pitch=0.35, jaw=0.35, split=0.4)
                last = (torso[0] - 2.0, torso[1] + 1.5, torso[2])
                base = (last[0] - mouth_off[0], last[1] - mouth_off[1], last[2] - mouth_off[2])
                eyaw = lerp(eyaw0, -math.pi / 2 + 0.3, sm(16.0, 16.7))
                eroot = (base[0] - 16.0 * k, base[1] - 0.6 * sm(16.0, 16.6), base[2])
                parts, eh2 = pose_elk(eroot[0], eroot[1], eroot[2], eyaw, phase=t * 6, amt=1.0, **ekw)
                out['parts'].append(parts)
                m2 = eh2 @ np.array([0.0, -0.1, 0.8, 1.0])
                mouth = (float(m2[0]), float(m2[1]), float(m2[2]))
            if t >= 14.4 and mouth is not None and t < 19.0:
                # the Goat Man hangs from its jaws, kicking
                gr = (mouth[0] + 0.2, mouth[1] - 2.15, mouth[2])
                kick = 1.0 if t < 16.5 else 0.5
                out['parts'].append(pose_goat(gr[0], gr[1], gr[2], -math.pi / 2 + 0.4, walk_phase=t * 18, walk_amt=kick,
                                              hunch=0.4, arms=0.8 + 0.6 * math.sin(t * 9), jaw=1.0, tilt=0.35,
                                              roll=0.4 * math.sin(t * 7), bloody=True, t=self.time)[0])
                out['goat_root'] = gr
        return out

    def render_window_cs(self):
        fr = self.window_frame()
        cam, look = fr['cam'], fr['look']
        f = (look[0] - cam[0], look[1] - cam[1], look[2] - cam[2])
        ln = math.sqrt(sum(v * v for v in f))
        fwd = tuple(v / ln for v in f)
        yaw = math.atan2(fwd[0], fwd[2])
        lp = self.held_lantern_pos(cam, yaw, 0.0)
        wx = -C2.CABIN_HX
        lights = [((lp[0], lp[1] + 0.2, lp[2]), 10.0, self.lantern_col()),
                  # cold moonlight outside the window, so the shapes out there read
                  ((wx - 1.6, C2.WINDOW_Y + 1.8, C2.WINDOW_Z), 7.5, (0.35, 0.42, 0.62)),
                  ((wx - 4.0, C2.WINDOW_Y + 3.5, C2.WINDOW_Z), 10.0, (0.2, 0.24, 0.36))]
        self.draw_world2(cam, fwd, lights, parts=fr['parts'], hold=(True, yaw, 0.0), fov=56)
        bar = int(self.UH * 0.11)
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, 0, self.UW, bar))
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, self.UH - bar, self.UW, bar))

    def chaser2_parts(self):
        c = self.chaser2
        ph, amt, roll = c['snap']
        return pose_moose(c['x'], c['y'], c['z'], c['yaw'], ph, amt, hunch=0.75, roll=roll, reach=0.7,
                          jaw=0.45, t=self.time)[0]

    def finish_ch2(self):
        self.progress['ch3'] = True
        save_progress(self.progress)
        self.ending_pages = lore.CH2_ENDING
        self.state = 'ch2_end'
        self.ch2_end_t = 0.0
        self.set_mouse(False)
        self.audio.loop('breath', 0)
        self.message("That's enough. Inside, now.", 4)

    def update_ch2_end(self, dt):
        self.ch2_end_t += dt
        self.fade = clamp((self.ch2_end_t - 1.5) / 2.0, 0, 1)
        if self.ch2_end_t > 1.0 and 'door_end' not in self.flags:
            self.flags.add('door_end')
            self.audio.play('door_close', 0.9)
        if self.ch2_end_t > 4.0:
            self.fade = 0.0
            self.start_ending()

    def draw_world2(self, cam, fwd, lights, door=None, lantern_at=None, lantern_lit=True, hold=None, parts=(),
                    up=(0.0, 1.0, 0.0), fov=None, extras=(), env=None, snowcover=False, blizzard=0.0):
        """Render the Chapter 2 map."""
        r = self.r
        w2 = self.w2
        all_lights = self.mp_lights() + list(lights)
        parts = list(parts) + self.mp_parts(cam, fwd)
        for L_ in w2.lights:
            x, y, z = L_['pos']
            if math.hypot(x - cam[0], z - cam[2]) < L_['rad'] + 40:
                k = (0.75 + 0.25 * math.sin(self.time * 9) * math.sin(self.time * 5.3 + 1.7)) * 1.9
                c = L_['col']
                all_lights.append(((x, y, z), L_['rad'], (c[0] * k, c[1] * k, c[2] * k)))
        storm = self.storm
        if env is None:
            env = {'ambient': (0.055, 0.06, 0.075), 'mooncol': (0.05, 0.055, 0.07), 'moondir': (0.3, -0.8, 0.5),
                   'fog': (0.045, 0.05, 0.06), 'fogdens': 0.04 + 0.03 * storm}
        r.begin(cam, fwd, fov or self.settings['fov'], env, self.time, 0.0, cam, fwd, all_lights[:8], up=up)
        r.draw(self.m_ch2)
        r.draw(self.m_water2)
        if snowcover:
            r.draw(self.m_cover2)
        if blizzard > 0:
            self.draw_blizzard(cam, blizzard)
        Y = C2.CABIN_Y
        if door is None:
            door = self.door_angle
        r.draw(self.m_door, model=T(C2.DOOR_HINGE_X, Y + 0.05, C2.CABIN_HZ) @ RY(door))
        if not self.window_broken:
            r.draw(self.m_bars)
        if not self.has_rifle:
            r.draw(self.m_rifle, model=T(C2.RIFLE_POS[0], C2.RIFLE_POS[1], -C2.CABIN_HZ + 0.24) @ RY(math.pi / 2) @ RZ(0.05))
        for mesh, M in extras:
            r.draw(mesh, model=M)
        for i, (wx, wy, wz, rot) in enumerate(w2.wood_spots):
            if i not in self.wood_taken:
                r.draw(self.m_wood, model=T(wx, wy, wz) @ RY(rot))
        # the porch woodpile grows as you stack
        px, pz = C2.WOODPILE
        for k in range(min(self.stacked, C2.WOOD_NEEDED)):
            row, col = divmod(k, 5)
            r.draw(self.m_log, model=T(px - 0.42 + col * 0.19, Y + 0.24 + row * 0.165, pz) @ RY(0.04 * ((k * 7) % 3 - 1)))
        if lantern_at is not None:
            r.draw(self.m_lantern, model=T(*lantern_at))
            r.draw(self.m_lantern_lit if lantern_lit else self.m_lantern_off, model=T(*lantern_at))
        if hold and hold[0]:
            _, yaw, pitch = hold
            lp = self.held_lantern_pos(cam, yaw, pitch)
            M = T(*lp) @ RY(yaw) @ RZ(0.05 * math.sin(self.time * 2.1))
            r.draw(self.m_lantern, model=M)
            r.draw(self.m_lantern_lit if lantern_lit else self.m_lantern_off, model=M)
        for pl in parts:
            for key, M in pl:
                r.draw(self.m_moose[key], model=M)
        # blood and glass
        for b in self.blood:
            key = b[9] if len(b) > 9 else 'blood'
            if b[7]:
                s = b[6] * 2.4
                r.draw(self.m_moose[key], model=T(b[0], b[1] - 0.005 + b[8], b[2]) @ S(s, 0.006, s * 0.8))
            else:
                s = b[6]
                r.draw(self.m_moose[key], model=T(b[0], b[1], b[2]) @ S(s, s * 1.6, s))

    def render_ch2_scene(self):
        p = self.player
        cam = p.eye()
        fwd = p.fwd()
        lights = []
        lp = self.held_lantern_pos(cam, p.yaw, p.pitch)
        lit = self.flash_on and self.flicker_t <= 0
        if lit:
            lights.append(((lp[0], lp[1] + 0.2, lp[2]), 10.0, self.lantern_col()))
        parts = []
        gt = self.goat
        if gt is not None and not self.mp_hidden('goat'):
            ph, amt, roll = gt.snap
            parts.append(C2_goat_parts(gt.x, gt.y, gt.z, gt.yaw, ph, amt, roll, gt.state in ('chase', 'search'), self.time))
        if self.deer is not None and self.ch2_phase == 'hunt':
            parts.append(self.deer.parts())
        if self.chaser2 is not None and self.ch2_phase == 'run' and not self.mp_hidden('chaser2'):
            parts.append(self.chaser2_parts())
        extras = []
        fov = None
        if self.has_rifle:
            # the rifle: at the hip, or up at the eye looking down the scope
            yaw, pitch = p.yaw, p.pitch
            right = (-math.cos(yaw), 0.0, math.sin(yaw))
            upv = (right[1] * fwd[2] - right[2] * fwd[1], right[2] * fwd[0] - right[0] * fwd[2],
                   right[0] * fwd[1] - right[1] * fwd[0])
            hip = tuple(cam[i] + right[i] * 0.2 + fwd[i] * 0.42 - upv[i] * 0.24 for i in range(3))
            eye = tuple(cam[i] + fwd[i] * 0.3 - upv[i] * 0.075 for i in range(3))
            a = self.aim
            pos = tuple(hip[i] + (eye[i] - hip[i]) * a for i in range(3))
            kick = 0.08 * (self.fire_cd / 1.5) ** 6
            M = T(*pos) @ RY(yaw) @ RX(-pitch - kick)
            extras.append((self.m_rifle, M))
            fov = self.settings['fov'] + (26 - self.settings['fov']) * a
            if self.muzzle_t > 0:
                mp = tuple(pos[i] + fwd[i] * 0.85 for i in range(3))
                lights.insert(0, (mp, 8.0, (2.5, 1.8, 0.9)))
                extras.append((self.m_moose['eye'], T(*mp) @ S(0.12)))
        self.draw_world2(cam, fwd, lights, lantern_lit=lit, hold=(True, p.yaw, p.pitch), parts=parts, extras=extras,
                         fov=fov)

    def goat_face_parts(self, cam, yaw, dist):
        roll = random.uniform(-0.25, 0.25)
        jaw = 0.8 + random.uniform(0, 0.25)
        kw = dict(hunch=0.6, roll=roll, jaw=jaw, arms=1.0, head_pitch=-0.45, bloody=True, t=self.time)
        _, head = pose_goat(0, 0, 0, yaw + math.pi, **kw)
        hx, hy, hz = float(head[0, 3]), float(head[1, 3]), float(head[2, 3])
        tx = cam[0] + math.sin(yaw) * dist
        tz = cam[2] + math.cos(yaw) * dist
        return pose_goat(tx - hx, cam[1] + 0.1 - hy, tz - hz, yaw + math.pi, **kw)[0]

    # ================================================================== CHAPTER 3
    BLIZZARD_ENV = {'ambient': (0.13, 0.14, 0.16), 'mooncol': (0.08, 0.09, 0.11), 'moondir': (0.3, -0.8, 0.5),
                    'fog': (0.2, 0.215, 0.24), 'fogdens': 0.075}

    def start_ch3(self):
        """CHAPTER THREE: the opening cutscene (cabin, blizzard, the cave, the Elk)."""
        self.new_game()
        self.chapter = 3
        self.progress['ch3'] = True
        self.set_resume(3, 'start')
        self.state = 'wake3'
        self.w3_t = 0.0
        self.w3_fired = set()
        self.window_broken = True
        self.msgs = []
        self.set_mouse(False)
        self.audio.stop_all()
        self.audio.stop_loops()
        self.clock_t = (3 * 86400 + 3 * 3600 + 12 * 60) - (23 * 3600 + 58 * 60 + 7)

    def w3_fire(self, name, at):
        if self.w3_t >= at and name not in self.w3_fired:
            self.w3_fired.add(name)
            return True
        return False

    def update_wake3(self, dt):
        self.w3_t += dt
        self.clock_t += dt
        t = self.w3_t
        A = self.audio
        A.loop('winter_amb', 0.0 if t < 3.5 else (0.95 if 8.5 < t < 18.5 else 0.45))
        A.loop('sewer_amb', 0.45 if t > 18.5 else 0.0)
        for at, text, dur in lore.CH3_WAKE_LINES:
            if self.w3_fire('l%.1f' % at, at):
                self.message(text, dur)
        if self.w3_fire('door', 9.3):
            A.play('door_open', 0.7)
        for i in range(10):
            if self.w3_fire('snowstep%d' % i, 9.8 + i * 0.42):
                A.play_rand('step_snow', 4, 0.6)
        for i in range(4):
            if self.w3_fire('cavestep%d' % i, 15.2 + i * 0.5):
                A.play_rand('step_conc', 4, 0.4)
        if self.w3_fire('growl', 23.3):
            A.play('breath', 1.0)
            A.play('heart', 0.8)
        if self.w3_fire('bugle', 26.0):
            A.play('elk_bugle', 0.8)
            A.play('stinger', 0.7)
        for m in self.msgs:
            m[1] -= dt
        self.msgs = [m for m in self.msgs if m[1] > 0]
        f = 0.0
        for a, b_ in ((3.5, 4.2), ):
            f = max(f, 1 - clamp((t - a) / (b_ - a), 0, 1)) if t > a else 1.0
        if t < 3.5:
            f = 1.0
        f = max(f, clamp((t - 13.6) / 0.6, 0, 1) * clamp((15.0 - t) / 0.6, 0, 1))
        f = max(f, clamp((t - 19.6) / 0.8, 0, 1) * clamp((23.0 - t) / 0.6, 0, 1))
        self.fade = f
        if t > 28.0:
            self.fade = 0.0
            self.begin_ch3()

    def render_wake3(self):
        t = self.w3_t
        Y = C2.CABIN_Y
        msgs_and_bars = True

        def lerp3(a, b, k):
            return tuple(a[i] + (b[i] - a[i]) * k for i in range(3))

        def sm(a, b):
            k = clamp((t - a) / (b - a), 0, 1)
            return k * k * (3 - 2 * k)

        def look(cam, tgt):
            f = (tgt[0] - cam[0], tgt[1] - cam[1], tgt[2] - cam[2])
            ln = math.sqrt(sum(v * v for v in f))
            return tuple(v / ln for v in f)
        if t < 3.5:
            self.r.fbo.use()
            self.r.fbo.clear(0, 0, 0, 1)
            a = int(255 * clamp((t - 0.3) / 0.8, 0, 1) * clamp((3.4 - t) / 0.6, 0, 1))
            self.blit_text("CHAPTER THREE", self.f_big, (210, 205, 198), (self.UW // 2, self.UH // 2 - 40), 'midtop', alpha=a)
            msgs_and_bars = False
        elif t < 8.5:
            # the stove is dying
            cam = (-1.6, Y + 1.15, -0.85)
            fwd = look(cam, (0.6, Y + 0.6, -1.5))
            glow = clamp(1.0 - (t - 3.5) / 4.5, 0.05, 1.0)
            lights = [((0.6, Y + 0.6, -1.15), 4.5, (1.4 * glow, 0.5 * glow, 0.15 * glow)),
                      ((1.5, Y + 0.95, -1.3), 7.0, self.lantern_col())]
            self.draw_world2(cam, fwd, lights, door=0.0, lantern_at=(1.5, Y + 0.78, -1.3), lantern_lit=True)
        elif t < 13.6:
            if t < 9.4:
                # at the broken window: a blizzard, knee-deep snow
                cam = (-1.9, Y + 1.42, C2.WINDOW_Z)
                fwd = look(cam, (-8.0, Y + 1.0, C2.WINDOW_Z - 1.0))
            else:
                # out into it, lantern held up, wading
                k = sm(9.4, 13.6)
                cam = lerp3((0.0, Y + 1.55, 3.4), (2.0, Y + 1.35, 16.0), k)
                cam = (cam[0], cam[1] + 0.06 * math.sin(t * 7), cam[2])
                fwd = look(cam, (cam[0] + 0.4, cam[1] - 0.2, cam[2] + 6))
            lp = self.held_lantern_pos(cam, math.atan2(fwd[0], fwd[2]), 0.0)
            self.draw_world2(cam, fwd, [((lp[0], lp[1] + 0.2, lp[2]), 8.0, self.lantern_col())],
                             hold=(t >= 9.4, math.atan2(fwd[0], fwd[2]), 0.0), env=self.BLIZZARD_ENV,
                             snowcover=True, blizzard=1.0)
        elif t < 19.6:
            lv = self.lv_up
            mx = lv.ox + 14 * C3.C
            if t < 18.2:
                # the cave mouth, out of the storm
                k = sm(14.2, 18.2)
                cam = lerp3((mx + 1.5, 1.5, lv.oz - 16.0), (mx, 1.55, lv.oz + 6.0), k)
                fwd = look(cam, (mx, 1.6, lv.oz + 14.0))
            else:
                # lie down on the cold floor
                k = sm(18.2, 19.6)
                cam = lerp3((mx, 1.55, lv.oz + 6.0), (mx + 0.4, 0.35, lv.oz + 11.5), k)
                fwd = look(cam, (mx + 0.4, 2.0 - 1.4 * k, lv.oz + 16.0))
            yaw = math.atan2(fwd[0], fwd[2])
            lp = self.held_lantern_pos(cam, yaw, 0.0)
            self.draw_world3(lv, cam, fwd, [((lp[0], lp[1] + 0.2, lp[2]), 8.0, self.lantern_col())],
                             hold=(True, yaw, 0.0), blizzard=1.0)
        else:
            lv = self.lv_up
            mx = lv.ox + 14 * C3.C
            if t < 23.0:
                self.r.fbo.use()
                self.r.fbo.clear(0, 0, 0, 1)
                a = int(255 * clamp((t - 20.4) / 0.7, 0, 1) * clamp((22.8 - t) / 0.6, 0, 1))
                self.blit_text("LATER", self.f_big, (200, 195, 188), (self.UW // 2, self.UH // 2 - 30), 'midtop', alpha=a)
            else:
                # a growl. look at the entrance: out in the storm, it is coming
                k = sm(23.0, 25.0)
                cam = (mx + 0.4, 0.35 + 0.35 * sm(25.5, 27.5), lv.oz + 11.5)
                fwd = look(cam, (mx + 0.4 - 2.0 * (1 - k), 0.9, lv.oz + 11.5 - 8.0 * k - 1.0))
                ez = lv.oz - 30.0 + 8.0 * sm(23.0, 28.0)
                elk = pose_elk(mx - 0.5, 0.0, ez, 0.0, phase=t * 4, amt=1.0, jaw=0.5, split=0.4, t=self.time)[0]
                # grey storm light at the mouth, so its pale shape shows against the snow
                storm = {'ambient': (0.1, 0.11, 0.13), 'mooncol': (0.1, 0.11, 0.14), 'moondir': (0.3, -0.8, 0.5),
                         'fog': (0.13, 0.14, 0.16), 'fogdens': 0.024}
                self.draw_world3(lv, cam, fwd, [], parts=[elk], blizzard=1.0, env_override=storm)
        if msgs_and_bars:
            y = self.UH - 120
            for m in reversed(self.msgs):
                txt, tl, td = m
                al = int(clamp(tl / 0.8, 0, 1) * clamp((td - tl) / 0.3, 0, 1) * 255)
                self.blit_text(txt, self.f_msg, (225, 215, 200), (self.UW // 2, y), 'midtop', alpha=al)
                y -= 30
            bar = int(self.UH * 0.11)
            pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, 0, self.UW, bar))
            pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, self.UH - bar, self.UW, bar))

    def begin_ch3(self, where='start'):
        """Gameplay: the upper mine (start) or the lower mine (after the elevator)."""
        self.chapter = 3
        self.state = 'play'
        self.flash_on = True
        self.fear = 0.0
        self.red = 0.0
        self.glitch = 0.0
        self.heart_t = 0.0
        self.blood = []
        p = self.player
        if where == 'start':
            lv = self.lv_up
            self.lv = lv
            sx, sz = lv.spawn
            p.reset(sx + 0.4, lv.y0, sz + 4.5, math.pi)
            # it comes in out of the storm
            mx = lv.ox + 14 * C3.C
            self.elk = C3.ElkHunter(lv, mx - 0.5, lv.oz - 38.0)
            self.elk.state = 'enter'
            self.elk.go_to(*lv.center(14, 8))
            self.elk.path = [(mx - 0.5, lv.oz - 4.0)] + self.elk.path
            self.elk.grace = 4.0
            self.set_objective("HIDE. Get into the narrow mineshafts -- it's too big to follow.")
            self.message("It can't fit in the mineshafts.", 4)
        else:
            lv = self.lv_low
            self.lv = lv
            sx, sz = lv.spawn
            p.reset(sx, lv.y0, sz, 0.0)
            self.elk = None
            self.goat_found_t = -1.0
            self.power = True
            self.set_objective("Keep going. Find a way out of the mine.")
        self.set_mouse(True)

    def continue_ch3_lower(self):
        self.chapter = 3
        for lev in self.lv_up.levers:
            lev.update(pulled=True, angle=0.8)
        self.begin_ch3('lower')

    def respawn_ch3(self):
        lv = self.lv
        p = self.player
        sx, sz = lv.safe
        p.reset(sx, lv.y0, sz, 0.0)
        cells = [c for c in lv.elk_cells() if math.hypot(lv.center(*c)[0] - sx, lv.center(*c)[1] - sz) > 30]
        if self.elk is not None or lv is self.lv_up:
            ex, ez = lv.center(*random.choice(cells))
            self.elk = C3.ElkHunter(lv, ex, ez)
            self.elk.grace = 8.0
        self.flash_on = True
        self.fear = 0.0
        self.red = 0.0
        self.glitch = 0.0
        self.msgs = []
        self.message("You wake in the dark of the mineshaft. It's somewhere out there.", 4)
        self.state = 'play'
        self.set_mouse(True)

    def update_ch3(self, dt):
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
        outside = lv.has_outside and p.z < lv.oz
        if outside:
            speed *= 0.6            # knee-deep snow
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
            if outside:
                self.audio.play_rand('step_snow', 4, vol)
            else:
                self.audio.play_rand('step_conc', 4, vol)
            rad = 2.5 if crouch else (20 if sprint else 8)
            if self.elk:
                self.elk.hear(p.x, p.z, rad)
        f = p.fwd()
        a = min(1.0, dt * 16)
        self.flash_dir = tuple(self.flash_dir[i] + (f[i] - self.flash_dir[i]) * a for i in range(3))
        self.flicker_t = max(0.0, self.flicker_t - dt)
        self.audio.set_listener(p.x, p.z, p.yaw)
        near_mouth = lv.has_outside and p.z < lv.oz + 10
        self.audio.loop('winter_amb', 0.7 if near_mouth else 0.12)
        self.audio.loop('sewer_amb', 0.25 if near_mouth else 0.55)
        self.audio.loop('forest_amb', 0.0)
        self.audio.loop('title_amb', 0.0)
        # levers
        turning = False
        for i, lev in enumerate(lv.levers):
            if lev['pulled']:
                lev['angle'] += (0.8 - lev['angle']) * min(1.0, dt * 8)
                continue
            if self.focus == ('lever', i) and keys[pygame.K_e]:
                turning = True
                lev['progress'] += dt / 1.6
                lev['angle'] = -0.8 + 1.0 * lev['progress']
                self.lever_noise_t = getattr(self, 'lever_noise_t', 0.0) - dt
                if self.lever_noise_t <= 0:
                    self.lever_noise_t = 0.5
                    if self.elk:
                        self.elk.hear(lev['pos'][0], lev['pos'][2], 30.0)
                if lev['progress'] >= 1.0:
                    self.mp_act('lever', i=i)
                    turning = False
        self.audio.loop('creak', 0.6 if turning else 0.0)
        # the lower mine: what's left of the Goat Man, and then the Elk
        if lv is self.lv_low:
            gx, gz = lv.center(*lv.goat_cell)
            if self.goat_found_t < 0 and math.hypot(p.x - gx, p.z - gz) < 8.0:
                self.goat_found_t = 0.0
                self.message("The Goat Man. What's left of him.", 4.5)
                self.audio.play('stinger', 0.6)
                self.mp_tell('goatfound')
            if self.goat_found_t >= 0:
                self.goat_found_t += dt
                if self.elk is None and self.goat_found_t > 5.0 and self.mp_sim():
                    ex, ez = lv.center(26, 20)
                    self.elk = C3.ElkHunter(lv, ex, ez)
                    self.elk.state = 'investigate'
                    self.elk.go_to(gx + 3.0, gz)
                    self.audio.play3d('elk_bugle', ex, ez, 90, 1.0)
                    self.message("It followed you down.", 3.5)
                    self.set_objective("Find a way out of the mine.")
            if self.mp_gather('exit3', lv.cell_of(p.x, p.z) == lv.exit):
                self.start_exit3()
                return
        if self.mp_on() and lv is self.lv_up and lv.elevator:
            cx, cz = lv.center(*lv.elevator)
            self.mp_gather('elevator', self.power and math.hypot(p.x - cx, p.z - cz) < 1.7)
        self.update_elk(dt)
        if self.state != 'play':
            return
        self.focus = self.find_focus_ch3()
        self.obj_t = max(0.0, self.obj_t - dt)
        self.glitch += (0.0 - self.glitch) * min(1.0, dt * 20)

    def update_elk(self, dt):
        e = self.elk
        p = self.player
        if e is None:
            self.fear += (0.0 - self.fear) * min(1.0, dt * 2)
            self.audio.loop('breath', 0)
            return
        tgt, lit = self.mp_ai_target(e, 'elk')
        if self.mp_sim() and not self.mp_frozen('elk'):
            e.update(dt, tgt, lit)
        for ev in self.mp_events('elk', e):
            if ev == 'step':
                self.audio.play3d('mstep', e.x, e.z, 45, 1.0)
            elif ev == 'roar':
                self.audio.play3d('elk_bugle', e.x, e.z, 80, 1.0)
                self.audio.play('stinger', 0.5)
            elif ev == 'lost':
                if 'elk_lost' not in self.flags:
                    self.flags.add('elk_lost')
                    self.message("Don't move. Don't make a light.", 4)
            elif ev == 'leave':
                if 'elk_leave' not in self.flags:
                    self.flags.add('elk_leave')
                    self.message("It's moving on.", 3)
            elif ev == 'kill':
                self.mp_caught(tgt, 'elk')
        e.events = []
        d = math.hypot(e.x - p.x, e.z - p.z)
        tf = clamp(1 - d / 24, 0, 1)
        if e.state == 'chase':
            tf = max(tf, 0.6)
        elif e.state == 'search':
            tf = max(tf, 0.75)
        self.fear += (tf - self.fear) * min(1.0, dt * 3)
        self.audio.loop3d('breath', e.x, e.z, 22, 1.0)
        if self.fear > 0.15:
            self.heart_t -= dt
            if self.heart_t <= 0:
                self.heart_t = 1.05 - 0.6 * self.fear
                self.audio.play('heart', 0.25 + 0.6 * self.fear)
        if self.fear > 0.4 and random.random() < dt * self.fear * 2.5:
            self.flicker_t = random.uniform(0.04, 0.2)

    def find_focus_ch3(self):
        p = self.player
        lv = self.lv
        ex, ey, ez = p.eye()
        f = p.fwd()
        best, bestd = None, -1
        for i, lev in enumerate(lv.levers):
            if lev['pulled']:
                continue
            dx, dy, dz = lev['pos'][0] - ex, lev['pos'][1] - ey, lev['pos'][2] - ez
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if d < 2.3:
                dot = (dx * f[0] + dy * f[1] + dz * f[2]) / max(d, 1e-4)
                if dot > 0.6 and dot > bestd:
                    best, bestd = ('lever', i), dot
        if best:
            return best
        if lv is self.lv_up and lv.elevator:
            cx, cz = lv.center(*lv.elevator)
            if math.hypot(p.x - cx, p.z - cz) < 1.7:
                return ('elevator', 0)
        return None

    def interact_ch3(self):
        if not self.focus:
            return
        kind, _ = self.focus
        if kind == 'elevator':
            if self.power and self.mp_on():
                self.message("Everyone has to be in the cage.", 2.5)
            elif self.power:
                self.start_ride()
            else:
                self.message("The elevator is dead. There's no power.", 3)

    # ------------------------------------------------------------------ the elevator ride
    def start_ride(self):
        self.state = 'ride'
        self.ride_t = 0.0
        self.set_mouse(False)
        self.audio.play('clunk', 1.0)
        self.audio.loop('breath', 0)

    def update_ride(self, dt):
        self.ride_t += dt
        t = self.ride_t
        self.audio.loop('creak', 0.7 if 0.6 < t < 6.0 else 0.0)
        self.audio.loop('sewer_amb', 0.5)
        if 6.0 < t and 'ride_end' not in self.flags:
            self.flags.add('ride_end')
            self.audio.play('clunk', 1.0)
        self.fade = clamp((t - 2.2) / 0.8, 0, 1) * clamp((4.6 - t) / 0.8, 0, 1)
        if t > 7.0:
            self.fade = 0.0
            self.set_resume(3, 'lower')
            self.begin_ch3('lower')

    def render_ride(self):
        t = self.ride_t
        if t < 3.6:
            lv = self.lv_up
            drop = max(0.0, t - 0.6) ** 1.6 * 0.9
        else:
            lv = self.lv_low
            drop = -max(0.0, 7.0 - t) ** 1.6 * 0.55
        cx, cz = lv.center(*lv.elevator)
        cage_y = lv.y0 - drop
        cam = (cx, cage_y + 1.6 + 0.02 * math.sin(t * 13), cz - 0.3)
        fwd = (0.0, -0.25, 1.0)
        n = math.sqrt(sum(v * v for v in fwd))
        fwd = tuple(v / n for v in fwd)
        lp = (cx + 0.3, cage_y + 1.2, cz + 0.2)
        self.draw_world3(lv, cam, fwd, [(lp, 6.0, self.lantern_col())], cage_y=cage_y, hold=(True, 0.0, -0.25))

    # ------------------------------------------------------------------ out, and back to the drain
    def start_exit3(self):
        self.state = 'exit3'
        self.ex_t = 0.0
        self.ex_fired = set()
        self.set_mouse(False)
        self.audio.loop('breath', 0)
        self.audio.loop('sewer_amb', 0)

    def update_exit3(self, dt):
        self.ex_t += dt
        t = self.ex_t
        A = self.audio
        A.loop('winter_amb', 0.9)
        for i in range(18):
            if ('s%d' % i) not in self.ex_fired and t > 0.6 + i * 0.38:
                self.ex_fired.add('s%d' % i)
                A.play_rand('step_snow', 4, 0.75)
        if 'bugle' not in self.ex_fired and t > 4.5:
            self.ex_fired.add('bugle')
            A.play('elk_bugle', 0.45, pan=-0.5)
        if 'msg' not in self.ex_fired and t > 1.0:
            self.ex_fired.add('msg')
            self.message("The storm drain. It was safe down there. It has to be.", 4)
        for m in self.msgs:
            m[1] -= dt
        self.msgs = [m for m in self.msgs if m[1] > 0]
        self.fade = max(clamp(1 - t / 0.8, 0, 1), clamp((t - 9.5) / 1.4, 0, 1))
        if t > 11.2:
            self.fade = 0.0
            self.progress['ch4'] = True
            self.progress.pop('resume', None)
            save_progress(self.progress)
            self.ending_pages = lore.CH3_ENDING
            self.start_ending()
            self.ending_next = self.start_ch4

    def render_exit3(self):
        t = self.ex_t
        k = clamp(t / 9.5, 0, 1)
        z = 14.0 + 36.0 * k
        x = 1.2 * math.sin(t * 0.7) * (1 - k)
        g = float(W.terrain_h(x, z)) + 0.35 if z < 47.6 else self.world.floor_at(0.0, z) or 0.0
        cam = (x, g + 1.5 + 0.07 * math.sin(t * 9.5), z)
        fwd = (0.0, -0.05, 1.0)
        rx = 0.25
        lp = (cam[0] + rx, cam[1] - 0.5, cam[2] + 0.5)
        env = dict(self.BLIZZARD_ENV)
        if z > 47:
            env = None
        self.draw_world(cam, fwd, 0.0, cam, fwd, [], extra_lights=[(lp, 9.0, self.lantern_col())], env=env,
                        extras=[(self.m_cover1, None)], blizzard=1.0 if z < 48 else 0.0)
        y = self.UH - 120
        for m in reversed(self.msgs):
            txt, tl, td = m
            al = int(clamp(tl / 0.8, 0, 1) * clamp((td - tl) / 0.3, 0, 1) * 255)
            self.blit_text(txt, self.f_msg, (225, 215, 200), (self.UW // 2, y), 'midtop', alpha=al)
            y -= 30
        bar = int(self.UH * 0.11)
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, 0, self.UW, bar))
        pygame.draw.rect(self.ui, (0, 0, 0, 255), (0, self.UH - bar, self.UW, bar))

    # ------------------------------------------------------------------ drawing the mine
    def draw_blizzard(self, cam, intensity):
        r = self.r
        t = self.time
        for layer in range(1 + int(intensity > 0.5) * 2):
            drift_x = t * (2.6 + 1.5 * layer) + layer * 13.7
            drift_z = t * 0.9 + layer * 7.1
            ox0 = drift_x + 30 * math.floor((cam[0] - 15 - drift_x) / 30)
            oz0 = drift_z + 30 * math.floor((cam[2] - 15 - drift_z) / 30)
            fall = (t * (2.2 + 0.4 * layer) + layer * 5.0) % 12
            oy0 = cam[1] - 6 - fall
            for ox in (ox0, ox0 + 30):
                for oz in (oz0, oz0 + 30):
                    for oy in (oy0, oy0 + 12):
                        r.draw(self.m_snow, model=T(ox, oy, oz))

    def draw_world3(self, lv, cam, fwd, lights, parts=(), extras=(), hold=None, blizzard=0.0, cage_y=None, fov=None,
                    env_override=None):
        r = self.r
        all_lights = self.mp_lights() + list(lights)
        parts = list(parts) + self.mp_parts(cam, fwd)
        cand = []
        for i, L_ in enumerate(lv.lights):
            if L_['powered'] and not self.power:
                continue
            x, y, z = L_['pos']
            d = math.hypot(x - cam[0], z - cam[2])
            if d < L_['rad'] + 22:
                k = 1.9 * (0.85 + 0.15 * math.sin(self.time * 13 + i)) if L_['powered'] else 1.9
                c = L_['col']
                cand.append((d, ((x, y, z), L_['rad'], (c[0] * k, c[1] * k, c[2] * k))))
        cand.sort(key=lambda o: o[0])
        all_lights += [c[1] for c in cand]
        outside_t = clamp((lv.oz + 6 - cam[2]) / 10.0, 0, 1) if lv.has_outside else 0.0
        cave = {'ambient': (0.014, 0.013, 0.013), 'mooncol': (0.0, 0.0, 0.0), 'moondir': (0.3, -0.8, 0.5),
                'fog': (0.0, 0.0, 0.0), 'fogdens': 0.045}
        bz = self.BLIZZARD_ENV
        env = {k: (tuple(cave[k][i] + (bz[k][i] - cave[k][i]) * outside_t for i in range(3))
                   if isinstance(cave[k], tuple) else cave[k] + (bz[k] - cave[k]) * outside_t) for k in cave}
        if env_override is not None:
            env = env_override
        r.begin(cam, fwd, fov or self.settings['fov'], env, self.time, 0.0, cam, fwd, all_lights[:8])
        r.draw(self.m_up if lv is self.lv_up else self.m_low)
        if self.power:
            for (x, y, z) in lv.bulbs:
                r.draw(self.m_bulb, model=T(x, y, z) @ S(0.07, 0.11, 0.07))
        for lev in lv.levers:
            r.draw(self.m_lever, model=T(*lev['pos']) @ RY(lev['yaw']) @ RX(lev['angle']))
        if lv.elevator:
            cx, cz = lv.center(*lv.elevator)
            r.draw(self.m_cage, model=T(cx, lv.y0 if cage_y is None else cage_y, cz))
        if lv is self.lv_low:
            # what is left of the Goat Man
            gx, gz = lv.center(*lv.goat_cell)
            dead = pose_goat(gx - 1.0, lv.y0 + 0.02, gz, 0.6, lie=1.0, jaw=1.1, head_yaw=0.9, arms=0.2, bloody=True, t=0.0)[0]
            for key, M in dead:
                r.draw(self.m_moose[key], model=M)
            for ox, oz, s in ((0.3, -0.3, 0.7), (0.9, 0.2, 0.55), (-0.2, 0.4, 0.5)):
                r.draw(self.m_moose['gore'], model=T(gx - 1.0 + ox, lv.y0 + 0.45, gz + oz - 1.5) @ S(s, 0.25, s * 0.8))
            for k in range(5):
                r.draw(self.m_moose['rib'], model=T(gx - 1.2 + k * 0.12, lv.y0 + 0.55, gz - 1.6) @ RX(1.2) @ S(0.03, 0.45, 0.03))
        for mesh, M in extras:
            r.draw(mesh, model=M)
        for pl in parts:
            for key, M in pl:
                r.draw(self.m_moose[key], model=M)
        if hold and hold[0]:
            _, yaw, pitch = hold
            lp = self.held_lantern_pos(cam, yaw, pitch)
            M = T(*lp) @ RY(yaw) @ RZ(0.05 * math.sin(self.time * 2.1))
            r.draw(self.m_lantern, model=M)
            r.draw(self.m_lantern_lit if (self.flash_on or self.state != 'play') else self.m_lantern_off, model=M)
        if blizzard > 0 or outside_t > 0:
            self.draw_blizzard(cam, max(blizzard, outside_t))

    def elk_parts(self):
        e = self.elk
        chasing = e.state in ('chase', 'search')
        return pose_elk(e.x, e.y, e.z, e.yaw, phase=e.phase, amt=e.amt, jaw=0.7 if chasing else 0.3,
                        split=0.8 if chasing else 0.3, head_pitch=0.15 if e.state == 'search' else 0.35, t=self.time)[0]

    def render_ch3_scene(self):
        p = self.player
        lv = self.lv
        cam = p.eye()
        fwd = p.fwd()
        lp = self.held_lantern_pos(cam, p.yaw, p.pitch)
        lit = self.flash_on and self.flicker_t <= 0
        lights = [((lp[0], lp[1] + 0.2, lp[2]), 10.0, self.lantern_col())] if lit else []
        parts = [self.elk_parts()] if self.elk is not None and not self.mp_hidden('elk') else []
        self.draw_world3(lv, cam, fwd, lights, parts=parts, hold=(True, p.yaw, p.pitch))

    def elk_face_parts(self, cam, yaw, dist):
        kw = dict(jaw=1.1, split=1.0, head_pitch=-0.2, head_roll=random.uniform(-0.2, 0.2), t=self.time)
        _, head = pose_elk(0.0, 0.0, 0.0, yaw + math.pi, **kw)
        hc = head @ np.array([0.0, 0.1, 0.35, 1.0])
        tx = cam[0] + math.sin(yaw) * dist
        tz = cam[2] + math.cos(yaw) * dist
        return pose_elk(tx - float(hc[0]), cam[1] - float(hc[1]), tz - float(hc[2]), yaw + math.pi, **kw)[0]

    def save_prog(self):
        save_progress(self.progress)

    def kill(self, from_net=False):
        if self.state != 'play' and not (self.mp_on() and self.state in PLAYISH):
            return
        if self.mp_on() and not from_net:
            p = self.player
            b = getattr(self, 'beast', None) or p
            self.mp_tell('died', v=self.mp.pid, k='beast', a='beast', x=round(p.x, 2), y=round(p.y, 2),
                         z=round(p.z, 2), mx=round(b.x, 2), my=0.0, mz=round(b.z, 2), myaw=0.0)
            self.mp_send_tick()
        if self.state != 'play':
            self.set_mouse(True)
        self.mp_ready = None
        self.block_input = False
        self.state = 'scare'
        self.scare_t = 0.0
        self.audio.stop_all()
        self.audio.stop_loops()
        self.audio.play('screech', 1.0)
        self.audio.play('stinger', 1.0)

    # ------------------------------------------------------------------ update
    def update(self, dt):
        self.mp_update(dt)
        st = self.state
        if self.mp_on() and st in ('pause', 'note', 'settings'):
            # nobody waits for you in co-op
            self.block_input = True
            self.update_play(dt)
            self.block_input = False
            if self.state == 'scare':
                self.set_mouse(False)
            return
        if st == 'chapters':
            self.locked_t = max(0.0, getattr(self, 'locked_t', 0.0) - dt)
        if st in ('title', 'chapters', 'coop', 'coopname', 'coopjoin', 'lobby'):
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
        elif st == 'climb':
            self.update_climb(dt)
        elif st == 'cutscene':
            self.update_cutscene(dt)
        elif st == 'daylater':
            self.update_daylater(dt)
        elif st == 'wake':
            self.update_wake(dt)
        elif st == 'ch2_end':
            self.update_ch2_end(dt)
        elif st == 'butcher':
            self.update_butcher(dt)
        elif st == 'windowcs':
            self.update_window_cs(dt)
        elif st == 'wake3':
            self.update_wake3(dt)
        elif st == 'ride':
            self.update_ride(dt)
        elif st == 'exit3':
            self.update_exit3(dt)
        elif st == 'ch4open':
            self.update_ch4open(dt)
        elif st == 'exit4':
            self.update_exit4(dt)
        elif st == 'card5':
            self.update_card5(dt)
        elif st == 'beastcs':
            self.update_beast_cs(dt)
        elif st == 'exit5':
            self.update_exit5(dt)
        elif st == 'scare':
            self.scare_t += dt
            if self.scare_t > 1.7 and self.mp_on():
                self.respawn()
            elif self.scare_t > 1.7:
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
        if self.chapter == 2:
            self.update_ch2(dt)
            return
        if self.chapter == 3:
            self.update_ch3(dt)
            return
        if self.chapter == 4:
            self.update_ch4(dt)
            return
        if self.chapter == 5:
            self.update_ch5(dt)
            return
        p = self.player
        w = self.world
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
        if self.escape:
            self.update_escape(dt)
            if self.state != 'play':
                return
        else:
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
        if self.mp_on() and w.ladder_pos and not self.escape:
            lx, _, lz = w.ladder_pos
            self.mp_gather('ladder', (w.drained or self.valves_done >= 5) and math.hypot(p.x - lx, p.z - lz) < 2.6)
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
                    self.mp_act('valve', i=i)
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
            self.set_resume(1, 'sewer')         # Chapter One checkpoint: down the drain, into the sewers
            self.message("Something has been living down here.", 4)
            self.set_objective("Find a way through the overflow system.")
        if room == 'gallery' and 'gallery' not in fl:
            fl.add('gallery')
            if self.mp_client():
                self.mp_tell('gallery', x=round(p.x, 2), z=round(p.z, 2))
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
        tgt, lit = self.mp_ai_target(m, 'moose')
        if self.mp_sim() and not self.mp_frozen('moose'):
            m.update(dt, tgt, lit)
        for ev in self.mp_events('moose', m):
            if ev == 'step':
                self.audio.play3d('mstep', m.x, m.z, 32, 1.0)
            elif ev == 'chase_start':
                self.audio.play3d('call_near', m.x, m.z, 50, 1.0)
                self.audio.play('stinger', 0.6)
            elif ev == 'kill':
                self.mp_caught(tgt, 'moose')
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

    def draw_world(self, cam, fwd, flash, flash_pos, flash_dir, moose_parts_list, fov=None, up=(0.0, 1.0, 0.0),
                   extra_lights=None, env=None, extras=(), blizzard=0.0):
        r = self.r
        lights = self.gather_lights(cam[0], cam[2])
        ml = self.mp_lights()
        if ml:
            lights = (ml + lights)[:8]
        moose_parts_list = list(moose_parts_list) + self.mp_parts(cam, fwd)
        if extra_lights:
            # headlights and the like always win a slot
            lights = (list(extra_lights) + lights)[:8]
        if env is None:
            env = self.env(cam[2])
        else:
            env = dict(env, moondir=self.world.moon_dir)
        r.begin(cam, fwd, fov or self.settings['fov'], env, self.time, flash, flash_pos, flash_dir, lights,
                up=up)
        for mesh, M in extras:
            r.draw(mesh, model=M)
        if blizzard > 0:
            self.draw_blizzard(cam, blizzard)
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
        if st in ('title', 'settings', 'update', 'chapters', 'coop', 'coopname', 'coopjoin', 'lobby') and \
                (st != 'settings' or self.settings_return == 'title'):
            self.render_title_scene()
            post = self.post_params({'fear': 0.15, 'glitch': self.title_glitch()})
            if st in ('coop', 'coopname', 'coopjoin', 'lobby'):
                self.draw_coop_ui()
            elif st == 'title':
                self.draw_title_ui()
                self.draw_coop_ui()
            elif st == 'chapters':
                self.draw_chapters_ui()
            elif st == 'update':
                self.draw_update_ui()
            else:
                self.draw_settings_ui()
        elif st == 'intro':
            self.r.fbo.use()
            self.r.fbo.clear(0, 0, 0, 1)
            self.draw_intro_ui()
            post = self.post_params({'fear': 0.0})
        elif st == 'climb':
            self.render_climb()
            post = self.post_params({'fear': 0.2})
            self.draw_osd()
        elif st == 'cutscene':
            self.render_cutscene()
            t = self.cs_t
            hit = 1.0 if (4.6 <= t < 5.0 or 17.8 <= t < 18.1) else 0.0
            post = self.post_params({'glitch': hit + (0.25 if 3.9 <= t < 4.6 else 0.0),
                                     'red': 0.35 * hit})
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
        elif st == 'daylater':
            self.r.fbo.use()
            self.r.fbo.clear(0, 0, 0, 1)
            self.draw_daylater_ui()
            post = self.post_params({'fear': 0.0, 'fade': 0.0})
        elif st == 'wake':
            self.render_wake()
            post = self.post_params({'fear': 0.1})
        elif st == 'ch2_end':
            self.render_ch2_scene()
            self.draw_hud(minimal=True)
            post = self.post_params()
        elif st == 'butcher':
            self.render_butcher()
            post = self.post_params({'fear': 0.15})
        elif st == 'wake3':
            self.render_wake3()
            post = self.post_params({'fear': 0.25 if self.w3_t > 23 else 0.05})
        elif st == 'ride':
            self.render_ride()
            post = self.post_params({'fear': 0.1})
        elif st == 'exit3':
            self.render_exit3()
            post = self.post_params({'fear': 0.2})
        elif st == 'ch4open':
            self.render_ch4open()
            post = self.ch4open_post()
        elif st == 'exit4':
            self.render_exit4()
            post = self.post_params({'fear': 0.3})
        elif st == 'card5':
            self.r.fbo.use()
            self.r.fbo.clear(0, 0, 0, 1)
            self.draw_card5()
            post = self.post_params({'fear': 0.0, 'fade': 0.0})
        elif st == 'beastcs':
            self.render_beast_cs()
            post = self.beast_cs_post()
        elif st == 'exit5':
            self.render_exit5()
            post = self.post_params({'fear': 0.0, 'red': 0.0})
        elif st == 'windowcs':
            self.render_window_cs()
            t = self.win_t
            post = self.post_params({'glitch': 0.8 if 11.4 <= t < 11.7 or 14.4 <= t < 14.6 else 0.0})
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
        if self.chapter == 2:
            self.render_ch2_scene()
            return
        if self.chapter == 3:
            self.render_ch3_scene()
            return
        if self.chapter == 4:
            self.render_ch4_scene()
            return
        if self.chapter == 5:
            self.render_ch5_scene()
            return
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
        if m.active and not self.mp_hidden('moose'):
            parts.append(m.parts())
        if self.app:
            a = self.app
            walk = 1.0 if a.get('leave', 0) > 0.6 else 0.0
            parts.append(pose_moose(a['x'], a['y'], a['z'], a['yaw'], a['phase'], walk,
                                    roll=0.6 if (self.time % 2.7) > 2.2 else 0.0)[0])
        if self.phantom > 0:
            parts.append(self.face_parts(cam, fwd, p.yaw, 0.9))
        extra = None
        if self.escape:
            cp = None if self.mp_hidden('chaser') else self.chaser_parts()
            if cp:
                parts.append(cp)
            for c in self.cars:
                if c['delay'] <= 0:
                    parts.append(car_parts(c['x'], c['z'], c['dir']))
            extra = self.car_lights()
        self.draw_world(cam, fwd, flash, fpos, self.flash_dir, parts, extra_lights=extra)

    def face_parts(self, cam, fwd, yaw, dist):
        # skull lifted to stare straight at you, jaw hanging open, head twitching
        roll = random.uniform(-0.3, 0.3)
        jaw = 0.75 + random.uniform(0, 0.25)
        pitch = -0.25 + random.uniform(-0.05, 0.05)
        kw = dict(hunch=0.45, roll=roll, jaw=jaw, reach=1.0, head_pitch=pitch, t=self.time)
        _, head = pose_moose(0, 0, 0, yaw + math.pi, 0.0, 0.0, **kw)
        hx, hy, hz = float(head[0, 3]), float(head[1, 3]), float(head[2, 3])
        tx = cam[0] + math.sin(yaw) * dist
        tz = cam[2] + math.cos(yaw) * dist
        ty = cam[1] + 0.1
        return pose_moose(tx - hx, ty - hy, tz - hz, yaw + math.pi, 0.0, 0.0, **kw)[0]

    def render_scare(self):
        p = self.player
        cam = p.eye()
        k = self.scare_t
        sh = 0.04 if k < 1.2 else 0.0
        cam = (cam[0] + random.uniform(-sh, sh), cam[1] + random.uniform(-sh, sh), cam[2])
        yaw = p.yaw + random.uniform(-0.03, 0.03)
        fwd = (math.sin(yaw), 0.0, math.cos(yaw))
        if self.chapter == 4:
            self.render_scare_ch4(cam, yaw, fwd, k)
            return
        if self.chapter == 5:
            self.render_scare_ch5(cam, yaw, fwd, k)
            return
        if self.chapter == 3:
            # the Elk's split face, inches away
            parts = [self.elk_face_parts(cam, yaw, 2.2 - min(k, 1.0) * 0.6)]
            lp = (cam[0] + math.sin(yaw) * 0.4, cam[1] - 0.35, cam[2] + math.cos(yaw) * 0.4)
            self.draw_world3(self.lv, cam, fwd, [(lp, 6.0, (1.5, 0.9, 0.45))], parts=parts)
            return
        if self.chapter == 2 and self.ch2_phase == 'run':
            parts = [self.face_parts(cam, fwd, yaw, 1.75 - min(k, 1.0) * 0.45)]
            lp = (cam[0] + math.sin(yaw) * 0.4, cam[1] - 0.35, cam[2] + math.cos(yaw) * 0.4)
            self.draw_world2(cam, fwd, [(lp, 6.0, (1.5, 0.9, 0.45))], parts=parts)
            return
        if self.chapter == 2:
            # the Goat Man fills the screen, lit by your lantern
            parts = [self.goat_face_parts(cam, yaw, 2.0 - min(k, 1.0) * 0.55)]
            lp = (cam[0] + math.sin(yaw) * 0.4, cam[1] - 0.35, cam[2] + math.cos(yaw) * 0.4)
            self.draw_world2(cam, fwd, [(lp, 6.0, (1.5, 0.9, 0.45))], parts=parts)
            return
        parts = [self.face_parts(cam, fwd, yaw, 1.75 - min(k, 1.0) * 0.45)]
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
        y0 = int(self.UH * 0.56)
        # where Continue will take you
        sel = self.menu_sel == 0
        cw = self.f_menu.size("> CONTINUE")[0]
        self.blit_text(self.RESUME_NAMES[self.resume_point()], self.f_small, (150, 140, 130) if sel else (110, 104, 98),
                       (80 + cw + 14, y0 + 13))
        self.blit_text("headphones recommended. play in the dark.", self.f_small, (110, 105, 100), (cx, self.UH - 30), 'midtop')
        self.blit_text("v" + VERSION, self.f_small, (110, 105, 100), (cx, 204), 'midtop')
        if self.new_build and self.update_state == 'working':
            self.draw_update_bar(330, y0 + 46 + 12)
        elif self.update_state == 'failed':
            self.blit_text("update failed -- try again, or download it from github.com/%s/releases" % updater.repo_path(),
                           self.f_small, (200, 90, 80), (330, y0 + 46 + 12))
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
        date = ("OCT.31 2003", "NOV. 1 2003", "NOV. 2 2003", "NOV. 3 2003")[min(day, 3)]
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
        self.draw_coop_hud()
        if minimal:
            return
        p = self.player
        cx, cy = self.UW // 2, self.UH // 2
        pygame.draw.circle(self.ui, (220, 220, 220, 120), (cx, cy), 2)
        if self.focus:
            kind, key = self.focus
            if kind == 'note':
                label = "[E] Read"
            elif kind == 'wood':
                label = "[E] Pick up firewood"
            elif kind == 'door':
                label = "[E] Close the door" if self.w2.door_open else "[E] Open the door"
            elif kind == 'rifle':
                label = "[E] Take the rifle"
            elif kind == 'deer':
                label = "[E] Butcher the deer"
            elif kind == 'lever':
                lev = self.lv.levers[key]
                label = "[Hold E] Pull the lever"
                if lev['progress'] > 0:
                    w = 160
                    pygame.draw.rect(self.ui, (0, 0, 0, 160), (cx - w // 2, cy + 52, w, 10))
                    pygame.draw.rect(self.ui, (190, 40, 30, 230), (cx - w // 2 + 1, cy + 53, int((w - 2) * min(1, lev['progress'])), 8))
            elif kind == 'elevator':
                label = "[E] Take the elevator down" if self.power else "The elevator (no power)"
            elif kind == 'shotgun':
                label = "[E] Take the shotgun"
            elif kind in ('generator', 'fuse', 'fusebox'):
                label, prog_ = self.focus_label_ch4(kind, key)
                if prog_ > 0:
                    w = 160
                    pygame.draw.rect(self.ui, (0, 0, 0, 160), (cx - w // 2, cy + 52, w, 10))
                    pygame.draw.rect(self.ui, (190, 40, 30, 230), (cx - w // 2 + 1, cy + 53, int((w - 2) * min(1, prog_)), 8))
            elif kind == 'woodpile':
                label = ("[E] Stack your firewood (%d)" % self.carried) if self.carried else "The woodpile"
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
        if self.chapter == 2:
            if self.has_rifle and self.aim > 0.55:
                # looking down the scope: everything but the circle goes black
                sc = pygame.Surface((self.UW, self.UH), pygame.SRCALPHA)
                sc.fill((0, 0, 0, int(255 * min(1.0, (self.aim - 0.55) / 0.3))))
                rad = int(self.UH * 0.42)
                pygame.draw.circle(sc, (0, 0, 0, 0), (cx, cy), rad)
                pygame.draw.line(sc, (10, 10, 10, 230), (cx - rad, cy), (cx + rad, cy), 1)
                pygame.draw.line(sc, (10, 10, 10, 230), (cx, cy - rad), (cx, cy + rad), 1)
                pygame.draw.line(sc, (10, 10, 10, 255), (cx - rad, cy), (cx - 30, cy), 3)
                pygame.draw.line(sc, (10, 10, 10, 255), (cx + 30, cy), (cx + rad, cy), 3)
                pygame.draw.line(sc, (10, 10, 10, 255), (cx, cy + 30), (cx, cy + rad), 3)
                self.ui.blit(sc, (0, 0))
            # what you are doing, always on screen in Chapter 2
            if self.ch2_phase == 'wood':
                status = "FIREWOOD  stacked %d/%d   carrying %d" % (self.stacked, C2.WOOD_NEEDED, self.carried)
            elif self.ch2_phase == 'rifle':
                status = "FIREWOOD  stacked %d/%d   -   get the rifle" % (self.stacked, C2.WOOD_NEEDED)
            elif self.ch2_phase == 'hunt':
                status = "RIFLE   [right mouse] aim   [left mouse] fire"
            else:
                status = "GET BACK TO THE CABIN"
            self.blit_text(status, self.f_small, (215, 205, 190), (26, 56))
            if self.obj_t > 0:
                a = int(clamp(self.obj_t / 1.0, 0, 1) * 255)
                self.blit_text(self.objective, self.f_small, (160, 152, 142), (26, 76), alpha=a)
        elif self.chapter == 5:
            self.draw_hud_ch5()
        elif self.chapter == 4:
            self.blit_text(self.hud_ch4(), self.f_small, (215, 205, 190), (26, 56))
            if self.obj_t > 0:
                a = int(clamp(self.obj_t / 1.0, 0, 1) * 255)
                self.blit_text(self.objective, self.f_small, (160, 152, 142), (26, 76), alpha=a)
        elif self.chapter == 3:
            if self.lv is self.lv_up:
                n = sum(1 for x in self.lv.levers if x['pulled'])
                status = ("LEVERS %d/3" % n) if n < 3 else "THE ELEVATOR HAS POWER"
            else:
                status = "FIND A WAY OUT"
            self.blit_text(status, self.f_small, (215, 205, 190), (26, 56))
            if self.obj_t > 0:
                a = int(clamp(self.obj_t / 1.0, 0, 1) * 255)
                self.blit_text(self.objective, self.f_small, (160, 152, 142), (26, 76), alpha=a)
        elif self.obj_t > 0:
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
        if self.chapter == 5:
            title, sub = "THE BEAST", "it is all of them now."
        elif self.chapter == 4:
            title, sub = "HE'S STRONGER NOW", "and he remembers you."
        elif self.chapter == 3:
            title, sub = "IT TOOK ITS TIME", "it was never in a hurry."
        elif self.chapter == 2 and self.ch2_phase == 'run':
            title, sub = "HE CAME BACK FOR YOU", "the cabin was right there."
        elif self.chapter == 2:
            title, sub = "HE WAS STILL HUNGRY", "whatever you were carrying is gone."
        else:
            title, sub = "YOU STOPPED MOVING", "the herd has room for one more."
        self.blit_text(title, self.f_big, (170, 15, 10), (cx + j, self.UH // 2 - 80), 'midtop', alpha=a)
        self.blit_text(sub, self.f_msg, (170, 160, 150), (cx, self.UH // 2), 'midtop', alpha=a)
        if t > 1.5:
            self.blit_text("ENTER - wake up          ESC - title", self.f_hud, (200, 190, 180), (cx, self.UH // 2 + 70), 'midtop')

    def draw_ending_ui(self):
        lines = self.ending_pages[self.ending_page]
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
