# 946 Post-Ready Cadence Doctor

- Status: `ok`
- Cluster id: `20260322-185544`
- Attempts analyzed: `12`
- Accepted-ready attempts: `12`
- Max tick PLAYER_INFO frames after ready: `0`
- Max NO_TIMEOUT packets after ready: `5`
- Accepted-ready attempts with scene archives: `0`

## Verdict

- Likely blocker: `post-ready-no-scene-archives`
- Recommendation: Accepted-ready attempts stay alive longer, but they still never transition into real scene archive delivery after reference-table[0].

## Exact Needs

- accepted ready at line 68812, then only 0 tick PLAYER_INFO frame before the attempt ended
- accepted ready never reached a real scene archive request; keep the world channel alive past reference-table[0]
- accepted ready clears into the deferred completion tail, but the cadence stops after the first tick follow-up

## Attempts

### Attempt 1

- Accepted ready: `True`
- Accepted ready line: `50156`
- Ready source: `latched-post-bootstrap`
- World sync frames after ready: `[1, 2, 3, 4, 5]`
- Tick PLAYER_INFO frames after ready: `[]`
- NO_TIMEOUT packets after ready: `5`
- PLAYER_INFO packets after ready: `13`
- Deferred tail after ready line: `50196`
- Content label: `` refTables=`0` archives=`0`
- Needs:
  - accepted ready at line 50156, then only 0 tick PLAYER_INFO frame before the attempt ended
  - accepted ready never reached a real scene archive request; keep the world channel alive past reference-table[0]
  - accepted ready clears into the deferred completion tail, but the cadence stops after the first tick follow-up

### Attempt 2

- Accepted ready: `True`
- Accepted ready line: `51856`
- Ready source: `latched-post-bootstrap`
- World sync frames after ready: `[1, 2, 3, 4, 5]`
- Tick PLAYER_INFO frames after ready: `[]`
- NO_TIMEOUT packets after ready: `5`
- PLAYER_INFO packets after ready: `6`
- Deferred tail after ready line: `51896`
- Content label: `` refTables=`0` archives=`0`
- Needs:
  - accepted ready at line 51856, then only 0 tick PLAYER_INFO frame before the attempt ended
  - accepted ready never reached a real scene archive request; keep the world channel alive past reference-table[0]
  - accepted ready clears into the deferred completion tail, but the cadence stops after the first tick follow-up

### Attempt 3

- Accepted ready: `True`
- Accepted ready line: `53540`
- Ready source: `latched-post-bootstrap`
- World sync frames after ready: `[1, 2, 3, 4, 5]`
- Tick PLAYER_INFO frames after ready: `[]`
- NO_TIMEOUT packets after ready: `5`
- PLAYER_INFO packets after ready: `12`
- Deferred tail after ready line: `53579`
- Content label: `` refTables=`0` archives=`0`
- Needs:
  - accepted ready at line 53540, then only 0 tick PLAYER_INFO frame before the attempt ended
  - accepted ready never reached a real scene archive request; keep the world channel alive past reference-table[0]
  - accepted ready clears into the deferred completion tail, but the cadence stops after the first tick follow-up

### Attempt 4

- Accepted ready: `True`
- Accepted ready line: `55237`
- Ready source: `latched-post-bootstrap`
- World sync frames after ready: `[1, 2, 3, 4, 5]`
- Tick PLAYER_INFO frames after ready: `[]`
- NO_TIMEOUT packets after ready: `4`
- PLAYER_INFO packets after ready: `11`
- Deferred tail after ready line: `55276`
- Content label: `reference-table[0]` refTables=`1` archives=`0`
- Needs:
  - accepted ready at line 55237, then only 0 tick PLAYER_INFO frame before the attempt ended
  - accepted ready never reached a real scene archive request; keep the world channel alive past reference-table[0]
  - accepted ready clears into the deferred completion tail, but the cadence stops after the first tick follow-up

### Attempt 5

- Accepted ready: `True`
- Accepted ready line: `56931`
- Ready source: `latched-post-bootstrap`
- World sync frames after ready: `[1, 2, 3, 4, 5]`
- Tick PLAYER_INFO frames after ready: `[]`
- NO_TIMEOUT packets after ready: `5`
- PLAYER_INFO packets after ready: `12`
- Deferred tail after ready line: `56971`
- Content label: `reference-table[0]` refTables=`1` archives=`0`
- Needs:
  - accepted ready at line 56931, then only 0 tick PLAYER_INFO frame before the attempt ended
  - accepted ready never reached a real scene archive request; keep the world channel alive past reference-table[0]
  - accepted ready clears into the deferred completion tail, but the cadence stops after the first tick follow-up

### Attempt 6

- Accepted ready: `True`
- Accepted ready line: `58628`
- Ready source: `latched-post-bootstrap`
- World sync frames after ready: `[1, 2, 3, 4, 5]`
- Tick PLAYER_INFO frames after ready: `[]`
- NO_TIMEOUT packets after ready: `5`
- PLAYER_INFO packets after ready: `12`
- Deferred tail after ready line: `58668`
- Content label: `` refTables=`0` archives=`0`
- Needs:
  - accepted ready at line 58628, then only 0 tick PLAYER_INFO frame before the attempt ended
  - accepted ready never reached a real scene archive request; keep the world channel alive past reference-table[0]
  - accepted ready clears into the deferred completion tail, but the cadence stops after the first tick follow-up

### Attempt 7

- Accepted ready: `True`
- Accepted ready line: `60325`
- Ready source: `latched-post-bootstrap`
- World sync frames after ready: `[1, 2, 3, 4, 5]`
- Tick PLAYER_INFO frames after ready: `[]`
- NO_TIMEOUT packets after ready: `4`
- PLAYER_INFO packets after ready: `10`
- Deferred tail after ready line: `60365`
- Content label: `` refTables=`0` archives=`0`
- Needs:
  - accepted ready at line 60325, then only 0 tick PLAYER_INFO frame before the attempt ended
  - accepted ready never reached a real scene archive request; keep the world channel alive past reference-table[0]
  - accepted ready clears into the deferred completion tail, but the cadence stops after the first tick follow-up

### Attempt 8

- Accepted ready: `True`
- Accepted ready line: `62016`
- Ready source: `latched-post-bootstrap`
- World sync frames after ready: `[1, 2, 3, 4, 5]`
- Tick PLAYER_INFO frames after ready: `[]`
- NO_TIMEOUT packets after ready: `4`
- PLAYER_INFO packets after ready: `10`
- Deferred tail after ready line: `62056`
- Content label: `` refTables=`0` archives=`0`
- Needs:
  - accepted ready at line 62016, then only 0 tick PLAYER_INFO frame before the attempt ended
  - accepted ready never reached a real scene archive request; keep the world channel alive past reference-table[0]
  - accepted ready clears into the deferred completion tail, but the cadence stops after the first tick follow-up

### Attempt 9

- Accepted ready: `True`
- Accepted ready line: `63707`
- Ready source: `latched-post-bootstrap`
- World sync frames after ready: `[1, 2, 3, 4, 5]`
- Tick PLAYER_INFO frames after ready: `[]`
- NO_TIMEOUT packets after ready: `5`
- PLAYER_INFO packets after ready: `16`
- Deferred tail after ready line: `63747`
- Content label: `reference-table[0]` refTables=`1` archives=`0`
- Needs:
  - accepted ready at line 63707, then only 0 tick PLAYER_INFO frame before the attempt ended
  - accepted ready never reached a real scene archive request; keep the world channel alive past reference-table[0]
  - accepted ready clears into the deferred completion tail, but the cadence stops after the first tick follow-up

### Attempt 10

- Accepted ready: `True`
- Accepted ready line: `65414`
- Ready source: `latched-post-bootstrap`
- World sync frames after ready: `[1, 2, 3, 4, 5]`
- Tick PLAYER_INFO frames after ready: `[]`
- NO_TIMEOUT packets after ready: `5`
- PLAYER_INFO packets after ready: `13`
- Deferred tail after ready line: `65453`
- Content label: `` refTables=`0` archives=`0`
- Needs:
  - accepted ready at line 65414, then only 0 tick PLAYER_INFO frame before the attempt ended
  - accepted ready never reached a real scene archive request; keep the world channel alive past reference-table[0]
  - accepted ready clears into the deferred completion tail, but the cadence stops after the first tick follow-up

### Attempt 11

- Accepted ready: `True`
- Accepted ready line: `67114`
- Ready source: `latched-post-bootstrap`
- World sync frames after ready: `[1, 2, 3, 4, 5]`
- Tick PLAYER_INFO frames after ready: `[]`
- NO_TIMEOUT packets after ready: `5`
- PLAYER_INFO packets after ready: `12`
- Deferred tail after ready line: `67153`
- Content label: `` refTables=`0` archives=`0`
- Needs:
  - accepted ready at line 67114, then only 0 tick PLAYER_INFO frame before the attempt ended
  - accepted ready never reached a real scene archive request; keep the world channel alive past reference-table[0]
  - accepted ready clears into the deferred completion tail, but the cadence stops after the first tick follow-up

### Attempt 12

- Accepted ready: `True`
- Accepted ready line: `68812`
- Ready source: `latched-post-bootstrap`
- World sync frames after ready: `[1, 2, 3, 4, 5]`
- Tick PLAYER_INFO frames after ready: `[]`
- NO_TIMEOUT packets after ready: `5`
- PLAYER_INFO packets after ready: `5`
- Deferred tail after ready line: `68851`
- Content label: `` refTables=`0` archives=`0`
- Needs:
  - accepted ready at line 68812, then only 0 tick PLAYER_INFO frame before the attempt ended
  - accepted ready never reached a real scene archive request; keep the world channel alive past reference-table[0]
  - accepted ready clears into the deferred completion tail, but the cadence stops after the first tick follow-up
