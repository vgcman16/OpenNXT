# 946 Live Var Packet Doctor

- Status: `ok`
- Latest likely blocker: `partial-post-reset-candidate-varp-gap`
- Candidate varps: `11`
- Candidate varps observed: `0`
- Candidate varps sent after reset: `0`
- Candidate varps missing after reset: `11`
- Golden VARP events in window: `0`
- Ignored embedded golden VARP events: `240`
- ResetClientVarcache observed: `False`
- Deferred default varps observed: `False`
- Ready accepted observed: `True`
- Minimal varcs: `[181, 1027, 1034, 3497]`
- Session window: `2026-03-22T07:44:10.551786300Z` -> `2026-03-22T09:28:54.947139900Z`

## Exact Needs

- candidate varps 0,1,2,6,3,4 are still missing post-reset/send-after-ready evidence
- confirm minimal varcs 181,1027,1034,3497 are sufficient for scene-start gating on the forced fallback path

## Observed Top Varps

- none

## Candidate Varps

- `varp 0` status=`never-sent` source=`heuristic` observed=`0` afterReset=`0` afterReady=`0` values=`[]` scripts=`[139, 2651, 3529, 4308, 4704, 5559, 7486, 8310, 8420, 8778, 8862, 10623, 14150]` domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=1793
  reason: no VarpSmall/VarpLarge send observed in the latest plateau window
- `varp 1` status=`never-sent` source=`heuristic` observed=`0` afterReset=`0` afterReady=`0` values=`[]` scripts=`[3529, 4704]` domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=1034
  reason: no VarpSmall/VarpLarge send observed in the latest plateau window
- `varp 2` status=`never-sent` source=`heuristic` observed=`0` afterReset=`0` afterReady=`0` values=`[]` scripts=`[3529, 4704]` domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=267
  reason: no VarpSmall/VarpLarge send observed in the latest plateau window
- `varp 6` status=`never-sent` source=`heuristic` observed=`0` afterReset=`0` afterReady=`0` values=`[]` scripts=`[3529, 8420]` domain=PLAYER type=LONG forceDefault=True backingVarbits=1312
  reason: no VarpSmall/VarpLarge send observed in the latest plateau window
- `varp 3` status=`never-sent` source=`heuristic` observed=`0` afterReset=`0` afterReady=`0` values=`[]` scripts=`[4704]` domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=305
  reason: no VarpSmall/VarpLarge send observed in the latest plateau window
- `varp 4` status=`never-sent` source=`heuristic` observed=`0` afterReset=`0` afterReady=`0` values=`[]` scripts=`[4704]` domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=1215
  reason: no VarpSmall/VarpLarge send observed in the latest plateau window
- `varp 7` status=`never-sent` source=`heuristic` observed=`0` afterReset=`0` afterReady=`0` values=`[]` scripts=`[4704]` domain=PLAYER type=LONG forceDefault=True backingVarbits=340
  reason: no VarpSmall/VarpLarge send observed in the latest plateau window
- `varp 10` status=`never-sent` source=`heuristic` observed=`0` afterReset=`0` afterReady=`0` values=`[]` scripts=`[4704]` domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=1533
  reason: no VarpSmall/VarpLarge send observed in the latest plateau window
- `varp 11` status=`never-sent` source=`heuristic` observed=`0` afterReset=`0` afterReady=`0` values=`[]` scripts=`[3529]` domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=1198
  reason: no VarpSmall/VarpLarge send observed in the latest plateau window
- `varp 3920` status=`never-sent` source=`heuristic` observed=`0` afterReset=`0` afterReady=`0` values=`[]` scripts=`[3529]` domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=0
  reason: no VarpSmall/VarpLarge send observed in the latest plateau window
- `varp 8256` status=`never-sent` source=`heuristic` observed=`0` afterReset=`0` afterReady=`0` values=`[]` scripts=`[3529]` domain=PLAYER type=QUESTHELP forceDefault=True backingVarbits=0
  reason: no VarpSmall/VarpLarge send observed in the latest plateau window

## Derived Base Varps

- none
