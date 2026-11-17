"""Where the game is running: the desktop .exe, or a web browser (Pyodide).

In the browser the drawing, sound, input, saving and networking are done by
JavaScript (web/mm.js); the game code talks to it through `js.mm`.
"""
import json
import sys

WEB = sys.platform == 'emscripten'

if WEB:
    import js                                   # noqa: F401  (Pyodide's bridge to the page)
    from pyodide.ffi import to_js               # noqa: F401
else:
    js = None
    to_js = None


def load_json(name, default):
    """Saves live in the browser's localStorage on the web."""
    try:
        raw = js.localStorage.getItem('mooseman.' + name)
        return json.loads(raw) if raw else default
    except Exception:
        return default


def save_json(name, obj):
    try:
        js.localStorage.setItem('mooseman.' + name, json.dumps(obj))
    except Exception:
        pass
