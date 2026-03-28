# 946 Interface Diff

- Status: `ok`
- Good session: `959546` -> `965668`
- Bad session: `1006615` -> `1006900`

## Verdict

- `activePlayer116Sent`: `no`
- `bootstrapMarkerPresent`: `no`
- `interfaceStageDelta`: `material`
- `handoffOutcomeChanged`: `unknown`
- Detected enabled session: `unknown`
- Detected disabled session: `goodSession`

## Top Findings

- `headModelBindings` `IF_SETPLAYERMODEL_SELF` score=`56` present in good session but missing in bad (1 event(s))
- `rootInterfaces` `IF_OPENTOP` score=`51` present in good session but missing in bad (1 event(s))
- `childInterfaces` `IF_OPENSUB` score=`41` present in good session but missing in bad (1 event(s))
- `uiState` `CLIENT_SETVARC_SMALL` score=`29` present in good session but missing in bad (4 event(s))
- `uiState` `opcode-206` score=`27` present in good session but missing in bad (2 event(s))

## Session Summaries

### Good

- Duration: `1309.193`
- Event count: `4647`
- Stage sequence: `['appearance', 'login-response', 'pipeline-switch', 'rebuild', 'default-state', 'interfaces']`
- Server opcodes: `{28: 2180, 38: 1, 39: 1, 42: 2180, 106: 1, 126: 1, 128: 4, 131: 257, 206: 2}`
- Marker counts: `{'world-skip-active-player': 1}`

### Bad

- Duration: `59.382`
- Event count: `216`
- Stage sequence: `[]`
- Server opcodes: `{28: 99, 42: 99, 131: 12}`
- Marker counts: `{}`
