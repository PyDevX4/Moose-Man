"""Procedurally synthesized sound + simple positional audio on pygame.mixer."""
import math
import random
import numpy as np
import pygame

SR = 22050
_rng = np.random.default_rng(31)


def tt(sec):
    return np.arange(int(SR * sec)) / SR


def noise(n):
    return _rng.uniform(-1, 1, n)


def band(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    m = ((f >= lo) & (f <= hi)).astype(float)
    # soften the edges a bit
    k = np.ones(9) / 9
    m = np.convolve(m, k, mode='same')
    return np.fft.irfft(X * m, len(x))


def norm(x, peak=0.9):
    m = np.max(np.abs(x))
    return x * (peak / m) if m > 1e-9 else x


def echo(x, delay, fb, taps=4):
    d = int(delay * SR)
    out = np.zeros(len(x) + d * taps)
    out[:len(x)] += x
    g = 1.0
    for i in range(1, taps + 1):
        g *= fb
        out[d * i:d * i + len(x)] += x * g
    return out


def loopable(x, fade=0.5):
    n = int(fade * SR)
    head = x[:n].copy()
    body = x[n:].copy()
    ramp = np.linspace(0, 1, n)
    body[-n:] = body[-n:] * (1 - ramp) + head * ramp
    return body


def env_ad(n, a, d):
    t = np.arange(n) / SR
    e = np.minimum(1.0, t / max(a, 1e-4)) * np.exp(-np.maximum(0, t - a) * d)
    return e


def slow_mod(n, rate, depth=1.0):
    k = max(2, int(n / SR * rate) + 2)
    pts = _rng.random(k)
    xp = np.linspace(0, n, k)
    return 1 - depth + depth * np.interp(np.arange(n), xp, pts)


def saw(phase):
    return 2.0 * (phase / (2 * np.pi) % 1.0) - 1.0


def synth_all():
    s = {}
    # ---- forest ambience: wind + crickets
    n = int(SR * 12)
    t = np.arange(n) / SR
    wind = band(noise(n), 40, 420) * slow_mod(n, 0.4, 0.8) * 1.4
    wind += band(noise(n), 700, 1600) * slow_mod(n, 0.7, 1.0) * 0.12
    cr1 = np.sin(2 * np.pi * 4300 * t) * (np.sin(2 * np.pi * 28 * t) > 0.2) * (np.sin(2 * np.pi * 0.9 * t) > 0.1) * 0.045
    cr2 = np.sin(2 * np.pi * 3700 * t) * (np.sin(2 * np.pi * 21 * t) > 0.4) * (np.sin(2 * np.pi * 0.63 * t + 1) > 0.3) * 0.03
    s['forest_amb'] = loopable(norm(wind, 0.5) + cr1 + cr2, 1.0)

    # ---- sewer ambience: drone + hiss + distant metal groan
    n = int(SR * 14)
    t = np.arange(n) / SR
    drone = np.sin(2 * np.pi * 41 * t) * 0.25 + np.sin(2 * np.pi * 41.8 * t) * 0.2 + np.sin(2 * np.pi * 61.5 * t) * 0.06
    rumble = band(noise(n), 20, 140) * slow_mod(n, 0.3, 0.7) * 1.5
    hiss = band(noise(n), 2500, 7000) * 0.025 * slow_mod(n, 0.5, 0.5)
    gf = 170 - 40 * np.clip((t - 6) / 4, 0, 1)
    groan = np.sin(2 * np.pi * np.cumsum(gf) / SR + 3 * np.sin(2 * np.pi * 3 * t)) * np.exp(-((t - 8) / 1.5) ** 2) * 0.07
    s['sewer_amb'] = loopable(norm(drone + rumble, 0.5) + hiss + groan, 1.0)

    # ---- drip
    t = tt(0.25)
    f = 700 + 900 * np.exp(-t * 60)
    d = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 45)
    s['drip'] = norm(echo(d, 0.11, 0.45, 4), 0.6)

    # ---- footsteps
    for i in range(4):
        n = int(SR * 0.2)
        x = band(noise(n), 250, 3500) * env_ad(n, 0.01, 22)
        crack = (noise(n) > 0.93) * noise(n) * env_ad(n, 0.005, 30)
        s['step_grass%d' % i] = norm(x + crack * 0.5, 0.5)
    for i in range(4):
        n = int(SR * 0.14)
        tt_ = np.arange(n) / SR
        x = band(noise(n), 900, 5000) * np.exp(-tt_ * 90) + np.sin(2 * np.pi * (110 + i * 9) * tt_) * np.exp(-tt_ * 45) * 0.8
        s['step_conc%d' % i] = norm(echo(x, 0.085, 0.35, 4), 0.5)
    for i in range(3):
        n = int(SR * 0.4)
        x = band(noise(n), 350, 2600) * env_ad(n, 0.025, 10) * slow_mod(n, 40, 0.6)
        s['step_water%d' % i] = norm(echo(x, 0.09, 0.25, 3), 0.55)

    # ---- heartbeat
    t = tt(0.55)
    hb = np.sin(2 * np.pi * 52 * t) * np.exp(-t * 28) + np.sin(2 * np.pi * 46 * np.maximum(0, t - 0.17)) * np.exp(-np.maximum(0, t - 0.17) * 30) * (t > 0.17) * 0.7
    s['heart'] = norm(hb, 0.9)

    # ---- moose call: bellow that turns into something human
    t = tt(3.6)
    f0 = 115 - 50 * (t / 3.6) + 5 * np.sin(2 * np.pi * 5.5 * t)
    ph = 2 * np.pi * np.cumsum(f0) / SR
    tone = np.zeros_like(t)
    for h in range(1, 14):
        w = 1.0 / h
        fh = f0 * h
        w *= 1 + 1.5 * np.exp(-((fh - 420) / 150) ** 2) + 1.2 * np.exp(-((fh - 950) / 250) ** 2)
        tone += np.sin(ph * h) * w
    hum = np.sin(ph * 3.17 + 2 * np.sin(2 * np.pi * 7 * t)) * 0.25 * np.clip((t - 1.2) / 1.0, 0, 1)
    envv = np.clip(t / 0.35, 0, 1) * np.clip((3.6 - t) / 1.0, 0, 1)
    call = np.tanh((tone + hum) * 0.9) * envv
    call = band(call, 40, 3200)
    s['call_near'] = norm(echo(call, 0.12, 0.3, 4), 0.95)
    s['call_far'] = norm(echo(band(call, 40, 700), 0.31, 0.55, 6), 0.7)

    # ---- monster breath loop
    n = int(SR * 2.6)
    t = np.arange(n) / SR
    inh = band(noise(n), 250, 1400) * np.sin(np.clip(t / 1.0, 0, 1) * np.pi) ** 2 * (t < 1.0)
    exh_e = np.sin(np.clip((t - 1.15) / 1.2, 0, 1) * np.pi) ** 2 * (t > 1.15)
    exh = band(noise(n), 90, 900) * exh_e * 1.6 + np.sin(2 * np.pi * 58 * t) * exh_e * 0.35
    clicks = (noise(n) > 0.995) * 0.6 * exh_e
    s['breath'] = norm(np.tanh((inh + exh + clicks) * 1.5), 0.8)

    # ---- monster step: heavy thud + hoof click
    t = tt(0.35)
    th = np.sin(2 * np.pi * 48 * t) * np.exp(-t * 16) + band(noise(len(t)), 60, 300) * np.exp(-t * 20) * 0.6
    cl = band(noise(len(t)), 2200, 7000) * np.exp(-t * 160) * 0.9
    s['mstep'] = norm(echo(th + cl, 0.1, 0.3, 3), 0.9)

    # ---- jumpscare screech
    t = tt(1.8)
    sc = np.zeros_like(t)
    for fq in (880, 931, 1347, 1781, 2210):
        ph = 2 * np.pi * np.cumsum(fq * (1 + 0.03 * np.sin(2 * np.pi * 13 * t) + 0.02 * _rng.standard_normal(len(t)).cumsum() / 400)) / SR
        sc += saw(ph)
    sc += noise(len(t)) * 1.5 + np.sin(2 * np.pi * 70 * t) * 2
    sc = np.tanh(sc * 0.8) * np.clip((1.8 - t) / 0.8, 0, 1)
    s['screech'] = norm(sc, 1.0)

    # ---- valve creak loop
    n = int(SR * 2.4)
    t = np.arange(n) / SR
    f = 260 + 140 * np.sin(2 * np.pi * 0.8 * t) + 60 * slow_mod(n, 6, 1.0)
    stick = (band(noise(n), 0, 25) > 0.0).astype(float)
    stick = np.convolve(stick, np.ones(200) / 200, mode='same')
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR + 2.5 * np.sin(2 * np.pi * f * 2.01 * t / 1.0) * 0.3)
    cr = band(tone * stick + band(noise(n), 800, 3000) * 0.15 * stick, 150, 4000)
    s['creak'] = loopable(norm(cr, 0.7), 0.2)

    # ---- valve clunk
    t = tt(0.9)
    ck = sum(np.sin(2 * np.pi * fq * t) * np.exp(-t * dc) for fq, dc in ((140, 7), (433, 9), (612, 12), (1290, 18)))
    ck += band(noise(len(t)), 100, 2000) * np.exp(-t * 40) * 2
    s['clunk'] = norm(echo(ck, 0.15, 0.35, 4), 0.9)

    # ---- drain rumble
    n = int(SR * 8)
    t = np.arange(n) / SR
    dr = band(noise(n), 25, 260) * 2 * np.clip(t / 1.0, 0, 1) * np.clip((8 - t) / 3, 0, 1)
    for _ in range(80):
        st = _rng.uniform(0.3, 7.0)
        ln = _rng.uniform(0.04, 0.15)
        i0 = int(st * SR)
        i1 = min(n, i0 + int(ln * SR))
        tb = np.arange(i1 - i0) / SR
        fq = _rng.uniform(150, 500)
        dr[i0:i1] += np.sin(2 * np.pi * (fq + fq * 3 * tb / ln) * tb) * np.sin(np.pi * tb / ln) * 0.4
    s['drain'] = norm(echo(dr, 0.2, 0.4, 4), 0.9)

    # ---- paper rustle
    n = int(SR * 0.45)
    x = band(noise(n), 1800, 8000) * slow_mod(n, 60, 1.0) * env_ad(n, 0.02, 6)
    s['paper'] = norm(x, 0.5)

    # ---- flashlight click
    t = tt(0.05)
    s['click'] = norm(band(noise(len(t)), 2000, 8000) * np.exp(-t * 200), 0.5)

    # ---- whisper
    n = int(SR * 3.2)
    t = np.arange(n) / SR
    syl = np.abs(np.sin(2 * np.pi * 3.3 * t + 2 * np.sin(2 * np.pi * 0.7 * t))) ** 3
    wh = band(noise(n), 1500, 6500) * syl + band(noise(n), 500, 1200) * syl * 0.4
    wh *= np.clip(t / 0.5, 0, 1) * np.clip((3.2 - t) / 0.8, 0, 1)
    s['whisper'] = norm(echo(wh, 0.17, 0.4, 4), 0.5)

    # ---- stinger
    t = tt(4.0)
    st = sum(np.sin(2 * np.pi * fq * t + 0.5 * np.sin(2 * np.pi * 4 * t)) for fq in (55, 58.3, 77.8, 116.5, 123.5))
    st += band(noise(len(t)), 100, 1500) * 0.8
    st *= np.clip(t / 0.03, 0, 1) * np.exp(-t * 0.9)
    s['stinger'] = norm(np.tanh(st * 0.6), 0.8)

    # ---- static
    t = tt(0.5)
    s['static'] = norm(band(noise(len(t)), 900, 9000) * (0.6 + 0.4 * (noise(len(t)) > 0)), 0.45)

    # ---- branch snap
    t = tt(0.3)
    sn = band(noise(len(t)), 800, 6000) * np.exp(-t * 60) + band(noise(len(t)), 200, 900) * np.exp(-t * 25) * 0.5
    s['snap'] = norm(echo(sn, 0.13, 0.2, 2), 0.8)

    # ---- low drone for title / ending
    n = int(SR * 16)
    t = np.arange(n) / SR
    td = np.sin(2 * np.pi * 36.7 * t) * 0.3 + np.sin(2 * np.pi * 55 * t + np.sin(2 * np.pi * 0.1 * t) * 3) * 0.15
    td += band(noise(n), 30, 200) * slow_mod(n, 0.2, 0.8) * 1.2
    tone = np.sin(2 * np.pi * 440 * 1.4983 * t) * 0.012 * slow_mod(n, 0.3, 1.0)
    s['title_amb'] = loopable(norm(td, 0.55) + tone, 1.5)
    return s


class Audio:
    LOOPS = ('forest_amb', 'sewer_amb', 'breath', 'creak', 'title_amb')

    def __init__(self, volume=0.8):
        self.master = volume
        pygame.mixer.set_num_channels(40)
        pygame.mixer.set_reserved(len(self.LOOPS))
        raw = synth_all()
        self.sounds = {}
        for k, v in raw.items():
            a = np.clip(v, -1, 1)
            a16 = (a * 32000).astype(np.int16)
            st = np.ascontiguousarray(np.repeat(a16[:, None], 2, axis=1))
            self.sounds[k] = pygame.sndarray.make_sound(st)
        self.loop_ch = {}
        for i, name in enumerate(self.LOOPS):
            ch = pygame.mixer.Channel(i)
            self.loop_ch[name] = ch
        self.loop_vol = {name: 0.0 for name in self.LOOPS}
        self.listener = (0.0, 0.0, 0.0)

    def set_master(self, v):
        self.master = v

    def set_listener(self, x, z, yaw):
        self.listener = (x, z, yaw)

    def _pan(self, x, z):
        lx, lz, yaw = self.listener
        dx, dz = x - lx, z - lz
        d = math.hypot(dx, dz)
        if d < 1e-4:
            return 0.0, 0.0
        rx, rz = -math.cos(yaw), math.sin(yaw)
        return (dx * rx + dz * rz) / d, d

    def play(self, name, vol=1.0, pan=0.0):
        snd = self.sounds.get(name)
        if snd is None:
            return None
        ch = pygame.mixer.find_channel(True)
        if ch is None:
            return None
        ch.play(snd)
        v = vol * self.master
        ch.set_volume(max(0, min(1, v * (1 - max(0, pan) * 0.8))), max(0, min(1, v * (1 - max(0, -pan) * 0.8))))
        return ch

    def play_rand(self, prefix, count, vol=1.0, pan=0.0):
        return self.play('%s%d' % (prefix, random.randrange(count)), vol, pan)

    def play3d(self, name, x, z, maxd=25.0, vol=1.0):
        pan, d = self._pan(x, z)
        if d > maxd:
            return
        att = (1 - d / maxd) ** 1.6
        self.play(name, vol * att, pan)

    def loop(self, name, vol, pan=0.0):
        ch = self.loop_ch[name]
        v = max(0.0, min(1.0, vol * self.master))
        if v <= 0.001:
            if ch.get_busy():
                ch.stop()
            return
        if not ch.get_busy():
            ch.play(self.sounds[name], loops=-1)
        ch.set_volume(max(0, min(1, v * (1 - max(0, pan) * 0.8))), max(0, min(1, v * (1 - max(0, -pan) * 0.8))))

    def loop3d(self, name, x, z, maxd, vol):
        pan, d = self._pan(x, z)
        att = max(0.0, 1 - d / maxd) ** 1.5
        self.loop(name, vol * att, pan)

    def stop_loops(self):
        for ch in self.loop_ch.values():
            ch.stop()

    def stop_all(self):
        pygame.mixer.stop()
