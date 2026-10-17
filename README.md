# swmap-tools

Command line (and small library) for **.swmap** custom maps: unpack a map into a folder of ordinary files
(PNG heightmap, PNG paint layers, JSON objects/settings), edit them, and pack them back.

The binary format itself (reading, writing, the game's validation rules, the prop and terrain-layer catalogs) is
**[sw-formats](https://github.com/xmake-studio/sw-formats)** (`swformats.swmap`); this package only maps its `SwMap` to and from
an editable folder. `pack` refuses what swformats' strict reader (= the game's loader) would reject.

Unpack -> pack gives back the original file whenever the same zlib wrote its compressed body; otherwise the content is identical and only
the deflate stream differs (`swmap verify` tells you which).

```
pip install -e .            # pulls swformats from GitHub, plus numpy + pillow

swmap unpack my.swmap -o my_map       # -> folder
#   edit my_map/terrain/heightmap.png, paint_01.png.., objects.json, map.json
swmap pack   my_map -o edited.swmap   # sets the modified time to now; --no-touch keeps map.json's
swmap info   edited.swmap             # summary (also works on a folder)
swmap validate edited.swmap
swmap verify *.swmap                  # unpack->pack reproduces the file byte for byte?
swmap new    blank --size 1024        # start from a flat map folder
```

## Folder layout
| file | content |
|---|---|
| `map.json` | name, author, GUID, size (m), modified time (UTC, 100 ns), environment (distances in metres), paint layer ids |
| `objects.json` | JSON array of objects (props, spawns, capture points, player spawns), positions in **metres** |
| `terrain/heightmap.png` | 16-bit grayscale, top-down view (top = +z, left = -x). `metres = value / 65535 * 500 - 100` (range -100..400 m) |
| `terrain/paint_NN.png` | 8-bit weights of the layer at position NN of `paint_layer_ids` (from 00), same orientation as the heightmap. The **last** layer is implied = `255 - sum(others)` (shown in `_derived/`) |
| `preview.jpg` | list thumbnail; `pack --regenerate-preview` makes a top-down placeholder |
| `_derived/` | helper images (ignored by `pack`) |

The JSON only holds what is stored in the map: heightmap/paint sizes come from the PNGs, the object counts and the
`caps` summary bytes are recomputed on pack. Save the heightmap as **16-bit** grayscale
(GIMP: Image > Precision > 16-bit; Krita/Photoshop: 16-bit grayscale).

### map.json
```json
{"format": "swmap-folder/5", "name": "...", "author": "...", "guid": "...", "size_m": 1024.0,
 "modified": "2026-10-03T06:34:05.6442096Z",
 "environment": {"water": true, "ice": false, "edge_walls": true, "fog": false, "time": 0.85, "weather": "sunny",
                 "shadow_distance_m": 150.0, "fog_mode": "linear", "fog_color": "#a0aab4", "fog_distance_m": 750.0},
 "paint_layer_ids": [2, 4, 5, 9]}
```

### objects.json
Fixed-size data are objects; positions are metres (x, z horizontal, y up, 1/128 m resolution).
```json
{"kind": "prop", "prop_id": 37, "position": {"x": 1, "y": 2, "z": 3},
 "rotation": 90,                                  // degrees (yaw)  OR  {"x": 0, "y": 0.7071, "z": 0, "w": 0.7071}
 "size": 2.0,                                     // uniform scale   OR  "scale": {"x": 1, "y": 2, "z": 1}
 "color": "#ff8800", "floors": 12, "collision": true}   // collision: true | false | left out = game default
{"kind": "spawn", "position": {...}, "rotation": 0, "team": "red|blue|ffa", "vehicle_type": "tank|boat|plane", "reserve": false}
{"kind": "capture_point", "position": {...}, "radius": 30, "letter": "a"}
{"kind": "player_spawn", "position": {...}, "rotation": 0}
```
(comments are for this README only; JSON has none.)

`prop_id` and the paint layer ids are listed in sw-formats' [map catalog](https://github.com/xmake-studio/sw-formats/blob/main/docs/map-catalog.md) (`swmap info` and `swmap validate` use it too).

**Colours** are `#rrggbb` (opaque) or `#rrggbbaa`; `#rrggbbaa` is written only when alpha is not 255.
The container version is never stored in the folder: swformats picks it the way the game does - version 2 if any prop colour
has alpha < 255, otherwise version 1 (the game rejects a file whose version doesn't match). Removing the last translucent colour
therefore turns the file back into version 1 by itself. A file stored with the wrong version is rejected by swformats' reader (as it is by the game).

A numeric `rotation` is a yaw in degrees, stored in steps of 360/65536.
A quaternion (models only) is stored as signed 16-bit integers divided by 32767 and normalised by the game when it loads the map;
`pack` rounds your floats to that grid (length must be 0.9..1.1). Capture points cannot be rotated. The container's `caps` bytes
are recomputed on every pack. (`"team": "deathmatch"`, `"kind": "model"` and `"model_id"` are still accepted as aliases.)

`weather` is `clear | sunny | cloudy | rain` (0-3) and `fog_mode` is `linear | exponential | exp_squared` (1-3); numbers are
accepted too. A value the game does not define is kept as a number and `validate` warns that it gets clamped.

Optional `map.json` keys written only when needed to keep `pack` byte-identical: `"deflate_level"` (the game has written zlib
level 6 and 9; default 9, what swformats writes) and `"preview": false` (the original map has no preview; delete the key or use
`pack --regenerate-preview` to get a generated one).

## Library
The map model is swformats' (`swformats.swmap.SwMap`, positions in world units = 2 per metre); see its
[docs](https://github.com/xmake-studio/sw-formats/blob/main/docs/swmap.md). This package adds the folder format and a few helpers:
```python
import swmap
from swformats import swmap as sw

mf = swmap.load("my.swmap")                       # MapFile(map=SwMap, level=<zlib level of the original body>)
m = mf.map                                        # m.terrain.heights, m.objects, m.env ...
m.objects.append(sw.MapObject(sw.PROP, prop_id=4, position=(20.0, 15.5, -10.0)))
print([str(i) for i in swmap.validate(m)])        # errors = the game rejects it, warnings = clamped / dropped on write
mf.save("out.swmap")                              # or mf.dumps() -> bytes
swmap.write_folder(mf, "folder"); mf = swmap.read_folder("folder")
```
`swmap.terrain` has numpy views (`heights_array`, `splat_array`) and metre conversions of the height samples.

## Changes from 0.3
* All binary parsing and writing now comes from swformats; `binio`, `container`, `payload`, `props`, `caps`, `model` and `FORMAT.md` are gone
  (the format is documented in sw-formats' `docs/swmap.md`). The `swmap payload` command went with them; use `python -m swformats json FILE`.
* **Paint layers**: the file stores the *first* `layerCount - 1` layers and the *last* one is implied. 0.3 treated the first as implied, so
  `paint_NN.png` was attached to the wrong layer id. Folders are now `swmap-folder/5` with `paint_00.png` = `paint_layer_ids[0]`; `/4` folders
  still pack (their files are renamed on the fly) but their numbering was misleading.
* Heights are `value / 65535` over the range, as in the spec (0.3 divided by 65536; the PNG values themselves are unchanged).
* `model` became `prop` (`prop_id`), as in swformats; the old names are still read. `new` creates the layers swformats uses by default.

## Format
Specified in sw-formats: [docs/swmap.md](https://github.com/xmake-studio/sw-formats/blob/main/docs/swmap.md) (verified against the game's
source and its sample maps). Heights and paint use a clamped-gradient predictor + zigzag residuals, stored as byte planes, deflated.

## Tests
`pytest -q` (add `SWMAP_SAMPLES=/folder/with/real/maps` to also round-trip real files, e.g. sw-formats' `samples/`).

## Not known / not checked
* Whether a given zlib build reproduces the game's deflate stream byte for byte (`swmap verify` reports it per file).
