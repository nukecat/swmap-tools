"""Prop (object) binary codec - CustomMapSerializer.ReadObject / WriteObject."""
from __future__ import annotations
from dataclasses import astuple, fields
from enum import IntFlag
import math
from .binio import Reader, Writer, FormatError
from .model import Color, Letter, Prop, Kind, Quaternion, Team, Vec3, VehicleType

class Flags(IntFlag):
    YAW = 1 << 0
    UNIFORM = 1 << 1
    SCALE3 = 1 << 2
    COLOR = 1 << 3
    FLOORS = 1 << 4
    COLL_ON = 1 << 5
    COLL_OFF = 1 << 6

def _check_flags(kind: int, fl: int):
    allowed = 0x7F if kind == Kind.MODEL else 0x07
    if fl & ~allowed:
        raise FormatError(f"flags {fl:#04x} not allowed for kind {kind}")
    if kind != Kind.MODEL and not fl & Flags.YAW:
        raise FormatError("kinds other than model must use simple rotation")
    if fl & 6 == 6:
        raise FormatError("uniform and free scale are mutually exclusive")
    if fl & 0x60 == 0x60:
        raise FormatError("collision on and off are mutually exclusive")
    if kind == Kind.CAPTURE_POINT and fl & Flags.SCALE3:
        raise FormatError("capture points cannot have free scale")

def _enum(cls, value: int, what: str):
    try:
        return cls(value)
    except ValueError:
        raise FormatError(f"invalid {what} {value}") from None

def read_props(r: Reader, count: int) -> list:
    props = []
    for _ in range(count):
        kind = r.u8()
        if kind > 3:
            raise FormatError(f"unknown prop kind {kind}")
        fl = r.u8()
        _check_flags(kind, fl)
        kind = Kind(kind)
        p = Prop(kind=kind, position=Vec3(x=0.0, y=0.0, z=0.0))
        if kind == Kind.MODEL:
            p.model_id = r.varuint()
            if p.model_id > 0xFFFF:
                raise FormatError("model id out of range")
        for f in fields(p.position):
            setattr(p.position, f.name, r.varint() / 128.0)
        if fl & Flags.YAW:
            raw = r.u16()
            if kind == Kind.CAPTURE_POINT and raw:
                raise FormatError("capture point yaw must be 0")
            p.angle = raw * 45.0 / 8192.0               # raw * 360 / 65536 (exact in binary)
        else:
            p.rotation = Quaternion(**{f.name: r.s16() / 32767.0 for f in fields(Quaternion)})
            n = math.sqrt(sum(v ** 2 for v in astuple(p.rotation)))
            if not 0.9 <= n <= 1.1:
                raise FormatError("quaternion is not normalised")
        if fl & Flags.UNIFORM:
            p.scale = r.f32()
        elif fl & Flags.SCALE3:
            p.scale = Vec3(x=r.f32(), y=r.f32(), z=r.f32())
        if kind == Kind.MODEL:
            if fl & Flags.COLOR:
                p.color = Color(r=r.u8(), g=r.u8(), b=r.u8())
            if fl & Flags.FLOORS:
                p.floors = r.u8()
            p.collision = True if fl & Flags.COLL_ON else (False if fl & Flags.COLL_OFF else None)
        elif kind == Kind.SPAWN:
            p.team = _enum(Team, r.u8(), "team")
            b = r.u8()
            p.vehicle_type, p.reserve = _enum(VehicleType, b & 0x7F, "vehicle type"), bool(b & 0x80)
        elif kind == Kind.CAPTURE_POINT:
            p.letter = _enum(Letter, r.u8(), "capture point letter")
        props.append(p)
    return props


def write_props(w: Writer, props):
    for p in props:
        fl = 0
        if p.angle is not None:
            fl |= Flags.YAW
        elif p.kind != Kind.MODEL:
            raise ValueError("only models may use a full quaternion rotation")
        elif p.rotation is None:
            raise ValueError("prop needs angle or rotation")
        if isinstance(p.scale, (int, float)):
            fl |= Flags.UNIFORM
        elif p.scale is not None:
            fl |= Flags.SCALE3
        if p.kind == Kind.MODEL:
            if p.color is not None: fl |= Flags.COLOR
            if p.floors is not None: fl |= Flags.FLOORS
            if p.collision is True: fl |= Flags.COLL_ON
            elif p.collision is False: fl |= Flags.COLL_OFF
            elif p.collision is not None: raise ValueError(f"bad collision {p.collision!r}")
        _check_flags(p.kind, fl)
        w.u8(p.kind)
        w.u8(fl)
        if p.kind == Kind.MODEL:
            w.varuint(p.model_id)
        for c in astuple(p.position):
            w.varint(int(round(c * 128.0)))
        if fl & Flags.YAW:
            w.u16(int(round(p.angle * 8192.0 / 45.0)) & 0xFFFF)
        else:
            for v in astuple(p.rotation):
                w.s16(int(round(v * 32767.0)))
        if fl & Flags.UNIFORM:
            w.f32(float(p.scale))
        elif fl & Flags.SCALE3:
            for v in astuple(p.scale):
                w.f32(float(v))
        if p.kind == Kind.MODEL:
            if fl & Flags.COLOR:
                for v in astuple(p.color): w.u8(v)
            if fl & Flags.FLOORS:
                w.u8(p.floors)
        elif p.kind == Kind.SPAWN:
            w.u8(p.team)
            w.u8((int(p.vehicle_type) & 0x7F) | (0x80 if p.reserve else 0))
        elif p.kind == Kind.CAPTURE_POINT:
            w.u8(p.letter)
