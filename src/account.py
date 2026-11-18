"""Accounts, the login screen, the admin menu, and the settings screen.

Accounts are Supabase Auth users. Players pick a username; Supabase wants an
email, so the game makes one from the name (nothing is ever sent to it). The
`mooseman_profiles` table holds the username and is_admin -- see
supabase/mooseman_accounts.sql.

"Remember me" keeps the refresh token on this machine (account.json, or the
browser's localStorage) and signs you straight back in next time.
"""
import json
import math
import os
import re
import threading
import time

import pygame

import net as NET
import webplat as WP

EMAIL_DOMAIN = 'players.moosemangame.com'
NAME_RE = re.compile(r'^[A-Za-z0-9_]{3,16}$')


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


# ---------------------------------------------------------------------- HTTP, desktop or browser
class Http:
    """Fire a request now, collect the answer on a later frame."""

    def __init__(self):
        self.done = {}
        self.n = 0

    def start(self, method, url, headers, body=None):
        self.n += 1
        h = self.n
        data = json.dumps(body) if body is not None else ''
        if WP.WEB:
            h = int(WP.js.mm.httpStart(method, url, json.dumps(headers), data))
            return ('web', h)

        def run():
            import urllib.request
            import urllib.error
            req = urllib.request.Request(url, data=data.encode() if data else None, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    self.done[h] = (r.status, r.read().decode('utf-8', 'replace'))
            except urllib.error.HTTPError as e:
                self.done[h] = (e.code, e.read().decode('utf-8', 'replace'))
            except Exception as e:
                self.done[h] = (0, str(e))
        threading.Thread(target=run, daemon=True).start()
        return ('desk', h)

    def result(self, handle):
        """None while waiting; (status, text) once it's back. status 0 = no connection."""
        kind, h = handle
        if kind == 'web':
            raw = WP.js.mm.httpResult(h)
            if not raw:
                return None
            r = json.loads(raw)
            return int(r['status']), r['body']
        return self.done.pop(h, None)


def _account_path():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'MooseMan', 'account.json')


def load_remembered():
    if WP.WEB:
        return WP.load_json('account', {})
    try:
        with open(_account_path()) as f:
            return json.load(f)
    except Exception:
        return {}


def save_remembered(d):
    if WP.WEB:
        WP.save_json('account', d)
        return
    try:
        os.makedirs(os.path.dirname(_account_path()), exist_ok=True)
        with open(_account_path(), 'w') as f:
            json.dump(d, f)
    except Exception:
        pass


def _err_text(status, body):
    if status == 0:
        return "Couldn't reach the server. Check your internet."
    try:
        j = json.loads(body)
    except Exception:
        j = {}
    msg = (j.get('msg') or j.get('error_description') or j.get('message') or j.get('error') or '').lower()
    code = (j.get('error_code') or j.get('code') or '').lower()
    if 'invalid login' in msg or code == 'invalid_credentials':
        return "Wrong username or password."
    if 'already' in msg or code in ('user_already_exists', 'email_exists'):
        return "That username is taken."
    if 'not confirmed' in msg or code == 'email_not_confirmed':
        return "Accounts aren't switched on yet (turn off Confirm email in Supabase)."
    if 'password' in msg:
        return "That password is too weak. Use at least 6 characters."
    if 'rate limit' in msg or status == 429:
        return "Too many tries. Wait a minute and try again."
    return "Something went wrong (%s)." % (msg or status)


SETTING_TABS = [
    ('GAME', ['sensitivity', 'invert_y', 'fov', 'auto_update', '@delete']),
    ('GRAPHICS', ['brightness', 'res', 'grain', 'vhs', 'show_fps', 'display']),
    ('AUDIO', ['volume']),
    ('ACCOUNT', ['@who', '@logout']),
]


class AccountMixin:
    # ================================================================== state
    def init_account(self):
        self.http = Http()
        self.acct = None              # {'user', 'id', 'admin', 'access', 'refresh'} once logged in
        self.login_user = ''
        self.login_pw = ''
        self.login_remember = True
        self.login_sel = 0
        self.login_err = ''
        self.login_busy = None        # (what, handle, extra)
        self.admin_open = False
        self.admin_sel = 0
        self.admin_msg_t = 0.0
        self.settings_tab = 0
        self.delete_arm_t = 0.0
        self.settings_note = ''
        self.settings_note_t = 0.0
        self.fullbright = self.freecam = self.noclip = False
        self.mark_mon = self.mark_puz = False
        self.admin_tp = 1
        self.admin_note = ''
        self.fly_cam = [0.0, 0.0, 0.0]
        self.fly_pos = [0.0, 0.0, 0.0]
        self.cloud_reset()

    def cloud_reset(self):
        self.cloud_busy = None        # (what, handle)
        self.cloud_dirty = False
        self.cloud_pull = False
        self.cloud_status = ''        # '', 'syncing', 'synced', 'offline', 'no table'
        self.cloud_wait = 0.0

    def account_start(self):
        """After loading: sign back in if remembered, otherwise the login screen."""
        self.state = 'login'
        self.login_sel = 0
        self.login_err = ''
        self.set_mouse(False)
        rem = load_remembered()
        if rem.get('refresh') and NET.configured():
            self.login_user = rem.get('user', '')
            self.login_busy = ('refresh', self._auth('token?grant_type=refresh_token', {'refresh_token': rem['refresh']}), None)
        elif rem.get('user'):
            self.login_user = rem['user']
            self.login_sel = 1

    @property
    def is_admin(self):
        return bool(self.acct and self.acct.get('admin'))

    # ================================================================== talking to Supabase
    def _auth(self, path, body):
        return self.http.start('POST', NET.SUPABASE_URL.rstrip('/') + '/auth/v1/' + path,
                               {'apikey': NET.SUPABASE_KEY, 'Content-Type': 'application/json'}, body)

    def _email(self, name):
        return '%s@%s' % (name.lower(), EMAIL_DOMAIN)

    def login_submit(self, create):
        u, pw = self.login_user.strip(), self.login_pw
        if not NET.configured():
            self.login_err = "Accounts aren't set up in this build."
            return
        if not NAME_RE.match(u):
            self.login_err = "Usernames are 3-16 letters, numbers or _."
            self.login_sel = 0
            return
        if len(pw) < 6:
            self.login_err = "Passwords are at least 6 characters."
            self.login_sel = 1
            return
        self.login_err = ''
        if create:
            self.login_busy = ('signup', self._auth('signup', {'email': self._email(u), 'password': pw,
                                                                'data': {'mm_username': u}}), u)
        else:
            self.login_busy = ('login', self._auth('token?grant_type=password', {'email': self._email(u), 'password': pw}), u)
        self.audio.play('click', 0.5)

    def update_login(self, dt):
        self.update_cloud(dt)
        self.admin_msg_t = max(0.0, self.admin_msg_t - dt)
        self.delete_arm_t = max(0.0, self.delete_arm_t - dt)
        self.settings_note_t = max(0.0, self.settings_note_t - dt)
        if not self.login_busy:
            return
        what, handle, extra = self.login_busy
        res = self.http.result(handle)
        if res is None:
            return
        status, body = res
        self.login_busy = None
        if what in ('login', 'signup', 'refresh'):
            if status != 200:
                if what == 'refresh':
                    if status:
                        save_remembered({'user': self.login_user})   # the old session is gone: log in again
                        self.login_err = "Please log in again."
                    else:
                        self.login_err = _err_text(status, body)     # offline: keep it for next time
                    self.login_sel = 1
                else:
                    self.login_err = _err_text(status, body)
                return
            j = json.loads(body)
            if not j.get('access_token'):
                self.login_err = "Account made, but it needs email confirmation (turn it off in Supabase)."
                return
            user = j.get('user') or {}
            name = (user.get('user_metadata') or {}).get('mm_username') or extra or self.login_user
            self.acct = {'user': name, 'id': user.get('id'), 'admin': False,
                         'access': j['access_token'], 'refresh': j.get('refresh_token'),
                         'exp': time.time() + float(j.get('expires_in') or 3600)}
            self.cloud_reset()
            self.cloud_pull = True
            if what == 'refresh' or self.login_remember:
                save_remembered({'user': name, 'refresh': j.get('refresh_token')})
            else:
                save_remembered({'user': name})
            self.login_pw = ''
            self.settings['coop_name'] = name
            url = '%s/rest/v1/mooseman_profiles?id=eq.%s&select=username,is_admin' % (NET.SUPABASE_URL.rstrip('/'),
                                                                                     self.acct['id'])
            self.login_busy = ('profile', self.http.start('GET', url, {'apikey': NET.SUPABASE_KEY,
                                                                       'Authorization': 'Bearer ' + j['access_token']}),
                               None)
            if what == 'signup':
                self.message("Account made. Welcome, %s." % name, 4)
            self.state = 'title'
            self.menu_sel = 0
        elif what == 'profile' and self.acct:
            try:
                rows = json.loads(body) if status == 200 else []
            except Exception:
                rows = []
            if rows:
                self.acct['admin'] = bool(rows[0].get('is_admin'))
                self.acct['user'] = rows[0].get('username') or self.acct['user']

    def log_out(self):
        rem = load_remembered()
        save_remembered({'user': rem.get('user', '')})
        self.acct = None
        self.cloud_reset()
        self.admin_open = False
        self.fullbright = self.freecam = self.noclip = False
        if self.mp is not None:
            self.mp_leave('')
        self.to_title()
        self.account_start()

    def play_as_guest(self):
        self.acct = None
        self.cloud_reset()
        self.audio.play('click', 0.5)
        self.state = 'title'
        self.menu_sel = 0

    # ================================================================== cloud saves
    def cloud_label(self):
        return {'syncing': "  -  syncing...", 'synced': "  -  progress synced", 'offline': "  -  offline, will sync",
                'no table': "  -  cloud saves not set up"}.get(self.cloud_status, '')

    def on_progress_saved(self, p):
        """Every save: stamp it, mark whose it is, and queue it for upload."""
        p['saved_at'] = round(time.time(), 3)
        if self.acct:
            p['owner'] = self.acct['id']
            self.cloud_dirty = True

    def _rest(self, method, path, body=None, extra=None):
        h = {'apikey': NET.SUPABASE_KEY, 'Authorization': 'Bearer ' + self.acct['access'],
             'Content-Type': 'application/json'}
        if extra:
            h.update(extra)
        return self.http.start(method, NET.SUPABASE_URL.rstrip('/') + '/rest/v1/' + path, h, body)

    def update_cloud(self, dt):
        a = self.acct
        if not a or not a.get('id'):
            return
        self.cloud_wait = max(0.0, self.cloud_wait - dt)
        if self.cloud_busy:
            what, handle = self.cloud_busy
            res = self.http.result(handle)
            if res is None:
                return
            self.cloud_busy = None
            self.cloud_done(what, *res)
            return
        if self.cloud_wait > 0 or not (self.cloud_pull or self.cloud_dirty):
            return
        if time.time() > a.get('exp', 0) - 60:
            # the access token has run out: swap the refresh token for a new one first
            self.cloud_busy = ('refresh', self._auth('token?grant_type=refresh_token', {'refresh_token': a['refresh']}))
            return
        self.cloud_status = 'syncing'
        if self.cloud_pull:
            self.cloud_busy = ('pull', self._rest('GET', 'mooseman_saves?user_id=eq.%s&select=data' % a['id']))
        else:
            self.cloud_dirty = False
            body = {'user_id': a['id'], 'data': self.progress,
                    'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
            self.cloud_busy = ('push', self._rest('POST', 'mooseman_saves?on_conflict=user_id', body,
                                                  {'Prefer': 'resolution=merge-duplicates,return=minimal'}))

    def cloud_done(self, what, status, body):
        a = self.acct
        if what == 'refresh':
            if status == 200:
                j = json.loads(body)
                a['access'], a['refresh'] = j['access_token'], j.get('refresh_token', a['refresh'])
                a['exp'] = time.time() + float(j.get('expires_in') or 3600)
                rem = load_remembered()
                if rem.get('refresh'):
                    save_remembered({'user': a['user'], 'refresh': a['refresh']})
            else:
                self.cloud_status = 'offline'
                self.cloud_wait = 20.0
            return
        if status == 0:
            self.cloud_status = 'offline'
            self.cloud_wait = 15.0
            if what == 'push':
                self.cloud_dirty = True
            return
        if status == 401:
            a['exp'] = 0                       # stale token: refresh and try again
            if what == 'push':
                self.cloud_dirty = True
            return
        if status == 404 or 'mooseman_saves' in (body or '') and status >= 400:
            self.cloud_status = 'no table'
            self.cloud_pull = False
            self.cloud_dirty = False
            return
        if what == 'pull':
            self.cloud_pull = False
            try:
                rows = json.loads(body) if status == 200 else None
            except Exception:
                rows = None
            if rows is None:
                self.cloud_status = 'offline'
                self.cloud_wait = 15.0
                self.cloud_pull = True
                return
            self.cloud_merge(rows[0]['data'] if rows else None)
            return
        if what == 'push':
            if 200 <= status < 300:
                self.cloud_status = 'synced' if not self.cloud_dirty else 'syncing'
            else:
                self.cloud_status = 'offline'
                self.cloud_wait = 20.0
                self.cloud_dirty = True

    def cloud_merge(self, cloud):
        """Newest wins -- but never copy another account's save into this one."""
        uid = self.acct['id']
        local = self.progress
        owner = local.get('owner')
        lt = float(local.get('saved_at') or 0)
        ct = float(cloud.get('saved_at') or 0) if cloud else -1.0
        mine_here = owner in (None, uid) and any(k != 'owner' for k in local)
        if cloud is not None and (not mine_here or ct >= lt):
            self.progress.clear()
            self.progress.update(cloud)
            self.progress['owner'] = uid
            self.write_progress_local(self.progress)
            self.cloud_status = 'synced'
            if ct > lt + 1:
                self.message("Your progress was loaded from your account.", 3.5)
        elif mine_here:
            self.progress['owner'] = uid
            if not self.progress.get('saved_at'):
                self.progress['saved_at'] = round(time.time(), 3)
            self.write_progress_local(self.progress)
            self.cloud_dirty = True
        else:
            # this device's save belongs to someone else and the account has none yet: start fresh
            self.progress.clear()
            self.progress['owner'] = uid
            self.write_progress_local(self.progress)
            self.cloud_status = 'synced'

    # ================================================================== the login screen
    LOGIN_ITEMS = ['USERNAME', 'PASSWORD', 'REMEMBER ME', 'LOG IN', 'CREATE ACCOUNT', 'PLAY AS GUEST']

    def login_rects(self):
        cx = self.UW // 2
        y = int(self.UH * 0.30)
        out = []
        for i in range(6):
            if i < 2:
                out.append(pygame.Rect(cx - 170, y + i * 62 + 18, 340, 34))
            elif i == 2:
                out.append(pygame.Rect(cx - 170, y + 2 * 62 + 4, 200, 28))
            else:
                out.append(pygame.Rect(cx - 170, y + 2 * 62 + 46 + (i - 3) * 44, 340, 38))
        return out

    def login_event(self, ev):
        if self.login_busy:
            return
        n = len(self.LOGIN_ITEMS)
        if ev.type == pygame.KEYDOWN:
            k = ev.key
            if k in (pygame.K_TAB, pygame.K_DOWN):
                self.login_sel = (self.login_sel + 1) % n
            elif k == pygame.K_UP:
                self.login_sel = (self.login_sel - 1) % n
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.login_activate(self.login_sel, enter=True)
            elif k == pygame.K_BACKSPACE and self.login_sel in (0, 1):
                if self.login_sel == 0:
                    self.login_user = self.login_user[:-1]
                else:
                    self.login_pw = self.login_pw[:-1]
            elif k == pygame.K_SPACE and self.login_sel >= 2:
                self.login_activate(self.login_sel)
            elif self.login_sel in (0, 1) and ev.unicode and ev.unicode.isprintable() and ev.unicode != '\t':
                if self.login_sel == 0 and len(self.login_user) < 16 and re.match(r'[A-Za-z0-9_]', ev.unicode):
                    self.login_user += ev.unicode
                elif self.login_sel == 1 and len(self.login_pw) < 64:
                    self.login_pw += ev.unicode
        elif ev.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            ux, uy = self.ui_mouse()
            for i, rc in enumerate(self.login_rects()):
                if rc.collidepoint(ux, uy):
                    if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                        self.login_sel = i
                        if i >= 2:
                            self.login_activate(i)
                    elif ev.type == pygame.MOUSEMOTION and i >= 2:
                        self.login_sel = i

    def login_activate(self, i, enter=False):
        if i == 0:
            self.login_sel = 1
        elif i == 1:
            self.login_submit(False)
        elif i == 2:
            self.login_remember = not self.login_remember
            self.audio.play('click', 0.4)
        elif i == 3:
            self.login_submit(False)
        elif i == 4:
            self.login_submit(True)
        else:
            self.play_as_guest()

    def draw_login_ui(self):
        ui = self.ui
        ui.fill((0, 0, 0, 150))
        cx = self.UW // 2
        self.blit_text("MOOSE MAN", self.f_big, (200, 190, 180), (cx, int(self.UH * 0.08)), 'midtop')
        rects = self.login_rects()
        for i, name in enumerate(self.LOGIN_ITEMS):
            rc = rects[i]
            sel = i == self.login_sel
            col = (230, 222, 212) if sel else (160, 154, 148)
            if i < 2:
                self.blit_text(name, self.f_small, (150, 140, 130), (rc.x, rc.y - 18))
                pygame.draw.rect(ui, (0, 0, 0, 210), rc)
                pygame.draw.rect(ui, (190, 45, 32, 255) if sel else (90, 80, 75, 255), rc, 2)
                txt = self.login_user if i == 0 else '*' * len(self.login_pw)
                cur = '_' if sel and int(self.time * 2) % 2 == 0 else ''
                self.blit_text(txt + cur, self.f_hud, (230, 222, 212), (rc.x + 10, rc.y + 7))
            elif i == 2:
                box = pygame.Rect(rc.x, rc.y + 4, 20, 20)
                pygame.draw.rect(ui, (190, 45, 32, 255) if sel else (110, 100, 95, 255), box, 2)
                if self.login_remember:
                    pygame.draw.line(ui, (230, 222, 212, 255), (box.x + 4, box.y + 10), (box.x + 8, box.y + 15), 3)
                    pygame.draw.line(ui, (230, 222, 212, 255), (box.x + 8, box.y + 15), (box.x + 16, box.y + 4), 3)
                self.blit_text("REMEMBER ME", self.f_small, col, (box.right + 10, box.y + 3))
            else:
                if sel:
                    pygame.draw.rect(ui, (80, 12, 10, 170), rc)
                self.blit_text(('> ' if sel else '') + name, self.f_hud, (210, 50, 38) if sel else col,
                               (rc.x + 10, rc.y + 9))
        y = rects[-1].bottom + 14
        if self.login_busy:
            what = self.login_busy[0]
            t = {'login': "logging in...", 'signup': "making your account...", 'refresh': "signing you back in...",
                 'profile': "..."}.get(what, '...')
            self.blit_text(t, self.f_hud, (200, 190, 180), (cx, y), 'midtop')
        elif self.login_err:
            self.blit_text(self.login_err, self.f_small, (230, 110, 90), (cx, y), 'midtop')
        self.blit_text("Tab / arrows to move, Enter to confirm", self.f_small, (110, 104, 98),
                       (cx, self.UH - 30), 'midtop')

    def draw_account_badge(self):
        if self.state != 'title':
            return
        if self.acct:
            t = "logged in as %s%s%s" % (self.acct['user'], "  (admin)" if self.is_admin else '', self.cloud_label())
        else:
            t = "playing as a guest"
        self.blit_text(t, self.f_small, (130, 122, 115), (self.UW - 16, 16), 'topright')

    # ================================================================== admin menu (` key)
    ADMIN_IDS = ['unlock', 'tp', 'fullbright', 'freecam', 'noclip', 'markmon', 'markpuz', 'close']

    @property
    def ADMIN_ITEMS(self):
        on = lambda b: 'ON' if b else 'OFF'
        return ['UNLOCK ALL CHAPTERS', 'TP TO CHAPTER   <  %d  >' % self.admin_tp,
                'FULLBRIGHT:  %s' % on(self.fullbright), 'FREECAM:  %s' % on(self.freecam),
                'NOCLIP:  %s' % on(self.noclip), 'MARK MONSTERS:  %s' % on(self.mark_mon),
                'MARK PUZZLES:  %s' % on(self.mark_puz), 'CLOSE']

    def admin_rows(self):
        x0, y0 = self.UW // 2 - 190, self.UH // 2 - 140
        return [pygame.Rect(x0, y0 + 36 + i * 32, 380, 28) for i in range(len(self.ADMIN_ITEMS))]

    # ---- fly about: freecam (the view goes, you stay) and noclip (you go, through everything)
    def admin_fly_start(self):
        p = self.player
        e = p.eye()
        self.fly_cam = list(e)
        self.fly_pos = [p.x, p.y, p.z]

    def _raw_keys(self):
        if getattr(self, 'web_keys', None) is not None:
            return self.web_keys
        return pygame.key.get_pressed()

    def admin_fly(self, dt):
        """WASD where you look, Space up, Ctrl/C down, Shift fast."""
        if not (self.freecam or self.noclip) or self.state != 'play':
            return
        if not self.is_admin:
            self.freecam = self.noclip = False
            return
        k = self._raw_keys()
        p = self.player
        cp = math.cos(p.pitch)
        f = (math.sin(p.yaw) * cp, math.sin(p.pitch), math.cos(p.yaw) * cp)
        rx, rz = -math.cos(p.yaw), math.sin(p.yaw)
        mv = (1 if k[pygame.K_w] or k[pygame.K_UP] else 0) - (1 if k[pygame.K_s] or k[pygame.K_DOWN] else 0)
        ms = (1 if k[pygame.K_d] or k[pygame.K_RIGHT] else 0) - (1 if k[pygame.K_a] or k[pygame.K_LEFT] else 0)
        up = (1 if k[pygame.K_SPACE] else 0) - (1 if (k[pygame.K_LCTRL] or k[pygame.K_c]) else 0)
        sp = 20.0 if (k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT]) else 6.0
        d = (f[0] * mv + rx * ms, f[1] * mv + up, f[2] * mv + rz * ms)
        if self.freecam:
            for i in range(3):
                self.fly_cam[i] += d[i] * sp * dt
        else:
            for i in range(3):
                self.fly_pos[i] += d[i] * sp * dt
            p.vx, p.vz = d[0] * sp, d[2] * sp

    def admin_fly_after(self):
        """Noclip: wherever the chapter's own movement put you, you're where you flew."""
        if self.noclip and not self.freecam and self.state == 'play' and self.is_admin:
            p = self.player
            p.x, p.y, p.z = self.fly_pos
            p.smooth_y = p.y
            p.bob_amt = 0.0

    def fly_keys_blocked(self):
        return (self.freecam or self.noclip) and self.state == 'play' and self.is_admin

    def admin_toggle(self):
        self.admin_open = not self.admin_open
        self.admin_sel = 0
        if self.admin_open:
            self.admin_was_grab = self.state == 'play'
            self.set_mouse(False)
        elif self.state == 'play':
            self.set_mouse(True)

    def admin_event(self, ev):
        n = len(self.ADMIN_ITEMS)
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self.admin_toggle()
            elif ev.key in (pygame.K_UP, pygame.K_w):
                self.admin_sel = (self.admin_sel - 1) % n
            elif ev.key in (pygame.K_DOWN, pygame.K_s):
                self.admin_sel = (self.admin_sel + 1) % n
            elif ev.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d) and self.ADMIN_IDS[self.admin_sel] == 'tp':
                self.admin_tp = (self.admin_tp - 1 + (1 if ev.key in (pygame.K_RIGHT, pygame.K_d) else -1)) % 5 + 1
                self.audio.play('click', 0.4)
            elif ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                self.admin_action(self.admin_sel)
        elif ev.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            ux, uy = self.ui_mouse()
            for i, rc in enumerate(self.admin_rows()):
                if rc.collidepoint(ux, uy):
                    self.admin_sel = i
                    if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                        if self.ADMIN_IDS[i] == 'tp' and ux > rc.x + rc.width * 0.62:
                            # the arrows: tap the left half of the number to go down, the right to go up
                            mid = rc.x + rc.width * 0.81
                            self.admin_tp = (self.admin_tp - 1 + (1 if ux > mid else -1)) % 5 + 1
                            self.audio.play('click', 0.4)
                        else:
                            self.admin_action(i)

    def admin_action(self, i):
        self.audio.play('click', 0.5)
        what = self.ADMIN_IDS[i]
        if what == 'unlock':
            self.admin_note = ''
            for k in ('ch2', 'ch3', 'ch4', 'ch5'):
                self.progress[k] = True
            self.save_prog()
            self.admin_msg_t = 2.5
        elif what == 'tp':
            self.admin_teleport(self.admin_tp)
        elif what == 'fullbright':
            self.fullbright = not self.fullbright
        elif what == 'freecam':
            self.freecam = not self.freecam
            if self.freecam:
                self.admin_fly_start()
        elif what == 'noclip':
            self.noclip = not self.noclip
            if self.noclip:
                self.admin_fly_start()
        elif what == 'markmon':
            self.mark_mon = not self.mark_mon
        elif what == 'markpuz':
            self.mark_puz = not self.mark_puz
        else:
            self.admin_toggle()

    def admin_teleport(self, ch):
        if self.mp_on():
            self.admin_note = "Not in co-op: everyone has to start a chapter together."
            self.admin_msg_t = 3.0
            return
        self.admin_open = False
        self.freecam = self.noclip = False
        self.audio.unpause()
        self.audio.stop_all()
        keep = self.progress.get('resume')
        self.new_game()
        if ch == 1:
            self.start_chapter1()
        elif ch == 2:
            self.start_daylater()
        elif ch == 3:
            self.start_ch3()
        elif ch == 4:
            self.start_ch4()
        else:
            self.start_ch5()
        # a teleport doesn't move your CONTINUE point
        if keep is None:
            self.progress.pop('resume', None)
        else:
            self.progress['resume'] = keep
        self.save_prog()

    # ---- marks: where the monsters are, where the puzzle pieces are (drawn through walls)
    def admin_marks(self):
        out = []
        ch = self.chapter
        if self.mark_mon:
            from coop import MONSTERS
            names = {'moose': 'MOOSE MAN', 'chaser': 'MOOSE MAN', 'goat': 'GOAT MAN', 'deer': 'DEER', 'chaser2': 'MOOSE MAN',
                     'elk': 'ELK', 'moose4': 'MOOSE MAN', 'beast': 'THE BEAST'}
            for attr, _ in MONSTERS.get(ch, []):
                m = getattr(self, attr, None)
                if m is None:
                    continue
                get = m.get if isinstance(m, dict) else (lambda n, m=m: getattr(m, n, None))
                if get('x') is None:
                    continue
                if attr == 'moose' and not m.active:
                    continue
                if attr == 'chaser' and not self.escape:
                    continue
                if attr == 'chaser2' and self.ch2_phase != 'run':
                    continue
                if attr == 'deer' and self.ch2_phase != 'hunt':
                    continue
                y = (get('y') or 0.0) + (13.0 if attr == 'beast' else 2.6)
                out.append(((get('x'), y, get('z')), names.get(attr, attr.upper()), (240, 70, 55)))
            h = getattr(self, 'herd5', None)
            if self.chapter == 5 and h is not None and getattr(self, 'c5_phase', '') == 'drain':
                for i in range(min(h.n, len(h._d['x']))):
                    if h.alive(i):
                        out.append(((h._d['x'][i], 2.4, h._d['z'][i]), 'HERD', (240, 70, 55)))
        if self.mark_puz:
            for pos, label in self.puzzle_marks():
                out.append((pos, label, (240, 205, 70)))
        return out

    def puzzle_marks(self):
        ch = self.chapter
        out = []
        if ch == 1:
            w = self.world
            for v in w.valves:
                if not v['done']:
                    out.append((v['pos'], 'VALVE'))
            for lev in w.c1_levers:
                if not lev['pulled']:
                    out.append((lev['pos'], 'LEVER'))
            if w.key_pos and not self.key_taken:
                out.append((w.key_pos, 'KEY'))
            if w.keygate_open < 1.0:
                gx, gz = self.keygate_spot()
                out.append(((gx, -3.6, gz + 0.6), 'LADDER GATE'))
        elif ch == 2:
            p = self.player
            ph = self.ch2_phase
            if ph == 'wood':
                spots = [(math.hypot(x - p.x, z - p.z), (x, y + 0.4, z)) for i, (x, y, z, _) in enumerate(self.w2.wood_spots)
                         if i not in self.wood_taken]
                spots.sort(key=lambda s: s[0])
                out += [(pos, 'WOOD') for _, pos in spots[:12]]
                import chapter2 as C2
                out.append(((C2.WOODPILE[0], C2.CABIN_Y + 0.6, C2.WOODPILE[1]), 'WOODPILE'))
            elif ph == 'fire':
                sx, sz = self.stove_spot()
                out.append(((sx, 0.9, sz), 'STOVE'))
            elif ph in ('rifle', 'hunt'):
                import chapter2 as C2
                if not self.has_rifle:
                    out.append(((C2.RIFLE_POS[0], C2.RIFLE_POS[1], -C2.CABIN_HZ + 0.24), 'RIFLE'))
                if not self.has_knife:
                    kx, kz = self.knife_spot()
                    out.append(((kx, C2.CABIN_Y + 0.8, kz), 'KNIFE'))
                if self.bait_pos is None and not self.owns('bait'):
                    out.append(((C2.BAIT_SPOT[0], C2.CABIN_Y + 0.5, C2.BAIT_SPOT[1]), 'BAIT'))
                elif self.bait_pos is not None:
                    bx, bz = self.bait_pos
                    out.append(((bx, float(C2.terrain_h2(bx, bz)) + 0.4, bz), 'BAIT'))
                if ph == 'hunt' and self.deer is not None:
                    out.append(((self.deer.x, self.deer.y + 1.2, self.deer.z), 'DEER'))
            elif ph == 'run':
                import chapter2 as C2
                out.append(((0.0, C2.CABIN_Y + 1.5, C2.CABIN_HZ), 'CABIN'))
        elif ch == 3:
            lv = self.lv
            for lev in lv.levers:
                if not lev['pulled']:
                    out.append((lev['pos'], 'LEVER'))
            if lv is self.lv_up and lv.elevator:
                x, z = lv.center(*lv.elevator)
                out.append(((x, lv.y0 + 1.5, z), 'ELEVATOR'))
            if lv is self.lv_low:
                if not self.cart_done:
                    x, z = self.cart_pos()
                    out.append(((x, lv.y0 + 1.0, z), 'MINECART'))
                x, z = lv.center(*lv.exit)
                out.append(((x, lv.y0 + 1.5, z), 'WAY OUT'))
        elif ch == 4:
            lv = self.lv4
            for g in lv.generators:
                if not g['running']:
                    out.append((g['pos'], 'GENERATOR'))
            for fu in lv.fuses:
                if not fu['taken']:
                    out.append((fu['pos'], 'FUSE'))
            if lv.fusebox:
                out.append((lv.fusebox['pos'], 'FUSE BOX'))
        elif ch == 5:
            import chapter5 as C5
            if not self.has_shotgun:
                out.append((C5.SHOTGUN_POS, 'SHOTGUN'))
            if self.c5_phase == 'drain':
                for pa in self.c5_papers:
                    if pa['digit'] not in self.c5_digits:
                        out.append((pa['pos'], 'PAPER'))
                if not self.door5_opening:
                    out.append((self.w5.fac.keypad, 'KEYPAD'))
                for s in self.c5_switches:
                    if not s['on']:
                        out.append((s['pos'], 'SWITCH %d' % (s['machine'] + 1)))
                if not self.key5:
                    out.append((self.key5_pos, 'KEY'))
                if not self.button5:
                    out.append(((C5.BUTTON[0], C5.BUTTON[1], C5.BUTTON[2]), 'BUTTON' if self.booth5_opening else 'BOOTH'))
        return out

    def draw_admin_marks(self):
        if not self.is_admin or self.state not in ('play', 'pause', 'note') or not (self.mark_mon or self.mark_puz):
            return
        marks = self.admin_marks()
        if not marks:
            return
        p = self.player
        cam = p.eye()
        fx, fy, fz = p.fwd()
        hl = math.hypot(fx, fz) or 1.0
        rx, rz = -fz / hl, fx / hl
        ux, uy, uz = -rz * fy, rz * fx - rx * fz, rx * fy
        th = math.tan(math.radians(self.settings['fov']) / 2)
        aspect = self.UW / float(self.UH)
        used = []

        def place(rc):
            # nudge a label up until it doesn't cover one already drawn
            for _ in range(12):
                if not any(rc.colliderect(u) for u in used):
                    break
                rc = rc.move(0, -(rc.height + 1))
            used.append(rc)
            return rc
        marks = sorted(marks, key=lambda m: (m[0][0] - cam[0]) ** 2 + (m[0][1] - cam[1]) ** 2 + (m[0][2] - cam[2]) ** 2)
        for (x, y, z), label, col in marks:
            dx, dy, dz = x - cam[0], y - cam[1], z - cam[2]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            depth = dx * fx + dy * fy + dz * fz
            if depth > 0.3:
                sx = (dx * rx + dz * rz) / (depth * th * aspect)
                sy = (dx * ux + dy * uy + dz * uz) / (depth * th)
                if abs(sx) <= 1.0 and abs(sy) <= 1.0:
                    px, py = int((1 + sx) * 0.5 * self.UW), int((1 - sy) * 0.5 * self.UH)
                    pygame.draw.polygon(self.ui, col + (230,), [(px, py - 7), (px + 6, py), (px, py + 7), (px - 6, py)], 2)
                    txt = '%s  %dm' % (label, dist)
                    w_, h_ = self.f_small.size(txt)
                    rc = place(pygame.Rect(px - w_ // 2, py - 10 - h_, w_, h_))
                    if rc.bottom < py - 10:
                        pygame.draw.line(self.ui, col + (120,), (px, py - 8), (px, rc.bottom), 1)
                    self.blit_text(txt, self.f_small, col, rc.midbottom, 'midbottom')
                    continue
            # off screen: an arrow at the edge pointing the way
            ang = math.atan2(dx * rx + dz * rz, depth if depth > 0 else -1e-3)
            if depth <= 0:
                ang = math.copysign(math.pi - abs(ang) * 0.0, ang) if abs(ang) > 0.01 else math.pi
            ex = self.UW / 2 + math.sin(ang) * (self.UW / 2 - 26)
            ey = self.UH / 2 - math.cos(ang) * (self.UH / 2 - 26)
            ex, ey = int(max(20, min(self.UW - 20, ex))), int(max(20, min(self.UH - 20, ey)))
            pygame.draw.circle(self.ui, col + (200,), (ex, ey), 4)
            txt = '%s %dm' % (label, dist)
            w_, h_ = self.f_small.size(txt)
            rc = place(pygame.Rect(ex - w_ // 2, ey + 6, w_, h_))
            self.blit_text(txt, self.f_small, col, rc.midtop, 'midtop', alpha=170)

    def draw_admin_ui(self):
        rows = self.admin_rows()
        panel = rows[0].unionall(rows).inflate(40, 80).move(0, -18)
        pygame.draw.rect(self.ui, (0, 0, 0, 220), panel)
        pygame.draw.rect(self.ui, (150, 30, 25, 255), panel, 1)
        self.blit_text("ADMIN", self.f_small, (210, 60, 50), (panel.centerx, panel.top + 12), 'midtop')
        for i, (it, rc) in enumerate(zip(self.ADMIN_ITEMS, rows)):
            sel = i == self.admin_sel
            if sel:
                pygame.draw.rect(self.ui, (90, 20, 16, 200), rc)
            self.blit_text(it, self.f_small, (240, 230, 220) if sel else (160, 155, 148), (rc.x + 10, rc.y + 6))
        if self.admin_msg_t > 0:
            self.blit_text(getattr(self, 'admin_note', '') or "all chapters unlocked", self.f_small, (120, 200, 120),
                           (panel.centerx, panel.bottom + 8), 'midtop')
        self.blit_text("arrows / tap the number to pick a chapter", self.f_small, (110, 105, 100),
                       (panel.centerx, panel.bottom + 26), 'midtop')

    # ================================================================== settings, in tabs
    def settings_tab_rows(self):
        from game import SETTINGS_ITEMS
        have = {it[0] for it in SETTINGS_ITEMS}
        return [k for k in SETTING_TABS[self.settings_tab][1] if k.startswith('@') or k in have]

    def settings_rows(self):
        """Rect 0 is the tab bar; then one per row; the last is BACK."""
        rows = [pygame.Rect(self.UW // 2 - 300, 100, 600, 34)]
        y = 152
        for i in range(len(self.settings_tab_rows()) + 1):
            rows.append(pygame.Rect(self.UW // 2 - 300, y + i * 34 - 4, 600, 30))
        return rows

    def tab_rects(self):
        bar = pygame.Rect(self.UW // 2 - 300, 100, 600, 34)
        w = bar.width // len(SETTING_TABS)
        return [pygame.Rect(bar.x + i * w, bar.y, w, bar.height) for i in range(len(SETTING_TABS))]

    def change_key(self, key, d):
        from game import SETTINGS_ITEMS
        it = next(i for i in SETTINGS_ITEMS if i[0] == key)
        _, label, kind, rng = it
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

    def settings_activate(self, key, d=1):
        if key == '@delete':
            if self.delete_arm_t > 0:
                self.progress.clear()
                self.save_prog()
                self.delete_arm_t = 0.0
                self.settings_note = "Save data deleted."
                self.settings_note_t = 3.0
                self.audio.play('clunk', 0.6)
            else:
                self.delete_arm_t = 4.0
                self.audio.play('click', 0.5)
        elif key == '@logout':
            if self.acct:
                self.log_out()
            else:
                self.to_title()
                self.account_start()
        elif key.startswith('@'):
            pass
        else:
            self.change_key(key, d)

    def settings_switch_tab(self, d):
        self.settings_tab = (self.settings_tab + d) % len(SETTING_TABS)
        self.delete_arm_t = 0.0
        self.audio.play('click', 0.4)

    def settings_event(self, ev):
        keys = self.settings_tab_rows()
        n = len(keys)
        last = n + 1                       # BACK
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self.leave_settings()
            elif ev.key == pygame.K_TAB:
                self.settings_switch_tab(1)
            elif ev.key in (pygame.K_UP, pygame.K_w):
                self.settings_sel = (self.settings_sel - 1) % (n + 2)
            elif ev.key in (pygame.K_DOWN, pygame.K_s):
                self.settings_sel = (self.settings_sel + 1) % (n + 2)
            elif ev.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                d = 1 if ev.key in (pygame.K_RIGHT, pygame.K_d) else -1
                if self.settings_sel == 0:
                    self.settings_switch_tab(d)
                elif 1 <= self.settings_sel <= n and not keys[self.settings_sel - 1].startswith('@'):
                    self.change_key(keys[self.settings_sel - 1], d)
            elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.settings_sel == last:
                    self.leave_settings()
                elif self.settings_sel == 0:
                    self.settings_switch_tab(1)
                else:
                    self.settings_activate(keys[self.settings_sel - 1])
        elif ev.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            ux, uy = self.ui_mouse()
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for i, rc in enumerate(self.tab_rects()):
                    if rc.collidepoint(ux, uy):
                        if i != self.settings_tab:
                            self.settings_tab = i
                            self.delete_arm_t = 0.0
                            self.audio.play('click', 0.4)
                        self.settings_sel = 0
                        return
            for i, rc in enumerate(self.settings_rows()):
                if i == 0 or not rc.collidepoint(ux, uy):
                    continue
                self.settings_sel = i
                if ev.type != pygame.MOUSEBUTTONDOWN:
                    continue
                if i == last:
                    if ev.button == 1:
                        self.leave_settings()
                elif ev.button in (1, 4):
                    self.settings_activate(keys[i - 1], 1)
                elif ev.button in (3, 5):
                    self.settings_activate(keys[i - 1], -1)

    def draw_settings_ui(self):
        from game import SETTINGS_ITEMS
        ui = self.ui
        ui.fill((0, 0, 0, 170))
        self.blit_text("SETTINGS", self.f_big, (200, 190, 180), (self.UW // 2, 30), 'midtop')
        for i, rc in enumerate(self.tab_rects()):
            on = i == self.settings_tab
            if on:
                pygame.draw.rect(ui, (80, 10, 10, 170), rc)
            if self.settings_sel == 0 and on:
                pygame.draw.rect(ui, (200, 50, 38, 255), rc, 2)
            pygame.draw.line(ui, (90, 80, 75, 255), (rc.x, rc.bottom), (rc.right, rc.bottom), 1)
            self.blit_text(SETTING_TABS[i][0], self.f_hud, (235, 225, 215) if on else (140, 134, 128),
                           (rc.centerx, rc.y + 8), 'midtop')
        keys = self.settings_tab_rows()
        rows = self.settings_rows()
        info = {it[0]: it for it in SETTINGS_ITEMS}
        for i, key in enumerate(keys):
            rc = rows[i + 1]
            sel = self.settings_sel == i + 1
            if sel:
                pygame.draw.rect(ui, (80, 10, 10, 150), rc)
            col = (230, 220, 210) if sel else (160, 155, 150)
            if key == '@delete':
                armed = self.delete_arm_t > 0
                self.blit_text("PRESS AGAIN TO DELETE ALL SAVE DATA" if armed else "DELETE SAVE DATA", self.f_hud,
                               (235, 90, 70) if armed else col, (rc.x + 14, rc.y + 6))
                continue
            if key == '@who':
                if self.acct:
                    t = "Logged in as %s%s%s" % (self.acct['user'], "  -  ADMIN" if self.is_admin else '', self.cloud_label())
                else:
                    t = "Playing as a guest"
                self.blit_text(t, self.f_hud, col, (rc.x + 14, rc.y + 6))
                continue
            if key == '@logout':
                self.blit_text("LOG OUT" if self.acct else "LOG IN / CREATE ACCOUNT", self.f_hud, col, (rc.x + 14, rc.y + 6))
                continue
            _, label, kind, rng = info[key]
            v = self.settings[key]
            if kind == 'bool':
                vs = "ON" if v else "OFF"
            elif kind == 'float':
                vs = "%.1f" % v
            elif kind == 'int':
                vs = ("%d%%" % v) if key == 'volume' else str(v)
            else:
                vs = str(v)
            self.blit_text(label, self.f_hud, col, (rc.x + 14, rc.y + 6))
            self.blit_text("<  %s  >" % vs if sel else vs, self.f_hud, col, (rc.right - 14, rc.y + 6), 'topright')
        rc = rows[-1]
        sel = self.settings_sel == len(keys) + 1
        if sel:
            pygame.draw.rect(ui, (80, 10, 10, 150), rc)
        self.blit_text("BACK", self.f_hud, (230, 220, 210) if sel else (160, 155, 150), (rc.centerx, rc.y + 6), 'midtop')
        if self.settings_note_t > 0:
            self.blit_text(self.settings_note, self.f_hud, (120, 200, 120), (self.UW // 2, rc.bottom + 14), 'midtop')
        self.blit_text("Tab: next tab  -  arrows / mouse to change  -  ESC: back",
                       self.f_small, (120, 115, 110), (self.UW // 2, self.UH - 34), 'midtop')
