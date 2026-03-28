# Phase 4 Verification Summary

Phase 4 begins here: it consumes the Phase 3 name candidates and turns them
into concrete work queues and safe parser-field extraction targets:

- field layout recovery for already named packets that still lack `946` field files
- runtime verification for unresolved packets that already have family or exact-name evidence
- sequential parser/sender field exports for the top safe recovery targets

## Queue Counts

- Field recovery targets: `58`
  - server: `9`
  - client: `49`
- Named packets skipped by do-not-touch blacklist: `5`
- Field gaps with a usable 919 reference file: `1`
- Runtime verification targets: `90`
  - server: `82`
  - client: `8`
- Runtime targets with exact-name candidates: `20`
- Runtime targets with unique exact-name candidates: `1`
- Runtime targets with ambiguous exact-name candidates: `19`
- Ambiguous client clusters carried forward from Phase 3: `1`
- Parser field exports generated: `15`

## Top Field Recovery Targets

- `server:21` `IF_OPENSUB_ACTIVE_LOC` family `IF` size `32` priority `100`
- `server:6` `LOC_ANIM_SPECIFIC` family `WORLD` size `10` priority `92`
- `server:64` `LOC_DEL` family `WORLD` size `2` priority `92`
- `server:78` `LOC_ADD_CHANGE` family `WORLD` size `7` priority `92`
- `server:122` `MAP_ANIM` family `WORLD` size `11` priority `92`
- `server:132` `LOC_PREFETCH` family `WORLD` size `5` priority `92`
- `client:12` `IF_BUTTOND` family `IF_BUTTON` size `16` priority `90`
- `client:18` `IF_BUTTON5` family `IF_BUTTON` size `8` priority `90`
- `client:47` `IF_BUTTON10` family `IF_BUTTON` size `8` priority `90`
- `client:54` `IF_BUTTON3` family `IF_BUTTON` size `8` priority `90`
- `client:61` `IF_BUTTON7` family `IF_BUTTON` size `8` priority `90`
- `client:63` `IF_BUTTON9` family `IF_BUTTON` size `8` priority `90`

## Parser Field Drafts

- `server:59` `IF_SETEVENTS` via `parser` `140109290` fields `4` types `intle, ushortle, intv2, ushortle128`
- `client:129` `RESUME_P_COUNTDIALOG` via `sender` `1401fda40` fields `1` types `long`
- `server:57` `IF_SETTEXT` via `parser` `140108fd0` fields `2` types `string, intle`
- `server:7` `IF_OPENSUB_ACTIVE_OBJ` via `parser` `1400fc390` fields `5` types `ushort, ushort, intv1, ubytec, intv1`
- `server:8` `IF_SETCOLOUR` via `parser` `140107d70` fields `2` types `intv1, ushort128`
- `server:21` `IF_OPENSUB_ACTIVE_LOC` via `parser` `1400fbf80` fields `10` types `ubyte, intle, ubyte, ubyte, ubyte, ubyte, intv1, ubyte, intle, ushortle128`
- `server:77` `IF_SETPLAYERHEAD` via `parser` `140108360` fields `1` types `intv1`
- `server:106` `IF_SETPLAYERMODEL_SELF` via `parser` `1401089c0` fields `1` types `intv2`
- `server:108` `IF_SETSCROLLPOS` via `parser` `140109650` fields `2` types `intle, ushort`
- `server:137` `IF_SETRETEX` via `parser` `140107c40` fields `1` types `ushort`
- `server:202` `IF_SETRECOL` via `parser` `140107b20` fields `4` types `ushortle, ushortle, ubytec, intle`
- `server:3` `OBJ_REVEAL` via `parser` `14013f5f0` fields `4` types `ushortle, ushortle, ubyte, ushortle`

## Do Not Touch

- `server:24` `MAP_PROJANIM` skipped: projectile map update packet; keep hand-crafted field handling
- `server:28` `NPC_INFO` skipped: bit-packed sync packet; keep hand-crafted parser and field handling
- `server:39` `REBUILD_NORMAL` skipped: region rebuild packet; keep hand-crafted field handling
- `server:42` `PLAYER_INFO` skipped: bit-packed sync packet; keep hand-crafted parser and field handling
- `server:214` `MAP_PROJANIM_HALFSQ` skipped: projectile map update packet; keep hand-crafted field handling

## Top Runtime Verification Targets

- `client:24` family `RESUME_STRING` priority `118` candidates `RESUME_P_STRINGDIALOG, RESUME_P_NAMEDIALOG, RESUME_P_OBJDIALOG` [dispatcher FUN_14003b9e0, selector 0x754]
- `client:67` family `RESUME_STRING` priority `118` candidates `RESUME_P_STRINGDIALOG, RESUME_P_NAMEDIALOG, RESUME_P_OBJDIALOG` [dispatcher FUN_14003b9e0, selector 0x323]
- `client:93` family `RESUME_STRING` priority `118` candidates `RESUME_P_STRINGDIALOG, RESUME_P_NAMEDIALOG, RESUME_P_OBJDIALOG` [dispatcher FUN_14003b9e0, selector 0x7d7]
- `server:67` family `IF` priority `102` candidates `IF_OPENSUB_ACTIVE_NPC`
- `server:4` family `IF` priority `98` candidates `IF_SETPLAYERMODEL_OTHER, IF_SETOBJECT, IF_SETPLAYERHEAD_OTHER, IF_SETANGLE, IF_SETTARGETPARAM, IF_SETPLAYERHEAD_IGNOREWORN`
- `server:26` family `IF` priority `98` candidates `IF_SETMODEL, IF_SETNPCHEAD, IF_SETANIM, IF_MOVESUB, IF_SETPOSITION, IF_SETTEXTFONT, IF_SET_HTTP_IMAGE, IF_SETGRAPHIC`
- `server:61` family `IF` priority `98` candidates `IF_SETMODEL, IF_SETNPCHEAD, IF_SETANIM, IF_MOVESUB, IF_SETPOSITION, IF_SETTEXTFONT, IF_SET_HTTP_IMAGE, IF_SETGRAPHIC`
- `server:62` family `IF` priority `98` candidates `IF_SETPLAYERMODEL_OTHER, IF_SETOBJECT, IF_SETPLAYERHEAD_OTHER, IF_SETANGLE, IF_SETTARGETPARAM, IF_SETPLAYERHEAD_IGNOREWORN`
- `server:71` family `IF` priority `98` candidates `IF_SETMODEL, IF_SETNPCHEAD, IF_SETANIM, IF_MOVESUB, IF_SETPOSITION, IF_SETTEXTFONT, IF_SET_HTTP_IMAGE, IF_SETGRAPHIC`
- `server:74` family `IF` priority `98` candidates `IF_SETMODEL, IF_SETNPCHEAD, IF_SETANIM, IF_MOVESUB, IF_SETPOSITION, IF_SETTEXTFONT, IF_SET_HTTP_IMAGE, IF_SETGRAPHIC`
- `server:75` family `IF` priority `98` candidates `IF_SETPLAYERMODEL_OTHER, IF_SETOBJECT, IF_SETPLAYERHEAD_OTHER, IF_SETANGLE, IF_SETTARGETPARAM, IF_SETPLAYERHEAD_IGNOREWORN`
- `server:89` family `IF` priority `98` candidates `IF_SETMODEL, IF_SETNPCHEAD, IF_SETANIM, IF_MOVESUB, IF_SETPOSITION, IF_SETTEXTFONT, IF_SET_HTTP_IMAGE, IF_SETGRAPHIC`

## Recommended Runtime Helpers

- `C:\Users\Demon\Documents\New project\OpenNXT\tools\trace_process_runtime.py`
- `C:\Users\Demon\Documents\New project\OpenNXT\tools\trace-win64c-runtime.ps1`

## Outputs

- `fieldGapAnalysis.json`
- `fieldRecoveryQueue.json`
- `runtimeVerificationQueue.json`
- `runtimeFocus.json`
- `parserFieldIndex.json`
- `parserFields/*.json`
- `phase4-summary.md`
