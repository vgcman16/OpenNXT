# 946 Scene Delivery Aid

- Status: `ok`
- World session present: `True`
- Relevant JS5 sessions: `1`
- Overlap confidence: `fallback`
- Selected capture format: `content-proxy`
- Scene delivery state: `reference-tables-only`
- Archive requests observed: `0`
- Response headers observed: `2`
- Response bytes observed: `4191`
- Truncated archive sessions: `0`
- Capture bundle present: `True`
- Live watcher present: `True`

## Verdict

- Likely blocker: `reference-tables-only`
- Recommendation: The client reached JS5 bootstrap but never progressed beyond reference tables. Focus on scene/prefetch gating and the first asset-delivery transition after rebuild.

## Delivery Answers

- Overlapping content capture matched: `True`
- Client requested real archives: `False`
- Server sent response headers back: `True`
- First JS5 request after `world-send-rebuild-tail`: `-4.903` seconds
- First archive request after `world-send-rebuild-tail`: `None` seconds
- First JS5 response after `world-send-rebuild-tail`: `-4.903` seconds
- First archive response after `world-send-rebuild-tail`: `None` seconds

## World Timeline

- `stage:appearance` t+`0.0`s
- `stage:login-response` t+`0.258`s
- `stage:pipeline-switch` t+`0.26`s
- `stage:rebuild` t+`0.263`s
- `world-send-rebuild-tail` t+`0.272`s {
  "areaType": "474",
  "chunkX": "402",
  "chunkY": "402",
  "hash1": "-2147483648",
  "hash2": "2147483647",
  "mapSize": "5",
  "name": "demon",
  "npcBits": "7"
}
- `world-waiting-map-build-complete` t+`0.288`s {
  "name": "demon"
}
- `world-client-display-config` t+`0.617`s {
  "awaitingMapBuildComplete": "true",
  "awaitingWorldReadySignal": "false",
  "count": "1",
  "height": "720",
  "mode": "2",
  "name": "demon",
  "opcode": "106",
  "trailingFlag": "0",
  "width": "1280"
}
- `world-ready-signal-latched` t+`0.628`s {
  "bytes": "78",
  "name": "demon",
  "opcode": "48",
  "preview": "0a12ffff026f0213e13b02ae021de04902a4040680321c80",
  "replaced": "-1",
  "source": "live-early"
}
- `world-map-build-complete-compat` t+`0.633`s {
  "bytes": "1291",
  "name": "demon",
  "opcode": "0",
  "preview": "010b2f2936ffff0b30264445350b31ff3728270b32ffffff",
  "source": "serverperm-after-display"
}
- `stage:stats` t+`0.635`s
- `stage:default-state` t+`0.637`s
- `stage:interfaces` t+`0.642`s
- `world-send-minimal-varcs` t+`0.66`s {
  "ids": "181,1027,1034,3497",
  "name": "demon"
}
- `world-awaiting-ready-signal` t+`0.687`s {
  "name": "demon",
  "reason": "forced-map-build-fallback"
}
- `world-ready-signal` t+`0.696`s {
  "bytes": "78",
  "name": "demon",
  "opcode": "48",
  "preview": "0a12ffff026f0213e13b02ae021de04902a4040680321c80",
  "source": "delayed-ready-wait"
}
- `send-raw:PLAYER_INFO` t+`0.719`s bytes=64
- `send-raw:PLAYER_INFO` t+`0.724`s bytes=64
- `world-client-display-config` t+`1.207`s {
  "awaitingMapBuildComplete": "false",
  "awaitingWorldReadySignal": "false",
  "count": "2",
  "height": "720",
  "mode": "2",
  "name": "demon",
  "opcode": "106",
  "trailingFlag": "0",
  "width": "1280"
}

## Capture Sessions

- `session-07-20260322-012001.log` format=`content-proxy` state=`reference-tables-only` requests=`1` archiveRequests=`0` responseHeaders=`2` responseBytes=`4191`

## Runtime Trace

- File: `rs2client-stuck-20260312-1235.jsonl` samples=`3` timeouts=`1` ports=`[443]`

## Capture Bundle

- Status: `partial`
- Status reason: `overlap-missing`
- World window selected: `1027327:1049489`
- Overlap achieved: `False`
- Canonical MITM launch: `False`
- hostRewrite: `0`
- lobbyHostRewrite: ``
- contentRouteRewrite: ``
- contentRouteMode: `disabled`
- Fresh local TLS sessions: `0`
- Local `/ms` observed: `False`
- Local MITM `:443` connections: `0`
- Direct external `:443` connections: `0`
- JS5 summary: ``
- Content capture: ``
- Runtime trace: `C:\Users\Demon\Documents\New project\OpenNXT\data\debug\runtime-trace\black-screen-runtime-20260316-224544.jsonl`

## Live Watch

- Terminal state: `black-screen-plateau`
- Deep hooks enabled: `True`
- Local content MITM observed: `True`
- First archive request seconds: `None`
- First archive response seconds: `None`
