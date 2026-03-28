# 946 Scene Start Doctor

- Status: `ok`
- Cluster id: `20260321-093106`
- Attempts analyzed: `12`
- Latest likely blocker: `region-advertised-too-late`
- Latest rebuild before first 50/82/50 burst: `False`
- Latest close-loading-overlay present: `True`
- Latest content first request: `reference-table[0]`
- Latest archive requests: `0`

## Verdict

- Recommendation: Client bootstrap controls start before the server has clearly advertised the rebuild/region payload, so the scene start may still be racing the world handoff.

## Exact Needs

- first non-reference /ms archive request after reference-table[0]
- post-ready client 17/83 signal capture to confirm the plateau stays alive after world sync

## Attempts

### Attempt 1

- Likely blocker: `accepted-ready-overlay-not-closed`
- World window: `7327:7415`
- Rebuild line: `7331`
- Ready line: `7378`
- Close loading overlay line: `None`
- Rebuild before ready: `True`
- Rebuild before bootstrap controls: `False`
- Control burst: `[]`
- Post-ready client signals: `[]`
- Content first request: ``
- Reference table requests: `0`
- Archive requests: `0`
- Content response bytes: `0`
- Needs: explicit loading-overlay close on the accepted-ready minimal branch
- Needs: post-ready client 17/83 signal capture to confirm the plateau stays alive after world sync

### Attempt 2

- Likely blocker: `accepted-ready-overlay-not-closed`
- World window: `7416:7502`
- Rebuild line: `7420`
- Ready line: `7466`
- Close loading overlay line: `None`
- Rebuild before ready: `True`
- Rebuild before bootstrap controls: `False`
- Control burst: `[]`
- Post-ready client signals: `[]`
- Content first request: ``
- Reference table requests: `0`
- Archive requests: `0`
- Content response bytes: `0`
- Needs: explicit loading-overlay close on the accepted-ready minimal branch
- Needs: post-ready client 17/83 signal capture to confirm the plateau stays alive after world sync

### Attempt 3

- Likely blocker: `accepted-ready-overlay-not-closed`
- World window: `7503:7591`
- Rebuild line: `7507`
- Ready line: `7554`
- Close loading overlay line: `None`
- Rebuild before ready: `True`
- Rebuild before bootstrap controls: `False`
- Control burst: `[]`
- Post-ready client signals: `[]`
- Content first request: `reference-table[0]`
- Reference table requests: `1`
- Archive requests: `0`
- Content response bytes: `4191`
- Needs: explicit loading-overlay close on the accepted-ready minimal branch
- Needs: first non-reference /ms archive request after reference-table[0]
- Needs: post-ready client 17/83 signal capture to confirm the plateau stays alive after world sync

### Attempt 4

- Likely blocker: `accepted-ready-overlay-not-closed`
- World window: `7592:7680`
- Rebuild line: `7596`
- Ready line: `7643`
- Close loading overlay line: `None`
- Rebuild before ready: `True`
- Rebuild before bootstrap controls: `False`
- Control burst: `[]`
- Post-ready client signals: `[]`
- Content first request: `reference-table[0]`
- Reference table requests: `1`
- Archive requests: `0`
- Content response bytes: `4191`
- Needs: explicit loading-overlay close on the accepted-ready minimal branch
- Needs: first non-reference /ms archive request after reference-table[0]
- Needs: post-ready client 17/83 signal capture to confirm the plateau stays alive after world sync

### Attempt 5

- Likely blocker: `accepted-ready-overlay-not-closed`
- World window: `7681:7771`
- Rebuild line: `7685`
- Ready line: `7734`
- Close loading overlay line: `None`
- Rebuild before ready: `True`
- Rebuild before bootstrap controls: `False`
- Control burst: `[]`
- Post-ready client signals: `[{'kind': 'world-ignore-client-compat', 'opcode': 83, 'lineNumber': 7764, 'bytes': 1, 'preview': '00'}]`
- Content first request: `reference-table[0]`
- Reference table requests: `1`
- Archive requests: `0`
- Content response bytes: `4191`
- Needs: explicit loading-overlay close on the accepted-ready minimal branch
- Needs: first non-reference /ms archive request after reference-table[0]

### Attempt 6

- Likely blocker: `accepted-ready-overlay-not-closed`
- World window: `7772:7860`
- Rebuild line: `7776`
- Ready line: `7823`
- Close loading overlay line: `None`
- Rebuild before ready: `True`
- Rebuild before bootstrap controls: `False`
- Control burst: `[]`
- Post-ready client signals: `[]`
- Content first request: `reference-table[0]`
- Reference table requests: `1`
- Archive requests: `0`
- Content response bytes: `4191`
- Needs: explicit loading-overlay close on the accepted-ready minimal branch
- Needs: first non-reference /ms archive request after reference-table[0]
- Needs: post-ready client 17/83 signal capture to confirm the plateau stays alive after world sync

### Attempt 7

- Likely blocker: `accepted-ready-overlay-not-closed`
- World window: `7861:7949`
- Rebuild line: `7865`
- Ready line: `7912`
- Close loading overlay line: `None`
- Rebuild before ready: `True`
- Rebuild before bootstrap controls: `False`
- Control burst: `[]`
- Post-ready client signals: `[]`
- Content first request: `reference-table[0]`
- Reference table requests: `1`
- Archive requests: `0`
- Content response bytes: `4191`
- Needs: explicit loading-overlay close on the accepted-ready minimal branch
- Needs: first non-reference /ms archive request after reference-table[0]
- Needs: post-ready client 17/83 signal capture to confirm the plateau stays alive after world sync

### Attempt 8

- Likely blocker: `accepted-ready-overlay-not-closed`
- World window: `7950:8036`
- Rebuild line: `7954`
- Ready line: `8000`
- Close loading overlay line: `None`
- Rebuild before ready: `True`
- Rebuild before bootstrap controls: `False`
- Control burst: `[]`
- Post-ready client signals: `[]`
- Content first request: `reference-table[0]`
- Reference table requests: `1`
- Archive requests: `0`
- Content response bytes: `4191`
- Needs: explicit loading-overlay close on the accepted-ready minimal branch
- Needs: first non-reference /ms archive request after reference-table[0]
- Needs: post-ready client 17/83 signal capture to confirm the plateau stays alive after world sync

### Attempt 9

- Likely blocker: `accepted-ready-overlay-not-closed`
- World window: `8037:9571`
- Rebuild line: `8041`
- Ready line: `8088`
- Close loading overlay line: `None`
- Rebuild before ready: `True`
- Rebuild before bootstrap controls: `False`
- Control burst: `[]`
- Post-ready client signals: `[]`
- Content first request: `reference-table[0]`
- Reference table requests: `1`
- Archive requests: `0`
- Content response bytes: `4191`
- Needs: explicit loading-overlay close on the accepted-ready minimal branch
- Needs: first non-reference /ms archive request after reference-table[0]
- Needs: post-ready client 17/83 signal capture to confirm the plateau stays alive after world sync

### Attempt 10

- Likely blocker: `region-advertised-too-late`
- World window: `9572:11260`
- Rebuild line: `9576`
- Ready line: `9623`
- Close loading overlay line: `9660`
- Rebuild before ready: `True`
- Rebuild before bootstrap controls: `False`
- Control burst: `[]`
- Post-ready client signals: `[]`
- Content first request: `reference-table[0]`
- Reference table requests: `1`
- Archive requests: `0`
- Content response bytes: `4191`
- Needs: first non-reference /ms archive request after reference-table[0]
- Needs: post-ready client 17/83 signal capture to confirm the plateau stays alive after world sync

### Attempt 11

- Likely blocker: `region-advertised-too-late`
- World window: `11261:12947`
- Rebuild line: `11265`
- Ready line: `11312`
- Close loading overlay line: `11350`
- Rebuild before ready: `True`
- Rebuild before bootstrap controls: `False`
- Control burst: `[]`
- Post-ready client signals: `[]`
- Content first request: `reference-table[0]`
- Reference table requests: `1`
- Archive requests: `0`
- Content response bytes: `4191`
- Needs: first non-reference /ms archive request after reference-table[0]
- Needs: post-ready client 17/83 signal capture to confirm the plateau stays alive after world sync

### Attempt 12

- Likely blocker: `region-advertised-too-late`
- World window: `12948:14415`
- Rebuild line: `12952`
- Ready line: `12999`
- Close loading overlay line: `13037`
- Rebuild before ready: `True`
- Rebuild before bootstrap controls: `False`
- Control burst: `[]`
- Post-ready client signals: `[]`
- Content first request: `reference-table[0]`
- Reference table requests: `1`
- Archive requests: `0`
- Content response bytes: `4191`
- Needs: first non-reference /ms archive request after reference-table[0]
- Needs: post-ready client 17/83 signal capture to confirm the plateau stays alive after world sync
