# Build 946 Extraction Automation Plan

## Goal

Turn the current ad hoc `946` reversing workflow into a repeatable pipeline that can:

- import a new client build into Ghidra
- extract packet size tables automatically
- recover packet families and handler/parser chains automatically
- emit draft protocol files with confidence markers
- leave only the ambiguous semantic checks for manual review

This is not a "press button and recover 100% of the build with no review" target.
The realistic target is "automate most discovery, then manually confirm the risky
or ambiguous parts."

## Current Milestone Status

- Phase 1: complete for build `946`
  - baseline discovery and size extraction are now automated by
    `C:\Users\Demon\Documents\New project\OpenNXT\tools\run_946_extraction.py`
- Phase 2: complete enough to feed Phase 3
  - descriptor-to-parser recovery is now automated by
    `C:\Users\Demon\Documents\New project\OpenNXT\tools\run_946_phase2.py`
  - current implementation now includes:
    - server parser recovery through the assign-helper path
    - client sender recovery from the direct `ClientProt` descriptor block
- Phase 3: in progress
  - initial family classification is now automated by
    `C:\Users\Demon\Documents\New project\OpenNXT\tools\run_946_phase3.py`
  - current implementation now emits:
    - confidence-scored `nameCandidates.json`
    - `clientAmbiguousClusters.json` for unresolved client prompt/input clusters
    - generated draft `serverProtNames.generated.toml`
    - generated draft `clientProtNames.generated.toml`
    - generated exact-candidate review files
      - `serverProtNames.uniqueCandidates.generated.toml`
      - `clientProtNames.uniqueCandidates.generated.toml`
    - `phase3-summary.md`
    - dispatcher-selector evidence for ambiguous client prompt clusters
  - current results:
    - `84` unresolved server opcodes now carry family hints
    - `8` unresolved client opcodes now carry family hints
    - `18` unresolved server opcodes now carry exact-name candidate lists
    - `3` unresolved client opcodes now carry exact-name candidate lists
  - remaining limitation: client output still needs deeper sender semantics
    beyond the current dispatcher/selector hints for the raw-string resume trio
    before most unresolved singletons can be named safely
- Phase 4: scaffolded
  - verification preparation is now automated by
    `C:\Users\Demon\Documents\New project\OpenNXT\tools\run_946_phase4.py`
  - current implementation now emits:
    - `fieldGapAnalysis.json`
    - `fieldRecoveryQueue.json`
    - `runtimeVerificationQueue.json`
    - `runtimeFocus.json`
    - `parserFieldIndex.json`
    - `parserFields/*.json`
    - `manualFieldDraftOverrides.json`
    - `phase4-summary.md`
  - current scope:
    - queue named packets that still lack `946` field declarations
    - queue unresolved packets that already have family or exact-name evidence
    - cross-reference named `946` packets against `919` field files when a legacy
      name/file exists
    - skip auto-field generation for the current do-not-touch packet blacklist
    - sequentially run `ExportParserFields.java` against the top safe recovery
      targets or explicit packet names
    - keep already-promoted packet drafts refreshable so `parserFieldIndex.json`
      and `phase4-summary.md` do not go stale after field-file promotions
    - merge reviewed draft overrides for packets whose semantics are already
      proven by manual decompile review but not yet recovered cleanly by the
      generic extractor
  - remaining limitation:
    - Phase 4 does not yet auto-run the live OpenNXT verification loop
    - current field export still uses decompiler-text heuristics rather than a
      full Pcode data-flow walk, so transformed reads are draft-quality evidence,
      not final truth
    - auto-emitting final `*.txt` field files is still gated on reviewing the
      extracted draft JSONs
  - current safe-target extractor results:
    - `IF_SETEVENTS` recovered `mask intle`, `fromSlot ushortle`,
      `parent intv2`, `toSlot ushortle128` after helper-argument validation
    - `IF_SETTEXT` draft recovered `string`, `intle`
    - `RESUME_P_COUNTDIALOG` now recovers a sender-side `count long`
    - `IF_SETCOLOUR` draft recovered `intv1`, `ushort128`
    - `IF_OPENSUB_ACTIVE_OBJ` draft recovered `ushort`, `ushort`, `intv1`, `ubytec`, `intv1`
    - `IF_SETPLAYERHEAD` draft recovered `intv1`
    - `IF_SETPLAYERMODEL_SELF` draft recovered `intv2`
    - `IF_SETSCROLLPOS` now recovers cleanly as `component intle`,
      `scrollPosition ushort`
    - `IF_SETRECOL` draft recovered `ushortle`, `ushortle`, `ubytec`, `intle`
    - `IF_SETRETEX` recovered `ubytec`, `intv1`, `ushort128`, `ushortle`
    - `OBJ_REVEAL` now recovers cleanly enough to emit a first-pass field file:
      `count ushortle`, `id ushortle`, `packedCoord ubyte`, `playerIndex ushortle`
    - shadowed direct-scalar byte loads are now filtered when a wider recovered
      field already consumes the same parser locals
    - top-level call-argument short expressions are now recovered separately from
      surrounding larger expressions, which lets mixed `IF_*` setter calls expose
      embedded `ushort*` fields instead of only the dominant `int` payload
    - top-level operator detection now ignores inner address arithmetic, which
      fixed the final `IF_SETRETEX` short-order classification

## What We Already Have

### Inputs and runtime

- Working local `946` client and cache download path
- Ghidra project import of the live `win64` client
- Live OpenNXT runtime loop for verifying protocol guesses against a real client

### Existing extraction outputs

- `serverProtSizes.toml`
- `clientProtSizes.toml`
- partial `serverProtNames.toml`
- partial `clientProtNames.toml`
- partial `serverProt/*.txt`

### Existing Ghidra script building blocks

Main legacy script:

- `C:\Users\Demon\Documents\New project\ghidra-scripts\RS3NXTRefactorer.java`

Helper scripts already useful for automation:

- `C:\Users\Demon\Documents\New project\ghidra-scripts\FindContiguousRegistrars.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\FindGenericContiguousRegistrars.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\FindDescriptorFunctionsWithShift16.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\ListDescriptorRefsInFunction.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\ListHandlerAssignmentsInFunction.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\TracePacketRefs.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\DumpCallRefsForTarget.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\FindFunctionsCallingAllTargets.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\FindFunctionsReferencingDescriptors.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\FindFunctionsReferencingRange.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\FindBitAccessFunctions.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\FindCallersWithScalars.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\FindFunctionsByScalars.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\ListRefsToAddress.java`
- `C:\Users\Demon\Documents\New project\ghidra-scripts\DecompileFunction.java`

### Confirmed hand-built anchors

We already have enough parser-confirmed anchors to automate outward from them:

- direct server registrar at `FUN_140301280`
- direct client registrar at `FUN_140301100`
- parser-backed server anchors such as `IF_OPENSUB`, `MAP_PROJANIM`,
  `PLAYER_INFO`, `NPC_INFO`, `UPDATE_STAT`, `RESET_CLIENT_VARCACHE`
- parser-backed client anchors such as `NO_TIMEOUT`, `CLIENT_CHEAT`,
  `MAP_BUILD_COMPLETE`, `OPPLAYER*`, `OPNPC*`, `OPLOC*`, `OPOBJ*`

That anchor set is strong enough to support a real pipeline.

## What Is Still Missing

### Missing automation features

- one orchestrator that runs the helper scripts in the right order
- structured machine-readable output from the helper scripts
- confidence scoring for draft names and field layouts
- automatic emission of draft `*.toml` and `*.txt` files
- a final verification step that compares generated data against runtime behavior

### Missing extraction coverage

- full packet naming coverage
- full field extraction coverage
- reliable auto-classification for ambiguous UI and login/init packets
- robust handling for transport changes such as TLS-wrapped post-lobby handoff

### Missing workflow hygiene

- a single command to run the whole extraction workflow
- one output directory for intermediate evidence
- a stable "generated vs confirmed" distinction in emitted protocol files

## Recommended Pipeline

## Stage 1: Build Import and Baseline Discovery

Inputs:

- client exe path
- Ghidra project path
- output workspace path

Automate:

- import/analyze the client if missing
- locate direct packet registrars
- locate descriptor tables
- record build metadata and registrar addresses

Output:

- `build-info.json`
- `registrars.json`

Status:

- complete for `946`
- implemented in `run_946_extraction.py`

## Stage 2: Size Extraction

Automate:

- extract contiguous server packet sizes from the direct server registrar
- extract contiguous client packet sizes from the direct client registrar
- diff against the previous supported build

Output:

- `serverProtSizes.toml`
- `clientProtSizes.toml`
- `sizeDiffReport.md`
- `sizeCandidates.json`

Status:

- solved enough for `946`
- current implementation: generic export for the server registrar, helper-driven
  fallback (`DumpCallRefsForTarget.java`) for the client registrar
- implemented in `run_946_extraction.py`

## Stage 3: Descriptor to Parser Recovery

Automate:

- walk `opcode -> descriptor`
- resolve `descriptor + 0x48 -> handler`
- resolve handler vtable -> thunk -> parser
- store parser addresses, family clusters, and nearby helper calls

Output:

- `serverParsers.json`
- `clientParsers.json`
- `handlerFamilies.json`

Status:

- in progress
- current implementation: `run_946_phase2.py` emits `serverParsers.json`,
  `clientParsers.json`, `handlerFamilies.json`, and `phase2-summary.md`
- current implementation now recovers:
  - `206` server parser mappings through the assign-helper path
  - `130` client sender mappings through the direct client descriptor block
- current limitation: client output is sender-oriented and still needs semantic
  family classification before draft naming is trustworthy

## Stage 4: Family Classification

Automate heuristics for:

- sync families: `PLAYER_INFO`, `NPC_INFO`
- UI families: `IF_*`, `RESUME_*`
- world families: `LOC_*`, `OBJ_*`, map/projectile packets
- input families: `OPPLAYER*`, `OPNPC*`, `OPLOC*`, `OPOBJ*`
- init families: `UPDATE_STAT`, `VARP_*`, `VARC_*`, reset packets

Signals to use:

- parser sizes
- scalar constants
- bit-reader usage
- selected-component state reads
- target-index access shape
- interface manager references
- scene/world helper references

Output:

- `nameCandidates.json` with confidence scores
- draft `serverProtNames.toml`
- draft `clientProtNames.toml`

Status:

- in progress
- current implementation: `run_946_phase3.py` emits `nameCandidates.json`,
  `serverProtNames.generated.toml`, `clientProtNames.generated.toml`, and
  `phase3-summary.md`
- current implementation now classifies:
  - `122` total server opcodes into broad families
  - `62` total client opcodes into broad families
  - `84` unresolved server opcodes with family hints
  - `8` unresolved client opcodes with family hints
- current exact-name candidate coverage:
  - `18` unresolved server opcodes with exact-name candidate lists
  - `3` unresolved client opcodes with exact-name candidate lists

## Stage 5: Field Recovery and Runtime Verification

Automate:

- diff named `946` packets against matching `919` field files
- produce a prioritized field-recovery queue with legacy-shape hints
- blacklist packets that should stay hand-crafted
- export draft field layouts from parser/sender functions for the safest targets
- carry unresolved packet families into a runtime verification queue

Outputs:

- `fieldGapAnalysis.json`
- `fieldRecoveryQueue.json`
- `runtimeVerificationQueue.json`
- `runtimeFocus.json`
- `parserFieldIndex.json`
- `parserFields/*.json`
- `phase4-summary.md`

Status:

- in progress
- current implementation: `run_946_phase4.py`
- current implementation now includes:
  - legacy field diffing against `919`
  - do-not-touch blacklist enforcement for `PLAYER_INFO`, `NPC_INFO`,
    `REBUILD_NORMAL`, `MAP_PROJANIM`, and `MAP_PROJANIM_HALFSQ`
  - sequential `ExportParserFields.java` runs for the top safe targets
  - sender fallback for client packets that do not yet have a parser target
  - explicit packet re-extraction for already-promoted packets so the generated
    parser index and summary stay aligned with the latest field drafts
  - direct scalar-load detection for `*(uint *)`, `*(ushort *)`, and `*(char *)`
    parser reads followed by byte-swap/rotate/negation transforms
- current limitation:
  - field draft extraction is still evidence-driven, not fully proven
  - transformed access detection still needs a deeper Pcode pass before we trust
    it for blind codegen
- current limitation: this stage still assigns broad families more reliably
  than exact semantic packet names

## Stage 5: Field Layout Recovery

Automate:

- classify parser reads by width and transform
- infer likely field order
- emit draft field files

Examples:

- `ubyte`
- `ushort`
- `ushortle`
- transformed byte/int variants
- bit-packed readers where appropriate

Output:

- draft `serverProt/*.txt`
- draft `clientProt/*.txt`
- `fieldCandidates.json`

Status:

- started
- current implementation: `run_946_phase4.py` emits `fieldRecoveryQueue.json`
  to prioritize named `946` packets that still lack field declaration files
- current implementation also emits `fieldGapAnalysis.json` so the queue can be
  cross-referenced against any matching `919` field file before touching Ghidra
- current safety rail: the phase now skips auto-field generation for the current
  do-not-touch blacklist (`PLAYER_INFO`, `NPC_INFO`, `REBUILD_NORMAL`)
- current limitation: field order and transform inference are still manual
  - next planned extractor requirement:
    - transformed reads must emit explicit unknown markers such as `byte_unknown`
      instead of guessed transforms when AST recovery is inconclusive

## Stage 6: Runtime Verification

Automate:

- boot OpenNXT with generated protocol data
- log packet registration gaps
- log client crash/init failures
- match missing runtime packets back to extractor evidence

Output:

- `runtimeVerification.md`
- `missingMappings.json`

Status:

- started
- current implementation: `run_946_phase4.py` emits
  `runtimeVerificationQueue.json`, `runtimeFocus.json`, and `phase4-summary.md`
- current helper entry points:
  - `trace_process_runtime.py`
  - `trace-win64c-runtime.ps1`
- current limitation: runtime verification is still queued and summarized rather
  than fully auto-executed end to end
- current safety rail: the verification prep path carries the do-not-touch
  blacklist forward so complex sync/rebuild packets are not silently
  auto-generated and overwritten

## Confidence Model

Every generated mapping should carry one of these labels:

- `confirmed`
  - parser-backed and runtime-verified
- `strong`
  - parser-backed with a clear family or semantic signature
- `candidate`
  - structurally likely, but not yet runtime-confirmed
- `unknown`
  - size/position only

That lets the pipeline emit useful draft files without pretending uncertain work is done.

## What Should Stay Manual

Do not try to fully automate these yet:

- final naming of ambiguous UI packets
- unusual login/bootstrap packets
- transport-layer shifts
- packets whose wrong field order will crash the client immediately

These should stay in a short manual confirmation pass after the automated run.

## Milestone Roadmap

## Phase 1: Extraction Foundation

Build one driver path that:

- finds registrars
- extracts size tables
- recovers initial parser/sender mappings
- writes JSON evidence and draft `*.toml`

Success:

- a new build can produce baseline draft protocol outputs in one command

## Phase 2: Parser and Sender Recovery

Expand descriptor-to-parser recovery so both server and client sides are
machine-readable enough to feed classification.

Success:

- parser/sender evidence is generated for most opcodes on both sides

## Phase 3: Semantic Naming

Classify families, emit confidence-scored name candidates, and promote only the
safe exact mappings into the working `946` protocol files.

Success:

- unresolved packets shrink into a small set of reviewable ambiguous clusters

## Phase 4: Field and Runtime Verification

Use the Phase 3 candidate output to recover field layouts, boot OpenNXT on the
generated protocol data, and feed runtime failures back into the extractor.

Success:

- runtime logs identify which generated mappings or field layouts are still
  wrong or missing

## Immediate Next Work

1. Finish the last ambiguous Phase 3 client resume/input names.
   - Current blocker:
     - `24`, `67`, and `93` still share the same raw-string sender shape
       and need a final callsite/runtime split.
2. Start the top of the Phase 4 field queue.
   - Best early targets are the highest-priority named packets without
     `946` field files in `fieldRecoveryQueue.json`.
3. Wire the Phase 4 runtime queue into a repeatable OpenNXT verification loop.
   - Use:
     - `trace_process_runtime.py`
     - `trace-win64c-runtime.ps1`
   - Goal:
     - prove or reject exact-name candidates from `runtimeVerificationQueue.json`

## Bottom Line

We do not need to reverse every packet by hand first.

We already have enough confirmed `946` anchors to automate most of the extraction
pipeline. What we still need is to turn the current helper-script collection into
one orchestrated workflow and keep a deliberate manual review pass for the tricky
parts.
