# 946 Curated Historical Compare

- Status: `ok`
- Sessions analyzed: `3299`
- Labels present: `True`
- Labels file: `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\curated-session-labels.json`
- Labels format: `rich-map`
- Manual labels applied: `0`
- Labeled stable sessions: `0`
- Labeled bad sessions: `0`
- Confidence: `low`
- Advisory ready: `False`
- Seed source: `heuristic`
- Anchor pair source: `labeled`

## Cohorts

### stable_interfaces

- Count: `865`
- Median eventCount: `183`
- Median durationSeconds: `3.003`
- Median PLAYER_INFO count: `1`
- Representatives:
- `427378:439930` score=`495463` events=`10218` duration=`8894.546` playerInfo=`3963`
- `439931:445171` score=`144815` events=`4460` duration=`915.563` playerInfo=`1312`
- `445172:449128` score=`99435` events=`3433` duration=`890.252` playerInfo=`871`
- `449129:451172` score=`75087` events=`1629` duration=`415.822` playerInfo=`693`
- `251442:253061` score=`62424` events=`1619` duration=`6070.573` playerInfo=`1`

### short_loop

- Count: `1965`
- Median eventCount: `79`
- Median durationSeconds: `3.0`
- Median PLAYER_INFO count: `1`
- Representatives:
- `121466:121536` score=`93` events=`70` duration=`2.391` playerInfo=`0`
- `122044:122114` score=`93` events=`70` duration=`2.396` playerInfo=`0`
- `68939:69009` score=`93` events=`70` duration=`2.398` playerInfo=`0`
- `78355:78425` score=`93` events=`70` duration=`2.391` playerInfo=`0`
- `82844:82914` score=`93` events=`70` duration=`2.399` playerInfo=`0`

### rebuild_fail

- Count: `21`
- Median eventCount: `19`
- Median durationSeconds: `6.0`
- Median PLAYER_INFO count: `0`
- Representatives:
- `1:5` score=`30` events=`5` duration=`2.57` playerInfo=`0`
- `376954:376961` score=`37` events=`8` duration=`2.993` playerInfo=`0`
- `289902:289911` score=`39` events=`10` duration=`2.998` playerInfo=`0`
- `272054:272061` score=`43` events=`8` duration=`3.591` playerInfo=`0`
- `142443:142460` score=`48` events=`18` duration=`3.0` playerInfo=`0`

### other

- Count: `448`
- Median eventCount: `137.0`
- Median durationSeconds: `3.019`
- Median PLAYER_INFO count: `0.0`
- Representatives:
- `57363:57487` score=`131` events=`123` duration=`0.857` playerInfo=`0`
- `11470:11605` score=`164` events=`135` duration=`2.996` playerInfo=`0`
- `15667:15802` score=`164` events=`135` duration=`2.992` playerInfo=`0`
- `16217:16352` score=`164` events=`135` duration=`2.971` playerInfo=`0`
- `16767:16902` score=`164` events=`135` duration=`2.977` playerInfo=`0`

## Best-Known Baseline

- Seed session: `427378:439930`
- Recommendation rationale: `Recommendations are limited to helped, bundle-eligible features that were already present in the chosen seed session.`

### Recommended Features

- `deferred_completion_structure` stable=`0.983` short=`0.0` delta=`0.983`
- `deferred_completion_tail` stable=`0.983` short=`0.0` delta=`0.983`
- `ready_signal` stable=`0.97` short=`0.367` delta=`0.603`
- `full_initial_player_info` stable=`0.994` short=`0.515` delta=`0.48`

### Rejected Features

- `server_opcode_45_present` reason=`observational-not-bundle-input` stable=`0.995` short=`0.226` delta=`0.769`
- `deferred_completion_scripts` reason=`absent-from-seed` stable=`0.65` short=`0.0` delta=`0.65`
- `post_initial_hold` reason=`absent-from-seed` stable=`0.976` short=`0.412` delta=`0.564`
- `server_opcode_42_present` reason=`observational-not-bundle-input` stable=`0.994` short=`0.515` delta=`0.48`

## Feature Rankings

### Helped

- `deferred_completion_structure` stable=`0.983` short=`0.0` delta=`0.983`
- `deferred_completion_tail` stable=`0.983` short=`0.0` delta=`0.983`
- `server_opcode_45_present` stable=`0.995` short=`0.226` delta=`0.769`
- `deferred_completion_scripts` stable=`0.65` short=`0.0` delta=`0.65`
- `ready_signal` stable=`0.97` short=`0.367` delta=`0.603`
- `post_initial_hold` stable=`0.976` short=`0.412` delta=`0.564`
- `full_initial_player_info` stable=`0.994` short=`0.515` delta=`0.48`
- `server_opcode_42_present` stable=`0.994` short=`0.515` delta=`0.48`

### Hurt

- None.

### Inconclusive

- `immediate_followup_sync` stable=`0.018` short=`0.103` delta=`-0.084`
- `active_player_116_sent` stable=`0.995` short=`0.932` delta=`0.063`
- `active_player_skipped` stable=`0.005` short=`0.068` delta=`-0.063`
- `server_opcode_116_present` stable=`0.995` short=`0.932` delta=`0.063`
- `deferred_completion_event_delta` stable=`0.031` short=`0.0` delta=`0.031`
- `client_opcode_48_present` stable=`0.039` short=`0.012` delta=`0.027`
- `client_opcode_17_present` stable=`0.025` short=`0.005` delta=`0.021`
- `client_opcode_83_present` stable=`0.021` short=`0.006` delta=`0.015`
- `sustained_player_info` stable=`0.008` short=`0.0` delta=`0.008`
- `close_loading_overlay` stable=`0.005` short=`0.0` delta=`0.005`
- `server_opcode_50_present` stable=`0.005` short=`0.0` delta=`0.005`
- `world_init_state_sent` stable=`0.995` short=`1.0` delta=`-0.005`

## Anchor Pair

- No stable/bad anchor pair available.
