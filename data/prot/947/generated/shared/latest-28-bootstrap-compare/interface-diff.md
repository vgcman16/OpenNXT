# 946 Interface Diff

- Status: `ok`
- Good session: `959546` -> `965668`
- Bad session: `1008816` -> `1009484`

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

- Duration: `124.074`
- Event count: `468`
- Stage sequence: `['appearance', 'login-response', 'pipeline-switch', 'rebuild', 'default-state', 'interfaces']`
- Server opcodes: `{28: 206, 38: 1, 39: 1, 42: 206, 106: 1, 126: 1, 128: 4, 131: 24, 206: 2}`
- Marker counts: `{'world-skip-active-player': 1}`
