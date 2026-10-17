"""Run:  pytest -q        (set SWMAP_SAMPLES=/path/to/real/maps to also run the sample-file tests)

The binary format has its own tests in swformats; these cover the folder layout, the JSON mapping and the CLI glue.
"""
import glob, json, os, random

import numpy as np
import pytest
from PIL import Image
from swformats import FormatError, MapCatalog, swmap as sw

import swmap
from swmap import terrain as T
from swmap.cli import main
from swmap.fileio import MapFile, deflated_body, inflated_body
from swmap.folder import (iso_to_ticks, obj_from_json, obj_to_json, read_folder, ticks_to_iso, write_folder)
from swmap.preview import render_preview

SAMPLES = sorted(glob.glob(os.path.join(os.environ.get("SWMAP_SAMPLES", "/nonexistent"), "*.swmap")))


def new_map(size=512, **kw):
    m = sw.SwMap(name="T", author="a", terrain=sw.Terrain.flat(size, height_res=129, alpha_res=128, **kw))
    m.modified_ticks = 639000000000000000
    return m


IDS = sorted(MapCatalog.default().props)[:4]          # prop ids the game knows (validate warns about others)


def all_kinds():
    O = sw.MapObject
    tilt = O(sw.PROP, prop_id=IDS[1], position=(3.0, 4.0, 6.0), rotation=(0.0, 23170 / 32767, 0.0, 23170 / 32767),
             scale=(1.0, 2.0, 3.0), color=(1, 2, 3, 255), floors=40, collision=sw.COLLISION_ON)
    tilt2 = O(sw.PROP, prop_id=IDS[2], position=(1.0, 2.0, 3.0), rotation=(0.1305263489484787, 0.0, 0.0, 0.9914448857307434))
    palm = O(sw.PROP, prop_id=IDS[0], position=(-8.0, 4.15625, -26.953125))
    palm.yaw = 0x907A / 65536 * 360
    objs = [palm, tilt, tilt2,
            O(sw.PROP, prop_id=IDS[3], scale=(2.5, 2.5, 2.5), collision=sw.COLLISION_OFF, glow=True),
            O(sw.SPAWN, position=(10.0, 6.0, 10.0), team=sw.TEAM_BLUE, spawn_type=sw.SPAWN_AIRCRAFT, reserve=True),
            O(sw.SPAWN, position=(12.0, 6.0, 10.0), team=sw.TEAM_DEATHMATCH, spawn_type=sw.SPAWN_WATER),
            O(sw.CAPTURE_POINT, position=(14.0, 6.0, 10.0), scale=(30.0, 30.0, 30.0), letter=0),
            O(sw.PLAYER_SPAWN, position=(0.0, 7.0, 0.0))]
    objs[4].yaw = 45.0
    return objs


# ---------------------------------------------------------------- heights
def test_height_conversion_matches_swformats():
    for m in (-100.0, 0.0, 2.0, 50.0, 400.0):
        assert int(T.m_to_height(m)) == sw.units_to_sample(m * 2)
    assert abs(float(T.height_to_m(T.m_to_height(50.0))) - 50.0) < 0.01
    assert float(T.height_to_m(0)) == -100.0 and float(T.height_to_m(65535)) == 400.0


# ---------------------------------------------------------------- full map
def test_full_map_roundtrip_in_memory_and_folder(tmp_path):
    m = new_map()
    m.objects = all_kinds()
    m.terrain.heights[40 * 129 + 40] = 30000
    m.terrain.splat[(10 * 128 + 10) * 4:(10 * 128 + 10) * 4 + 4] = bytes([55, 200, 0, 0])
    data = sw.write(m)
    mf = swmap.loads(data)
    assert mf.dumps() == data
    write_folder(mf, tmp_path / "f")
    back = read_folder(tmp_path / "f")
    assert back.dumps() == data
    assert not [i for i in swmap.validate(back.map) if i.level == "error"]


def test_folder_preserves_every_object_field(tmp_path):
    m = new_map()
    m.objects = all_kinds()
    mf = swmap.loads(sw.write(m))                       # as stored: quantised like a real file
    write_folder(mf, tmp_path / "f")
    back = read_folder(tmp_path / "f").map
    assert len(back.objects) == len(mf.map.objects)
    for a, b in zip(mf.map.objects, back.objects):
        assert (a.kind, a.prop_id, a.position, a.scale, a.color, a.floors, a.collision, a.glow, a.team, a.spawn_type,
                a.reserve, a.letter) == (b.kind, b.prop_id, b.position, b.scale, b.color, b.floors, b.collision, b.glow,
                                         b.team, b.spawn_type, b.reserve, b.letter)


def test_deflate_level_is_detected_and_kept(tmp_path):
    m = new_map()
    m.objects = all_kinds()
    data6 = sw.write(m, 6)
    mf = swmap.loads(data6)
    assert mf.level == 6 and mf.dumps() == data6
    write_folder(mf, tmp_path / "f")
    assert json.loads((tmp_path / "f" / "map.json").read_text())["deflate_level"] == 6
    assert read_folder(tmp_path / "f").dumps() == data6
    data9 = sw.write(m, 9)
    assert swmap.loads(data9).level == 9
    assert "deflate_level" not in json.loads((write_folder(swmap.loads(data9), tmp_path / "g") or (tmp_path / "g" / "map.json")).read_text())


def test_deflated_body_and_header_split():
    m = new_map()
    m.name, m.author = "Привіт", "ü"
    m.preview_jpeg = render_preview(m.terrain)
    data = sw.write(m)
    assert sw.read(data).name == "Привіт"
    assert inflated_body(data)[:1] and len(data) - len(deflated_body(data)) > 40


# ---------------------------------------------------------------- paint layers
def test_last_layer_is_the_implied_one(tmp_path):
    """swformats stores the FIRST layerCount-1 planes; the last layer is 255 - sum(the others)."""
    m = new_map()                                      # flat(): the first layer (grass, id 2) covers everything
    mf = MapFile(m)
    write_folder(mf, tmp_path / "f")
    ts = tmp_path / "f" / "terrain"
    assert sorted(p.name for p in ts.glob("paint_*.png")) == ["paint_00.png", "paint_01.png", "paint_02.png"]
    assert (np.array(Image.open(ts / "paint_00.png")) == 255).all()
    assert not np.array(Image.open(ts / "paint_01.png")).any()
    assert not np.array(Image.open(tmp_path / "f" / "_derived" / "paint_03_implied.png")).any()
    # paint the last layer by taking weight away from the first
    p0 = np.array(Image.open(ts / "paint_00.png")); p0[:10, :] = 0
    Image.fromarray(p0, "L").save(ts / "paint_00.png")
    t = read_folder(tmp_path / "f").map.terrain
    w = T.splat_array(t)
    assert (w[-10:, :, 3] == 255).all() and (w[:-10, :, 0] == 255).all()       # image top = +z = last array rows
    assert (w.sum(axis=2, dtype=int) == 255).all()


def test_overpainted_weights_are_reported_not_hidden(tmp_path):
    write_folder(MapFile(new_map()), tmp_path / "f")
    ts = tmp_path / "f" / "terrain"
    Image.fromarray(np.full((128, 128), 100, np.uint8), "L").save(ts / "paint_01.png")      # 255 + 100 > 255
    mf = read_folder(tmp_path / "f")
    assert mf.notes and "more than 255" in mf.notes[0]
    sw.read(mf.dumps())                                # swformats caps the weights, so the file is still valid


def test_pngs_are_top_down_with_plus_z_at_the_top(tmp_path):
    m = new_map()
    res = m.terrain.height_res
    for x in range(res):
        m.terrain.heights[0 * res + x] = 40000               # z = -size/2 -> bottom of the image
    m.terrain.heights[(res - 1) * res + 0] = 50000           # z = +size/2, x = -size/2 -> top-left
    write_folder(MapFile(m), tmp_path / "f")
    hm = np.array(Image.open(tmp_path / "f" / "terrain" / "heightmap.png"))
    assert (hm[-1, :] == 40000).all() and hm[0, 0] == 50000
    assert read_folder(tmp_path / "f").map.terrain.heights == m.terrain.heights


def test_old_folder_format_4_still_packs_identically(tmp_path):
    """folder/4 numbered the stored paint layers from 1 and defaulted to zlib level 6; the bytes were the same planes."""
    m = new_map()
    m.terrain.splat[(5 * 128 + 5) * 4:(5 * 128 + 5) * 4 + 4] = bytes([0, 99, 156, 0])
    mf = MapFile(m, 6)
    data = mf.dumps()
    write_folder(mf, tmp_path / "f")
    ts, meta = tmp_path / "f" / "terrain", tmp_path / "f" / "map.json"
    for i in (2, 1, 0):
        (ts / f"paint_{i:02d}.png").rename(ts / f"paint_{i + 1:02d}.png")
    j = json.loads(meta.read_text()); j["format"] = "swmap-folder/4"; j.pop("deflate_level"); meta.write_text(json.dumps(j))
    assert read_folder(tmp_path / "f").dumps() == data


def test_unknown_folder_format_rejected(tmp_path):
    write_folder(MapFile(new_map()), tmp_path / "f")
    meta = tmp_path / "f" / "map.json"
    j = json.loads(meta.read_text()); j["format"] = "swmap-folder/3"; meta.write_text(json.dumps(j))
    with pytest.raises(FormatError):
        read_folder(tmp_path / "f")


# ---------------------------------------------------------------- JSON mapping
def test_json_has_no_redundant_info_and_no_fixed_size_arrays(tmp_path):
    m = new_map()
    m.objects = all_kinds()
    write_folder(MapFile(m), tmp_path / "f")
    text = (tmp_path / "f" / "map.json").read_text(encoding="utf-8")
    meta = json.loads(text)
    for gone in ("counts", "height_formula", "height_points", "modified_utc", "modified_ticks"):
        assert gone not in text
    assert meta["format"] == "swmap-folder/5" and meta["modified"].endswith("Z")
    assert len(meta["modified"].split(".")[1]) == 8
    objs = json.loads((tmp_path / "f" / "objects.json").read_text(encoding="utf-8"))
    for o in objs:
        assert set(o["position"]) == {"x", "y", "z"}
        if "scale" in o:
            assert set(o["scale"]) == {"x", "y", "z"}
        if isinstance(o.get("rotation"), dict):
            assert set(o["rotation"]) == {"x", "y", "z", "w"} and all(isinstance(v, float) for v in o["rotation"].values())


def test_quaternion_floats_roundtrip_exactly():
    rng = random.Random(3)
    for _ in range(2000):
        q = tuple(rng.randint(-32767, 32767) / 32767.0 for _ in range(4))
        if abs(q[0]) < 1e-4 and abs(q[2]) < 1e-4:
            continue                                   # that one is a plain yaw, covered below
        o = sw.MapObject(sw.PROP, prop_id=1, rotation=q)
        assert obj_from_json(json.loads(json.dumps(obj_to_json(o)))).rotation == q


def test_yaw_and_position_roundtrip_through_json():
    rng = random.Random(4)
    for _ in range(2000):
        raw = rng.randint(0, 65535)
        o = sw.MapObject(sw.PROP, prop_id=2, position=tuple(rng.randint(-100000, 100000) / 64.0 for _ in range(3)))
        o.yaw = raw / 65536 * 360
        back = obj_from_json(json.loads(json.dumps(obj_to_json(o))))
        assert back.position == o.position              # metres in the JSON, exact multiples of 1/128
        assert round((back.yaw % 360) / 360 * 65536) & 0xFFFF == raw     # the stored 16-bit step is unchanged


def test_timestamp_is_lossless():
    for t in (639266060456442096, 621355968000000000, 639000000000000001, 864000000000):
        assert iso_to_ticks(ticks_to_iso(t)) == t
    assert iso_to_ticks("2026-10-03T06:34:05Z") == iso_to_ticks("2026-10-03T06:34:05.0000000Z")


def test_object_json_field_names():
    spawn = sw.MapObject(sw.SPAWN, position=(2.0, 4.0, 6.0), team=sw.TEAM_RED, spawn_type=sw.SPAWN_WATER, reserve=True)
    spawn.yaw = 90.0
    assert obj_to_json(spawn) == {"kind": "spawn", "position": {"x": 1.0, "y": 2.0, "z": 3.0}, "rotation": 90.0,
                                  "team": "red", "vehicle_type": "boat", "reserve": True}
    prop = sw.MapObject(sw.PROP, prop_id=3, scale=(2.0, 2.0, 2.0), collision=sw.COLLISION_OFF)
    j = obj_to_json(prop)
    assert j["prop_id"] == 3 and j["size"] == 2.0 and j["collision"] is False
    assert obj_from_json(j).collision == sw.COLLISION_OFF and obj_from_json(j).scale == (2.0, 2.0, 2.0)
    assert "collision" not in obj_to_json(sw.MapObject(sw.PROP, prop_id=3)) and "size" not in obj_to_json(sw.MapObject(sw.PROP))
    cp = sw.MapObject(sw.CAPTURE_POINT, scale=(30.0,) * 3, letter=2)
    assert obj_to_json(cp)["radius"] == 30.0 and obj_to_json(cp)["letter"] == "c" and "rotation" not in obj_to_json(cp)
    # older folders / aliases
    assert obj_from_json({"kind": "model", "model_id": 7, "position": {"x": 0, "y": 0, "z": 0}}).prop_id == 7
    assert obj_from_json({"kind": "spawn", "position": {"x": 0, "y": 0, "z": 0}, "team": "deathmatch"}).team == sw.TEAM_DEATHMATCH
    with pytest.raises(ValueError):
        obj_from_json({"kind": "prop", "prop_id": 1, "position": {"x": 0, "y": 0, "z": 0}, "collision": "on"})
    with pytest.raises(ValueError):
        obj_from_json({"kind": "prop", "position": {"x": 0, "y": 0, "z": 0}})


def test_bad_hex_colours_rejected():
    base = {"kind": "prop", "prop_id": 1, "position": {"x": 0, "y": 0, "z": 0}}
    assert obj_from_json({**base, "color": "#11223344"}).color == (0x11, 0x22, 0x33, 0x44)
    assert obj_from_json({**base, "color": "#112233"}).color == (0x11, 0x22, 0x33, 0xFF)
    with pytest.raises(ValueError):
        obj_from_json({**base, "color": "#1122"})


def test_weather_and_fog_mode_names(tmp_path):
    m = new_map()
    m.env.weather, m.env.fog_mode = 3, sw.FOG_EXPONENTIAL_SQUARED
    write_folder(MapFile(m), tmp_path / "f")
    env = json.loads((tmp_path / "f" / "map.json").read_text())["environment"]
    assert env["weather"] == "rain" and env["fog_mode"] == "exp_squared"
    meta = json.loads((tmp_path / "f" / "map.json").read_text())
    meta["environment"]["weather"], meta["environment"]["fog_mode"] = "CLOUDY", 2        # any case, or numbers
    (tmp_path / "f" / "map.json").write_text(json.dumps(meta))
    e = read_folder(tmp_path / "f").map.env
    assert e.weather == 2 and e.fog_mode == sw.FOG_EXPONENTIAL


# ---------------------------------------------------------------- container versions come from swformats
def test_version_follows_translucent_colours(tmp_path):
    m = new_map()
    m.objects = [sw.MapObject(sw.PROP, prop_id=1, position=(1, 2, 3), color=(255, 136, 0, 64)),
                 sw.MapObject(sw.PROP, prop_id=1, position=(2, 2, 3), color=(255, 136, 0, 255))]
    write_folder(MapFile(m), tmp_path / "f")
    objs = json.loads((tmp_path / "f" / "objects.json").read_text())
    assert objs[0]["color"] == "#ff880040" and objs[1]["color"] == "#ff8800"
    assert "container_version" not in json.loads((tmp_path / "f" / "map.json").read_text())
    assert int.from_bytes(read_folder(tmp_path / "f").dumps()[4:6], "little") == 2
    objs[0]["color"] = "#ff8800"                         # no alpha left -> version 1 by itself
    (tmp_path / "f" / "objects.json").write_text(json.dumps(objs))
    assert int.from_bytes(read_folder(tmp_path / "f").dumps()[4:6], "little") == 1


# ---------------------------------------------------------------- validation
@pytest.mark.parametrize("mut,level,frag", [
    (lambda m: setattr(m.objects[0], "scale", (0.01,) * 3), "warning", "scale"),
    (lambda m: setattr(m.objects[1], "floors", 41), "warning", "floors"),
    (lambda m: setattr(m.objects[4], "spawn_type", 3), "warning", "vehicle type"),
    (lambda m: setattr(m.objects[6], "rotation", (0.0, 0.5, 0.0, 0.8660254)), "warning", "rotated"),
    (lambda m: setattr(m.objects[0], "position", (0.0, 5000.0, 0.0)), "warning", "y ="),
    (lambda m: setattr(m.objects[0], "position", (9000.0, 5.0, 0.0)), "warning", "outside the map"),
    (lambda m: setattr(m.objects[0], "prop_id", 60000), "warning", "catalog"),
    (lambda m: setattr(m.env, "shadow_distance", 5), "warning", "shadow"),
    (lambda m: setattr(m, "name", "<b>x</b>"), "warning", "name"),
    (lambda m: m.objects.append(sw.MapObject(sw.CAPTURE_POINT, letter=0)), "error", "duplicate capture point"),
    (lambda m: setattr(m.terrain, "alpha_res", 100), "error", "alpha_res"),
])
def test_validation_catches(mut, level, frag):
    m = new_map()
    m.objects = all_kinds()
    mut(m)
    issues = [i for i in swmap.validate(m) if i.level == level]
    assert issues and any(frag in i.message for i in issues), [str(i) for i in swmap.validate(m)]


def test_valid_map_has_no_issues():
    m = new_map()
    m.objects = all_kinds()
    m.objects[1].rotation = (0.0, 0.7071067690849304, 0.0, 0.7071067690849304)
    issues = swmap.validate(m)
    assert not issues, [str(i) for i in issues]


def test_reader_rejects_garbage():
    with pytest.raises(FormatError):
        swmap.loads(b"nope")
    data = sw.write(new_map())
    with pytest.raises(FormatError):
        swmap.loads(data[:-5])


# ---------------------------------------------------------------- preview
def test_generated_preview_is_accepted_by_the_game_rules(tmp_path):
    m = new_map()
    m.terrain.heights[60 * 129 + 60] = 40000
    jpg = render_preview(m.terrain)
    assert sw.is_valid_preview(jpg) and sw.preview_size(jpg) == (640, 320)
    m.preview_jpeg = jpg
    assert sw.read(sw.write(m)).preview_jpeg == jpg


# ---------------------------------------------------------------- CLI
def test_new_unpack_pack_cycle(tmp_path, capsys):
    f, out = str(tmp_path / "blank"), str(tmp_path / "blank.swmap")
    assert main(["new", f, "--size", "256", "--height-res", "129", "--paint-resolution", "128", "--floor", "5"]) == 0
    assert main(["validate", f]) == 0
    assert main(["pack", f, "-o", out]) == 0
    m = swmap.load(out).map
    assert m.terrain.size_meters == 256 and m.terrain.height_res == 129 and m.preview_jpeg and sw.is_valid_preview(m.preview_jpeg)
    assert abs(T.height_to_m(m.terrain.heights[0]) - 5.0) < 0.01
    assert main(["info", out]) == 0
    assert main(["verify", out]) == 0
    assert capsys.readouterr().out.strip().endswith("identical")


def test_pack_touches_modified_time_unless_no_touch(tmp_path):
    m = new_map()
    write_folder(MapFile(m), tmp_path / "f")
    main(["pack", str(tmp_path / "f"), "-o", str(tmp_path / "a.swmap")])
    main(["pack", str(tmp_path / "f"), "--no-touch", "-o", str(tmp_path / "b.swmap")])
    assert swmap.load(tmp_path / "a.swmap").map.modified_ticks > 639000000000000000
    assert swmap.load(tmp_path / "b.swmap").map.modified_ticks == 639000000000000000


def test_pack_refuses_what_the_game_would_reject(tmp_path):
    write_folder(MapFile(new_map()), tmp_path / "f")
    objs = [{"kind": "capture_point", "position": {"x": 0, "y": 0, "z": 0}, "radius": 10, "letter": "a"}] * 2
    (tmp_path / "f" / "objects.json").write_text(json.dumps(objs))
    assert main(["pack", str(tmp_path / "f"), "-o", str(tmp_path / "x.swmap")]) == 1
    assert not (tmp_path / "x.swmap").exists()


# ---------------------------------------------------------------- real samples (optional)
@pytest.mark.skipif(not SAMPLES, reason="set SWMAP_SAMPLES to a folder of real .swmap files")
@pytest.mark.parametrize("path", SAMPLES)
def test_real_sample_roundtrips(path, tmp_path):
    raw = open(path, "rb").read()
    mf = swmap.load(path)
    write_folder(mf, tmp_path / "f")
    again = read_folder(tmp_path / "f").dumps()
    # same header and same inflated body; the deflate stream is identical whenever the same zlib wrote the file
    assert again[:len(again) - len(deflated_body(again)) - 4] == raw[:len(raw) - len(deflated_body(raw)) - 4]   # up to bodyLength
    assert inflated_body(again) == inflated_body(raw)
    assert not [i for i in swmap.validate(mf.map) if i.level == "error"]
