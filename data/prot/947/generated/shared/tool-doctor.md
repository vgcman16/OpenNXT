# 946 Tool Doctor

- Status: `partial`
- Blocked: `0`
- Partial: `4`

## Requirements

- `world-log` status=`ok` present=`True` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\debug\world-bootstrap-raw.log`
- `phase3-name-candidates` status=`partial` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\phase3\nameCandidates.json`
- `phase5-generated-packets` status=`partial` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\phase5\generatedPackets.json`
- `shared-verified-packets` status=`partial` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\verified-packets.json`
- `shared-evidence-index` status=`partial` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\evidence-index.json`
- `curated-labels` status=`ok` present=`True` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\curated-session-labels.json`
- `decomp-log-dir` status=`ok` present=`True` path=`C:\Users\Demon\Documents\New project\ghidra-projects`
- `ghidra-headless` status=`ok` present=`True` path=`C:\Users\Demon\Tools\ghidra\ghidra_12.0.4_PUBLIC\support\analyzeHeadless.bat`
- `curated-compare` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\curated-compare.json`
- `sender-aid` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\sender-analysis.json`
- `active-sub-aid` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\active-sub-analysis.json`
- `interface-diff` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\interface-diff.json`
- `scene-delivery-aid` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\scene-delivery-analysis.json`
- `js5-archive-resolver` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\js5-archive-resolution.json`
- `plateau-diff` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\plateau-diff.json`
- `black-screen-capture` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\black-screen-capture.json`
- `loopback-doctor` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\loopback-doctor.json`
- `attempt-diff` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\attempt-diff.json`
- `ready-signal-doctor` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\ready-signal-doctor.json`
- `disconnect-pivot-doctor` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\disconnect-pivot-doctor.json`
- `script-burst-doctor` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\script-burst-doctor.json`
- `scene-start-doctor` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\scene-start-doctor.json`
- `post-scene-opcode-doctor` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\post-scene-opcode-doctor.json`
- `live-var-packet-doctor` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\live-var-packet-doctor.json`
- `forced-fallback-parity-doctor` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\forced-fallback-parity-doctor.json`
- `client-live-watch` status=`ok` present=`True` freshness=`fresh` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\debug\client-live-watch\latest-summary.json`
- `runtime-verifier` status=`ok` present=`True` freshness=`stale` path=`C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\runtime-verification-results.json`

## Readiness

- `run_946_pipeline` `production-ready` Pipeline manifest present.
- `run_946_curated_compare` `near-ready` freshness=`stale` Needs stronger advisory coverage or labels.
- `run_946_runtime_verifier` `near-ready` freshness=`stale` Artifact missing or not fully green.
- `run_946_sender_aid` `near-ready` freshness=`stale` Standard artifact present.
- `run_946_active_sub_aid` `near-ready` freshness=`stale` Standard artifact present.
- `run_946_interface_diff` `near-ready` freshness=`stale` Standard artifact present.
- `run_946_scene_delivery_aid` `near-ready` freshness=`stale` Standard artifact present.
- `run_946_js5_archive_resolver` `near-ready` freshness=`stale` Structured JS5 archive labeling present.
- `run_946_plateau_diff` `near-ready` freshness=`stale` Post-interfaces plateau comparison present.
- `run_946_black_screen_capture` `near-ready` freshness=`stale` Capture bundle present.
- `run_946_loopback_doctor` `near-ready` freshness=`stale` Attempt-level loopback diagnosis is present.
- `run_946_attempt_diff` `near-ready` freshness=`stale` Exact attempt-tail diffing is present.
- `run_946_ready_signal_doctor` `near-ready` freshness=`stale` Ready-signal latch/skip analysis is present.
- `run_946_post_ready_cadence_doctor` `near-ready` freshness=`stale` Accepted-ready post-bootstrap cadence analysis is present.
- `run_946_disconnect_pivot_doctor` `near-ready` freshness=`stale` Disconnect-window dominant packet-family analysis is present.
- `run_946_script_burst_doctor` `near-ready` freshness=`stale` RUNCLIENTSCRIPT-family burst analysis is present.
- `run_946_scene_start_doctor` `near-ready` freshness=`stale` Accepted-ready plateau analysis is present with rebuild/ready/control ordering.
- `run_946_post_scene_opcode_doctor` `near-ready` freshness=`stale` Late accepted-ready unresolved client opcode analysis is present.
- `run_946_live_var_packet_doctor` `near-ready` freshness=`stale` Latest plateau session is correlated against golden VARP traffic and candidate loading vars.
- `run_946_forced_fallback_parity_doctor` `near-ready` freshness=`stale` Forced fallback is compared against the stable/full WorldPlayer bootstrap families.
- `watch_rs2client_live` `near-ready` freshness=`fresh` Live watcher summary present with deep client-side evidence.
