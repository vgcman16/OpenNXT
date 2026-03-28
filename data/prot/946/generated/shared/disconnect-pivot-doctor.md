# 946 Disconnect Pivot Doctor

- Status: `ok`
- Cluster id: `20260321-125712`
- Attempts analyzed: `12`
- Attempts with IF_SETEVENTS pivot: `0`
- Latest dominant opcode: `72`
- Latest dominant opcode count: `520`

## Verdict

- Likely blocker: `post-ready-disconnect-unclassified`
- Recommendation: The client still disconnects after ready acceptance, but no single dominant server opcode was isolated.

## Exact Needs

- keep the world channel alive longer after the first post-ready PLAYER_INFO frames

## Attempts

### Attempt 1

- Likely pivot: `post-ready-unclassified`
- World window: ``
- Pivot lines: `7332:7414`
- Dominant opcode: `128` x `4`
- Content first request: ``
- Archive requests: `0`
- Opcode counts: `{28: 2, 38: 2, 39: 1, 42: 2, 45: 1, 57: 1, 59: 1, 106: 1, 126: 1, 128: 4, 131: 3, 134: 1, 141: 2, 206: 1}`
- Marker counts: `{'world-allow-deferred-default-varps': 1, 'world-awaiting-ready-signal': 1, 'world-bind-local-player-model': 1, 'world-channel-inactive': 1, 'world-client-display-config': 1, 'world-defer-default-varps': 1, 'world-defer-forced-fallback-completion-companions': 1, 'world-defer-forced-fallback-completion-structure': 1, 'world-defer-forced-fallback-deferred-completion-scripts': 1, 'world-defer-forced-fallback-light-tail': 1, 'world-defer-forced-fallback-light-tail-pre-hold': 1, 'world-defer-forced-fallback-restored-world-panels': 1, 'world-defer-forced-fallback-scene-bridge': 1, 'world-defer-forced-fallback-supplemental-children': 2, 'world-defer-forced-fallback-utility-panel-deck': 1, 'world-force-local-appearance': 2, 'world-force-minimal-interface-bootstrap': 1, 'world-hold-keepalive': 1, 'world-hold-post-initial-sync': 1, 'world-keep-post-initial-sync-hold': 1, 'world-map-build-complete-compat': 1, 'world-open-loading-notes': 1, 'world-open-minimal-child': 1, 'world-prime-forced-fallback-pre-deferred-families': 1, 'world-prime-post-initial-sync-hold': 1, 'world-prime-post-initial-sync-hold-keepalive': 1, 'world-queue-deferred-completion-tail': 1, 'world-ready-signal': 1, 'world-ready-signal-accelerate-followup': 1, 'world-ready-signal-consume-latched': 1, 'world-ready-signal-deferred': 1, 'world-ready-signal-latched': 1, 'world-recv-serverperm-varcs': 1, 'world-send-immediate-followup-sync': 1, 'world-send-minimal-varcs': 1, 'world-send-npc-info': 2, 'world-send-player-info': 2, 'world-send-reset-client-varcache': 1, 'world-send-serverperm-ack-candidate': 1, 'world-skip-active-player': 1, 'world-skip-bootstrap-script': 1, 'world-skip-close-loading-overlay': 1, 'world-skip-forced-fallback-completion-companions': 1, 'world-skip-hold-sync': 1, 'world-skip-prime-forced-fallback-pre-deferred-families': 1, 'world-skip-prime-post-initial-sync-hold-sync': 1, 'world-skip-stats': 1, 'world-stage': 3, 'world-sync-frame': 2, 'world-waiting-map-build-complete': 1}`
- Needs: keep the world channel alive longer after the first post-ready PLAYER_INFO frames

### Attempt 2

- Likely pivot: `post-ready-unclassified`
- World window: ``
- Pivot lines: `7420:7501`
- Dominant opcode: `128` x `4`
- Content first request: ``
- Archive requests: `0`
- Opcode counts: `{28: 2, 38: 2, 39: 1, 42: 2, 45: 1, 57: 1, 59: 1, 106: 1, 126: 1, 128: 4, 131: 2, 134: 1, 141: 2, 206: 1}`
- Marker counts: `{'world-allow-deferred-default-varps': 1, 'world-awaiting-ready-signal': 1, 'world-bind-local-player-model': 1, 'world-channel-inactive': 1, 'world-client-display-config': 1, 'world-defer-default-varps': 1, 'world-defer-forced-fallback-completion-companions': 1, 'world-defer-forced-fallback-completion-structure': 1, 'world-defer-forced-fallback-deferred-completion-scripts': 1, 'world-defer-forced-fallback-light-tail': 1, 'world-defer-forced-fallback-light-tail-pre-hold': 1, 'world-defer-forced-fallback-restored-world-panels': 1, 'world-defer-forced-fallback-scene-bridge': 1, 'world-defer-forced-fallback-supplemental-children': 2, 'world-defer-forced-fallback-utility-panel-deck': 1, 'world-force-local-appearance': 2, 'world-force-minimal-interface-bootstrap': 1, 'world-hold-keepalive': 1, 'world-hold-post-initial-sync': 1, 'world-keep-post-initial-sync-hold': 1, 'world-map-build-complete-compat': 1, 'world-open-loading-notes': 1, 'world-open-minimal-child': 1, 'world-prime-forced-fallback-pre-deferred-families': 1, 'world-prime-post-initial-sync-hold': 1, 'world-prime-post-initial-sync-hold-keepalive': 1, 'world-queue-deferred-completion-tail': 1, 'world-ready-signal': 1, 'world-ready-signal-accelerate-followup': 1, 'world-ready-signal-consume-latched': 1, 'world-ready-signal-deferred': 1, 'world-ready-signal-latched': 1, 'world-recv-serverperm-varcs': 1, 'world-send-immediate-followup-sync': 1, 'world-send-minimal-varcs': 1, 'world-send-npc-info': 2, 'world-send-player-info': 2, 'world-send-rebuild-tail': 1, 'world-send-reset-client-varcache': 1, 'world-send-serverperm-ack-candidate': 1, 'world-skip-active-player': 1, 'world-skip-bootstrap-script': 1, 'world-skip-close-loading-overlay': 1, 'world-skip-forced-fallback-completion-companions': 1, 'world-skip-hold-sync': 1, 'world-skip-prime-forced-fallback-pre-deferred-families': 1, 'world-skip-prime-post-initial-sync-hold-sync': 1, 'world-skip-stats': 1, 'world-stage': 3, 'world-sync-frame': 2, 'world-waiting-map-build-complete': 1}`
- Needs: keep the world channel alive longer after the first post-ready PLAYER_INFO frames

### Attempt 3

- Likely pivot: `post-ready-unclassified`
- World window: ``
- Pivot lines: `7508:7590`
- Dominant opcode: `128` x `4`
- Content first request: `reference-table[0]`
- Archive requests: `0`
- Opcode counts: `{28: 2, 38: 2, 39: 1, 42: 2, 45: 1, 57: 1, 59: 1, 106: 1, 126: 1, 128: 4, 131: 3, 134: 1, 141: 2, 206: 1}`
- Marker counts: `{'world-allow-deferred-default-varps': 1, 'world-awaiting-ready-signal': 1, 'world-bind-local-player-model': 1, 'world-channel-inactive': 1, 'world-client-display-config': 1, 'world-defer-default-varps': 1, 'world-defer-forced-fallback-completion-companions': 1, 'world-defer-forced-fallback-completion-structure': 1, 'world-defer-forced-fallback-deferred-completion-scripts': 1, 'world-defer-forced-fallback-light-tail': 1, 'world-defer-forced-fallback-light-tail-pre-hold': 1, 'world-defer-forced-fallback-restored-world-panels': 1, 'world-defer-forced-fallback-scene-bridge': 1, 'world-defer-forced-fallback-supplemental-children': 2, 'world-defer-forced-fallback-utility-panel-deck': 1, 'world-force-local-appearance': 2, 'world-force-minimal-interface-bootstrap': 1, 'world-hold-keepalive': 1, 'world-hold-post-initial-sync': 1, 'world-keep-post-initial-sync-hold': 1, 'world-map-build-complete-compat': 1, 'world-open-loading-notes': 1, 'world-open-minimal-child': 1, 'world-prime-forced-fallback-pre-deferred-families': 1, 'world-prime-post-initial-sync-hold': 1, 'world-prime-post-initial-sync-hold-keepalive': 1, 'world-queue-deferred-completion-tail': 1, 'world-ready-signal': 1, 'world-ready-signal-accelerate-followup': 1, 'world-ready-signal-consume-latched': 1, 'world-ready-signal-deferred': 1, 'world-ready-signal-latched': 1, 'world-recv-serverperm-varcs': 1, 'world-send-immediate-followup-sync': 1, 'world-send-minimal-varcs': 1, 'world-send-npc-info': 2, 'world-send-player-info': 2, 'world-send-reset-client-varcache': 1, 'world-send-serverperm-ack-candidate': 1, 'world-skip-active-player': 1, 'world-skip-bootstrap-script': 1, 'world-skip-close-loading-overlay': 1, 'world-skip-forced-fallback-completion-companions': 1, 'world-skip-hold-sync': 1, 'world-skip-prime-forced-fallback-pre-deferred-families': 1, 'world-skip-prime-post-initial-sync-hold-sync': 1, 'world-skip-stats': 1, 'world-stage': 3, 'world-sync-frame': 2, 'world-waiting-map-build-complete': 1}`
- Needs: first non-reference /ms archive request after reference-table[0]
- Needs: keep the world channel alive longer after the first post-ready PLAYER_INFO frames

### Attempt 4

- Likely pivot: `post-ready-unclassified`
- World window: ``
- Pivot lines: `7597:7679`
- Dominant opcode: `128` x `4`
- Content first request: ``
- Archive requests: `0`
- Opcode counts: `{28: 2, 38: 2, 39: 1, 42: 2, 45: 1, 57: 1, 59: 1, 106: 1, 126: 1, 128: 4, 131: 3, 134: 1, 141: 2, 206: 1}`
- Marker counts: `{'world-allow-deferred-default-varps': 1, 'world-awaiting-ready-signal': 1, 'world-bind-local-player-model': 1, 'world-channel-inactive': 1, 'world-client-display-config': 1, 'world-defer-default-varps': 1, 'world-defer-forced-fallback-completion-companions': 1, 'world-defer-forced-fallback-completion-structure': 1, 'world-defer-forced-fallback-deferred-completion-scripts': 1, 'world-defer-forced-fallback-light-tail': 1, 'world-defer-forced-fallback-light-tail-pre-hold': 1, 'world-defer-forced-fallback-restored-world-panels': 1, 'world-defer-forced-fallback-scene-bridge': 1, 'world-defer-forced-fallback-supplemental-children': 2, 'world-defer-forced-fallback-utility-panel-deck': 1, 'world-force-local-appearance': 2, 'world-force-minimal-interface-bootstrap': 1, 'world-hold-keepalive': 1, 'world-hold-post-initial-sync': 1, 'world-keep-post-initial-sync-hold': 1, 'world-map-build-complete-compat': 1, 'world-open-loading-notes': 1, 'world-open-minimal-child': 1, 'world-prime-forced-fallback-pre-deferred-families': 1, 'world-prime-post-initial-sync-hold': 1, 'world-prime-post-initial-sync-hold-keepalive': 1, 'world-queue-deferred-completion-tail': 1, 'world-ready-signal': 1, 'world-ready-signal-accelerate-followup': 1, 'world-ready-signal-consume-latched': 1, 'world-ready-signal-deferred': 1, 'world-ready-signal-latched': 1, 'world-recv-serverperm-varcs': 1, 'world-send-immediate-followup-sync': 1, 'world-send-minimal-varcs': 1, 'world-send-npc-info': 2, 'world-send-player-info': 2, 'world-send-reset-client-varcache': 1, 'world-send-serverperm-ack-candidate': 1, 'world-skip-active-player': 1, 'world-skip-bootstrap-script': 1, 'world-skip-close-loading-overlay': 1, 'world-skip-forced-fallback-completion-companions': 1, 'world-skip-hold-sync': 1, 'world-skip-prime-forced-fallback-pre-deferred-families': 1, 'world-skip-prime-post-initial-sync-hold-sync': 1, 'world-skip-stats': 1, 'world-stage': 3, 'world-sync-frame': 2, 'world-waiting-map-build-complete': 1}`
- Needs: keep the world channel alive longer after the first post-ready PLAYER_INFO frames

### Attempt 5

- Likely pivot: `post-ready-unclassified`
- World window: ``
- Pivot lines: `7690:7770`
- Dominant opcode: `128` x `4`
- Content first request: ``
- Archive requests: `0`
- Opcode counts: `{28: 2, 38: 2, 42: 2, 45: 1, 57: 1, 59: 1, 106: 1, 126: 1, 128: 4, 131: 2, 134: 1, 141: 2, 206: 1}`
- Marker counts: `{'world-allow-deferred-default-varps': 1, 'world-awaiting-ready-signal': 1, 'world-bind-local-player-model': 1, 'world-channel-inactive': 1, 'world-client-display-config': 1, 'world-defer-default-varps': 1, 'world-defer-forced-fallback-completion-companions': 1, 'world-defer-forced-fallback-completion-structure': 1, 'world-defer-forced-fallback-deferred-completion-scripts': 1, 'world-defer-forced-fallback-light-tail': 1, 'world-defer-forced-fallback-light-tail-pre-hold': 1, 'world-defer-forced-fallback-restored-world-panels': 1, 'world-defer-forced-fallback-scene-bridge': 1, 'world-defer-forced-fallback-supplemental-children': 2, 'world-defer-forced-fallback-utility-panel-deck': 1, 'world-force-local-appearance': 2, 'world-force-minimal-interface-bootstrap': 1, 'world-hold-keepalive': 1, 'world-hold-post-initial-sync': 1, 'world-ignore-client-compat': 2, 'world-keep-post-initial-sync-hold': 1, 'world-map-build-complete-compat': 1, 'world-open-loading-notes': 1, 'world-open-minimal-child': 1, 'world-prime-forced-fallback-pre-deferred-families': 1, 'world-prime-post-initial-sync-hold': 1, 'world-prime-post-initial-sync-hold-keepalive': 1, 'world-queue-deferred-completion-tail': 1, 'world-ready-signal': 1, 'world-ready-signal-accelerate-followup': 1, 'world-ready-signal-consume-latched': 1, 'world-ready-signal-deferred': 1, 'world-ready-signal-latched': 1, 'world-recv-serverperm-varcs': 1, 'world-send-immediate-followup-sync': 1, 'world-send-minimal-varcs': 1, 'world-send-npc-info': 2, 'world-send-player-info': 2, 'world-send-reset-client-varcache': 1, 'world-send-serverperm-ack-candidate': 1, 'world-skip-active-player': 1, 'world-skip-bootstrap-script': 1, 'world-skip-close-loading-overlay': 1, 'world-skip-forced-fallback-completion-companions': 1, 'world-skip-hold-sync': 1, 'world-skip-prime-forced-fallback-pre-deferred-families': 1, 'world-skip-prime-post-initial-sync-hold-sync': 1, 'world-skip-stats': 1, 'world-stage': 3, 'world-sync-frame': 2}`
- Needs: keep the world channel alive longer after the first post-ready PLAYER_INFO frames

### Attempt 6

- Likely pivot: `post-ready-unclassified`
- World window: ``
- Pivot lines: `7777:7859`
- Dominant opcode: `128` x `4`
- Content first request: `reference-table[0]`
- Archive requests: `0`
- Opcode counts: `{28: 2, 38: 2, 39: 1, 42: 2, 45: 1, 57: 1, 59: 1, 106: 1, 126: 1, 128: 4, 131: 3, 134: 1, 141: 2, 206: 1}`
- Marker counts: `{'world-allow-deferred-default-varps': 1, 'world-awaiting-ready-signal': 1, 'world-bind-local-player-model': 1, 'world-channel-inactive': 1, 'world-client-display-config': 1, 'world-defer-default-varps': 1, 'world-defer-forced-fallback-completion-companions': 1, 'world-defer-forced-fallback-completion-structure': 1, 'world-defer-forced-fallback-deferred-completion-scripts': 1, 'world-defer-forced-fallback-light-tail': 1, 'world-defer-forced-fallback-light-tail-pre-hold': 1, 'world-defer-forced-fallback-restored-world-panels': 1, 'world-defer-forced-fallback-scene-bridge': 1, 'world-defer-forced-fallback-supplemental-children': 2, 'world-defer-forced-fallback-utility-panel-deck': 1, 'world-force-local-appearance': 2, 'world-force-minimal-interface-bootstrap': 1, 'world-hold-keepalive': 1, 'world-hold-post-initial-sync': 1, 'world-keep-post-initial-sync-hold': 1, 'world-map-build-complete-compat': 1, 'world-open-loading-notes': 1, 'world-open-minimal-child': 1, 'world-prime-forced-fallback-pre-deferred-families': 1, 'world-prime-post-initial-sync-hold': 1, 'world-prime-post-initial-sync-hold-keepalive': 1, 'world-queue-deferred-completion-tail': 1, 'world-ready-signal': 1, 'world-ready-signal-accelerate-followup': 1, 'world-ready-signal-consume-latched': 1, 'world-ready-signal-deferred': 1, 'world-ready-signal-latched': 1, 'world-recv-serverperm-varcs': 1, 'world-send-immediate-followup-sync': 1, 'world-send-minimal-varcs': 1, 'world-send-npc-info': 2, 'world-send-player-info': 2, 'world-send-reset-client-varcache': 1, 'world-send-serverperm-ack-candidate': 1, 'world-skip-active-player': 1, 'world-skip-bootstrap-script': 1, 'world-skip-close-loading-overlay': 1, 'world-skip-forced-fallback-completion-companions': 1, 'world-skip-hold-sync': 1, 'world-skip-prime-forced-fallback-pre-deferred-families': 1, 'world-skip-prime-post-initial-sync-hold-sync': 1, 'world-skip-stats': 1, 'world-stage': 3, 'world-sync-frame': 2, 'world-waiting-map-build-complete': 1}`
- Needs: first non-reference /ms archive request after reference-table[0]
- Needs: keep the world channel alive longer after the first post-ready PLAYER_INFO frames

### Attempt 7

- Likely pivot: `post-ready-unclassified`
- World window: ``
- Pivot lines: `7866:7948`
- Dominant opcode: `128` x `4`
- Content first request: ``
- Archive requests: `0`
- Opcode counts: `{28: 2, 38: 2, 39: 1, 42: 2, 45: 1, 57: 1, 59: 1, 106: 1, 126: 1, 128: 4, 131: 3, 134: 1, 141: 2, 206: 1}`
- Marker counts: `{'world-allow-deferred-default-varps': 1, 'world-awaiting-ready-signal': 1, 'world-bind-local-player-model': 1, 'world-channel-inactive': 1, 'world-client-display-config': 1, 'world-defer-default-varps': 1, 'world-defer-forced-fallback-completion-companions': 1, 'world-defer-forced-fallback-completion-structure': 1, 'world-defer-forced-fallback-deferred-completion-scripts': 1, 'world-defer-forced-fallback-light-tail': 1, 'world-defer-forced-fallback-light-tail-pre-hold': 1, 'world-defer-forced-fallback-restored-world-panels': 1, 'world-defer-forced-fallback-scene-bridge': 1, 'world-defer-forced-fallback-supplemental-children': 2, 'world-defer-forced-fallback-utility-panel-deck': 1, 'world-force-local-appearance': 2, 'world-force-minimal-interface-bootstrap': 1, 'world-hold-keepalive': 1, 'world-hold-post-initial-sync': 1, 'world-keep-post-initial-sync-hold': 1, 'world-map-build-complete-compat': 1, 'world-open-loading-notes': 1, 'world-open-minimal-child': 1, 'world-prime-forced-fallback-pre-deferred-families': 1, 'world-prime-post-initial-sync-hold': 1, 'world-prime-post-initial-sync-hold-keepalive': 1, 'world-queue-deferred-completion-tail': 1, 'world-ready-signal': 1, 'world-ready-signal-accelerate-followup': 1, 'world-ready-signal-consume-latched': 1, 'world-ready-signal-deferred': 1, 'world-ready-signal-latched': 1, 'world-recv-serverperm-varcs': 1, 'world-send-immediate-followup-sync': 1, 'world-send-minimal-varcs': 1, 'world-send-npc-info': 2, 'world-send-player-info': 2, 'world-send-reset-client-varcache': 1, 'world-send-serverperm-ack-candidate': 1, 'world-skip-active-player': 1, 'world-skip-bootstrap-script': 1, 'world-skip-close-loading-overlay': 1, 'world-skip-forced-fallback-completion-companions': 1, 'world-skip-hold-sync': 1, 'world-skip-prime-forced-fallback-pre-deferred-families': 1, 'world-skip-prime-post-initial-sync-hold-sync': 1, 'world-skip-stats': 1, 'world-stage': 3, 'world-sync-frame': 2, 'world-waiting-map-build-complete': 1}`
- Needs: keep the world channel alive longer after the first post-ready PLAYER_INFO frames

### Attempt 8

- Likely pivot: `post-ready-unclassified`
- World window: ``
- Pivot lines: `7954:8035`
- Dominant opcode: `128` x `4`
- Content first request: ``
- Archive requests: `0`
- Opcode counts: `{28: 2, 38: 2, 39: 1, 42: 2, 45: 1, 57: 1, 59: 1, 106: 1, 126: 1, 128: 4, 131: 2, 134: 1, 141: 2, 206: 1}`
- Marker counts: `{'world-allow-deferred-default-varps': 1, 'world-awaiting-ready-signal': 1, 'world-bind-local-player-model': 1, 'world-channel-inactive': 1, 'world-client-display-config': 1, 'world-defer-default-varps': 1, 'world-defer-forced-fallback-completion-companions': 1, 'world-defer-forced-fallback-completion-structure': 1, 'world-defer-forced-fallback-deferred-completion-scripts': 1, 'world-defer-forced-fallback-light-tail': 1, 'world-defer-forced-fallback-light-tail-pre-hold': 1, 'world-defer-forced-fallback-restored-world-panels': 1, 'world-defer-forced-fallback-scene-bridge': 1, 'world-defer-forced-fallback-supplemental-children': 2, 'world-defer-forced-fallback-utility-panel-deck': 1, 'world-force-local-appearance': 2, 'world-force-minimal-interface-bootstrap': 1, 'world-hold-keepalive': 1, 'world-hold-post-initial-sync': 1, 'world-keep-post-initial-sync-hold': 1, 'world-map-build-complete-compat': 1, 'world-open-loading-notes': 1, 'world-open-minimal-child': 1, 'world-prime-forced-fallback-pre-deferred-families': 1, 'world-prime-post-initial-sync-hold': 1, 'world-prime-post-initial-sync-hold-keepalive': 1, 'world-queue-deferred-completion-tail': 1, 'world-ready-signal': 1, 'world-ready-signal-accelerate-followup': 1, 'world-ready-signal-consume-latched': 1, 'world-ready-signal-deferred': 1, 'world-ready-signal-latched': 1, 'world-recv-serverperm-varcs': 1, 'world-send-immediate-followup-sync': 1, 'world-send-minimal-varcs': 1, 'world-send-npc-info': 2, 'world-send-player-info': 2, 'world-send-rebuild-tail': 1, 'world-send-reset-client-varcache': 1, 'world-send-serverperm-ack-candidate': 1, 'world-skip-active-player': 1, 'world-skip-bootstrap-script': 1, 'world-skip-close-loading-overlay': 1, 'world-skip-forced-fallback-completion-companions': 1, 'world-skip-hold-sync': 1, 'world-skip-prime-forced-fallback-pre-deferred-families': 1, 'world-skip-prime-post-initial-sync-hold-sync': 1, 'world-skip-stats': 1, 'world-stage': 3, 'world-sync-frame': 2, 'world-waiting-map-build-complete': 1}`
- Needs: keep the world channel alive longer after the first post-ready PLAYER_INFO frames

### Attempt 9

- Likely pivot: `post-ready-unclassified`
- World window: ``
- Pivot lines: `8042:8124`
- Dominant opcode: `128` x `4`
- Content first request: `reference-table[0]`
- Archive requests: `0`
- Opcode counts: `{28: 2, 38: 2, 39: 1, 42: 2, 45: 1, 57: 1, 59: 1, 106: 1, 126: 1, 128: 4, 131: 3, 134: 1, 141: 2, 206: 1}`
- Marker counts: `{'world-allow-deferred-default-varps': 1, 'world-awaiting-ready-signal': 1, 'world-bind-local-player-model': 1, 'world-channel-inactive': 1, 'world-client-display-config': 1, 'world-defer-default-varps': 1, 'world-defer-forced-fallback-completion-companions': 1, 'world-defer-forced-fallback-completion-structure': 1, 'world-defer-forced-fallback-deferred-completion-scripts': 1, 'world-defer-forced-fallback-light-tail': 1, 'world-defer-forced-fallback-light-tail-pre-hold': 1, 'world-defer-forced-fallback-restored-world-panels': 1, 'world-defer-forced-fallback-scene-bridge': 1, 'world-defer-forced-fallback-supplemental-children': 2, 'world-defer-forced-fallback-utility-panel-deck': 1, 'world-force-local-appearance': 2, 'world-force-minimal-interface-bootstrap': 1, 'world-hold-keepalive': 1, 'world-hold-post-initial-sync': 1, 'world-keep-post-initial-sync-hold': 1, 'world-map-build-complete-compat': 1, 'world-open-loading-notes': 1, 'world-open-minimal-child': 1, 'world-prime-forced-fallback-pre-deferred-families': 1, 'world-prime-post-initial-sync-hold': 1, 'world-prime-post-initial-sync-hold-keepalive': 1, 'world-queue-deferred-completion-tail': 1, 'world-ready-signal': 1, 'world-ready-signal-accelerate-followup': 1, 'world-ready-signal-consume-latched': 1, 'world-ready-signal-deferred': 1, 'world-ready-signal-latched': 1, 'world-recv-serverperm-varcs': 1, 'world-send-immediate-followup-sync': 1, 'world-send-minimal-varcs': 1, 'world-send-npc-info': 2, 'world-send-player-info': 2, 'world-send-reset-client-varcache': 1, 'world-send-serverperm-ack-candidate': 1, 'world-skip-active-player': 1, 'world-skip-bootstrap-script': 1, 'world-skip-close-loading-overlay': 1, 'world-skip-forced-fallback-completion-companions': 1, 'world-skip-hold-sync': 1, 'world-skip-prime-forced-fallback-pre-deferred-families': 1, 'world-skip-prime-post-initial-sync-hold-sync': 1, 'world-skip-stats': 1, 'world-stage': 3, 'world-sync-frame': 2, 'world-waiting-map-build-complete': 1}`
- Needs: first non-reference /ms archive request after reference-table[0]
- Needs: keep the world channel alive longer after the first post-ready PLAYER_INFO frames

### Attempt 10

- Likely pivot: `post-ready-unclassified`
- World window: ``
- Pivot lines: `9662:11259`
- Dominant opcode: `72` x `833`
- Content first request: ``
- Archive requests: `0`
- Opcode counts: `{28: 7, 38: 57, 42: 7, 45: 7, 51: 552, 57: 5, 59: 30, 72: 833, 128: 4, 131: 2, 141: 47}`
- Marker counts: `{'world-arm-scene-start-sync-burst': 1, 'world-channel-inactive': 1, 'world-defer-deferred-completion-announcement-scripts': 1, 'world-defer-deferred-completion-event-delta': 1, 'world-defer-late-root-interface-events': 1, 'world-force-local-appearance': 3, 'world-open-forced-fallback-scene-bridge': 1, 'world-open-minimal-supplemental-child': 2, 'world-open-restored-interface': 1, 'world-prime-late-default-varps-followup-sync': 1, 'world-prime-late-default-varps-keepalive': 1, 'world-queued-deferred-default-varps': 1, 'world-send-deferred-completion-structure': 1, 'world-send-deferred-completion-tail': 1, 'world-send-deferred-completion-tail-after-sync': 1, 'world-send-deferred-default-varps': 1, 'world-send-deferred-forced-fallback-completion-companions': 1, 'world-send-forced-fallback-deferred-completion-scripts': 1, 'world-send-forced-fallback-light-tail-scripts': 1, 'world-send-forced-fallback-restored-world-panels': 1, 'world-send-forced-fallback-utility-panel-deck': 1, 'world-send-light-interface-tail': 1, 'world-send-npc-info': 3, 'world-send-player-info': 3, 'world-send-scene-start-sync-burst': 3, 'world-skip-forced-fallback-deferred-completion-events': 1, 'world-skip-forced-fallback-light-tail-events': 1, 'world-skip-forced-fallback-supplemental-events': 1, 'world-skip-forced-fallback-utility-panel-events': 1, 'world-stage': 1, 'world-sync-frame': 3}`
- Needs: keep the world channel alive longer after the first post-ready PLAYER_INFO frames

### Attempt 11

- Likely pivot: `post-ready-unclassified`
- World window: ``
- Pivot lines: `11352:12946`
- Dominant opcode: `72` x `833`
- Content first request: ``
- Archive requests: `0`
- Opcode counts: `{28: 6, 38: 57, 42: 6, 45: 7, 51: 552, 57: 5, 59: 30, 72: 833, 128: 4, 131: 1, 141: 47}`
- Marker counts: `{'world-arm-scene-start-sync-burst': 1, 'world-channel-inactive': 1, 'world-defer-deferred-completion-announcement-scripts': 1, 'world-defer-deferred-completion-event-delta': 1, 'world-defer-late-root-interface-events': 1, 'world-force-local-appearance': 3, 'world-open-forced-fallback-scene-bridge': 1, 'world-open-minimal-supplemental-child': 2, 'world-open-restored-interface': 1, 'world-prime-late-default-varps-followup-sync': 1, 'world-prime-late-default-varps-keepalive': 1, 'world-queued-deferred-default-varps': 1, 'world-send-deferred-completion-structure': 1, 'world-send-deferred-completion-tail': 1, 'world-send-deferred-completion-tail-after-sync': 1, 'world-send-deferred-default-varps': 1, 'world-send-deferred-forced-fallback-completion-companions': 1, 'world-send-forced-fallback-deferred-completion-scripts': 1, 'world-send-forced-fallback-light-tail-scripts': 1, 'world-send-forced-fallback-restored-world-panels': 1, 'world-send-forced-fallback-utility-panel-deck': 1, 'world-send-light-interface-tail': 1, 'world-send-npc-info': 3, 'world-send-player-info': 3, 'world-send-scene-start-sync-burst': 3, 'world-skip-forced-fallback-deferred-completion-events': 1, 'world-skip-forced-fallback-light-tail-events': 1, 'world-skip-forced-fallback-supplemental-events': 1, 'world-skip-forced-fallback-utility-panel-events': 1, 'world-stage': 1, 'world-sync-frame': 3}`
- Needs: keep the world channel alive longer after the first post-ready PLAYER_INFO frames

### Attempt 12

- Likely pivot: `post-ready-unclassified`
- World window: ``
- Pivot lines: `13039:14150`
- Dominant opcode: `72` x `520`
- Content first request: ``
- Archive requests: `0`
- Opcode counts: `{28: 1, 38: 57, 42: 1, 45: 7, 51: 406, 57: 5, 59: 30, 72: 520, 128: 4, 131: 1, 141: 47}`
- Marker counts: `{'world-arm-scene-start-sync-burst': 1, 'world-defer-deferred-completion-announcement-scripts': 1, 'world-defer-deferred-completion-event-delta': 1, 'world-defer-late-root-interface-events': 1, 'world-force-local-appearance': 1, 'world-open-forced-fallback-scene-bridge': 1, 'world-open-minimal-supplemental-child': 2, 'world-open-restored-interface': 1, 'world-prime-late-default-varps-followup-sync': 1, 'world-prime-late-default-varps-keepalive': 1, 'world-queued-deferred-default-varps': 1, 'world-send-deferred-completion-structure': 1, 'world-send-deferred-completion-tail': 1, 'world-send-deferred-completion-tail-after-sync': 1, 'world-send-deferred-default-varps': 1, 'world-send-deferred-forced-fallback-completion-companions': 1, 'world-send-forced-fallback-deferred-completion-scripts': 1, 'world-send-forced-fallback-light-tail-scripts': 1, 'world-send-forced-fallback-restored-world-panels': 1, 'world-send-forced-fallback-utility-panel-deck': 1, 'world-send-light-interface-tail': 1, 'world-send-npc-info': 1, 'world-send-player-info': 1, 'world-skip-forced-fallback-deferred-completion-events': 1, 'world-skip-forced-fallback-light-tail-events': 1, 'world-skip-forced-fallback-supplemental-events': 1, 'world-skip-forced-fallback-utility-panel-events': 1, 'world-stage': 1, 'world-sync-frame': 1}`
- Needs: keep the world channel alive longer after the first post-ready PLAYER_INFO frames
