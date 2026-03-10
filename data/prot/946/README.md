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
- Server `28` -> `NPC_INFO`
- Server `38` -> `IF_OPENSUB`
- Server `42` -> `PLAYER_INFO`
- Server `43` -> `UPDATE_ZONE_PARTIAL_ENCLOSED`
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
- Server `129` -> `UPDATE_STAT`
- Server `131` -> `NO_TIMEOUT`
- Server `132` -> `LOC_PREFETCH`
- Server `134` -> `RESET_CLIENT_VARCACHE`
- Server `214` -> `MAP_PROJANIM_HALFSQ`
- Client `80` -> `NO_TIMEOUT`
- Client `4` -> `MESSAGE_PUBLIC`
- Client `6` -> `OPPLAYER5`
- Client `9` -> `OPNPC1`
- Client `14` -> `OPPLAYER7`
- Client `16` -> `OPNPCT`
- Client `19` -> `OPNPC2`
- Client `20` -> `OPPLAYER1`
- Client `23` -> `OPOBJ3`
- Client `25` -> `OPOBJ2`
- Client `26` -> `OPOBJ1`
- Client `30` -> `OPPLAYER10`
- Client `34` -> `MAP_BUILD_COMPLETE`
- Client `35` -> `OPNPC6`
- Client `36` -> `OPNPC5`
- Client `37` -> `OPOBJT`
- Client `38` -> `OPLOC1`
- Client `40` -> `OPLOC3`
- Client `43` -> `OPLOC6`
- Client `46` -> `OPPLAYER2`
- Client `49` -> `MESSAGE_PRIVATE`
- Client `56` -> `CLIENT_CHEAT`
- Client `58` -> `OPLOCT`
- Client `59` -> `OPPLAYER8`
- Client `60` -> `OPPLAYER6`
- Client `68` -> `OPLOC2`
- Client `69` -> `OPNPC4`
- Client `77` -> `OPOBJ6`
- Client `90` -> `OPOBJ4`
- Client `91` -> `OPPLAYER9`
- Client `96` -> `OPPLAYER4`
- Client `101` -> `OPLOC4`
- Client `103` -> `OPOBJ5`
- Client `105` -> `OPPLAYERT`
- Client `111` -> `OPLOC5`
- Client `115` -> `OPPLAYER3`
- Client `125` -> `OPNPC3`
- Client `87` -> `RESUME_PAUSEBUTTON`
- Client `129` -> `RESUME_P_COUNTDIALOG`

Current local handler path used for confirmation:

- `opcode -> descriptor -> descriptor + 0x48 -> handler vtable -> dispatch thunk -> parser`
- `21` parser: `FUN_1400fbf80`
- `24` parser: `FUN_140113af0`
- `28` parser: `FUN_140106920 -> FUN_14011ebb0`
- `38` parser: `FUN_1400fb9d0`
- `42` parser: `FUN_140106360 -> FUN_140124e30`
- `43` parser: `FUN_14013fb30`
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
- `129` parser: `FUN_1401412d0`
- `131` parser: `FUN_140106b30`
- `132` parser: `FUN_1401149f0`
- `134` parser: `FUN_1400fe780`
- `214` parser: `FUN_140113e10`
- `3` parser: `FUN_14013f5f0`

Current login-init notes:

- `129` is the strongest `UPDATE_STAT` match. Its parser writes through the
  per-skill table at `client + 0x19810` and consumes a 6-byte shape that no
  longer matches the old `919` field order, so `946` now has an explicit
  `serverProt/UPDATE_STAT.txt`.
- `72` (`FUN_140140be0`) is the current `VARP_SMALL` mapping. It reads
  `id ushort`, then a raw single-byte value, and applies the pair through the
  client var manager at `+0x19f78`.
- `51` (`FUN_140140b10`) is the current `VARP_LARGE` mapping. It reads a
  big-endian 4-byte value followed by a big-endian `ushort` id before applying
  the result through the same var manager.
- `128` (`FUN_1400f8610`) is the current `CLIENT_SETVARC_SMALL` mapping. It
  consumes `id ushortle`, then a raw byte value.
- `124` (`FUN_140140dd0`) is the current `CLIENT_SETVARC_LARGE` mapping. It
  consumes `id ushortle`, then a `V1`-ordered integer payload, and forwards the
  decoded pair into the client varc manager.
- `131` is the strongest `NO_TIMEOUT` match. It is zero-byte and only bumps a
  30-second deadline on the client session object.
- `134` is the current `RESET_CLIENT_VARCACHE` login-reset mapping. It is
  zero-byte and performs a broad client-state reset across world, interface,
  and cached session state before the next init wave.

Current client sender notes from runtime packet refs:

- `FUN_140100220` is not involved in outbound input mapping; the useful pivot on
  the client side is the `ClientProtOP_*` descriptor block at
  `140ebf770..140ebff80`, which is now labeled in the local Ghidra workspace
- `80` remains the confirmed keepalive packet: `FUN_1400ea070` gates it on a
  `0x4e20` (20 second) timer before emitting the zero-byte descriptor
- `FUN_140099710` is the strongest public-chat sender:
  it pops one script string, derives two extra single-byte values through
  `FUN_140097a10`, writes a placeholder length byte, and then compresses the
  chat payload through `FUN_1403d62a0`; that shape matches
  `4 -> MESSAGE_PUBLIC`
- `FUN_140099a90` is the matching private-message sender:
  it pops two strings, writes the first raw through `FUN_1400ac540`, then
  compresses the second through `FUN_1403d62a0`; that shape matches
  `49 -> MESSAGE_PRIVATE`
- `FUN_140099e30` is still not named:
  it pops two strings plus two small control values, writes one raw string,
  appends a byte/bool pair, and then emits a second bounded raw string, which
  looks more like a structured text submission than a clean `CLIENT_CHEAT`
- `FUN_14008d5e0` is the strongest raw command sender:
  it pops exactly one string, emits a single length-like byte via
  `FUN_1400aa740`, and then writes the string through `FUN_1400ac540`
  without touching the Huffman compressor; with descriptor `DAT_140ebfaf0`
  this resolves to `56 -> CLIENT_CHEAT`
- the neighboring raw-string wrappers help calibrate that interpretation:
  `FUN_14008d840` uses descriptor `DAT_140ebf7e0` (`7`) and writes two raw
  strings with a combined short length, while `FUN_14008db20` uses
  `DAT_140ebf810` (`10`) and writes one raw string plus a trailing packed
  flag byte, so `56` is the clean single-command outlier in that family
- the late colon-parser funnels `FUN_140646bf0` and `FUN_140641090` were ruled
  out during this pass; both feed URL/connection setup through
  `FUN_140643ea0`, `FUN_1406466d0`, and `FUN_140656d10` rather than outbound
  gameplay/chat packets
- `FUN_1400e6bc0` is the resolved player-option sender family:
  it first resolves a target through `FUN_140124550`, and `FUN_140124550`
  explicitly walks the active player list at `client + 0x4038 / 0x4040`
  before returning the matched player object
- that sender writes only a modifier byte plus the target player index from
  `target + 0x88`, which matches the fixed 3-byte `OPPLAYER*` packet family
- the `param_2` switch in `FUN_1400e6bc0` maps player option indices directly
  onto concrete `946` opcodes:
  `20 -> OPPLAYER1`, `46 -> OPPLAYER2`, `115 -> OPPLAYER3`, `96 -> OPPLAYER4`,
  `6 -> OPPLAYER5`, `60 -> OPPLAYER6`, `14 -> OPPLAYER7`, `59 -> OPPLAYER8`,
  `91 -> OPPLAYER9`, `30 -> OPPLAYER10`
- `FUN_1400e6ea0` is the player-targeted selected-cursor sender:
  it writes selected component data from `client + 0x198c0` plus a 2-byte
  target index, then resolves the target through the active-player holder at
  `*(param_1 + 0x19910) + 0x10` and routes toward that player's world position
- the raw entry stubs at `14010cdc0` and `14010ce10`, plus the higher-level
  caller `FUN_1401f9710`, all feed `FUN_1400e6ea0`, so `105` is `OPPLAYERT`
- `FUN_1400e5d10` is the NPC-targeted mirror family:
  it emits one 11-byte selected-component variant and six 3-byte base variants,
  all using a short target index from `target + 0x48` and world-position routing
  through `FUN_1400e37e0` / `FUN_1400e38f0`
- the raw stub block around `14010d3a0..14010d587` is laid out as
  `T,6,5,4,3,2,1`, while the same vtables are registered in `FUN_1400e39d0`
  in calibrated `1,2,3,4,5,6,T` order, matching the already-resolved
  `OPOBJ` and `OPLOC` families
- that resolves the NPC interaction family as:
  `9 -> OPNPC1`, `19 -> OPNPC2`, `125 -> OPNPC3`, `69 -> OPNPC4`,
  `36 -> OPNPC5`, `35 -> OPNPC6`, `16 -> OPNPCT`
- `FUN_1401bbf60` resolves ground-item definitions through `DAT_140c9b578`,
  which is now confirmed as the item-definition manager by the widget item-model
  parsers `FUN_1400fcbe0` and `FUN_1400fce90`
- its 1-based option switch maps onto the six fixed-size 7-byte ground-item
  action packets:
  `26 -> OPOBJ1`, `25 -> OPOBJ2`, `23 -> OPOBJ3`, `90 -> OPOBJ4`,
  `103 -> OPOBJ5`, `77 -> OPOBJ6`
- the raw stub block at `14010d170..14010d35e` wires those same descriptors,
  plus `ClientProtOP_37`, into `FUN_1400e6190`
- the special `param_2 == &DAT_140ebf9c0` branch in `FUN_1400e6190` appends
  selected component data from `client + 0x198c0` to the same ground-item
  target shape, so `37` is `OPOBJT`
- `FUN_1400e5780` is the matching world-object interaction sender family:
  the fixed-size non-target variants write local `x/y`, the run modifier, and a
  4-byte target id from `target + 0x48`, which is the loc/object-shaped target
  payload rather than the 3-byte player/NPC interaction shape
- its special `param_2 == &DAT_140ebfb10` branch appends selected component
  data from `client + 0x198c0`, and `ClientProtOP_58` is the only 17-byte
  descriptor in the family, so `58` is `OPLOCT`
- the action-class registrar `FUN_1400e39d0` wires the already-resolved
  `OPOBJ` family in strict `1,2,3,4,5,6,T` order, and the `FUN_1400e5780`
  vtable family is registered in the same seven-slot pattern:
  `140b8dc88`, `140b8dc58`, `140b8db68`, `140b8db38`, `140b8dbc8`,
  `140b8db98`, `140b8daa8`
- the raw stubs then pair those vtables with concrete `946` descriptors in the
  same order, which resolves the loc interaction family as:
  `38 -> OPLOC1`, `68 -> OPLOC2`, `40 -> OPLOC3`, `101 -> OPLOC4`,
  `111 -> OPLOC5`, `43 -> OPLOC6`, `58 -> OPLOCT`
- `FUN_1400e4cd0` is the first confirmed click-to-move sender pair:
  it reads destination tiles from `target + 0x4c/+0x50`, writes the shared
  `x + run + y` movement core, and then branches on `target + 0x48`
- when that mode field is `0`, it emits fixed-size `ClientProtOP_33` with only
  the 5-byte destination payload, which matches the plain scene-click walk path
- when that mode field is `1`, it emits fixed-size `ClientProtOP_92` with the
  same destination payload plus an extra 13-byte attachment block containing
  click-context constants and local-player tile data
- the structural split is consistent with `33 -> WALK` and
  `92 -> MINIMAP_WALK`; those names are still based on packet shape because the
  legacy label walk no longer survives in the `946` client
- `FUN_140169660` is the strongest widget-targeted sender:
  it only runs when a selected component is active at `client + 0x198c0`,
  writes the selected component fields from `+0x28c/+0x290/+0x294`, appends
  the target widget/component key from `target + 0x4c/+0x50`, and then writes
  a final target-derived short via `(**(code **)(*plVar10 + 0xb0))(plVar10)`;
  with descriptor `DAT_140ebff10` that resolves to `122 -> IF_BUTTONT`
- `FUN_1401a3600` is the plain widget menu-action router:
  it carries the clicked option as `param_5`, gates it through the widget
  clickmask via `FUN_14019b6b0`, and for `param_5 - 1 < 10` dispatches through
  the 1-based descriptor table at `DAT_140b92f18`
- `DAT_140b92f18` resolves the numbered widget button family directly:
  `1 -> 97`, `2 -> 118`, `3 -> 54`, `4 -> 128`, `5 -> 18`,
  `6 -> 64`, `7 -> 61`, `8 -> 124`, `9 -> 63`, `10 -> 47`
- that table is sufficient to name the base widget packets as:
  `97 -> IF_BUTTON1`, `118 -> IF_BUTTON2`, `54 -> IF_BUTTON3`,
  `128 -> IF_BUTTON4`, `18 -> IF_BUTTON5`, `64 -> IF_BUTTON6`,
  `61 -> IF_BUTTON7`, `124 -> IF_BUTTON8`, `63 -> IF_BUTTON9`,
  `47 -> IF_BUTTON10`
- `FUN_1401a60d0` is the drag/drop-style widget sender reached from the drag
  manager `FUN_1401a4c60`:
  it serializes two widget/component objects stored at `param_1 + 0x2b8/0x2e8`,
  writing source and destination interface hashes, slot-like shorts, and the
  per-component `0xb0` values through descriptor `DAT_140ebf830`;
  that payload shape matches `12 -> IF_BUTTOND`
- `FUN_1401693a0 -> FUN_1401a5e00` remains intentionally unnamed:
  it stores a resolved widget/component into the selected-component state at
  `client + 0x198c0 + 0x178/0x180`, then emits a 6-byte packet through
  `DAT_140ebfec0` containing only the widget hash and a slot-like short
  (`117` in the current size table)
- that `117` packet is clearly the self/select-side counterpart to
  `IF_BUTTONT`, but the exact legacy label or option index is not yet proven,
  so it is left out of `clientProtNames.toml` for now
- `FUN_1401fda40` is the numeric prompt-resume sender:
  it pops a script-stack string from `param_2 + 0x10a8`, parses it as base-10
  through `FUN_1407e3b74(..., 10)`, and writes the resulting integer through
  descriptor `DAT_140ebff80`; that resolves to `129 -> RESUME_P_COUNTDIALOG`
- `FUN_1401fe5e0` is the zero-byte prompt continue sender:
  it emits descriptor `DAT_140ebfce0` without appending any payload data,
  using the same UI/script connection context as the prompt-resume helpers;
  that resolves to `87 -> RESUME_PAUSEBUTTON`
- `FUN_1401fd5b0`, `FUN_1401fdf30`, and `FUN_1401fe390` are the current
  unresolved raw-string prompt trio:
  all three pop a script-stack string, emit a single length-like byte via
  `FUN_1400aa740`, and then write the raw text through `FUN_1400ac540`
  without Huffman compression
- those three helpers resolve to descriptors `67`, `93`, and `24`
  respectively, so they are strong candidates for the remaining
  string/name-style resume packets, but they are still left unnamed until the
  clientscript hook context cleanly separates their prompt semantics
- `FUN_1401f6b50` is the strongest world-build completion sender:
  it only emits `ClientProtOP_34` when the client is in logged-in state `0x14`
  and the world-build object at `client + 0x198d0` reports `+0x10 == 0`
- the neighboring native hook at raw block `1401f4c50` manipulates the same
  `client + 0x198d0` state block, resetting build markers and flipping a
  follow-up byte flag once that state reaches the ready path
- that shared state gate makes `34 -> MAP_BUILD_COMPLETE` the cleanest fit for
  the zero-byte world-handshake packet in the current `946` client
- `15` and `21` remain unresolved zero-byte client packets:
  `15` currently looks tied to the text-entry object at `client + 0x19838`,
  while `21` tears down local UI/selection state and walks a local list
  through `FUN_14019b190` / `FUN_1401ab3b0`

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

- `43` reads a local-zone base from the packet header, then loops nested sub-opcodes
  through the local descriptor table at `PTR_DAT_140c99f88` until the enclosing
  payload is exhausted; that behavior matches `UPDATE_ZONE_PARTIAL_ENCLOSED`
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

Current entity-sync notes from the bit-reader path:

- `FUN_140100220` is the live `946` packet bit-reader used by both entity-sync
  chains; it advances a bit cursor, uses `>> 3` and `& 7` addressing, and
  slices packed values directly from the packet payload buffer
- `28` resolves through `FUN_140106920` into `FUN_14011ebb0`, which in turn
  drives `FUN_14011f040`, `FUN_14011f4b0`, and the flagged-update reader
  `FUN_14011fd30`
- the `28` chain reads a repeating `0x10`-bit entity id with a `0xffff`
  sentinel, creates or rehydrates missing entities, tracks add/remove/update
  lists at `+0xa0a0`, `+0xb0a0`, and `+0xc0f0`, and then applies queued update
  blocks; that behavior matches `NPC_INFO`
- `42` resolves through `FUN_140106360` into `FUN_140124e30`, which snapshots
  the prior active list, performs four bit-packed passes over active/inactive
  entries via `FUN_140125350` and `FUN_140125ab0`, and then emits flagged
  update blocks through `FUN_14012ba50`
- the `42` chain explicitly iterates until `uVar14 < 0x800`, which is the
  client-side local-player cap, and its movement/update stages operate over the
  player-index lists at `+0x4038/+0x4040` and `+0x6060/+0x6068`; that behavior
  matches `PLAYER_INFO`

Regenerate the size-based shortlist with:

`python scripts/protocol_size_diff.py --source-build 919 --target-build 946 --out data/prot/946/sizeDiffReport.md`
