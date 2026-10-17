"""swmap command line:  unpack | pack | info | validate | verify | new"""
from __future__ import annotations
import argparse, collections, sys, tempfile
from pathlib import Path

from swformats import FormatError, MapCatalog, swmap as sw

from . import __version__
from .fileio import MapFile, inflated_body, load
from .folder import FOG_MODES, TEAMS, VEHICLES, WEATHER, read_folder, write_folder
from .terrain import height_to_m, heights_array
from .validate import validate


def _load_any(path: Path) -> MapFile:
    return read_folder(path) if path.is_dir() else load(path)


def _print_issues(issues) -> int:
    for i in issues:
        print(" ", i, file=sys.stderr)
    return sum(1 for i in issues if i.level == "error")


# ------------------------------------------------------------------------- commands
def cmd_unpack(a):
    src = Path(a.file)
    mf = load(src)
    out = Path(a.output) if a.output else src.with_suffix("")
    write_folder(mf, out, force=a.force, derived=not a.no_derived)
    t = mf.map.terrain
    print(f"unpacked {src.name} -> {out}/  ({len(mf.map.objects)} objects, heightmap {t.height_res}x{t.height_res}, "
          f"{t.layer_count} paint layers)")


def cmd_pack(a):
    src = Path(a.folder)
    mf = read_folder(src, regenerate_preview=a.regenerate_preview, touch=not a.no_touch)
    for n in mf.notes:
        print("note:", n, file=sys.stderr)
    if not a.no_validate:
        issues = validate(mf.map)
        if issues:
            print("validation:", file=sys.stderr)
        if _print_issues(issues):
            print("not packed: fix the errors above (or use --no-validate)", file=sys.stderr)
            return 1
    out = Path(a.output) if a.output else src.with_suffix(".swmap")
    data = mf.dumps(a.level)
    out.write_bytes(data)
    print(f"packed {src} -> {out}  ({len(data):,} bytes, {len(mf.map.objects)} objects)")


def cmd_info(a):
    p = Path(a.path)
    mf = _load_any(p)
    m = mf.map
    e, t = m.env, m.terrain
    cat = MapCatalog.default()
    print(f"{p.name}")
    print(f"  name      {m.name!r}   author {m.author!r}   container v{m.version}")
    print(f"  id        {m.id}   modified {m.modified:%Y-%m-%d %H:%M:%S} UTC")
    print(f"  size      {t.size_meters:g} m   heightmap {t.height_res}x{t.height_res}   paint {t.alpha_res}x{t.alpha_res}   "
          f"layers {[cat.layers[i].name if i in cat.layers else i for i in t.layer_ids]}")
    z = height_to_m(heights_array(t))
    print(f"  heights   {z.min():.1f} .. {z.max():.1f} m")
    print(f"  env       water={e.water} ice={e.ice} walls={e.edge_walls} fog={e.fog} time={e.time:g} "
          f"weather={WEATHER.get(e.weather, e.weather)} shadow={e.shadow_distance / sw.METERS_TO_UNITS:g} m "
          f"fog_mode={FOG_MODES.get(e.fog_mode, e.fog_mode)} fog={e.fog_distance / sw.METERS_TO_UNITS:g} m "
          f"#{''.join('%02x' % c for c in e.fog_color)}")
    kinds = collections.Counter(o.kind for o in m.objects)
    names = {sw.PROP: "prop", sw.SPAWN: "spawn", sw.CAPTURE_POINT: "capture_point", sw.PLAYER_SPAWN: "player_spawn"}
    print(f"  objects   {len(m.objects)}   " + "  ".join(f"{names[k]}={v}" for k, v in sorted(kinds.items())))
    props = collections.Counter(o.prop_id for o in m.objects if o.kind == sw.PROP)
    if props:
        label = lambda i: cat.props[i].name if i in cat.props else f"#{i}"
        print("  props     " + "  ".join(f"{label(k)}x{v}" for k, v in props.most_common(8)) + ("  ..." if len(props) > 8 else ""))
    c = m.caps
    sp = [f"{TEAMS[tm]}: " + "/".join(f"{c.spawn_counts[tm * 3 + s]}{v}" for s, v in enumerate("TBP"))
          for tm in range(3) if any(c.spawn_counts[tm * 3:tm * 3 + 3])]
    print(f"  caps      spawns ({', '.join(sp) or 'none'}; T=tank B=boat P=plane)  capture points={c.capture_points}  "
          f"player spawns={c.player_spawns}")


def cmd_validate(a):
    rc = 0
    for f in a.paths:
        mf = _load_any(Path(f))
        for n in mf.notes:
            print(f"{f}: note: {n}", file=sys.stderr)
        issues = validate(mf.map)
        print(f"{f}: {'OK' if not issues else str(len(issues)) + ' issue(s)'}")
        rc |= bool(_print_issues(issues))
    return rc


def _first_diff(a: bytes, b: bytes) -> str:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return f"first difference at byte {i}"
    return f"length {len(a)} vs {len(b)}"


def _same_content(a: bytes, b: bytes) -> bool:
    try:
        return inflated_body(a) == inflated_body(b)
    except Exception:                                     # noqa: BLE001
        return False


def cmd_verify(a):
    bad = 0
    for f in a.files:
        raw = Path(f).read_bytes()
        try:
            mf = load(f)
            direct = mf.dumps()
            with tempfile.TemporaryDirectory() as td:
                write_folder(mf, td, force=True)
                via_folder = read_folder(td).dumps()
            if direct == raw and via_folder == raw:
                status = "identical"
            elif _same_content(direct, raw) and _same_content(via_folder, raw):
                # only the deflate stream differs: the game's zlib build compressed it differently from Python's
                status = "same content, different deflate stream"
            else:
                bad += 1
                status = "DIFFERS (" + ("folder: " + _first_diff(raw, via_folder) if direct == raw else _first_diff(raw, direct)) + ")"
        except Exception as ex:                            # noqa: BLE001
            bad += 1
            status = f"ERROR {type(ex).__name__}: {ex}"
        print(f"{Path(f).name}: {status}")
    return 1 if bad else 0


def cmd_new(a):
    t = sw.Terrain.flat(a.size, height_res=a.height_res, alpha_res=a.paint_resolution, ground_units=a.floor * sw.METERS_TO_UNITS)
    m = sw.SwMap(name=a.name, author=a.author, terrain=t)
    m.touch()
    write_folder(MapFile(m), a.folder, force=a.force, mark_no_preview=False)   # pack renders the preview
    print(f"created empty map folder {a.folder}  (edit it, then: swmap pack {a.folder})")


# ------------------------------------------------------------------------- entry
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="swmap", description="Unpack / pack .swmap custom maps (format code: swformats).")
    ap.add_argument("--version", action="version", version=f"swmap-tools {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("unpack", help="split a .swmap into editable files")
    s.add_argument("file"); s.add_argument("-o", "--output", help="output folder (default: file name without extension)")
    s.add_argument("-f", "--force", action="store_true", help="write into a non-empty folder")
    s.add_argument("--no-derived", action="store_true", help="skip the _derived/ helper images")
    s.set_defaults(fn=cmd_unpack)

    s = sub.add_parser("pack", help="build a .swmap from an unpacked folder")
    s.add_argument("folder"); s.add_argument("-o", "--output", help="output file (default: <folder>.swmap)")
    s.add_argument("--no-validate", action="store_true", help="do not run the validity checks")
    s.add_argument("--regenerate-preview", action="store_true", help="replace preview.jpg by a generated top-down render")
    s.add_argument("--no-touch", action="store_true", help="keep the modified time from map.json (default: set it to now)")
    s.add_argument("--level", type=int, default=None, help="zlib level (default: the map's original level, else 9)")
    s.set_defaults(fn=cmd_pack)

    s = sub.add_parser("info", help="summarise a .swmap file or unpacked folder")
    s.add_argument("path"); s.set_defaults(fn=cmd_info)

    s = sub.add_parser("validate", help="check maps against the game's loading rules")
    s.add_argument("paths", nargs="+"); s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("verify", help="check that unpack->pack reproduces the file")
    s.add_argument("files", nargs="+"); s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("new", help="create a flat empty map folder to start from")
    s.add_argument("folder"); s.add_argument("--name", default="New map"); s.add_argument("--author", default="")
    s.add_argument("--size", type=float, default=1024.0, help="map size in metres (128..8000, multiple of 16)")
    s.add_argument("--height-res", "--height-points", dest="height_res", type=int, default=0,
                   help="heightmap samples per side: 129, 257, 513, 1025 or 2049 (default: by map size)")
    s.add_argument("--paint-resolution", type=int, default=0,
                   help="paint texels per side: 128, 256, 512 or 1024 (default: by map size)")
    s.add_argument("--floor", type=float, default=2.0, help="flat terrain height in metres")
    s.add_argument("-f", "--force", action="store_true"); s.set_defaults(fn=cmd_new)

    a = ap.parse_args(argv)
    try:
        return a.fn(a) or 0
    except (FormatError, FileNotFoundError, FileExistsError, ValueError, KeyError) as e:
        print(f"swmap: error: {e}", file=sys.stderr)
        return 1
    except BrokenPipeError:                      # e.g. `swmap info x | head`
        try:
            sys.stdout.close()
        except Exception:                        # noqa: BLE001
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
