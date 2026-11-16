"""
Build MOOSE MAN into a single Windows .exe (same workflow as Until Dawn).

    python build_exe.py                     build only
    python build_exe.py --bump --publish    bump the patch version, build,
                                            and put it on GitHub
    python build_exe.py --minor --publish   same, but 1.1.x -> 1.2.0

Publishing needs the GitHub CLI, set up once:

    winget install --id GitHub.cli
    gh auth login

Leaves dist/MooseMan.exe, dist/latest.json and dist/Moose Man <version>.zip.
Publishing uploads all three to a release tagged v<version>:

  * the .zip is what people download from the releases page;
  * latest.json + MooseMan.exe are what the game's own updater reads.
"""

import hashlib
import io
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
sys.path.insert(0, SRC)

from version import VERSION                      # noqa: E402
from version import parse as version_parse      # noqa: E402

NAME = "Moose Man"
REPO = "PyDevX4/Moose-Man"
ASSET = "MooseMan.exe"   # no spaces: GitHub rewrites them in asset names
ENTRY = os.path.join("src", "game.py")
ICON = "icon.ico"

# What the update screen shows players; one entry per line. Edit for each release.
NOTES = "\n".join([
    "Twice as much firewood out in the woods (68 bundles), so it's much easier to find.",
    "The Goat Man now hunts LIGHT and MOVEMENT.",
    "Lantern off and stand still: he stops, stares toward you, looks around... and leaves.",
    "Move or turn the light back on while he's searching, and he's on you again.",
])
DOWNLOAD_NOTE = "\n".join([
    "---",
    "**To play: download the .zip below.** Unzip it and run \"Moose Man.exe\" inside.",
    "",
    "The loose MooseMan.exe and latest.json are what the game's own updater uses --"
    " you do not need them.",
    "",
    "Contains flashing, glitch effects and a jumpscare. Turn off Camcorder Effects"
    " and Film Grain in Settings to tone it down.",
])


def write_icon():
    """A moose skull with antlers, drawn with pygame and saved as a PNG-in-ICO."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame
    pygame.init()
    s = 256
    surf = pygame.Surface((s, s), pygame.SRCALPHA)
    pygame.draw.circle(surf, (20, 6, 6, 255), (128, 128), 126)
    bone = (225, 214, 190)
    for side in (-1, 1):
        # beam and palm
        pygame.draw.line(surf, bone, (128 + side * 22, 104), (128 + side * 70, 70), 12)
        palm = [(128 + side * 60, 80), (128 + side * 112, 34), (128 + side * 118, 70), (128 + side * 84, 98)]
        pygame.draw.polygon(surf, bone, palm)
        for k in range(4):
            x = 128 + side * (70 + k * 13)
            y = 62 - k * 9
            pygame.draw.line(surf, bone, (x, y + 8), (x + side * 4, y - 22), 7)
    pygame.draw.polygon(surf, bone, [(96, 96), (160, 96), (150, 160), (140, 222), (116, 222), (106, 160)])
    pygame.draw.ellipse(surf, (20, 6, 6), (104, 114, 18, 22))
    pygame.draw.ellipse(surf, (20, 6, 6), (134, 114, 18, 22))
    pygame.draw.ellipse(surf, (150, 20, 15), (110, 122, 6, 6))
    pygame.draw.ellipse(surf, (150, 20, 15), (140, 122, 6, 6))
    pygame.draw.ellipse(surf, (20, 6, 6), (118, 196, 8, 14))
    pygame.draw.ellipse(surf, (20, 6, 6), (130, 196, 8, 14))
    png = io.BytesIO()
    pygame.image.save(surf, png, "icon.png")
    data = png.getvalue()
    head = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(data), 22)
    with open(os.path.join(HERE, ICON), "wb") as fh:
        fh.write(head + entry + data)
    pygame.quit()
    print("icon.ico written")


def bump_version(part="patch"):
    global VERSION
    path = os.path.join(SRC, "version.py")
    text = open(path, encoding="utf-8").read()
    major, minor, patch = version_parse(VERSION)[:3]
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    new = "%d.%d.%d" % (major, minor, patch)
    old_line = 'VERSION = "%s"' % VERSION
    if old_line not in text:
        sys.exit("could not find %s in version.py" % old_line)
    open(path, "w", encoding="utf-8").write(text.replace(old_line, 'VERSION = "%s"' % new))
    print("version %s -> %s" % (VERSION, new))
    VERSION = new
    return new


def find_gh():
    found = shutil.which("gh")
    if found:
        return found
    for guess in (os.path.join(os.environ.get("ProgramFiles", ""), "GitHub CLI", "gh.exe"),
                  os.path.join(os.environ.get("ProgramFiles(x86)", ""), "GitHub CLI", "gh.exe"),
                  os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links", "gh.exe")):
        if guess and os.path.exists(guess):
            return guess
    return None


def publish(asset, manifest, bundle):
    gh = find_gh()
    if gh is None:
        sys.exit("the GitHub CLI is not installed:\n  winget install --id GitHub.cli\n  gh auth login")
    tag = "v" + VERSION
    seen = subprocess.call([gh, "release", "view", tag, "--repo", REPO],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    if seen:
        print("release %s exists -- replacing its files" % tag)
        cmd = [gh, "release", "upload", tag, asset, manifest, bundle, "--repo", REPO, "--clobber"]
    else:
        print("creating release %s" % tag)
        cmd = [gh, "release", "create", tag, asset, manifest, bundle, "--repo", REPO,
               "--title", "%s %s" % (NAME, VERSION), "--notes", NOTES + "\n\n" + DOWNLOAD_NOTE]
    if subprocess.call(cmd) != 0:
        sys.exit("gh failed -- nothing was published")
    print("\npublished. every copy out there will update to %s on next launch." % VERSION)


def package(exe, publish_it=False):
    dist = os.path.dirname(exe)
    digest = hashlib.sha256()
    with open(exe, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    sha = digest.hexdigest()

    folder = "%s %s" % (NAME, VERSION)
    zip_path = os.path.join(dist, folder + ".zip")
    readme = "\r\n".join([
        NAME + "  v" + VERSION,
        "",
        'Double-click "%s.exe" to play. Headphones recommended. Play in the dark.' % NAME,
        "",
        "Windows may warn that it does not recognise the file -- it is not",
        "signed. Click More info, then Run anyway.",
        "",
        "The game updates itself when a new version is released",
        "(turn it off in Settings -> Auto Update).",
        "",
        "WARNING: contains flashing, glitch effects and a jumpscare.",
        "",
    ])
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(exe, "%s/%s.exe" % (folder, NAME))
        zf.writestr("%s/README.txt" % folder, readme)

    url = "https://github.com/%s/releases/latest/download/%s" % (REPO, ASSET)
    manifest = os.path.join(dist, "latest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"version": VERSION, "url": url, "sha256": sha, "notes": NOTES}, fh, indent=1)

    print("packed  %s  (%.1f MB)" % (zip_path, os.path.getsize(zip_path) / 1e6))
    print("asset   %s" % exe)
    print("wrote   %s" % manifest)
    print("        sha256 %s\n" % sha)
    if publish_it:
        publish(exe, manifest, zip_path)
        return
    print("to publish an update:  python build_exe.py --bump --publish")


def main():
    os.chdir(HERE)
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        return
    for part in ("major", "minor", "patch"):
        if "--" + part in args:
            bump_version(part)
            break
    else:
        if "--bump" in args:
            bump_version("patch")

    write_icon()
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
           "--name", os.path.splitext(ASSET)[0], "--paths", "src",
           "--hidden-import", "glcontext", "--collect-submodules", "glcontext",
           "--icon", ICON, ENTRY]
    print(" ".join(cmd))
    if subprocess.call(cmd) != 0:
        sys.exit("PyInstaller failed")
    shutil.rmtree(os.path.join(HERE, "build"), ignore_errors=True)
    out = os.path.join(HERE, "dist", ASSET)
    if not os.path.exists(out):
        sys.exit("build reported success but %s is missing" % out)
    print("\nbuilt %s  (%.1f MB)" % (out, os.path.getsize(out) / 1e6))
    package(out, publish_it="--publish" in args)


if __name__ == "__main__":
    main()
