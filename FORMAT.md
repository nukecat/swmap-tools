# .swmap format (reverse engineered; verified against GameAssembly.dll + 12 maps)

## Container (little endian)
`"SWMP"` | u16 version(1) | 16B GUID (.NET Guid bytes = file name) | string name | string author (BinaryWriter strings)
| i64 .NET ticks | f32 sizeMeters | 11B caps | u32 jpegLen | JPEG 640x320 | u32 payloadLen | raw DEFLATE payload (to EOF)

caps (CustomMapCaps.Compute/ToBytes) - redundant summary of the props, every counter saturates at 255:
  bytes 0-8  spawn points, index = min(team,2)*3 + slot  (team 0 deathmatch/1 red/2 blue; spawnType 1->slot 0, 2->1, 4->2)
  byte 9     capture points      byte 10  player spawns       (model props are not counted)

## Payload (CustomMapSerializer.ReadBody)
env flags u8 (b0 water, b1 ice, b2 edge walls, b3 fog) | f32 time | u8 weather | u16 shadowDistance (units)
| u8 fogMode | RGB | u16 fogDistance (units) | heightmap | paint | varuint numProps (<=20000) | props
Units = 0.5 m (shadow 300 -> 150 m, fog 1500 -> 750 m).

### Heightmap  (ReadPredicted16 / Predict16)
u16 points; lo plane, hi plane (points^2 bytes each); v = lo | hi<<8; residual = (v>>1) ^ -(v&1);
pred = 0 (corner) | left (row 0) | up (col 0) | clamp(left+up-upleft, 0, 65535);
height = (pred + residual) & 0xFFFF; metres = height*500/65536 - 100.

### Paint (ReadSplat / Predict8)
u16 resolution; u8 layerCount; u16 layerIds[layerCount]; (layerCount-1) planes of resolution^2 bytes:
value = (clamp(left+up-upleft,0,255) + raw) & 0xFF. Last layer = 255 - sum(others).

### Props (ReadObject)
u8 kind (0 model, 1 spawn, 2 capture point, 3 player spawn) | u8 flags | [varuint modelId if model]
| 3x zigzag varint position (1/64 unit = 1/128 m; x, y up, z) | rotation: u16 yaw (flag bit0: *360/65536 deg) else 4x s16 quaternion /32767
| bit1: one f4 uniform scale (capture point: radius) / bit2: 3x f4 scale (0.05..5000)
| model: bit3 RGB, bit4 u8 floors (1..40), collision: bit5 On, bit6 Off, neither = Default
| spawn: u8 team (0 DM,1 red,2 blue), u8 (low 7 bits type 1/2/4, bit7 reserve) | capture point: u8 letter (a-d)
Rules: kind!=0 -> only bits 0-2, bit0 required; bit1/bit2 exclusive; bit5/bit6 exclusive; capture point: no bit2, yaw 0.
