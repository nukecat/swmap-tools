"""In-memory representation of a map."""
from __future__ import annotations
from enum import IntEnum, IntFlag
import uuid
from dataclasses import dataclass, field
from typing import Optional, Sequence, Union

import numpy as np

class Kind(IntEnum):
    MODEL = 0
    SPAWN = 1
    CAPTURE_POINT = 2
    PLAYER_SPAWN = 3

class Team(IntEnum):
    FFA = 0
    RED = 1
    BLUE = 2

class Collision(IntEnum):
    DEFAULT = 0
    ON = 1
    OFF = 2

class Letter(IntEnum):
    A = 0
    B = 1
    C = 2
    D = 3

# it's actually a bitmask, but game enforces it to be
# either 1, 2 or 4, so making it enum makes more sense
class VehicleType(IntEnum):
    TANK = 1 << 0
    BOAT = 1 << 1
    PLANE = 1 << 2

UNITS_PER_M = 2          # one game unit is 0.5 m
NET_EPOCH_TICKS = 621355968000000000          # 1970-01-01 in .NET ticks

@dataclass
class Environment:
    water: bool = True
    ice: bool = False
    edge_walls: bool = True
    fog: bool = False
    time: float = 0.85
    weather: int = 1
    shadow_distance_units: int = 300
    fog_mode: int = 1
    fog_color: tuple = (0xA0, 0xAA, 0xB4)
    fog_distance_units: int = 1500

    shadow_distance_m = property(lambda s: s.shadow_distance_units / UNITS_PER_M)
    fog_distance_m = property(lambda s: s.fog_distance_units / UNITS_PER_M)


@dataclass
class Terrain:
    heights: np.ndarray                      # uint16 (N, N), metres = v*500/65536-100
    layer_ids: list                          # texture id per paint layer (first = implied base layer)
    layers: list                             # uint8 (R, R) arrays for layers 1..n-1 (base is implied)
    paint_resolution: int = 0

    def __post_init__(self):
        if self.layers:
            self.paint_resolution = int(self.layers[0].shape[0])

    @property
    def height_points(self) -> int:
        return int(self.heights.shape[0])

@dataclass
class Color:
    r: int
    g: int
    b: int

@dataclass
class Vec3:
    x: float
    y: float
    z: float

@dataclass
class Quaternion:
    x: float
    y: float
    z: float
    w: float

@dataclass
class Prop:
    kind: Kind
    position: Vec3                                 # metres (x, y up, z); resolution 1/128 m
    model_id: Optional[int] = None                 # kind == model
    yaw_deg: Optional[float] = None                # simple rotation (required for kinds != model)
    quat_rotation: Optional[Quaternion] = None     # full rotation as floats
    scale: Union[None, float, Vec3] = None         # float = uniform (capture point: radius), tuple = x, y, z
    color: Optional[Color] = None
    floors: Optional[int] = None
    collision: Collision = Collision.DEFAULT
    team: Team = Team.FFA                          # spawn: 0 deathmatch, 1 red, 2 blue
    spawn_type: VehicleType = VehicleType.TANK     # spawn: 1, 2 or 4
    reserve: bool = False                          # spawn
    letter: Letter = Letter.A                      # capture point 0..3 = a..d


@dataclass
class Header:
    guid: uuid.UUID
    name: str = "New map"
    author: str = ""
    modified_ticks: int = 0
    size_m: float = 1024.0
    version: int = 1

    @property
    def modified_utc(self):
        import datetime
        us = (self.modified_ticks - NET_EPOCH_TICKS) // 10
        return datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(microseconds=us)


_TICKS_PER_DAY = 864_000_000_000


def ticks_to_iso(ticks: int) -> str:
    """.NET ticks -> 'YYYY-MM-DDTHH:MM:SS.fffffffZ' (100 ns resolution, lossless)."""
    import datetime
    days, rem = divmod(ticks, _TICKS_PER_DAY)
    secs, frac = divmod(rem, 10_000_000)
    d = datetime.date.fromordinal(days + 1)
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}T{secs // 3600:02d}:{secs // 60 % 60:02d}:{secs % 60:02d}.{frac:07d}Z"


def iso_to_ticks(s: str) -> int:
    import datetime, re
    mt = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)(?:\.(\d{1,7}))?(?:Z|\+00:00)?", s.strip())
    if not mt:
        raise ValueError(f"bad timestamp {s!r}; expected e.g. 2026-10-03T06:34:05.6442096Z (UTC)")
    y, mo, d, h, mi, se = (int(g) for g in mt.groups()[:6])
    frac = int((mt.group(7) or "0").ljust(7, "0"))
    days = datetime.date(y, mo, d).toordinal() - 1
    return days * _TICKS_PER_DAY + (h * 3600 + mi * 60 + se) * 10_000_000 + frac


def now_ticks() -> int:
    import time
    return NET_EPOCH_TICKS + int(time.time() * 10_000_000)


@dataclass
class SwMap:
    header: Header
    environment: Environment
    terrain: Terrain
    props: list = field(default_factory=list)
    preview_jpg: bytes = b""

    # --- convenience -----------------------------------------------------------------
    @property
    def caps(self) -> list:
        from .caps import compute_caps
        return compute_caps(self.props)

    @classmethod
    def load(cls, path) -> "SwMap":
        from .fileio import load
        return load(path)

    def save(self, path, **kw):
        from .fileio import save
        return save(self, path, **kw)

    def validate(self):
        from .validate import validate
        return validate(self)

    @classmethod
    def new(cls, name="New map", author="", size_m=1024.0, height_points=513, paint_resolution=512,
            floor_m=2.0, layer_ids=(2, 4, 5, 9)):
        from .terrain import m_to_height
        h = np.full((height_points, height_points), m_to_height(floor_m), dtype=np.uint16)
        layers = [np.zeros((paint_resolution, paint_resolution), np.uint8) for _ in layer_ids[1:]]
        return cls(Header(uuid.uuid4(), name, author, now_ticks(), float(size_m)), Environment(),
                   Terrain(h, list(layer_ids), layers, paint_resolution))
