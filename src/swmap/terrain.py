"""numpy views of swformats' terrain (which keeps plain lists / interleaved bytes).

Arrays are indexed [z, x] with row 0 at z = -size/2, exactly like swformats' ``index = z * res + x``.
"""
from __future__ import annotations
import numpy as np
from swformats import swmap as sw


def height_to_m(h):
    """16-bit height samples -> metres (the game's range is -100 .. +400 m)."""
    units = sw.MIN_HEIGHT_UNITS + np.asarray(h, dtype=np.float64) / 65535 * sw.HEIGHT_RANGE_UNITS
    return units / sw.METERS_TO_UNITS


def m_to_height(m):
    units = np.asarray(m, dtype=np.float64) * sw.METERS_TO_UNITS
    v = np.rint((units - sw.MIN_HEIGHT_UNITS) / sw.HEIGHT_RANGE_UNITS * 65535)
    return np.clip(v, 0, 65535).astype(np.uint16)


def heights_array(t: sw.Terrain) -> np.ndarray:
    """uint16 (height_res, height_res)"""
    return np.array(t.heights, dtype=np.uint16).reshape(t.height_res, t.height_res)


def splat_array(t: sw.Terrain) -> np.ndarray:
    """uint8 (alpha_res, alpha_res, layer_count): the weight of every layer, the last one included."""
    return np.frombuffer(bytes(t.splat), dtype=np.uint8).reshape(t.alpha_res, t.alpha_res, t.layer_count)
