"""Run:  pytest -q        (set SWMAP_SAMPLES=/path/to/real/maps to also run the byte-identical sample tests)"""
import glob, os, random

import numpy as np
import pytest

import swmap
from swmap import terrain as T
from swmap.binio import FormatError, Reader, Writer
from swmap.caps import compute_caps
from swmap.folder import read_folder, write_folder
from swmap.model import Color, Letter, Prop, Kind, Quaternion, Team, Vec3, VehicleType

SAMPLES = sorted(glob.glob(os.path.join(os.environ.get("SWMAP_SAMPLES", "/nonexistent"), "*.swmap")))


# ---------------------------------------------------------------- codecs
def test_varints_roundtrip():
    w = Writer()
    vals = [0, 1, 127, 128, 16383, 16384, 2 ** 31 - 1, 2 ** 32 - 1]
    for v in vals: w.varuint(v)
    sv = [0, -1, 1, -64, 64, -(2 ** 30), 2 ** 30]
    for v in sv: w.varint(v)
    w.string("Привіт ‹color›")
    r = Reader(w.getvalue())
    assert [r.varuint() for _ in vals] == vals
    assert [r.varint() for _ in sv] == sv
    assert r.string() == "Привіт ‹color›" and r.remaining == 0


@pytest.mark.parametrize("seed", range(3))
def test_height_codec_is_lossless(seed):
    rng = np.random.default_rng(seed)
    n = 65
    h = rng.integers(0, 65536, (n, n)).astype(np.uint16)          # worst case: white noise incl. big jumps
    h[10:20, 10:20] = 0; h[30:40, 5:9] = 65535
    lo, hi = T.encode_heights(h)
    assert (T.decode_heights(lo, hi, n) == h).all()


def test_splat_codec_is_lossless():
    rng = np.random.default_rng(1)
    l = rng.integers(0, 256, (64, 64)).astype(np.uint8)
    assert (T.decode_splat(T.encode_splat(l), 64) == l).all()


def test_known_heights():
    # game constants: 2 m default floor, bump hill 50 m
    assert int(T.m_to_height(2.0)) in (13368, 13369)
    assert abs(float(T.height_to_m(T.m_to_height(50.0))) - 50.0) < 0.01


# ---------------------------------------------------------------- props
def all_kinds():
    return [
        Prop(Kind.MODEL, Vec3(-4.0, 2.078125, -13.4765625), model_id=1, angle=0x907A * 45.0 / 8192.0),   # the palm tree: stored yaw is quantised to 360/65536 degrees
        Prop(Kind.MODEL, Vec3(1.5, 2.0, 3.0), model_id=300, rotation=Quaternion(0, 23170 / 32767, 0, 23170 / 32767), scale=Vec3(1.0, 2.0, 3.0),
             color=Color(1, 2, 3), floors=40, collision=True),
        Prop(Kind.MODEL, Vec3(0.0, 0.0, 0.0), model_id=0, angle=0.0, scale=2.5, collision=False),
        Prop(Kind.SPAWN, Vec3(5.0, 3.0, 5.0), angle=45.0, team=Team.BLUE, vehicle_type=VehicleType.PLANE, reserve=True),
        Prop(Kind.SPAWN, Vec3(6.0, 3.0, 5.0), angle=45.0, team=Team.FFA, vehicle_type=VehicleType.BOAT),
        Prop(Kind.CAPTURE_POINT, Vec3(7.0, 3.0, 5.0), angle=0.0, scale=30.0, letter=Letter.A),
        Prop(Kind.PLAYER_SPAWN, Vec3(0.0, 3.5, 0.0), angle=0.0),
    ]


def test_full_map_roundtrip_in_memory_and_folder(tmp_path):
    m = swmap.SwMap.new("T", "a", 512, 129, 128)
    m.props = all_kinds()
    m.terrain.heights[40:60, 40:60] = 30000
    m.terrain.layers[0][10:20, 10:20] = 200
    data = swmap.dumps(m)
    m2 = swmap.loads(data)
    assert swmap.dumps(m2) == data
    assert m2.props == m.props
    write_folder(m2, tmp_path / "f")
    m3 = read_folder(tmp_path / "f")
    assert swmap.dumps(m3) == data
    assert not [i for i in swmap.validate(m3) if i.level == "error"]


def test_caps():
    caps = compute_caps(all_kinds())
    assert caps == [0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1]     # ffa boat; blue plane; 1 capture point; 1 player spawn
    many = [Prop(Kind.SPAWN, Vec3(0, 0, 0), angle=0.0, team=Team.RED, vehicle_type=VehicleType.TANK)] * 300
    assert compute_caps(many)[3] == 255                  # saturates


# ---------------------------------------------------------------- validation
@pytest.mark.parametrize("mut,frag", [
    (lambda m: setattr(m.props[0], "scale", 0.01), "scale"),
    (lambda m: setattr(m.props[0], "floors", 41), "floors"),
    (lambda m: setattr(m.props[3], "vehicle_type", 3), "vehicle_type"),
    (lambda m: setattr(m.props[5], "angle", 10.0), "rotated"),
    (lambda m: setattr(m.props[0], "position", Vec3(0, 5000, 0)), "outside"),
    (lambda m: setattr(m.environment, "shadow_distance_units", 5), "shadow"),
])
def test_validation_catches(mut, frag):
    m = swmap.SwMap.new("T", "a", 512, 129, 128)
    m.props = all_kinds()
    mut(m)
    errs = [i for i in swmap.validate(m) if i.level == "error"]
    assert errs and any(frag in i.message for i in errs), errs


def test_reader_rejects_garbage():
    with pytest.raises(FormatError):
        swmap.loads(b"nope")
    m = swmap.SwMap.new()
    data = bytearray(swmap.dumps(m))
    with pytest.raises(FormatError):
        swmap.loads(bytes(data[:-5]))


# ---------------------------------------------------------------- real samples (optional)
@pytest.mark.skipif(not SAMPLES, reason="set SWMAP_SAMPLES to a folder of real .swmap files")
@pytest.mark.parametrize("path", SAMPLES)
def test_real_sample_byte_identical(path, tmp_path):
    raw = open(path, "rb").read()
    m = swmap.load(path)
    assert swmap.dumps(m) == raw
    write_folder(m, tmp_path / "f")
    assert swmap.dumps(read_folder(tmp_path / "f")) == raw
    assert not [i for i in swmap.validate(m) if i.level == "error"]


# ---------------------------------------------------------------- folder JSON shape
def test_json_has_no_redundant_info_and_no_fixed_size_arrays(tmp_path):
    import json
    m = swmap.SwMap.new("T", "a", 512, 129, 128)
    m.props = all_kinds()
    write_folder(m, tmp_path / "f")
    meta = json.loads((tmp_path / "f" / "map.json").read_text(encoding="utf-8"))
    text = (tmp_path / "f" / "map.json").read_text(encoding="utf-8")
    for gone in ("counts", "height_formula", "height_points", "paint_resolution", "modified_utc", "modified_ticks"):
        assert gone not in text
    assert meta["modified"].endswith("Z") and len(meta["modified"].split(".")[1]) == 8       # 7 digits + Z
    objs = json.loads((tmp_path / "f" / "objects.json").read_text(encoding="utf-8"))
    assert isinstance(objs, list)
    for o in objs:
        assert set(o["position"]) == {"x", "y", "z"}
        for k in ("scale",):
            if k in o: assert set(o[k]) == {"x", "y", "z"}
        if "quaternion" in o:
            assert set(o["quaternion"]) == {"x", "y", "z", "w"} and all(isinstance(v, float) for v in o["quaternion"].values())
    # nothing but dicts / scalars except the variable-length layer id list
    def no_lists(v, path=""):
        if isinstance(v, dict):
            for k, x in v.items(): no_lists(x, path + "/" + k)
        elif isinstance(v, list):
            assert path == "/paint_layer_ids", path
    no_lists(meta)


def test_quaternion_floats_roundtrip_exactly():
    import json
    from swmap.folder import prop_to_json, prop_from_json
    rng = random.Random(3)
    for _ in range(2000):
        q = Quaternion(*(rng.randint(-32767, 32767) / 32767.0 for _ in range(4)))
        p = Prop(Kind.MODEL, Vec3(0, 0, 0), model_id=1, rotation=q)
        back = prop_from_json(json.loads(json.dumps(prop_to_json(p))))
        assert back.rotation == q


def test_yaw_and_position_roundtrip_through_json():
    import json
    from swmap.folder import prop_to_json, prop_from_json
    rng = random.Random(4)
    for _ in range(2000):
        raw = rng.randint(0, 65535)
        p = Prop(Kind.MODEL, Vec3(*(rng.randint(-100000, 100000) / 128.0 for _ in range(3))), model_id=2,
                 angle=raw * 45.0 / 8192.0)
        back = prop_from_json(json.loads(json.dumps(prop_to_json(p))))
        assert back.position == p.position
        # the JSON shows yaw rounded to 4 decimals; what is stored (a 16-bit step) must be unchanged
        assert int(round(back.angle * 8192.0 / 45.0)) & 0xFFFF == raw


def test_timestamp_is_lossless():
    from swmap.model import ticks_to_iso, iso_to_ticks
    for t in (639266060456442096, 621355968000000000, 639000000000000001, 0 + 864000000000):
        assert iso_to_ticks(ticks_to_iso(t)) == t
    assert iso_to_ticks("2026-10-03T06:34:05Z") == iso_to_ticks("2026-10-03T06:34:05.0000000Z")
