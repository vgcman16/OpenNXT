# 946 Script Burst Doctor

- Status: `ok`
- Cluster id: `20260322-170307`
- Attempts analyzed: `1`
- Attempts with RUNCLIENTSCRIPT burst: `0`
- Latest dominant opcode: `141`
- Latest dominant opcode count: `9`

## Verdict

- Likely blocker: `post-ready-script-unclassified`
- Recommendation: RUNCLIENTSCRIPT traffic is present, but the latest cluster does not yet isolate one script family as the blocker.

## Exact Needs

- first non-reference /ms archive request after reference-table[0]

## Attempts

### Attempt 1

- Likely pivot: `post-ready-script-unclassified`
- Pivot lines: `1:54`
- Dominant opcode: `141` x `9`
- RUNCLIENTSCRIPT packet sizes: `{10: 3, 15: 2, 30: 2, 37: 2}`
- Content first request: `reference-table[0]`
- Archive requests: `0`
- Script families:
  - `light-interface-tail` via `world-send-light-interface-tail` x `1` `scripts=11145,8420,8310`
- Needs: first non-reference /ms archive request after reference-table[0]
