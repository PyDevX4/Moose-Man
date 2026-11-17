"""The renderer, for the browser.

Same interface as engine.Renderer / engine.Mesh, but instead of drawing it
records each frame as one Float32Array of commands and hands it to the WebGL2
renderer in web/mm.js, which runs the same shaders.

Command stream (floats):
  BEGIN  1, then HEADER floats (matrices, camera, flashlight, environment, lights)
  DRAW   2, mesh id, nofog, tint r g b, 16 model floats (column-major)
  CLEAR  3, r, g, b
"""
import numpy as np

from webplat import js, to_js

HEADER = 113
_mesh_ids = [0]


class Mesh:
    def __init__(self, ctx, prog, data):
        data = np.ascontiguousarray(data, dtype=np.float32)
        _mesh_ids[0] += 1
        self.id = _mesh_ids[0]
        self.count = len(data)
        js.mm.newMesh(self.id, to_js(data.reshape(-1)))


class _FBO:
    def __init__(self, r):
        self.r = r

    def use(self):
        pass

    def clear(self, rr, g, b, a=1.0, depth=1.0):
        self.r.cmds.append(np.array([3.0, rr, g, b], np.float32))


class Renderer:
    def __init__(self, ctx, win_w, win_h, tex_data):
        self.ctx = None
        self.prog = None
        self.win_w, self.win_h = win_w, win_h
        layers, h, w = tex_data.shape[0], tex_data.shape[1], tex_data.shape[2]
        js.mm.setTextures(to_js(np.ascontiguousarray(tex_data, dtype=np.uint8).reshape(-1)), w, h, layers)
        self.ui_h = 540
        self.ui_w = int(round(540 * win_w / win_h))
        self.fbo = _FBO(self)
        self.cmds = []
        self._draws = []
        self.rw, self.rh = win_w, win_h
        self.set_resolution("480p")

    def resize(self, win_w, win_h):
        self.win_w, self.win_h = win_w, win_h
        self.ui_w = int(round(540 * win_w / win_h))
        self.set_resolution(self._res)

    def set_resolution(self, res):
        self._res = res
        hts = {"360p": 360, "480p": 480, "720p": 720}
        h = min(hts.get(res, self.win_h), self.win_h)
        w = max(1, int(round(h * self.win_w / self.win_h)))
        self.rw, self.rh = w, h
        js.mm.setRes(w, h)

    def _flush_draws(self):
        if not self._draws:
            return
        n = len(self._draws)
        out = np.empty((n, 22), np.float32)
        out[:, 0] = 2.0
        models = np.empty((n, 4, 4), np.float32)
        for i, (mid, nofog, tint, model) in enumerate(self._draws):
            out[i, 1] = mid
            out[i, 2] = nofog
            out[i, 3:6] = tint
            models[i] = model
        out[:, 6:22] = models.transpose(0, 2, 1).reshape(n, 16)
        self.cmds.append(out.reshape(-1))
        self._draws = []

    def begin(self, cam_pos, cam_fwd, fov, env, time, flash_on, flash_pos, flash_dir, lights, far=140.0, up=(0.0, 1.0, 0.0)):
        from engine import perspective, view_matrix
        self._flush_draws()
        h = np.zeros(HEADER + 1, np.float32)
        h[0] = 1.0
        proj = perspective(fov, self.rw / self.rh, 0.05, far)
        view = view_matrix(cam_pos, cam_fwd, up)
        h[1:17] = proj.T.reshape(-1)
        h[17:33] = view.T.reshape(-1)
        h[33:36] = cam_pos
        h[36:39] = flash_pos
        h[39:42] = flash_dir
        h[42] = float(flash_on)
        h[43:46] = env['ambient']
        h[46:49] = env['moondir']
        h[49:52] = env['mooncol']
        h[52:55] = env['fog']
        h[55] = env['fogdens']
        h[56] = time
        n = min(8, len(lights))
        h[57] = n
        for i in range(n):
            pos, rad, colr = lights[i]
            h[58 + i * 4:61 + i * 4] = pos
            h[61 + i * 4] = rad
            h[90 + i * 3:93 + i * 3] = colr
        self.cmds.append(h)

    _IDENT = np.identity(4, dtype=np.float32)

    def draw(self, mesh, model=None, tint=None, nofog=False):
        self._draws.append((mesh.id, 1.0 if nofog else 0.0, tint or (1.0, 1.0, 1.0),
                            self._IDENT if model is None else model))

    def finish(self, ui_bytes, time, post):
        self._flush_draws()
        cmds = np.concatenate(self.cmds) if self.cmds else np.zeros(0, np.float32)
        self.cmds = []
        pp = np.array([time, post.get('grain', 0.0), post.get('vhs', 0.0), post.get('bright', 1.0), post.get('fear', 0.0),
                       post.get('red', 0.0), post.get('glitch', 0.0), post.get('fade', 0.0)], np.float32)
        js.mm.frame(to_js(cmds), to_js(np.frombuffer(ui_bytes, np.uint8)), self.ui_w, self.ui_h, to_js(pp))
