# 946 Interface Diff

- Status: `ok`
- Good session: `238890` -> `245204`
- Bad session: `1049489` -> `1052444`

## Verdict

- `activePlayer116Sent`: `yes`
- `bootstrapMarkerPresent`: `yes`
- `interfaceStageDelta`: `none`
- `handoffOutcomeChanged`: `no`
- Detected enabled session: `goodSession`
- Detected disabled session: `badSession`

## Top Findings

- `activeSubBindings` `IF_OPENSUB_ACTIVE_PLAYER` score=`61` present in good session but missing in bad (1 event(s))

## Session Summaries

### Good

- Duration: `1345.795`
- Event count: `4798`
- Stage sequence: `['appearance', 'login-response', 'pipeline-switch', 'rebuild', 'default-state', 'interfaces']`
- Server opcodes: `{28: 2240, 38: 1, 39: 1, 42: 2240, 106: 1, 116: 1, 126: 1, 128: 4, 131: 264, 206: 2}`
- Marker counts: `{'world-open-active-player': 1}`

### Bad

- Duration: `2675.24`
- Event count: `2178`
- Stage sequence: `['appearance', 'login-response', 'pipeline-switch', 'rebuild', 'default-state', 'interfaces']`
- Server opcodes: `{28: 997, 38: 1, 39: 1, 42: 998, 106: 1, 126: 1, 128: 4, 131: 118, 206: 2}`
- Marker counts: `{'world-skip-active-player': 1}`
