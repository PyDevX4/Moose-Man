"""
The one place the version number lives.

Bump this before building a release (or let `build_exe.py --bump` do it).
`build_exe.py` stamps it into the zip name and the update manifest, and
`updater.py` compares it against whatever the manifest says is current.
"""

VERSION = "1.4.0"


def parse(text):
    """"1.2.3" -> (1, 2, 3). Junk sorts lowest rather than raising."""
    out = []
    for part in str(text or "").split(".")[:4]:
        digits = "".join(c for c in part if c.isdigit())
        out.append(int(digits) if digits else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def is_newer(candidate, current=VERSION):
    return parse(candidate) > parse(current)
