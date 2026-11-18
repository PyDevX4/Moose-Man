"""Your truck: an old pickup, parked at the trailhead in Chapter One.

Local frame: origin on the ground under the middle, nose down +z, the driver's side
(and the door that opens) on +x. Everything is boxes and cylinders, like the rest."""
import math

from engine import MeshBuilder, T, RX, RZ
from textures import L, EMIS

PAINT = (0.42, 0.13, 0.1)        # faded red
DARK = (0.12, 0.12, 0.13)
CHROME = (0.62, 0.62, 0.64)
WHEEL_R = 0.4
WHEELS = [(sx * 0.86, WHEEL_R, sz) for sz in (1.62, -1.62) for sx in (1, -1)]
DOOR_HINGE = (0.9, 1.08, 0.64)   # the driver's door swings out on its front edge
SEAT_EYE = (0.42, 1.62, -0.32)   # your head, behind the wheel
HEADLIGHTS = [(sx * 0.62, 1.0, 2.53) for sx in (1, -1)]
BOX = (1.02, 2.62)               # half width, half length: what you walk into


def body_mesh():
    b = MeshBuilder()
    box = b.box
    # chassis, hood, grille, bumpers
    box((0, 0.56, 0), (1.66, 0.24, 4.9), L.METAL, DARK)
    box((0, 0.97, 1.82), (1.8, 0.52, 1.36), L.METAL, PAINT)
    box((0, 1.24, 1.82), (1.72, 0.03, 1.3), L.METAL, (0.36, 0.11, 0.08))
    box((0, 0.92, 2.51), (1.24, 0.42, 0.04), L.GRATE, (0.35, 0.35, 0.37))
    box((0, 0.55, 2.56), (1.9, 0.18, 0.14), L.METAL, CHROME)
    box((0, 0.6, -2.56), (1.9, 0.16, 0.12), L.METAL, CHROME)
    # fenders over the wheels
    for sx in (1, -1):
        for sz in (1.62, -1.62):
            box((sx * 0.9, 0.86, sz), (0.16, 0.22, 1.02), L.METAL, PAINT)
    # the cab: floor, dash, bench seat, back wall, roof and pillars
    box((0, 0.76, -0.04), (1.7, 0.06, 1.36), L.METAL, DARK)
    box((0, 1.12, 0.64), (1.72, 0.34, 0.12), L.METAL, PAINT)          # firewall up to the dash
    box((0, 1.31, 0.55), (1.64, 0.08, 0.3), L.METAL, (0.1, 0.1, 0.1))  # the dash top
    box((0.42, 1.25, 0.52), (0.36, 0.12, 0.04), L.BLACK)               # gauges
    box((0, 0.98, -0.36), (1.5, 0.2, 0.52), L.CLOTH, (0.3, 0.24, 0.2))
    box((0, 1.3, -0.6), (1.5, 0.62, 0.12), L.CLOTH, (0.3, 0.24, 0.2))
    box((0, 1.1, -0.72), (1.8, 0.62, 0.06), L.METAL, PAINT)
    box((0, 1.62, -0.72), (1.8, 0.42, 0.04), L.BLACK, (0.6, 0.65, 0.7))  # rear window
    box((0, 1.86, -0.05), (1.8, 0.06, 1.42), L.METAL, PAINT)
    box((-0.9, 1.08, -0.04), (0.06, 0.6, 1.36), L.METAL, PAINT)       # passenger door
    for sx in (1, -1):
        box((0, 0, 0), (0.07, 0.56, 0.07), L.METAL, PAINT, m=T(sx * 0.87, 1.6, 0.52) @ RX(-0.5))   # A pillars
        box((sx * 0.87, 1.58, -0.7), (0.07, 0.56, 0.07), L.METAL, PAINT)                          # B pillars
        box((sx * 1.0, 1.42, 0.55), (0.12, 0.1, 0.05), L.METAL, CHROME)                           # mirrors
    # the steering wheel
    b.cylinder(0.16, 0.16, 0.025, 12, L.BLACK, (0.3, 0.3, 0.3), m=T(0.42, 1.1, 0.34) @ RX(-1.25), cap=True)
    b.cylinder(0.025, 0.025, 0.3, 6, L.BLACK, (0.3, 0.3, 0.3), m=T(0.42, 1.08, 0.36) @ RX(-1.25 + math.pi))
    # the bed
    box((0, 0.86, -1.62), (1.76, 0.08, 1.76), L.WOOD, (0.45, 0.4, 0.36))
    for sx in (1, -1):
        box((sx * 0.88, 1.1, -1.62), (0.06, 0.46, 1.76), L.METAL, PAINT)
    box((0, 1.1, -2.5), (1.82, 0.46, 0.06), L.METAL, PAINT)
    # wheels
    for (x, y, z) in WHEELS:
        b.cylinder(WHEEL_R, WHEEL_R, 0.28, 12, L.BLACK, (0.25, 0.25, 0.25), m=T(x, y, z) @ RZ(math.pi / 2) @ T(0, -0.14, 0), cap=True)
        b.cylinder(0.18, 0.18, 0.3, 8, L.METAL, CHROME, m=T(x, y, z) @ RZ(math.pi / 2) @ T(0, -0.15, 0), cap=True)
    return b.array()


def door_mesh():
    """The driver's door, hinged at the origin (its front edge), closing along -z."""
    b = MeshBuilder()
    b.box((0, 0, -0.68), (0.06, 0.6, 1.34), L.METAL, PAINT)
    b.box((0, 0.3, -0.68), (0.07, 0.04, 1.3), L.METAL, PAINT)
    b.box((0, 0.52, -1.3), (0.05, 0.48, 0.05), L.METAL, PAINT)
    b.box((0.04, 0.12, -1.2), (0.03, 0.04, 0.14), L.METAL, CHROME)     # the handle
    return b.array()


def lights_mesh(on):
    b = MeshBuilder()
    if on:
        for (x, y, z) in HEADLIGHTS:
            b.box((x, y, z), (0.3, 0.2, 0.04), L.GLOW + EMIS, (1.6, 1.5, 1.2))
        for sx in (1, -1):
            b.box((sx * 0.78, 1.0, -2.54), (0.12, 0.22, 0.03), L.GLOW + EMIS, (1.2, 0.08, 0.05))
    else:
        for (x, y, z) in HEADLIGHTS:
            b.box((x, y, z), (0.3, 0.2, 0.04), L.METAL, (0.7, 0.7, 0.68))
        for sx in (1, -1):
            b.box((sx * 0.78, 1.0, -2.54), (0.12, 0.22, 0.03), L.METAL, (0.35, 0.05, 0.04))
    return b.array()


def antler_mesh():
    """One antler, pulled from something dead: a beam up +y with tines. Base at the origin."""
    b = MeshBuilder()
    col = (0.85, 0.8, 0.7)
    b.box((0, 0.3, 0), (0.045, 0.6, 0.045), L.BONE, col)
    for k, (y, a) in enumerate(((0.2, 0.7), (0.38, -0.6), (0.52, 0.55))):
        m = T(0, y, 0) @ RZ(a) @ T(0, 0.12, 0)
        b.box((0, 0, 0), (0.03, 0.24, 0.03), L.BONE, col, m=m)
    b.box((0, 0.64, 0), (0.025, 0.12, 0.025), L.BONE, col)
    b.box((0, 0.02, 0), (0.07, 0.05, 0.07), L.BLOOD, (0.7, 0.2, 0.2))
    return b.array()
