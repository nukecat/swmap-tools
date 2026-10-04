"""Placeholder preview.jpg (top-down shaded terrain) for maps that have none."""
from __future__ import annotations
import io
import numpy as np
from PIL import Image
from .terrain import height_to_m


def render_preview(terrain, size_m: float, width=640, height=320) -> bytes:
    z = height_to_m(terrain.heights)
    n = z.shape[0]
    dz_dy, dz_dx = np.gradient(z, size_m / (n - 1))
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
    canvas.save(buf, "JPEG", quality=85)
    return buf.getvalue()
