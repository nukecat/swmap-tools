# swmap-tools

Library + command line for **.swmap** custom maps: unpack a map into a folder of ordinary files
(PNG heightmap, PNG paint layers, JSON objects/settings), edit them, and pack them back.

Round trips are **byte-identical** on every map I could test (unpack -> pack gives the original file; version 1 maps are upgraded to version 2 instead),
and `pack` refuses things the game's loader would reject.

```
pip install -e .            # needs numpy + pillow

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
| `objects.json` | JSON array of props, positions in **metres** |
| `terrain/heightmap.png` | 16-bit grayscale, top-down view (top = +z, left = -x). `metres = value * 500 / 65536 - 100` (range -100..400 m) |
| `terrain/paint_NN.png` | 8-bit weights of layer NN, same orientation as the heightmap. Layer 00 (base) is implied = `255 - sum(others)` |
| `preview.jpg` | list thumbnail; `pack --regenerate-preview` makes a top-down placeholder |
| `_derived/` | helper images (ignored by `pack`) |

The JSON only holds what is stored in the map: heightmap/paint sizes come from the PNGs, prop counts and the
`caps` summary bytes are recomputed on pack. Save the heightmap as **16-bit** grayscale
(GIMP: Image > Precision > 16-bit; Krita/Photoshop: 16-bit grayscale).

### map.json
```json
{"format": "swmap-folder/4", "name": "...", "author": "...", "guid": "...", "size_m": 1024.0,
 "modified": "2026-10-03T06:34:05.6442096Z",
 "environment": {"water": true, "ice": false, "edge_walls": true, "fog": false, "time": 0.85, "weather": "sunny",
                 "shadow_distance_m": 150.0, "fog_mode": "linear", "fog_color": "#a0aab4", "fog_distance_m": 750.0},
 "paint_layer_ids": [2, 4, 5, 9]}
```

### objects.json
Fixed-size data are objects; positions are metres (x, z horizontal, y up, 1/128 m resolution).
```json
{"kind": "model", "model_id": 37, "position": {"x": 1, "y": 2, "z": 3},
 "rotation": 90,                                  // degrees (yaw)  OR  {"x": 0, "y": 0.7071, "z": 0, "w": 0.7071}
 "size": 2.0,                                     // uniform scale   OR  "scale": {"x": 1, "y": 2, "z": 1}
 "color": "#ff8800", "floors": 12, "collision": true}   // collision: true | false | left out = game default
{"kind": "spawn", "position": {...}, "rotation": 0, "team": "red|blue|ffa", "vehicle_type": "tank|boat|plane", "reserve": false}
{"kind": "capture_point", "position": {...}, "radius": 30, "letter": "a"}
{"kind": "player_spawn", "position": {...}, "rotation": 0}
```
(comments are for this README only; JSON has none.)

**Colours** are `#rrggbb` (opaque) or `#rrggbbaa`; a map is written with `#rrggbbaa` only when alpha is not 255.
`pack` always writes container **version 2** (RGBA, 4 bytes). Version 1 maps can still be read (their colours load with alpha 255)
and are saved as version 2, so unpack -> pack of a v1 file upgrades it instead of reproducing it byte for byte.

A numeric `rotation` is a yaw in degrees, stored in steps of 360/65536.
A quaternion (models only) is stored as signed 16-bit integers divided by 32767 and normalised by the game when it loads the map;
`pack` rounds your floats to that grid (length must be 0.9..1.1). Capture points cannot be rotated. The container's `caps` bytes
are recomputed on every pack. (`"team": "deathmatch"` is still accepted as an alias of `ffa`.)

`weather` is `clear | sunny | cloudy | rain` (0-3) and `fog_mode` is `linear | exponential | exp_squared` (1-3); numbers are
accepted too. A value the game does not define is kept as a number and `validate` warns about it.

Optional `map.json` keys written only when needed to keep `pack` byte-identical: `"deflate_level"` (the game has written zlib
level 6 and 9; default 6) and `"preview": false` (the original map has no preview; delete the key or use
`pack --regenerate-preview` to get a generated one).

## Library
```python
import swmap
m = swmap.load("my.swmap")                       # SwMap(header, environment, terrain, props, preview_jpg)
m.terrain.heights                                 # uint16 (N, N) numpy array
m.props.append(swmap.Prop(swmap.Kind.MODEL, swmap.Vec3(10, 5, 20), model_id=1, rotation=0.0))
print([str(i) for i in m.validate()])
m.save("out.swmap")                               # or swmap.dumps(m) -> bytes
swmap.write_folder(m, "folder"); m = swmap.read_folder("folder")
```

## Format
See `FORMAT.md` (verified against the game's `CustomMapSerializer` and 12 sample maps).
Heights and paint use a clamped-gradient predictor + zigzag residuals, stored as byte planes, deflated with zlib level 6.

## Tests
`pytest -q` (add `SWMAP_SAMPLES=/folder/with/real/maps` for the byte-identical checks).

## Not known / not checked
* Which `model_id` is which model, what the `layer_ids` values mean in-game.
* Position limits relative to map size are only warned about (the game's exact bound is not confirmed).
* Limits on name/author length and on compressed file size, if any, are not enforced here.
