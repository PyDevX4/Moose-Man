"""
Checking for a new build, and installing it.  (Same system as Until Dawn.)

  * `build_exe.py --publish` puts two files on the GitHub release:

      latest.json     {"version": "1.1.0", "url": "https://.../MooseMan.exe",
                       "sha256": "a3f1...", "notes": "What changed."}
      MooseMan.exe    the build itself

  * Every copy of the game reads MANIFEST_URL on startup and offers (or, with
    auto-update on, just installs) anything newer than its own VERSION.

Rules, because an auto-updater downloads a program and runs it:

  * HTTPS only, for the manifest and the download both.
  * The download is checked against the manifest's SHA-256 before anything is
    swapped. A mismatch is deleted, never run.

Windows cannot overwrite a running .exe, so installing writes a small batch
file that waits for the game to exit, swaps the file, restarts it and deletes
itself.
"""

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

from paths import FROZEN, app_dir
from version import VERSION, is_newer

CAN_INSTALL = os.name == "nt"

# Empty means the feature is off: no check, no button, no network at all.
MANIFEST_URL = ("https://github.com/PyDevX4/Moose-Man"
                "/releases/latest/download/latest.json")

EXE_NAME = "Moose Man"
TIMEOUT = 6.0                  # seconds; a slow host must not delay the menu
MAX_BYTES = 200 * 1024 * 1024  # a build is ~28 MB; refuse anything absurd
USER_AGENT = "MooseMan/%s" % VERSION


def repo_path():
    """"PyDevX4/Moose-Man", pulled out of MANIFEST_URL."""
    try:
        after = MANIFEST_URL.split("github.com/", 1)[1]
        return "/".join(after.split("/")[:2])
    except Exception:
        return ""


class Update(object):
    def __init__(self, version, url, sha256, notes=""):
        self.version = version
        self.url = url
        self.sha256 = (sha256 or "").lower()
        self.notes = notes or ""


def _log(msg):
    """Breadcrumbs in update.log next to the .exe (a windowed build has no
    console, and every failure here is deliberately swallowed)."""
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(app_dir(), "update.log"), "a") as fh:
            fh.write("%s  %s\n" % (stamp, msg))
    except Exception:
        pass


def _get(url, timeout=TIMEOUT):
    if not url.lower().startswith("https://"):
        raise ValueError("refusing a non-HTTPS url: %r" % url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout)


def check(force=False):
    """Ask the manifest whether there is anything newer. None if not."""
    _log("check: frozen=%s version=%s" % (FROZEN, VERSION))
    if not MANIFEST_URL or not (FROZEN or force):
        _log("check: skipped -- %s" % ("no MANIFEST_URL" if not MANIFEST_URL else "not a built .exe"))
        return None
    try:
        with _get(MANIFEST_URL) as resp:
            data = json.loads(resp.read(64 * 1024).decode("utf-8"))
        version = str(data.get("version", ""))
        url = str(data.get("url", ""))
        sha = str(data.get("sha256", ""))
        _log("check: manifest says %s" % version)
        if not is_newer(version):
            _log("check: %s is not newer than %s -- nothing to do" % (version, VERSION))
            return None
        if not url.lower().startswith("https://"):
            _log("check: refusing non-https url %r" % url)
            return None
        if len(sha) != 64:
            _log("check: manifest has no usable sha256")
            return None
        _log("check: offering %s" % version)
        return Update(version, url, sha, str(data.get("notes", "")))
    except Exception as exc:
        _log("check: failed -- %s: %s" % (type(exc).__name__, exc))
        return None


def check_async(on_done):
    """Run check() off the main thread and hand the result back."""
    def run():
        try:
            on_done(check())
        except Exception:
            on_done(None)
    t = threading.Thread(target=run, name="update-check")
    t.daemon = True
    t.start()
    return t


def download(update, progress=None, folder=None):
    """Fetch the new build beside the current one, checked against its hash.
    Returns the staged path, or None."""
    dest = os.path.join(folder or app_dir(), EXE_NAME + ".new.exe")
    part = dest + ".part"
    digest = hashlib.sha256()
    _log("download: starting %s" % update.url)
    try:
        with _get(update.url, timeout=30.0) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            if total > MAX_BYTES:
                return None
            got = 0
            with open(part, "wb") as fh:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    got += len(chunk)
                    if got > MAX_BYTES:
                        raise ValueError("download too large")
                    digest.update(chunk)
                    fh.write(chunk)
                    if progress:
                        progress(got, total)
        if digest.hexdigest().lower() != update.sha256:
            _log("download: CHECKSUM MISMATCH -- got %s, wanted %s"
                 % (digest.hexdigest()[:16], update.sha256[:16]))
            os.remove(part)
            return None
        _log("download: %d bytes, checksum ok" % got)
        if os.path.exists(dest):
            os.remove(dest)
        os.rename(part, dest)
        return dest
    except Exception as exc:
        _log("download: failed -- %s: %s" % (type(exc).__name__, exc))
        for path in (part, dest):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        return None


def tidy():
    """Clear leftovers from an update that did not finish."""
    for name in (EXE_NAME + ".new.exe", EXE_NAME + ".new.exe.part", "update.bat"):
        path = os.path.join(app_dir(), name)
        try:
            if os.path.exists(path):
                os.remove(path)
                _log("tidy: removed leftover %s" % name)
        except OSError:
            pass


def install(staged):
    """Swap the staged build in and restart, via a script that outlives us."""
    if not CAN_INSTALL:
        _log("install: not supported on this platform -- manual download")
        return False
    if not FROZEN or not staged or not os.path.exists(staged):
        _log("install: nothing to install")
        return False
    exe = os.path.abspath(sys.executable)
    script = os.path.join(app_dir(), "update.bat")
    # Retry the move until Windows lets go of the running .exe. `ping` is the
    # sleep that works with no console attached; the game is relaunched through
    # Explorer so PyInstaller's bootloader does not complain about its parent.
    body = "\r\n".join([
        "@echo off",
        "setlocal",
        'set "SRC=%s"' % staged,
        'set "DST=%s"' % exe,
        "set /a tries=0",
        ":retry",
        "set /a tries+=1",
        'move /y "%SRC%" "%DST%" >nul 2>&1',
        'if not exist "%SRC%" goto done',
        "if %tries% geq 90 goto giveup",
        "ping -n 2 127.0.0.1 >nul",
        "goto retry",
        ":done",
        'explorer.exe "%DST%"',
        "ping -n 3 127.0.0.1 >nul",
        'del "%~f0"',
        "exit /b 0",
        ":giveup",
        'del /q "%SRC%" >nul 2>&1',
        'explorer.exe "%DST%"',
        "ping -n 3 127.0.0.1 >nul",
        'del "%~f0"',
        '',
    ])
    try:
        with open(script, "w", newline="") as fh:
            fh.write(body)
        subprocess.Popen(["cmd", "/c", script], creationflags=0x08000000)  # CREATE_NO_WINDOW
        _log("install: swap script started, quitting for the handover")
        return True
    except Exception as exc:
        _log("install: failed -- %s: %s" % (type(exc).__name__, exc))
        return False
