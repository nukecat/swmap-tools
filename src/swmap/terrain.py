"""Heightmap / paint-layer codec (CustomMapSerializer.ReadPredicted16 / ReadSplat).

Both use the clamped gradient predictor  clamp(left + up - upleft)  with
row 0 -> left, column 0 -> up, corner -> 0.
Heights: residual is a zigzag-coded int16 stored as two byte planes (all low bytes, then all high bytes).
Paint:   residual is a plain byte difference (mod 256).
"""
from __future__ import annotations
import numpy as np

HEIGHT_MIN_M = -100.0
HEIGHT_RANGE_M = 500.0          # 0..65535 -> -100..400 m


def height_to_m(h):
    return np.asarray(h, dtype=np.float64) * HEIGHT_RANGE_M / 65536.0 + HEIGHT_MIN_M


def m_to_height(m):
    v = np.rint((np.asarray(m, dtype=np.float64) - HEIGHT_MIN_M) * 65536.0 / HEIGHT_RANGE_M)
    return np.clip(v, 0, 65535).astype(np.uint16)


def _decode(vals, res: int, top: int, zigzag: bool) -> np.ndarray:
    out = [0] * (res * res)
    for z in range(res):
        row = z * res
        for x in range(res):
            i = row + x
            if x == 0:
                pred = out[i - res] if z else 0
            elif z == 0:
                pred = out[i - 1]
            else:
                pred = out[i - 1] + out[i - res] - out[i - res - 1]
                if pred > top:
                    pred = top
                elif pred < 0:
                    pred = 0
            v = vals[i]
            if zigzag:
                v = (v >> 1) ^ -(v & 1)
            out[i] = (pred + v) & top
    return np.array(out, dtype=np.uint16 if top == 0xFFFF else np.uint8).reshape(res, res)


def _predict(a: np.ndarray, top: int) -> np.ndarray:
    a = a.astype(np.int64)
    p = np.zeros_like(a)
    p[0, 1:] = a[0, :-1]
    p[1:, 0] = a[:-1, 0]
    p[1:, 1:] = np.clip(a[1:, :-1] + a[:-1, 1:] - a[:-1, :-1], 0, top)
    return p


def decode_heights(lo: bytes, hi: bytes, points: int) -> np.ndarray:
    l = np.frombuffer(lo, np.uint8).astype(np.int64)
    h = np.frombuffer(hi, np.uint8).astype(np.int64)
    return _decode((l | (h << 8)).tolist(), points, 0xFFFF, True)


def encode_heights(heights: np.ndarray) -> tuple[bytes, bytes]:
    """uint16 (N,N) -> (low plane, high plane)."""
    a = np.asarray(heights).astype(np.int64)
    s = (((a - _predict(a, 0xFFFF)) + 32768) & 0xFFFF) - 32768        # signed 16-bit residual
    zz = ((s << 1) ^ (s >> 15)) & 0xFFFF
    return (zz & 0xFF).astype(np.uint8).tobytes(), (zz >> 8).astype(np.uint8).tobytes()


def decode_splat(raw: bytes, res: int) -> np.ndarray:
    return _decode(list(raw), res, 0xFF, False)


def encode_splat(layer: np.ndarray) -> bytes:
    a = np.asarray(layer).astype(np.int64)
    return ((a - _predict(a, 0xFF)) & 0xFF).astype(np.uint8).tobytes()


def base_layer(layers) -> np.ndarray:
    """The implied first layer: 255 - sum(stored layers), clamped at 0."""
    return np.clip(255 - sum(l.astype(np.int32) for l in layers), 0, 255).astype(np.uint8)
