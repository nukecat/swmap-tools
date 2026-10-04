"""Checks mirroring what the game's loader enforces (errors) plus sanity warnings."""
from __future__ import annotations
import math
from dataclasses import dataclass
from dataclasses import astuple
from .model import Color, FogMode, Kind, Letter, Quaternion, SwMap, Team, Vec3, VehicleType, Weather


@dataclass
class Issue:
    level: str            # "error" = the game rejects it, "warning" = suspicious
    where: str
    message: str

    def __str__(self):
        return f"{self.level.upper():7} {self.where}: {self.message}"


MAX_PROPS = 20000


def validate(m: SwMap) -> list:
    out = []
    E = lambda w, msg: out.append(Issue("error", w, msg))
    W = lambda w, msg: out.append(Issue("warning", w, msg))
    env, t = m.environment, m.terrain

    if not 128 <= m.header.size_m <= 8000:
        W("map", f"size {m.header.size_m} m is outside the game's 128..8000 m range")
    if not (math.isfinite(env.time) and 0 <= env.time <= 2):
        E("environment", f"time {env.time} must be within 0..2")
    elif env.time > 1:
        W("environment", "time > 1 (editor slider is 0..1)")
    if not 100 <= env.shadow_distance_units <= 4000:
        E("environment", f"shadow distance {env.shadow_distance_units / 2} m must be 50..2000 m")
    if not 50 <= env.fog_distance_units <= 20000:
        E("environment", f"fog distance {env.fog_distance_units / 2} m must be 25..10000 m")
    if not all(0 <= c <= 255 for c in env.fog_color):
        E("environment", "fog colour components must be 0..255")
    if not 0 <= env.weather <= 255:
        E("environment", "weather must be a byte")
    elif env.weather not in tuple(Weather):
        W("environment", f"weather {int(env.weather)} is not a known value ({', '.join(f'{m.name.lower()}={m.value}' for m in Weather)})")
    if not 0 <= env.fog_mode <= 255:
        E("environment", "fog_mode must be a byte")
    elif env.fog_mode not in tuple(FogMode):
        W("environment", f"fog_mode {int(env.fog_mode)} is not a known value ({', '.join(f'{m.name.lower()}={m.value}' for m in FogMode)})")
    if env.ice and not env.water:
        W("environment", "ice without water has no effect")

    n = t.height_points
    if t.heights.ndim != 2 or t.heights.shape[0] != t.heights.shape[1]:
        E("terrain", "heightmap must be square")
    elif n < 3 or n > 65535:
        E("terrain", f"heightmap size {n} out of range")
    elif (n - 1) & (n - 2):
        W("terrain", f"heightmap size {n} is not 2^k+1 (the game uses 129/257/513/...)")
    r = t.paint_resolution
    if not 1 <= len(t.layer_ids) <= 255:
        E("terrain", "need 1..255 paint layers")
    if len(t.layers) != max(len(t.layer_ids) - 1, 0):
        E("terrain", "number of stored paint layers must be len(layer_ids)-1")
    for i, l in enumerate(t.layers, 1):
        if l.shape != (r, r):
            E("terrain", f"paint layer {i} is {l.shape}, expected ({r}, {r})")
    if t.layers and (r & (r - 1)):
        W("terrain", f"paint resolution {r} is not a power of two")
    if t.layers and not any(e for e in out if e.where == "terrain"):
        import numpy as np
        if int(sum(l.astype(np.int32) for l in t.layers).max()) > 255:
            W("terrain", "paint layers sum to more than 255 somewhere (base layer is clamped to 0)")

    if len(m.props) > MAX_PROPS:
        E("props", f"{len(m.props)} props, maximum is {MAX_PROPS}")
    half = m.header.size_m / 2
    for i, p in enumerate(m.props):
        w = f"prop[{i}] {p.kind.name.lower() if isinstance(p.kind, Kind) else p.kind}"
        if not isinstance(p.kind, Kind):
            E(w, "unknown kind"); continue
        x, y, z = astuple(p.position)
        if not -500 <= y <= 2000:
            E(w, f"y={y} m outside -500..2000 m")
        if abs(x) > half + 1 or abs(z) > half + 1:
            W(w, f"position ({x}, {z}) is outside the map (+-{half} m)")
        if p.kind == Kind.MODEL:
            if p.model_id is None or not 0 <= p.model_id <= 0xFFFF:
                E(w, "model_id must be 0..65535")
            if p.floors is not None and not 1 <= p.floors <= 40:
                E(w, f"floors {p.floors} must be 1..40")
            if p.color is not None and not all(0 <= c <= 255 for c in astuple(p.color)):
                E(w, "colour components must be 0..255")
            if p.collision not in (None, True, False):
                E(w, f"collision {p.collision!r}")
            if not isinstance(p.rotation, (int, float)):
                if not isinstance(p.rotation, Quaternion):
                    E(w, "needs rotation (angle in degrees or quaternion)")
                else:
                    nn = math.sqrt(sum(c ** 2 for c in astuple(p.rotation)))
                    if not 0.9 <= nn <= 1.1:
                        E(w, "quaternion length must be 0.9..1.1")
        else:
            if not isinstance(p.rotation, (int, float)):
                E(w, "this kind only supports a plain angle (rotation in degrees)")
            if p.kind == Kind.CAPTURE_POINT and p.rotation:
                E(w, "capture points cannot be rotated")
        if p.scale is not None:
            vals = [p.scale] if isinstance(p.scale, (int, float)) else list(astuple(p.scale))
            if not all(math.isfinite(v) and 0.05 <= v <= 5000 for v in vals):
                E(w, "scale must be within 0.05..5000")
            if p.kind == Kind.CAPTURE_POINT and not isinstance(p.scale, (int, float)):
                E(w, "capture point radius must be a single number")
        if p.kind == Kind.SPAWN:
            if p.team not in tuple(Team): E(w, "team must be 0, 1 or 2")
            if p.vehicle_type not in tuple(VehicleType): E(w, "vehicle_type must be 1, 2 or 4")
        if p.kind == Kind.CAPTURE_POINT and p.letter not in tuple(Letter):
            E(w, "letter must be 0..3 (a..d)")
    return out
