"""CustomMapCaps - the 11 summary bytes of the container header (CustomMapCaps.Compute / ToBytes)."""
from __future__ import annotations
from .model import Kind

_SLOT = {2: 1, 4: 2}        # spawn type 1 -> slot 0, 2 -> 1, 4 -> 2 (anything else counts as 0)

def compute_caps(props) -> list:
    """bytes 0-8: spawns at index min(team,2)*3 + slot; byte 9: capture points; byte 10: player spawns.
    Every counter saturates at 255; model props are not counted."""
    c = [0] * 11
    for p in props:
        if p.kind == Kind.SPAWN:
            i = min(p.team, 2) * 3 + _SLOT.get(p.spawn_type, 0)
        elif p.kind == Kind.CAPTURE_POINT:
            i = 9
        elif p.kind == Kind.PLAYER_SPAWN:
            i = 10
        else:
            continue
        c[i] = min(c[i] + 1, 255)
    return c


def spawn_count(caps, team: int, type_mask: int) -> int:
    """CustomMapCaps.GetSpawnCount(team, mask): mask bit n selects spawn slot n."""
    return sum(caps[team * 3 + s] for s in range(3) if type_mask >> s & 1)
