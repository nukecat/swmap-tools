"""High level load / save."""
from __future__ import annotations
from pathlib import Path
from .container import read_container, write_container
from .payload import decode_payload, encode_payload
from .model import SwMap
from .caps import compute_caps


def loads(data: bytes) -> SwMap:
    c = read_container(data)
    env, terr, props = decode_payload(c.payload)
    return SwMap(c.header, env, terr, props, c.preview_jpg)


def load(path) -> SwMap:
    return loads(Path(path).read_bytes())


def dumps(m: SwMap, level: int = 6) -> bytes:
    """Serialise to .swmap bytes. A map without a preview gets a generated top-down placeholder
    (stored on m.preview_jpg), because the game's map list expects one."""
    if not m.preview_jpg:
        from .preview import render_preview
        m.preview_jpg = render_preview(m.terrain, m.header.size_m)
    return write_container(m.header, compute_caps(m.props), m.preview_jpg,
                           encode_payload(m.environment, m.terrain, m.props), level)


def save(m: SwMap, path, level: int = 6):
    Path(path).write_bytes(dumps(m, level))
