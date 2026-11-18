"""The backpack: two hands, a head, and a bag. Mixed into game.Game.

[Tab] opens it. Click and drag (or tap an item, then tap where it goes) to move
things between the bag, your left and right hands, and your head.

  lantern   one hand    the light ([F] on/off)
  revolver  one hand    six shots; stuns what it hits (you can't kill them -- only The Beast and the Herd)
  knife     one hand
  rifle     two hands   [Right mouse] scope
  shotgun   two hands
  headlamp  head        a light that leaves both hands free

Whatever you carry at the end of a chapter comes with you into the next one,
and is saved as that chapter's starting kit.
"""
import math

import pygame

from engine import MeshBuilder, T, S, RX, RY, RZ
from textures import L, EMIS

ITEMS = {
    'lantern': {'name': "LANTERN", 'hands': 1, 'desc': "Light. [F] turns it on and off."},
    'revolver': {'name': "REVOLVER", 'hands': 1, 'desc': "Six shots. It won't kill them -- it scares them off."},
    'knife': {'name': "KNIFE", 'hands': 1, 'desc': "For butchering."},
    'rifle': {'name': "HUNTING RIFLE", 'hands': 2, 'desc': "Two hands. [Right mouse] to look down the scope."},
    'shotgun': {'name': "SHOTGUN", 'hands': 2, 'desc': "Two hands. Six shells. [R] reloads."},
    'headlamp': {'name': "HEADLAMP", 'hands': 0, 'head': True, 'desc': "Wear it. Light, and both hands free."},
}
BAG = 8
REV_ROUNDS = 6
STUN_T = 1.8          # frozen
SCARE_T = 7.0         # then it goes off somewhere else and forgets you
MENUS = ('title', 'chapters', 'settings', 'update', 'coop', 'coopname', 'coopjoin', 'lobby', 'login', 'ending')


# what you no longer have from a chapter on: the knife stays by the deer in Chapter Two,
# and the Elk takes both guns at the end of Chapter Three
LOST_FROM = {3: ('knife',), 4: ('knife', 'rifle', 'revolver')}


def default_kit(ch):
    inv = {'left': 'lantern', 'right': None, 'head': None, 'bag': [None] * BAG}
    inv['bag'][0] = 'revolver'
    if ch >= 3:
        inv['bag'][1] = 'rifle'
        inv['bag'][2] = 'knife'
    return strip_lost(inv, ch)


def strip_lost(inv, ch):
    lost = LOST_FROM.get(min(ch, 4)) if ch >= 3 else None
    if inv is None or not lost:
        return inv
    for k in ('left', 'right', 'head'):
        if inv[k] in lost:
            inv[k] = None
    inv['bag'] = [None if i in lost else i for i in inv['bag']]
    if inv['left'] is None and inv['right'] is None and 'lantern' in inv['bag']:
        inv['bag'][inv['bag'].index('lantern')] = None
        inv['left'] = 'lantern'
    return inv


def clean(inv):
    """A saved kit, made safe to use."""
    try:
        out = {'left': inv.get('left'), 'right': inv.get('right'), 'head': inv.get('head'),
               'bag': list(inv.get('bag') or [])[:BAG]}
    except AttributeError:
        return None
    out['bag'] += [None] * (BAG - len(out['bag']))
    for k in ('left', 'right', 'head'):
        if out[k] not in ITEMS:
            out[k] = None
    out['bag'] = [i if i in ITEMS else None for i in out['bag']]
    return out


# ---------------------------------------------------------------------- meshes
def revolver_mesh():
    """A revolver pointing down +z, origin at the grip."""
    b = MeshBuilder()
    steel, dark, wood = (0.45, 0.45, 0.48), (0.2, 0.2, 0.22), (0.5, 0.3, 0.18)
    b.box((0, 0.0, -0.02), (0.035, 0.11, 0.05), L.WOOD, wood, m=RX(0.35))           # grip
    b.box((0, 0.06, 0.04), (0.04, 0.05, 0.08), L.METAL, dark)                        # frame
    b.cylinder(0.026, 0.026, 0.05, 8, L.METAL, steel, m=T(0, 0.07, 0.035) @ RX(math.pi / 2))   # cylinder
    b.cylinder(0.011, 0.011, 0.17, 6, L.METAL, steel, m=T(0, 0.082, 0.06) @ RX(math.pi / 2))  # barrel
    b.box((0, 0.1, 0.22), (0.006, 0.012, 0.01), L.METAL, dark)                       # sight
    b.box((0, 0.035, 0.035), (0.012, 0.03, 0.03), L.METAL, dark)                     # trigger guard
    return b.array()


def headlamp_mesh():
    b = MeshBuilder()
    b.cylinder(0.11, 0.11, 0.035, 12, L.CLOTH, (0.2, 0.2, 0.22))
    b.box((0, 0.02, 0.11), (0.06, 0.045, 0.04), L.METAL, (0.3, 0.3, 0.3))
    b.box((0, 0.02, 0.132), (0.04, 0.03, 0.006), L.GLOW + EMIS, (1.0, 0.95, 0.8))
    return b.array()


# ---------------------------------------------------------------------- the mixin
class InventoryMixin:
    # ---- the state, made on first use
    def _invd(self):
        inv = self.__dict__.get('inv')
        if inv is None:
            inv = default_kit(1)
            self.__dict__['inv'] = inv
        return inv

    def owns(self, item):
        inv = self._invd()
        return item in (inv['left'], inv['right'], inv['head']) or item in inv['bag']

    def holding(self, item):
        inv = self._invd()
        return item in (inv['left'], inv['right'])

    def hand_items(self):
        inv = self._invd()
        out = []
        for k in ('right', 'left'):
            if inv[k] and inv[k] not in out:
                out.append(inv[k])
        return out

    def held_gun(self):
        for g in ('shotgun', 'rifle', 'revolver'):
            if self.holding(g):
                return g
        return None

    def lantern_hand(self):
        inv = self._invd()
        if inv['left'] == 'lantern':
            return 'left'
        if inv['right'] == 'lantern':
            return 'right'
        return None

    def headlamp_on(self):
        return self._invd()['head'] == 'headlamp'

    def has_light(self):
        return self.lantern_hand() is not None or self.headlamp_on()

    def toggle_light(self):
        """[F]: the lantern (or the headlamp, if that's your only light) on or off, with its own sound."""
        self.flash_on = not self.flash_on
        on = self.__dict__.get('_flash', True)
        if self.lantern_hand() is None and self.headlamp_on():
            self.audio.play('headlamp', 0.7)
        else:
            self.audio.play('lantern_on' if on else 'lantern_off', 0.7)

    def inv_lose(self, *items):
        """Gone: out of your hands and your bag."""
        inv = self._invd()
        for k in ('left', 'right', 'head'):
            if inv[k] in items:
                inv[k] = None
        inv['bag'] = [None if i in items else i for i in inv['bag']]

    def give(self, item, hold=False):
        """Into the bag (or straight into your hands). Returns where it went."""
        inv = self._invd()
        if self.owns(item):
            return None
        if hold:
            if ITEMS[item].get('head'):
                if inv['head'] is None:
                    inv['head'] = item
                    return 'head'
            elif self.inv_put_hands(item, None):
                return 'hand'
        for i in range(BAG):
            if inv['bag'][i] is None:
                inv['bag'][i] = item
                return 'bag'
        # a full bag: it goes in your hands whatever you were holding
        if ITEMS[item].get('head'):
            inv['head'] = item
        else:
            self.inv_put_hands(item, None, force=True)
        return 'hand'

    def take_item(self, item):
        inv = self._invd()
        for k in ('left', 'right', 'head'):
            if inv[k] == item:
                inv[k] = None
        inv['bag'] = [None if i == item else i for i in inv['bag']]

    # the old flags, now asked of the bag
    @property
    def flash_on(self):
        return self.__dict__.get('_flash', True) and self.has_light()

    @flash_on.setter
    def flash_on(self, v):
        self.__dict__['_flash'] = bool(v)

    @property
    def has_rifle(self):
        return self.owns('rifle')

    @has_rifle.setter
    def has_rifle(self, v):
        if v:
            self.give('rifle')

    @property
    def has_knife(self):
        return self.owns('knife')

    @has_knife.setter
    def has_knife(self, v):
        if v:
            self.give('knife')

    @property
    def has_shotgun(self):
        return self.owns('shotgun')

    @has_shotgun.setter
    def has_shotgun(self, v):
        if v and not self.owns('shotgun'):
            # if you've no gun in your hands, it goes straight into them
            self.give('shotgun', hold=self.held_gun() is None)

    # ---- moving things about
    def _free_bag(self, exclude=()):
        inv = self._invd()
        return [i for i in range(BAG) if inv['bag'][i] is None and i not in exclude]

    def inv_put_hands(self, item, side, force=False, from_slot=None):
        """Put an item in your hands (side: 'left', 'right' or None for wherever). What was there goes
        to the bag. False if there isn't room in the bag for it."""
        inv = self._invd()
        two = ITEMS[item]['hands'] == 2
        if two:
            out = [x for x in {inv['left'], inv['right']} if x and x != item]
        else:
            if side is None:
                side = 'right' if inv['right'] is None else ('left' if inv['left'] is None else 'right')
            cur = inv[side]
            out = [cur] if cur and cur != item else []
            if cur and ITEMS[cur]['hands'] == 2:
                out = [cur]
        free = self._free_bag()
        if from_slot is not None and from_slot[0] == 'bag' and from_slot[1] not in free:
            free.append(from_slot[1])
        if len(out) > len(free) and not force:
            return False
        # clear where it came from
        if from_slot is not None:
            self._clear(from_slot)
        for k in ('left', 'right'):
            if inv[k] == item:
                inv[k] = None
        for x in out:
            for k in ('left', 'right'):
                if inv[k] == x:
                    inv[k] = None
            if free:
                inv['bag'][free.pop(0)] = x
        if two:
            inv['left'] = inv['right'] = item
        else:
            if inv[side] and ITEMS[inv[side]]['hands'] == 2:
                inv['left'] = inv['right'] = None
            inv[side] = item
        return True

    def _get(self, slot):
        inv = self._invd()
        return inv['bag'][slot[1]] if slot[0] == 'bag' else inv[slot[0]]

    def _clear(self, slot):
        inv = self._invd()
        it = self._get(slot)
        if slot[0] == 'bag':
            inv['bag'][slot[1]] = None
        elif slot[0] in ('left', 'right') and it and ITEMS[it]['hands'] == 2:
            inv['left'] = inv['right'] = None
        else:
            inv[slot[0]] = None

    def inv_move(self, src, dst):
        """Drag from one slot to another. True if anything moved."""
        if src == dst:
            return False
        inv = self._invd()
        item = self._get(src)
        if item is None:
            return False
        if src[0] in ('left', 'right') and dst[0] in ('left', 'right') and ITEMS[item]['hands'] == 2:
            return False
        there = self._get(dst)
        if dst[0] == 'head':
            if not ITEMS[item].get('head'):
                return False
            self._clear(src)
            inv['head'] = item
            if there:
                self._put_back(there, src)
            return True
        if dst[0] in ('left', 'right'):
            if ITEMS[item].get('head'):
                return False
            if src[0] in ('left', 'right') and there and ITEMS[there]['hands'] == 1:
                # swap hands
                inv[src[0]], inv[dst[0]] = there, item
                return True
            return self.inv_put_hands(item, dst[0], from_slot=src)
        # into the bag
        if there is None:
            self._clear(src)
            inv['bag'][dst[1]] = item
            return True
        # swap with what's in that bag slot
        if src[0] == 'bag':
            inv['bag'][src[1]], inv['bag'][dst[1]] = there, item
            return True
        if src[0] == 'head':
            if not ITEMS[there].get('head'):
                return False
            inv['head'], inv['bag'][dst[1]] = there, item
            return True
        # from a hand onto an occupied bag slot: try to put that thing in the hand instead
        if ITEMS[there].get('head'):
            return False
        self._clear(src)
        inv['bag'][dst[1]] = item
        if not self.inv_put_hands(there, src[0], from_slot=None):
            return False
        return True

    def _put_back(self, item, slot):
        inv = self._invd()
        if slot[0] == 'bag' and inv['bag'][slot[1]] is None:
            inv['bag'][slot[1]] = item
            return
        free = self._free_bag()
        if free:
            inv['bag'][free[0]] = item

    # ---- chapters: what you carry comes with you
    def inv_tick(self):
        st = self.state
        if st in MENUS:
            self.__dict__['inv_chapter'] = None
            self.inv_open = False
            return
        ch = self.chapter
        cur = self.__dict__.get('inv_chapter')
        if cur == ch:
            return
        saved = self.progress.setdefault('inv', {})
        if cur is not None and cur == ch - 1:
            # straight on from the last chapter: you keep what you had, and that's the new start
            snap = strip_lost(clean(self._invd()), ch)
            self.__dict__['inv'] = snap
            saved[str(ch)] = snap
            try:
                self.save_prog()
            except Exception:
                pass
        else:
            kit = clean(saved.get(str(ch)) or {}) if saved.get(str(ch)) else None
            self.__dict__['inv'] = strip_lost(kit, ch) or default_kit(ch)
        self.__dict__['inv_chapter'] = ch
        self.rev_ammo = REV_ROUNDS
        self.rev_reload_t = -1.0

    # ---- the screen
    def inv_layout(self):
        """Rects for every slot, in UI pixels."""
        W, H = self.UW, self.UH
        cs = max(52, min(92, int(H * 0.1)))
        gap = 10
        cx = W // 2
        top = int(H * 0.15)
        rects = {}
        rects[('head',)] = pygame.Rect(cx - cs // 2, top, cs, cs)
        rects[('left',)] = pygame.Rect(cx - cs * 2 - gap * 2, top + cs + gap * 2, int(cs * 1.4), int(cs * 1.4))
        rects[('right',)] = pygame.Rect(cx + cs - gap * 2 + gap * 3, top + cs + gap * 2, int(cs * 1.4), int(cs * 1.4))
        by = top + cs * 3 + gap * 4
        cols = 4
        bx0 = cx - (cols * cs + (cols - 1) * gap) // 2
        for i in range(BAG):
            r, c = divmod(i, cols)
            rects[('bag', i)] = pygame.Rect(bx0 + c * (cs + gap), by + r * (cs + gap), cs, cs)
        return rects

    def inv_close_rect(self):
        rects = self.inv_layout()
        bottom = rects[('bag', BAG - 1)].bottom
        rc = pygame.Rect(0, 0, 160, 38)
        rc.midtop = (self.UW // 2, min(bottom + 12, self.UH - 44))
        return rc

    def inv_slot_at(self, pos):
        for k, rc in self.inv_layout().items():
            if rc.collidepoint(pos):
                return k
        return None

    def inv_toggle(self):
        self.inv_open = not getattr(self, 'inv_open', False)
        self.inv_drag = None
        self.inv_pick = None
        self.audio.play('paper', 0.4)
        if self.inv_open:
            self.set_mouse(False)
        else:
            self.set_mouse(True)

    def inv_event(self, ev):
        """True if the event was the bag's."""
        if not getattr(self, 'inv_open', False):
            return False
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_TAB, pygame.K_ESCAPE, pygame.K_i):
                self.inv_toggle()
            elif ev.key == pygame.K_f:
                self.toggle_light()
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            pos = self.ui_mouse()
            if self.inv_close_rect().collidepoint(pos):
                self.inv_toggle()
                return True
            slot = self.inv_slot_at(pos)
            if self.inv_pick is not None:
                # tap-to-move: the second tap puts it down
                if slot is not None:
                    self._inv_do(self.inv_pick, slot)
                self.inv_pick = None
                return True
            if slot is not None and self._get(slot) is not None:
                self.inv_drag = slot
            return True
        if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            if self.inv_drag is None:
                return True
            slot = self.inv_slot_at(self.ui_mouse())
            src, self.inv_drag = self.inv_drag, None
            if slot is None:
                return True
            if slot == src:
                self.inv_pick = src          # a tap: pick it up, tap again where it goes
            else:
                self._inv_do(src, slot)
            return True
        if ev.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            return True
        return False

    def _inv_do(self, src, dst):
        if self.inv_move(src, dst):
            self.audio.play('click', 0.5)
            self.inv_msg = None
        else:
            self.audio.play('clunk', 0.4)
            it = self._get(src)
            if it and dst[0] == 'head':
                self.inv_msg = "That doesn't go on your head."
            elif it and ITEMS[it].get('head') and dst[0] in ('left', 'right'):
                self.inv_msg = "Wear it. Drag it to your head."
            else:
                self.inv_msg = "No room in the bag for what's in your hands."
            self.inv_msg_t = 2.5

    def draw_inventory(self):
        if not getattr(self, 'inv_open', False):
            return
        ui = self.ui
        W, H = self.UW, self.UH
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((6, 4, 4, 200))
        ui.blit(shade, (0, 0))
        self.blit_text("BACKPACK", self.f_hud, (210, 200, 188), (W // 2, int(H * 0.07)), 'midtop')
        self.blit_text("drag items between your bag, your hands and your head   (or tap one, then tap where it goes)",
                       self.f_small, (150, 142, 132), (W // 2, int(H * 0.07) + 40), 'midtop')
        rects = self.inv_layout()
        inv = self._invd()
        mpos = self.ui_mouse()
        hover = self.inv_slot_at(mpos)
        drag = getattr(self, 'inv_drag', None)
        pick = getattr(self, 'inv_pick', None)
        labels = {('head',): "HEAD", ('left',): "LEFT HAND", ('right',): "RIGHT HAND"}
        two = inv['left'] and inv['left'] == inv['right']
        for slot, rc in rects.items():
            sel = slot == hover or slot == pick
            pygame.draw.rect(ui, (40, 32, 30, 230) if not sel else (70, 48, 40, 240), rc, border_radius=6)
            pygame.draw.rect(ui, (150, 120, 100, 200) if not sel else (220, 70, 50, 255), rc, 2, border_radius=6)
            if slot in labels:
                self.blit_text(labels[slot], self.f_small, (170, 160, 150), (rc.centerx, rc.bottom + 4), 'midtop')
            it = self._get(slot)
            if it and slot not in (drag, pick):
                if two and slot == ('left',):
                    self.blit_text("(both hands)", self.f_small, (150, 140, 130), rc.center, 'center')
                    continue
                self.draw_item_icon(it, rc)
        # what you're dragging, under the pointer
        held = drag or pick
        if held is not None and self._get(held):
            rc = pygame.Rect(0, 0, 70, 70)
            rc.center = (int(mpos[0]), int(mpos[1]))
            self.draw_item_icon(self._get(held), rc)
        # the description of what's under the pointer
        it = self._get(hover) if hover else None
        if it:
            info = ITEMS[it]
            y0 = self.inv_close_rect().bottom + 8
            if y0 + 50 > H:
                y0 = rects[('head',)].top
                self.blit_text(info['name'], self.f_msg, (230, 215, 195), (W - 30, y0), 'topright')
                self.blit_text(info['desc'], self.f_small, (170, 160, 150), (W - 30, y0 + 30), 'topright')
            else:
                self.blit_text(info['name'], self.f_msg, (230, 215, 195), (W // 2, y0), 'midtop')
                self.blit_text(info['desc'], self.f_small, (170, 160, 150), (W // 2, y0 + 30), 'midtop')
        msg = getattr(self, 'inv_msg', None)
        if msg and getattr(self, 'inv_msg_t', 0) > 0:
            self.blit_text(msg, self.f_small, (230, 90, 70), (W // 2, int(H * 0.16)), 'midtop')
        rc = self.inv_close_rect()
        pygame.draw.rect(ui, (60, 40, 36, 230), rc, border_radius=6)
        pygame.draw.rect(ui, (170, 130, 110, 220), rc, 2, border_radius=6)
        self.blit_text("CLOSE  [Tab]", self.f_small, (215, 205, 190), rc.center, 'center')

    def draw_item_icon(self, it, rc):
        """A little drawing of each thing."""
        ui = self.ui
        cx, cy = rc.center
        s = rc.w / 80.0
        P = lambda x, y: (int(cx + x * s), int(cy + y * s))
        if it == 'lantern':
            pygame.draw.rect(ui, (60, 55, 50), (*P(-14, -18), int(28 * s), int(34 * s)), border_radius=3)
            pygame.draw.rect(ui, (250, 190, 90), (*P(-9, -12), int(18 * s), int(22 * s)))
            pygame.draw.arc(ui, (90, 85, 80), (*P(-12, -32), int(24 * s), int(24 * s)), 0, math.pi, max(2, int(3 * s)))
        elif it == 'revolver':
            pygame.draw.rect(ui, (120, 120, 128), (*P(-20, -10), int(38 * s), int(8 * s)))
            pygame.draw.circle(ui, (90, 90, 96), P(-6, -5), int(9 * s))
            pygame.draw.polygon(ui, (110, 70, 40), [P(-22, -4), P(-12, -4), P(-16, 18), P(-26, 16)])
        elif it == 'rifle':
            pygame.draw.line(ui, (90, 90, 96), P(-34, 0), P(34, -8), max(3, int(4 * s)))
            pygame.draw.polygon(ui, (130, 85, 50), [P(-34, -2), P(-6, -5), P(-4, 4), P(-36, 10)])
            pygame.draw.rect(ui, (40, 40, 44), (*P(-2, -16), int(20 * s), int(6 * s)))
        elif it == 'shotgun':
            pygame.draw.line(ui, (70, 70, 76), P(-34, 0), P(34, -6), max(4, int(6 * s)))
            pygame.draw.polygon(ui, (110, 70, 40), [P(-34, -3), P(-12, -5), P(-10, 6), P(-36, 12)])
            pygame.draw.rect(ui, (110, 70, 40), (*P(4, -6), int(14 * s), int(8 * s)))
        elif it == 'knife':
            pygame.draw.polygon(ui, (200, 200, 205), [P(-4, -26), P(4, -20), P(3, 6), P(-3, 6)])
            pygame.draw.rect(ui, (80, 50, 30), (*P(-4, 6), int(8 * s), int(18 * s)))
        elif it == 'headlamp':
            pygame.draw.ellipse(ui, (50, 50, 55), (*P(-26, -10), int(52 * s), int(22 * s)), max(3, int(4 * s)))
            pygame.draw.rect(ui, (90, 90, 95), (*P(-9, -6), int(18 * s), int(14 * s)))
            pygame.draw.circle(ui, (255, 245, 210), P(0, 1), int(5 * s))

    # ---- held things, drawn in the world
    def held_pos(self, cam, yaw, pitch, side, fwd=0.5, down=0.28):
        """Where your left (side -1) or right (+1) hand is."""
        rx, rz = -math.cos(yaw), math.sin(yaw)
        fx, fz = math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch)
        return (cam[0] + rx * 0.22 * side + fx * fwd, cam[1] - down + math.sin(pitch) * fwd, cam[2] + rz * 0.22 * side + fz * fwd)

    def draw_hand_items(self, r, cam, yaw, pitch):
        """Everything in your hands except the lantern (each chapter draws that), the Ch2 rifle and the
        Ch5 shotgun (those chapters draw their own, with the scope and the pump)."""
        inv = self._invd()
        kick = getattr(self, 'gun_kick', 0.0)
        for side_name, side in (('right', 1), ('left', -1)):
            it = inv[side_name]
            if not it or it == 'lantern':
                continue
            if ITEMS[it]['hands'] == 2 and side_name == 'left':
                continue
            if (it == 'rifle' and self.chapter == 2) or (it == 'shotgun' and self.chapter == 5):
                continue
            if it == 'revolver':
                p = self.held_pos(cam, yaw, pitch, side, 0.42, 0.22)
                rl = 0.0
                if getattr(self, 'rev_reload_t', -1) >= 0:
                    rl = math.sin(min(1.0, self.rev_reload_t / 1.6) * math.pi)
                M = T(*p) @ RY(yaw) @ RX(-pitch - 0.35 * kick - 0.6 * rl) @ RZ(0.6 * rl * side)
                r.draw(self.m_revolver, model=M)
                if getattr(self, 'muzzle_t', 0) > 0 and getattr(self, 'muzzle_gun', '') == 'revolver':
                    r.draw(self.m_flash, model=M @ T(0, 0.08, 0.3) @ S(0.5))
            elif it == 'knife':
                p = self.held_pos(cam, yaw, pitch, side, 0.42, 0.25)
                r.draw(self.m_knife, model=T(*p) @ RY(yaw) @ RX(-pitch + 1.2) @ RZ(0.3 * side))
            elif it in ('rifle', 'shotgun'):
                p = self.held_pos(cam, yaw, pitch, 0.9, 0.42, 0.24)
                M = T(*p) @ RY(yaw) @ RX(-pitch - 0.1 * kick)
                r.draw(self.m_rifle if it == 'rifle' else self.m_shotgun, model=M)
                if getattr(self, 'muzzle_t', 0) > 0:
                    r.draw(self.m_flash, model=M @ T(0, 0.025, 0.95 if it == 'rifle' else 0.88))

    def head_light_pos(self, cam, yaw, pitch):
        fx, fz = math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch)
        return (cam[0] + fx * 0.35, cam[1] + 0.12 + math.sin(pitch) * 0.35, cam[2] + fz * 0.35)
