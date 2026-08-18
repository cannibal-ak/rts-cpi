#!/usr/bin/env python3
"""Generate a 102x54 transparent 'fly-across' paper-airplane loading GIF.

Drop-in replacement for Superset 3.1.0 loading.gif. Native size kept at 102x54
so Superset's loader centering/layout does not shift.
"""
import numpy as np
from PIL import Image, ImageDraw

W, H = 102, 54          # final native size (must match Superset loading.gif)
S = 5                   # supersample factor for smooth edges
N = 28                  # frames
DUR = 45                # ms per frame  -> ~1.26s loop
CY = 27                 # vertical centre

LIGHT  = (91, 155, 213)   # upper wing
DARK   = (46, 111, 176)   # lower flap
TRAIL  = (157, 188, 219)  # contrail dashes
PAL_RGB = np.array([LIGHT, DARK, TRAIL])
FLAT_PAL = [255, 0, 255, *LIGHT, *DARK, *TRAIL] + [0] * (256 * 3 - 12)

def plane_polys(px):
    top = CY - 9
    tip       = (px + 28, top + 9)
    back_top  = (px + 0,  top + 1)
    back_bot  = (px + 0,  top + 17)
    notch     = (px + 9,  top + 11)
    return [tip, back_top, notch], [tip, notch, back_bot]

def trail_segments(px):
    segs = []
    start = px - 4
    for _ in range(3):
        segs.append((start - 6, start))
        start -= 11
    return segs

def render_frame(px):
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for x0, x1 in trail_segments(px):
        d.line([(x1 * S, CY * S), (x0 * S, CY * S)], fill=TRAIL + (255,), width=2 * S)
    upper, lower = plane_polys(px)
    d.polygon([(x * S, y * S) for x, y in lower], fill=DARK + (255,))
    d.polygon([(x * S, y * S) for x, y in upper], fill=LIGHT + (255,))
    small = img.resize((W, H), Image.LANCZOS)
    arr = np.array(small)
    alpha = arr[..., 3]
    rgb = arr[..., :3].astype(int)
    dist = ((rgb[:, :, None, :] - PAL_RGB[None, None, :, :]) ** 2).sum(3)
    nearest = dist.argmin(2) + 1
    idx = np.where(alpha >= 128, nearest, 0).astype(np.uint8)
    pim = Image.fromarray(idx, mode="P")
    pim.putpalette(FLAT_PAL)
    return pim

xs = np.linspace(-30, 102, N)
frames = [render_frame(int(round(x))) for x in xs]
frames[0].save("loading_airplane.gif", save_all=True, append_images=frames[1:],
               duration=DUR, loop=0, transparency=0, disposal=2, optimize=False)
print("wrote loading_airplane.gif")
