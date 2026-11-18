"""The Elk: white, crawling, as tall on all fours as the Goat Man standing.

First appears at the end of Chapter Two. Design and preview renderer live in
concepts/chapter3_elk/.
"""
import math

from engine import MeshBuilder, T, S, RX, RY, RZ
from textures import L, EMIS

ELK_SCALE = 1.19     # hump at 3.76 m: the Goat Man's standing height


def _cube(layer, col=(1, 1, 1)):
    b = MeshBuilder()
    b.box((0, 0, 0), (1, 1, 1), layer, col, uvscale=1.0)
    return b.array()


def elk_meshes():
    return {
        'wfur': _cube(L.WFUR),
        'wfurb': _cube(L.WFUR_B),
        'wskin': _cube(L.SKIN, (0.92, 0.9, 0.88)),
        'ebone': _cube(L.BONE, (0.78, 0.74, 0.66)),
        'antler': _cube(L.BONE, (0.5, 0.45, 0.36)),
        'muscle': _cube(L.SKIN, (0.75, 0.12, 0.1)),
        'redeye': _cube(L.GLOW + EMIS, (1.0, 0.06, 0.03)),
        'glint': _cube(L.GLOW + EMIS, (0.55, 0.55, 0.6)),
    }


def pose_elk(x, y, z, yaw, phase=0.0, amt=0.0, jaw=0.4, split=0.5, head_pitch=0.0, head_roll=0.0, t=0.0,
             scale=ELK_SCALE, pitch=1.2, arms=None, hands=None, neck_a=0.35):
    """Always on all fours: elk hind legs, long pale human arms splayed like a spider's.
    pitch < 1.2 rears it up. arms = {side: (swing, splay, elbow_out, elbow_bend)} poses an arm by hand
    (side -1 or 1); hands, a dict, gets each palm's matrix. Returns (parts, head_matrix)."""
    p = []
    add = p.append
    M0 = T(x, y, z) @ RY(yaw) @ S(scale)
    H = 2.0
    # ---- elk hind legs, reversed hocks, split hooves
    for side in (-1, 1):
        ph = phase + (0.0 if side < 0 else math.pi)
        sw = math.sin(ph) * 0.35 * amt
        hip = M0 @ T(side * 0.3, H, -0.1) @ RX(-0.55 - sw)
        add(('wfur', hip @ T(0, -0.52, 0) @ S(0.34, 1.08, 0.38)))
        knee = hip @ T(0, -1.04, 0) @ RX(1.25 + 0.3 * amt * max(0.0, math.cos(ph)))
        add(('wfur', knee @ T(0, -0.5, 0) @ S(0.17, 1.02, 0.19)))
        ank = knee @ T(0, -1.0, 0) @ RX(-0.72)
        add(('wskin', ank @ T(0, -0.22, 0) @ S(0.09, 0.46, 0.1)))
        add(('wfur', ank @ T(0, -0.42, 0) @ S(0.15, 0.12, 0.15)))
        for toe in (-1, 1):
            add(('black', ank @ T(toe * 0.045, -0.53, 0.06) @ RY(toe * 0.15) @ S(0.08, 0.13, 0.26)))
    # ---- torso, pitched almost flat
    tor = M0 @ T(0, H, 0) @ RX(pitch)
    add(('wfur', tor @ T(0, 0.12, 0) @ S(0.62, 0.44, 0.56)))
    add(('wskin', tor @ T(0, 0.62, 0.05) @ S(0.36, 0.62, 0.3)))
    for k in range(5):
        add(('ebone', tor @ T(0, 0.42 + k * 0.1, 0.16) @ S(0.34 - 0.02 * abs(k - 2), 0.025, 0.03)))
    add(('wfurb', tor @ T(0, 1.3, 0.04) @ S(0.86, 0.9, 0.74)))
    add(('wfur', tor @ T(0, 1.82, -0.12) @ S(0.7, 0.5, 0.66)))
    add(('muscle', tor @ T(-0.432, 1.22, 0.02) @ S(0.01, 0.62, 0.52)))
    for k in range(6):
        add(('ebone', tor @ T(-0.445, 0.98 + k * 0.095, 0.02) @ RX(0.2) @ S(0.025, 0.03, 0.5)))
    add(('gore', tor @ T(-0.44, 0.86, 0.05) @ S(0.012, 0.18, 0.4)))
    for k in range(11):
        ln = 0.12 + 0.16 * math.sin(k * 0.6 + 0.4) ** 2
        sp = tor @ T(0, 0.15 + k * 0.19, -0.3 - 0.06 * math.sin(k * 0.45)) @ RX(-1.0)
        add(('ebone', sp @ T(0, ln / 2, 0) @ S(0.06, ln, 0.06)))
    for i in range(12):
        px = -0.36 + i * 0.066
        ln = 0.3 + 0.18 * ((i * 5) % 3)
        sw = 0.1 * math.sin(t * 1.9 + i) + 0.2 * amt * math.sin(phase * 2 + i)
        m = tor @ T(px, 0.95 + 0.06 * (i % 4), 0.38) @ RX(-pitch + sw)
        add(('wfurb' if i % 4 == 0 else 'wfur', m @ T(0, -ln / 2, 0) @ S(0.07, ln, 0.03)))
    # ---- long pale human arms, elbows splayed out like a spider, hands planted
    for side in (-1, 1):
        ph = phase + (math.pi if side < 0 else 0.0)
        sw = math.sin(ph) * 0.45 * amt
        a_ = (arms or {}).get(side)
        if a_ is None:
            a_ = (-0.45 - sw, 0.55, 0.9, -0.25 + 0.3 * amt * max(0.0, math.cos(ph)))
        sh = tor @ T(side * 0.48, 1.72, 0.1) @ RX(-pitch + a_[0]) @ RZ(side * a_[1])
        add(('wfur', sh @ T(0, -0.2, 0) @ S(0.24, 0.42, 0.24)))
        add(('wskin', sh @ T(0, -0.68, 0) @ S(0.13, 1.36, 0.13)))
        el = sh @ T(0, -1.36, 0) @ RZ(-side * a_[2]) @ RX(a_[3])
        add(('wskin', el @ T(0, -0.72, 0) @ S(0.1, 1.44, 0.1)))
        hand = el @ T(0, -1.44, 0) @ RX(0.5)
        if hands is not None:
            hands[side] = hand @ T(0, -0.3, 0)
        add(('wskin', hand @ T(0, -0.1, 0) @ S(0.2, 0.2, 0.07)))
        for f in (-2, -1, 0, 1, 2):
            fm = hand @ T(f * 0.045, -0.2, 0) @ RZ(f * 0.22) @ RX(-0.25)
            add(('wskin', fm @ T(0, -0.16, 0) @ S(0.03, 0.32, 0.03)))
            j2 = fm @ T(0, -0.32, 0) @ RX(-0.5)
            add(('wskin', j2 @ T(0, -0.13, 0) @ S(0.026, 0.26, 0.026)))
            add(('black', j2 @ T(0, -0.3, 0.008) @ S(0.022, 0.1, 0.02)))
    # ---- long neck, mane, and a row of eyes down each side
    neck = tor @ T(0, 1.95, 0.22) @ RX(neck_a)
    add(('wfur', neck @ T(0, 0.6, 0) @ S(0.34, 1.25, 0.36)))
    for i in range(10):
        ln = 0.4 + 0.2 * (i % 3)
        add(('wfurb' if i % 3 == 0 else 'wfur', neck @ T(0, 0.15 + i * 0.11, 0.17) @ RX(-neck_a - pitch + 0.1 * math.sin(t + i))
             @ T(0, -ln / 2, 0) @ S(0.09, ln, 0.03)))
    for side in (-1, 1):
        for i in range(5):
            ey = neck @ T(side * 0.176, 0.3 + i * 0.2, 0.04 + 0.02 * math.sin(i * 2.1)) @ RZ(side * 0.15 * i)
            sz = 0.07 - 0.008 * i
            add(('black', ey @ S(0.02, sz, sz * 1.2)))
            add(('glint', ey @ T(side * 0.011, sz * 0.2, sz * 0.25) @ S(0.004, 0.012, 0.012)))
    # ---- the head: the face skinned, the jaw split in two
    head = neck @ T(0, 1.24, 0.02) @ RX(-neck_a - pitch + 0.35 + head_pitch) @ RZ(head_roll) @ S(1.35)
    add(('wfur', head @ T(0, 0.12, -0.05) @ S(0.36, 0.34, 0.4)))
    add(('wfur', head @ T(0, 0.2, 0.14) @ S(0.3, 0.14, 0.26)))
    muz = head @ T(0, 0.04, 0.22) @ RX(0.25)
    add(('ebone', muz @ T(0, 0.02, 0.32) @ S(0.22, 0.18, 0.62)))
    for side in (-1, 1):
        add(('muscle', muz @ T(side * 0.112, 0.0, 0.18) @ S(0.012, 0.16, 0.36)))
        add(('gore', muz @ T(side * 0.114, 0.06, 0.38) @ S(0.012, 0.05, 0.3)))
    add(('black', muz @ T(0, 0.09, 0.5) @ S(0.12, 0.04, 0.2)))
    add(('black', muz @ T(0, 0.0, 0.632) @ S(0.13, 0.11, 0.01)))
    for side in (-1, 1):
        for k in range(9):
            add(('teeth', muz @ T(side * 0.09, -0.1, 0.06 + k * 0.064) @ S(0.018, 0.09, 0.018)))
    for side in (-1, 1):
        jm = head @ T(side * 0.05, -0.1, 0.2) @ RX(0.35 + jaw) @ RY(side * 0.12 * split) @ RZ(side * 0.75 * split)
        add(('ebone', jm @ T(0, 0, 0.32) @ S(0.075, 0.06, 0.62)))
        add(('muscle', jm @ T(-side * 0.02, 0.03, 0.3) @ S(0.03, 0.02, 0.56)))
        for k in range(9):
            add(('teeth', jm @ T(0.0, 0.07, 0.08 + k * 0.062) @ RZ(-side * 0.2) @ S(0.016, 0.1, 0.016)))
        for k in range(2):
            add(('gore', jm @ T(0, -0.05, 0.25 + k * 0.25) @ T(0, -0.15, 0) @ S(0.012, 0.3 + 0.1 * k, 0.012)))
    tg = head @ T(0, -0.08, 0.3) @ RX(0.55 + jaw * 0.8)
    for k in range(5):
        add(('muscle', tg @ T(0, 0, 0.12) @ S(0.07, 0.025, 0.24)))
        tg = tg @ T(0, 0, 0.22) @ RX(0.32)
    for side in (-1, 1):
        add(('black', head @ T(side * 0.17, 0.15, 0.17) @ S(0.06, 0.1, 0.13)))
        add(('redeye', head @ T(side * 0.2, 0.15, 0.18) @ S(0.008, 0.016, 0.016)))
        add(('wfur', head @ T(side * 0.24, 0.26, -0.06) @ RZ(-side * 0.7) @ S(0.24, 0.06, 0.12)))
    # ---- enormous antlers swept back, skin hanging off the tines
    for side in (-1, 1):
        m = head @ T(side * 0.12, 0.3, -0.04) @ RZ(-side * 0.55) @ RX(-0.55)
        w = 0.1
        for i in range(10):
            seg = 0.24
            add(('antler', m @ T(0, seg / 2, 0) @ S(w, seg + 0.03, w)))
            m = m @ T(0, seg, 0) @ RX(0.07) @ RZ(side * 0.06)
            w *= 0.93
            if i in (1, 3, 5, 6, 7, 8):
                ln = (0.95, 0.85, 0.7, 0.6, 0.48, 0.38)[(1, 3, 5, 6, 7, 8).index(i)]
                tm = m @ RX(0.95 + 0.05 * i) @ RZ(-side * 0.15)
                add(('antler', tm @ T(0, ln / 2, 0) @ S(w * 0.7, ln, w * 0.7)))
                tip = tm @ T(0, ln, 0) @ RX(0.4)
                add(('antler', tip @ T(0, 0.08, 0) @ S(w * 0.45, 0.16, w * 0.45)))
                if i in (3, 6):
                    add(('gore', tm @ T(0.02, ln * 0.55, 0) @ RX(-0.95) @ T(0, -0.22, 0) @ S(0.012, 0.44, 0.05)))
        bt = head @ T(side * 0.12, 0.3, 0.02) @ RZ(-side * 0.35) @ RX(1.05)
        add(('antler', bt @ T(0, 0.3, 0) @ S(0.06, 0.6, 0.06)))
    return p, head
