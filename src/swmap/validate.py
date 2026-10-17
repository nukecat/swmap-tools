"""Checks before packing.

Errors  = swformats refuses to write the map, or the game would reject what it writes (checked by writing the map and
          reading it back with swformats' strict reader, which implements the game's rules).
Warnings = the writer silently clamps / drops / rewrites something, or the value is suspicious.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

from swformats import FormatError, MapCatalog, swmap as sw
from .folder import FOG_MODES, KINDS, WEATHER


@dataclass
class Issue:
    level: str            # "error" = the game rejects it, "warning" = changed on write or suspicious
    where: str
    message: str

    def __str__(self):
        return f"{self.level.upper():7} {self.where}: {self.message}"


def validate(m: sw.SwMap, catalog: MapCatalog | None = None) -> list:
    out = []
    E = lambda w, msg: out.append(Issue("error", w, msg))
    W = lambda w, msg: out.append(Issue("warning", w, msg))
    cat = catalog or MapCatalog.default()
    env, t = m.env, m.terrain

    # ---- errors: what the game would reject
    try:
        data = sw.write(m)
    except Exception as ex:                                   # noqa: BLE001 - swformats raises ValueError for bad terrain
        E("map", str(ex) or type(ex).__name__)
        return out
    try:
        sw.read(data)
    except FormatError as ex:
        E("map", f"the game would reject the written file: {ex}")
    if len(data) > sw.MAX_ONLINE_FILE_BYTES:
        W("map", f"{len(data):,} bytes: too big to host, publish or download online (limit {sw.MAX_ONLINE_FILE_BYTES:,}); "
                 "lower the resolution or remove objects")

    # ---- warnings: written differently from what is in memory
    for what, text, limit in (("name", m.name, sw.MAX_NAME_LENGTH), ("author", m.author, sw.MAX_AUTHOR_LENGTH)):
        if sw.clean_text(text, limit) != text:
            W("map", f"{what} {text!r} will be written as {sw.clean_text(text, limit)!r} "
                     f"(max {limit} characters, no control characters or < >)")
    if m.preview_jpeg and not sw.is_valid_preview(m.preview_jpeg):
        W("preview", "not a baseline JPEG the game accepts (max 1024x1024, 256 KiB, no EXIF/progressive); it will be left out")

    if not (math.isfinite(env.time) and 0 <= env.time <= 2):
        W("environment", f"time {env.time} is outside 0..2 and will be clamped")
    if not sw.MIN_SHADOW <= env.shadow_distance <= sw.MAX_SHADOW:
        W("environment", f"shadow distance {env.shadow_distance / sw.METERS_TO_UNITS:g} m is outside "
                         f"{sw.MIN_SHADOW / 2:g}..{sw.MAX_SHADOW / 2:g} m and will be clamped")
    if not sw.MIN_FOG <= env.fog_distance <= sw.MAX_FOG:
        W("environment", f"fog distance {env.fog_distance / sw.METERS_TO_UNITS:g} m is outside "
                         f"{sw.MIN_FOG / 2:g}..{sw.MAX_FOG / 2:g} m and will be clamped")
    if env.weather not in WEATHER:
        W("environment", f"weather {env.weather} is not a known value ({', '.join(f'{n}={v}' for v, n in WEATHER.items())}); "
                         "it will be clamped to 0..3")
    if env.fog_mode not in FOG_MODES:
        W("environment", f"fog_mode {env.fog_mode} is not a known value ({', '.join(f'{n}={v}' for v, n in FOG_MODES.items())}); "
                         "it will be written as linear")
    if env.ice and not env.water:
        W("environment", "ice without water has no effect")

    for lid in t.layer_ids:
        if lid not in cat.layers:
            W("terrain", f"paint layer id {lid} is not in sw-formats' catalog (unknown layers do not show up in game)")

    half = t.world_size / 2
    for i, o in enumerate(m.objects):
        kind = o.kind
        w = f"object[{i}] {KINDS.get(kind, kind)}"
        if not 0 <= kind <= sw.PLAYER_SPAWN:
            E(w, "unknown kind")
            continue
        x, y, z = o.position
        if abs(x) > half or abs(z) > half:
            W(w, f"position ({x / 2:g}, {z / 2:g}) m is outside the map (+-{half / 2:g} m) and will be moved to the edge")
        if not sw.MIN_OBJECT_Y <= y <= sw.MAX_OBJECT_Y:
            W(w, f"y = {y / 2:g} m is outside {sw.MIN_OBJECT_Y / 2:g}..{sw.MAX_OBJECT_Y / 2:g} m and will be clamped")
        if not all(math.isfinite(v) and sw.MIN_SCALE <= v <= sw.MAX_SCALE for v in o.scale):
            W(w, f"scale must be within {sw.MIN_SCALE}..{sw.MAX_SCALE}; it will be clamped")
        if kind == sw.PROP:
            if o.prop_id not in cat.props:
                W(w, f"prop id {o.prop_id} is not in sw-formats' catalog (an unknown prop does not appear in game)")
            if o.floors and not 1 <= o.floors <= sw.MAX_FLOORS:
                W(w, f"floors {o.floors} will be clamped to 1..{sw.MAX_FLOORS}")
            if o.color is not None and not all(0 <= c <= 255 for c in o.color):
                E(w, "colour components must be 0..255")
        else:
            if kind == sw.CAPTURE_POINT and abs(o.yaw) > 0.01:
                W(w, "capture points cannot be rotated; the rotation is dropped")
            if abs(o.rotation[0]) >= 1e-4 or abs(o.rotation[2]) >= 1e-4:
                W(w, "only props can be tilted; spawns, capture points and player spawns keep just their heading")
            if kind == sw.CAPTURE_POINT and not o.scale[0] == o.scale[1] == o.scale[2]:
                W(w, "a capture point has one radius; only the x scale is used")
        if kind == sw.SPAWN:
            if o.team not in (0, 1, 2):
                W(w, f"team {o.team} must be 0, 1 or 2; it will be clamped")
            if o.spawn_type not in (sw.SPAWN_GROUND, sw.SPAWN_WATER, sw.SPAWN_AIRCRAFT):
                W(w, f"vehicle type {o.spawn_type} must be 1 (tank), 2 (boat) or 4 (plane); it will be written as tank")
        if kind == sw.CAPTURE_POINT and not 0 <= o.letter < sw.MAX_CAPTURE_POINTS:
            W(w, f"letter {o.letter} must be 0..{sw.MAX_CAPTURE_POINTS - 1} (a..d); it will be clamped")
    return out
