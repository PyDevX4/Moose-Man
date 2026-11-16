"""The Moose Man: model, animation and AI.  Also small dynamic meshes (valve, herd heads)."""
import math
import random

from engine import MeshBuilder, T, S, RX, RY, RZ
from textures import L, EMIS
from world import cell_of, cell_center, ROWS, COLS, OZ


def unit_cube(layer, col=(1, 1, 1)):
    b = MeshBuilder()
    b.box((0, 0, 0), (1, 1, 1), layer, col, uvscale=1.0)
    return b.array()


def moose_meshes():
    return {
        'fur': unit_cube(L.FUR),
        'bone': unit_cube(L.BONE, (0.74, 0.7, 0.62)),
        'black': unit_cube(L.BLACK),
        'eye': unit_cube(L.GLOW + EMIS, (0.9, 0.85, 0.6)),
        'skin': unit_cube(L.SKIN, (0.35, 0.3, 0.3)),
        'flesh': unit_cube(L.SKIN, (0.5, 0.45, 0.42)),
        'gore': unit_cube(L.SKIN, (0.24, 0.035, 0.03)),
        'rib': unit_cube(L.BONE, (0.58, 0.53, 0.44)),
        # the Goat Man
        'gfur': unit_cube(L.FUR, (0.62, 0.6, 0.58)),
        'gdark': unit_cube(L.FUR, (0.32, 0.3, 0.3)),
        'horn': unit_cube(L.BONE, (0.42, 0.37, 0.3)),
        'geye': unit_cube(L.GLOW + EMIS, (0.95, 0.7, 0.1)),
        # the car
        'carbody': unit_cube(L.METAL, (0.55, 0.6, 0.85)),
        'glass': unit_cube(L.METAL, (0.12, 0.14, 0.2)),
        'tire': unit_cube(L.BLACK),
        'chrome': unit_cube(L.METAL, (1.4, 1.4, 1.4)),
        'headl': unit_cube(L.GLOW + EMIS, (1.0, 0.95, 0.8)),
        'taill': unit_cube(L.GLOW + EMIS, (0.85, 0.05, 0.03)),
        'teeth': unit_cube(L.BONE, (0.8, 0.68, 0.42)),
        'eyewhite': unit_cube(L.GLOW + EMIS, (0.62, 0.6, 0.52)),
    }


def valve_mesh():
    b = MeshBuilder()
    # stem from wall
    b.cylinder(0.05, 0.05, 0.36, 8, L.METAL, m=RX(-math.pi / 2))
    b.box((0, 0, -0.32), (0.3, 0.3, 0.06), L.METAL, (0.7, 0.7, 0.7))
    return b.array()


def wheel_mesh():
    b = MeshBuilder()
    segs = 10
    r = 0.33
    rc = (0.85, 0.25, 0.15)
    for i in range(segs):
        a = i / segs * 2 * math.pi
        m = RZ(a) @ T(0, r, 0)
        b.box((0, 0, 0), (2 * math.pi * r / segs + 0.02, 0.05, 0.05), L.METAL, rc, m=m)
    for i in range(4):
        m = RZ(i * math.pi / 4)
        b.box((0, 0, 0), (0.04, 2 * r, 0.03), L.METAL, rc, m=m)
    b.box((0, 0, 0), (0.1, 0.1, 0.1), L.METAL, (0.6, 0.6, 0.6))
    return b.array()


def herd_head_mesh():
    b = MeshBuilder()
    b.box((0, 0.13, 0), (0.2, 0.25, 0.22), L.SKIN, (0.9, 0.9, 0.9))
    b.box((-0.05, 0.16, 0.111), (0.045, 0.035, 0.01), L.BLACK)
    b.box((0.05, 0.16, 0.111), (0.045, 0.035, 0.01), L.BLACK)
    b.box((0, 0.07, 0.111), (0.07, 0.02, 0.01), L.BLACK)
    for s in (-1, 1):
        m = T(s * 0.07, 0.24, 0) @ RZ(-s * 0.45)
        b.box((0, 0.25, 0), (0.035, 0.5, 0.035), L.BARK, (0.8, 0.8, 0.8), m=m)
        m2 = m @ T(0, 0.3, 0) @ RZ(-s * 0.7)
        b.box((0, 0.13, 0), (0.025, 0.26, 0.025), L.BARK, (0.8, 0.8, 0.8), m=m2)
        m3 = m @ T(0, 0.42, 0) @ RZ(s * 0.5)
        b.box((0, 0.1, 0), (0.02, 0.2, 0.02), L.BARK, (0.8, 0.8, 0.8), m=m3)
        b.box((s * 0.02, 0.24, 0), (0.06, 0.03, 0.24), L.CLOTH, (0.5, 0.45, 0.4))
    return b.array()


def pose_moose(x, y, z, yaw, walk_phase, walk_amt, hunch=0.45, roll=0.0, head_yaw=0.0,
               head_pitch=0.0, scale=1.0, reach=0.0, jaw=0.0, t=0.0, tilt=0.0):
    """Build the Moose Man as a list of (mesh_key, matrix).

    Tall, starved and wrong: bare pale shins and forearms, ribs and spine
    through torn hide, hands that reach the floor, a skull fused onto a raw
    neck, human eyes in the sockets looking two different ways, and one
    antler snapped off with skin peeling from both.
    """
    parts = []
    add = parts.append
    M0 = T(x, y, z) @ RY(yaw) @ RX(tilt) @ S(scale)    # tilt -pi/2: flat on his back
    H = 1.55
    # ---------------------------------------------------------- legs (reverse knees)
    for side in (-1, 1):
        ph = walk_phase + (0.0 if side < 0 else math.pi)
        swing = math.sin(ph) * 0.55 * walk_amt
        hip = M0 @ T(side * 0.13, H, -0.02) @ RX(-0.35 - swing)
        add(('fur', hip @ T(0, -0.39, 0) @ S(0.11, 0.8, 0.12)))
        knee = hip @ T(0, -0.78, 0) @ RX(0.85 + 0.4 * walk_amt * max(0.0, math.cos(ph)))
        add(('fur', knee @ T(0, -0.02, 0) @ S(0.1, 0.12, 0.1)))
        add(('flesh', knee @ T(0, -0.41, 0) @ S(0.072, 0.82, 0.072)))
        ankle = knee @ T(0, -0.82, 0) @ RX(-0.5)
        add(('fur', ankle @ T(0, 0.05, 0) @ S(0.12, 0.12, 0.12)))
        add(('black', ankle @ T(0, -0.06, 0.05) @ S(0.11, 0.13, 0.2)))
    # ---------------------------------------------------------- starved torso
    torso = M0 @ T(0, H, 0) @ RX(hunch)
    add(('fur', torso @ T(0, 0.03, 0) @ S(0.3, 0.18, 0.22)))
    add(('flesh', torso @ T(0, 0.28, 0) @ S(0.19, 0.36, 0.15)))
    add(('fur', torso @ T(0, 0.73, 0) @ S(0.4, 0.56, 0.27)))
    # torn open down the chest: dark wet patches behind the ribs, not a tidy square
    for gx_, gy_, gw, gh in ((0.05, 0.62, 0.12, 0.2), (-0.04, 0.72, 0.09, 0.14), (0.08, 0.8, 0.07, 0.09), (0.0, 0.52, 0.06, 0.1)):
        add(('gore', torso @ T(gx_, gy_, 0.137) @ RZ(gx_ * 3) @ S(gw, gh, 0.01)))
    for k in range(6):
        w = 0.34 - 0.03 * abs(k - 2.5)
        add(('rib', torso @ T(0, 0.5 + k * 0.08, 0.145) @ RZ(0.04 * (k - 2.5)) @ S(w, 0.016, 0.025)))
    for side in (-1, 1):
        for k in range(5):
            add(('rib', torso @ T(side * 0.2, 0.52 + k * 0.09, 0.02) @ RY(side * 0.3) @ S(0.016, 0.018, 0.25)))
        add(('bone', torso @ T(side * 0.12, 0.88, -0.135) @ RX(0.2) @ S(0.14, 0.2, 0.03)))
    for k in range(9):
        add(('bone', torso @ T(0, 0.08 + k * 0.11, -0.15 + 0.02 * math.sin(k)) @ S(0.06, 0.07, 0.07)))
    # strips of hide hanging off the back, swaying
    for i in range(7):
        px = -0.18 + i * 0.06
        ln = 0.32 + 0.12 * (i % 3)
        sway = 0.15 * math.sin(t * 1.7 + i * 1.3) + 0.25 * walk_amt * math.sin(walk_phase + i)
        m = torso @ T(px, 0.98 - (i % 3) * 0.14, -0.13) @ RX(-hunch * 0.9 + sway) @ RZ((i - 3) * 0.06)
        add(('fur' if i % 3 else 'gore', m @ T(0, -ln / 2, 0) @ S(0.05, ln, 0.012)))
    # ---------------------------------------------------------- arms that reach the floor
    curl = 0.2 + 0.35 * reach
    for side in (-1, 1):
        ph = walk_phase + (math.pi if side < 0 else 0.0)
        aswing = math.sin(ph) * 0.22 * walk_amt
        sh = torso @ T(side * 0.25, 0.92, 0) @ RX(-hunch - aswing - reach) @ RZ(side * 0.12)
        add(('fur', sh @ T(0, -0.43, 0) @ S(0.085, 0.86, 0.085)))
        el = sh @ T(0, -0.86, 0) @ RX(-0.3 - 0.2 * walk_amt - reach * 0.3)
        add(('fur', el @ T(0, -0.05, 0) @ S(0.1, 0.15, 0.1)))
        add(('flesh', el @ T(0, -0.45, 0) @ S(0.062, 0.9, 0.062)))
        hand = el @ T(0, -0.9, 0)
        add(('flesh', hand @ T(0, -0.07, 0) @ S(0.11, 0.14, 0.04)))
        for f in (-1.5, -0.5, 0.5, 1.5):
            base = hand @ T(f * 0.028, -0.14, 0) @ RZ(f * 0.08 * side) @ RX(-0.15 - curl)
            add(('flesh', base @ T(0, -0.12, 0) @ S(0.022, 0.24, 0.022)))
            j2 = base @ T(0, -0.24, 0) @ RX(-0.35 - curl)
            add(('flesh', j2 @ T(0, -0.1, 0) @ S(0.018, 0.2, 0.018)))
            add(('black', j2 @ T(0, -0.23, 0.004) @ S(0.016, 0.07, 0.012)))
    # ---------------------------------------------------------- raw neck
    neck = torso @ T(0, 1.0, 0.05) @ RX(0.7)
    add(('flesh', neck @ T(0, 0.22, 0) @ S(0.11, 0.48, 0.11)))
    add(('fur', neck @ T(0, 0.2, -0.05) @ S(0.15, 0.42, 0.06)))
    for k in range(7):
        a = k * 0.9
        add(('gore', neck @ T(math.cos(a) * 0.075, 0.44, math.sin(a) * 0.075) @ RY(-a) @ RZ(0.5) @ S(0.05, 0.11, 0.02)))
    # ---------------------------------------------------------- the skull
    # the skull hangs snout-down, the way a dead head would
    head = neck @ T(0, 0.46, 0) @ RX(-(hunch + 0.7) + 0.5 + head_pitch) @ RY(head_yaw) @ RZ(roll)
    add(('bone', head @ T(0, 0.1, 0) @ S(0.3, 0.28, 0.34)))
    add(('bone', head @ T(0, 0.2, 0.12) @ S(0.32, 0.06, 0.1)))
    snout = head @ T(0, 0.02, 0.32) @ RX(0.3)
    # long tapering snout: wide at the eyes, narrow at the tip
    add(('bone', snout @ T(0, 0.0, -0.14) @ S(0.21, 0.2, 0.34)))
    add(('bone', snout @ T(0, -0.01, 0.17) @ S(0.15, 0.16, 0.3)))
    add(('black', snout @ T(0, 0.07, 0.17) @ S(0.08, 0.03, 0.24)))
    add(('black', snout @ T(0, -0.02, 0.322) @ S(0.1, 0.09, 0.01)))
    add(('gore', snout @ T(0, -0.05, 0.12) @ S(0.155, 0.06, 0.22)))
    for side in (-1, 1):
        for k in range(6):
            add(('teeth', snout @ T(side * (0.085 - k * 0.006), -0.1, -0.04 + k * 0.06) @ S(0.022, 0.06, 0.02)))
    jaw_m = head @ T(0, -0.1, 0.14) @ RX(0.42 + jaw)
    add(('bone', jaw_m @ T(0, 0, 0.26) @ S(0.16, 0.045, 0.52)))
    for side in (-1, 1):
        for k in range(6):
            add(('teeth', jaw_m @ T(side * 0.062, 0.045, 0.08 + k * 0.06) @ S(0.02, 0.05, 0.02)))
        add(('gore', jaw_m @ T(side * 0.05, -0.08, 0.3) @ S(0.015, 0.15, 0.015)))
    # human eyes, each looking somewhere slightly different
    for side in (-1, 1):
        add(('black', head @ T(side * 0.135, 0.13, 0.11) @ S(0.08, 0.09, 0.1)))
        add(('eyewhite', head @ T(side * 0.155, 0.13, 0.125) @ S(0.05, 0.05, 0.05)))
        py = 0.012 if side > 0 else -0.01
        pz = 0.0 if side > 0 else 0.014
        add(('black', head @ T(side * 0.18, 0.13 + py, 0.13 + pz) @ S(0.008, 0.02, 0.02)))
    # right antler: whole palm
    base = head @ T(0.13, 0.22, -0.03) @ RZ(-1.05)
    add(('bone', base @ T(0, 0.24, 0) @ S(0.065, 0.48, 0.065)))
    # broad palm facing forward, so from the front it is a wide pale plate
    palm = base @ T(0, 0.46, 0) @ RZ(0.75) @ RX(-0.25)
    add(('bone', palm @ T(0.1, 0.32, 0) @ S(0.42, 0.64, 0.045)))
    for k in range(6):
        tm = palm @ T(-0.08 + k * 0.075, 0.62, 0) @ RZ(0.45 - k * 0.17) @ T(0, 0.12, 0)
        add(('bone', tm @ S(0.03, 0.26, 0.03)))
    add(('bone', palm @ T(0.32, 0.18, 0) @ RZ(-1.1) @ T(0, 0.12, 0) @ S(0.03, 0.25, 0.03)))
    for k in range(3):
        sw = 0.12 * math.sin(t * 2.1 + k)
        add(('gore', palm @ T(-0.05 + k * 0.13, 0.08, 0.03) @ RX(sw) @ T(0, -0.15, 0) @ S(0.04, 0.3, 0.01)))
    # left antler: snapped off, splintered
    base = head @ T(-0.13, 0.22, -0.03) @ RZ(1.05)
    add(('bone', base @ T(0, 0.22, 0) @ S(0.065, 0.44, 0.065)))
    stub = base @ T(0, 0.43, 0) @ RZ(-0.5) @ RX(-0.25)
    add(('bone', stub @ T(-0.04, 0.12, 0) @ S(0.26, 0.24, 0.045)))
    for k, (az, ln) in enumerate(((0.3, 0.14), (-0.4, 0.1), (0.1, 0.18))):
        add(('bone', stub @ T(-0.13 + k * 0.09, 0.24, 0) @ RZ(az) @ T(0, ln / 2, 0) @ S(0.02, ln, 0.02)))
    add(('gore', stub @ T(0.0, 0.12, 0.03) @ RX(0.1 * math.sin(t * 1.9)) @ T(0, -0.2, 0) @ S(0.05, 0.4, 0.012)))
    return parts, head


def pose_goat(x, y, z, yaw, walk_phase=0.0, walk_amt=0.0, hunch=0.35, crouch=0.0, head_pitch=0.0,
              head_yaw=0.0, roll=0.0, jaw=0.0, arms=0.0, tilt=0.0, bloody=False, t=0.0):
    """The Goat Man: bigger than the Moose Man and built like a bull.

    Shaggy grey-black fur, goat legs on hooves, a massive humped chest, long
    arms with black claws, a long sloping goat face with a beard, yellow eyes
    with sideways pupils, and ram horns that curl back around his head.
    """
    parts = []
    add = parts.append
    M0 = T(x, y, z) @ RY(yaw) @ RX(tilt)
    H = 1.75 * (1.0 - 0.42 * crouch)
    for side in (-1, 1):
        ph = walk_phase + (0.0 if side < 0 else math.pi)
        swing = math.sin(ph) * 0.6 * walk_amt
        hip = M0 @ T(side * 0.24, H, 0) @ RX(-0.45 - 0.95 * crouch - swing)
        add(('gfur', hip @ T(0, -0.45, 0) @ S(0.25, 0.92, 0.28)))
        knee = hip @ T(0, -0.9, 0) @ RX(1.1 + 1.05 * crouch + 0.45 * walk_amt * max(0.0, math.cos(ph)))
        add(('gfur', knee @ T(0, -0.42, 0) @ S(0.15, 0.86, 0.16)))
        ankle = knee @ T(0, -0.85, 0) @ RX(-0.65 - 0.15 * crouch)
        add(('gdark', ankle @ T(0, -0.16, 0) @ S(0.1, 0.32, 0.1)))
        add(('black', ankle @ T(0, -0.37, 0.04) @ S(0.17, 0.12, 0.23)))
    torso = M0 @ T(0, H, 0) @ RX(hunch)
    add(('gfur', torso @ T(0, 0.12, 0) @ S(0.52, 0.38, 0.44)))
    add(('gfur', torso @ T(0, 0.72, 0.02) @ S(0.8, 0.82, 0.56)))
    add(('gdark', torso @ T(0, 1.12, -0.1) @ S(0.62, 0.36, 0.5)))
    for i in range(9):
        px = -0.34 + i * 0.085
        ln = 0.3 + 0.12 * ((i * 7) % 3)
        sw = 0.12 * math.sin(t * 2.3 + i) + 0.2 * walk_amt * math.sin(walk_phase + i)
        add(('gdark', torso @ T(px, 0.35, 0.25) @ RX(-hunch + sw) @ T(0, -ln / 2, 0) @ S(0.07, ln, 0.03)))
    if bloody:
        add(('gore', torso @ T(0.05, 0.8, 0.285) @ S(0.42, 0.5, 0.01)))
        add(('gore', torso @ T(-0.12, 0.5, 0.285) @ S(0.18, 0.3, 0.01)))
    for side in (-1, 1):
        ph = walk_phase + (math.pi if side < 0 else 0.0)
        aswing = math.sin(ph) * 0.3 * walk_amt
        sh = torso @ T(side * 0.46, 1.05, 0) @ RX(-hunch - aswing - arms * 1.2) @ RZ(side * 0.2)
        add(('gfur', sh @ T(0, -0.4, 0) @ S(0.21, 0.82, 0.21)))
        el = sh @ T(0, -0.8, 0) @ RX(-0.35 - arms * 0.45)
        add(('gfur', el @ T(0, -0.42, 0) @ S(0.17, 0.86, 0.17)))
        hand = el @ T(0, -0.86, 0)
        add(('skin', hand @ T(0, -0.08, 0) @ S(0.17, 0.17, 0.08)))
        for f in (-1.5, -0.5, 0.5, 1.5):
            cm = hand @ T(f * 0.04, -0.16, 0) @ RZ(f * 0.07) @ RX(-0.45) @ T(0, -0.14, 0)
            add(('black', cm @ S(0.03, 0.3, 0.03)))
            if bloody:
                add(('gore', cm @ T(0, 0.06, 0) @ S(0.034, 0.12, 0.034)))
    neck = torso @ T(0, 1.22, 0.16) @ RX(0.5)
    add(('gfur', neck @ T(0, 0.15, 0) @ S(0.32, 0.42, 0.32)))
    head = neck @ T(0, 0.36, 0.05) @ RX(-(hunch + 0.5) + 0.3 + head_pitch) @ RY(head_yaw) @ RZ(roll)
    add(('gfur', head @ T(0, 0.12, 0) @ S(0.33, 0.31, 0.35)))
    face = head @ T(0, 0.06, 0.16) @ RX(0.8)
    add(('gdark', face @ T(0, 0.0, 0.25) @ S(0.22, 0.21, 0.52)))
    add(('black', face @ T(0, 0.02, 0.51) @ S(0.17, 0.11, 0.05)))
    jaw_m = face @ T(0, -0.11, 0.06) @ RX(jaw * 0.8)
    add(('gdark', jaw_m @ T(0, 0, 0.23) @ S(0.18, 0.06, 0.44)))
    for side in (-1, 1):
        for k in range(5):
            add(('teeth', face @ T(side * 0.075, -0.1, 0.1 + k * 0.07) @ S(0.03, 0.05, 0.035)))
            add(('teeth', jaw_m @ T(side * 0.065, 0.05, 0.08 + k * 0.07) @ S(0.03, 0.05, 0.035)))
    for k in range(4):
        sw = 0.15 * math.sin(t * 2.0 + k)
        bm = jaw_m @ T(-0.06 + k * 0.04, -0.03, 0.12 + k * 0.05) @ RX(-0.8 - 0.4 * jaw + sw) @ T(0, -0.2, 0)
        add(('gore' if (bloody and k % 2 == 0) else 'gdark', bm @ S(0.04, 0.42, 0.03)))
    if bloody:
        add(('gore', jaw_m @ T(0, -0.02, 0.26) @ S(0.185, 0.05, 0.4)))
        add(('gore', face @ T(0, -0.06, 0.38) @ S(0.225, 0.08, 0.26)))
    for side in (-1, 1):
        add(('geye', head @ T(side * 0.165, 0.15, 0.16) @ S(0.03, 0.06, 0.08)))
        add(('black', head @ T(side * 0.181, 0.15, 0.16) @ S(0.005, 0.016, 0.06)))
        add(('gdark', head @ T(side * 0.24, 0.17, 0.02) @ RZ(-side * 0.35) @ S(0.24, 0.06, 0.11)))
        # ram horn, curling back and around
        m = head @ T(side * 0.12, 0.27, 0.02) @ RZ(-side * 0.35)
        w = 0.12
        for i in range(12):
            seg = 0.13
            add(('horn', m @ T(0, seg / 2, 0) @ S(w, seg + 0.02, w)))
            m = m @ T(0, seg, 0) @ RX(-0.52) @ RZ(-side * 0.16)
            w *= 0.92
    return parts, head


def car_parts(x, z, heading):
    """A 2003 four-door sedan. heading: +1 drives toward +z, -1 toward -z."""
    yaw = 0.0 if heading > 0 else math.pi
    M = T(x, 0.0, z) @ RY(yaw)
    p = []
    add = p.append
    add(('carbody', M @ T(0, 0.62, 0) @ S(1.78, 0.62, 4.7)))
    add(('carbody', M @ T(0, 1.15, -0.25) @ S(1.6, 0.5, 2.3)))
    add(('glass', M @ T(0, 1.16, 0.93) @ RX(-0.55) @ S(1.5, 0.48, 0.04)))
    add(('glass', M @ T(0, 1.16, -1.42) @ RX(0.6) @ S(1.5, 0.45, 0.04)))
    for s in (-1, 1):
        add(('glass', M @ T(s * 0.805, 1.17, -0.25) @ S(0.02, 0.36, 2.1)))
        for wz in (1.45, -1.45):
            add(('tire', M @ T(s * 0.82, 0.33, wz) @ S(0.24, 0.66, 0.66)))
            add(('chrome', M @ T(s * 0.95, 0.33, wz) @ S(0.02, 0.32, 0.32)))
        add(('headl', M @ T(s * 0.62, 0.72, 2.36) @ S(0.36, 0.16, 0.03)))
        add(('taill', M @ T(s * 0.66, 0.78, -2.36) @ S(0.3, 0.16, 0.03)))
    add(('chrome', M @ T(0, 0.42, 2.37) @ S(1.76, 0.12, 0.06)))
    add(('chrome', M @ T(0, 0.42, -2.37) @ S(1.76, 0.12, 0.06)))
    return p


class Moose:
    """AI for the thing in the sewer."""

    def __init__(self, world):
        self.w = world
        self.state = 'inactive'
        self.x = 0.0
        self.z = 0.0
        self.y = -5.0
        self.yaw = 0.0
        self.path = []
        self.timer = 0.0
        self.walk_phase = 0.0
        self.walk_amt = 0.0
        self.roll = 0.0
        self.roll_target = 0.0
        self.twitch_t = 0.0
        self.head_yaw = 0.0
        self.last_seen = None
        self.lost_t = 0.0
        self.sense_t = 0.0
        self.repath_t = 0.0
        self.grace = 0.0
        self.step_acc = 0.0
        self.speed = 0.0
        self.sees = False
        self.hunt = False
        self.events = []
        self.reach = 0.0
        self.jaw = 0.0
        self.stuck_t = 0.0
        self.prev = (0.0, 0.0)
        self.head_yaw_target = 0.0
        self.anim_clock = 0.0
        self.anim_acc = 0.0
        self.anim_step = 0.1
        self.snap = (0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.0)
        self.cells = None

    def place_cell(self, c, r):
        self.x, self.z = cell_center(c, r)
        self.y = self.w.floor_at(self.x, self.z) or -5.0
        self.path = []

    @property
    def active(self):
        return self.state not in ('inactive',)

    def emit(self, ev):
        self.events.append(ev)

    def path_to(self, tx, tz):
        start = cell_of(self.x, self.z)
        goal = cell_of(tx, tz)
        if not (0 <= goal[1] < ROWS and 0 <= goal[0] < COLS):
            self.path = []
            return False
        p = self.w.astar(start, goal)
        if p is None:
            self.path = []
            return False
        self.path = [cell_center(c, r) for c, r in p[1:]]
        if not self.path:
            self.path = [(tx, tz)]
        else:
            self.path[-1] = (tx, tz) if self.w.in_grid(tx, tz) else self.path[-1]
        return True

    def random_target(self, px, pz):
        if self.cells is None:
            self.cells = self.w.sewer_cells()
        if random.random() < 0.55:
            near = [c for c in self.cells if abs(cell_center(*c)[0] - px) + abs(cell_center(*c)[1] - pz) < 26]
            if near:
                return cell_center(*random.choice(near))
        return cell_center(*random.choice(self.cells))

    def hear(self, x, z, radius):
        if self.state in ('inactive', 'intro', 'chase') or self.grace > 0:
            return
        d = math.hypot(x - self.x, z - self.z)
        if d < radius:
            self.state = 'investigate'
            self.timer = 0.0
            self.path_to(x, z)

    def start_chase(self, px, pz):
        if self.state != 'chase':
            self.emit('chase_start')
        self.state = 'chase'
        self.last_seen = (px, pz)
        self.lost_t = 0.0

    def update(self, dt, player, flash_on):
        if self.state == 'inactive':
            return
        self.grace = max(0.0, self.grace - dt)
        px, pz = player.x, player.z
        dx, dz = px - self.x, pz - self.z
        dist = math.hypot(dx, dz)
        # ---- senses
        self.sense_t -= dt
        if self.sense_t <= 0:
            self.sense_t = 0.15
            self.sees = False
            if self.grace <= 0 and player.y > -9 and self.w.in_grid(px, pz) and abs(player.y - self.y) < 3.5:
                los = dist < 32 and self.w.los(self.x, self.z, px, pz)
                if los:
                    fx, fz = math.sin(self.yaw), math.cos(self.yaw)
                    cosang = (fx * dx + fz * dz) / max(dist, 1e-4)
                    vision = 22.0 if flash_on else 9.0
                    if player.crouch > 0.5:
                        vision *= 0.6
                    in_fov = cosang > 0.25 or dist < 4.0
                    beam = False
                    if flash_on and dist < 20:
                        bx, bz = -dx / dist, -dz / dist
                        beam = (player.fx * bx + player.fz * bz) > 0.93
                    if (in_fov and dist < vision) or beam or dist < 2.5:
                        self.sees = True
            if self.sees and self.state not in ('intro_leave',):
                self.start_chase(px, pz)
        # ---- states
        speed = 0.0
        target = None
        st = self.state
        if st == 'intro':
            self.yaw = self._turn(self.yaw, math.atan2(dx, dz), dt * 2)
            self.timer -= dt
            if dist < 9 and self.grace <= 0:
                self.start_chase(px, pz)
            elif self.timer <= 0:
                self.state = 'intro_leave'
                self.path_to(*cell_center(20, 30))
        elif st == 'intro_leave':
            speed = 1.7
            if not self.path:
                self.state = 'roam'
                self.timer = 1.0
        elif st == 'roam':
            speed = 1.5 if not self.hunt else 2.6
            if self.hunt:
                self.repath_t -= dt
                if self.repath_t <= 0:
                    self.repath_t = 2.5
                    self.path_to(px, pz)
            if not self.path:
                self.timer -= dt
                speed = 0.0
                if self.timer <= 0:
                    tx, tz = self.random_target(px, pz)
                    self.path_to(tx, tz)
                    self.timer = random.uniform(1.5, 4.0)
        elif st == 'investigate':
            speed = 2.5
            if not self.path:
                speed = 0.0
                self.timer += dt
                self.yaw += math.sin(self.timer * 1.7) * dt * 1.5
                if self.timer > 3.5:
                    self.state = 'roam'
                    self.timer = 1.0
        elif st == 'chase':
            speed = 4.25
            can_see = self.w.los(self.x, self.z, px, pz) and self.w.in_grid(px, pz)
            if can_see:
                self.last_seen = (px, pz)
                self.lost_t = 0.0
                target = (px, pz)
                self.path = []
            else:
                self.lost_t += dt
                self.repath_t -= dt
                if self.repath_t <= 0 or not self.path:
                    self.repath_t = 0.6
                    if self.last_seen:
                        self.path_to(*self.last_seen)
                if self.lost_t > 5.0 or (not self.path and self.lost_t > 1.0):
                    self.state = 'investigate'
                    self.timer = 0.0
                    if self.last_seen:
                        self.path_to(*self.last_seen)
            if dist < 1.05 and abs(player.y - self.y) < 2.0:
                self.emit('kill')
        # ---- movement
        if target is None and self.path:
            # skip ahead when possible
            while len(self.path) > 1 and self.w.los(self.x, self.z, *self.path[1]):
                ax, az = self.path[1]
                if math.hypot(ax - self.x, az - self.z) > 6:
                    break
                self.path.pop(0)
            target = self.path[0]
            if math.hypot(target[0] - self.x, target[1] - self.z) < 0.45:
                self.path.pop(0)
                target = self.path[0] if self.path else None
        moved = 0.0
        if target is not None and speed > 0:
            tx, tz = target
            mx, mz = tx - self.x, tz - self.z
            md = math.hypot(mx, mz)
            if md > 1e-4:
                step = min(md, speed * dt)
                nx = self.x + mx / md * step
                nz = self.z + mz / md * step
                nx, nz, _ = self.w.collide(nx, nz, 0.38, self.y, forest=False)
                moved = math.hypot(nx - self.x, nz - self.z)
                self.x, self.z = nx, nz
                self.yaw = self._turn(self.yaw, math.atan2(mx, mz), dt * (7 if st == 'chase' else 3.5))
        # stuck detection
        if speed > 0 and moved < speed * dt * 0.2:
            self.stuck_t += dt
            if self.stuck_t > 1.5:
                self.stuck_t = 0
                self.path = []
                self.repath_t = 0
                if st == 'roam':
                    self.timer = 0
        else:
            self.stuck_t = 0
        fl = self.w.floor_at(self.x, self.z)
        if fl is not None:
            self.y += (fl - self.y) * min(1.0, dt * 10)
        self.speed = moved / max(dt, 1e-4)
        self.walk_amt += (min(1.0, self.speed / 2.5) - self.walk_amt) * min(1.0, dt * 6)
        self.walk_phase += moved * 2.1
        self.step_acc += moved
        if self.step_acc > 1.25:
            self.step_acc = 0.0
            self.emit('step')
        # ---- twitchy head
        self.twitch_t -= dt
        if self.twitch_t <= 0:
            if random.random() < 0.5:
                self.roll_target = random.uniform(-0.7, 0.7)
            else:
                self.roll_target = 0.0
            self.twitch_t = random.uniform(0.15, 1.8) if st != 'chase' else random.uniform(0.05, 0.4)
            # the head also snaps sideways, like it heard its name
            self.head_yaw_target = random.uniform(-0.6, 0.6) if random.random() < 0.35 else 0.0
        self.roll += (self.roll_target - self.roll) * min(1.0, dt * 25)
        self.head_yaw += (self.head_yaw_target - self.head_yaw) * min(1.0, dt * 30)
        want_reach = 0.9 if st == 'chase' and dist < 6 else 0.0
        self.reach += (want_reach - self.reach) * min(1.0, dt * 4)
        if st == 'chase':
            self.jaw = 0.35 + 0.25 * abs(math.sin(self.walk_phase * 3))
        else:
            self.jaw = 0.05 + 0.5 * max(0.0, math.sin(self.anim_clock * 0.7) - 0.85) * 6
        # ---- stop-motion: limbs and head only update a few times a second,
        # at an uneven rate, while the body still glides. It reads as wrong.
        self.anim_clock += dt
        self.anim_acc += dt
        if self.anim_acc >= self.anim_step:
            self.anim_acc = 0.0
            self.anim_step = random.uniform(0.06, 0.12) if st == 'chase' else random.uniform(0.08, 0.2)
            self.snap = (self.walk_phase, self.walk_amt, self.roll, self.head_yaw, self.reach, self.jaw, self.anim_clock)

    @staticmethod
    def _turn(a, b, k):
        d = (b - a + math.pi) % (2 * math.pi) - math.pi
        return a + d * min(1.0, k)

    def ceiling_scale(self):
        c, r = cell_of(self.x, self.z)
        if 0 <= r < ROWS and 0 <= c < COLS:
            h = self.w.ceil[r, c] - self.w.floor[r, c]
            if h < 3.2:
                return max(0.72, (h - 0.15) / 2.95)
        return 1.0

    def parts(self):
        hunch = 0.45 if self.state != 'chase' else 0.75
        phase, amt, roll, hyaw, reach, jaw, clock = self.snap
        return pose_moose(self.x, self.y, self.z, self.yaw, phase, amt, hunch=hunch, roll=roll,
                          head_yaw=hyaw, scale=self.ceiling_scale(), reach=reach, jaw=jaw, t=clock)[0]
