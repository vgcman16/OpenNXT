# Protocol Size Diff Report: 919 -> 946

Generated from packet size tables and existing named packet maps.
This is a shortlist generator, not a final authority. All names still need behavioral validation.

## Summary

- Source named server packets: `194`
- Source named client packets: `3`
- Target server packet sizes: `217`
- Target client packet sizes: `130`
- High-confidence server size-only transfers: `3`

## High-Confidence Server Candidates

| Name | 919 Opcode | Size | 946 Candidates | Shape File | Notes |
| --- | ---: | ---: | --- | --- | --- |
| IF_OPENSUB | 40 | 23 | 38 | yes | unique size on both sides |
| MAP_PROJANIM | 50 | 20 | 24 | no | unique size on both sides |
| IF_OPENSUB_ACTIVE_LOC | 71 | 32 | 21 | no | unique size on both sides |

## Medium-Confidence Server Candidates

| Name | 919 Opcode | Size | 946 Candidates | Shape File | Notes |
| --- | ---: | ---: | --- | --- | --- |
| MAP_ANIM | 23 | 11 | 117, 122 | no | 919 same-size names: MAP_ANIM, MIDI_SONG_LOCATION |
| IF_OPENTOP | 38 | 19 | 94, 126 | yes | 919 same-size names: IF_OPENTOP, NPC_ANIM_SPECIFIC |
| UPDATE_STOCKMARKET_SLOT | 87 | 21 | 214 | no | 919 same-size names: MAP_PROJANIM_HALFSQ, UPDATE_STOCKMARKET_SLOT |
| UPDATE_UID192 | 90 | 28 | 0, 159 | no | - |
| NPC_ANIM_SPECIFIC | 94 | 19 | 94, 126 | no | 919 same-size names: IF_OPENTOP, NPC_ANIM_SPECIFIC |
| IF_OPENSUB_ACTIVE_OBJ | 101 | 29 | 7, 147 | no | - |
| MIDI_SONG_LOCATION | 117 | 11 | 117, 122 | no | 919 same-size names: MAP_ANIM, MIDI_SONG_LOCATION |
| MAP_PROJANIM_HALFSQ | 193 | 21 | 214 | no | 919 same-size names: MAP_PROJANIM_HALFSQ, UPDATE_STOCKMARKET_SLOT |

## Field-Backed Server Shortlist

| Name | 919 Opcode | Size | 946 Candidates | Shape File | Notes |
| --- | ---: | ---: | --- | --- | --- |
| IF_SETEVENTS | 16 | 12 | 59, 91, 158 | yes | 919 same-size names: IF_SETEVENTS, SPOTANIM_SPECIFIC, VORBIS_SOUND_GROUP |
| IF_OPENTOP | 38 | 19 | 94, 126 | yes | 919 same-size names: IF_OPENTOP, NPC_ANIM_SPECIFIC |
| IF_OPENSUB | 40 | 23 | 38 | yes | unique size on both sides |

## Small Server Size Buckets

| Size | 919 Named Packets | 946 Opcodes |
| ---: | --- | --- |
| 7 | LOC_ANIM, OBJ_COUNT, OBJ_REVEAL | 3, 78, 127 |
| 9 | IF_SETRETEX, NPC_HEADICON_SPECIFIC, IF_SETRECOL | 137, 165, 202 |
| 11 | MAP_ANIM, MIDI_SONG_LOCATION | 117, 122 |
| 12 | SPOTANIM_SPECIFIC, IF_SETEVENTS, VORBIS_SOUND_GROUP | 59, 91, 158 |
| 14 | HINT_ARROW | 47, 176, 194 |
| 19 | IF_OPENTOP, NPC_ANIM_SPECIFIC | 94, 126 |
| 21 | UPDATE_STOCKMARKET_SLOT, MAP_PROJANIM_HALFSQ | 214 |
| 25 | IF_OPENSUB_ACTIVE_PLAYER, PROJANIM_SPECIFIC, IF_OPENSUB_ACTIVE_NPC | 54, 67, 116 |
| 28 | UPDATE_UID192 | 0, 159 |
| 29 | IF_OPENSUB_ACTIVE_OBJ | 7, 147 |

## Known Client Packet Candidates

| Name | 919 Opcode | Size | 946 Candidates | Shape File | Notes |
| --- | ---: | ---: | --- | --- | --- |
| CLIENT_CHEAT | 72 | -1 | 4, 17, 24, 28, 29, 32, 39, 48, 56, 62, 67, 71, 78, 81, 84, 86, 93, 94, 98, 104, 107, 109, 112, 116, 119, 121, 126, 127 | yes | - |
| NO_TIMEOUT | 93 | 0 | 15, 21, 34, 41, 80, 87 | no | - |
| WORLDLIST_FETCH | 108 | 4 | 8, 11, 50, 51, 65, 66, 70, 95, 100, 110, 113 | yes | - |

## 946 Client Zero-Size Shortlist

Size `0` client packets are strong `NO_TIMEOUT` / keepalive / tick-loop candidates:

- `15`, `21`, `34`, `41`, `80`, `87`

