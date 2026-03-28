# 946 Pipeline Run Report

- Generated: `2026-03-16T22:39:23.034059+00:00`

## Phase Runs

- Phase `1` status=`cached` durationMs=`0`
- Phase `2` status=`cached` durationMs=`0`
- Phase `3` status=`cached` durationMs=`0`
- Phase `4` status=`cached` durationMs=`0`
- Phase `5` status=`cached` durationMs=`0`
- Phase `handoff` status=`ok` durationMs=`5365`
- Phase `sender-aid` status=`partial` durationMs=`53980`
- Phase `curated-compare` status=`ok` durationMs=`4718`
- Phase `active-sub-aid` status=`cached` durationMs=`145`
- Phase `interface-diff` status=`ok` durationMs=`7752`
- Phase `scene-delivery-aid` status=`partial` durationMs=`4605`
- Phase `js5-archive-resolver` status=`cached` durationMs=`104`
- Phase `plateau-diff` status=`ok` durationMs=`21300`
- Phase `opcode-113-verdict` status=`ok` durationMs=`4446`
- Phase `tool-doctor` status=`partial` durationMs=`222`

## Baseline

- Drift detected: `29` artifact(s)
- Informational only: `False`
- Drift categories: `{'generated-analysis': 5, 'promotion-surface': 2, 'runtime-results': 2, 'shared-evidence': 20}`
- `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\phase3\nameCandidates.json`
- `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\phase4\fieldGapAnalysis.json`
- `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\phase4\parserFieldIndex.json`
- `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\active-sub-analysis.json`
- `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\active-sub-analysis.md`
- `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\cross-build-index.json`
- `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\curated-compare.json`
- `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\curated-compare.md`
- `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\evidence-index.json`
- `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\handoff-analysis.json`
- `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\handoff-analysis.md`
- `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\interface-diff.json`

## Runtime Verification

- Runtime verification not requested

## Handoff Aid

- Status: `partial`
- Suspects: `5`
- Top targets: `6`
- PLAYER_INFO needs review: `True`

## Sender Aid

- Status: `partial`
- Sender entries: `5`

## Active-Sub Aid

- Status: `ok`
- Targets: `3`

## Interface Diff

- Status: `ok`
- Findings: `7`
- Verdict: `unknown`

## Scene Delivery Aid

- Status: `partial`
- Relevant JS5 sessions: `0`
- Scene delivery state: `capture-missing`
- Likely blocker: `capture-missing`

## JS5 Archive Resolver

- Status: `partial`
- Resolved archives: `0`

## Plateau Diff

- Status: `ok`
- Top hypothesis: `asset-delivery stall`

## Black Screen Capture

- Black-screen capture not available

## Curated Compare

- Status: `ok`
- Confidence: `high`
- Advisory ready: `True`
- Labels applied: `6`
- Seed source: `labeled`
- Anchor pair source: `labeled`
- Recommendation rationale: `No bundle recommendation because the helped features did not coexist in the seed session; synthetic unions were intentionally rejected.`

## Opcode 113 Verdict

- Status: `ok`
- Verdict: `state-report`
- Next lead: `116` `server`

## Tool Doctor

- Status: `partial`
- Blocked: `0`
- Partial: `5`

## Tool Readiness

- `run_946_runtime_verifier` `experimental` Run with --verify-runtime to populate runtime verification.
- `run_946_handoff_aid` `near-ready` Pipeline advisory artifact present.
- `run_946_sender_aid` `near-ready` Standard artifact present.
- `run_946_active_sub_aid` `near-ready` Standard artifact present.
- `run_946_interface_diff` `near-ready` Standard artifact present.
- `run_946_scene_delivery_aid` `near-ready` Standard artifact present.
- `run_946_js5_archive_resolver` `near-ready` Structured JS5 archive labels present.
- `run_946_plateau_diff` `near-ready` Post-interfaces plateau comparison present.
- `run_946_black_screen_capture` `experimental` Capture bundle not created yet.
- `run_946_curated_compare` `production-ready` Labeled advisory-ready compare.
- `run_946_tool_doctor` `near-ready` Doctor can validate current trust surfaces.
