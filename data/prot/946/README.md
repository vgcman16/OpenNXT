# Build 946 Protocol Workspace

This directory is the in-repo workspace for RS3 build `946`.

## Status

- Live RS3 client build confirmed: `946`
- Ghidra import of the `win64` client succeeded
- The legacy `RS3NXTRefactorer` script does not yet complete on build `946`
- `serverProtSizes.toml` is now extracted from the live client
- `clientProtSizes.toml` is now extracted from the live client
- `serverProtNames.toml` now contains the first parser-confirmed server anchors
  and the first horizontally expanded UI-family names
- `clientProtNames.toml` now contains the first parser-confirmed client anchor
- `sizeDiffReport.md` now compares `919` vs `946` size tables to produce the first naming shortlist
- The 2026 client registers `217` contiguous server packets through a new direct registrar at `FUN_140301280`
- The 2026 client registers `130` contiguous client packets through a direct registrar at `FUN_140301100`
- Runtime handler binding is now traced through `descriptor + 0x48` and into the real parser entrypoints

Current script breakpoints observed during headless runs:

- The legacy packet naming walk does not yet match the new `946` packet object layout
- The legacy `SendPing` anchor is no longer required for packet size extraction, but packet naming still needs new heuristics
- Build `946` is still not bootable in OpenNXT; the current name files are partial anchor sets only

## Inputs

- Client binary:
  `data/clients/946/win64/original/rs2client.exe`

## Goal

Populate the following once the Ghidra heuristics are updated for build `946`:

- `clientProtNames.toml`
- `serverProtNames.toml`
- `clientProt/*.txt`
- `serverProt/*.txt`

## Notes

The current repository can download and patch the live `946` client and cache. The server remains pinned to
supported protocol data until packet names and handler mappings are recovered for build `946`.

Current parser-confirmed anchors:

- Server `3` -> `OBJ_REVEAL`
- Server `8` -> `IF_SETCOLOUR`
- Server `21` -> `IF_OPENSUB_ACTIVE_LOC`
- Server `24` -> `MAP_PROJANIM`
- Server `38` -> `IF_OPENSUB`
- Server `50` -> `IF_CLOSESUB`
- Server `57` -> `IF_SETTEXT`
- Server `59` -> `IF_SETEVENTS`
- Server `64` -> `LOC_DEL`
- Server `77` -> `IF_SETPLAYERHEAD`
- Server `78` -> `LOC_ADD_CHANGE`
- Server `87` -> `OBJ_ADD`
- Server `98` -> `OBJ_DEL`
- Server `106` -> `IF_SETPLAYERMODEL_SELF`
- Server `108` -> `IF_SETSCROLLPOS`
- Server `122` -> `MAP_ANIM`
- Server `127` -> `OBJ_COUNT`
- Server `132` -> `LOC_PREFETCH`
- Server `214` -> `MAP_PROJANIM_HALFSQ`
- Client `80` -> `NO_TIMEOUT`

Current local handler path used for confirmation:

- `opcode -> descriptor -> descriptor + 0x48 -> handler vtable -> dispatch thunk -> parser`
- `21` parser: `FUN_1400fbf80`
- `24` parser: `FUN_140113af0`
- `38` parser: `FUN_1400fb9d0`
- `57` parser: `FUN_140108fd0`
- `59` parser: `FUN_140109290`
- `64` parser: `FUN_1401132f0`
- `50` parser: `FUN_1400fc630`
- `77` parser: `FUN_140108360`
- `78` parser: `FUN_140113830`
- `87` parser: `FUN_14013f820`
- `98` parser: `FUN_14013f760`
- `106` parser: `FUN_1401089c0`
- `8` parser: `FUN_140107d70`
- `108` parser: `FUN_140109650`
- `122` parser: `FUN_140114110`
- `127` parser: `FUN_1401143f0`
- `132` parser: `FUN_1401149f0`
- `214` parser: `FUN_140113e10`
- `3` parser: `FUN_14013f5f0`

Current UI-family notes from the `FUN_1400fadb0` constructor cluster:

- `57` is a string reader followed by widget-manager update calls, which matches
  `IF_SETTEXT`
- `59` reads `parent int + mask int + two slot shorts`, which matches
  `IF_SETEVENTS`
- `50` reads a single interface key, looks it up in the interface manager hash
  table, and unlinks/releases the matched node, which matches `IF_CLOSESUB`
- `8` reads `parent int + packed 15-bit colour` and expands it into RGB-like
  components before the widget update path, which matches `IF_SETCOLOUR`
- `77` and `106` are twin local-player widget-model updaters that both read only
  a parent interface id and source the appearance/model value from the cached
  local-player object at `client + 0x19f68`
- `77` writes widget model type `3`, which matches the legacy
  `IF_SETPLAYERHEAD` path
- `106` writes widget model type `5`, which matches the legacy
  `IF_SETPLAYERMODEL_SELF` path
- `108` reads `parent int + short` and routes through the dedicated interface
  manager path, which matches `IF_SETSCROLLPOS`
- `137` and `202` remain the leading `IF_SETRETEX` / `IF_SETRECOL` candidates
  and are now narrowed to a property-id split instead of a generic pair:
  `137` decompiles to `FUN_1400cc6f0` with helper type `0x11`, while `202`
  decompiles to `FUN_1400cc630` with helper type `0x12`
- both decode `parent int + slot byte + short pair` shapes, but `137` applies a
  `byte128`-style bias to one of the short-like values before the helper call,
  while `202` passes the corresponding short through directly
- The 4-byte UI-family packets are not yet committed as names; at least one of
  the remaining unresolved 4-byte packets sits outside the widget close/self-model
  cluster documented above

Current world-family notes from the `FUN_1401112c0` constructor cluster:

- `87` reads `coord byte + short + short` and feeds the same ground-item helper
  later used by the reveal/count parsers, which matches `OBJ_ADD`
- `98` reads `coord byte + short` and calls the tile-ground-item removal helper,
  which matches `OBJ_DEL`
- `3` reads `short + short + coord byte + target-player short`, gates on the
  local-player id, and then feeds the same ground-item helper as `87`, which
  matches `OBJ_REVEAL`
- `127` reads `coord byte + item id short + old count short + new count short`
  and mutates a matching ground-item stack entry in place, which matches
  `OBJ_COUNT`
- `64` reads a packed local coordinate plus a loc type/orientation byte and
  pushes a removal-shaped scene update through the loc manager path, which
  matches `LOC_DEL`
- `78` reads a 4-byte loc id plus packed type/orientation and local tile data,
  then enqueues a loc scene update object, which matches `LOC_ADD_CHANGE`
- `122` reads a local tile, a resource id, and angle/height-style fields before
  spawning a scene effect through the world renderer, which matches `MAP_ANIM`
- `214` reads two packed 3-byte world points plus projectile/timing fields and
  routes them into the projectile scene path, which matches
  `MAP_PROJANIM_HALFSQ`
- `132` reads a loc/object id plus shape byte, loads the object definition, and
  preloads the matching model resources for that shape; despite the `946`
  fixed-size form differing from the old `919` size, the behavior matches
  `LOC_PREFETCH`

Regenerate the size-based shortlist with:

`python scripts/protocol_size_diff.py --source-build 919 --target-build 946 --out data/prot/946/sizeDiffReport.md`
