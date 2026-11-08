"""Shared edit timeline for the Tatry reel.

All times are in seconds. Output is 1080x1920 @ 30 fps, 120 BPM grid
(beat = 0.5 s, bar = 2 s), so every cut lands on a beat.
"""

FPS = 30
W, H = 1080, 1920
BPM = 120
BEAT = 60 / BPM
DURATION = 20.0

# Source intermediates (SDR, tone-mapped from iPhone HLG), produced by render.sh
SRC = {
    "ice": "src_7517.mp4",      # icefall: axes in snow -> pan up -> climbers on ice
    "ridge": "src_8052.mp4",    # ski touring bootpack under a snowy ridge
    "gully": "src_7739.mp4",    # couloir: POV feet -> partner climbing below
    "wide": "src_d.mp4",        # tiny figure on a huge slope, tilt up to peaks
}

# Each shot: output start/end, source clip, and speed pieces.
# pieces: list of (output_duration, speed). Source start = src_in.
# "zoom": (start_scale, end_scale) slow push-in across the shot.
# "tin"/"tout": transition style into / out of the shot.
SHOTS = [
    dict(name="pov_feet", clip="gully", t0=0.0, t1=2.0, src_in=0.00,
         pieces=[(2.0, 1.0)], zoom=(1.06, 1.00), grade="gully"),
    dict(name="axes", clip="ice", t0=2.0, t1=2.5, src_in=0.02,
         pieces=[(0.5, 1.0)], zoom=(1.18, 1.08), grade="ice", tin="flash"),
    dict(name="ice_reveal", clip="ice", t0=2.5, t1=4.5, src_in=0.55,
         pieces=[(2.0, 1.175)], zoom=(1.00, 1.05), grade="ice"),
    dict(name="ice_climbers", clip="ice", t0=4.5, t1=6.5, src_in=3.00,
         pieces=[(2.0, 1.2)], zoom=(1.02, 1.12), grade="ice", tin="zoomblur"),
    dict(name="gully_partner", clip="gully", t0=6.5, t1=8.0, src_in=2.00,
         pieces=[(1.5, 1.0)], zoom=(1.00, 1.06), grade="gully", tin="whip"),
    # slow-mo breakdown, then speed ramp into drop B at 12.0
    dict(name="ridge_ramp", clip="ridge", t0=8.0, t1=13.5, src_in=1.50,
         pieces=[(4.0, 0.5), (1.5, 3.0)], zoom=(1.00, 1.08), grade="ridge",
         tin="dissolve"),
    dict(name="wide_finale", clip="wide", t0=13.5, t1=20.0, src_in=0.50,
         pieces=[(3.0, 3.0), (3.5, 1.5)], zoom=(1.10, 1.00), grade="wide",
         tin="zoomblur"),
]

# Cut points (for SFX + flashes)
CUTS = [s["t0"] for s in SHOTS[1:]]

# Musical structure (bar index -> section)
#   bar 0      0-2   intro / hook (pad + riser)
#   bars 1-3   2-8   drop A
#   bars 4-5   8-12  breakdown (slow-mo), build into 12
#   bars 6-8  12-18  drop B
#   bar 9     18-20  outro
DROP_A = 2.0
BREAK = 8.0
DROP_B = 12.0
OUTRO = 18.0

# Sound-design cues: (time, kind)
SFX = [
    (DROP_A, "impact"),
    (2.5, "whoosh_short"),
    (4.5, "whoosh_zoom"),
    (6.5, "whoosh_whip"),
    (BREAK, "swell_down"),
    (DROP_B, "impact_big"),
    (13.5, "whoosh_zoom"),
    (OUTRO, "impact_soft"),
]

# Text "ticks" (typewriter labels) are generated from LABELS

# Big serif captions: (t_in, t_out, y_center_px, [(text, style, word_times)...])
# style: "reg" = Instrument Serif, "it" = Instrument Serif Italic.
CAPTIONS = [
    (0.12, 1.94, 610, [("Niektorí cez víkend", "reg", 0.12), ("vyspávajú.", "it", 0.70)]),
    (2.00, 4.38, 620, [("My chodíme", "reg", 2.00), ("hore.", "it", 2.50)]),
    (8.40, 11.92, 600, [("Nohy bolia.", "reg", 8.50), ("Hlava oddychuje.", "it", 10.00)]),
    (14.10, 17.40, 600, [("Malí ľudia.", "reg", 14.20), ("Veľké hory.", "it", 15.20)]),
    (17.55, 20.00, 640, [("Pošli to parťákovi,", "reg", 17.60), ("s ktorým ideš túto zimu.", "it", 18.00)]),
]

LABELS = [
    # (t_in, t_out, line1, line2)
    (4.55, 6.45, "01 — ĽAD", "49.2485° N  20.1032° E"),
    (6.55, 7.95, "02 — ŽĽAB", "TATRY"),
    (8.45, 11.9, "03 — SKIALP", "1 954 m n. m."),
    (14.2, 20.0, "TATRY", "ZIMA 2026"),
]
