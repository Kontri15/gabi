"""Generate captions.ass (animated titles) from timeline.py.

Usage: python3 make_captions.py <out.ass>

Big lines: Instrument Serif (regular + italic) with a soft dark glow so the
cream type reads on snow; lines "track in" (letter spacing), rise and
de-blur. Small labels: DM Mono with a typewriter reveal and a growing rule.
"""
import os
import sys

from fontTools.ttLib import TTFont
from PIL import ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from timeline import W, H, CAPTIONS, LABELS

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
SERIF = {"reg": os.path.join(FONTS, "InstrumentSerif-Regular.ttf"),
         "it": os.path.join(FONTS, "InstrumentSerif-Italic.ttf")}
MAX_W = 940          # keep clear of the right-side UI buttons
CREAM = "&H00EEF6FF&"   # ASS is &HAABBGGRR -> RGB(255,246,238)

# per caption block: (size_reg, size_it)
SIZES = [(140, 172), (150, 204), (132, 144), (140, 166), (96, 102)]


def ass_scale(path):
    """libass treats font size as winAscent+winDescent; convert to em px."""
    f = TTFont(path)
    os2 = f["OS/2"]
    return f["head"].unitsPerEm / (os2.usWinAscent + os2.usWinDescent)


def text_w(text, style, size):
    em = size * ass_scale(SERIF[style])
    font = ImageFont.truetype(SERIF[style], max(1, int(round(em))))
    return font.getlength(text)


def ts(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Serif,Instrument Serif,110,{CREAM},&H000000FF,&H8C000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Glow,Instrument Serif,110,&HFF000000,&H000000FF,&H78000000,&H00000000,0,0,0,0,100,100,0,0,1,9,0,5,0,0,0,1
Style: Mono,DM Mono Medium,42,{CREAM},&H000000FF,&H90000000,&H00000000,0,0,0,0,100,100,6,0,1,2.5,0,7,0,0,0,1
Style: MonoSmall,DM Mono,31,&H30EEF6FF,&H000000FF,&H90000000,&H00000000,0,0,0,0,100,100,4,0,1,2,0,7,0,0,0,1
Style: Rule,DM Mono,20,{CREAM},&H000000FF,&H90000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def caption_events():
    ev = []
    for ci, (t_in, t_out, yc, lines) in enumerate(CAPTIONS):
        sizes = SIZES[ci]
        n = len(lines)
        # fit sizes to MAX_W
        fs = []
        for text, style, _ in lines:
            s = sizes[0] if style == "reg" else sizes[1]
            while text_w(text, style, s) > MAX_W:
                s -= 2
            fs.append(s)
        gap = 0.86 * (sum(fs) / n)
        ys = [yc + (i - (n - 1) / 2) * gap for i in range(n)]
        for (text, style, t0), s, y in zip(lines, fs, ys):
            dur_ms = int((t_out - t0) * 1000)
            it = "\\i1" if style == "it" else "\\i0"
            anim = (f"\\fad(160,220)\\move(540,{y + 26:.0f},540,{y:.0f},0,320)"
                    f"\\fsp10\\t(0,420,0.45,\\fsp0)"
                    f"\\t({dur_ms - 220},{dur_ms},\\fscx104\\fscy104)")
            glow = f"{{\\an5{it}\\fs{s}{anim}\\blur16\\t(0,420,\\blur18)}}"
            body = f"{{\\an5{it}\\fs{s}{anim}\\blur9\\t(0,300,0.5,\\blur0.6)\\t({dur_ms - 220},{dur_ms},\\blur6)}}"
            ev.append(f"Dialogue: 0,{ts(t0)},{ts(t_out)},Glow,,0,0,0,,{glow}{text}")
            ev.append(f"Dialogue: 1,{ts(t0)},{ts(t_out)},Serif,,0,0,0,,{body}{text}")
    return ev


def label_events():
    ev = []
    x, y1, y2 = 78, 250, 306
    for t_in, t_out, l1, l2 in LABELS:
        dur_ms = int((t_out - t_in) * 1000)
        # growing rule above the label
        ev.append(f"Dialogue: 2,{ts(t_in - 0.05)},{ts(t_out)},Rule,,0,0,0,,"
                  f"{{\\an7\\pos({x},{y1 - 22})\\fad(0,200)\\fscx0\\t(0,280,0.5,\\fscx100)\\p1}}"
                  f"m 0 0 l 56 0 56 3 0 3{{\\p0}}")
        # typewriter: each char pops in 35 ms apart
        parts = []
        for i, ch in enumerate(l1):
            k = i * 35
            c = "\\h" if ch == " " else ch
            parts.append(f"{{\\alpha&HFF&\\t({k},{k + 1},\\alpha&H00&)}}{c}")
        ev.append(f"Dialogue: 2,{ts(t_in)},{ts(t_out)},Mono,,0,0,0,,"
                  f"{{\\an7\\pos({x},{y1})\\fad(0,200)}}" + "".join(parts))
        l2s = l2.replace(" ", "\\h")
        d2 = len(l1) * 35 + 60
        ev.append(f"Dialogue: 2,{ts(t_in)},{ts(t_out)},MonoSmall,,0,0,0,,"
                  f"{{\\an7\\pos({x},{y2})\\alpha&HFF&\\t({d2},{d2 + 300},\\alpha&H30&)\\fad(0,200)}}{l2s}")
    return ev


def cover_events():
    """Static title for the cover image (no animation)."""
    ev = []
    for text, style, y, size in (("Malí ľudia.", "reg", 370, 150), ("Veľké hory.", "it", 500, 176)):
        it = "\\i1" if style == "it" else "\\i0"
        ev.append(f"Dialogue: 0,0:00:00.00,0:00:05.00,Glow,,0,0,0,,{{\\an5{it}\\fs{size}\\pos(540,{y})\\blur18}}{text}")
        ev.append(f"Dialogue: 1,0:00:00.00,0:00:05.00,Serif,,0,0,0,,{{\\an5{it}\\fs{size}\\pos(540,{y})\\blur0.6}}{text}")
    return ev


if __name__ == "__main__":
    out = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "--cover":
        with open(out, "w", encoding="utf-8") as f:
            f.write(HEADER + "\n".join(cover_events()) + "\n")
        sys.exit(0)
    with open(out, "w", encoding="utf-8") as f:
        f.write(HEADER)
        for e in caption_events() + label_events():
            f.write(e + "\n")
    print("wrote", out)
