"""Grow a hand-made grid map into a bigger one.

The original rooms stay exactly as they were. New rooms are dropped into the
solid rock around them and each is joined to the map by a one-cell corridor,
until the map has about `factor` times as much floor.

Puzzle gating is kept: the map is split into ZONES (the parts you can walk
between without passing a gate, a flooded basin, planks...). Each new room
joins exactly one zone and never touches another, so no new corridor can be a
shortcut around a puzzle.
"""
import random


def zones_of(g, passable, barrier=()):
    """Label connected regions. `barrier` kinds count as walls when flooding,
    so the two sides of a gate end up in different zones."""
    rows, cols = len(g), len(g[0])
    zone = {}
    n = 0
    for r in range(rows):
        for c in range(cols):
            k = g[r][c]
            if k not in passable or k in barrier or (c, r) in zone:
                continue
            n += 1
            stack = [(c, r)]
            zone[(c, r)] = n
            while stack:
                cc, rr = stack.pop()
                for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nc, nr = cc + dc, rr + dr
                    if 0 <= nr < rows and 0 <= nc < cols and (nc, nr) not in zone:
                        kk = g[nr][nc]
                        if kk in passable and kk not in barrier:
                            zone[(nc, nr)] = n
                            stack.append((nc, nr))
    return zone


def grow(g, rng, factor=3.0, passable='.', connect_to=None, room_kinds='.', corridor_kinds=None,
         barrier=(), bounds=None, room_w=(3, 8), room_h=(3, 7), max_corridor=14, tries=20000, keep_out=()):
    """Grow grid `g` (list of row lists, '#' = rock) in place.

    connect_to:      kinds a new corridor may end on (default: room_kinds)
    room_kinds:      what new rooms are made of, picked at random per room
    corridor_kinds:  what new corridors are made of (default: the room's kind)
    barrier:         kinds that separate zones (gates, water...)
    bounds:          (c0, r0, c1, r1) where new rooms may go
    keep_out:        cells new stuff must not touch (spawns, special rooms...)
    Returns the list of new rooms as (c0, r0, c1, r1, kind).
    """
    rows, cols = len(g), len(g[0])
    if bounds is None:
        bounds = (1, 1, cols - 2, rows - 2)
    bc0, br0, bc1, br1 = bounds
    connect_to = connect_to or room_kinds
    floor0 = sum(1 for r in range(rows) for c in range(cols) if g[r][c] != '#')
    target = int(floor0 * factor)
    zone = zones_of(g, passable, barrier)
    keep_out = set(keep_out)
    rooms = []

    def is_rock(c, r):
        return 0 <= r < rows and 0 <= c < cols and g[r][c] == '#'

    def floor_count():
        return sum(1 for r in range(rows) for c in range(cols) if g[r][c] != '#')

    have = floor0
    for _ in range(tries):
        if have >= target:
            break
        w = rng.randint(*room_w)
        h = rng.randint(*room_h)
        if bc1 - bc0 - w < 2 or br1 - br0 - h < 2:
            continue
        c0 = rng.randint(bc0 + 1, bc1 - w)
        r0 = rng.randint(br0 + 1, br1 - h)
        c1, r1 = c0 + w - 1, r0 + h - 1
        # the room and a one-cell rim must all be rock
        ok = all(is_rock(c, r) for r in range(r0 - 1, r1 + 2) for c in range(c0 - 1, c1 + 2))
        if not ok:
            continue
        kind = rng.choice(room_kinds)
        ckind = rng.choice(corridor_kinds) if corridor_kinds else kind
        # walk a corridor out of a random side until it meets the map
        best = None
        for _attempt in range(6):
            side = rng.randrange(4)
            if side == 0:
                start, step = (rng.randint(c0, c1), r0 - 1), (0, -1)
            elif side == 1:
                start, step = (rng.randint(c0, c1), r1 + 1), (0, 1)
            elif side == 2:
                start, step = (c0 - 1, rng.randint(r0, r1)), (-1, 0)
            else:
                start, step = (c1 + 1, rng.randint(r0, r1)), (1, 0)
            path = []
            c, r = start
            hit = None
            for _n in range(max_corridor):
                if not (0 <= r < rows and 0 <= c < cols):
                    break
                k = g[r][c]
                if k != '#':
                    hit = (c, r)
                    break
                path.append((c, r))
                # sometimes turn once, to make an L
                if len(path) == 3 and rng.random() < 0.35:
                    step = (step[1], step[0]) if rng.random() < 0.5 else (-step[1], -step[0])
                c, r = c + step[0], r + step[1]
            if hit is None or g[hit[1]][hit[0]] not in connect_to or hit not in zone or hit in keep_out:
                continue
            # the corridor may only touch rock (and the cell it joins, and the room it leaves)
            room_cells = {(cc, rr) for rr in range(r0, r1 + 1) for cc in range(c0, c1 + 1)}
            pathset = set(path)
            clean = True
            for (pc, pr) in path:
                if (pc, pr) in keep_out:
                    clean = False
                    break
                for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nb = (pc + dc, pr + dr)
                    if nb in pathset or nb in room_cells or nb == hit:
                        continue
                    if not is_rock(*nb):
                        clean = False
                        break
                if not clean:
                    break
            if clean:
                best = (path, hit)
                break
        if best is None:
            continue
        path, hit = best
        if any((cc, rr) in keep_out for rr in range(r0 - 1, r1 + 2) for cc in range(c0 - 1, c1 + 2)):
            continue
        z = zone[hit]
        for rr in range(r0, r1 + 1):
            for cc in range(c0, c1 + 1):
                g[rr][cc] = kind
                zone[(cc, rr)] = z
        for (pc, pr) in path:
            g[pr][pc] = ckind
            zone[(pc, pr)] = z
        rooms.append((c0, r0, c1, r1, kind))
        have += w * h + len(path)
    return rooms


def pad(g, add_cols=0, add_rows=0, fill='#'):
    """Make the grid bigger to the east (cols) and north (rows)."""
    for row in g:
        row.extend([fill] * add_cols)
    cols = len(g[0])
    for _ in range(add_rows):
        g.append([fill] * cols)
    return g


def stamp(seed):
    return random.Random(seed)
