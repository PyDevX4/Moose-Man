"""The other players, as you see them in co-op: a kid in a coat with a light."""
import math

from engine import T, S, RX, RY, RZ
from moose import unit_cube
from textures import L, EMIS

# coat colours, one per player slot, so you can tell each other apart in the dark
COATS = [(0.55, 0.16, 0.12), (0.16, 0.3, 0.5), (0.5, 0.42, 0.14), (0.2, 0.38, 0.2)]


def avatar_meshes():
    m = {
        'jeans': unit_cube(L.SKIN, (0.22, 0.27, 0.42)),
        'boot': unit_cube(L.BLACK),
        'pskin': unit_cube(L.SKIN, (0.85, 0.66, 0.55)),
        'hair': unit_cube(L.FUR, (0.22, 0.14, 0.08)),
        'torch': unit_cube(L.METAL, (0.3, 0.3, 0.32)),
        'lens': unit_cube(L.GLOW + EMIS, (1.0, 0.95, 0.75)),
        'lensoff': unit_cube(L.METAL, (0.4, 0.4, 0.38)),
        'lamp': unit_cube(L.GLOW + EMIS, (1.0, 0.7, 0.3)),
        'gunwood': unit_cube(L.WOOD if hasattr(L, 'WOOD') else L.FUR, (0.4, 0.24, 0.12)),
        'gunmetal': unit_cube(L.METAL, (0.2, 0.2, 0.22)),
    }
    for i, c in enumerate(COATS):
        m['coat%d' % i] = unit_cube(L.SKIN, c)
    return m


def pose_player(x, y, z, yaw, pitch=0.0, phase=0.0, amt=0.0, crouch=0.0, slot=0, item='flash', light_on=True,
                lift=0.0, flail=0.0, lie=0.0, t=0.0):
    """lift: 0..1 hoisted off the ground (something has you); flail: thrashing;
    lie: 0..1 fallen flat on your back."""
    parts = []
    add = parts.append
    coat = 'coat%d' % (slot % len(COATS))
    up = 1.0 - lie
    M0 = T(x, y + 0.12 * lie, z) @ RY(yaw) @ RX(-math.pi / 2 * lie)
    sink = 0.32 * crouch * up
    hip_h = 0.93 - sink
    thrash = flail * math.sin(t * 23.0)
    # legs
    for side in (-1, 1):
        ph = phase + (0.0 if side < 0 else math.pi)
        sw = math.sin(ph) * 0.6 * amt * up + side * 0.5 * thrash + (0.35 * lift if side > 0 else -0.2 * lift)
        hip = M0 @ T(side * 0.1, hip_h, 0) @ RX(-sw - 0.9 * crouch * up)
        add(('jeans', hip @ T(0, -0.23, 0) @ S(0.13, 0.46, 0.14)))
        knee = hip @ T(0, -0.46, 0) @ RX(0.25 * amt * max(0.0, math.cos(ph)) + 1.6 * crouch * up + 0.5 * lift)
        add(('jeans', knee @ T(0, -0.22, 0) @ S(0.12, 0.44, 0.13)))
        add(('boot', knee @ T(0, -0.46, 0.04) @ S(0.13, 0.1, 0.26)))
    # body
    torso = M0 @ T(0, hip_h, 0) @ RX(0.25 * crouch * up + 0.3 * thrash * 0.4)
    add((coat, torso @ T(0, 0.3, 0) @ S(0.4, 0.62, 0.24)))
    add((coat, torso @ T(0, 0.05, 0) @ S(0.42, 0.14, 0.26)))
    add(('boot', torso @ T(0, 0.62, 0.0) @ S(0.3, 0.05, 0.2)))       # collar
    # head
    neck = torso @ T(0, 0.66, 0) @ RX(-pitch * 0.6 * up + 0.5 * thrash) @ RZ(0.4 * lift * math.sin(t * 7))
    add(('pskin', neck @ T(0, 0.14, 0.01) @ S(0.21, 0.24, 0.22)))
    add(('hair', neck @ T(0, 0.27, -0.01) @ S(0.23, 0.07, 0.24)))
    add(('hair', neck @ T(0, 0.17, -0.11) @ S(0.23, 0.2, 0.04)))
    add(('boot', neck @ T(-0.05, 0.16, 0.115) @ S(0.03, 0.025, 0.01)))
    add(('boot', neck @ T(0.05, 0.16, 0.115) @ S(0.03, 0.025, 0.01)))
    # arms: the right one holds the light (or the gun), aimed where you look
    aim = -math.pi / 2 - pitch * up
    for side in (-1, 1):
        sh = torso @ T(side * 0.25, 0.56, 0)
        holding = side > 0 or item in ('rifle', 'shotgun')
        if lift > 0 or flail > 0:
            a = -2.4 * lift + side * 0.9 * thrash - 0.6 * flail
            arm = sh @ RX(a) @ RZ(side * (0.4 + 0.5 * flail))
        elif holding and up > 0.5:
            arm = sh @ RX(aim * 0.85 if item != 'lantern' or side < 0 else -0.35) @ RZ(side * 0.06 if item not in ('rifle', 'shotgun') else -side * 0.25)
        else:
            sw = math.sin(phase + (math.pi if side < 0 else 0.0)) * 0.5 * amt * up
            arm = sh @ RX(sw) @ RZ(side * 0.08 + side * 1.2 * lie)
        add((coat, arm @ T(0, -0.27, 0) @ S(0.11, 0.56, 0.12)))
        hand = arm @ T(0, -0.58, 0)
        add(('pskin', hand @ S(0.08, 0.1, 0.08)))
        if side > 0 and up > 0.5 and lift <= 0.05:
            if item == 'flash':
                add(('torch', hand @ T(0, -0.08, 0) @ S(0.05, 0.22, 0.05)))
                add(('lens' if light_on else 'lensoff', hand @ T(0, -0.2, 0) @ S(0.07, 0.03, 0.07)))
            elif item in ('rifle', 'shotgun'):
                g = hand @ T(-0.12, -0.05, 0.0) @ RZ(-0.5)
                ln = 1.05 if item == 'rifle' else 0.8
                add(('gunmetal', g @ T(0, -ln / 2, 0) @ S(0.035, ln, 0.035)))
                add(('gunwood', g @ T(0, 0.18, 0) @ S(0.06, 0.4, 0.09)))
        if side > 0 and item == 'lantern' and up > 0.5 and lift <= 0.05:
            add(('torch', hand @ T(0, -0.12, 0) @ S(0.16, 0.04, 0.16)))
            add(('lamp' if light_on else 'lensoff', hand @ T(0, -0.24, 0) @ S(0.11, 0.18, 0.11)))
            add(('torch', hand @ T(0, -0.35, 0) @ S(0.17, 0.04, 0.17)))
    return parts
