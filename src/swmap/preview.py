"""Placeholder preview.jpg (top-down shaded terrain) for maps that have none."""
from __future__ import annotations
import io
import numpy as np
from PIL import Image
from swformats import swmap as sw
from .terrain import height_to_m, heights_array


def render_preview(terrain: sw.Terrain, width=640, height=320) -> bytes:
    """Plain baseline JPEG (what the game accepts: see swformats.swmap.is_valid_preview)."""
    z = height_to_m(heights_array(terrain))[::-1]      # image row 0 = top = +z, like the PNGs in an unpacked folder
    n = z.shape[0]
    dz_dy, dz_dx = np.gradient(z, terrain.size_meters / (n - 1))
    shade = np.clip(0.5 + 0.9 * (-dz_dx - dz_dy) / 2.0, 0, 1)
    lo, hi = float(z.min()), float(max(z.max(), z.min() + 1))
    t = np.clip((z - lo) / (hi - lo), 0, 1)
    low = np.array([0.30, 0.50, 0.28]); mid = np.array([0.62, 0.55, 0.38]); high = np.array([0.95, 0.95, 0.95])
    col = np.where(t[..., None] < 0.5, low + (mid - low) * (t[..., None] * 2), mid + (high - mid) * (t[..., None] * 2 - 1))
    img = np.clip(col * (0.55 + 0.6 * shade[..., None]), 0, 1)
    side = min(width, height)
    tile = Image.fromarray((img * 255).astype(np.uint8)).resize((side, side), Image.BILINEAR)
    canvas = Image.new("RGB", (width, height), (30, 36, 44))
    canvas.paste(tile, ((width - side) // 2, 0))
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=85, optimize=False, progressive=False)
    jpg = buf.getvalue()
    if not sw.is_valid_preview(jpg):                   # never hand the game something it would reject
        raise RuntimeError("generated preview is not a baseline JPEG the game accepts (Pillow version?)")
    return jpg
