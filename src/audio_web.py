"""Sound in the browser: the same synthesized sounds, played by WebAudio in web/mm.js."""
import random

import numpy as np

from audio import Audio as DesktopAudio, synth_all, SR
from webplat import js, to_js


class Audio(DesktopAudio):
    def __init__(self, volume=0.8):
        self.master = volume
        self.listener = (0.0, 0.0, 0.0)
        self.enabled = True
        self.loop_vol = {name: -1.0 for name in self.LOOPS}
        self.loop_pan = {name: 0.0 for name in self.LOOPS}
        self.names = set()
        for k, v in synth_all().items():
            a = np.clip(np.asarray(v, dtype=np.float32), -1, 1) * 0.98
            js.mm.addSound(k, to_js(np.ascontiguousarray(a)), SR)
            self.names.add(k)

    def play(self, name, vol=1.0, pan=0.0):
        if name not in self.names:
            return None
        v = max(0.0, min(1.0, vol * self.master))
        if v > 0.002:
            js.mm.playSound(name, v, max(-1.0, min(1.0, pan)))
        return None

    def play_rand(self, prefix, count, vol=1.0, pan=0.0):
        return self.play('%s%d' % (prefix, random.randrange(count)), vol, pan)

    def loop(self, name, vol, pan=0.0):
        if name not in self.loop_vol:
            return
        v = max(0.0, min(1.0, vol * self.master))
        if v <= 0.001:
            v = 0.0
        if abs(v - self.loop_vol[name]) > 0.01 or abs(pan - self.loop_pan[name]) > 0.05:
            self.loop_vol[name] = v
            self.loop_pan[name] = pan
            js.mm.loopSound(name, v, max(-1.0, min(1.0, pan)))

    def stop_loops(self):
        for name in self.LOOPS:
            self.loop_vol[name] = 0.0
            js.mm.loopSound(name, 0.0, 0.0)

    def stop_all(self):
        js.mm.stopAll()

    def pause(self):
        js.mm.pauseAudio(True)

    def unpause(self):
        js.mm.pauseAudio(False)
