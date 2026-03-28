# 946 Forced Fallback Parity Doctor

- Status: `ok`
- Latest likely blocker: `forced-fallback-family-gap-before-scene-archives`
- Forced fallback session found: `True`
- Full bootstrap session found: `True`
- Missing family count: `2`
- Deferred family count: `2`

## Verdict

- Recommendation: The forced fallback path is still materially smaller than the stable/full bootstrap. The next concrete gap is the full-only restored interface families that never materialize before scene loading should start.

## Exact Needs

- materialize the restored world panel deck or a narrower subset that advances the client beyond reference-table[0]
- materialize the utility/status panel deck or the smallest subset that actually gates scene start
- decide whether these scripts must move earlier than scene-start phase 3 on the forced path

## Families

### restored-world-panels

- Kind: `full-only-open-family`
- Status: `missing-on-forced-fallback`
- Members: `1464,1458,1461,1884,1885,1887,1886,1460,1881,1888,1883,1449,1882,1452 plus 8862(3,4,5)`
- Why it matters: This is the first large world-side interface deck that the full bootstrap opens after the minimal child. The forced fallback still returns before opening it.
- Needs: materialize the restored world panel deck or a narrower subset that advances the client beyond reference-table[0]
- Source: `C:\Users\Demon\Documents\New project\OpenNXT\src\main\kotlin\com\opennxt\model\world\WorldPlayer.kt:2658` -> `1525`
- Runtime marker: `world-open-restored-interface` observed=`True`
- Runtime line: `310828`

### utility-panel-deck

- Kind: `full-only-open-family`
- Status: `missing-on-forced-fallback`
- Members: `550,1427,1110,590,1416,1519,1588,1678,190,1854,1894 plus 8862(14,15,16,9,10,27,28,29,31,32)`
- Why it matters: The full bootstrap follows the restored world panels with utility/status panels and their 8862 bootstrap scripts. Forced fallback restores only the minimal varcs, not the interfaces that consume them.
- Needs: materialize the utility/status panel deck or the smallest subset that actually gates scene start
- Source: `C:\Users\Demon\Documents\New project\OpenNXT\src\main\kotlin\com\opennxt\model\world\WorldPlayer.kt:2707` -> `2750`
- Runtime marker: `world-send-forced-fallback-utility-panel-deck` observed=`True`
- Runtime line: `310857`

### scene-bridge-family

- Kind: `forced-fallback-bridge`
- Status: `present`
- Members: `1431,568,1465,1919 plus events 60/94`
- Why it matters: This bridge was previously missing and is now restored on the forced fallback path.
- Needs: keep this family intact while testing later scene-start families
- Source: `C:\Users\Demon\Documents\New project\OpenNXT\src\main\kotlin\com\opennxt\model\world\WorldPlayer.kt:1621` -> `1641`
- Runtime marker: `world-open-forced-fallback-scene-bridge` observed=`True`
- Runtime line: `310863`

### late-light-tail-scripts

- Kind: `forced-fallback-deferred-family`
- Status: `deferred-on-forced-fallback`
- Members: `scripts 11145,8420,8310`
- Why it matters: The full bootstrap runs these scripts when the light tail opens. Forced fallback still waits until scene-start control50 phase 3.
- Needs: decide whether these scripts must move earlier than scene-start phase 3 on the forced path
- Source: `C:\Users\Demon\Documents\New project\OpenNXT\src\main\kotlin\com\opennxt\model\world\WorldPlayer.kt:2183` -> `2193`
- Runtime marker: `world-send-deferred-light-tail-scripts-after-scene-start` observed=`False`

### announcement-bundle

- Kind: `forced-fallback-deferred-family`
- Status: `deferred-on-forced-fallback`
- Members: `scripts 1264,3529`
- Why it matters: The full path sends the announcement bundle during deferred completion. Forced fallback still defers it until final late-ready.
- Needs: keep it deferred only if earlier delivery reintroduces loops; otherwise consider moving it closer to the full path
- Source: `C:\Users\Demon\Documents\New project\OpenNXT\src\main\kotlin\com\opennxt\model\world\WorldPlayer.kt:2075` -> `2101`
- Runtime marker: `world-send-deferred-completion-announcement-scripts-after-late-ready` observed=`False`

### completion-script-batch

- Kind: `forced-fallback-deferred-family`
- Status: `present`
- Members: `8862,2651,7486,10903,8778,4704,4308,10623,5559,3957`
- Why it matters: The forced path now restores the full deferred completion script batch, including 5559 and 3957.
- Needs: leave this intact unless a later trace proves one script is still ordered too late
- Source: `C:\Users\Demon\Documents\New project\OpenNXT\src\main\kotlin\com\opennxt\model\world\WorldPlayer.kt:1994` -> `2008`
- Runtime marker: `world-send-forced-fallback-deferred-completion-scripts` observed=`True`
- Runtime line: `310909`
