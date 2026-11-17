"""
Build the browser version of MOOSE MAN into web/dist/.

    python build_web.py              build
    python build_web.py --serve      build, then serve it on http://127.0.0.1:8800
    python build_web.py --publish    build, then put it on GitHub Pages (the gh-pages branch)

The page is plain static files: index.html, mm.js, and game.zip (the same
Python source as the .exe). It loads Python (Pyodide) from the jsDelivr CDN.
"""
import io
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
WEB = os.path.join(HERE, "web")
DIST = os.path.join(WEB, "dist")
sys.path.insert(0, SRC)
from version import VERSION     # noqa: E402

SKIP = {'updater.py'}           # the browser always has the latest version


def build():
    os.makedirs(DIST, exist_ok=True)
    for name in os.listdir(DIST):            # empty it (a test server may be sitting in it)
        p = os.path.join(DIST, name)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    with zipfile.ZipFile(os.path.join(DIST, "game.zip"), "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(os.listdir(SRC)):
            if name.endswith(".py") and name not in SKIP:
                zf.write(os.path.join(SRC, name), name)
        # a stand-in so `import updater` still works
        zf.writestr("updater.py", "CAN_INSTALL = False\n\ndef tidy():\n    pass\n\n"
                                  "def check_async(cb):\n    pass\n\ndef download(*a, **k):\n    return None\n\n"
                                  "def install(*a, **k):\n    return False\n")
    page = open(os.path.join(WEB, "index.html"), encoding="utf-8").read().replace("__VERSION__", VERSION)
    open(os.path.join(DIST, "index.html"), "w", encoding="utf-8").write(page)
    shutil.copy(os.path.join(WEB, "mm.js"), os.path.join(DIST, "mm.js"))
    icon = os.path.join(HERE, "icon.ico")
    if os.path.exists(icon):
        data = open(icon, "rb").read()
        png = data[data.index(b"\x89PNG"):]
        open(os.path.join(DIST, "favicon.png"), "wb").write(png)
    open(os.path.join(DIST, ".nojekyll"), "w").close()
    size = sum(os.path.getsize(os.path.join(DIST, f)) for f in os.listdir(DIST))
    print("built %s  (%.1f KB, version %s)" % (DIST, size / 1024, VERSION))


def serve(port=8800):
    import http.server
    import functools
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DIST)
    print("serving http://127.0.0.1:%d" % port)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()


def publish():
    """Commit web/dist onto the gh-pages branch (a separate worktree) and push it."""
    wt = os.path.join(HERE, "web", ".gh-pages")
    git = ["git", "-C", HERE]
    if not os.path.isdir(wt):
        have = subprocess.call(git + ["show-ref", "--verify", "--quiet", "refs/remotes/origin/gh-pages"]) == 0
        if have:
            subprocess.check_call(git + ["worktree", "add", wt, "gh-pages"])
        else:
            subprocess.check_call(git + ["worktree", "add", "--detach", wt])
            subprocess.check_call(["git", "-C", wt, "checkout", "--orphan", "gh-pages"])
            subprocess.check_call(["git", "-C", wt, "rm", "-rfq", "."])
    for name in os.listdir(wt):
        if name != ".git":
            p = os.path.join(wt, name)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    for name in os.listdir(DIST):
        shutil.copy(os.path.join(DIST, name), os.path.join(wt, name))
    subprocess.check_call(["git", "-C", wt, "add", "-A"])
    if subprocess.call(["git", "-C", wt, "diff", "--cached", "--quiet"]) == 0:
        print("nothing changed on the web build")
    else:
        subprocess.check_call(["git", "-C", wt, "-c", "user.email=PyDevX4@users.noreply.github.com",
                               "commit", "-q", "-m", "Web build %s" % VERSION])
    subprocess.check_call(["git", "-C", wt, "push", "-q", "origin", "HEAD:gh-pages"])
    print("pushed to gh-pages")


if __name__ == "__main__":
    os.chdir(HERE)
    build()
    if "--publish" in sys.argv:
        publish()
    if "--serve" in sys.argv:
        serve()
