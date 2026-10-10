"""swmap command line:  unpack | pack | info | validate | verify | new"""
from __future__ import annotations
import argparse, collections, sys, tempfile
from pathlib import Path

from swmap.container import read_container

from . import __version__
from .binio import FormatError
from .caps import compute_caps
from .fileio import load, dumps
from .folder import read_folder, write_folder
from .model import Kind, SwMap
from .validate import validate


def _load_any(path: Path, **kw) -> SwMap:
    return read_folder(path, **kw) if path.is_dir() else load(path)


def _print_issues(issues) -> int:
    for i in issues:
        print(" ", i, file=sys.stderr)
    return sum(1 for i in issues if i.level == "error")


# ------------------------------------------------------------------------- commands
def cmd_unpack(a):
    src = Path(a.file)
    m = load(src)
    out = Path(a.output) if a.output else src.with_suffix("")
    write_folder(m, out, force=a.force, derived=not a.no_derived)
    print(f"unpacked {src.name} -> {out}/  ({len(m.props)} props, heightmap {m.terrain.height_points}x{m.terrain.height_points}, "
          f"{len(m.terrain.layer_ids)} paint layers)")


def cmd_pack(a):
    src = Path(a.folder)
    m = read_folder(src, regenerate_preview=a.regenerate_preview, touch=not a.no_touch)
    if not a.no_validate:
        issues = validate(m)
        if issues:
            print("validation:", file=sys.stderr)
        if _print_issues(issues):
            print("not packed: fix the errors above (or use --no-validate)", file=sys.stderr)
            return 1
    out = Path(a.output) if a.output else src.with_suffix(".swmap")
    data = dumps(m, a.level)
    out.write_bytes(data)
    print(f"packed {src} -> {out}  ({len(data):,} bytes, {len(m.props)} props)")


def cmd_info(a):
    p = Path(a.path)
    m = _load_any(p)
    h, e, t = m.header, m.environment, m.terrain
    print(f"{p.name}")
    print(f"  name      {h.name!r}   author {h.author!r}   container v{getattr(m, 'source_version', h.version)}" + (" (saved as v2)" if getattr(m, "source_version", 2) != 2 else ""))
    print(f"  guid      {h.guid}   modified {h.modified_utc:%Y-%m-%d %H:%M:%S} UTC")
    print(f"  size      {h.size_m:g} m   heightmap {t.height_points}x{t.height_points}   paint {t.paint_resolution}x{t.paint_resolution}   layers {t.layer_ids}")
    from .terrain import height_to_m
    z = height_to_m(t.heights)
    print(f"  heights   {z.min():.1f} .. {z.max():.1f} m")
    print(f"  env       water={e.water} ice={e.ice} walls={e.edge_walls} fog={e.fog} time={e.time:g} weather={getattr(e.weather, 'name', e.weather)} "
          f"shadow={e.shadow_distance_m:g} m fog_mode={getattr(e.fog_mode, 'name', e.fog_mode)} fog={e.fog_distance_m:g} m #{''.join('%02x' % c for c in e.fog_color)}")
    kinds = collections.Counter(Kind(q.kind).name.lower() for q in m.props)
    print(f"  props     {len(m.props)}   " + "  ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    models = collections.Counter(q.model_id for q in m.props if q.kind == Kind.MODEL)
    if models:
        print("  models    " + "  ".join(f"#{k}x{v}" for k, v in models.most_common(8)) + ("  ..." if len(models) > 8 else ""))
    caps = compute_caps(m.props)
    names = ("ffa", "red", "blue")
    sp = [f"{names[t]}: " + "/".join(f"{caps[t * 3 + s]}{v}" for s, v in enumerate("TBP")) for t in range(3) if any(caps[t * 3:t * 3 + 3])]
    print(f"  caps      spawns ({', '.join(sp) or 'none'}; T=tank B=boat P=plane)  capture points={caps[9]}  player spawns={caps[10]}")


def cmd_validate(a):
    rc = 0
    for f in a.paths:
        m = _load_any(Path(f))
        issues = validate(m)
        print(f"{f}: {'OK' if not issues else str(len(issues)) + ' issue(s)'}")
        rc |= bool(_print_issues(issues))
    return rc


def _first_diff(a: bytes, b: bytes) -> str:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return f"first difference at byte {i}"
    return f"length {len(a)} vs {len(b)}"


def cmd_verify(a):
    bad = 0
    for f in a.files:
        raw = Path(f).read_bytes()
        try:
            m = load(f)
            v1 = getattr(m, "source_version", 2) != 2          # v1 files are upgraded to v2, so compare with the v2 form
            ref = dumps(m) if v1 else raw
            ok1 = dumps(m) == ref
            with tempfile.TemporaryDirectory() as td:
                write_folder(m, td, force=True)
                m2 = read_folder(td)
                data2 = dumps(m2)
            ok2 = data2 == ref
            status = ("identical (v1 -> v2)" if v1 else "identical") if ok1 and ok2 else ("memory ok, folder differs" if ok1 else "DIFFERS")
            if not (ok1 and ok2):
                bad += 1
                status += f" ({_first_diff(raw, data2 if ok1 else dumps(m))})"
        except Exception as ex:                      # noqa: BLE001
            bad += 1
            status = f"ERROR {type(ex).__name__}: {ex}"
        print(f"{Path(f).name}: {status}")
    return 1 if bad else 0


def cmd_payload(a):
    data = read_container(Path(a.file).read_bytes()).payload
    if a.output == "-":
        sys.stdout.buffer.write(data)
    else:
        out = Path(a.output) if a.output else Path(a.file).with_suffix(".payload.bin")
        out.write_bytes(data)
        print(f"wrote {len(data):,} bytes -> {out}", file=sys.stderr)


def cmd_new(a):
    m = SwMap.new(a.name, a.author, a.size, a.height_points, a.paint_resolution, a.floor)
    write_folder(m, a.folder, force=a.force)
    print(f"created empty map folder {a.folder}  (edit it, then: swmap pack {a.folder})")


# ------------------------------------------------------------------------- entry
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="swmap", description="Unpack / pack .swmap custom maps.")
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
    s.add_argument("--level", type=int, default=None, help="zlib level (default: the map's original level, else 6)")
    s.set_defaults(fn=cmd_pack)

    s = sub.add_parser("info", help="summarise a .swmap file or unpacked folder")
    s.add_argument("path"); s.set_defaults(fn=cmd_info)

    s = sub.add_parser("validate", help="check maps against the game's loading rules")
    s.add_argument("paths", nargs="+"); s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("verify", help="check that unpack->pack reproduces the file byte for byte")
    s.add_argument("files", nargs="+"); s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("payload", help="dump the inflated payload as binary (any container version)")
    s.add_argument("file"); s.add_argument("-o", "--output", help="output file, or - for stdout (default: <file>.payload.bin)")
    s.set_defaults(fn=cmd_payload)

    s = sub.add_parser("new", help="create a flat empty map folder to start from")
    s.add_argument("folder"); s.add_argument("--name", default="New map"); s.add_argument("--author", default="")
    s.add_argument("--size", type=float, default=1024.0, help="map size in metres (128..8000)")
    s.add_argument("--height-points", type=int, default=513); s.add_argument("--paint-resolution", type=int, default=512)
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
