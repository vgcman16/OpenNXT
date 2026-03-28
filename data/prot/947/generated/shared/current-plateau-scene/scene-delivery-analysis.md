# 946 Scene Delivery Aid

- Status: `ok`
- World session present: `True`
- Relevant JS5 sessions: `1`
- Overlap confidence: `fallback`
- Selected capture format: `content-proxy`
- Scene delivery state: `content-proxy-no-response`
- Archive requests observed: `0`
- Response headers observed: `0`
- Response bytes observed: `0`
- Capture bundle present: `True`

## Verdict

- Likely blocker: `content-proxy-no-response`
- Recommendation: The content MITM path forwarded HTTPS content requests into the local JS5 recorder at `127.0.0.1:43595` and got no response bytes. Use direct TLS MITM relay or an HTTP-aware recorder for content capture instead of the JS5 proxy.

## Delivery Answers

- Overlapping content capture matched: `True`
- Client requested real archives: `False`
- Server sent response headers back: `False`
- First JS5 request after `world-send-rebuild-tail`: `-522.184` seconds
- First archive request after `world-send-rebuild-tail`: `None` seconds
- First JS5 response after `world-send-rebuild-tail`: `None` seconds
- First archive response after `world-send-rebuild-tail`: `None` seconds

## World Timeline

- `stage:appearance` t+`2075.85`s
- `stage:login-response` t+`2075.937`s
- `stage:pipeline-switch` t+`2075.941`s
- `stage:rebuild` t+`2075.944`s
- `world-send-rebuild-tail` t+`2075.953`s {
  "areaType": "0",
  "chunkX": "402",
  "chunkY": "402",
  "hash1": "0",
  "hash2": "0",
  "mapSize": "5",
  "name": "demon",
  "npcBits": "7"
}
- `world-waiting-map-build-complete` t+`2075.964`s {
  "name": "demon"
}
- `world-client-display-config` t+`2076.451`s {
  "awaitingMapBuildComplete": "true",
  "awaitingWorldReadySignal": "false",
  "count": "1",
  "height": "720",
  "mode": "2",
  "name": "demon",
  "opcode": "106",
  "trailingFlag": "2",
  "width": "1280"
}
- `world-ready-signal-latched` t+`2076.459`s {
  "bytes": "246",
  "name": "demon",
  "opcode": "48",
  "preview": "0758ffff002c0457e02600290454071c079d06dd06da0699"
}
- `world-ready-signal-latched` t+`2076.47`s {
  "bytes": "103",
  "name": "demon",
  "opcode": "48",
  "preview": "0a2b1822086118610821907f7f075c071d05d80518065b04"
}
- `world-map-build-complete-compat` t+`2076.476`s {
  "bytes": "4",
  "name": "demon",
  "opcode": "113",
  "preview": "000000e4"
}
- `stage:stats` t+`2076.479`s
- `stage:default-state` t+`2076.483`s
- `stage:interfaces` t+`2076.49`s
- `world-send-minimal-varcs` t+`2076.526`s {
  "ids": "181,1027,1034,3497",
  "name": "demon"
}
- `world-awaiting-ready-signal` t+`2076.533`s {
  "name": "demon"
}
- `world-ready-signal` t+`2076.537`s {
  "bytes": "103",
  "name": "demon",
  "opcode": "48",
  "preview": "0a2b1822086118610821907f7f075c071d05d80518065b04",
  "source": "latched"
}
- `send-raw:PLAYER_INFO` t+`2076.557`s bytes=64
- `world-client-display-config` t+`2077.049`s {
  "awaitingMapBuildComplete": "false",
  "awaitingWorldReadySignal": "false",
  "count": "2",
  "height": "720",
  "mode": "2",
  "name": "demon",
  "opcode": "106",
  "trailingFlag": "2",
  "width": "1280"
}

## Capture Sessions

- `session-35-20260316-230400.log` format=`content-proxy` state=`reference-tables-only` requests=`1` archiveRequests=`0` responseHeaders=`0`

## Runtime Trace

- File: `rs2client-stuck-20260312-1235.jsonl` samples=`3` timeouts=`1` ports=`[443]`

## Capture Bundle

- Status: `partial`
- World window selected: `1027327:1049489`
- Overlap achieved: `False`
- JS5 summary: ``
- Content capture: ``
- Runtime trace: `C:\Users\Demon\Documents\New project\OpenNXT\data\debug\runtime-trace\black-screen-runtime-20260316-224544.jsonl`
