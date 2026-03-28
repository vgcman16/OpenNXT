# 946 Attempt Diff Doctor

- Status: `ok`
- Cluster id: `20260322-092945`
- Attempts analyzed: `12`
- Unique tail signatures: `6`
- Latest outcome: `interfaces-loopback`
- Latest disconnect stage: `interfaces`
- Latest content label: ``

## Verdict

- Likely blocker: `interfaces-tail-variant-loopback`
- Recommendation: The client still dies at interfaces, but there are multiple tail signatures. Diff the dominant signatures instead of changing routing again.

## Exact Needs

- fresh content capture on the looping attempt cluster; no paired scene archive request exists yet
- first surviving step after world-hold-keepalive:forced-map-build-fallback -> world-skip-hold-sync:forced-map-build-fallback-post-prime -> world-channel-inactive -> world-added; the channel still drops at interfaces on the dominant signature
- content pairing disappears on attempts 1, 2, 3, 4, 5, 6; capture the exact first content session that should follow the interface tail on those later attempts
- compare the dominant world-tail signature against a non-looping baseline: world-hold-post-initial-sync -> world-hold-keepalive:forced-map-build-fallback -> world-skip-hold-sync:forced-map-build-fallback-post-prime -> world-channel-inactive -> world-added
- compare the last server raw tail against a non-looping baseline: send-raw:28 -> send-raw:42 -> send-raw:131 -> send-raw:131 -> send-raw:131

## Cluster Diffs

- all attempts end with the same outcome: interfaces-loopback
- every paired server attempt closes at bootstrap stage interfaces
- paired content labels: <missing> x12
- paired raw login byte-shapes: 0->0 x12
- tail signatures split into 5x attempts [2, 4, 5, 7, 8], 3x attempts [1, 3, 9], 1x attempts [10], 1x attempts [12]

## Signature Groups

### Signature 1

- Attempts: `[2, 4, 5, 7, 8]`
- Outcomes: `['interfaces-loopback']`
- Disconnect stages: `['interfaces']`
- Content labels: `['<missing>']`
- World tail:
  - line 7404: world-defer-forced-fallback-scene-bridge  reason=accepted-ready-before-hold-clear
  - line 7405: world-defer-forced-fallback-light-tail-pre-hold  reason=accepted-ready-before-hold-clear
  - line 7406: world-defer-forced-fallback-completion-structure  reason=accepted-ready-before-hold-clear
  - line 7407: world-defer-forced-fallback-deferred-completion-scripts  reason=accepted-ready-before-hold-clear
  - line 7409: world-skip-prime-forced-fallback-pre-deferred-families  reason=already-primed
  - line 7410: world-hold-post-initial-sync
  - line 7412: world-hold-keepalive  reason=forced-map-build-fallback
  - line 7413: world-skip-hold-sync  reason=forced-map-build-fallback-post-prime
  - line 7414: world-channel-inactive interfaces
  - line 7415: world-added
- Server raw tail:
  - line 7364: send-raw interfaces opcode=45 bytes=5
  - line 7365: send-raw interfaces opcode=141 bytes=15
  - line 7366: send-raw interfaces opcode=141 bytes=15
  - line 7384: send-raw interfaces opcode=28 bytes=2
  - line 7387: send-raw interfaces opcode=42 bytes=64
  - line 7391: send-raw interfaces opcode=28 bytes=2
  - line 7394: send-raw interfaces opcode=42 bytes=64
  - line 7397: send-raw interfaces opcode=131 bytes=0
  - line 7408: send-raw interfaces opcode=131 bytes=0
  - line 7411: send-raw interfaces opcode=131 bytes=0
- Client raw tail:
  - line 7335: recv-raw rebuild opcode=0 bytes=1291

### Signature 2

- Attempts: `[1, 3, 9]`
- Outcomes: `['interfaces-loopback']`
- Disconnect stages: `['interfaces']`
- Content labels: `['<missing>']`
- World tail:
  - line 7316: world-defer-forced-fallback-scene-bridge  reason=accepted-ready-before-hold-clear
  - line 7317: world-defer-forced-fallback-light-tail-pre-hold  reason=accepted-ready-before-hold-clear
  - line 7318: world-defer-forced-fallback-completion-structure  reason=accepted-ready-before-hold-clear
  - line 7319: world-defer-forced-fallback-deferred-completion-scripts  reason=accepted-ready-before-hold-clear
  - line 7320: world-skip-prime-forced-fallback-pre-deferred-families  reason=already-primed
  - line 7321: world-hold-post-initial-sync
  - line 7323: world-hold-keepalive  reason=forced-map-build-fallback
  - line 7324: world-skip-hold-sync  reason=forced-map-build-fallback-post-prime
  - line 7325: world-channel-inactive interfaces
  - line 7326: world-added
- Server raw tail:
  - line 7275: send-raw interfaces opcode=57 bytes=36
  - line 7276: send-raw interfaces opcode=45 bytes=5
  - line 7277: send-raw interfaces opcode=141 bytes=15
  - line 7278: send-raw interfaces opcode=141 bytes=15
  - line 7296: send-raw interfaces opcode=28 bytes=2
  - line 7299: send-raw interfaces opcode=42 bytes=64
  - line 7303: send-raw interfaces opcode=28 bytes=2
  - line 7306: send-raw interfaces opcode=42 bytes=64
  - line 7309: send-raw interfaces opcode=131 bytes=0
  - line 7322: send-raw interfaces opcode=131 bytes=0
- Client raw tail:
  - line 7248: recv-raw rebuild opcode=0 bytes=1291

### Signature 3

- Attempts: `[10]`
- Outcomes: `['interfaces-loopback']`
- Disconnect stages: `['interfaces']`
- Content labels: `['<missing>']`
- World tail:
  - line 8115: world-defer-forced-fallback-light-tail-pre-hold  reason=accepted-ready-before-hold-clear
  - line 8116: world-defer-forced-fallback-completion-structure  reason=accepted-ready-before-hold-clear
  - line 8117: world-defer-forced-fallback-deferred-completion-scripts  reason=accepted-ready-before-hold-clear
  - line 8119: world-skip-prime-forced-fallback-pre-deferred-families  reason=already-primed
  - line 8120: world-hold-post-initial-sync
  - line 8122: world-hold-keepalive  reason=forced-map-build-fallback
  - line 8123: world-skip-hold-sync  reason=forced-map-build-fallback-post-prime
  - line 8124: world-channel-inactive interfaces
  - line 9570: world-channel-inactive social-state
  - line 9571: world-added
- Server raw tail:
  - line 9560: send-raw child-interfaces opcode=38 bytes=23
  - line 9561: send-raw child-interfaces opcode=38 bytes=23
  - line 9562: send-raw child-interfaces opcode=38 bytes=23
  - line 9563: send-raw child-interfaces opcode=38 bytes=23
  - line 9564: send-raw child-interfaces opcode=38 bytes=23
  - line 9565: send-raw child-interfaces opcode=38 bytes=23
  - line 9566: send-raw child-interfaces opcode=38 bytes=23
  - line 9567: send-raw child-interfaces opcode=38 bytes=23
  - line 9568: send-raw social-state opcode=131 bytes=0
  - line 9569: send-raw social-state opcode=131 bytes=0
- Client raw tail:
  - line 8045: recv-raw rebuild opcode=0 bytes=1291

### Signature 4

- Attempts: `[12]`
- Outcomes: `['interfaces-loopback']`
- Disconnect stages: `['interfaces']`
- Content labels: `['<missing>']`
- World tail:
  - line 11521: world-send-deferred-completion-tail
  - line 11523: world-send-deferred-default-varps
  - line 11524: world-queued-deferred-default-varps
  - line 11525: world-arm-scene-start-sync-burst  reason=late-default-varps-prime
  - line 11527: world-prime-late-default-varps-keepalive
  - line 11528: world-prime-late-default-varps-followup-sync
  - line 11529: world-sync-frame  reason=late-default-varps-prime
  - line 11530: world-send-npc-info  opcode=28 bytes=2 reason=late-default-varps-prime
  - line 11532: world-force-local-appearance  reason=late-default-varps-prime
  - line 11533: world-send-player-info  opcode=42 bytes=64 reason=late-default-varps-prime
- Server raw tail:
  - line 11667: send-raw late-default-varps opcode=72 bytes=3
  - line 11668: send-raw late-default-varps opcode=72 bytes=3
  - line 11669: send-raw late-default-varps opcode=72 bytes=3
  - line 11670: send-raw late-default-varps opcode=72 bytes=3
  - line 11671: send-raw late-default-varps opcode=72 bytes=3
  - line 11672: send-raw late-default-varps opcode=72 bytes=3
  - line 11673: send-raw late-default-varps opcode=72 bytes=3
  - line 11674: send-raw late-default-varps opcode=72 bytes=3
  - line 11675: send-raw late-default-varps opcode=72 bytes=3
  - line 11676: send-raw
- Client raw tail:
  - line 11269: recv-raw rebuild opcode=0 bytes=1291

### Signature 5

- Attempts: `[11]`
- Outcomes: `['interfaces-loopback']`
- Disconnect stages: `['interfaces']`
- Content labels: `['<missing>']`
- World tail:
  - line 11240: world-force-local-appearance  reason=scene-start-nudge
  - line 11241: world-send-player-info  opcode=42 bytes=64 reason=scene-start-nudge
  - line 11243: world-send-scene-start-sync-burst
  - line 11244: world-sync-frame  reason=scene-start-nudge
  - line 11245: world-send-npc-info  opcode=28 bytes=2 reason=scene-start-nudge
  - line 11247: world-force-local-appearance  reason=scene-start-nudge
  - line 11248: world-send-player-info  opcode=42 bytes=64 reason=scene-start-nudge
  - line 11250: world-send-scene-start-sync-burst
  - line 11259: world-channel-inactive late-default-varps
  - line 11260: world-added
- Server raw tail:
  - line 11246: send-raw late-default-varps opcode=28 bytes=2
  - line 11249: send-raw late-default-varps opcode=42 bytes=64
  - line 11251: send-raw late-default-varps opcode=28 bytes=2
  - line 11252: send-raw late-default-varps opcode=42 bytes=3
  - line 11253: send-raw late-default-varps opcode=28 bytes=2
  - line 11254: send-raw late-default-varps opcode=42 bytes=3
  - line 11255: send-raw late-default-varps opcode=28 bytes=2
  - line 11256: send-raw late-default-varps opcode=42 bytes=3
  - line 11257: send-raw late-default-varps opcode=28 bytes=2
  - line 11258: send-raw late-default-varps opcode=42 bytes=3
- Client raw tail:
  - line 9580: recv-raw rebuild opcode=48 bytes=105
  - line 9581: recv-raw rebuild opcode=0 bytes=1291

### Signature 6

- Attempts: `[6]`
- Outcomes: `['interfaces-loopback']`
- Disconnect stages: `['interfaces']`
- Content labels: `['<missing>']`
- World tail:
  - line 7761: world-defer-forced-fallback-light-tail-pre-hold  reason=accepted-ready-before-hold-clear
  - line 7762: world-defer-forced-fallback-completion-structure  reason=accepted-ready-before-hold-clear
  - line 7763: world-defer-forced-fallback-deferred-completion-scripts  reason=accepted-ready-before-hold-clear
  - line 7764: world-ignore-client-compat  opcode=83 bytes=1
  - line 7765: world-skip-prime-forced-fallback-pre-deferred-families  reason=already-primed
  - line 7766: world-hold-post-initial-sync
  - line 7768: world-hold-keepalive  reason=forced-map-build-fallback
  - line 7769: world-skip-hold-sync  reason=forced-map-build-fallback-post-prime
  - line 7770: world-channel-inactive interfaces
  - line 7771: world-added
- Server raw tail:
  - line 7719: send-raw interfaces opcode=57 bytes=36
  - line 7720: send-raw interfaces opcode=45 bytes=5
  - line 7721: send-raw interfaces opcode=141 bytes=15
  - line 7722: send-raw interfaces opcode=141 bytes=15
  - line 7740: send-raw interfaces opcode=28 bytes=2
  - line 7743: send-raw interfaces opcode=42 bytes=64
  - line 7747: send-raw interfaces opcode=28 bytes=2
  - line 7750: send-raw interfaces opcode=42 bytes=64
  - line 7753: send-raw interfaces opcode=131 bytes=0
  - line 7767: send-raw interfaces opcode=131 bytes=0
- Client raw tail:
  - line 7689: recv-raw rebuild opcode=83 bytes=1
  - line 7690: recv-raw rebuild opcode=0 bytes=1291
  - line 7691: recv-raw rebuild opcode=83 bytes=1

## Attempts

### Attempt 1

- Outcome: `interfaces-loopback`
- Disconnect stage: `interfaces`
- Paired content: `<missing>` archives=`0` refTables=`0`
- Paired raw login bytes: `0->0`
- Tail signature: `{"client":["recv-raw:0"],"server":["send-raw:57","send-raw:45","send-raw:141","send-raw:141","send-raw:28","send-raw:42","send-raw:28","send-raw:42","send-raw:131","send-raw:131"],"world":["world-defer-forced-fallback-scene-bridge:accepted-ready-before-hold-clear","world-defer-forced-fallback-light-tail-pre-hold:accepted-ready-before-hold-clear","world-defer-forced-fallback-completion-structure:accepted-ready-before-hold-clear","world-defer-forced-fallback-deferred-completion-scripts:accepted-ready-before-hold-clear","world-skip-prime-forced-fallback-pre-deferred-families:already-primed","world-hold-post-initial-sync","world-hold-keepalive:forced-map-build-fallback","world-skip-hold-sync:forced-map-build-fallback-post-prime","world-channel-inactive","world-added"]}`

### Attempt 2

- Outcome: `interfaces-loopback`
- Disconnect stage: `interfaces`
- Paired content: `<missing>` archives=`0` refTables=`0`
- Paired raw login bytes: `0->0`
- Tail signature: `{"client":["recv-raw:0"],"server":["send-raw:45","send-raw:141","send-raw:141","send-raw:28","send-raw:42","send-raw:28","send-raw:42","send-raw:131","send-raw:131","send-raw:131"],"world":["world-defer-forced-fallback-scene-bridge:accepted-ready-before-hold-clear","world-defer-forced-fallback-light-tail-pre-hold:accepted-ready-before-hold-clear","world-defer-forced-fallback-completion-structure:accepted-ready-before-hold-clear","world-defer-forced-fallback-deferred-completion-scripts:accepted-ready-before-hold-clear","world-skip-prime-forced-fallback-pre-deferred-families:already-primed","world-hold-post-initial-sync","world-hold-keepalive:forced-map-build-fallback","world-skip-hold-sync:forced-map-build-fallback-post-prime","world-channel-inactive","world-added"]}`

### Attempt 3

- Outcome: `interfaces-loopback`
- Disconnect stage: `interfaces`
- Paired content: `<missing>` archives=`0` refTables=`0`
- Paired raw login bytes: `0->0`
- Tail signature: `{"client":["recv-raw:0"],"server":["send-raw:57","send-raw:45","send-raw:141","send-raw:141","send-raw:28","send-raw:42","send-raw:28","send-raw:42","send-raw:131","send-raw:131"],"world":["world-defer-forced-fallback-scene-bridge:accepted-ready-before-hold-clear","world-defer-forced-fallback-light-tail-pre-hold:accepted-ready-before-hold-clear","world-defer-forced-fallback-completion-structure:accepted-ready-before-hold-clear","world-defer-forced-fallback-deferred-completion-scripts:accepted-ready-before-hold-clear","world-skip-prime-forced-fallback-pre-deferred-families:already-primed","world-hold-post-initial-sync","world-hold-keepalive:forced-map-build-fallback","world-skip-hold-sync:forced-map-build-fallback-post-prime","world-channel-inactive","world-added"]}`

### Attempt 4

- Outcome: `interfaces-loopback`
- Disconnect stage: `interfaces`
- Paired content: `<missing>` archives=`0` refTables=`0`
- Paired raw login bytes: `0->0`
- Tail signature: `{"client":["recv-raw:0"],"server":["send-raw:45","send-raw:141","send-raw:141","send-raw:28","send-raw:42","send-raw:28","send-raw:42","send-raw:131","send-raw:131","send-raw:131"],"world":["world-defer-forced-fallback-scene-bridge:accepted-ready-before-hold-clear","world-defer-forced-fallback-light-tail-pre-hold:accepted-ready-before-hold-clear","world-defer-forced-fallback-completion-structure:accepted-ready-before-hold-clear","world-defer-forced-fallback-deferred-completion-scripts:accepted-ready-before-hold-clear","world-skip-prime-forced-fallback-pre-deferred-families:already-primed","world-hold-post-initial-sync","world-hold-keepalive:forced-map-build-fallback","world-skip-hold-sync:forced-map-build-fallback-post-prime","world-channel-inactive","world-added"]}`

### Attempt 5

- Outcome: `interfaces-loopback`
- Disconnect stage: `interfaces`
- Paired content: `<missing>` archives=`0` refTables=`0`
- Paired raw login bytes: `0->0`
- Tail signature: `{"client":["recv-raw:0"],"server":["send-raw:45","send-raw:141","send-raw:141","send-raw:28","send-raw:42","send-raw:28","send-raw:42","send-raw:131","send-raw:131","send-raw:131"],"world":["world-defer-forced-fallback-scene-bridge:accepted-ready-before-hold-clear","world-defer-forced-fallback-light-tail-pre-hold:accepted-ready-before-hold-clear","world-defer-forced-fallback-completion-structure:accepted-ready-before-hold-clear","world-defer-forced-fallback-deferred-completion-scripts:accepted-ready-before-hold-clear","world-skip-prime-forced-fallback-pre-deferred-families:already-primed","world-hold-post-initial-sync","world-hold-keepalive:forced-map-build-fallback","world-skip-hold-sync:forced-map-build-fallback-post-prime","world-channel-inactive","world-added"]}`

### Attempt 6

- Outcome: `interfaces-loopback`
- Disconnect stage: `interfaces`
- Paired content: `<missing>` archives=`0` refTables=`0`
- Paired raw login bytes: `0->0`
- Tail signature: `{"client":["recv-raw:83","recv-raw:0","recv-raw:83"],"server":["send-raw:57","send-raw:45","send-raw:141","send-raw:141","send-raw:28","send-raw:42","send-raw:28","send-raw:42","send-raw:131","send-raw:131"],"world":["world-defer-forced-fallback-light-tail-pre-hold:accepted-ready-before-hold-clear","world-defer-forced-fallback-completion-structure:accepted-ready-before-hold-clear","world-defer-forced-fallback-deferred-completion-scripts:accepted-ready-before-hold-clear","world-ignore-client-compat:83","world-skip-prime-forced-fallback-pre-deferred-families:already-primed","world-hold-post-initial-sync","world-hold-keepalive:forced-map-build-fallback","world-skip-hold-sync:forced-map-build-fallback-post-prime","world-channel-inactive","world-added"]}`

### Attempt 7

- Outcome: `interfaces-loopback`
- Disconnect stage: `interfaces`
- Paired content: `<missing>` archives=`0` refTables=`0`
- Paired raw login bytes: `0->0`
- Tail signature: `{"client":["recv-raw:0"],"server":["send-raw:45","send-raw:141","send-raw:141","send-raw:28","send-raw:42","send-raw:28","send-raw:42","send-raw:131","send-raw:131","send-raw:131"],"world":["world-defer-forced-fallback-scene-bridge:accepted-ready-before-hold-clear","world-defer-forced-fallback-light-tail-pre-hold:accepted-ready-before-hold-clear","world-defer-forced-fallback-completion-structure:accepted-ready-before-hold-clear","world-defer-forced-fallback-deferred-completion-scripts:accepted-ready-before-hold-clear","world-skip-prime-forced-fallback-pre-deferred-families:already-primed","world-hold-post-initial-sync","world-hold-keepalive:forced-map-build-fallback","world-skip-hold-sync:forced-map-build-fallback-post-prime","world-channel-inactive","world-added"]}`

### Attempt 8

- Outcome: `interfaces-loopback`
- Disconnect stage: `interfaces`
- Paired content: `<missing>` archives=`0` refTables=`0`
- Paired raw login bytes: `0->0`
- Tail signature: `{"client":["recv-raw:0"],"server":["send-raw:45","send-raw:141","send-raw:141","send-raw:28","send-raw:42","send-raw:28","send-raw:42","send-raw:131","send-raw:131","send-raw:131"],"world":["world-defer-forced-fallback-scene-bridge:accepted-ready-before-hold-clear","world-defer-forced-fallback-light-tail-pre-hold:accepted-ready-before-hold-clear","world-defer-forced-fallback-completion-structure:accepted-ready-before-hold-clear","world-defer-forced-fallback-deferred-completion-scripts:accepted-ready-before-hold-clear","world-skip-prime-forced-fallback-pre-deferred-families:already-primed","world-hold-post-initial-sync","world-hold-keepalive:forced-map-build-fallback","world-skip-hold-sync:forced-map-build-fallback-post-prime","world-channel-inactive","world-added"]}`

### Attempt 9

- Outcome: `interfaces-loopback`
- Disconnect stage: `interfaces`
- Paired content: `<missing>` archives=`0` refTables=`0`
- Paired raw login bytes: `0->0`
- Tail signature: `{"client":["recv-raw:0"],"server":["send-raw:57","send-raw:45","send-raw:141","send-raw:141","send-raw:28","send-raw:42","send-raw:28","send-raw:42","send-raw:131","send-raw:131"],"world":["world-defer-forced-fallback-scene-bridge:accepted-ready-before-hold-clear","world-defer-forced-fallback-light-tail-pre-hold:accepted-ready-before-hold-clear","world-defer-forced-fallback-completion-structure:accepted-ready-before-hold-clear","world-defer-forced-fallback-deferred-completion-scripts:accepted-ready-before-hold-clear","world-skip-prime-forced-fallback-pre-deferred-families:already-primed","world-hold-post-initial-sync","world-hold-keepalive:forced-map-build-fallback","world-skip-hold-sync:forced-map-build-fallback-post-prime","world-channel-inactive","world-added"]}`

### Attempt 10

- Outcome: `interfaces-loopback`
- Disconnect stage: `interfaces`
- Paired content: `<missing>` archives=`0` refTables=`0`
- Paired raw login bytes: `0->0`
- Tail signature: `{"client":["recv-raw:0"],"server":["send-raw:38","send-raw:38","send-raw:38","send-raw:38","send-raw:38","send-raw:38","send-raw:38","send-raw:38","send-raw:131","send-raw:131"],"world":["world-defer-forced-fallback-light-tail-pre-hold:accepted-ready-before-hold-clear","world-defer-forced-fallback-completion-structure:accepted-ready-before-hold-clear","world-defer-forced-fallback-deferred-completion-scripts:accepted-ready-before-hold-clear","world-skip-prime-forced-fallback-pre-deferred-families:already-primed","world-hold-post-initial-sync","world-hold-keepalive:forced-map-build-fallback","world-skip-hold-sync:forced-map-build-fallback-post-prime","world-channel-inactive","world-channel-inactive","world-added"]}`

### Attempt 11

- Outcome: `interfaces-loopback`
- Disconnect stage: `interfaces`
- Paired content: `<missing>` archives=`0` refTables=`0`
- Paired raw login bytes: `0->0`
- Tail signature: `{"client":["recv-raw:48","recv-raw:0"],"server":["send-raw:28","send-raw:42","send-raw:28","send-raw:42","send-raw:28","send-raw:42","send-raw:28","send-raw:42","send-raw:28","send-raw:42"],"world":["world-force-local-appearance:scene-start-nudge","world-send-player-info:42","world-send-scene-start-sync-burst","world-sync-frame:scene-start-nudge","world-send-npc-info:28","world-force-local-appearance:scene-start-nudge","world-send-player-info:42","world-send-scene-start-sync-burst","world-channel-inactive","world-added"]}`

### Attempt 12

- Outcome: `interfaces-loopback`
- Disconnect stage: `interfaces`
- Paired content: `<missing>` archives=`0` refTables=`0`
- Paired raw login bytes: `0->0`
- Tail signature: `{"client":["recv-raw:0"],"server":["send-raw:72","send-raw:72","send-raw:72","send-raw:72","send-raw:72","send-raw:72","send-raw:72","send-raw:72","send-raw:72","send-raw"],"world":["world-send-deferred-completion-tail","world-send-deferred-default-varps","world-queued-deferred-default-varps","world-arm-scene-start-sync-burst:late-default-varps-prime","world-prime-late-default-varps-keepalive","world-prime-late-default-varps-followup-sync","world-sync-frame:late-default-varps-prime","world-send-npc-info:28","world-force-local-appearance:late-default-varps-prime","world-send-player-info:42"]}`
