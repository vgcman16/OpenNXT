# 946 Interface Diff

- Status: `ok`
- Good session: `959546` -> `965703`
- Bad session: `971342` -> `997717`

## Verdict

- `activePlayer116Sent`: `no`
- `bootstrapMarkerPresent`: `no`
- `interfaceStageDelta`: `material`
- `handoffOutcomeChanged`: `unknown`
- Detected enabled session: `unknown`
- Detected disabled session: `unknown`

## Top Findings

- `uiState` `UPDATE_STAT` score=`54` present in good session but missing in bad (29 event(s))
- `rootInterfaces` `IF_OPENTOP` score=`51` present in good session but missing in bad (1 event(s))
- `uiState` `RESET_CLIENT_VARCACHE` score=`26` present in good session but missing in bad (1 event(s))

## Session Summaries

### Good

- Duration: `1641.98`
- Event count: `4865`
- Stage sequence: `['appearance', 'login-response', 'pipeline-switch', 'rebuild', 'stats', 'default-state', 'interfaces']`
- Server opcodes: `{28: 2180, 38: 1, 39: 1, 42: 2180, 106: 1, 126: 2, 128: 4, 129: 29, 131: 258, 134: 1, 206: 2}`
- Marker counts: `{'world-added': 1, 'world-awaiting-ready-signal': 1, 'world-bind-local-player-model': 1, 'world-client-bootstrap-control': 3, 'world-client-display-config': 5, 'world-force-local-appearance': 4, 'world-hold-post-initial-sync': 3, 'world-ignore-client-compat': 5, 'world-ignore-client-timed': 3, 'world-map-build-complete-compat': 1, 'world-open-minimal-child': 1, 'world-post-initial-sync-hold': 1, 'world-ready-signal': 1, 'world-ready-signal-deferred': 1, 'world-ready-signal-latched': 1, 'world-recv-serverperm-varcs': 2, 'world-send-minimal-varcs': 1, 'world-send-npc-info': 48, 'world-send-player-info': 48, 'world-send-serverperm-ack-candidate': 2, 'world-skip-active-player': 1, 'world-skip-init-state': 1, 'world-skip-stats': 1, 'world-sync-frame': 48, 'world-unhandled-client-compat': 1, 'world-waiting-map-build-complete': 1}`

### Bad

- Duration: `5702.344`
- Event count: `20779`
- Stage sequence: `['appearance', 'login-response', 'pipeline-switch', 'rebuild', 'stats', 'default-state', 'interfaces']`
- Server opcodes: `{28: 9503, 38: 1, 39: 1, 42: 9503, 106: 1, 126: 1, 128: 4, 131: 1118, 206: 2}`
- Marker counts: `{'world-awaiting-ready-signal': 1, 'world-bind-local-player-model': 1, 'world-client-bootstrap-control': 3, 'world-client-display-config': 5, 'world-force-local-appearance': 4, 'world-hold-post-initial-sync': 3, 'world-ignore-client-compat': 5, 'world-ignore-client-timed': 2, 'world-map-build-complete-compat': 1, 'world-open-minimal-child': 1, 'world-post-initial-sync-hold': 1, 'world-ready-signal': 1, 'world-ready-signal-deferred': 1, 'world-ready-signal-latched': 1, 'world-recv-serverperm-varcs': 2, 'world-send-minimal-varcs': 1, 'world-send-npc-info': 195, 'world-send-player-info': 195, 'world-send-rebuild-tail': 1, 'world-send-serverperm-ack-candidate': 2, 'world-skip-active-player': 1, 'world-skip-init-state': 1, 'world-skip-stats': 1, 'world-sync-frame': 195, 'world-unhandled-client-compat': 1, 'world-waiting-map-build-complete': 1}`
