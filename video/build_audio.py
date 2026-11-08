"""Synthesise the soundtrack for the Tatry reel: music + sound design.

Usage: python3 build_audio.py <work_dir> <out_dir>
Writes out_dir/music.wav, sfx.wav, amb.wav (48 kHz stereo float).

Everything is generated from scratch (numpy + pedalboard) so it is royalty
free. 120 BPM, D minor, cuts and hits match timeline.py.
"""
import math
import os
import sys
import wave

import numpy as np
from scipy import signal
from pedalboard import (Pedalboard, Reverb, Compressor, Delay, HighpassFilter,
                        LowpassFilter, Chorus, Gain, Distortion)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from timeline import (DURATION, BEAT, SFX, LABELS, CAPTIONS, SHOTS,
                      DROP_A, BREAK, DROP_B, OUTRO)

SR = 48000
N = int((DURATION + 0.0) * SR)
WORK, OUTD = sys.argv[1], sys.argv[2]
rng = np.random.default_rng(42)
BAR = BEAT * 4
S16 = BEAT / 4


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def buf():
    return np.zeros((2, N), np.float32)


def place(dst, x, t, gain=1.0, pan=0.0):
    """Add mono/stereo x into dst at time t with constant-power pan."""
    i = int(round(t * SR))
    if x.ndim == 1:
        l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
        x = np.stack([x * l * 1.414, x * r * 1.414])
    if i < 0:
        x = x[:, -i:]
        i = 0
    n = min(x.shape[1], N - i)
    if n > 0:
        dst[:, i:i + n] += x[:, :n] * gain


def fx(x, board):
    return board(x.astype(np.float32), SR)


def env_adsr(n, a, d, s, r, sus_len):
    t = np.arange(n) / SR
    e = np.zeros(n, np.float32)
    e = np.where(t < a, t / max(a, 1e-4), e)
    m = (t >= a) & (t < a + d)
    e = np.where(m, 1 - (1 - s) * (t - a) / max(d, 1e-4), e)
    m = (t >= a + d) & (t < sus_len)
    e = np.where(m, s, e)
    m = t >= sus_len
    e = np.where(m, s * np.exp(-(t - sus_len) / max(r, 1e-4)), e)
    return e.astype(np.float32)


def tv_lowpass(x, cutoff, q=0.707, block=256):
    """Time-varying RBJ lowpass. cutoff: array (len x.shape[-1])."""
    x = np.atleast_2d(x)
    y = np.zeros_like(x)
    zi = np.zeros((x.shape[0], 2))
    for s in range(0, x.shape[1], block):
        fc = float(np.clip(cutoff[min(s + block // 2, len(cutoff) - 1)], 30, SR * 0.45))
        w0 = 2 * math.pi * fc / SR
        alpha = math.sin(w0) / (2 * q)
        cw = math.cos(w0)
        b = np.array([(1 - cw) / 2, 1 - cw, (1 - cw) / 2])
        a = np.array([1 + alpha, -2 * cw, 1 - alpha])
        b, a = b / a[0], a / a[0]
        for c in range(x.shape[0]):
            y[c, s:s + block], zi[c] = signal.lfilter(b, a, x[c, s:s + block], zi=zi[c])
    return y


def bandpass(x, lo, hi, order=2):
    sos = signal.butter(order, [lo, hi], btype="band", fs=SR, output="sos")
    return signal.sosfilt(sos, x).astype(np.float32)


def highpass(x, f, order=2):
    sos = signal.butter(order, f, btype="high", fs=SR, output="sos")
    return signal.sosfilt(sos, x).astype(np.float32)


def lowpass(x, f, order=2):
    sos = signal.butter(order, f, btype="low", fs=SR, output="sos")
    return signal.sosfilt(sos, x).astype(np.float32)


def noise(n):
    return rng.normal(0, 1, n).astype(np.float32)


def saw(freq, n, phase=0.0):
    ph = (phase + np.cumsum(np.full(n, freq / SR))) % 1.0
    return (2 * ph - 1).astype(np.float32)


# ------------------------------------------------------------------ harmony
CH = {
    "Dm9": ([50, 57, 62, 65, 69, 76], 38),
    "Dm":  ([50, 57, 62, 65, 69], 38),
    "Bb":  ([46, 53, 58, 62, 65], 34),
    "F":   ([48, 53, 57, 60, 65], 41),
    "C":   ([48, 55, 60, 64, 67], 36),
}
# (start, end, chord)
PROG = [
    (0.0, 2.0, "Dm9"),
    (2.0, 4.0, "Dm"), (4.0, 6.0, "Bb"), (6.0, 8.0, "F"),
    (8.0, 10.0, "C"), (10.0, 11.0, "Bb"), (11.0, 12.0, "C"),
    (12.0, 14.0, "Dm"), (14.0, 16.0, "Bb"), (16.0, 17.0, "F"), (17.0, 18.0, "C"),
    (18.0, 20.0, "Dm9"),
]


def chord_at(t):
    for a, b, c in PROG:
        if a <= t < b:
            return c
    return PROG[-1][2]


# sidechain envelope driven by kick times
KICKS = []
HALF_A = [0, 10]            # drop A: half-time feel (16th steps)
FOUR_B = [0, 4, 8, 12]      # drop B: four on the floor
for bar in range(1, 4):
    for st in HALF_A + ([14] if bar == 3 else []):
        KICKS.append(DROP_A + (bar - 1) * BAR + st * S16)
for bar in range(3):
    for st in FOUR_B:
        KICKS.append(DROP_B + bar * BAR + st * S16)
KICKS.append(OUTRO)

tt = np.arange(N) / SR
sc = np.ones(N, np.float32)
for k in KICKS:
    m = tt >= k
    d = np.clip((tt - k) / 0.28, 0, 1)
    sc = np.where(m & (tt < k + 0.28), np.minimum(sc, 0.35 + 0.65 * (d ** 1.5)), sc)


# ------------------------------------------------------------------ pad
def make_pad():
    out = buf()
    for a, b, c in PROG:
        notes, _ = CH[c]
        n = int((b - a + 1.2) * SR)
        voice = np.zeros((2, n), np.float32)
        for m in notes:
            f = mtof(m)
            for v in range(5):
                det = (v - 2) * 0.09   # semitone spread
                for ch in range(2):
                    dd = det * (1 if ch == 0 else -1) + rng.uniform(-0.02, 0.02)
                    voice[ch] += saw(f * 2 ** (dd / 12), n, rng.uniform()) * 0.06
        e = env_adsr(n, 0.25 if a > 0 else 0.6, 0.4, 0.85, 0.5, b - a)
        place(out, voice * e, a)
    # filter automation: dark intro, open in drops, closed in breakdown
    cut = np.interp(tt, [0, 1.9, 2.0, 7.9, 8.0, 10.0, 11.9, 12.0, 17.9, 18.0, 20],
                        [500, 1800, 3200, 3200, 900, 1100, 3500, 4200, 4200, 1500, 600])
    out = tv_lowpass(out, cut, q=0.9)
    out = fx(out, Pedalboard([HighpassFilter(110), Chorus(rate_hz=0.3, depth=0.3, mix=0.4),
                              Reverb(room_size=0.85, damping=0.5, wet_level=0.45,
                                     dry_level=0.7, width=1.0)]))
    duck = np.where((tt >= DROP_A) & (tt < OUTRO + 0.4), sc, 1.0)
    return out * duck * 0.55


# ------------------------------------------------------------------ sub bass
def make_bass():
    out = buf()
    for a, b, c in PROG:
        if a < DROP_A or a >= OUTRO + 0.1:
            continue
        if BREAK <= a < DROP_B:
            continue
        _, root = CH[c]
        f = mtof(root)
        n = int((b - a) * SR)
        x = np.sin(2 * math.pi * f * np.arange(n) / SR) + 0.25 * np.sin(4 * math.pi * f * np.arange(n) / SR)
        e = env_adsr(n, 0.01, 0.1, 0.9, 0.05, (b - a) - 0.05)
        place(out, (np.tanh(x * 1.6) * e).astype(np.float32), a, 0.42)
    return out * sc


# ------------------------------------------------------------------ pluck arp
ARP = [0, 2, 4, 2, 1, 3, 4, 3, 0, 2, 4, 5, 3, 2, 1, 2]


def pluck(f, dur=0.35):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = (saw(f, n) * 0.6 + np.sin(2 * math.pi * f * t) * 0.6 +
         np.sin(2 * math.pi * 2 * f * t) * 0.2)
    e = np.exp(-t / 0.11) * np.clip(t / 0.002, 0, 1)
    x = x * e
    cut = 800 + 6000 * np.exp(-t / 0.05)
    return tv_lowpass(x[None, :], cut, q=1.2, block=128)[0]


def make_arp():
    out = buf()
    t = 0.0
    step = 0
    while t < DURATION:
        sec_ok = (DROP_A <= t < OUTRO) or (t < DROP_A and step % 2 == 0) or (t >= OUTRO and step % 2 == 0)
        if sec_ok:
            notes, _ = CH[chord_at(t)]
            tones = sorted(set(notes))[1:] + [notes[1] + 12]
            m = tones[ARP[step % 16] % len(tones)] + 12
            g = 0.16 if (DROP_A <= t < OUTRO) else 0.10
            if BREAK <= t < DROP_B:
                g = 0.12
            acc = 1.0 if step % 4 == 0 else 0.7
            pan = 0.35 * math.sin(step * 0.7)
            place(out, pluck(mtof(m)), t, g * acc, pan)
        t += S16
        step += 1
    cut = np.interp(tt, [0, 2, 8, 8.1, 11.9, 12, 18, 20], [1500, 5000, 6000, 1400, 4500, 7000, 7000, 1200])
    out = tv_lowpass(out, cut)
    out = fx(out, Pedalboard([Delay(delay_seconds=BEAT * 0.75, feedback=0.32, mix=0.28),
                              Reverb(room_size=0.6, wet_level=0.25, dry_level=0.85)]))
    duck = np.where((tt >= DROP_A) & (tt < OUTRO), 0.5 + 0.5 * sc, 1.0)
    return out * duck


# ------------------------------------------------------------------ drums
def kick(big=1.0):
    n = int(0.5 * SR)
    t = np.arange(n) / SR
    f = 46 + 120 * np.exp(-t / 0.035)
    ph = 2 * math.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-t / (0.22 * big))
    click = highpass(noise(n), 3000) * np.exp(-t / 0.004) * 0.3
    return np.tanh((x + click) * 1.8).astype(np.float32)


def clap():
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    x = np.zeros(n, np.float32)
    nz = bandpass(noise(n), 900, 2600)
    for k, off in enumerate([0, 0.011, 0.022]):
        m = t >= off
        x += np.where(m, nz * np.exp(-(t - off) / (0.012 if k < 2 else 0.16)), 0)
    return x * 0.55


def hat(open_=False):
    n = int((0.25 if open_ else 0.06) * SR)
    t = np.arange(n) / SR
    x = highpass(noise(n), 7500, 4) * np.exp(-t / (0.08 if open_ else 0.014))
    return x * 0.5


def crash(dur=2.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = highpass(noise(n), 4000, 2) * np.exp(-t / 0.7) * 0.5
    return np.stack([x, highpass(noise(n), 4000, 2) * np.exp(-t / 0.7) * 0.5])


def make_drums():
    dr = buf()
    rev = buf()
    for k in KICKS:
        place(dr, kick(1.4 if k in (DROP_B, OUTRO) else 1.0), k, 0.95)
    # drop A: clap on beat 3, hats 8ths
    for bar in range(3):
        b0 = DROP_A + bar * BAR
        place(dr, clap(), b0 + 8 * S16, 0.75)
        place(rev, clap(), b0 + 8 * S16, 0.5)
        for st in range(0, 16, 2):
            place(dr, hat(), b0 + st * S16, 0.35 if st % 4 else 0.22, 0.25)
        if bar == 2:
            for st in (13, 15):
                place(dr, hat(), b0 + st * S16, 0.28, -0.25)
    # drop B: clap 2 & 4, offbeat open hats, 16th closed hats
    for bar in range(3):
        b0 = DROP_B + bar * BAR
        for st in (4, 12):
            place(dr, clap(), b0 + st * S16, 0.8)
            place(rev, clap(), b0 + st * S16, 0.5)
        for st in range(16):
            if st % 4 == 2:
                place(dr, hat(True), b0 + st * S16, 0.32, 0.2)
            else:
                place(dr, hat(), b0 + st * S16, 0.26 if st % 2 else 0.16, -0.2)
    # build: snare roll 10-12 accelerating, silence 11.875-12
    t = 10.0
    while t < 11.875:
        prog = (t - 10.0) / 1.875
        step = BEAT / 2 if t < 11.0 else (BEAT / 4 if t < 11.5 else BEAT / 8)
        sn = clap()
        place(dr, sn, t, 0.18 + 0.55 * prog)
        place(rev, sn, t, 0.2 + 0.3 * prog)
        t += step
    place(dr, crash(), DROP_A, 0.55)
    place(dr, crash(2.6), DROP_B, 0.7)
    place(dr, crash(2.0), OUTRO, 0.35)
    rev = fx(rev, Pedalboard([Reverb(room_size=0.8, wet_level=0.6, dry_level=0.0)]))
    return dr + rev


# ------------------------------------------------------------------ sound design
def riser(dur, t_end, out, gain=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    u = t / dur
    nz = np.stack([noise(n), noise(n)])
    cut = 300 + 9000 * u ** 2
    x = tv_lowpass(nz, cut, q=2.5) * (u ** 2.2) * 0.5
    f = 200 * 2 ** (2.5 * u)
    tone = np.sin(2 * math.pi * np.cumsum(f) / SR) * (u ** 3) * 0.12
    x += tone
    place(out, x, t_end - dur, gain)


def impact(out, t, size=1.0):
    n = int(2.5 * SR)
    tt_ = np.arange(n) / SR
    f = 30 + 70 * np.exp(-tt_ / 0.08)
    boom = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-tt_ / (0.55 * size))
    crack = lowpass(noise(n), 5000) * np.exp(-tt_ / 0.05) * 0.6
    x = np.tanh((boom * 1.2 + crack) * 1.5) * 0.8
    st = fx(np.stack([x, x]), Pedalboard([Reverb(room_size=0.9, wet_level=0.35, dry_level=0.9)]))
    place(out, st, t, 0.55 * size)


def whoosh(out, t, dur=0.45, up=True, gain=0.6, pan_sweep=True):
    n = int(dur * SR)
    tt_ = np.arange(n) / SR
    u = tt_ / dur
    e = np.sin(np.pi * np.clip(u, 0, 1)) ** 2
    cut = (500 + 5000 * u) if up else (5500 - 5000 * u)
    nzl, nzr = noise(n), noise(n)
    x = tv_lowpass(np.stack([nzl, nzr]), cut, q=3.0) * e * 0.8
    if pan_sweep:
        p = np.clip(u, 0, 1)
        x[0] *= (1 - p) * 1.2 + 0.2
        x[1] *= p * 1.2 + 0.2
    place(out, x, t - dur * 0.6, gain)


def swell_down(out, t):
    # reverse cymbal into the breakdown + air
    c = crash(1.2)[:, ::-1].copy()
    place(out, c, t - 1.2, 0.35)
    whoosh(out, t + 0.05, 0.9, up=False, gain=0.8)


def tick(out, t, gain=0.12):
    n = int(0.02 * SR)
    tt_ = np.arange(n) / SR
    x = (np.sin(2 * math.pi * 3200 * tt_) * 0.5 + highpass(noise(n), 4000)) * np.exp(-tt_ / 0.0025)
    place(out, x.astype(np.float32), t, gain, rng.uniform(-0.3, 0.3))


def soft_pop(out, t, gain=0.18):
    # gentle airy "pop" for big captions
    n = int(0.25 * SR)
    tt_ = np.arange(n) / SR
    f = 900 * np.exp(-tt_ / 0.03) + 300
    x = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-tt_ / 0.04) * 0.4
    x += bandpass(noise(n), 2000, 8000) * np.exp(-tt_ / 0.02) * 0.15
    st = fx(np.stack([x, x]).astype(np.float32), Pedalboard([Reverb(room_size=0.5, wet_level=0.3)]))
    place(out, st, t, gain)


def make_sfx():
    out = buf()
    riser(1.7, DROP_A, out, 0.55)
    riser(2.0, DROP_B - 0.125, out, 0.7)
    # reverse crash into first drop
    place(out, crash(1.0)[:, ::-1].copy(), DROP_A - 1.0, 0.3)
    for t, kind in SFX:
        if kind == "impact":
            impact(out, t, 1.0)
        elif kind == "impact_big":
            impact(out, t, 1.4)
        elif kind == "impact_soft":
            impact(out, t, 0.6)
        elif kind == "whoosh_short":
            whoosh(out, t, 0.3, gain=0.8)
        elif kind == "whoosh_zoom":
            whoosh(out, t, 0.5, up=True, gain=1.3)
        elif kind == "whoosh_whip":
            whoosh(out, t, 0.32, up=False, gain=1.4)
        elif kind == "swell_down":
            swell_down(out, t)
    # typewriter ticks for the mono labels (must match make_captions.py timing)
    for t_in, t_out, l1, l2 in LABELS:
        for i, ch in enumerate(l1):
            if ch != " ":
                tick(out, t_in + i * 0.035, 0.30)
    # soft pops when caption lines land
    for t_in, t_out, y, lines in CAPTIONS:
        for text, style, t0 in lines:
            soft_pop(out, t0, 0.45)
    # opening "tape start" whoosh to grab attention in the first frame
    whoosh(out, 0.25, 0.45, up=True, gain=0.9)
    return out


# ------------------------------------------------------------------ ambience
def read_wav(p):
    with wave.open(p) as w:
        n = w.getnframes()
        x = np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768
        return x.reshape(-1, w.getnchannels()).T


def make_amb():
    out = buf()
    # synthetic wind bed (whole piece): brown-ish noise, slow gusts
    n = N
    w = np.stack([np.cumsum(noise(n)), np.cumsum(noise(n))])
    w = highpass(w, 150, 2)
    w /= np.abs(w).max() + 1e-9
    gust = 0.55 + 0.45 * np.sin(2 * math.pi * 0.13 * tt + 1.0) * np.sin(2 * math.pi * 0.07 * tt)
    cut = 400 + 900 * gust
    w = tv_lowpass(w, cut, q=1.4) * gust * 0.5
    out += w
    # real clip ambience (crunching snow, wind) under the 1x shots
    amb = {k: read_wav(os.path.join(WORK, f"amb_{k}.wav")) for k in ("7517", "8052", "7739")}
    clipmap = {"ice": "7517", "ridge": "8052", "gully": "7739"}
    for sh in SHOTS:
        if sh["clip"] not in clipmap:
            continue
        a = amb[clipmap[sh["clip"]]]
        s0 = int(sh["src_in"] * SR)
        ln = int((sh["t1"] - sh["t0"]) * SR)
        seg = a[:, s0:s0 + ln]
        if seg.shape[1] < 100:
            continue
        fade = min(int(0.03 * SR), seg.shape[1] // 2)
        e = np.ones(seg.shape[1], np.float32)
        e[:fade] = np.linspace(0, 1, fade)
        e[-fade:] = np.linspace(1, 0, fade)
        seg = highpass(seg, 140, 2) * e * 10.0   # ~ +20 dB, these are very quiet
        place(out, seg, sh["t0"], 1.0)
    return out


def write(path, x):
    """32-bit float WAV, no clipping (levels are set in the final mix)."""
    from scipy.io import wavfile
    wavfile.write(path, SR, x.T.astype(np.float32))



# ------------------------------------------------------------------ final mix
def mixdown(outd):
    """Full mix (music + sfx + ambience) and a no-music mix for in-app audio."""
    from scipy.io import wavfile
    from pedalboard import Limiter
    st = {k: wavfile.read(os.path.join(outd, f"{k}.wav"))[1].T for k in ("music", "sfx", "amb")}
    db = lambda d: 10 ** (d / 20)
    full = st["music"] * db(0) + st["sfx"] * db(-10) + st["amb"] * db(-6)
    bare = st["sfx"] * db(-10) + st["amb"] * db(0)
    lim = Pedalboard([Compressor(threshold_db=-10, ratio=2, attack_ms=5, release_ms=80),
                      Limiter(threshold_db=-2.0, release_ms=60)])
    for name, x in (("mix_full", full), ("mix_nomusic", bare)):
        y = lim(x.astype(np.float32), SR)
        y *= 10 ** (-2.0 / 20) / (np.abs(y).max() + 1e-9)   # peak -2 dBFS (true-peak headroom)
        wavfile.write(os.path.join(outd, name + ".wav"), SR, y.T.astype(np.float32))


if __name__ == "__main__":
    os.makedirs(OUTD, exist_ok=True)
    print("pad");   pad = make_pad()
    print("bass");  bass = make_bass()
    print("arp");   arp = make_arp()
    print("drums"); drums = make_drums()
    music = pad + bass + arp + drums
    music = fx(music, Pedalboard([HighpassFilter(28),
                                  Compressor(threshold_db=-14, ratio=2.5, attack_ms=10, release_ms=120)]))
    # end fade for a clean loop
    fade = np.clip((DURATION - tt) / 0.45, 0, 1)
    music *= fade
    print("sfx");   sfx = make_sfx() * fade
    print("amb");   amb = make_amb() * fade
    write(os.path.join(OUTD, "music.wav"), music)
    write(os.path.join(OUTD, "sfx.wav"), sfx)
    write(os.path.join(OUTD, "amb.wav"), amb)
    print("peaks", [float(np.abs(x).max()) for x in (music, sfx, amb)])
    mixdown(OUTD)
