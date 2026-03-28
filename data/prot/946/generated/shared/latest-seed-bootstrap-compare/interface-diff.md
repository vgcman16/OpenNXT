# 946 Interface Diff

- Status: `ok`
- Good session: `959546` -> `965668`
- Bad session: `971342` -> `997717`

## Verdict

- `activePlayer116Sent`: `no`
- `bootstrapMarkerPresent`: `no`
- `interfaceStageDelta`: `none`
- `handoffOutcomeChanged`: `unknown`
- Detected enabled session: `unknown`
- Detected disabled session: `unknown`

## Top Findings

- No structural diffs detected.

## Session Summaries

### Good

- Duration: `1309.193`
- Event count: `4647`
- Stage sequence: `['appearance', 'login-response', 'pipeline-switch', 'rebuild', 'default-state', 'interfaces']`
- Server opcodes: `{28: 2180, 38: 1, 39: 1, 42: 2180, 106: 1, 126: 1, 128: 4, 131: 257, 206: 2}`
- Marker counts: `{'world-skip-active-player': 1}`

### Bad

- Duration: `5702.344`
- Event count: `20153`
- Stage sequence: `['appearance', 'login-response', 'pipeline-switch', 'rebuild', 'default-state', 'interfaces']`
- Server opcodes: `{28: 9503, 38: 1, 39: 1, 42: 9503, 106: 1, 126: 1, 128: 4, 131: 1118, 206: 2}`
- Marker counts: `{'world-skip-active-player': 1}`
