#!/usr/bin/env python3
"""Generate a 102x54 transparent 'sail-across' ferry loading GIF.

Cruise/ferry counterpart to make_airplane_loader.py (FJL tenant). Deliberately
an intentional matching PAIR with the airplane loader: SAME canvas (102x54),
SAME frame count (28) and timing (45ms -> 40ms stored, ~1.12s loop), SAME blue
palette + transparency + infinite loop + disposal, SAME minimalist dashed-trail
motif. Only the glyph differs: a small ferry silhouette (hull + cabin + funnel)
glides along the trail, the dashes reading as its wake.
"""
import numpy as np
from PIL import Image, ImageDraw

W, H = 102, 54          # final native size (must match Superset loading.gif)
S = 5                   # supersample factor for smooth edges
N = 28                  # frames
DUR = 45                # ms per frame  -> ~1.12s loop (stored as 40ms, like airplane)
CY = 27                 # vertical centre / waterline

LIGHT  = (91, 155, 213)   # cabin / superstructure
DARK   = (46, 111, 176)   # hull / funnel
TRAIL  = (157, 188, 219)  # wake dashes
PAL_RGB = np.array([LIGHT, DARK, TRAIL])
FLAT_PAL = [255, 0, 255, *LIGHT, *DARK, *TRAIL] + [0] * (256 * 3 - 12)

def ship_polys(px):
    """Ferry silhouette referenced to px (advancing left->right), bow at right."""
    cy = CY
    # Hull: deck line at cy-2, pointed bow at right, flat-ish bottom at cy+6.
    hull = [(px + 3, cy - 2), (px + 27, cy - 2), (px + 32, cy + 1),
            (px + 27, cy + 6), (px + 9, cy + 6)]
    # Cabin / superstructure block sitting on the deck.
    cabin = [(px + 9, cy - 2), (px + 9, cy - 8), (px + 23, cy - 8), (px + 23, cy - 2)]
    # Funnel on top of the cabin.
    funnel = [(px + 16, cy - 8), (px + 16, cy - 12), (px + 19, cy - 12), (px + 19, cy - 8)]
    return hull, cabin, funnel

def trail_segments(px):
    """Wake dashes trailing behind the ship (same motif as the airplane contrail)."""
    segs = []
    start = px - 2
    for _ in range(3):
        segs.append((start - 6, start))
        start -= 11
    return segs

def render_frame(px):
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for x0, x1 in trail_segments(px):
        d.line([(x1 * S, CY * S), (x0 * S, CY * S)], fill=TRAIL + (255,), width=2 * S)
    hull, cabin, funnel = ship_polys(px)
    d.polygon([(x * S, y * S) for x, y in hull], fill=DARK + (255,))
    d.polygon([(x * S, y * S) for x, y in cabin], fill=LIGHT + (255,))
    d.polygon([(x * S, y * S) for x, y in funnel], fill=DARK + (255,))
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
frames[0].save("loading_ship.gif", save_all=True, append_images=frames[1:],
               duration=DUR, loop=0, transparency=0, disposal=2, optimize=False)
print("wrote loading_ship.gif")
