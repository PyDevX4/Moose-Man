"""Rendering core: math, mesh building, shaders, post-processing."""
import math
import numpy as np
try:
    import moderngl
except ImportError:            # in the browser: see engine_web.py
    moderngl = None


# ---------------------------------------------------------------- math
def perspective(fovy_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2.0)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2.0 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


def view_matrix(eye, fwd, up=(0.0, 1.0, 0.0)):
    f = np.array(fwd, dtype=np.float64)
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= max(np.linalg.norm(s), 1e-8)
    u = np.cross(s, f)
    e = np.array(eye, dtype=np.float64)
    m = np.identity(4)
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -s.dot(e)
    m[1, 3] = -u.dot(e)
    m[2, 3] = f.dot(e)
    return m.astype(np.float32)


IDENT = np.identity(4, dtype=np.float32)


def T(x, y, z):
    m = np.identity(4, dtype=np.float32)
    m[0, 3] = x
    m[1, 3] = y
    m[2, 3] = z
    return m


def S(x, y=None, z=None):
    if y is None:
        y = x
    if z is None:
        z = x
    m = np.identity(4, dtype=np.float32)
    m[0, 0] = x
    m[1, 1] = y
    m[2, 2] = z
    return m


def RX(a):
    c, s = math.cos(a), math.sin(a)
    m = np.identity(4, dtype=np.float32)
    m[1, 1] = c
    m[1, 2] = -s
    m[2, 1] = s
    m[2, 2] = c
    return m


def RY(a):
    c, s = math.cos(a), math.sin(a)
    m = np.identity(4, dtype=np.float32)
    m[0, 0] = c
    m[0, 2] = s
    m[2, 0] = -s
    m[2, 2] = c
    return m


def RZ(a):
    c, s = math.cos(a), math.sin(a)
    m = np.identity(4, dtype=np.float32)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    return m


def _norm(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n < 1e-9:
        return (0.0, 1.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _len(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _tp(m, p):
    return (m[0, 0] * p[0] + m[0, 1] * p[1] + m[0, 2] * p[2] + m[0, 3],
            m[1, 0] * p[0] + m[1, 1] * p[1] + m[1, 2] * p[2] + m[1, 3],
            m[2, 0] * p[0] + m[2, 1] * p[1] + m[2, 2] * p[2] + m[2, 3])


# ---------------------------------------------------------------- mesh building
class MeshBuilder:
    def __init__(self):
        self.v = []
        self.extra = []

    def _push(self, p, n, uv, c, layer):
        self.v.extend((p[0], p[1], p[2], n[0], n[1], n[2], uv[0], uv[1], c[0], c[1], c[2], layer))

    def quad(self, p0, p1, p2, p3, layer, col=(1, 1, 1), uvs=None, uscale=0.5, vscale=0.5):
        e1 = _sub(p1, p0)
        e2 = _sub(p3, p0)
        n = _norm(_cross(e1, e2))
        if uvs is None:
            lu = _len(e1) * uscale
            lv = _len(e2) * vscale
            uvs = ((0, 0), (lu, 0), (lu, lv), (0, lv))
        for i in (0, 1, 2, 0, 2, 3):
            self._push((p0, p1, p2, p3)[i], n, uvs[i], col, layer)

    def quad_world(self, p0, p1, p2, p3, layer, col=(1, 1, 1), scale=0.5, axis='y'):
        """UVs from world coordinates (good for floors / walls that must tile seamlessly)."""
        pts = (p0, p1, p2, p3)
        uvs = []
        for p in pts:
            if axis == 'y':
                uvs.append((p[0] * scale, p[2] * scale))
            elif axis == 'x':
                uvs.append((p[2] * scale, p[1] * scale))
            else:
                uvs.append((p[0] * scale, p[1] * scale))
        self.quad(p0, p1, p2, p3, layer, col, uvs=uvs)

    def facing_quad(self, center, normal, w, h, layer, col=(1, 1, 1), up=(0.0, 1.0, 0.0), uv=None):
        n = _norm(normal)
        f = (-n[0], -n[1], -n[2])
        r = _norm(_cross(f, up))
        u = _norm(_cross(r, f))
        cx, cy, cz = center
        hw, hh = w / 2, h / 2
        p0 = (cx - r[0] * hw - u[0] * hh, cy - r[1] * hw - u[1] * hh, cz - r[2] * hw - u[2] * hh)
        p1 = (cx + r[0] * hw - u[0] * hh, cy + r[1] * hw - u[1] * hh, cz + r[2] * hw - u[2] * hh)
        p2 = (cx + r[0] * hw + u[0] * hh, cy + r[1] * hw + u[1] * hh, cz + r[2] * hw + u[2] * hh)
        p3 = (cx - r[0] * hw + u[0] * hh, cy - r[1] * hw + u[1] * hh, cz - r[2] * hw + u[2] * hh)
        self.quad(p0, p1, p2, p3, layer, col, uvs=uv or ((0, 0), (1, 0), (1, 1), (0, 1)))

    def box(self, center, size, layer, col=(1, 1, 1), m=None, uvscale=0.5):
        cx, cy, cz = center
        hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
        c = [(cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz), (cx + hx, cy + hy, cz - hz), (cx - hx, cy + hy, cz - hz),
             (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz), (cx + hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz + hz)]
        if m is not None:
            c = [_tp(m, p) for p in c]
        sx, sy, sz = size[0] * uvscale, size[1] * uvscale, size[2] * uvscale
        faces = [((4, 5, 6, 7), sx, sy), ((1, 0, 3, 2), sx, sy), ((0, 4, 7, 3), sz, sy),
                 ((5, 1, 2, 6), sz, sy), ((7, 6, 2, 3), sx, sz), ((0, 1, 5, 4), sx, sz)]
        for (a, b, cc, d), uw, vh in faces:
            self.quad(c[a], c[b], c[cc], c[d], layer, col, uvs=((0, 0), (uw, 0), (uw, vh), (0, vh)))

    def cylinder(self, r0, r1, h, segs, layer, col=(1, 1, 1), m=None, uvscale=0.5, cap=False):
        """Vertical cylinder/cone from y=0..h in local space, optionally transformed by m."""
        circ = 2 * math.pi * max(r0, r1)
        pts = []
        for i in range(segs + 1):
            a = 2 * math.pi * i / segs
            ca, sa = math.cos(a), math.sin(a)
            pts.append(((r0 * ca, 0.0, r0 * sa), (r1 * ca, h, r1 * sa)))
        if m is not None:
            pts = [(_tp(m, a), _tp(m, b)) for a, b in pts]
        for i in range(segs):
            b0, t0 = pts[i]
            b1, t1 = pts[i + 1]
            u0 = circ * uvscale * i / segs
            u1 = circ * uvscale * (i + 1) / segs
            self.quad(b0, b1, t1, t0, layer, col, uvs=((u0, 0), (u1, 0), (u1, h * uvscale), (u0, h * uvscale)))
        if cap and r1 > 0:
            ctr = (0.0, h, 0.0) if m is None else _tp(m, (0.0, h, 0.0))
            for i in range(segs):
                self.quad(ctr, pts[i][1], pts[i + 1][1], ctr, layer, col, uvs=((0.5, 0.5), (0, 0), (1, 0), (0.5, 0.5)))

    def add_array(self, arr):
        self.extra.append(np.asarray(arr, dtype=np.float32).reshape(-1, 12))

    def array(self):
        parts = []
        if self.v:
            parts.append(np.array(self.v, dtype=np.float32).reshape(-1, 12))
        parts.extend(self.extra)
        if not parts:
            return np.zeros((3, 12), np.float32)
        return np.concatenate(parts, 0)


def pipe(b, a, c, r, layer, col=(1, 1, 1), segs=8):
    """Axis-aligned pipe from point a to point c."""
    dx, dy, dz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    if abs(dy) >= abs(dx) and abs(dy) >= abs(dz):
        start = a if dy > 0 else c
        m = T(*start)
        ln = abs(dy)
    elif abs(dx) >= abs(dz):
        start = a if dx > 0 else c
        m = T(*start) @ RZ(-math.pi / 2)
        ln = abs(dx)
    else:
        start = a if dz > 0 else c
        m = T(*start) @ RX(math.pi / 2)
        ln = abs(dz)
    b.cylinder(r, r, ln, segs, layer, col, m=m)


# ---------------------------------------------------------------- shaders
SCENE_VS = """
#version 330
uniform mat4 u_proj;
uniform mat4 u_view;
uniform mat4 u_model;
in vec3 in_pos;
in vec3 in_norm;
in vec2 in_uv;
in vec3 in_col;
in float in_layer;
out vec3 v_wpos;
out vec3 v_norm;
out vec2 v_uv;
out vec3 v_col;
flat out float v_layer;
void main() {
    vec4 wp = u_model * vec4(in_pos, 1.0);
    v_wpos = wp.xyz;
    v_norm = mat3(u_model) * in_norm;
    v_uv = in_uv;
    v_col = in_col;
    v_layer = in_layer;
    gl_Position = u_proj * u_view * wp;
}
"""

SCENE_FS = """
#version 330
uniform sampler2DArray u_tex;
uniform vec3 u_campos;
uniform vec3 u_flashpos;
uniform vec3 u_flashdir;
uniform float u_flash;
uniform vec3 u_ambient;
uniform vec3 u_moondir;
uniform vec3 u_mooncol;
uniform vec3 u_fogcol;
uniform float u_fogdens;
uniform int u_nlights;
uniform vec4 u_lpos[8];
uniform vec3 u_lcol[8];
uniform float u_time;
uniform float u_nofog;
uniform vec3 u_tint;
uniform vec4 u_clip;
uniform float u_cliptop;
in vec3 v_wpos;
in vec3 v_norm;
in vec2 v_uv;
in vec3 v_col;
flat in float v_layer;
out vec4 f_color;
void main() {
    if (v_wpos.x > u_clip.x && v_wpos.x < u_clip.z && v_wpos.z > u_clip.y && v_wpos.z < u_clip.w
        && v_wpos.y < u_cliptop) discard;   // e.g. no snow inside the cabin
    float lay = v_layer;
    bool emis = false;
    if (lay > 99.5) { emis = true; lay -= 100.0; }
    bool water = abs(lay - 4.0) < 0.1;
    vec2 uv = v_uv;
    if (water) uv += vec2(sin(u_time * 0.3 + v_wpos.z * 0.5) * 0.05, u_time * 0.04);
    vec4 t = texture(u_tex, vec3(uv, lay));
    if (t.a < 0.5) discard;
    vec3 base = t.rgb * v_col * u_tint;
    float dist = length(v_wpos - u_campos);
    vec3 col;
    if (emis) {
        col = base;
    } else {
        vec3 n = normalize(v_norm);
        vec3 V = normalize(u_campos - v_wpos);
        if (dot(n, V) < 0.0) n = -n;
        if (water) {
            n = normalize(n + vec3(sin(v_wpos.x * 3.1 + u_time * 1.3) * 0.07, 0.0,
                                   cos(v_wpos.z * 2.7 + u_time * 1.1) * 0.07));
        }
        vec3 light = u_ambient;
        light += u_mooncol * max(dot(n, -u_moondir), 0.0);
        vec3 Lf = u_flashpos - v_wpos;
        float df = length(Lf);
        Lf /= max(df, 1e-4);
        float ca = dot(-Lf, u_flashdir);
        float spot = smoothstep(0.88, 0.975, ca) * 0.85 + smoothstep(0.66, 0.9, ca) * 0.35;
        float att = 1.0 / (1.0 + 0.04 * df + 0.035 * df * df);
        float ndl = max(dot(n, Lf), 0.0);
        light += vec3(1.0, 0.93, 0.80) * (u_flash * spot * att * 3.2 * ndl);
        for (int i = 0; i < 8; i++) {
            if (i >= u_nlights) break;
            vec3 Lp = u_lpos[i].xyz - v_wpos;
            float dp = length(Lp);
            float a = clamp(1.0 - dp / u_lpos[i].w, 0.0, 1.0);
            a *= a;
            light += u_lcol[i] * a * (0.25 + 0.75 * max(dot(n, Lp / max(dp, 1e-4)), 0.0));
        }
        col = base * light;
        if (water) {
            vec3 H = normalize(Lf + V);
            float sp = pow(max(dot(n, H), 0.0), 70.0);
            col += vec3(0.9, 0.85, 0.7) * sp * u_flash * spot * att * 2.5;
        }
    }
    if (u_nofog < 0.5) {
        float fg = 1.0 - exp(-pow(dist * u_fogdens, 2.0));
        col = mix(col, u_fogcol, fg);
    }
    f_color = vec4(col, 1.0);
}
"""

POST_VS = """
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

POST_FS = """
#version 330
uniform sampler2D u_scene;
uniform sampler2D u_ui;
uniform float u_time;
uniform float u_grain;
uniform float u_vhs;
uniform float u_bright;
uniform float u_fear;
uniform float u_red;
uniform float u_glitch;
uniform float u_fade;
uniform vec2 u_res;
in vec2 v_uv;
out vec4 f_color;
float rand(vec2 co) { return fract(sin(dot(co, vec2(12.9898, 78.233))) * 43758.5453); }
void main() {
    vec2 uv = v_uv;
    float g = clamp(u_glitch + u_fear * 0.25 * u_vhs, 0.0, 1.5);
    float line = floor(uv.y * 90.0);
    float tq = floor(u_time * 24.0);
    float sel = step(1.0 - g * 0.6, rand(vec2(tq, line * 0.37)));
    uv.x += (rand(vec2(line, tq)) - 0.5) * 0.06 * g * sel;
    // slow tape wobble
    uv.x += sin(uv.y * 12.0 + u_time * 1.7) * 0.0006 * u_vhs;
    float ca = (0.0012 + 0.005 * u_fear + 0.012 * u_glitch) * (0.4 + 0.6 * u_vhs);
    vec3 c;
    c.r = texture(u_scene, uv + vec2(ca, 0.0)).r;
    c.g = texture(u_scene, uv).g;
    c.b = texture(u_scene, uv - vec2(ca, 0.0)).b;
    c *= u_bright;
    c = pow(max(c, 0.0), vec3(0.92));
    float lum = dot(c, vec3(0.3, 0.59, 0.11));
    c = mix(c, vec3(lum), 0.22);
    c += (rand(uv * u_res + fract(u_time * 7.13) * 100.0) - 0.5) * u_grain * (0.07 + 0.12 * u_fear + 0.2 * u_glitch);
    c *= mix(1.0, 0.9 + 0.1 * sin(v_uv.y * u_res.y * 1.5708), u_vhs);
    float vig = smoothstep(0.95, 0.30, length(v_uv - 0.5) * (1.0 + u_fear * 0.5));
    c *= mix(0.3, 1.0, vig);
    c = mix(c, vec3(lum * 1.6 + 0.12, lum * 0.15, lum * 0.12), u_red);
    c *= (1.0 - u_fade);
    vec4 ui = texture(u_ui, vec2(v_uv.x, 1.0 - v_uv.y));
    c = mix(c, ui.rgb, ui.a);
    f_color = vec4(c, 1.0);
}
"""


def setu(prog, name, value):
    if name in prog:
        prog[name].value = value


def setm(prog, name, m):
    if name in prog:
        prog[name].write(np.ascontiguousarray(m.T, dtype=np.float32).tobytes())


class Mesh:
    def __init__(self, ctx, prog, data):
        data = np.ascontiguousarray(data, dtype=np.float32)
        self.vbo = ctx.buffer(data.tobytes())
        self.vao = ctx.vertex_array(
            prog, [(self.vbo, '3f 3f 2f 3f 1f', 'in_pos', 'in_norm', 'in_uv', 'in_col', 'in_layer')],
            skip_errors=True)
        self.count = len(data)

    def render(self):
        self.vao.render(moderngl.TRIANGLES)


RES_HEIGHTS = {"360p": 360, "480p": 480, "720p": 720}


class Renderer:
    def __init__(self, ctx, win_w, win_h, tex_data):
        self.ctx = ctx
        self.win_w, self.win_h = win_w, win_h
        self.prog = ctx.program(vertex_shader=SCENE_VS, fragment_shader=SCENE_FS)
        self.post = ctx.program(vertex_shader=POST_VS, fragment_shader=POST_FS)
        q = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype=np.float32)
        self.qvbo = ctx.buffer(q.tobytes())
        self.qvao = ctx.vertex_array(self.post, [(self.qvbo, '2f', 'in_vert')], skip_errors=True)
        layers, h, w = tex_data.shape[0], tex_data.shape[1], tex_data.shape[2]
        self.tex = ctx.texture_array((w, h, layers), 4, tex_data.tobytes())
        self.tex.build_mipmaps()
        self.tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.NEAREST)
        try:
            self.tex.anisotropy = 4.0
        except Exception:
            pass
        self.ui_h = 540
        self.ui_w = int(round(540 * win_w / win_h))
        self.ui_tex = ctx.texture((self.ui_w, self.ui_h), 4)
        self.ui_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.fbo = None
        self.scene_tex = None
        self.depth = None
        self.set_resolution("480p")
        setu(self.prog, 'u_tex', 0)
        setu(self.post, 'u_scene', 0)
        setu(self.post, 'u_ui', 1)

    def set_resolution(self, res):
        if res in RES_HEIGHTS:
            h = min(RES_HEIGHTS[res], self.win_h)
        else:
            h = self.win_h
        w = max(1, int(round(h * self.win_w / self.win_h)))
        for o in (self.fbo, self.scene_tex, self.depth):
            if o is not None:
                o.release()
        self.rw, self.rh = w, h
        self.scene_tex = self.ctx.texture((w, h), 3)
        self.scene_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.scene_tex.repeat_x = False
        self.scene_tex.repeat_y = False
        self.depth = self.ctx.depth_renderbuffer((w, h))
        self.fbo = self.ctx.framebuffer([self.scene_tex], self.depth)

    def begin(self, cam_pos, cam_fwd, fov, env, time, flash_on, flash_pos, flash_dir, lights, far=140.0, up=(0.0, 1.0, 0.0)):
        if getattr(self, 'fullbright', False):
            env = dict(env, ambient=(1.05, 1.05, 1.05), mooncol=(0.0, 0.0, 0.0), fogdens=0.0)
        ctx = self.ctx
        self.fbo.use()
        ctx.viewport = (0, 0, self.rw, self.rh)
        fc = env['fog']
        self.fbo.clear(fc[0], fc[1], fc[2], 1.0, depth=1.0)
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.disable(moderngl.CULL_FACE)
        p = self.prog
        proj = perspective(fov, self.rw / self.rh, 0.05, far)
        view = view_matrix(cam_pos, cam_fwd, up)
        setm(p, 'u_proj', proj)
        setm(p, 'u_view', view)
        setm(p, 'u_model', IDENT)
        setu(p, 'u_campos', tuple(float(v) for v in cam_pos))
        setu(p, 'u_flashpos', tuple(float(v) for v in flash_pos))
        setu(p, 'u_flashdir', tuple(float(v) for v in flash_dir))
        setu(p, 'u_flash', float(flash_on))
        setu(p, 'u_ambient', env['ambient'])
        setu(p, 'u_moondir', env['moondir'])
        setu(p, 'u_mooncol', env['mooncol'])
        setu(p, 'u_fogcol', env['fog'])
        setu(p, 'u_fogdens', env['fogdens'])
        setu(p, 'u_time', float(time))
        setu(p, 'u_nofog', 0.0)
        setu(p, 'u_tint', (1.0, 1.0, 1.0))
        self.set_clip(None)
        n = min(8, len(lights))
        lp = np.zeros((8, 4), np.float32)
        lc = np.zeros((8, 3), np.float32)
        for i in range(n):
            pos, rad, colr = lights[i]
            lp[i, :3] = pos
            lp[i, 3] = rad
            lc[i] = colr
        setu(p, 'u_nlights', n)
        if 'u_lpos' in p:
            p['u_lpos'].write(lp.tobytes())
        if 'u_lcol' in p:
            p['u_lcol'].write(lc.tobytes())
        self.tex.use(0)
        self._model_is_ident = True

    def set_clip(self, box=None):
        """Hide everything drawn after this inside box = (x0, z0, x1, z1, y_top); None turns it off."""
        p = self.prog
        if box is None:
            setu(p, 'u_clip', (1.0, 1.0, -1.0, -1.0))
            setu(p, 'u_cliptop', -1e9)
        else:
            setu(p, 'u_clip', tuple(float(v) for v in box[:4]))
            setu(p, 'u_cliptop', float(box[4]))

    def draw(self, mesh, model=None, tint=None, nofog=False):
        p = self.prog
        if model is None:
            if not self._model_is_ident:
                setm(p, 'u_model', IDENT)
                self._model_is_ident = True
        else:
            setm(p, 'u_model', model)
            self._model_is_ident = False
        if tint is not None:
            setu(p, 'u_tint', tint)
        if nofog:
            setu(p, 'u_nofog', 1.0)
        mesh.render()
        if tint is not None:
            setu(p, 'u_tint', (1.0, 1.0, 1.0))
        if nofog:
            setu(p, 'u_nofog', 0.0)

    def finish(self, ui_bytes, time, post):
        ctx = self.ctx
        ctx.screen.use()
        ctx.viewport = (0, 0, self.win_w, self.win_h)
        ctx.disable(moderngl.DEPTH_TEST)
        self.ui_tex.write(ui_bytes)
        self.scene_tex.use(0)
        self.ui_tex.use(1)
        pp = self.post
        setu(pp, 'u_time', float(time))
        setu(pp, 'u_res', (float(self.rw), float(self.rh)))
        for k in ('grain', 'vhs', 'bright', 'fear', 'red', 'glitch', 'fade'):
            setu(pp, 'u_' + k, float(post.get(k, 0.0)))
        self.qvao.render(moderngl.TRIANGLE_STRIP)


if moderngl is None:
    from engine_web import Mesh, Renderer  # noqa: F811,E402
