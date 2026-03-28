# Phase 3 Name Candidate Summary

## Server

- Total opcodes: `217`
- Named opcodes: `40`
- Unresolved opcodes: `177`
- Confirmed: `40`
- Candidate: `166`
- Unknown: `11`
- Family classified: `122`
- Unresolved with family hint: `82`
- Unresolved with exact-name candidates: `17`
- Unresolved with unique exact candidate: `1`
- Mean confidence score: `0.4101`

Top unresolved families:
- `VAR` -> `43`
- `IF` -> `21`
- `SYNC` -> `10`
- `WORLD` -> `8`

Sample unique exact-name candidates:
- `67` -> `IF_OPENSUB_ACTIVE_NPC` via `legacy-family-size-unique`

Sample ambiguous exact-name candidates:
- `4` -> `IF_SETPLAYERMODEL_OTHER, IF_SETOBJECT, IF_SETPLAYERHEAD_OTHER, IF_SETANGLE, IF_SETTARGETPARAM, IF_SETPLAYERHEAD_IGNOREWORN` via `legacy-family-size-ambiguous`
- `26` -> `IF_SETMODEL, IF_SETNPCHEAD, IF_SETANIM, IF_MOVESUB, IF_SETPOSITION, IF_SETTEXTFONT, IF_SET_HTTP_IMAGE, IF_SETGRAPHIC` via `legacy-family-size-ambiguous`
- `61` -> `IF_SETMODEL, IF_SETNPCHEAD, IF_SETANIM, IF_MOVESUB, IF_SETPOSITION, IF_SETTEXTFONT, IF_SET_HTTP_IMAGE, IF_SETGRAPHIC` via `legacy-family-size-ambiguous`
- `62` -> `IF_SETPLAYERMODEL_OTHER, IF_SETOBJECT, IF_SETPLAYERHEAD_OTHER, IF_SETANGLE, IF_SETTARGETPARAM, IF_SETPLAYERHEAD_IGNOREWORN` via `legacy-family-size-ambiguous`
- `71` -> `IF_SETMODEL, IF_SETNPCHEAD, IF_SETANIM, IF_MOVESUB, IF_SETPOSITION, IF_SETTEXTFONT, IF_SET_HTTP_IMAGE, IF_SETGRAPHIC` via `legacy-family-size-ambiguous`
- `74` -> `IF_SETMODEL, IF_SETNPCHEAD, IF_SETANIM, IF_MOVESUB, IF_SETPOSITION, IF_SETTEXTFONT, IF_SET_HTTP_IMAGE, IF_SETGRAPHIC` via `legacy-family-size-ambiguous`

## Client

- Total opcodes: `130`
- Named opcodes: `54`
- Unresolved opcodes: `76`
- Confirmed: `54`
- Candidate: `57`
- Unknown: `19`
- Family classified: `62`
- Unresolved with family hint: `8`
- Unresolved with exact-name candidates: `3`
- Unresolved with unique exact candidate: `0`
- Mean confidence score: `0.5438`

Top unresolved families:
- `RAW_TEXT` -> `3`
- `RESUME_STRING` -> `3`
- `TEXT_ENTRY` -> `1`
- `UI_RESET` -> `1`

Sample ambiguous exact-name candidates:
- `24` -> `RESUME_P_STRINGDIALOG, RESUME_P_NAMEDIALOG, RESUME_P_OBJDIALOG` via `manual-override` [dispatcher FUN_14003b9e0, selector 0x754]
- `67` -> `RESUME_P_STRINGDIALOG, RESUME_P_NAMEDIALOG, RESUME_P_OBJDIALOG` via `manual-override` [dispatcher FUN_14003b9e0, selector 0x323]
- `93` -> `RESUME_P_STRINGDIALOG, RESUME_P_NAMEDIALOG, RESUME_P_OBJDIALOG` via `manual-override` [dispatcher FUN_14003b9e0, selector 0x7d7]

## Ambiguous Client Clusters

- `resume-prompt-cluster` via `FUN_14003b9e0` with candidates `RESUME_P_STRINGDIALOG, RESUME_P_NAMEDIALOG, RESUME_P_OBJDIALOG`
  - opcode `24` selector `0x754` sender `FUN_1401fe390`
  - opcode `67` selector `0x323` sender `FUN_1401fd5b0`
  - opcode `93` selector `0x7d7` sender `FUN_1401fdf30`

## Outputs

- `nameCandidates.json`
- `clientAmbiguousClusters.json`
- `serverProtNames.generated.toml`
- `clientProtNames.generated.toml`
- `serverProtNames.uniqueCandidates.generated.toml`
- `clientProtNames.uniqueCandidates.generated.toml`
- `phase3-summary.md`
