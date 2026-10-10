"""Outer .swmap container: header, JPEG preview and raw-DEFLATE payload."""
from __future__ import annotations
import uuid, zlib
from dataclasses import dataclass
from .binio import Reader, Writer, FormatError
from .model import Header

MAGIC = b"SWMP"
VERSION = 2                # written version (1 can still be read; its colours have no alpha)


@dataclass
class Container:
    header: Header
    caps: bytes
    preview_jpg: bytes
    payload: bytes            # inflated


def read_container(data: bytes) -> Container:
    r = Reader(data)
    if r.take(4) != MAGIC:
        raise FormatError("not a .swmap file (bad magic)")
    version = r.u16()
    guid = uuid.UUID(bytes_le=r.take(16))
    name = r.string()
    author = r.string()
    ticks = r.i64()
    size = r.f32()
    caps = r.take(11)
    jpg = r.take(r.u32())
    comp = r.take(r.u32())
    if r.remaining:
        raise FormatError(f"{r.remaining} trailing bytes after payload")
    try:
        payload = zlib.decompress(comp, -15)
    except zlib.error as e:
        raise FormatError(f"payload is not valid DEFLATE: {e}") from None
    return Container(Header(guid, name, author, ticks, size, version), caps, jpg, payload)


def compress(payload: bytes, level: int = 6) -> bytes:
    """The game uses zlib level 6, raw deflate (the game has also written level 9; fileio.loads detects it)."""
    c = zlib.compressobj(level, zlib.DEFLATED, -15, 8)
    return c.compress(payload) + c.flush()


def write_container(header: Header, caps, preview_jpg: bytes, payload: bytes, level: int = 6) -> bytes:
    w = Writer()
    w.raw(MAGIC)
    w.u16(VERSION)
    w.raw(header.guid.bytes_le)
    w.string(header.name)
    w.string(header.author)
    w.i64(header.modified_ticks)
    w.f32(header.size_m)
    w.raw(bytes(caps))
    w.u32(len(preview_jpg))
    w.raw(preview_jpg)
    comp = compress(payload, level)
    w.u32(len(comp))
    w.raw(comp)
    return w.getvalue()
