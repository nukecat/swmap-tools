"""High level load / save."""
from __future__ import annotations
from pathlib import Path

from swmap.binio import FormatError
from .container import compress, read_container, write_container
from .props import READ_VERSIONS, WRITE_VERSION
from .payload import decode_payload, encode_payload
from .model import SwMap
from .caps import compute_caps


DEFAULT_LEVEL = 6
_LEVELS_TO_TRY = (6, 9, 7, 8, 5, 4, 3, 2, 1)


def _detect_level(data: bytes, payload: bytes) -> int:
    """The game has written maps with different zlib levels (6 and 9 seen). Find the one that reproduces
    the stored stream so that unpack -> pack stays byte-identical; fall back to the default."""
    for lvl in _LEVELS_TO_TRY:
        if data.endswith(compress(payload, lvl)):
            return lvl
    return DEFAULT_LEVEL


def loads(data: bytes) -> SwMap:
    c = read_container(data)
    version = c.header.version
    if version not in READ_VERSIONS:
        raise FormatError(f"unsupported version {version}")
    env, terr, props = decode_payload(c.payload, version)
    m = SwMap(c.header, env, terr, props, c.preview_jpg)
    m.source_version = version                    # older maps are read and saved as the current version
    c.header.version = WRITE_VERSION
    # remembered so that dumps() reproduces the file exactly (not part of the model classes)
    m.deflate_level = _detect_level(data, c.payload)
    m.loaded_from_file = True
    return m


def load(path) -> SwMap:
    return loads(Path(path).read_bytes())


def dumps(m: SwMap, level: int | None = None) -> bytes:
    """Serialise to .swmap bytes. level=None keeps the zlib level the map was loaded with (default 6).
    A map built in memory without a preview gets a generated top-down placeholder (stored on
    m.preview_jpg); a loaded map is written back exactly as it was, even if it has no preview."""
    if level is None:
        level = getattr(m, "deflate_level", DEFAULT_LEVEL)
    if not m.preview_jpg and not getattr(m, "loaded_from_file", False):
        from .preview import render_preview
        m.preview_jpg = render_preview(m.terrain, m.header.size_m)
    return write_container(m.header, compute_caps(m.props), m.preview_jpg,
                           encode_payload(m.environment, m.terrain, m.props), level)


def save(m: SwMap, path, level: int | None = None):
    Path(path).write_bytes(dumps(m, level))
