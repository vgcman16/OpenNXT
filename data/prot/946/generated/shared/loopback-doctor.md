# 946 Loopback Doctor

- Status: `ok`
- Cluster id: `20260322-071633`
- Attempts analyzed: `1`
- Raw-game sessions: `5`
- Content sessions: `2`
- Reference-table requests: `2`
- Scene archive requests: `0`
- Latest outcome: `reference-tables-only`
- Latest disconnect stage: ``

## Verdict

- Likely blocker: `reference-tables-only-cluster`
- Recommendation: Across the current launch cluster, content capture shows repeated reference-table fetches with zero real scene archive requests.

## Exact Needs

- first non-reference /ms request after reference-table[0]; current content capture has archiveRequests=0
- post-bootstrap scene/archive transition, not more pre-login routing
- first real scene archive request after interfaces

## Attempts

### Attempt 1

- Outcome: `reference-tables-only`
- World stages: `['appearance', 'login-response', 'pipeline-switch', 'rebuild', 'stats', 'default-state', 'interfaces']`
- World window: `194382:197074`
- Disconnect stage: ``
- Bootstrap finished: `True`
- Waiting MAP_BUILD_COMPLETE: `True`
- Skipped ready wait: `False`
- Paired content: `session-07-20260322-071633.log` route=`tls-http-content` first=`reference-table[0]` refTables=`1` archives=`0`
- Paired login raw: `<missing>`
- Needs: first non-reference /ms request after reference-table[0]; current content capture has archiveRequests=0
- Needs: post-bootstrap scene/archive transition, not more pre-login routing
- Needs: first real scene archive request after interfaces
