"""Entry points the web page (web/mm.js) calls into.

    boot(w, h)          make the Game (fast: just the renderer and the UI)
    load_step()         one loading step; True once everything is built
    frame(dt, ev, w, h) input in, one update and one render out; returns what
                        the page should show (touch controls, text box...)
"""
import json

import pygame

G = None

_CODES = {
    'ArrowUp': pygame.K_UP, 'ArrowDown': pygame.K_DOWN, 'ArrowLeft': pygame.K_LEFT, 'ArrowRight': pygame.K_RIGHT,
    'ShiftLeft': pygame.K_LSHIFT, 'ShiftRight': pygame.K_RSHIFT, 'ControlLeft': pygame.K_LCTRL,
    'ControlRight': pygame.K_RCTRL, 'Space': pygame.K_SPACE, 'Enter': pygame.K_RETURN, 'NumpadEnter': pygame.K_KP_ENTER,
    'Escape': pygame.K_ESCAPE, 'Tab': pygame.K_TAB, 'Backspace': pygame.K_BACKSPACE, 'Backquote': pygame.K_BACKQUOTE,
}
for _c in 'abcdefghijklmnopqrstuvwxyz':
    _CODES['Key' + _c.upper()] = getattr(pygame, 'K_' + _c)
for _d in '0123456789':
    _CODES['Digit' + _d] = getattr(pygame, 'K_' + _d)


class WebKeys:
    """What pygame.key.get_pressed() would say."""

    def __init__(self):
        self.down = set()

    def __getitem__(self, k):
        return k in self.down


def boot(w, h):
    global G
    import game
    G = game.Game(web_size=(int(w), int(h)))
    return True


def load_step():
    try:
        next(G.loader)
        return False
    except StopIteration:
        G.web_keys = WebKeys()
        G.web_buttons = [False, False, False]
        G.web_mouse = (0, 0)
        G.account_start()
        return True


def _event(e):
    t = e.get('t')
    g = G
    if t in ('kd', 'ku'):
        code = _CODES.get(e.get('code', ''), 0)
        ch = e.get('key', '')
        uni = ch if len(ch) == 1 else ''
        if code == 0 and uni:
            code = _CODES.get('Key' + uni.upper(), 0)
        if t == 'kd':
            if code:
                g.web_keys.down.add(code)
            return pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, unicode=uni, scancode=0)
        g.web_keys.down.discard(code)
        return pygame.event.Event(pygame.KEYUP, key=code, mod=0, unicode='', scancode=0)
    if t == 'txt':
        return pygame.event.Event(pygame.KEYDOWN, key=0, mod=0, unicode=e.get('ch', ''), scancode=0)
    if t in ('md', 'mu', 'mm'):
        x, y = e.get('x', g.web_mouse[0]), e.get('y', g.web_mouse[1])
        g.web_mouse = (x, y)
        if t == 'mm':
            return pygame.event.Event(pygame.MOUSEMOTION, pos=(int(x), int(y)), rel=(e.get('dx', 0), e.get('dy', 0)),
                                      buttons=tuple(int(b) for b in g.web_buttons))
        b = int(e.get('b', 1))
        if 1 <= b <= 3:
            g.web_buttons[b - 1] = t == 'md'
        etype = pygame.MOUSEBUTTONDOWN if t == 'md' else pygame.MOUSEBUTTONUP
        return pygame.event.Event(etype, pos=(int(x), int(y)), button=b)
    if t == 'wh':
        # a drag or the wheel on a menu: dy is a fraction of the screen's height
        return pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=0, flipped=False, ui_dy=float(e.get('dy', 0)) * g.UH)
    if t == 'blur':
        g.web_keys.down.clear()
        g.web_buttons = [False, False, False]
        return pygame.event.Event(pygame.WINDOWFOCUSLOST)
    return None


def frame(dt, events, w, h):
    g = G
    w, h = int(w), int(h)
    if (w, h) != (g.win_w, g.win_h) and w > 50 and h > 50:
        g.web_resize(w, h)
    for e in json.loads(events) if events else ():
        ev = _event(e)
        if ev is not None:
            g.handle_event(ev)
    dt = min(max(float(dt), 0.0), 0.05)
    g.time += dt
    if dt > 0:
        g.clock.fps += ((1.0 / dt) - g.clock.fps) * 0.1
    g.update(dt)
    g.render()
    return g.web_mode()
