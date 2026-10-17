"""Load / save .swmap files. The format itself is swformats' job; this only adds what unpack -> pack needs."""
from __future__ import annotations
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from swformats import swmap as sw

DEFAULT_LEVEL = 9                       # what swformats writes
_LEVELS_TO_TRY = (9, 6, 7, 8, 5, 4, 3, 2, 1)   # the game's files have been seen with 6 and 9


@dataclass
class MapFile:
    """A map plus the one thing swformats does not keep: the zlib level of the stream it was read from,
    so that writing the map back reproduces the original bytes whenever the same zlib produced them."""
    map: sw.SwMap
    level: int = DEFAULT_LEVEL
    notes: list = field(default_factory=list)       # things read_folder() noticed (e.g. paint weights above 255)

    def dumps(self, level: int | None = None) -> bytes:
        return sw.write(self.map, self.level if level is None else level)

    def save(self, path, level: int | None = None) -> None:
        Path(path).write_bytes(self.dumps(level))


def _leb(n: int) -> int:
    return max(1, (n.bit_length() + 6) // 7)


def deflated_body(data: bytes) -> bytes:
    """The compressed body of a (valid) .swmap: everything after the header's bodyLength field."""
    h = sw.read_header(data)
    name, author = h.name.encode("utf-8"), h.author.encode("utf-8")
    off = (4 + 2 + 16 + _leb(len(name)) + len(name) + _leb(len(author)) + len(author)
           + 8 + 4 + 11 + 4 + len(h.preview_jpeg) + 4)
    return data[off:]


def inflated_body(data: bytes) -> bytes:
    return zlib.decompress(deflated_body(data), -15)


def _detect_level(data: bytes) -> int:
    comp = deflated_body(data)
    raw = zlib.decompress(comp, -15)
    for lvl in _LEVELS_TO_TRY:
        c = zlib.compressobj(lvl, zlib.DEFLATED, -15)
        if c.compress(raw) + c.flush() == comp:
            return lvl
    return DEFAULT_LEVEL


def loads(data: bytes, max_bytes: int = sw.MAX_LOCAL_FILE_BYTES) -> MapFile:
    m = sw.read(data, max_bytes)          # strict: raises swformats.FormatError for anything the game rejects
    return MapFile(m, _detect_level(data))


def load(path, max_bytes: int = sw.MAX_LOCAL_FILE_BYTES) -> MapFile:
    return loads(Path(path).read_bytes(), max_bytes)
