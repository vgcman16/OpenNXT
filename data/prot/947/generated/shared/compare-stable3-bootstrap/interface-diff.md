# 946 Interface Diff

- Status: `ok`
- Good session: `223284` -> `238713`
- Bad session: `971342` -> `997717`

## Verdict

- `activePlayer116Sent`: `no`
- `bootstrapMarkerPresent`: `no`
- `interfaceStageDelta`: `none`
- `handoffOutcomeChanged`: `unknown`
- Detected enabled session: `unknown`
- Detected disabled session: `badSession`

## Top Findings

- No structural diffs detected.

## Session Summaries

### Good

- Duration: `3326.39`
- Event count: `11775`
- Stage sequence: `['appearance', 'login-response', 'pipeline-switch', 'rebuild', 'default-state', 'interfaces']`
- Server opcodes: `{28: 5536, 38: 1, 39: 1, 42: 5536, 106: 1, 126: 1, 128: 4, 131: 651, 206: 2}`
- Marker counts: `{}`

### Bad

- Duration: `5702.344`
- Event count: `20153`
- Stage sequence: `['appearance', 'login-response', 'pipeline-switch', 'rebuild', 'default-state', 'interfaces']`
- Server opcodes: `{28: 9503, 38: 1, 39: 1, 42: 9503, 106: 1, 126: 1, 128: 4, 131: 1118, 206: 2}`
- Marker counts: `{'world-skip-active-player': 1}`
