"""Co-op: up to four players through the story together.

One player hosts. The host's game runs the monsters and decides who they go
after and who they catch; everyone else draws what the host sends. Puzzles
(valves, levers, firewood, generators, fuses...) are shared: whoever does one
does it for everybody. Doors to the next area (the ladder, the elevator, the
gates...) only open once everyone is standing at them.

If a monster catches you, you get the jumpscare and wake up at the
checkpoint, and everyone else watches it happen.
"""
import math
import random
import time

import pygame

import net as NET
from avatar import pose_player, avatar_meshes, COATS
from engine import Mesh
from moose import Moose, pose_moose, pose_goat
from elk import pose_elk
import chapter2 as C2
import chapter3 as C3
import chapter4 as C4
import chapter5 as C5

PLAYISH = ('play', 'pause', 'note', 'settings')
KILL_T = 2.4

# monsters each chapter syncs (attribute names on the Game), and what kind of thing they are
MONSTERS = {1: [('moose', 'moose'), ('chaser', 'moose')],
            2: [('goat', 'goat'), ('deer', None), ('chaser2', 'moose')],
            3: [('elk', 'elk')],
            4: [('moose4', 'moose4')],
            5: [('beast', 'beast'), ('herd5', None), ('herdb', None)]}

GATHER_NAMES = {'ladder': "the ladder", 'road': "the road", 'cabin': "the cabin", 'elevator': "the elevator",
                'exit3': "the way out", 'exit4': "the second gate", 'factory': "the end of the drain",
                'exit5': "the gate", 'cart': "the minecart"}

CHAPTER_NAMES = ["1  -  THE WOODS", "2  -  THE CABIN", "3  -  THE CAVE", "4  -  THE DEEP SEWER", "5  -  THE BEAST"]


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def _simple(v):
    if v is None or isinstance(v, (bool, int, str)):
        return True
    if isinstance(v, float):
        return math.isfinite(v)
    if isinstance(v, (tuple, list)) and len(v) <= 16:
        return all(isinstance(e, (int, float)) and not isinstance(e, bool) and math.isfinite(e) for e in v)
    return False


def _r(v):
    if isinstance(v, float):
        return round(v, 3)
    if isinstance(v, (tuple, list)):
        return [round(e, 3) if isinstance(e, float) else e for e in v]
    return v


SKIP_KEYS = {'events', 'path', 'cells', 'did'}


def pack(obj):
    src = obj if isinstance(obj, dict) else obj.__dict__
    return {k: _r(v) for k, v in src.items() if k not in SKIP_KEYS and _simple(v)}


def unpack_into(obj, data, skip=()):
    for k, v in data.items():
        if k in skip:
            continue
        if isinstance(v, list):
            v = tuple(v)
        if isinstance(obj, dict):
            obj[k] = v
        else:
            setattr(obj, k, v)


class Peer:
    """Another player, as this machine knows them."""

    def __init__(self, pid, name, slot):
        self.pid, self.name, self.slot = pid, name, slot
        self.last = time.time()
        self.s = {}
        self.x = self.y = self.z = 0.0
        self.yaw = self.pitch = 0.0
        self.vx = self.vz = 0.0
        self.fx, self.fz = 0.0, 1.0
        self.crouch = 0.0
        self.sprinting = False
        self.rx = self.ry = self.rz = None     # smoothed, for drawing
        self.ryaw = 0.0
        self.phase = 0.0
        self.amt = 0.0

    def take(self, s):
        self.s = s
        self.x, self.y, self.z = s.get('x', 0.0), s.get('y', 0.0), s.get('z', 0.0)
        self.yaw, self.pitch = s.get('yaw', 0.0), s.get('pitch', 0.0)
        self.vx, self.vz = s.get('vx', 0.0), s.get('vz', 0.0)
        self.fx, self.fz = math.sin(self.yaw), math.cos(self.yaw)
        self.crouch = s.get('cr', 0.0)
        self.sprinting = bool(s.get('spr'))
        self.last = time.time()

    @property
    def alive(self):
        return self.s.get('st') in PLAYISH

    @property
    def area(self):
        return self.s.get('area')

    def smooth(self, dt):
        if self.rx is None or math.hypot(self.x - self.rx, self.z - self.rz) > 6:
            self.rx, self.ry, self.rz, self.ryaw = self.x, self.y, self.z, self.yaw
            return
        k = min(1.0, dt * 10)
        tx, tz = self.x + self.vx * 0.06, self.z + self.vz * 0.06
        ox, oz = self.rx, self.rz
        self.rx += (tx - self.rx) * k
        self.rz += (tz - self.rz) * k
        self.ry += (self.y - self.ry) * k
        d = (self.yaw - self.ryaw + math.pi) % (2 * math.pi) - math.pi
        self.ryaw += d * k
        moved = math.hypot(self.rx - ox, self.rz - oz)
        self.phase += moved * 2.6
        sp = moved / max(dt, 1e-4)
        self.amt += (min(1.0, sp / 2.7) - self.amt) * min(1.0, dt * 8)


class MP:
    def __init__(self, host, code, name):
        self.host = host
        self.code = code
        self.name = name
        self.pid = NET.new_pid()
        self.net = NET.Net(code, self.pid)
        self.peers = {}
        self.slot = 0
        self.joined = host           # a client is in once the host lists it
        self.started = False
        self.chapter = 1             # the host's pick in the lobby
        self.host_pid = self.pid if host else None
        self.t_send = 0.0
        self.t_hello = 0.0
        self.t_lobby = 0.0
        self.since = time.time()
        self.out_ev = []             # acts to send with the next tick
        self.mev_out = {}            # monster events (host)
        self.error = ''


class CoopMixin:
    # ================================================================== setup
    def init_coop(self, prog):
        for k, v in avatar_meshes().items():
            self.m_moose[k] = Mesh(self.ctx, prog, v)
        self.mp = None
        self.mp_kills = []
        self.mp_ready = None
        self.mp_wait_t = 0.0
        self.mev_in = {}
        self.mon_tgt = {}
        self.mon_freeze = {}
        self.mon_lock = {}
        self.mon_tgt_pid = {}
        self.block_input = False
        self.coop_msg = ''
        self.coop_msg_t = 0.0
        self.text_buf = ''
        self.applying_remote = False
        self._cam = None
        if not self.settings.get('coop_name'):
            self.settings['coop_name'] = 'Player%d' % random.randint(100, 999)

    # ================================================================== small helpers used all over
    def mp_on(self):
        return self.mp is not None and self.mp.started

    def mp_sim(self):
        """True on the machine that runs the monsters: always in single player, the host in co-op."""
        return self.mp is None or not self.mp.started or self.mp.host

    def mp_client(self):
        return self.mp_on() and not self.mp.host

    def keys(self):
        if self.block_input or getattr(self, 'inv_open', False):
            return _NoKeys()
        if self.fly_keys_blocked():
            return _NoMoveKeys(self._raw_keys())
        if getattr(self, 'web_keys', None) is not None:
            return self.web_keys
        return pygame.key.get_pressed()

    def mouse_buttons(self):
        if self.block_input:
            return (False, False, False)
        if getattr(self, 'web_keys', None) is not None:
            return self.web_buttons
        return pygame.mouse.get_pressed()

    def mp_count(self):
        return 1 + (len(self.mp.peers) if self.mp else 0)

    def mp_area(self):
        ch = self.chapter
        if ch == 1:
            return '1e' if self.escape else '1'
        if ch == 3:
            return '3l' if self.lv is self.lv_low else '3u'
        return str(ch)

    def local_alive(self):
        return self.state in PLAYISH

    # ================================================================== menus
    def coop_open(self):
        self.state = 'coop'
        self.menu_sel = 0
        if not NET.configured():
            self.coop_note("Co-op isn't set up in this build yet.")

    def coop_note(self, text, t=5.0):
        self.coop_msg = text
        self.coop_msg_t = t

    def coop_items(self):
        return ['HOST GAME', 'JOIN GAME', 'NAME:  ' + self.settings['coop_name'], 'BACK']

    def coop_action(self, i):
        self.audio.play('click', 0.5)
        if i == 0:
            if not NET.configured():
                self.coop_note("Co-op isn't set up in this build yet.")
                return
            self.mp_begin(True, NET.new_code())
        elif i == 1:
            if not NET.configured():
                self.coop_note("Co-op isn't set up in this build yet.")
                return
            self.state = 'coopjoin'
            self.text_buf = ''
        elif i == 2:
            self.state = 'coopname'
            self.text_buf = self.settings['coop_name']
        else:
            self.state = 'title'
            self.menu_sel = 3

    def text_event(self, ev, limit, allowed, done, cancel):
        if ev.type != pygame.KEYDOWN:
            return
        if ev.key == pygame.K_ESCAPE:
            cancel()
        elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            done(self.text_buf)
        elif ev.key == pygame.K_BACKSPACE:
            self.text_buf = self.text_buf[:-1]
        elif ev.unicode and len(self.text_buf) < limit and allowed(ev.unicode):
            self.text_buf += ev.unicode

    def coop_event(self, ev):
        st = self.state
        if st == 'coop':
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.state = 'title'
                self.menu_sel = 3
                return
            self.menu_event(ev, self.coop_items(), self.coop_action)
        elif st == 'coopname':
            def done(t):
                t = t.strip()
                if t:
                    self.settings['coop_name'] = t
                self.state = 'coop'
                self.menu_sel = 2
            self.text_event(ev, 14, lambda c: c.isprintable(), done, lambda: done(''))
        elif st == 'coopjoin':
            def done(t):
                t = t.strip().upper()
                if len(t) == 5:
                    self.mp_begin(False, t)
                else:
                    self.coop_note("Room codes are 5 letters.")
            def cancel():
                self.state = 'coop'
                self.menu_sel = 1
            self.text_event(ev, 5, lambda c: c.isalpha(), done, cancel)
            self.text_buf = self.text_buf.upper()
        elif st == 'lobby':
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.mp_leave("")
                return
            m = self.mp
            items = self.lobby_items()
            if m.host and ev.type == pygame.KEYDOWN and self.menu_sel == 0 and ev.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d):
                self.lobby_cycle(1 if ev.key in (pygame.K_RIGHT, pygame.K_d) else -1)
                return
            self.menu_event(ev, items, self.lobby_action)

    def lobby_unlocked(self):
        pr = self.progress
        return [1] + [n for n in (2, 3, 4, 5) if pr.get('ch%d' % n)]

    def lobby_cycle(self, d):
        ok = self.lobby_unlocked()
        i = ok.index(self.mp.chapter) if self.mp.chapter in ok else 0
        self.mp.chapter = ok[(i + d) % len(ok)]
        self.audio.play('click', 0.4)

    def lobby_items(self):
        m = self.mp
        if m.host:
            return ['CHAPTER  < %s >' % CHAPTER_NAMES[m.chapter - 1], 'START', 'LEAVE']
        return ['LEAVE']

    def lobby_action(self, i):
        m = self.mp
        self.audio.play('click', 0.5)
        if m.host and i == 0:
            self.lobby_cycle(1)
        elif m.host and i == 1:
            if not m.net.ok:
                return
            m.seed = random.randrange(1, 1 << 30)            # everyone gets the same puzzle layout
            m.net.send('start', {'ch': m.chapter, 'players': self.lobby_list(), 'seed': m.seed})
            self.mp_start(m.chapter)
        else:
            self.mp_leave("")

    def lobby_list(self):
        m = self.mp
        out = [[m.pid, m.name, m.slot]] if m.host else []
        for p in m.peers.values():
            out.append([p.pid, p.name, p.slot])
        return out

    # ================================================================== connecting
    def mp_begin(self, host, code):
        if self.mp:
            self.mp.net.close()
        self.mp = MP(host, code, self.settings['coop_name'])
        self.state = 'lobby'
        self.menu_sel = 0
        self.coop_msg = ''

    def mp_leave(self, why):
        m = self.mp
        if m is not None:
            try:
                m.net.send('bye', {})
            except Exception:
                pass
            m.net.close()
        self.mp = None
        self.mp_kills = []
        self.mp_ready = None
        self.block_input = False
        self.to_title()
        self.state = 'title'
        if why:
            self.coop_note(why, 6.0)

    def mp_start(self, chapter):
        """Everybody starts the chosen chapter at the same moment."""
        m = self.mp
        m.started = True
        self.mp_kills = []
        self.mp_ready = None
        self.mev_in = {}
        self.mon_tgt = {}
        self.mon_freeze = {}
        self.mon_lock = {}
        self.player.pid = m.pid
        self.new_game()
        if chapter == 1:
            self.start_chapter1()
        elif chapter == 2:
            self.start_daylater()
        elif chapter == 3:
            self.start_ch3()
        elif chapter == 4:
            self.start_ch4()
        else:
            self.start_ch5()

    # ================================================================== the per-frame network step
    def mp_update(self, dt):
        if self.coop_msg_t > 0:
            self.coop_msg_t -= dt
        m = self.mp
        if m is None:
            return
        now = time.time()
        if m.net.dead:
            self.mp_leave(("Lost the connection: %s." % (m.net.error or 'it dropped')) if m.started
                          else "Couldn't reach the co-op server.")
            return
        for kind, data, frm in m.net.poll():
            try:
                self.mp_recv(kind, data or {}, frm)
            except Exception:
                pass
            if self.mp is None:
                return
        # who has gone quiet
        for pid in list(m.peers):
            if now - m.peers[pid].last > 20.0:
                gone = m.peers.pop(pid)
                if pid == m.host_pid and not m.host:
                    self.mp_leave("The host left the game.")
                    return
                self.message("%s left." % gone.name, 4)
        if not m.joined:
            if not m.net.ok:
                if now - m.since > 12:
                    self.mp_leave("Couldn't reach the co-op server.")
                return
            m.t_hello -= dt
            if m.t_hello <= 0:
                m.t_hello = 1.0
                m.net.send('hello', {'name': m.name})
            if now - m.since > 10:
                self.mp_leave("No game found with code %s." % m.code)
            return
        if not m.started:
            m.t_lobby -= dt
            if m.t_lobby <= 0:
                m.t_lobby = 1.5
                if m.host:
                    m.net.send('lobby', {'players': self.lobby_list(), 'ch': m.chapter})
                else:
                    m.net.send('ping', {})
            return
        for p in m.peers.values():
            p.smooth(dt)
        self.update_kill_anims(dt)
        for k in list(self.mon_freeze):
            self.mon_freeze[k] -= dt
            if self.mon_freeze[k] <= 0:
                del self.mon_freeze[k]
                self.mp_after_kill(k)
        rate = clamp(24.0 / max(1, self.mp_count()), 5.0, 12.0)
        m.t_send -= dt
        urgent = any(e[0] in ('kill', 'go', 'died', 'page') for e in m.out_ev)
        if m.t_send <= 0 or urgent:
            m.t_send = 1.0 / rate
            self.mp_send_tick()
        if not self.mp_sim():
            self.mp_smooth_monsters(dt)

    def mp_send_tick(self):
        m = self.mp
        p = self.player
        s = {'st': self.state, 'c': self.chapter, 'area': self.mp_area(),
             'x': round(p.x, 3), 'y': round(p.y, 3), 'z': round(p.z, 3), 'yaw': round(p.yaw, 3),
             'pitch': round(p.pitch, 3), 'vx': round(p.vx, 2), 'vz': round(p.vz, 2), 'cr': round(p.crouch, 2),
             'spr': bool(p.sprinting), 'fl': bool(self.flash_on and self.flicker_t <= 0), 'it': self.mp_item(),
             'at': self.mp_ready or ''}
        d = {'s': s}
        if m.out_ev:
            d['ev'] = m.out_ev
            m.out_ev = []
        if m.host and self.state in PLAYISH + ('scare',):
            mons = {}
            for attr, _ in MONSTERS.get(self.chapter, []):
                obj = getattr(self, attr, None)
                mons[attr] = None if obj is None else pack(obj)
            d['mon'] = mons
            d['mt'] = {attr: self.mon_lock.get(attr) for attr, _ in MONSTERS.get(self.chapter, [])}
            d['mc'] = self.chapter
            d['ma'] = self.mp_area()
            if m.mev_out:
                d['mev'] = m.mev_out
                m.mev_out = {}
        m.net.send('t', d)

    def mp_item(self):
        g = self.held_gun()
        if g in ('rifle', 'shotgun'):
            return g
        return 'lantern' if self.lantern_hand() else 'none'

    def mp_recv(self, kind, d, frm):
        m = self.mp
        if kind == 'hello' and m.host:
            if m.started or len(m.peers) >= NET.MAX_PLAYERS - 1:
                if frm not in m.peers:
                    m.net.send('full', {'started': m.started}, to=frm)
                return
            if frm not in m.peers:
                used = {m.slot} | {p.slot for p in m.peers.values()}
                slot = min(set(range(NET.MAX_PLAYERS)) - used)
                m.peers[frm] = Peer(frm, str(d.get('name', '?'))[:14], slot)
                self.audio.play('click', 0.6)
            m.peers[frm].last = time.time()
            m.net.send('lobby', {'players': self.lobby_list(), 'ch': m.chapter})
            return
        if kind == 'full' and not m.joined:
            self.mp_leave("That game has already started." if d.get('started') else "That game is full.")
            return
        if kind == 'lobby' and not m.host:
            if m.host_pid is None:
                m.host_pid = frm
            if frm != m.host_pid:
                return
            self.mp_set_roster(d.get('players', []))
            m.chapter = d.get('ch', 1)
            return
        if kind == 'start' and not m.host and frm == m.host_pid:
            self.mp_set_roster(d.get('players', []))
            m.seed = d.get('seed')
            if m.joined:
                self.mp_start(d.get('ch', 1))
            return
        if kind == 'bye':
            if frm == m.host_pid and not m.host:
                self.mp_leave("The host left the game.")
                return
            gone = m.peers.pop(frm, None)
            if gone:
                self.message("%s left." % gone.name, 4)
            return
        if kind == 'ping':
            if frm in m.peers:
                m.peers[frm].last = time.time()
            return
        if kind == 'lobbyback' and frm == m.host_pid:
            self.mp_to_lobby()
            return
        if kind != 't':
            return
        peer = m.peers.get(frm)
        if peer is None:
            return
        if 's' in d:
            peer.take(d['s'])
        for name, args in d.get('ev', []):
            self.mp_apply(name, args, frm)
        if 'mon' in d and frm == m.host_pid and not m.host:
            if d.get('mc') == self.chapter and d.get('ma') == self.mp_area() and self.state in PLAYISH + ('scare',):
                self.mp_take_monsters(d['mon'])
                self.mon_tgt_pid = d.get('mt', {})
            for k, evs in d.get('mev', {}).items():
                self.mev_in.setdefault(k, []).extend(evs)

    def mp_set_roster(self, players):
        m = self.mp
        seen = set()
        for pid, name, slot in players:
            seen.add(pid)
            if pid == m.pid:
                m.slot = slot
                m.joined = True
                continue
            if pid not in m.peers:
                m.peers[pid] = Peer(pid, name, slot)
            m.peers[pid].name, m.peers[pid].slot = name, slot
            m.peers[pid].last = time.time()
        for pid in list(m.peers):
            if pid not in seen:
                m.peers.pop(pid)

    def mp_to_lobby(self):
        m = self.mp
        if m is None:
            return
        if m.host:
            m.net.send('lobbyback', {})
        m.started = False
        self.mp_kills = []
        self.audio.stop_all()
        self.audio.stop_loops()
        self.new_game()
        self.state = 'lobby'
        self.menu_sel = 0
        self.set_mouse(False)

    # ================================================================== shared actions
    def mp_act(self, _act, **args):
        """Do something to the shared world: here, and on everyone else's machine."""
        self.mp_apply(_act, args, None)
        if self.mp_on():
            self.mp.out_ev.append([_act, args])

    def mp_tell(self, _act, **args):
        """Send without doing it here (when it has already been done locally)."""
        if self.mp_on():
            self.mp.out_ev.append([_act, args])

    def mp_apply(self, name, a, frm):
        fn = getattr(self, 'act_' + name, None)
        if fn is None:
            return
        self.applying_remote = frm is not None
        try:
            fn(a, frm)
        finally:
            self.applying_remote = False

    # ---- monsters: what a client is told, and the noises it makes
    def act_hear(self, a, frm):
        if not self.mp_sim() or frm is None:
            return
        obj = getattr(self, a.get('m', ''), None)
        if obj is not None and not isinstance(obj, dict) and hasattr(obj, 'hear'):
            obj.hear(a['x'], a['z'], a['r'])

    def remote_hear(self, attr):
        def hear(x, z, radius):
            if self.applying_remote or not self.mp_on():
                return
            self.mp.out_ev.append(['hear', {'m': attr, 'x': round(x, 2), 'z': round(z, 2), 'r': round(radius, 1)}])
        return hear

    def mp_take_monsters(self, mons):
        for attr, data in mons.items():
            obj = getattr(self, attr, None)
            if data is None:
                if obj is not None:
                    setattr(self, attr, None)
                continue
            if obj is None:
                obj = self.mp_make_monster(attr)
                if obj is None:
                    continue
                setattr(self, attr, obj)
                fresh = True
            else:
                fresh = False
            pos_keys = ('x', 'y', 'z', 'yaw')
            if fresh or attr not in self.mon_tgt:
                unpack_into(obj, data)
            else:
                unpack_into(obj, data, skip=pos_keys)
            self.mon_tgt[attr] = tuple(data.get(k) for k in pos_keys)
            if not isinstance(obj, dict) and hasattr(obj, 'hear'):
                obj.hear = self.remote_hear(attr)
            if attr == 'elk' and self.lv is not None:
                obj.lv = self.lv

    def mp_make_monster(self, attr):
        if attr in ('chaser', 'chaser2'):
            return {}
        if attr == 'moose':
            return Moose(self.world)
        if attr == 'goat':
            return C2.GoatHunter(self.w2)
        if attr == 'deer':
            return C2.Deer(self.w2, random.Random())
        if attr == 'elk':
            return C3.ElkHunter(self.lv or self.lv_up, 0.0, 0.0)
        if attr == 'moose4':
            return C4.MooseHunter(self.lv4, 0.0, 0.0)
        if attr == 'beast':
            return C5.Beast(0.0, 0.0, 0.0)
        if attr == 'herd5':
            import herd5
            return herd5.Herd5(self.w5.fac, n=8)
        if attr == 'herdb':
            import herd5
            return herd5.Herd5(self.w5.fac, n=0, world=self.w5)
        return None

    def mp_smooth_monsters(self, dt):
        k = min(1.0, dt * 12)
        for attr, tgt in self.mon_tgt.items():
            obj = getattr(self, attr, None)
            if obj is None or tgt[0] is None:
                continue
            get = obj.get if isinstance(obj, dict) else (lambda n, o=obj: getattr(o, n, None))

            def put(n, v, o=obj):
                if isinstance(o, dict):
                    o[n] = v
                else:
                    setattr(o, n, v)
            x, z = get('x'), get('z')
            if x is None or z is None:
                continue
            tx, ty, tz, tyaw = tgt
            if math.hypot(tx - x, tz - z) > 5:
                put('x', tx)
                put('z', tz)
            else:
                put('x', x + (tx - x) * k)
                put('z', z + (tz - z) * k)
            if ty is not None and get('y') is not None:
                put('y', get('y') + (ty - get('y')) * k)
            if tyaw is not None and get('yaw') is not None:
                yaw = get('yaw')
                d = (tyaw - yaw + math.pi) % (2 * math.pi) - math.pi
                put('yaw', yaw + d * k)

    def mp_events(self, attr, obj):
        """The monster's events this frame: its own on the host (which also sends
        them on), the host's on a client."""
        if self.mp_sim():
            evs = list(obj.events) if obj is not None and not isinstance(obj, dict) else []
            if self.mp_on():
                out = [e for e in evs if e != 'kill']
                if out:
                    self.mp.mev_out.setdefault(attr, []).extend(out)
            return evs
        return [e for e in self.mev_in.pop(attr, []) if e != 'kill']

    def mp_send_mev(self, attr, ev):
        """For scripted monsters (dicts) that don't have an event list of their own."""
        if self.mp_on() and self.mp.host:
            self.mp.mev_out.setdefault(attr, []).append(ev)

    def mp_is_target(self, attr):
        """Is this monster after ME? Single player: always. Co-op: only if the host says so --
        so one player being chased doesn't make everyone's screen panic."""
        if not self.mp_on():
            return True
        pid = self.mon_lock.get(attr) if self.mp.host else self.mon_tgt_pid.get(attr)
        return pid is not None and pid == self.mp.pid

    def mp_frozen(self, attr):
        return attr in self.mon_freeze

    # ---- who the monster goes after
    def mp_ai_target(self, obj, attr):
        """(target, light_on). Whoever it's already after, if they're still about;
        otherwise whoever is closest. In single player, always you."""
        p = self.player
        decoy = self.scared_target(attr)
        if decoy is not None:
            return (decoy, False)          # shot: it's off somewhere else, forgetting you
        mine = (p, self.flash_on and self.flicker_t <= 0)
        if not self.mp_on():
            return mine
        get = obj.get if isinstance(obj, dict) else (lambda n: getattr(obj, n, 0.0))
        mx, mz = get('x') or 0.0, get('z') or 0.0
        area = self.mp_area()
        cands = []
        if self.local_alive():
            cands.append(mine)
        for peer in self.mp.peers.values():
            if peer.alive and peer.area == area and not self.being_killed(peer.pid):
                cands.append((peer, bool(peer.s.get('fl'))))
        if not cands:
            return mine
        locked = self.mon_lock.get(attr)
        chasing = get('state') in ('chase', 'search', 'charge', 'charge_wind') if not isinstance(obj, dict) else True
        if locked and chasing:
            for c in cands:
                if getattr(c[0], 'pid', None) == locked and math.hypot(c[0].x - mx, c[0].z - mz) < 50:
                    return c
        best = min(cands, key=lambda c: math.hypot(c[0].x - mx, c[0].z - mz) - (8.0 if c[1] else 0.0))
        self.mon_lock[attr] = getattr(best[0], 'pid', None)
        return best

    # ---- caught
    def mp_caught(self, target, attr, kind=None):
        """A monster got someone."""
        if getattr(target, 'pid', 0) is None and not hasattr(target, 'eye'):
            return                         # the decoy: nobody was there
        if not self.mp_on():
            self.kill()
            return
        if not self.mp.host:
            return
        if self.mp_frozen(attr):
            return
        obj = getattr(self, attr, None)
        get = (obj.get if isinstance(obj, dict) else (lambda n: getattr(obj, n, 0.0))) if obj is not None else (lambda n: 0.0)
        kind = kind or dict(MONSTERS.get(self.chapter, [])).get(attr) or 'moose'
        rec = {'v': getattr(target, 'pid', self.mp.pid), 'k': kind, 'a': attr,
               'mx': round(get('x') or 0.0, 2), 'my': round(get('y') or 0.0, 2), 'mz': round(get('z') or 0.0, 2),
               'myaw': round(get('yaw') or 0.0, 3), 'x': round(target.x, 2), 'y': round(target.y, 2), 'z': round(target.z, 2)}
        self.mon_freeze[attr] = KILL_T
        self.mp_act('kill', **rec)

    def act_kill(self, a, frm):
        if a['v'] == self.mp.pid:
            self.kill(from_net=True)
        else:
            self.start_kill_anim(a)

    def act_died(self, a, frm):
        """Someone died on their own machine (The Beast's attacks)."""
        if a['v'] != self.mp.pid:
            self.start_kill_anim(a)

    def mp_after_kill(self, attr):
        obj = getattr(self, attr, None)
        if obj is None or isinstance(obj, dict):
            return
        if hasattr(obj, 'grace'):
            obj.grace = max(getattr(obj, 'grace', 0.0), 3.0)
        if getattr(obj, 'state', None) in ('chase', 'search') and attr != 'beast':
            obj.state = 'roam'
            if hasattr(obj, 'path'):
                obj.path = []
            obj.last_seen = None
            obj.timer = 0.0
        self.mon_lock.pop(attr, None)

    # ---- kill animations: what everyone else sees
    def start_kill_anim(self, a):
        self.mp_kills = [k for k in self.mp_kills if k['v'] != a['v']]
        rec = dict(a)
        rec['t'] = 0.0
        rec['blood'] = 0
        self.mp_kills.append(rec)
        peer = self.mp.peers.get(a['v']) if self.mp else None
        name = peer.name if peer else 'Someone'
        what = {'moose': "The Moose Man", 'moose4': "The Moose Man", 'goat': "The Goat Man", 'elk': "The Elk",
                'beast': "The Beast"}.get(a.get('k'), "It")
        self.message("%s got %s." % (what, name), 3.5)
        self.audio.play3d('screech', a['x'], a['z'], 60, 0.9)

    def being_killed(self, pid):
        return any(k['v'] == pid for k in self.mp_kills)

    def update_kill_anims(self, dt):
        for k in self.mp_kills:
            k['t'] += dt
            t = k['t']
            for i, at in enumerate((0.45, 0.8, 1.15, 1.55)):
                if k['blood'] <= i and t > at:
                    k['blood'] = i + 1
                    vx, vy, vz = self.kill_victim_pos(k)
                    self.spawn_blood(vx, vy + 1.2, vz, 18, vel=(0.0, 2.5, 0.0), spread=1.6)
                    if i == 0:
                        self.audio.play3d('tackle', vx, vz, 40, 0.8)
        self.mp_kills = [k for k in self.mp_kills if k['t'] < KILL_T + 0.6]

    def mp_hidden(self, attr):
        """The real monster isn't drawn while it's busy with someone."""
        return any(k['a'] == attr and k['k'] != 'beast' and k['t'] < KILL_T for k in self.mp_kills)

    def kill_victim_pos(self, k):
        t = k['t']
        lift = clamp((t - 0.25) / 0.35, 0, 1) * (1 - clamp((t - 1.65) / 0.25, 0, 1))
        if k['k'] == 'beast':
            return k['x'], k['y'], k['z']
        reach = {'moose': 0.75, 'moose4': 1.0, 'goat': 0.9, 'elk': 0.8}.get(k['k'], 0.8)
        dx, dz = k['x'] - k['mx'], k['z'] - k['mz']
        d = math.hypot(dx, dz) or 1.0
        ux, uz = dx / d, dz / d
        hx, hz = k['mx'] + ux * reach, k['mz'] + uz * reach
        hy = k['my'] + {'moose': 1.5, 'moose4': 1.9, 'goat': 1.7, 'elk': 0.9}.get(k['k'], 1.4)
        shake = 0.12 * math.sin(t * 31) * lift
        x = k['x'] + (hx - k['x']) * lift + shake
        z = k['z'] + (hz - k['z']) * lift
        y = k['y'] + (hy - 1.1 - k['y']) * lift
        return x, y, z

    def kill_parts(self, k):
        t = k['t']
        out = []
        dx, dz = k['x'] - k['mx'], k['z'] - k['mz']
        face = math.atan2(dx, dz)
        lift = clamp((t - 0.25) / 0.35, 0, 1) * (1 - clamp((t - 1.65) / 0.25, 0, 1))
        lie = clamp((t - 1.75) / 0.3, 0, 1)
        vx, vy, vz = self.kill_victim_pos(k)
        if k['k'] == 'beast':
            lie = clamp(t / 0.5, 0, 1)
            lift = 0.0
        peer = self.mp.peers.get(k['v']) if self.mp else None
        slot = peer.slot if peer else 0
        if t < KILL_T + 0.6:
            out.append(pose_player(vx, vy, vz, face + math.pi, pitch=-0.3, slot=slot, item='none', light_on=False,
                                   lift=lift, flail=lift * (1 - clamp((t - 1.3) / 0.4, 0, 1)), lie=lie, t=self.time))
        if k['k'] != 'beast' and t < KILL_T:
            lunge = clamp(t / 0.25, 0, 1)
            mx = k['mx'] + (math.sin(face) * 0.4) * lunge
            mz = k['mz'] + (math.cos(face) * 0.4) * lunge
            jaw = 0.8 + 0.3 * math.sin(t * 19)
            kind = k['k']
            if kind in ('moose', 'moose4'):
                out.append(pose_moose(mx, k['my'], mz, face, 0.0, 0.0, hunch=0.85, roll=0.3 * math.sin(t * 9),
                                      reach=1.0, jaw=jaw, t=t, shift=1.0 if kind == 'moose4' else 0.0,
                                      arms_up=0.8 * lift if kind == 'moose4' else 0.0)[0])
            elif kind == 'goat':
                out.append(pose_goat(mx, k['my'], mz, face, hunch=0.9, arms=1.0, jaw=jaw, bloody=True, t=t)[0])
            elif kind == 'elk':
                out.append(pose_elk(mx, k['my'], mz, face, jaw=1.1, split=1.0, head_pitch=-0.1 - 0.3 * lift, t=t)[0])
        return out

    # ================================================================== everyone at the door
    def mp_gather(self, name, here):
        """Single player: True when you're there. Co-op: only when everyone is."""
        if not self.mp_on():
            return here
        if here:
            if self.mp_ready != name:
                self.mp_ready = name
                self.mp_ready_pos = (self.player.x, self.player.z)
        elif self.mp_ready == name:
            self.mp_ready = None
        if self.mp.host and self.mp_ready == name:
            waiting = [p for p in self.mp.peers.values() if p.s.get('at') != name]
            if not waiting:
                p = self.player
                self.mp_act('go', name=name, x=round(p.x, 2), z=round(p.z, 2), yaw=round(p.yaw, 3))
        return False

    def gather_status(self):
        if not self.mp_on() or not self.mp_ready:
            return None
        n = 1 + sum(1 for p in self.mp.peers.values() if p.s.get('at') == self.mp_ready)
        return "Waiting for everyone at %s  (%d/%d)" % (GATHER_NAMES.get(self.mp_ready, 'the exit'), n, self.mp_count())

    def act_go(self, a, frm):
        name = a['name']
        was_ready = self.mp_ready == name
        self.mp_ready = None
        p = self.player
        if not was_ready and name != 'butcher' and math.hypot(p.x - a['x'], p.z - a['z']) > 2.5:
            # you weren't there: you come along anyway
            p.x, p.z, p.yaw = a['x'], a['z'], a['yaw']
            p.vx = p.vz = 0.0
        if self.state != 'play':
            self.state = 'play'
            self.set_mouse(True)
        self.block_input = False
        fn = {'ladder': self.start_climb, 'road': self.start_cutscene, 'cabin': self.start_window_cs,
              'elevator': self.start_ride, 'exit3': self.start_elkgrab, 'exit4': self.start_exit4,
              'factory': self.start_beast_cs, 'exit5': self.start_exit5, 'butcher': self.start_butcher,
              'cart': self.start_cart, 'beastcs': self.start_beast_cs}.get(name)
        if fn:
            fn()

    # ================================================================== the shared puzzles, chapter by chapter
    def who(self, frm):
        if frm is None or self.mp is None:
            return None
        p = self.mp.peers.get(frm)
        return p.name if p else 'Someone'

    # ---- chapter 1
    def act_valve(self, a, frm):
        v = self.world.valves[a['i']]
        if not v['done']:
            v['progress'] = 1.0
            self.valve_complete(v)

    def act_gallery(self, a, frm):
        if not (self.mp_on() and self.mp.host) or self.chapter != 1:
            return
        m = self.moose
        if m.state == 'inactive':
            self.flags.add('gallery')
            m.place_cell(20, 26)
            m.state = 'intro'
            m.timer = 5.0
            m.yaw = math.atan2(a['x'] - m.x, a['z'] - m.z)

    # ---- chapter 2
    def act_wood(self, a, frm):
        self.wood_taken.add(a['i'])

    def act_wood_back(self, a, frm):
        if frm is not None:
            for s in a.get('spots', []):
                self.wood_taken.discard(s)

    def act_stack(self, a, frm):
        if self.ch2_phase != 'wood':
            return
        self.stacked = min(C2.WOOD_NEEDED, self.stacked + a['n'])
        if frm is not None:
            self.audio.play('wood_drop', 0.5)
        if self.stacked >= C2.WOOD_NEEDED:
            self.start_rifle_phase()
        else:
            if frm is None:
                self.message("You stack the wood. (%d/%d)" % (self.stacked, C2.WOOD_NEEDED), 3.5)
            else:
                self.message("%s stacked some wood. (%d/%d)" % (self.who(frm), self.stacked, C2.WOOD_NEEDED), 3.5)
            self.set_objective("Gather firewood before the storm. Stacked %d/%d." % (self.stacked, C2.WOOD_NEEDED))

    def act_door(self, a, frm):
        self.w2.door_open = bool(a['open'])
        self.audio.play('door_open' if self.w2.door_open else 'door_close', 0.8)

    def act_rifle(self, a, frm):
        if self.ch2_phase != 'rifle':
            return
        self.ch2_phase = 'hunt'
        self.message("%s took a rifle down. There's another on the rack." % self.who(frm), 4)
        self.set_objective("Pick a spot outside and put the bait down: hold it ([Tab]) and press [E]. "
                           "A deer will come to it.")

    def act_deer_shot(self, a, frm):
        if self.mp_sim() and self.deer is not None:
            self.deer.shot()

    def act_deer_spook(self, a, frm):
        if self.mp_sim() and self.deer is not None:
            self.deer.spook(a['x'], a['z'])

    # ---- chapter 3
    def act_lever(self, a, frm):
        lv = self.lv_low if a.get('low') else self.lv_up
        lev = lv.levers[a['i']]
        if lev['pulled']:
            return
        lev['pulled'] = True
        lev['progress'] = 1.0
        self.audio.play('clunk', 1.0 if frm is None else 0.6)
        if lv is self.lv_low:
            self.ch3_low_lever_done()
            return
        n = sum(1 for x in lv.levers if x['pulled'])
        k = len(lv.levers)
        if n < k:
            self.message(("The lever slams down. (%d/%d)" % (n, k)) if frm is None else
                         ("%s pulled a lever. (%d/%d)" % (self.who(frm), n, k)), 3)
            self.set_objective("Pull the %d levers to start the elevator. (%d/%d)" % (k, n, k))
        else:
            self.power = True
            self.audio.play('drain', 0.5)
            self.message("Somewhere a generator coughs, and catches. The lights come on.", 5)
            self.set_objective("Take the elevator down. It's past the mine office.")

    def act_goatfound(self, a, frm):
        if self.mp_sim() and self.goat_found_t < 0:
            self.goat_found_t = 0.0

    # ---- chapter 4
    def act_gen(self, a, frm):
        self.gen_done(a['i'])

    def act_fuse_take(self, a, frm):
        self.lv4.fuses[a['i']]['taken'] = True

    def act_fuse_in(self, a, frm):
        self.fuses_added(a['n'], a['x'], a['z'])

    # ---- chapter 5
    def act_herd_dmg(self, a, frm):
        h = getattr(self, a.get('h', 'herd5'), None)
        if self.mp_sim() and h is not None and frm is not None:
            h.damage(int(a['i']), float(a['amt']))

    def act_beast_dmg(self, a, frm):
        b = self.beast
        if self.mp_sim() and b is not None and frm is not None:
            b.damage(a['amt'])

    # ---- endings: the host turns the pages
    def act_page(self, a, frm):
        if self.state == 'ending' and not self.mp.host:
            self.ending_page = a['n']
            self.ending_t = 0.0
            if self.ending_page >= len(self.ending_pages):
                self.ending_done()

    def ending_done(self):
        nxt = getattr(self, 'ending_next', None)
        self.ending_next = None
        if nxt:
            nxt()
        elif self.mp_on():
            self.mp_to_lobby()
        else:
            self.to_title()

    # ================================================================== drawing the others
    def mp_parts(self, cam=None, fwd=None):
        if not self.mp_on():
            return []
        if cam is not None:
            self._cam = (cam, fwd)
        if self.state not in PLAYISH + ('scare',):
            return []
        out = []
        area = self.mp_area()
        for peer in self.mp.peers.values():
            if not peer.alive or peer.area != area or peer.rx is None or self.being_killed(peer.pid):
                continue
            out.append(pose_player(peer.rx, peer.ry, peer.rz, peer.ryaw, pitch=peer.pitch, phase=peer.phase,
                                   amt=peer.amt, crouch=peer.crouch, slot=peer.slot, item=peer.s.get('it', 'flash'),
                                   light_on=bool(peer.s.get('fl')), t=self.time))
        for k in self.mp_kills:
            out.extend(self.kill_parts(k))
        return out

    def mp_lights(self):
        if not self.mp_on() or self.state not in PLAYISH + ('scare',):
            return []
        out = []
        area = self.mp_area()
        for peer in self.mp.peers.values():
            if not peer.alive or peer.area != area or peer.rx is None or not peer.s.get('fl'):
                continue
            fx, fz = math.sin(peer.ryaw), math.cos(peer.ryaw)
            if peer.s.get('it') == 'flash':
                out.append(((peer.rx + fx * 2.2, peer.ry + 1.2, peer.rz + fz * 2.2), 7.5, (1.1, 1.0, 0.8)))
            else:
                k = 0.9 + 0.08 * math.sin(self.time * 11 + peer.slot)
                out.append(((peer.rx + fx * 0.5, peer.ry + 1.3, peer.rz + fz * 0.5), 9.0, (1.25 * k, 0.78 * k, 0.38 * k)))
        return out

    def draw_coop_hud(self):
        if not self.mp_on():
            return
        # names over heads
        if self._cam and self.state == 'play':
            cam, fwd = self._cam
            fx, fy, fz = fwd
            hl = math.hypot(fx, fz) or 1.0
            rx, rz = -fz / hl, fx / hl            # the camera's right, as the movement code has it
            ux, uy, uz = -rz * fy, rz * fx - rx * fz, rx * fy
            th = math.tan(math.radians(self.settings['fov']) / 2)
            aspect = self.UW / float(self.UH)
            area = self.mp_area()
            for peer in self.mp.peers.values():
                if not peer.alive or peer.area != area or peer.rx is None:
                    continue
                dx, dy, dz = peer.rx - cam[0], peer.ry + 2.15 - cam[1], peer.rz - cam[2]
                depth = dx * fx + dy * fy + dz * fz
                if depth < 0.5 or depth > 30:
                    continue
                sx = (dx * rx + dz * rz) / (depth * th * aspect)
                upd = dx * ux + dy * uy + dz * uz
                sy = upd / (depth * th)
                if abs(sx) > 1.1 or abs(sy) > 1.1:
                    continue
                px = int((1 + sx) * 0.5 * self.UW)
                py = int((1 - sy) * 0.5 * self.UH)
                col = tuple(int(min(255, 90 + c * 260)) for c in COATS[peer.slot % len(COATS)])
                al = int(255 * clamp(1.3 - depth / 25.0, 0.25, 1.0))
                self.blit_text(peer.name, self.f_small, col, (px, py), 'midbottom', alpha=al)
        if not self.mp.net.ok:
            self.blit_text("reconnecting...", self.f_hud, (220, 120, 100), (self.UW // 2, int(self.UH * 0.14)), 'midtop')
        gs = self.gather_status()
        if gs:
            self.blit_text(gs, self.f_hud, (215, 205, 190), (self.UW // 2, int(self.UH * 0.2)), 'midtop')

    def draw_coop_ui(self):
        st = self.state
        cx = self.UW // 2
        if st == 'coop':
            self.draw_menu(self.coop_items(), "CO-OP")
        elif st in ('coopname', 'coopjoin'):
            title = "YOUR NAME" if st == 'coopname' else "ROOM CODE"
            self.blit_text(title, self.f_big, (200, 190, 180), (80, int(self.UH * 0.56) - 90))
            box = pygame.Rect(80, int(self.UH * 0.56), 420, 54)
            pygame.draw.rect(self.ui, (0, 0, 0, 200), box)
            pygame.draw.rect(self.ui, (160, 40, 30, 255), box, 2)
            cur = '_' if int(self.time * 2) % 2 == 0 else ' '
            self.blit_text(self.text_buf + cur, self.f_menu, (225, 215, 200), (box.x + 14, box.y + 10))
            hint = "Enter to confirm, Esc to go back" if st == 'coopname' else "Type the 5-letter code your friend sees, then Enter"
            self.blit_text(hint, self.f_small, (140, 132, 125), (80, box.bottom + 12))
        elif st == 'lobby':
            m = self.mp
            if m is None:
                return
            y0 = int(self.UH * 0.18)
            if not m.net.ok:
                self.blit_text("connecting...", self.f_med, (170, 160, 150), (80, y0))
            elif not m.joined:
                self.blit_text("joining %s..." % m.code, self.f_med, (170, 160, 150), (80, y0))
            else:
                self.blit_text("ROOM CODE", self.f_small, (150, 140, 130), (80, y0))
                self.blit_text(m.code, self.f_big, (220, 60, 45), (80, y0 + 18))
                y = y0 + 100
                roster = [(m.name + ('  (host)' if m.host else '') + '  - you', m.slot)]
                for p in sorted(m.peers.values(), key=lambda p: p.slot):
                    roster.append((p.name + ('  (host)' if p.pid == m.host_pid else ''), p.slot))
                for name, slot in roster:
                    c = COATS[slot % len(COATS)]
                    pygame.draw.rect(self.ui, tuple(int(min(255, v * 330)) for v in c) + (255,), (80, y + 5, 14, 14))
                    self.blit_text(name, self.f_hud, (210, 200, 190), (104, y))
                    y += 28
                self.blit_text("%d/%d players" % (len(roster), NET.MAX_PLAYERS), self.f_small, (130, 122, 115), (80, y + 4))
                if not m.host:
                    self.blit_text("Waiting for the host to start...  (%s)" % CHAPTER_NAMES[m.chapter - 1],
                                   self.f_small, (170, 160, 150), (80, int(self.UH * 0.56) - 40))
            self.draw_menu(self.lobby_items(), None)
        if self.coop_msg_t > 0 and self.coop_msg and st in ('title', 'coop', 'coopjoin', 'coopname', 'lobby'):
            self.blit_text(self.coop_msg, self.f_hud, (220, 120, 100), (cx, self.UH - 70), 'midtop')


class _NoKeys:
    def __getitem__(self, k):
        return False


_MOVE = {pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d, pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT,
         pygame.K_LSHIFT, pygame.K_RSHIFT, pygame.K_LCTRL, pygame.K_RCTRL, pygame.K_c, pygame.K_SPACE}


class _NoMoveKeys:
    """While flying (freecam / noclip) the chapter's own walking code sees no movement keys."""
    def __init__(self, real):
        self.real = real

    def __getitem__(self, k):
        return False if k in _MOVE else self.real[k]
