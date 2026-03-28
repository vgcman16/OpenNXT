# 946 Loading Var Gate Doctor

- Status: `ok`
- Latest likely blocker: `accepted-ready-no-scene-archives`
- Loading-tail scripts found: `17`
- Scripts missing evidence: `[1264, 3957, 11145]`
- ResetClientVarcache observed: `False`
- Deferred default varps observed: `False`
- Map-gate idx lookups: `0`
- Map-gate /ms requests: `0`
- Map-gate non-reference /ms requests: `0`

## Verdict

- Recommendation: The client is still stalling before scene archive fetches begin. Focus on the candidate loading vars touched by the late bootstrap scripts, especially where the live map-gate capture shows no idx lookups and no non-reference /ms requests.

## Exact Needs

- client-side var gate before archive resolution; no cache idx lookups or /ms archive requests occurred
- live read/write capture for candidate varps 0,1,2,6,3,4 before the first scene archive request
- materialize or infer var evidence for loading-tail scripts 1264,3957,11145

## Scripts

- `script 139` decode=`unsupported` exact=`False` sources=`['world-send-deferred-forced-fallback-completion-companions']` directVarps=`0` heuristicVarps=`2` directVarbits=`0` heuristicVarbits=`0`
- `script 1264` decode=`missing` exact=`False` sources=`['world-send-deferred-completion-announcement-scripts']` directVarps=`0` heuristicVarps=`0` directVarbits=`0` heuristicVarbits=`0`
- `script 2651` decode=`unsupported` exact=`False` sources=`['world-send-forced-fallback-deferred-completion-scripts']` directVarps=`0` heuristicVarps=`2` directVarbits=`0` heuristicVarbits=`0`
- `script 3529` decode=`unsupported` exact=`False` sources=`['world-send-deferred-completion-announcement-scripts']` directVarps=`0` heuristicVarps=`9` directVarbits=`0` heuristicVarbits=`0`
- `script 3957` decode=`missing` exact=`False` sources=`['world-send-forced-fallback-deferred-completion-scripts']` directVarps=`0` heuristicVarps=`0` directVarbits=`0` heuristicVarbits=`0`
- `script 4308` decode=`unsupported` exact=`False` sources=`['world-send-forced-fallback-deferred-completion-scripts']` directVarps=`0` heuristicVarps=`2` directVarbits=`0` heuristicVarbits=`0`
- `script 4704` decode=`unsupported` exact=`False` sources=`['world-send-forced-fallback-deferred-completion-scripts']` directVarps=`0` heuristicVarps=`20` directVarbits=`0` heuristicVarbits=`4`
- `script 5559` decode=`unsupported` exact=`False` sources=`['world-send-forced-fallback-deferred-completion-scripts']` directVarps=`0` heuristicVarps=`2` directVarbits=`0` heuristicVarbits=`0`
- `script 7486` decode=`unsupported` exact=`False` sources=`['world-send-forced-fallback-deferred-completion-scripts']` directVarps=`0` heuristicVarps=`2` directVarbits=`0` heuristicVarbits=`0`
- `script 8310` decode=`unsupported` exact=`False` sources=`['world-send-deferred-light-tail-scripts-after-scene-start']` directVarps=`0` heuristicVarps=`2` directVarbits=`0` heuristicVarbits=`0`
- `script 8420` decode=`unsupported` exact=`False` sources=`['world-send-deferred-light-tail-scripts-after-scene-start']` directVarps=`0` heuristicVarps=`2` directVarbits=`0` heuristicVarbits=`0`
- `script 8778` decode=`unsupported` exact=`False` sources=`['world-send-forced-fallback-deferred-completion-scripts']` directVarps=`0` heuristicVarps=`1` directVarbits=`0` heuristicVarbits=`0`
- `script 8862` decode=`unsupported` exact=`False` sources=`['world-send-forced-fallback-deferred-completion-scripts']` directVarps=`0` heuristicVarps=`2` directVarbits=`0` heuristicVarbits=`0`
- `script 10623` decode=`unsupported` exact=`False` sources=`['world-send-forced-fallback-deferred-completion-scripts']` directVarps=`0` heuristicVarps=`2` directVarbits=`0` heuristicVarbits=`0`
- `script 10903` decode=`unsupported` exact=`False` sources=`['world-send-forced-fallback-deferred-completion-scripts']` directVarps=`0` heuristicVarps=`0` directVarbits=`0` heuristicVarbits=`1`
- `script 11145` decode=`missing` exact=`False` sources=`['world-send-deferred-light-tail-scripts-after-scene-start']` directVarps=`0` heuristicVarps=`0` directVarbits=`0` heuristicVarbits=`0`
- `script 14150` decode=`unsupported` exact=`False` sources=`['world-send-deferred-forced-fallback-completion-companions']` directVarps=`0` heuristicVarps=`2` directVarbits=`0` heuristicVarbits=`0`

## Candidate Vars

### Direct Varps

- none

### Heuristic Varps

- `varp 0` scripts=[139, 2651, 3529, 4308, 4704, 5559, 7486, 8310, 8420, 8778, 8862, 10623, 14150] accesses={'get': 9, 'set': 14} extractions={'heuristic': 23} domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=1793
- `varp 1` scripts=[3529, 4704] accesses={'get': 7, 'set': 1} extractions={'heuristic': 8} domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=1034
- `varp 2` scripts=[3529, 4704] accesses={'get': 4, 'set': 1} extractions={'heuristic': 5} domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=267
- `varp 6` scripts=[3529, 8420] accesses={'get': 3, 'set': 1} extractions={'heuristic': 4} domain=PLAYER type=LONG forceDefault=True backingVarbits=1312
- `varp 3` scripts=[4704] accesses={'set': 1} extractions={'heuristic': 1} domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=305
- `varp 4` scripts=[4704] accesses={'get': 2, 'set': 2} extractions={'heuristic': 4} domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=1215
- `varp 7` scripts=[4704] accesses={'set': 1} extractions={'heuristic': 1} domain=PLAYER type=LONG forceDefault=True backingVarbits=340
- `varp 10` scripts=[4704] accesses={'get': 1} extractions={'heuristic': 1} domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=1533
- `varp 11` scripts=[3529] accesses={'set': 1} extractions={'heuristic': 1} domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=1198
- `varp 3920` scripts=[3529] accesses={'set': 1} extractions={'heuristic': 1} domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=0
- `varp 8256` scripts=[3529] accesses={'get': 1} extractions={'heuristic': 1} domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=0

### Direct Varbits

- none

### Heuristic Varbits

- `varbit 0` scripts=[10903] accesses={'get': 1} extractions={'heuristic': 1} baseVar=0 bits=2..4
- `varbit 5` scripts=[4704] accesses={'get': 1} extractions={'heuristic': 1} baseVar=0 bits=2..4
- `varbit 9` scripts=[4704] accesses={'get': 1} extractions={'heuristic': 1} baseVar=0 bits=2..4
- `varbit 82` scripts=[4704] accesses={'get': 1} extractions={'heuristic': 1} baseVar=0 bits=2..18
- `varbit 88` scripts=[4704] accesses={'set': 1} extractions={'heuristic': 1} baseVar=0 bits=2..20
