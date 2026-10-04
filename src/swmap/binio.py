"""Little-endian binary reader/writer incl. .NET BinaryWriter strings and 7-bit varints."""
from __future__ import annotations
import struct


class FormatError(ValueError):
    """The data does not look like a valid .swmap / payload."""


class Reader:
    __slots__ = ("b", "p")

    def __init__(self, data: bytes, pos: int = 0):
        self.b = data
        self.p = pos

    def take(self, n: int) -> bytes:
        if n < 0 or self.p + n > len(self.b):
            raise FormatError(f"unexpected end of data at offset {self.p} (need {n} bytes)")
        v = self.b[self.p:self.p + n]
        self.p += n
        return v

    def _u(self, fmt: str, n: int):
        if self.p + n > len(self.b):
            raise FormatError(f"unexpected end of data at offset {self.p}")
        v = struct.unpack_from(fmt, self.b, self.p)[0]
        self.p += n
        return v

    def u8(self): return self._u("<B", 1)
    def u16(self): return self._u("<H", 2)
    def s16(self): return self._u("<h", 2)
    def u32(self): return self._u("<I", 4)
    def i64(self): return self._u("<q", 8)
    def f32(self): return self._u("<f", 4)

    def varuint(self) -> int:
        n = shift = 0
        while True:
            c = self.u8()
            n |= (c & 0x7F) << shift
            if not c & 0x80:
                return n
            shift += 7
            if shift > 28:
                raise FormatError("varint too long")

    def varint(self) -> int:
        v = self.varuint()
        return (v >> 1) ^ -(v & 1)

    def string(self) -> str:
        return self.take(self.varuint()).decode("utf-8")

    @property
    def remaining(self) -> int:
        return len(self.b) - self.p


class Writer:
    def __init__(self):
        self.b = bytearray()

    def raw(self, data: bytes): self.b += data
    def u8(self, v): self.b += struct.pack("<B", v)
    def u16(self, v): self.b += struct.pack("<H", v)
    def s16(self, v): self.b += struct.pack("<h", v)
    def u32(self, v): self.b += struct.pack("<I", v)
    def i64(self, v): self.b += struct.pack("<q", v)
    def f32(self, v): self.b += struct.pack("<f", v)

    def varuint(self, v: int):
        if not 0 <= v < (1 << 32):
            raise ValueError(f"varuint out of range: {v}")
        while v >= 0x80:
            self.b.append((v & 0x7F) | 0x80)
            v >>= 7
        self.b.append(v)

    def varint(self, v: int):
        self.varuint(((v << 1) ^ (v >> 31)) & 0xFFFFFFFF)

    def string(self, s: str):
        e = s.encode("utf-8")
        self.varuint(len(e))
        self.b += e

    def getvalue(self) -> bytes:
        return bytes(self.b)
