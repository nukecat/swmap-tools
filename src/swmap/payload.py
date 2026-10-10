"""Inflated payload codec (CustomMapSerializer.ReadBody / WriteBody)."""
from __future__ import annotations
import numpy as np
from .binio import Reader, Writer, FormatError
from .model import Environment, FogMode, Terrain, Weather
from .props import READ_VERSIONS, read_props, write_props
from . import terrain as T


def _enum_or_int(cls, v: int):
    """Known value -> enum member; anything else stays a plain int so such a map still loads and round-trips."""
    try:
        return cls(v)
    except ValueError:
        return v


def decode_payload(data: bytes, version: int):
    if version not in READ_VERSIONS:
        raise FormatError(f"unsupported version {version}")
    r = Reader(data)
    fl = r.u8()
    if fl & 0xF0:
        raise FormatError(f"unknown environment flags {fl:#04x}")
    env = Environment(water=bool(fl & 1), ice=bool(fl & 2), edge_walls=bool(fl & 4), fog=bool(fl & 8))
    env.time = r.f32()
    env.weather = _enum_or_int(Weather, r.u8())
    env.shadow_distance_units = r.u16()
    env.fog_mode = _enum_or_int(FogMode, r.u8())
    env.fog_color = (r.u8(), r.u8(), r.u8())
    env.fog_distance_units = r.u16()

    points = r.u16()
    n = points * points
    heights = T.decode_heights(r.take(n), r.take(n), points)

    res = r.u16()
    nl = r.u8()
    ids = [r.u16() for _ in range(nl)]
    layers = [T.decode_splat(r.take(res * res), res) for _ in range(max(nl - 1, 0))]
    terr = Terrain(heights, ids, layers, res)
    if not layers:
        terr.paint_resolution = res

    count = r.varuint()
    props = read_props(r, count, version)
    if r.remaining:
        raise FormatError(f"{r.remaining} unexpected trailing bytes in payload")
    return env, terr, props


def encode_payload(env: Environment, terr: Terrain, props) -> bytes:
    w = Writer()
    w.u8(int(env.water) | int(env.ice) << 1 | int(env.edge_walls) << 2 | int(env.fog) << 3)
    w.f32(env.time)
    w.u8(int(env.weather))
    w.u16(env.shadow_distance_units)
    w.u8(int(env.fog_mode))
    for c in env.fog_color:
        w.u8(c)
    w.u16(env.fog_distance_units)

    h = np.asarray(terr.heights, dtype=np.uint16)
    if h.ndim != 2 or h.shape[0] != h.shape[1]:
        raise ValueError("heightmap must be square")
    w.u16(h.shape[0])
    lo, hi = T.encode_heights(h)
    w.raw(lo)
    w.raw(hi)

    if len(terr.layers) != max(len(terr.layer_ids) - 1, 0):
        raise ValueError("need exactly len(layer_ids)-1 stored paint layers")
    w.u16(terr.paint_resolution)
    w.u8(len(terr.layer_ids))
    for i in terr.layer_ids:
        w.u16(i)
    for layer in terr.layers:
        if layer.shape != (terr.paint_resolution, terr.paint_resolution):
            raise ValueError("paint layer has wrong size")
        w.raw(T.encode_splat(layer))

    w.varuint(len(props))
    write_props(w, props)
    return w.getvalue()
