"""Render the picture (no text) for the Tatry reel.

Usage: python3 build_video.py <work_dir_with_src_mp4s> <out_picture.mp4>

Reads the tone-mapped intermediates, applies speed ramps (with shutter-style
motion blur), push-ins, beat pulses, transitions (flash / zoom-blur / whip /
dissolve), colour grade, vignette and film grain, then pipes raw frames to
ffmpeg.
"""
import math
import os
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from timeline import (FPS, W, H, DURATION, SRC, SHOTS, CAPTIONS, LABELS,
                      DROP_A, DROP_B, BREAK, OUTRO, BEAT, SNOW, COLD_INTRO)

WORK = sys.argv[1]
OUT = sys.argv[2]
RAMP = 0.30  # seconds of smoothing between speed pieces


# ---------------------------------------------------------------- sources
class Clip:
    """Holds only the source frames inside the given time ranges (RAM)."""

    def __init__(self, path, ranges):
        cap = cv2.VideoCapture(path)
        self.fps = cap.get(cv2.CAP_PROP_FPS)
        self.n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        want = set()
        for a, b in ranges:
            want.update(range(max(0, int(a * self.fps) - 3), int(b * self.fps) + 4))
        self.frames = {}
        i = 0
        while True:
            ok, f = cap.read()
            if not ok:
                break
            if i in want:
                self.frames[i] = f
            i += 1
        cap.release()
        self.n = i
        self.keys = sorted(self.frames)

    def _f(self, i):
        i = min(max(i, self.keys[0]), self.keys[-1])
        while i not in self.frames:
            i -= 1
        return self.frames[i]

    def get(self, t0, t1):
        """Average source frames covering [t0, t1] (shutter blur)."""
        a = int(round(t0 * self.fps))
        b = max(int(round(t1 * self.fps)), a)
        if b == a:
            return self._f(a).astype(np.float32)
        acc = np.zeros(self._f(a).shape, dtype=np.float32)
        for i in range(a, b + 1):
            acc += self._f(i)
        return acc / (b - a + 1)


# ---------------------------------------------------------------- timing
def speed_at(shot, lt):
    """Speed at local time lt, smoothed between pieces with a cosine ramp."""
    pieces = shot["pieces"]
    edges = [0.0]
    for d, _ in pieces:
        edges.append(edges[-1] + d)
    sp = pieces[0][1]
    for i in range(1, len(pieces)):
        e = edges[i]
        prev, nxt = pieces[i - 1][1], pieces[i][1]
        if lt >= e + RAMP / 2:
            sp = nxt
        elif lt > e - RAMP / 2:
            u = (lt - (e - RAMP / 2)) / RAMP
            sp = prev + (nxt - prev) * (0.5 - 0.5 * math.cos(math.pi * u))
    return sp


def src_time(shot, lt):
    """Integrate speed from 0 to lt (lt may be negative for pre-roll)."""
    steps = max(4, int(abs(lt) * 240))
    if lt == 0:
        return shot["src_in"]
    dt = lt / steps
    acc = 0.0
    for i in range(steps):
        acc += speed_at(shot, (i + 0.5) * dt) * dt
    return shot["src_in"] + acc


def _load_clips():
    ranges = {}
    for sh in SHOTS:
        dur = sh["t1"] - sh["t0"]
        a = src_time(sh, -0.3)
        b = src_time(sh, dur + 0.3) + 0.2
        ranges.setdefault(sh["clip"], []).append((a, b))
    out = {}
    for key, rr in ranges.items():
        print("loading", key, [(round(a, 2), round(b, 2)) for a, b in rr], flush=True)
        out[key] = Clip(os.path.join(WORK, SRC[key]), rr)
    return out


clips = _load_clips()


# ---------------------------------------------------------------- grading
GRADES = {
    #        exposure(stops), temp, tint, contrast, sat, red_boost
    "ice":   dict(exp=0.10, temp=0.03, tint=0.00, con=0.30, sat=1.12, red=0.35),
    "gully": dict(exp=0.12, temp=0.07, tint=0.01, con=0.22, sat=1.02, red=0.25),
    "ridge": dict(exp=-0.05, temp=0.02, tint=0.00, con=0.28, sat=1.10, red=0.30),
    "wide":  dict(exp=0.05, temp=0.04, tint=0.00, con=0.32, sat=1.15, red=0.20),
}


def make_luts(g):
    x = np.arange(256, dtype=np.float32) / 255.0
    luts = []
    for ch, wb in ((0, -g["temp"]), (1, g["tint"]), (2, g["temp"])):  # BGR
        y = x * (2 ** g["exp"]) * (1 + wb)
        # filmic S-curve around 0.45 pivot, soft shoulder
        c = g["con"]
        y = np.clip(y, 0, 1.25)
        s = y + c * (y - 0.45) * (1 - np.abs(2 * np.clip(y, 0, 1) - 1) ** 1.6) * 0.9
        # gentle highlight roll-off so snow keeps texture
        s = np.where(s > 0.82, 0.82 + (1 - np.exp(-(s - 0.82) * 3.2)) * 0.17, s)
        s = np.clip(s, 0.012, 1.0)  # lifted black, film feel
        luts.append(np.clip(s * 255, 0, 255).astype(np.uint8))
    return luts


LUTS = {k: make_luts(v) for k, v in GRADES.items()}

yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
r2 = ((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.58)) ** 2
VIGNETTE = (1 - 0.22 * np.clip(r2 - 0.25, 0, 1.5) ** 1.3)[..., None].astype(np.float32)

rng = np.random.default_rng(7)
GRAIN = []
for _ in range(8):
    n = rng.normal(0, 1, (H // 2, W // 2)).astype(np.float32)
    n = cv2.GaussianBlur(n, (0, 0), 0.6)
    n = cv2.resize(n, (W, H), interpolation=cv2.INTER_LINEAR)
    GRAIN.append(n[..., None] * 0.022)


def text_shade(t):
    """Soft dark band behind captions so white serif type reads on snow."""
    m = np.ones((H, 1, 1), np.float32)
    ycol = np.arange(H, dtype=np.float32)[:, None, None]
    for t_in, t_out, yc, _ in CAPTIONS:
        if t_in - 0.2 <= t <= t_out + 0.2:
            a = min(1, (t - (t_in - 0.2)) / 0.3, ((t_out + 0.2) - t) / 0.3)
            band = np.exp(-((ycol - yc) / 300.0) ** 2)
            m *= 1 - 0.30 * a * band
    for t_in, t_out, _, _ in LABELS:
        if t_in - 0.2 <= t <= t_out + 0.2:
            a = min(1, (t - (t_in - 0.2)) / 0.3, ((t_out + 0.2) - t) / 0.3)
            band = np.exp(-((ycol - 285) / 140.0) ** 2)
            m *= 1 - 0.18 * a * band
    return m


def grade(img_f, key, t, frame_idx):
    """img_f: float32 BGR 0..255 -> uint8 BGR graded."""
    u8 = np.clip(img_f, 0, 255).astype(np.uint8)
    b, g_, r = cv2.split(u8)
    lb, lg, lr = LUTS[key]
    u8 = cv2.merge([cv2.LUT(b, lb), cv2.LUT(g_, lg), cv2.LUT(r, lr)])
    f = u8.astype(np.float32) / 255.0
    gp = GRADES[key]
    luma = (0.0722 * f[..., 0] + 0.7152 * f[..., 1] + 0.2126 * f[..., 2])[..., None]
    # saturation, with extra push on reds (jackets pop against snow)
    redness = np.clip((f[..., 2:3] - np.maximum(f[..., 0:1], f[..., 1:2])) * 3.0, 0, 1)
    sat = gp["sat"] + gp["red"] * redness
    f = luma + (f - luma) * sat
    # split tone: cool teal shadows, warm highlights
    sh = np.clip(1 - luma * 2.2, 0, 1)
    hi = np.clip((luma - 0.55) * 2.2, 0, 1)
    f += sh * np.array([0.030, 0.012, -0.012], np.float32)   # BGR
    f += hi * np.array([-0.020, 0.004, 0.022], np.float32)
    if t < COLD_INTRO:   # "winter is coming": colder, a bit drained, snaps back on the drop
        lum = (0.0722 * f[..., 0] + 0.7152 * f[..., 1] + 0.2126 * f[..., 2])[..., None]
        f = lum + (f - lum) * 0.72
        f += np.array([0.04, 0.012, -0.025], np.float32)
        f *= 0.95
    f *= VIGNETTE
    f *= text_shade(t)
    f += GRAIN[frame_idx % len(GRAIN)] * (0.6 + 0.8 * (1 - np.abs(luma - 0.5) * 2))
    return np.clip(f * 255, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- snow
class Snow:
    """Deterministic falling snow: position is a pure function of time."""

    def __init__(self, seed=3):
        r = np.random.default_rng(seed)
        self.layers = []
        #        count, radius px (half-res), fall px/s, blur, alpha
        for cnt, rad, vy, blur, alpha in ((240, (1.0, 2.2), (70, 140), 0.0, (0.35, 0.75)),
                                          (110, (2.2, 4.0), (150, 260), 1.2, (0.45, 0.85)),
                                          (22, (6.0, 10.0), (330, 480), 4.5, (0.25, 0.5))):
            self.layers.append(dict(
                x=r.uniform(0, W / 2, cnt), y=r.uniform(0, H / 2, cnt),
                r=r.uniform(*rad, cnt), vy=r.uniform(*vy, cnt) / 2,
                vx=r.uniform(-25, -5, cnt) / 2, amp=r.uniform(4, 18, cnt) / 2,
                fq=r.uniform(0.4, 1.4, cnt), ph=r.uniform(0, 6.28, cnt),
                a=r.uniform(*alpha, cnt), blur=blur, keep=r.uniform(0, 1, cnt)))

    def alpha(self, t, density):
        hw, hh = W // 2, H // 2
        out = np.zeros((hh, hw), np.float32)
        for L in self.layers:
            lay = np.zeros((hh, hw), np.float32)
            y = (L["y"] + L["vy"] * t) % (hh + 30) - 15
            x = (L["x"] + L["vx"] * t + L["amp"] * np.sin(L["fq"] * t * 6.28 + L["ph"])) % (hw + 30) - 15
            for i in np.nonzero(L["keep"] < density)[0]:
                cv2.circle(lay, (int(x[i] * 4), int(y[i] * 4)), max(1, int(L["r"][i] * 4)),
                           float(L["a"][i]), -1, lineType=cv2.LINE_AA, shift=2)
            if L["blur"]:
                lay = cv2.GaussianBlur(lay, (0, 0), L["blur"])
            out = np.maximum(out, lay)
        return cv2.resize(out, (W, H), interpolation=cv2.INTER_LINEAR)


SNOWFALL = Snow()


def add_snow(img, t):
    for t_in, t_out, dens in SNOW:
        if t_in <= t < t_out:
            fade = min(1.0, (t - t_in) / 0.25 if t_in > 0 else 1.0, (t_out - t) / 0.12)
            a = SNOWFALL.alpha(t, dens)[..., None] * fade
            f = img.astype(np.float32)
            f = f * (1 - a) + np.array([255, 250, 246], np.float32) * a   # BGR, faintly cool white
            return np.clip(f, 0, 255).astype(np.uint8)
    return img


# ---------------------------------------------------------------- geometry
def warp(img, scale, dx=0.0, dy=0.0, rot=0.0):
    M = cv2.getRotationMatrix2D((W / 2, H / 2), rot, scale)
    M[0, 2] += dx
    M[1, 2] += dy
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REFLECT)


def zoom_blur(img, scale, strength, n=7):
    acc = np.zeros_like(img)
    for i in range(n):
        acc += warp(img, scale * (1 + strength * i / (n - 1)))
    return acc / n


def dir_blur(img, length):
    k = max(1, int(length)) | 1
    return cv2.blur(img, (k, 1))


def ease_in_out(u):
    return 0.5 - 0.5 * math.cos(math.pi * min(max(u, 0), 1))


def shot_frame(shot, t, extra_scale=1.0):
    lt = t - shot["t0"]
    clip = clips[shot["clip"]]
    st = src_time(shot, lt)
    sp = speed_at(shot, lt)
    shutter = sp * 0.5 / FPS if sp > 1.05 else 0.0
    img = clip.get(st, st + shutter)
    if img.shape[1] != W or img.shape[0] != H:
        img = cv2.resize(img, (W, H), interpolation=cv2.INTER_LANCZOS4)
    dur = shot["t1"] - shot["t0"]
    z0, z1 = shot["zoom"]
    u = min(max(lt / dur, 0), 1)
    if shot.get("tin") == "flash":   # punch-in that settles fast
        z = z1 + (z0 - z1) * math.exp(-lt / 0.12)
    else:
        z = z0 + (z1 - z0) * u
    return img, z * extra_scale


# beat pulses on bar downbeats during the drops, plus shake on the drops
def pulse(t):
    s = 1.0
    for start, end in ((DROP_A, BREAK), (DROP_B, OUTRO)):
        if start <= t < end + 0.5:
            k = math.floor((t - start) / (BEAT * 2))
            tb = start + k * BEAT * 2
            s += 0.018 * math.exp(-(t - tb) / 0.12)
    return s


def shake(t):
    dx = dy = rot = 0.0
    for t0, amp in ((DROP_A, 10), (DROP_B, 16), (13.5, 8)):
        if t0 <= t < t0 + 0.5:
            e = math.exp(-(t - t0) / 0.12)
            dx += amp * e * math.sin(t * 97)
            dy += amp * e * math.cos(t * 83)
            rot += 0.25 * amp / 10 * e * math.sin(t * 71)
    return dx, dy, rot


# ---------------------------------------------------------------- compose
TRANS_IN = 5 / FPS    # frames after a cut affected by incoming transition
TRANS_OUT = 4 / FPS   # frames before a cut affected by outgoing transition
DISSOLVE = 8 / FPS


def compose(t):
    idx = next(i for i, s in enumerate(SHOTS) if s["t0"] <= t < s["t1"] or i == len(SHOTS) - 1)
    shot = SHOTS[idx]
    nxt = SHOTS[idx + 1] if idx + 1 < len(SHOTS) else None
    p = pulse(t)
    dx, dy, rot = shake(t)

    img, z = shot_frame(shot, t, p)
    lt = t - shot["t0"]
    tin = shot.get("tin")

    # ---- incoming transitions
    if tin == "zoomblur" and lt < TRANS_IN:
        u = 1 - lt / TRANS_IN                     # 1 -> 0
        out = zoom_blur(img, z * (1 + 0.25 * u * u), 0.10 * u)
    elif tin == "whip" and lt < TRANS_IN:
        u = 1 - lt / TRANS_IN
        out = warp(img, z, dx - 260 * u * u, dy, rot)
        out = dir_blur(out, 180 * u)
        dx = dy = rot = 0
    elif tin == "dissolve" and lt < DISSOLVE / 2:
        prev = SHOTS[idx - 1]
        a = 0.5 + lt / DISSOLVE                    # 0.5 -> 1
        pimg, pz = shot_frame(prev, t, p)
        out = warp(img, z) * a + warp(pimg, pz) * (1 - a)
        out = cv2.GaussianBlur(out, (0, 0), 6 * (1 - a) * 2)
    else:
        out = None

    # ---- outgoing transitions (into the next shot)
    if out is None and nxt is not None:
        to_cut = nxt["t0"] - t
        if nxt.get("tin") == "zoomblur" and to_cut <= TRANS_OUT:
            u = 1 - to_cut / TRANS_OUT             # 0 -> 1
            out = zoom_blur(img, z * (1 + 0.30 * u * u), 0.12 * u)
        elif nxt.get("tin") == "whip" and to_cut <= TRANS_OUT:
            u = 1 - to_cut / TRANS_OUT
            out = dir_blur(warp(img, z, 260 * u * u, 0), 180 * u)
        elif nxt.get("tin") == "dissolve" and to_cut <= DISSOLVE / 2:
            a = 0.5 + to_cut / DISSOLVE            # 1 -> 0.5 (this shot's weight)
            nimg, nz = shot_frame(nxt, t, p)
            out = warp(img, z) * a + warp(nimg, nz) * (1 - a)
            out = cv2.GaussianBlur(out, (0, 0), 6 * (1 - a) * 2)

    if out is None:
        out = warp(img, z, dx, dy, rot)
    elif dx or dy or rot:
        out = warp(out, 1.0, dx, dy, rot)

    # soften the upscaled phone clip a touch less: unsharp
    if shot["clip"] == "wide":
        bl = cv2.GaussianBlur(out, (0, 0), 1.4)
        out = cv2.addWeighted(out, 1.45, bl, -0.45, 0)

    key = shot["grade"]
    # during a dissolve the grade follows the dominant shot
    frame_idx = int(round(t * FPS))
    g = grade(out, key, t, frame_idx)
    g = add_snow(g, t)

    # white flash on the hard drop cut
    if tin == "flash" and lt < 0.2:
        a = math.exp(-lt / 0.05) * 0.85
        g = cv2.addWeighted(g, 1 - a, np.full_like(g, 255), a, 0)
    # fade from black at very start, tiny dip at the end for the loop
    if t < 0.10:
        g = (g.astype(np.float32) * (t / 0.10)).astype(np.uint8)
    return g


def main():
    nframes = int(round(DURATION * FPS))
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "12",
           "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
           "-color_trc", "bt709", "-colorspace", "bt709", OUT]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for k in range(nframes):
        t = k / FPS
        frame = compose(t)
        proc.stdin.write(frame.tobytes())
        if k % 30 == 0:
            print(f"frame {k}/{nframes}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("done", OUT)


if __name__ == "__main__":
    if len(sys.argv) > 3:   # preview stills: build_video.py work out.png t1,t2,...
        ts = [float(x) for x in sys.argv[3].split(",")]
        for t in ts:
            cv2.imwrite(OUT.replace(".png", f"_{t:05.2f}.png"), compose(t))
    else:
        main()
