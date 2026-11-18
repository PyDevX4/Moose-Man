"""Procedurally synthesized sound + simple positional audio on pygame.mixer.

Recordings in the sounds/ folder (next to src/) replace or add to the synthesized ones. A file's
name says what it is; "(loop)" loops it, "(random pitch)" pitches every play a little up or down.
CUSTOM maps names onto the game's sounds.
"""
import math
import os
import random
import re
import sys
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

    # ---- Goat Man roar: a bleat dropped two octaves, stuttering, with a growl under it
    t = tt(3.2)
    f0 = 150 - 60 * (t / 3.2) + 6 * np.sin(2 * np.pi * 4 * t)
    ph = 2 * np.pi * np.cumsum(f0) / SR
    tone = np.zeros_like(t)
    for h in range(1, 16):
        fh = f0 * h
        w = (1.0 / h) * (1 + 1.8 * np.exp(-((fh - 650) / 180) ** 2) + 1.3 * np.exp(-((fh - 1250) / 260) ** 2))
        tone += np.sin(ph * h) * w
    bleat = 0.45 + 0.55 * (np.sin(2 * np.pi * 9.5 * t) > -0.2)
    growl = band(noise(len(t)), 40, 260) * 2.2 * (0.6 + 0.4 * np.sin(2 * np.pi * 23 * t))
    env = np.clip(t / 0.08, 0, 1) * np.clip((3.2 - t) / 1.2, 0, 1)
    roar = np.tanh((tone * bleat + growl) * 1.2) * env
    s['goat_roar'] = norm(echo(band(roar, 40, 4000), 0.14, 0.35, 4), 1.0)

    # ---- eating: wet tearing and crunching
    for i in range(3):
        n = int(SR * 0.7)
        x = np.zeros(n)
        for _ in range(4):
            i0 = int(_rng.uniform(0, 0.45) * SR)
            ln = int(_rng.uniform(0.06, 0.2) * SR)
            seg = band(noise(ln), 250, 2600) * np.sin(np.linspace(0, np.pi, ln)) * slow_mod(ln, 80, 0.8)
            x[i0:i0 + ln] += seg
        crunch = (noise(n) > 0.985) * noise(n) * env_ad(n, 0.01, 4) * 1.5
        x += band(crunch, 600, 6000)
        s['eat%d' % i] = norm(x, 0.8)

    # ---- body impact: car hits flesh
    t = tt(1.4)
    im = np.sin(2 * np.pi * 42 * t) * np.exp(-t * 7) * 1.6
    im += band(noise(len(t)), 70, 1600) * np.exp(-t * 14) * 1.4
    im += sum(np.sin(2 * np.pi * fq * t) * np.exp(-t * dc) for fq, dc in ((380, 18), (731, 24), (1133, 30))) * 0.5
    im += band((noise(len(t)) > 0.97) * noise(len(t)), 3000, 9000) * np.exp(-t * 5) * 0.8
    s['impact'] = norm(np.tanh(im * 1.3), 1.0)

    # ---- tackle: two big bodies colliding
    t = tt(0.8)
    tk = np.sin(2 * np.pi * 55 * t) * np.exp(-t * 10) + band(noise(len(t)), 80, 900) * np.exp(-t * 16) * 1.2
    s['tackle'] = norm(echo(np.tanh(tk * 1.5), 0.09, 0.3, 3), 1.0)

    # ---- car passing at speed: engine with a doppler drop, tyre roar
    n = int(SR * 5.0)
    t = np.arange(n) / SR
    tc = 2.5
    dop = 1.0 + 0.13 * np.tanh(-(t - tc) * 3.0)
    f = 88 * dop
    phs = 2 * np.pi * np.cumsum(f) / SR
    eng = sum(saw(phs * k) / k for k in (1, 2, 3)) + np.sin(phs * 0.5) * 0.6
    tyre = band(noise(n), 180, 1800) * 1.3
    env = 1.0 / (1.0 + ((t - tc) * 1.9) ** 2)
    s['car'] = norm(band((eng * 0.5 + tyre) * env, 40, 5000), 0.95)

    # ================================================================ chapter 2
    # ---- winter wind: howling resonances sweeping over a low roar
    n = int(SR * 14)
    t = np.arange(n) / SR
    wind = band(noise(n), 30, 300) * slow_mod(n, 0.25, 0.7) * 1.6
    for fc, rate in ((420, 0.11), (610, 0.07), (880, 0.13)):
        sweep = fc * (1 + 0.25 * np.sin(2 * np.pi * rate * t + fc))
        ph = 2 * np.pi * np.cumsum(sweep) / SR
        howl = np.sin(ph) * band(noise(n), 0, 40) * 6 * slow_mod(n, 0.3, 1.0)
        wind += howl * 0.25
    wind += band(noise(n), 2000, 6000) * 0.05 * slow_mod(n, 0.5, 1.0)
    s['winter_amb'] = loopable(norm(wind, 0.6), 1.5)

    # ---- snow footsteps: a soft compressed crunch
    for i in range(4):
        n = int(SR * 0.28)
        grains = (noise(n) > 0.6) * noise(n)
        x = band(grains, 500, 4500) * env_ad(n, 0.04, 9) + band(noise(n), 100, 600) * env_ad(n, 0.02, 20) * 0.5
        s['step_snow%d' % i] = norm(x, 0.5)

    # ---- match: a scratch, then the flare
    t = tt(1.2)
    scratch = band(noise(len(t)), 2000, 8000) * (t < 0.16) * slow_mod(len(t), 90, 1.0)
    flare = band(noise(len(t)), 150, 2500) * np.clip((t - 0.12) / 0.05, 0, 1) * np.exp(-np.maximum(0, t - 0.17) * 3.5)
    crackle = (noise(len(t)) > 0.992) * noise(len(t)) * np.exp(-t * 2) * (t > 0.15)
    s['match'] = norm(scratch * 0.9 + flare * 0.6 + band(crackle, 1500, 8000) * 0.8, 0.8)

    # ---- the cabin door: a creak, and (closing) a heavy thud
    t = tt(1.0)
    f = 340 + 160 * np.sin(2 * np.pi * 1.3 * t) + 40 * slow_mod(len(t), 8, 1.0)
    creak = np.sin(2 * np.pi * np.cumsum(f) / SR) * band(noise(len(t)), 0, 30) * 4
    creak = band(creak, 200, 3000) * np.clip(t / 0.05, 0, 1) * np.clip((1.0 - t) / 0.3, 0, 1)
    s['door_open'] = norm(echo(creak, 0.07, 0.2, 2), 0.6)
    t = tt(0.9)
    thud = np.sin(2 * np.pi * 85 * t) * np.exp(-t * 18) + band(noise(len(t)), 100, 1500) * np.exp(-t * 30) * 0.8
    s['door_close'] = norm(echo(np.concatenate([creak[:int(SR * 0.35)] * 0.6, thud]), 0.08, 0.25, 2), 0.8)

    # ---- firewood: picked up (a couple of knocks) and stacked (a clatter)
    def knock(fq, at, total):
        tk = np.arange(int(SR * total)) / SR
        o = np.zeros_like(tk)
        m = tk >= at
        tt_ = tk[m] - at
        o[m] = (np.sin(2 * np.pi * fq * tt_) * np.exp(-tt_ * 35) + band(noise(m.sum()), 400, 3000) * np.exp(-tt_ * 60) * 0.6)
        return o
    s['wood_pick'] = norm(knock(330, 0.0, 0.5) + knock(410, 0.11, 0.5) * 0.8, 0.7)
    s['wood_drop'] = norm(knock(300, 0.0, 0.9) + knock(370, 0.09, 0.9) + knock(280, 0.2, 0.9) * 0.8
                          + knock(450, 0.31, 0.9) * 0.6, 0.8)

    # ---- rifle: a hard crack, then the shot rolling away through the hills
    t = tt(3.0)
    crack = band(noise(len(t)), 300, 9000) * np.exp(-t * 60) * 2.0 + np.sin(2 * np.pi * 60 * t) * np.exp(-t * 14) * 1.2
    roll = band(noise(len(t)), 60, 700) * np.exp(-t * 1.6) * 0.5 * np.clip(t / 0.08, 0, 1)
    s['rifle'] = norm(np.tanh(echo(crack, 0.34, 0.35, 4)[:len(t)] + roll), 1.0)
    # ---- bolt cycled
    s['bolt'] = norm(knock(1300, 0.0, 0.6) * 0.6 + knock(900, 0.18, 0.6) + knock(1500, 0.36, 0.6) * 0.7, 0.6)
    # ---- a window smashed in
    t = tt(1.4)
    gl = np.zeros_like(t)
    for _ in range(60):
        i0 = int(_rng.uniform(0, 0.9) * SR)
        ln = int(_rng.uniform(0.02, 0.12) * SR)
        i1 = min(len(t), i0 + ln)
        tb = np.arange(i1 - i0) / SR
        fq = _rng.uniform(2500, 7500)
        gl[i0:i1] += np.sin(2 * np.pi * fq * tb) * np.exp(-tb * 40) * _rng.uniform(0.3, 1.0)
    gl += band(noise(len(t)), 1500, 9000) * np.exp(-t * 6) * 1.2 + np.sin(2 * np.pi * 70 * t) * np.exp(-t * 15)
    s['glass'] = norm(echo(gl, 0.07, 0.25, 3), 1.0)
    # ---- a deer's alarm snort
    t = tt(0.5)
    s['snort'] = norm(band(noise(len(t)), 300, 3000) * np.exp(-t * 9) * (t > 0.02), 0.7)
    # ---- the Elk: a bugle that climbs into a scream, with grunts under it
    t = tt(3.6)
    f0 = np.where(t < 1.2, 220 + 900 * (t / 1.2) ** 1.5, 1120 + 700 * np.clip((t - 1.2) / 1.2, 0, 1))
    f0 = f0 * (1 + 0.02 * np.sin(2 * np.pi * 7 * t))
    ph = 2 * np.pi * np.cumsum(f0) / SR
    bug = np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.25 * np.sin(3.01 * ph)
    bug *= np.clip(t / 0.2, 0, 1) * np.clip((3.6 - t) / 1.2, 0, 1)
    grunt = band(noise(len(t)), 50, 400) * (np.sin(2 * np.pi * 2.2 * t) > 0.6) * 1.5
    s['elk_bugle'] = norm(echo(np.tanh((bug + grunt) * 1.2), 0.21, 0.4, 5), 0.95)

    # ---- chapter 4 -------------------------------------------------------
    # bones cracking and re-setting: a burst of wet snaps
    t = tt(2.4)
    cr = np.zeros_like(t)
    for _ in range(26):
        i0 = int(_rng.uniform(0, 2.2) * SR)
        ln = int(_rng.uniform(0.01, 0.05) * SR)
        i1 = min(len(t), i0 + ln)
        tb = np.arange(i1 - i0) / SR
        cr[i0:i1] += band(noise(i1 - i0), 800, 7000) * np.exp(-tb * 120) * _rng.uniform(0.4, 1.0) \
            + np.sin(2 * np.pi * _rng.uniform(120, 260) * tb) * np.exp(-tb * 60) * 0.6
    wet = band(noise(len(t)), 80, 900) * slow_mod(len(t), 6, 1.0) * 0.25
    s['crack'] = norm(echo(cr + wet, 0.05, 0.2, 2), 0.95)
    # the floor giving way: a huge slam, then concrete breaking up and pouring down
    t = tt(4.0)
    slam = np.sin(2 * np.pi * 42 * t) * np.exp(-t * 3.5) * 1.6 + band(noise(len(t)), 40, 2500) * np.exp(-t * 7) * 1.4
    rub = band(noise(len(t)), 150, 3500) * np.clip((t - 0.25) / 0.2, 0, 1) * np.exp(-np.maximum(0, t - 0.4) * 1.3)
    rub *= 0.5 + 0.5 * (noise(len(t)) > 0.7)
    s['smash'] = norm(np.tanh(echo(slam + rub * 0.8, 0.29, 0.4, 5)[:len(t)] * 1.3), 1.0)
    # his new voice: low, doubled and torn
    t = tt(3.2)
    f0 = 58 + 22 * np.sin(2 * np.pi * 0.4 * t) + 10 * slow_mod(len(t), 9, 1.0)
    ph = 2 * np.pi * np.cumsum(f0) / SR
    v = np.sin(ph) + 0.7 * np.sin(2.01 * ph) + 0.5 * np.sin(3.03 * ph) + 0.4 * np.sin(1.49 * ph)
    v = np.tanh(v * 2.2) + band(noise(len(t)), 100, 1800) * 0.9
    v *= np.clip(t / 0.25, 0, 1) * np.clip((3.2 - t) / 1.0, 0, 1)
    s['moose_roar'] = norm(echo(v, 0.23, 0.45, 5), 1.0)
    # a generator: pull cord, a cough, then it catches
    t = tt(2.6)
    cord = band(noise(len(t)), 600, 5000) * (t < 0.35) * np.clip(t / 0.05, 0, 1) * 0.6
    eng = (np.sign(np.sin(2 * np.pi * (14 + 12 * np.clip((t - 0.9) / 1.0, 0, 1)) * t)) + 1) * 0.5
    eng = band(eng * noise(len(t)), 40, 1200) * np.clip((t - 0.7) / 0.3, 0, 1)
    s['gen_start'] = norm(cord + eng + band(noise(len(t)), 60, 300) * np.exp(-np.abs(t - 0.6) * 15), 0.9)
    t = tt(3.0)
    hum = np.sin(2 * np.pi * 60 * t) + 0.5 * np.sin(2 * np.pi * 120 * t) + band(noise(len(t)), 40, 500) * 1.2 \
        * (0.7 + 0.3 * np.sin(2 * np.pi * 26 * t))
    s['gen_hum'] = norm(loopable(hum, 0.5), 0.6)
    # a huge gate grinding up on its chains
    t = tt(6.0)
    f = 70 + 15 * slow_mod(len(t), 3, 1.0)
    grind = np.sin(2 * np.pi * np.cumsum(f) / SR) * band(noise(len(t)), 0, 25) * 6
    grind = band(grind, 50, 2500) + band(noise(len(t)), 200, 3000) * 0.3 * (noise(len(t)) > 0.4)
    chain = np.zeros_like(t)
    for k in range(40):
        chain += knock(1200 + 200 * (k % 3), k * 0.14, 6.0) * 0.25
    grind = (grind + chain) * np.clip(t / 0.3, 0, 1) * np.clip((6.0 - t) / 0.8, 0, 1)
    s['gate'] = norm(echo(grind, 0.31, 0.4, 4)[:len(t)] + np.sin(2 * np.pi * 50 * t) * np.exp(-np.abs(t - 5.6) * 9) * 1.5, 1.0)
    # a fuse pushed home: click, then a buzz
    t = tt(0.8)
    buzz = np.sign(np.sin(2 * np.pi * 120 * t)) * 0.3 * np.clip((t - 0.1) / 0.02, 0, 1) * np.exp(-t * 4)
    s['fuse'] = norm(knock(2200, 0.0, 0.8) + band(buzz, 100, 3000), 0.7)
    return s


# ---------------------------------------------------------------------- recorded sounds
# file name (lower case, letters and digits only, tags dropped) -> the game's sound
CUSTOM = {
    'forestfootstep': 'step_grass', 'snowfootstep': 'step_snow', 'woodfootstep': 'step_wood',
    'lanternon': 'lantern_on', 'lanternoff': 'lantern_off',
    'headlightonandoff': 'headlamp', 'headlamponandoff': 'headlamp',
    'revolvershot': 'revolver', 'rifleshot': 'rifle_shot',
}
# sounds the game asks for that only exist as recordings: what plays without the file
FALLBACK = {'step_wood': 'step_conc', 'lantern_on': 'click', 'lantern_off': 'click', 'headlamp': 'click',
            'revolver': 'rifle', 'rifle_shot': 'rifle'}
PITCHES = (-2.0, -1.3, -0.6, 0.0, 0.7, 1.4, 2.0)     # semitones, for "(random pitch)"


def parse_sound_name(fname):
    """'ForestFootstep (Random Pitch).mp3' -> ('step_grass', loop=False, random_pitch=True)."""
    low = os.path.splitext(os.path.basename(fname))[0].lower()
    loop = '(loop)' in low
    rp = '(random pitch)' in low or '(randompitch)' in low
    key = re.sub(r'[^a-z0-9]', '', re.sub(r'\(.*?\)', '', low))
    return CUSTOM.get(key, key), loop, rp


def sound_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [os.path.join(sys._MEIPASS, 'sounds')] if hasattr(sys, '_MEIPASS') else []
    cands += [os.path.join(here, '..', 'sounds'), os.path.join(here, 'sounds')]
    for d in cands:
        if os.path.isdir(d):
            return d
    return None


def decode_sounds(folder):
    """Every recording in the folder as (key, mono float array at SR, loop, random_pitch). Needs pygame.mixer."""
    out = []
    if not folder or not pygame.mixer.get_init():
        return out
    freq = pygame.mixer.get_init()[0]
    for f in sorted(os.listdir(folder)):
        if not f.lower().endswith(('.wav', '.ogg', '.mp3', '.flac')):
            continue
        try:
            a = pygame.sndarray.array(pygame.mixer.Sound(os.path.join(folder, f))).astype(np.float32) / 32768.0
        except Exception as e:
            print("sound %s: %s" % (f, e))
            continue
        if a.ndim == 2:
            a = a.mean(axis=1)
        if freq != SR and len(a) > 1:
            a = np.interp(np.arange(0, len(a), freq / SR), np.arange(len(a)), a).astype(np.float32)
        key, loop, rp = parse_sound_name(f)
        out.append((key, a, loop, rp))
    return out


def recorded_sounds():
    """The browser can't decode these itself: build_web.py packs them, decoded, into custom_sounds.npz."""
    npz = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'custom_sounds.npz')
    if os.path.exists(npz):
        z = np.load(npz)
        out = []
        for name in z.files:
            key, flags = name.split('__')
            out.append((key, z[name].astype(np.float32) / 32767.0, 'L' in flags, 'R' in flags))
        return out
    return decode_sounds(sound_dir())


def pitched(a, semis):
    if abs(semis) < 1e-3:
        return a
    rate = 2.0 ** (semis / 12.0)
    return np.interp(np.arange(0, len(a) - 1, rate), np.arange(len(a)), a).astype(np.float32)


def with_recordings(raw):
    """raw (the synthesized sounds) plus the recordings. Returns (sounds, variants, loops)."""
    variants = {}
    loops = set()
    for key, a, loop, rp in recorded_sounds():
        a = np.clip(a, -1, 1)
        if key.startswith('step_') and len(a):
            # footsteps all at one loudness, whatever level they were recorded at
            rms = float(np.sqrt(np.mean(a * a))) or 1e-6
            a = a * min(0.07 / rms, 0.95 / max(1e-6, float(np.abs(a).max())))
        if loop:
            a = loopable(a, min(0.3, len(a) / SR / 4))
            loops.add(key)
        raw[key] = a
        if rp and not loop:
            names = []
            for i, st in enumerate(PITCHES):
                nm = '%s~%d' % (key, i)
                raw[nm] = pitched(a, st)
                names.append(nm)
            variants[key] = names
        else:
            variants[key] = [key]
    return raw, variants, loops


class Audio:
    LOOPS = ('forest_amb', 'sewer_amb', 'breath', 'creak', 'title_amb', 'winter_amb', 'gen_hum')
    variants = {}

    def resolve(self, name, have):
        """Which sound actually plays for name: a random pitch of a recording, or its fallback."""
        v = self.variants.get(name)
        if v:
            return random.choice(v)
        if name not in have and name in FALLBACK:
            return FALLBACK[name]
        return name

    def resolve_rand(self, prefix, count):
        if prefix in self.variants:
            return self.resolve(prefix, ())
        if prefix in FALLBACK:
            prefix = FALLBACK[prefix]
        return '%s%d' % (prefix, random.randrange(count))

    def __init__(self, volume=0.8):
        self.master = volume
        self.listener = (0.0, 0.0, 0.0)
        self.sounds = {}
        self.loop_ch = {}
        self.loop_vol = {}
        # No sound device (unplugged headset, device grabbed by another app...)
        # must not stop the game from starting: fall back to silence.
        self.enabled = bool(pygame.mixer.get_init())
        if not self.enabled:
            try:
                pygame.mixer.init(22050, -16, 2, 512)
                self.enabled = True
            except Exception:
                self.enabled = False
        if not self.enabled:
            return
        pygame.mixer.set_num_channels(40)
        pygame.mixer.set_reserved(len(self.LOOPS))
        raw, self.variants, loops = with_recordings(synth_all())
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
        snd = self.sounds.get(self.resolve(name, self.sounds))
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
        return self.play(self.resolve_rand(prefix, count), vol, pan)

    def play3d(self, name, x, z, maxd=25.0, vol=1.0):
        pan, d = self._pan(x, z)
        if d > maxd:
            return
        att = (1 - d / maxd) ** 1.6
        self.play(name, vol * att, pan)

    def loop(self, name, vol, pan=0.0):
        ch = self.loop_ch.get(name)
        if ch is None:
            return
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
        if self.enabled:
            pygame.mixer.stop()

    def pause(self):
        if self.enabled:
            pygame.mixer.pause()

    def unpause(self):
        if self.enabled:
            pygame.mixer.unpause()
