// MOOSE MAN in the browser.
//
// The game itself is the same Python as the .exe, running in Pyodide. This file
// is everything around it: the WebGL2 renderer (the same shaders as engine.py),
// WebAudio sound, keyboard / mouse / touch input, the co-op connection to
// Supabase Realtime, and the loading screen.
'use strict';

const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.27.2/full/';
const mm = (window.mm = {});
const canvas = document.getElementById('game');
const gl = canvas.getContext('webgl2', { antialias: false, alpha: false, preserveDrawingBuffer: false });
const isTouch = matchMedia('(pointer: coarse)').matches || 'ontouchstart' in window;
const $ = (id) => document.getElementById(id);

// ============================================================== renderer
const SCENE_VS = `#version 300 es
precision highp float;
uniform mat4 u_proj; uniform mat4 u_view; uniform mat4 u_model;
in vec3 in_pos; in vec3 in_norm; in vec2 in_uv; in vec3 in_col; in float in_layer;
out vec3 v_wpos; out vec3 v_norm; out vec2 v_uv; out vec3 v_col; flat out float v_layer;
void main() {
  vec4 wp = u_model * vec4(in_pos, 1.0);
  v_wpos = wp.xyz; v_norm = mat3(u_model) * in_norm; v_uv = in_uv; v_col = in_col; v_layer = in_layer;
  gl_Position = u_proj * u_view * wp;
}`;
const SCENE_FS = `#version 300 es
precision highp float; precision highp sampler2DArray;
uniform sampler2DArray u_tex;
uniform vec3 u_campos; uniform vec3 u_flashpos; uniform vec3 u_flashdir; uniform float u_flash;
uniform vec3 u_ambient; uniform vec3 u_moondir; uniform vec3 u_mooncol; uniform vec3 u_fogcol; uniform float u_fogdens;
uniform int u_nlights; uniform vec4 u_lpos[8]; uniform vec3 u_lcol[8];
uniform float u_time; uniform float u_nofog; uniform vec3 u_tint;
in vec3 v_wpos; in vec3 v_norm; in vec2 v_uv; in vec3 v_col; flat in float v_layer;
out vec4 f_color;
void main() {
  float lay = v_layer; bool emis = false;
  if (lay > 99.5) { emis = true; lay -= 100.0; }
  bool water = abs(lay - 4.0) < 0.1;
  vec2 uv = v_uv;
  if (water) uv += vec2(sin(u_time * 0.3 + v_wpos.z * 0.5) * 0.05, u_time * 0.04);
  vec4 t = texture(u_tex, vec3(uv, lay));
  if (t.a < 0.5) discard;
  vec3 base = t.rgb * v_col * u_tint;
  float dist = length(v_wpos - u_campos);
  vec3 col;
  if (emis) { col = base; } else {
    vec3 n = normalize(v_norm); vec3 V = normalize(u_campos - v_wpos);
    if (dot(n, V) < 0.0) n = -n;
    if (water) n = normalize(n + vec3(sin(v_wpos.x * 3.1 + u_time * 1.3) * 0.07, 0.0, cos(v_wpos.z * 2.7 + u_time * 1.1) * 0.07));
    vec3 light = u_ambient + u_mooncol * max(dot(n, -u_moondir), 0.0);
    vec3 Lf = u_flashpos - v_wpos; float df = length(Lf); Lf /= max(df, 1e-4);
    float ca = dot(-Lf, u_flashdir);
    float spot = smoothstep(0.88, 0.975, ca) * 0.85 + smoothstep(0.66, 0.9, ca) * 0.35;
    float att = 1.0 / (1.0 + 0.04 * df + 0.035 * df * df);
    light += vec3(1.0, 0.93, 0.80) * (u_flash * spot * att * 3.2 * max(dot(n, Lf), 0.0));
    for (int i = 0; i < 8; i++) {
      if (i >= u_nlights) break;
      vec3 Lp = u_lpos[i].xyz - v_wpos; float dp = length(Lp);
      float a = clamp(1.0 - dp / u_lpos[i].w, 0.0, 1.0); a *= a;
      light += u_lcol[i] * a * (0.25 + 0.75 * max(dot(n, Lp / max(dp, 1e-4)), 0.0));
    }
    col = base * light;
    if (water) {
      vec3 H = normalize(Lf + V);
      col += vec3(0.9, 0.85, 0.7) * pow(max(dot(n, H), 0.0), 70.0) * u_flash * spot * att * 2.5;
    }
  }
  if (u_nofog < 0.5) col = mix(col, u_fogcol, 1.0 - exp(-pow(dist * u_fogdens, 2.0)));
  f_color = vec4(col, 1.0);
}`;
const POST_VS = `#version 300 es
in vec2 in_vert; out vec2 v_uv;
void main() { v_uv = in_vert * 0.5 + 0.5; gl_Position = vec4(in_vert, 0.0, 1.0); }`;
const POST_FS = `#version 300 es
precision highp float;
uniform sampler2D u_scene; uniform sampler2D u_ui;
uniform float u_time; uniform float u_grain; uniform float u_vhs; uniform float u_bright; uniform float u_fear;
uniform float u_red; uniform float u_glitch; uniform float u_fade; uniform vec2 u_res;
in vec2 v_uv; out vec4 f_color;
float rand(vec2 co) { return fract(sin(dot(co, vec2(12.9898, 78.233))) * 43758.5453); }
void main() {
  vec2 uv = v_uv;
  float g = clamp(u_glitch + u_fear * 0.25 * u_vhs, 0.0, 1.5);
  float line = floor(uv.y * 90.0); float tq = floor(u_time * 24.0);
  float sel = step(1.0 - g * 0.6, rand(vec2(tq, line * 0.37)));
  uv.x += (rand(vec2(line, tq)) - 0.5) * 0.06 * g * sel;
  uv.x += sin(uv.y * 12.0 + u_time * 1.7) * 0.0006 * u_vhs;
  float ca = (0.0012 + 0.005 * u_fear + 0.012 * u_glitch) * (0.4 + 0.6 * u_vhs);
  vec3 c;
  c.r = texture(u_scene, uv + vec2(ca, 0.0)).r; c.g = texture(u_scene, uv).g; c.b = texture(u_scene, uv - vec2(ca, 0.0)).b;
  c *= u_bright; c = pow(max(c, 0.0), vec3(0.92));
  float lum = dot(c, vec3(0.3, 0.59, 0.11)); c = mix(c, vec3(lum), 0.22);
  c += (rand(uv * u_res + fract(u_time * 7.13) * 100.0) - 0.5) * u_grain * (0.07 + 0.12 * u_fear + 0.2 * u_glitch);
  c *= mix(1.0, 0.9 + 0.1 * sin(v_uv.y * u_res.y * 1.5708), u_vhs);
  float vig = smoothstep(0.95, 0.30, length(v_uv - 0.5) * (1.0 + u_fear * 0.5));
  c *= mix(0.3, 1.0, vig);
  c = mix(c, vec3(lum * 1.6 + 0.12, lum * 0.15, lum * 0.12), u_red);
  c *= (1.0 - u_fade);
  vec4 ui = texture(u_ui, vec2(v_uv.x, 1.0 - v_uv.y));
  c = mix(c, ui.rgb, ui.a);
  f_color = vec4(c, 1.0);
}`;

function compile(vs, fs) {
  const p = gl.createProgram();
  for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    gl.attachShader(p, s);
  }
  gl.bindAttribLocation(p, 0, 'in_pos'); gl.bindAttribLocation(p, 1, 'in_norm'); gl.bindAttribLocation(p, 2, 'in_uv');
  gl.bindAttribLocation(p, 3, 'in_col'); gl.bindAttribLocation(p, 4, 'in_layer'); gl.bindAttribLocation(p, 0, 'in_vert');
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  const u = {};
  const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < n; i++) {
    const info = gl.getActiveUniform(p, i);
    u[info.name.replace('[0]', '')] = gl.getUniformLocation(p, info.name);
  }
  return { p, u };
}

let scene = null, post = null, quad = null;
const meshes = new Map();
let texArray = null, uiTex = null, fbo = null, sceneTex = null, depthRb = null;
let rw = 640, rh = 360;

function initGL() {
  scene = compile(SCENE_VS, SCENE_FS);
  post = compile(POST_VS, POST_FS);
  quad = gl.createVertexArray();
  gl.bindVertexArray(quad);
  const qb = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, qb);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  gl.bindVertexArray(null);
  uiTex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, uiTex);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
}

mm.newMesh = (id, data) => {
  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);
  const b = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, b);
  gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
  const st = 48;
  const lay = [[0, 3, 0], [1, 3, 12], [2, 2, 24], [3, 3, 32], [4, 1, 44]];
  for (const [loc, size, off] of lay) {
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, size, gl.FLOAT, false, st, off);
  }
  gl.bindVertexArray(null);
  meshes.set(id, { vao, count: data.length / 12 });
};

mm.setTextures = (data, w, h, layers) => {
  texArray = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D_ARRAY, texArray);
  gl.texImage3D(gl.TEXTURE_2D_ARRAY, 0, gl.RGBA8, w, h, layers, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
  gl.generateMipmap(gl.TEXTURE_2D_ARRAY);
  gl.texParameteri(gl.TEXTURE_2D_ARRAY, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
  gl.texParameteri(gl.TEXTURE_2D_ARRAY, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  const an = gl.getExtension('EXT_texture_filter_anisotropic');
  if (an) gl.texParameterf(gl.TEXTURE_2D_ARRAY, an.TEXTURE_MAX_ANISOTROPY_EXT, 4);
};

mm.setRes = (w, h) => {
  rw = w; rh = h;
  if (fbo) { gl.deleteFramebuffer(fbo); gl.deleteTexture(sceneTex); gl.deleteRenderbuffer(depthRb); }
  sceneTex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, sceneTex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  depthRb = gl.createRenderbuffer();
  gl.bindRenderbuffer(gl.RENDERBUFFER, depthRb);
  gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT24, w, h);
  fbo = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, sceneTex, 0);
  gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, depthRb);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
};

// one frame of draw commands from engine_web.py
mm.frame = (cmds, ui, uw, uh, pp) => {
  const u = scene.u;
  let i = 0;
  const n = cmds.length;
  let inScene = false;
  while (i < n) {
    const op = cmds[i];
    if (op === 1) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
      gl.viewport(0, 0, rw, rh);
      gl.clearColor(cmds[i + 53], cmds[i + 54], cmds[i + 55], 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST);
      gl.disable(gl.CULL_FACE);
      gl.useProgram(scene.p);
      gl.uniformMatrix4fv(u.u_proj, false, cmds.subarray(i + 1, i + 17));
      gl.uniformMatrix4fv(u.u_view, false, cmds.subarray(i + 17, i + 33));
      gl.uniform3fv(u.u_campos, cmds.subarray(i + 33, i + 36));
      gl.uniform3fv(u.u_flashpos, cmds.subarray(i + 36, i + 39));
      gl.uniform3fv(u.u_flashdir, cmds.subarray(i + 39, i + 42));
      gl.uniform1f(u.u_flash, cmds[i + 42]);
      gl.uniform3fv(u.u_ambient, cmds.subarray(i + 43, i + 46));
      gl.uniform3fv(u.u_moondir, cmds.subarray(i + 46, i + 49));
      gl.uniform3fv(u.u_mooncol, cmds.subarray(i + 49, i + 52));
      gl.uniform3fv(u.u_fogcol, cmds.subarray(i + 52, i + 55));
      gl.uniform1f(u.u_fogdens, cmds[i + 55]);
      gl.uniform1f(u.u_time, cmds[i + 56]);
      gl.uniform1i(u.u_nlights, cmds[i + 57]);
      gl.uniform4fv(u.u_lpos, cmds.subarray(i + 58, i + 90));
      gl.uniform3fv(u.u_lcol, cmds.subarray(i + 90, i + 114));
      gl.uniform1f(u.u_nofog, 0);
      gl.uniform3f(u.u_tint, 1, 1, 1);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D_ARRAY, texArray);
      gl.uniform1i(u.u_tex, 0);
      inScene = true;
      i += 114;
    } else if (op === 2) {
      const m = meshes.get(cmds[i + 1]);
      if (m && inScene) {
        const nofog = cmds[i + 2];
        if (nofog) gl.uniform1f(u.u_nofog, 1);
        gl.uniform3f(u.u_tint, cmds[i + 3], cmds[i + 4], cmds[i + 5]);
        gl.uniformMatrix4fv(u.u_model, false, cmds.subarray(i + 6, i + 22));
        gl.bindVertexArray(m.vao);
        gl.drawArrays(gl.TRIANGLES, 0, m.count);
        if (nofog) gl.uniform1f(u.u_nofog, 0);
      }
      i += 22;
    } else if (op === 3) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
      gl.viewport(0, 0, rw, rh);
      gl.clearColor(cmds[i + 1], cmds[i + 2], cmds[i + 3], 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      i += 4;
    } else {
      break;
    }
  }
  gl.bindVertexArray(null);
  // post: the camcorder look, and the UI on top
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.viewport(0, 0, canvas.width, canvas.height);
  gl.disable(gl.DEPTH_TEST);
  gl.useProgram(post.p);
  gl.activeTexture(gl.TEXTURE1);
  gl.bindTexture(gl.TEXTURE_2D, uiTex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, uw, uh, 0, gl.RGBA, gl.UNSIGNED_BYTE, ui);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, sceneTex);
  const pu = post.u;
  gl.uniform1i(pu.u_scene, 0); gl.uniform1i(pu.u_ui, 1);
  gl.uniform1f(pu.u_time, pp[0]); gl.uniform1f(pu.u_grain, pp[1]); gl.uniform1f(pu.u_vhs, pp[2]);
  gl.uniform1f(pu.u_bright, pp[3]); gl.uniform1f(pu.u_fear, pp[4]); gl.uniform1f(pu.u_red, pp[5]);
  gl.uniform1f(pu.u_glitch, pp[6]); gl.uniform1f(pu.u_fade, pp[7]);
  gl.uniform2f(pu.u_res, rw, rh);
  gl.bindVertexArray(quad);
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  gl.bindVertexArray(null);
};

// ============================================================== sound
let actx = null, master = null;
const sounds = new Map();
const loops = new Map();
let oneShots = [];

function audioInit() {
  if (actx) return;
  actx = new (window.AudioContext || window.webkitAudioContext)();
  master = actx.createGain();
  master.connect(actx.destination);
}
mm.addSound = (name, data, sr) => {
  audioInit();
  const buf = actx.createBuffer(1, data.length, sr);
  buf.copyToChannel(data, 0);
  sounds.set(name, buf);
};
function chain(vol, pan) {
  const g = actx.createGain();
  g.gain.value = vol;
  const p = actx.createStereoPanner();
  p.pan.value = pan;
  g.connect(p);
  p.connect(master);
  return { g, p };
}
mm.playSound = (name, vol, pan) => {
  const buf = sounds.get(name);
  if (!buf || !actx) return;
  const src = actx.createBufferSource();
  src.buffer = buf;
  const c = chain(vol, pan);
  src.connect(c.g);
  src.start();
  oneShots.push(src);
  src.onended = () => { oneShots = oneShots.filter((s) => s !== src); };
  if (oneShots.length > 48) { try { oneShots.shift().stop(); } catch (e) { /* already done */ } }
};
mm.loopSound = (name, vol, pan) => {
  if (!actx) return;
  let L = loops.get(name);
  if (vol <= 0) {
    if (L) { try { L.src.stop(); } catch (e) { /* stopped */ } loops.delete(name); }
    return;
  }
  if (!L) {
    const buf = sounds.get(name);
    if (!buf) return;
    const src = actx.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    const c = chain(vol, pan);
    src.connect(c.g);
    src.start();
    L = { src, g: c.g, p: c.p };
    loops.set(name, L);
  }
  L.g.gain.setTargetAtTime(vol, actx.currentTime, 0.03);
  L.p.pan.setTargetAtTime(pan, actx.currentTime, 0.03);
};
mm.stopAll = () => {
  for (const s of oneShots) { try { s.stop(); } catch (e) { /* stopped */ } }
  oneShots = [];
  for (const [, L] of loops) { try { L.src.stop(); } catch (e) { /* stopped */ } }
  loops.clear();
};
mm.pauseAudio = (p) => { if (actx) { if (p) actx.suspend(); else actx.resume(); } };

// ============================================================== input
let events = [];
let grabWanted = false;
let mode = 'menu';
const push = (e) => events.push(e);
function canvasPos(cx, cy) {
  const r = canvas.getBoundingClientRect();
  return { x: (cx - r.left) * (cw / r.width), y: (cy - r.top) * (ch / r.height) };
}
const GAME_KEYS = new Set(['Tab', 'Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Backspace', 'Escape', 'Enter']);
window.addEventListener('keydown', (e) => {
  if (!booted || document.activeElement === $('textin')) return;
  if (GAME_KEYS.has(e.code) || e.ctrlKey) e.preventDefault();
  if (e.repeat && mode !== 'text' && mode !== 'menu') return;
  push({ t: 'kd', code: e.code, key: e.key });
});
window.addEventListener('keyup', (e) => {
  if (!booted) return;
  push({ t: 'ku', code: e.code, key: e.key });
});
window.addEventListener('blur', () => push({ t: 'blur' }));
canvas.addEventListener('mousedown', (e) => {
  if (!booted) return;
  if (grabWanted && !isTouch && document.pointerLockElement !== canvas) {
    canvas.requestPointerLock();
    return;
  }
  const p = canvasPos(e.clientX, e.clientY);
  push({ t: 'md', b: e.button === 2 ? 3 : (e.button === 1 ? 2 : 1), x: p.x, y: p.y });
});
window.addEventListener('mouseup', (e) => {
  if (!booted) return;
  const p = canvasPos(e.clientX, e.clientY);
  push({ t: 'mu', b: e.button === 2 ? 3 : (e.button === 1 ? 2 : 1), x: p.x, y: p.y });
});
window.addEventListener('mousemove', (e) => {
  if (!booted || isTouch) return;
  const locked = document.pointerLockElement === canvas;
  const p = canvasPos(e.clientX, e.clientY);
  push({ t: 'mm', dx: locked ? e.movementX : 0, dy: locked ? e.movementY : 0, x: p.x, y: p.y });
});
canvas.addEventListener('contextmenu', (e) => e.preventDefault());
document.addEventListener('pointerlockchange', () => {
  // the browser drops the lock on Esc: treat that as Esc (pause)
  if (document.pointerLockElement !== canvas && grabWanted && mode.startsWith('play')) {
    push({ t: 'kd', code: 'Escape', key: 'Escape' });
    push({ t: 'ku', code: 'Escape', key: 'Escape' });
  }
});
mm.setGrab = (g) => {
  grabWanted = g;
  if (!g && document.pointerLockElement) document.exitPointerLock();
  $('clicklock').style.display = g && !isTouch && document.pointerLockElement !== canvas ? 'flex' : 'none';
};

// ---------------- touch controls
const held = new Map();     // touch id -> what it is doing
let stick = null;
function key(code, down) { push({ t: down ? 'kd' : 'ku', code, key: '' }); }
function setStickKeys(fx, fy, mag) {
  const want = {
    KeyW: fy > 0.35, KeyS: fy < -0.35, KeyD: fx > 0.35, KeyA: fx < -0.35, ShiftLeft: mag > 0.95 && fy > 0.5,
  };
  for (const k in want) {
    if (want[k] !== !!stick.keys[k]) { key(k, want[k]); stick.keys[k] = want[k]; }
  }
}
function releaseStick() {
  if (!stick) return;
  for (const k in stick.keys) if (stick.keys[k]) key(k, false);
  stick = null;
  $('stick').style.display = 'none';
}
function touchStart(e) {
  if (!booted) return;
  e.preventDefault();
  for (const t of e.changedTouches) {
    const p = canvasPos(t.clientX, t.clientY);
    if (!mode.startsWith('play')) {
      push({ t: 'md', b: 1, x: p.x, y: p.y });
      held.set(t.identifier, { kind: 'tap' });
      continue;
    }
    if (t.clientX < window.innerWidth * 0.4 && !stick) {
      stick = { id: t.identifier, x0: t.clientX, y0: t.clientY, keys: {} };
      const s = $('stick');
      s.style.display = 'block';
      s.style.left = (t.clientX - 60) + 'px';
      s.style.top = (t.clientY - 60) + 'px';
      $('knob').style.transform = 'translate(0px,0px)';
      held.set(t.identifier, { kind: 'stick' });
    } else {
      held.set(t.identifier, { kind: 'look', x: t.clientX, y: t.clientY });
    }
  }
}
function touchMove(e) {
  if (!booted) return;
  e.preventDefault();
  for (const t of e.changedTouches) {
    const h = held.get(t.identifier);
    if (!h) continue;
    if (h.kind === 'stick' && stick) {
      let dx = t.clientX - stick.x0, dy = t.clientY - stick.y0;
      const d = Math.hypot(dx, dy), R = 60;
      if (d > R) { dx *= R / d; dy *= R / d; }
      $('knob').style.transform = `translate(${dx}px,${dy}px)`;
      setStickKeys(dx / R, -dy / R, Math.min(1, d / R));
    } else if (h.kind === 'look') {
      const sens = 2.2;
      push({ t: 'mm', dx: (t.clientX - h.x) * sens, dy: (t.clientY - h.y) * sens, x: 0, y: 0 });
      h.x = t.clientX; h.y = t.clientY;
    }
  }
}
function touchEnd(e) {
  if (!booted) return;
  e.preventDefault();
  for (const t of e.changedTouches) {
    const h = held.get(t.identifier);
    held.delete(t.identifier);
    if (!h) continue;
    if (h.kind === 'stick') releaseStick();
    if (h.kind === 'tap') {
      const p = canvasPos(t.clientX, t.clientY);
      push({ t: 'mu', b: 1, x: p.x, y: p.y });
    }
  }
}
canvas.addEventListener('touchstart', touchStart, { passive: false });
canvas.addEventListener('touchmove', touchMove, { passive: false });
canvas.addEventListener('touchend', touchEnd, { passive: false });
canvas.addEventListener('touchcancel', touchEnd, { passive: false });

// on-screen buttons: each one is a key (or a mouse button) held while touched
let crouchOn = false;
for (const b of document.querySelectorAll('#pad [data-key]')) {
  const code = b.dataset.key;
  const down = (e) => {
    e.preventDefault(); e.stopPropagation();
    b.classList.add('on');
    if (code === 'Crouch') { crouchOn = !crouchOn; key('KeyC', crouchOn); b.classList.toggle('lit', crouchOn); return; }
    if (code === 'Fire') push({ t: 'md', b: 1, x: 0, y: 0 });
    else if (code === 'Aim') push({ t: 'md', b: 3, x: 0, y: 0 });
    else key(code, true);
  };
  const up = (e) => {
    e.preventDefault(); e.stopPropagation();
    b.classList.remove('on');
    if (code === 'Crouch') return;
    if (code === 'Fire') push({ t: 'mu', b: 1, x: 0, y: 0 });
    else if (code === 'Aim') push({ t: 'mu', b: 3, x: 0, y: 0 });
    else key(code, false);
  };
  b.addEventListener('touchstart', down, { passive: false });
  b.addEventListener('touchend', up, { passive: false });
  b.addEventListener('touchcancel', up, { passive: false });
  b.addEventListener('mousedown', down);
  b.addEventListener('mouseup', up);
}

// typing on a phone: a real text box, so the on-screen keyboard comes up
const textin = $('textin');
textin.addEventListener('input', () => {
  for (const ch of textin.value) push({ t: 'txt', ch });
  textin.value = '';
});
textin.addEventListener('keydown', (e) => {
  const fwd = { Enter: 'Enter', Backspace: 'Backspace', Escape: 'Escape', Tab: 'Tab', ArrowUp: 'ArrowUp', ArrowDown: 'ArrowDown' };
  if (fwd[e.key]) {
    e.preventDefault();
    const code = fwd[e.key];
    push({ t: 'kd', code, key: e.key });
    push({ t: 'ku', code, key: e.key });
  }
});
$('textok').addEventListener('click', () => { push({ t: 'kd', code: 'Enter', key: 'Enter' }); push({ t: 'ku', code: 'Enter', key: 'Enter' }); });

function applyMode(m) {
  if (m === mode) return;
  const was = mode;
  mode = m;
  const play = m.startsWith('play');
  document.body.classList.toggle('touchplay', isTouch && play);
  document.body.classList.toggle('gun', m.includes('gun'));
  document.body.classList.toggle('aim', m.includes('aim'));
  document.body.classList.toggle('reload', m.includes('reload'));
  if (!play) { releaseStick(); held.clear(); }
  const txt = m.startsWith('text');
  $('textbox').style.display = txt ? 'flex' : 'none';
  if (txt) {
    textin.type = m.includes('pw') ? 'password' : 'text';
    textin.autocapitalize = m.includes('user') ? 'none' : 'characters';
  }
  if (txt && !was.startsWith('text')) { textin.value = ''; setTimeout(() => textin.focus(), 50); }
  if (!txt && document.activeElement === textin) textin.blur();
  if (!play) $('clicklock').style.display = 'none';
  else mm.setGrab(grabWanted);
}

// ============================================================== co-op: Supabase Realtime (same protocol as net.py)
const nets = new Map();
let netSeq = 0;
mm.netOpen = (url, topic, pid, token) => {
  const h = ++netSeq;
  const n = { url, topic, pid, token, state: 'connecting', error: '', inbox: [], pending: [], everOk: false, ref: 0, fails: 0, ws: null, hb: null };
  nets.set(h, n);
  netConnect(n);
  return h;
};
function netRaw(n, topic, event, payload) {
  n.ref += 1;
  const msg = { topic, event, payload, ref: String(n.ref) };
  if (topic === n.topic) msg.join_ref = '1';
  n.ws.send(JSON.stringify(msg));
}
function netConnect(n) {
  let ws;
  try { ws = new WebSocket(n.url); } catch (e) { n.state = 'dead'; n.error = 'could not connect'; return; }
  n.ws = ws;
  n.ref = 0;
  ws.onopen = () => {
    const cfg = { config: { broadcast: { self: false, ack: false }, presence: { key: '' }, private: false } };
    if (n.token) cfg.access_token = n.token;
    netRaw(n, n.topic, 'phx_join', cfg);
    clearInterval(n.hb);
    n.hb = setInterval(() => { if (n.state === 'ok') { try { netRaw(n, 'phoenix', 'heartbeat', {}); } catch (e) { /* reconnecting */ } } }, 15000);
  };
  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    const pl = msg.payload || {};
    if (msg.event === 'phx_reply' && msg.ref === '1') {
      if (pl.status === 'ok') {
        n.state = 'ok'; n.everOk = true; n.fails = 0;
        const pend = n.pending; n.pending = [];
        for (const [kind, inner] of pend) mm.netSend(netKey(n), kind, inner);
      } else { n.state = 'dead'; n.error = 'the server refused the room'; ws.close(); }
    } else if (msg.event === 'broadcast') {
      n.inbox.push([pl.event, pl.payload || {}]);
    }
  };
  ws.onclose = () => {
    clearInterval(n.hb);
    if (n.state === 'closed' || n.state === 'dead') return;
    n.state = 'connecting';
    n.fails += 1;
    if (n.fails >= (n.everOk ? 8 : 3)) { n.state = 'dead'; n.error = n.error || 'the connection dropped'; return; }
    setTimeout(() => netConnect(n), Math.min(4000, 400 * n.fails));
  };
}
function netKey(n) { for (const [k, v] of nets) if (v === n) return k; return 0; }
mm.netState = (h) => { const n = nets.get(h); return n ? n.state : 'dead'; };
mm.netError = (h) => { const n = nets.get(h); return n ? n.error : ''; };
mm.netSend = (h, kind, innerJson) => {
  const n = nets.get(h);
  if (!n || n.state === 'closed' || n.state === 'dead') return false;
  const inner = typeof innerJson === 'string' ? JSON.parse(innerJson) : innerJson;
  if (n.state !== 'ok') {
    if (n.everOk && n.pending.length < 300) n.pending.push([kind, inner]);
    return false;
  }
  try {
    netRaw(n, n.topic, 'broadcast', { type: 'broadcast', event: kind, payload: inner });
    return true;
  } catch (e) {
    if (n.pending.length < 300) n.pending.push([kind, inner]);
    return false;
  }
};
mm.netTake = (h) => {
  const n = nets.get(h);
  if (!n || !n.inbox.length) return '';
  const out = JSON.stringify(n.inbox);
  n.inbox = [];
  return out;
};
mm.netClose = (h) => {
  const n = nets.get(h);
  if (!n) return;
  if (n.state === 'ok') { try { netRaw(n, n.topic, 'phx_leave', {}); } catch (e) { /* gone */ } }
  n.state = 'closed';
  clearInterval(n.hb);
  try { n.ws.close(); } catch (e) { /* gone */ }
};

// ============================================================== plain HTTP (accounts)
const https = new Map();
let httpSeq = 0;
mm.httpStart = (method, url, headersJson, body) => {
  const h = ++httpSeq;
  const opt = { method, headers: JSON.parse(headersJson) };
  if (body) opt.body = body;
  fetch(url, opt).then(async (r) => {
    https.set(h, JSON.stringify({ status: r.status, body: await r.text() }));
  }).catch(() => https.set(h, JSON.stringify({ status: 0, body: 'network' })));
  return h;
};
mm.httpResult = (h) => {
  const r = https.get(h);
  if (!r) return '';
  https.delete(h);
  return r;
};

// ============================================================== boot and the frame loop
let py = null, game = null, booted = false;
let cw = 960, ch = 540;
function fitCanvas() {
  const dpr = Math.min(window.devicePixelRatio || 1, isTouch ? 1.5 : 2);
  cw = Math.max(320, Math.round(window.innerWidth));
  ch = Math.max(200, Math.round(window.innerHeight));
  canvas.width = Math.round(cw * dpr);
  canvas.height = Math.round(ch * dpr);
}
window.addEventListener('resize', fitCanvas);

function status(t) { $('status').textContent = t; }

async function boot() {
  $('start').style.display = 'none';
  $('loading').style.display = 'flex';
  audioInit();
  actx.resume();
  if (isTouch && document.documentElement.requestFullscreen) {
    document.documentElement.requestFullscreen().catch(() => {});
    try { screen.orientation.lock('landscape').catch(() => {}); } catch (e) { /* not supported */ }
  }
  try {
    fitCanvas();
    initGL();
    status('starting Python...');
    const s = document.createElement('script');
    s.src = PYODIDE + 'pyodide.js';
    await new Promise((res, rej) => { s.onload = res; s.onerror = rej; document.head.appendChild(s); });
    py = await loadPyodide({ indexURL: PYODIDE });
    status('loading numpy and pygame...');
    await py.loadPackage(['numpy', 'pygame-ce']);
    status('loading the game...');
    const zip = await (await fetch('game.zip?v=' + window.MM_VERSION)).arrayBuffer();
    py.unpackArchive(zip, 'zip', { extractDir: '/game' });
    py.runPython("import sys; sys.path.insert(0, '/game')");
    if (isTouch) {
      // phones: start a little lighter
      const cur = JSON.parse(localStorage.getItem('mooseman.settings') || '{}');
      if (!cur.res) { cur.res = '360p'; localStorage.setItem('mooseman.settings', JSON.stringify(cur)); }
    }
    game = py.pyimport('web_main');
    game.boot(cw, ch);
    $('loading').style.display = 'none';
    const step = () => {
      let done = false;
      try { done = game.load_step(); } catch (e) { fail(e); return; }
      if (done) { booted = true; requestAnimationFrame(loop); } else setTimeout(step, 0);
    };
    setTimeout(step, 0);
  } catch (e) {
    fail(e);
  }
}

function fail(e) {
  console.error(e);
  $('loading').style.display = 'flex';
  status('Something went wrong: ' + (e && e.message ? e.message.split('\n').slice(-3).join(' ') : e));
}

let last = 0;
function loop(t) {
  const dt = last ? (t - last) / 1000 : 1 / 60;
  last = t;
  const ev = events.length ? JSON.stringify(events) : '';
  events = [];
  try {
    const m = game.frame(dt, ev, cw, ch);
    applyMode(String(m));
  } catch (e) {
    fail(e);
    return;
  }
  requestAnimationFrame(loop);
}

$('start').addEventListener('click', boot);
if (!gl) {
  $('start').style.display = 'none';
  $('loading').style.display = 'flex';
  status('Your browser does not support WebGL2, which Moose Man needs.');
}
document.body.classList.toggle('touch', isTouch);
