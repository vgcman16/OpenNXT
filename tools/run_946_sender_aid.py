from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from protocol_automation_common import (
    SHARED_DIR,
    WORKSPACE,
    artifact_input_fingerprint,
    cache_hit,
    ensure_directory,
    load_json,
    output_artifact_map,
    record_cache_entry,
    stable_json_text,
    standard_tool_artifact,
    write_json,
)
from protocol_946_debug_common import (
    DECOMP_LOG_DIR_DEFAULT,
    DEFAULT_GHIDRA_DIR,
    DEFAULT_SENDER_OPCODES,
    GHIDRA_CLONE_ROOT_DEFAULT,
    GHIDRA_PROJECT_DIR_DEFAULT,
    GHIDRA_PROJECT_NAME_DEFAULT,
    GHIDRA_PROGRAM_NAME_DEFAULT,
    GHIDRA_SCRIPTS_DEFAULT,
    HIGH_SIGNAL_HANDOFF_OPCODES,
    WORLD_LOG_DEFAULT,
    build_index,
    classify_headless_error,
    cleanup_ghidra_project_clone,
    clone_ghidra_project,
    decomp_status_for_path,
    decomp_status_for_text,
    evidence_sender_fields,
    extract_symbol_references,
    find_latest_session,
    load_phase_inputs,
    load_sender_analysis,
    observed_client_opcode_events,
    parse_world_log,
    phase3_sender_fields,
    read_text_best_effort,
    resolve_project_location,
    run_headless_postscript,
    sample_previews,
    stage_counts,
    unresolved_client_candidates,
)


SENDER_ANALYSIS_JSON = "sender-analysis.json"
SENDER_ANALYSIS_MD = "sender-analysis.md"
PER_OPCODE_DIR = "sender-aid"
SENDER_AID_CACHE_KEY = "sender-aid"
TOKEN_RE = re.compile(r"\b(CreatePacket|GetFocus|SetFocus|GetForegroundWindow|GetAsyncKeyState|SendMessage|PostMessage)\b")
FUNCTION_HEADER_RE = re.compile(r"Function:\s+(\S+)\s+@\s+([0-9A-Fa-f]+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate clean sender evidence for unresolved RS3 946 client opcodes.")
    parser.add_argument("--opcode", type=int, action="append", default=[])
    parser.add_argument("--handoff-json", type=Path, default=SHARED_DIR / "handoff-analysis.json")
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--ghidra-dir", type=Path, default=DEFAULT_GHIDRA_DIR)
    parser.add_argument("--ghidra-project-dir", type=Path, default=GHIDRA_PROJECT_DIR_DEFAULT)
    parser.add_argument("--ghidra-project-name", default=GHIDRA_PROJECT_NAME_DEFAULT)
    parser.add_argument("--ghidra-scripts", type=Path, default=GHIDRA_SCRIPTS_DEFAULT)
    parser.add_argument("--program-name", default=GHIDRA_PROGRAM_NAME_DEFAULT)
    parser.add_argument("--decomp-log-dir", type=Path, default=DECOMP_LOG_DIR_DEFAULT)
    parser.add_argument("--ghidra-clone-root", type=Path, default=GHIDRA_CLONE_ROOT_DEFAULT)
    parser.add_argument("--keep-ghidra-clone", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def handoff_suspect_index(handoff_payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    suspects = handoff_payload.get("suspects")
    if not isinstance(suspects, list):
        return {}
    return {
        int(entry["opcode"]): entry
        for entry in suspects
        if isinstance(entry, dict) and isinstance(entry.get("opcode"), int)
    }


def select_sender_opcodes(
    *,
    handoff_payload: dict[str, Any],
    unresolved: dict[int, dict[str, Any]],
    manual_opcodes: list[int],
) -> list[int]:
    suspect_index = handoff_suspect_index(handoff_payload)
    top_targets = handoff_payload.get("topTargets")
    selected: list[int] = []
    seen: set[int] = set()

    for opcode in manual_opcodes:
        if opcode in unresolved and opcode not in seen:
            selected.append(opcode)
            seen.add(opcode)

    if isinstance(top_targets, list):
        for entry in top_targets:
            if not isinstance(entry, dict) or entry.get("kind") != "client-opcode":
                continue
            opcode = entry.get("opcode")
            if isinstance(opcode, int) and opcode in unresolved and opcode not in seen:
                selected.append(opcode)
                seen.add(opcode)

    for opcode in DEFAULT_SENDER_OPCODES:
        if opcode in unresolved and (opcode in suspect_index or opcode in HIGH_SIGNAL_HANDOFF_OPCODES) and opcode not in seen:
            selected.append(opcode)
            seen.add(opcode)

    if not selected:
        for opcode in sorted(opcode for opcode in suspect_index if opcode in unresolved):
            if opcode not in seen:
                selected.append(opcode)
                seen.add(opcode)

    return selected


def latest_world_log_evidence(world_log: Path, opcode: int) -> dict[str, Any]:
    events = parse_world_log(world_log)
    session = find_latest_session(events)
    observed = observed_client_opcode_events(session).get(opcode, [])
    return {
        "observedCount": len(observed),
        "observedStageCounts": stage_counts(observed),
        "samplePreviews": sample_previews(observed),
    }


def write_text(path: Path, text: str) -> None:
    ensure_directory(path.parent)
    path.write_text(text, encoding="utf-8")


def summarize_caller_output(text: str) -> list[str]:
    lines = []
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("INFO ", "WARNING:", "WARN  ", "ERROR ")):
            continue
        if "GhidraScript" in stripped:
            continue
        if stripped.endswith("ghidra_scripts") or stripped.endswith("(HeadlessAnalyzer)"):
            continue
        if ":\\" in stripped and "FUN_" not in stripped and "caller" not in stripped.lower():
            continue
        lines.append(stripped)
    callerish = [
        line
        for line in lines
        if "FUN_" in line or "caller" in line.lower() or "CALL" in line or "opcode=" in line or "->" in line
    ]
    return (callerish or lines)[:24]


def normalize_address(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip().lower()
    return cleaned[2:] if cleaned.startswith("0x") else cleaned


def parse_reported_function_identity(text: str) -> dict[str, str]:
    match = FUNCTION_HEADER_RE.search(text)
    if not match:
        return {"name": "", "entry": ""}
    return {
        "name": match.group(1),
        "entry": normalize_address(match.group(2)),
    }


def parse_caller_refs(lines: list[str]) -> list[dict[str, Any]]:
    caller_refs: list[dict[str, Any]] = []
    for line in lines:
        parts = [part.strip() for part in line.split(",", 7)]
        if len(parts) != 8:
            continue
        opcode_value = parts[2] if parts[2] != "?" else ""
        size_value = parts[3] if parts[3] != "?" else ""
        caller_refs.append(
            {
                "fromAddress": parts[0],
                "packetAddress": parts[1],
                "opcode": int(opcode_value) if opcode_value.isdigit() else None,
                "size": int(size_value) if size_value.isdigit() else None,
                "referenceType": parts[4],
                "callerFunction": parts[5],
                "opcodeSource": parts[6],
                "sizeSource": parts[7],
            }
        )
    return caller_refs[:24]


def descriptor_evidence(body: str, caller_lines: list[str]) -> dict[str, Any]:
    symbols = extract_symbol_references(body)
    named_tokens = sorted(set(TOKEN_RE.findall(body)))[:16]
    helper_lines = [line for line in caller_lines if "FUN_" in line or "caller" in line.lower()][:8]
    return {
        "symbols": symbols,
        "namedTokens": named_tokens,
        "callerHighlights": helper_lines,
    }


def status_from_sources(
    *,
    sender_address: str,
    ghidra_available: bool,
    decomp_summary: dict[str, Any] | None,
    used_fallback: bool,
) -> str:
    if not sender_address:
        return "missing-sender"
    if decomp_summary and decomp_summary.get("status") == "clean":
        return "clean"
    if decomp_summary and decomp_summary.get("status") == "warning-only":
        return "warning-only"
    if decomp_summary and decomp_summary.get("status") == "error-only":
        return "error-only"
    if not ghidra_available and not used_fallback:
        return "missing-ghidra-project"
    if used_fallback and decomp_summary:
        return decomp_summary.get("status", "warning-only")
    return "error-only"


def try_read_fallback_log(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.exists():
        return None, ""
    text, _ = read_text_best_effort(path)
    return decomp_status_for_text(text), text


def analyze_sender(
    *,
    opcode: int,
    candidate: dict[str, Any],
    evidence_entry: dict[str, Any] | None,
    handoff_entry: dict[str, Any] | None,
    world_log: Path,
    ghidra_dir: Path,
    ghidra_project_dir: Path,
    ghidra_project_name: str,
    ghidra_scripts: Path,
    program_name: str,
    decomp_log_dir: Path,
    ghidra_clone_root: Path,
    keep_ghidra_clone: bool,
    output_dir: Path,
) -> dict[str, Any]:
    if evidence_entry:
        primary_sender, primary_sender_name, parser_target, parser_name = evidence_sender_fields(evidence_entry)
    else:
        primary_sender, primary_sender_name, parser_target, parser_name = phase3_sender_fields(candidate)

    sender_address = primary_sender or parser_target
    sender_name = primary_sender_name or parser_name
    packet_name = str(
        (evidence_entry or {}).get("packetName")
        or candidate.get("suggestedName")
        or ""
    )
    per_opcode_dir = output_dir / PER_OPCODE_DIR / f"opcode-{opcode}"
    ensure_directory(per_opcode_dir)

    ghidra_available = False
    fallback_used = False
    decomp_summary: dict[str, Any] | None = None
    caller_lines: list[str] = []
    raw_decomp_text = ""
    notes: list[str] = []
    error_kind = ""
    clone_strategy = "disposable-project-clone"
    clone_cleanup_status = "not-used"
    clone_cleanup_error = ""
    clone_info: dict[str, Any] | None = None
    resolved_function_name = ""
    resolved_function_entry = ""
    caller_lookup_address = normalize_address(sender_address)
    caller_lookup_function = sender_name
    caller_lookup_source = "requested-address"
    caller_refs: list[dict[str, Any]] = []

    if sender_address:
        try:
            resolve_project_location(ghidra_project_dir, ghidra_project_name)
            ghidra_available = (ghidra_dir / "support" / "analyzeHeadless.bat").exists()
        except FileNotFoundError:
            ghidra_available = False
            error_kind = "missing-source-project"

    if sender_address and ghidra_available:
        try:
            clone_info = clone_ghidra_project(
                project_dir=ghidra_project_dir,
                project_name=ghidra_project_name,
                clone_root=ghidra_clone_root,
                clone_label=f"sender-opcode-{opcode}",
            )
            decompile_result = run_headless_postscript(
                ghidra_dir=ghidra_dir,
                project_dir=Path(clone_info["cloneProjectDir"]),
                project_name=str(clone_info["cloneProjectName"]),
                script_name="DecompileFunction.java",
                script_args=[sender_address],
                script_path=ghidra_scripts,
                program_name=program_name,
                analyze=False,
            )
            raw_decomp_text = decompile_result["stdoutText"]
            write_text(per_opcode_dir / "decompile.stdout.log", decompile_result["stdoutText"])
            write_text(per_opcode_dir / "decompile.stderr.log", decompile_result["stderrText"])
            decomp_summary = decomp_status_for_text(decompile_result["stdoutText"] + "\n" + decompile_result["stderrText"])
            reported_identity = parse_reported_function_identity(decompile_result["stdoutText"] + "\n" + decompile_result["stderrText"])
            resolved_function_name = reported_identity["name"]
            resolved_function_entry = reported_identity["entry"]
            if decompile_result["returnCode"] != 0:
                notes.append(f"DecompileFunction.java returned {decompile_result['returnCode']}.")
            decompile_error = classify_headless_error(
                decompile_result["stdoutText"],
                decompile_result["stderrText"],
                decompile_result["returnCode"],
                output_exists=bool(decomp_summary.get("body")),
            )
            if decompile_error and not error_kind:
                error_kind = decompile_error

            requested_caller_result = run_headless_postscript(
                ghidra_dir=ghidra_dir,
                project_dir=Path(clone_info["cloneProjectDir"]),
                project_name=str(clone_info["cloneProjectName"]),
                script_name="DumpCallRefsForTarget.java",
                script_args=[sender_address],
                script_path=ghidra_scripts,
                program_name=program_name,
                analyze=False,
            )
            write_text(per_opcode_dir / "callers.requested.stdout.log", requested_caller_result["stdoutText"])
            write_text(per_opcode_dir / "callers.requested.stderr.log", requested_caller_result["stderrText"])
            caller_result = requested_caller_result
            caller_lines = summarize_caller_output(requested_caller_result["stdoutText"] + "\n" + requested_caller_result["stderrText"])
            caller_refs = parse_caller_refs(caller_lines)
            if (
                not caller_refs
                and resolved_function_entry
                and normalize_address(resolved_function_entry) != normalize_address(sender_address)
            ):
                resolved_caller_result = run_headless_postscript(
                    ghidra_dir=ghidra_dir,
                    project_dir=Path(clone_info["cloneProjectDir"]),
                    project_name=str(clone_info["cloneProjectName"]),
                    script_name="DumpCallRefsForTarget.java",
                    script_args=[resolved_function_entry],
                    script_path=ghidra_scripts,
                    program_name=program_name,
                    analyze=False,
                )
                write_text(per_opcode_dir / "callers.resolved.stdout.log", resolved_caller_result["stdoutText"])
                write_text(per_opcode_dir / "callers.resolved.stderr.log", resolved_caller_result["stderrText"])
                resolved_lines = summarize_caller_output(
                    resolved_caller_result["stdoutText"] + "\n" + resolved_caller_result["stderrText"]
                )
                resolved_refs = parse_caller_refs(resolved_lines)
                if resolved_refs:
                    caller_result = resolved_caller_result
                    caller_lines = resolved_lines
                    caller_refs = resolved_refs
                    caller_lookup_address = normalize_address(resolved_function_entry)
                    caller_lookup_function = resolved_function_name or caller_lookup_function
                    caller_lookup_source = "resolved-containing-function"
                    notes.append(
                        f"Caller lookup resolved {sender_address} inside {resolved_function_name or resolved_function_entry}."
                    )
            write_text(per_opcode_dir / "callers.stdout.log", caller_result["stdoutText"])
            write_text(per_opcode_dir / "callers.stderr.log", caller_result["stderrText"])
            caller_error = classify_headless_error(
                caller_result["stdoutText"],
                caller_result["stderrText"],
                caller_result["returnCode"],
                output_exists=bool(caller_lines),
            )
            if caller_error and not error_kind:
                error_kind = caller_error
        except FileNotFoundError:
            ghidra_available = False
            error_kind = "missing-source-project"
        except OSError as exc:
            error_kind = "project-lock" if "lock" in str(exc).lower() else "headless-failure"
            notes.append(f"Failed to create disposable Ghidra clone: {exc}")
        finally:
            cleanup = cleanup_ghidra_project_clone(clone_info, keep_clone=keep_ghidra_clone)
            clone_cleanup_status = cleanup["status"]
            clone_cleanup_error = cleanup.get("error", "")
            if clone_info:
                clone_strategy = str(clone_info.get("cloneStrategy", clone_strategy))
            if clone_cleanup_status == "cleanup-failed" and clone_cleanup_error:
                notes.append(f"Ghidra clone cleanup failed: {clone_cleanup_error}")
    elif sender_address:
        notes.append("Unlocked Ghidra project or analyzeHeadless.bat is missing; falling back to on-disk logs when available.")
        if not error_kind:
            error_kind = "headless-failure"

    if sender_address and (not decomp_summary or decomp_summary.get("status") != "clean"):
        fallback_path = decomp_log_dir / f"decomp-{sender_address}.log"
        fallback_summary, fallback_text = try_read_fallback_log(fallback_path)
        if fallback_summary and (fallback_summary.get("body") or not decomp_summary or decomp_summary.get("status") == "empty"):
            decomp_summary = fallback_summary
            raw_decomp_text = fallback_text
            fallback_used = True
            notes.append(f"Used fallback decomp log {fallback_path}.")
        caller_fallback_path = decomp_log_dir / f"callers-{sender_address}.log"
        if not caller_lines and caller_fallback_path.exists():
            caller_text, _ = read_text_best_effort(caller_fallback_path)
            caller_lines = summarize_caller_output(caller_text)
            fallback_used = True
            notes.append(f"Used fallback caller log {caller_fallback_path}.")

    if not decomp_summary:
        decomp_summary = {"status": "empty", "body": "", "snippet": [], "warnings": [], "errors": [], "symbols": {}}

    status = status_from_sources(
        sender_address=sender_address,
        ghidra_available=ghidra_available,
        decomp_summary=decomp_summary,
        used_fallback=fallback_used,
    )
    packet_size_evidence = handoff_entry or latest_world_log_evidence(world_log, opcode)
    descriptors = descriptor_evidence(decomp_summary.get("body", ""), caller_lines)

    return {
        "opcode": opcode,
        "side": "client",
        "packetName": packet_name,
        "suggestedName": str(candidate.get("suggestedName", "") or ""),
        "size": candidate.get("size"),
        "family": str((evidence_entry or {}).get("family") or candidate.get("familyLabel") or ""),
        "senderFunction": sender_name,
        "senderAddress": sender_address,
        "requestedSenderFunction": sender_name,
        "requestedSenderAddress": sender_address,
        "resolvedFunctionName": resolved_function_name,
        "resolvedFunctionEntry": resolved_function_entry,
        "callerLookupAddress": caller_lookup_address,
        "callerLookupFunction": caller_lookup_function,
        "callerLookupSource": caller_lookup_source,
        "status": status,
        "errorKind": error_kind or ("missing-sender" if not sender_address else ""),
        "cloneStrategy": clone_strategy,
        "cloneCleanupStatus": clone_cleanup_status,
        "cloneCleanupError": clone_cleanup_error,
        "usedFallbackLogs": fallback_used,
        "packetSizeEvidence": {
            "observedCount": packet_size_evidence.get("observedCount", 0),
            "observedStageCounts": packet_size_evidence.get("observedStageCounts", {}),
            "samplePreviews": packet_size_evidence.get("samplePreviews", []),
        },
        "decompiledBody": decomp_summary.get("body", ""),
        "decompSnippet": decomp_summary.get("snippet", []),
        "warnings": decomp_summary.get("warnings", []),
        "errors": decomp_summary.get("errors", []),
        "callerChain": caller_lines,
        "callerRefs": caller_refs,
        "descriptorEvidence": descriptors,
        "artifacts": {
            "perOpcodeDir": str(per_opcode_dir),
            "decompileStdoutLog": str(per_opcode_dir / "decompile.stdout.log"),
            "decompileStderrLog": str(per_opcode_dir / "decompile.stderr.log"),
            "callerStdoutLog": str(per_opcode_dir / "callers.stdout.log"),
            "callerStderrLog": str(per_opcode_dir / "callers.stderr.log"),
            "requestedCallerStdoutLog": str(per_opcode_dir / "callers.requested.stdout.log"),
            "requestedCallerStderrLog": str(per_opcode_dir / "callers.requested.stderr.log"),
            "resolvedCallerStdoutLog": str(per_opcode_dir / "callers.resolved.stdout.log"),
            "resolvedCallerStderrLog": str(per_opcode_dir / "callers.resolved.stderr.log"),
        },
        "notes": notes,
    }


def analyze_senders(args: argparse.Namespace) -> dict[str, Any]:
    phase_inputs = load_phase_inputs()
    generated_index = build_index(phase_inputs["generatedPackets"])
    verified_index = build_index(phase_inputs["verifiedPackets"])
    evidence_index = build_index(phase_inputs["evidenceIndex"])
    unresolved = unresolved_client_candidates(phase_inputs["phase3Candidates"], generated_index, verified_index)

    handoff_payload = load_sender_analysis(args.handoff_json)
    handoff_index = handoff_suspect_index(handoff_payload)
    selected_opcodes = select_sender_opcodes(
        handoff_payload=handoff_payload,
        unresolved=unresolved,
        manual_opcodes=sorted(set(args.opcode)),
    )

    senders: list[dict[str, Any]] = []
    for opcode in selected_opcodes:
        candidate = unresolved.get(opcode)
        if not candidate:
            continue
        evidence_entry = evidence_index.get(("client", opcode))
        handoff_entry = handoff_index.get(opcode)
        senders.append(
            analyze_sender(
                opcode=opcode,
                candidate=candidate,
                evidence_entry=evidence_entry,
                handoff_entry=handoff_entry,
                world_log=args.world_log,
                ghidra_dir=args.ghidra_dir,
                ghidra_project_dir=args.ghidra_project_dir,
                ghidra_project_name=args.ghidra_project_name,
                ghidra_scripts=args.ghidra_scripts,
                program_name=args.program_name,
                decomp_log_dir=args.decomp_log_dir,
                ghidra_clone_root=args.ghidra_clone_root,
                keep_ghidra_clone=args.keep_ghidra_clone,
                output_dir=args.output_dir,
            )
        )

    statuses = {entry["status"] for entry in senders}
    status = "ok"
    if senders and statuses != {"clean"}:
        status = "partial"
    if any(entry["status"] in {"missing-sender", "missing-ghidra-project", "error-only"} for entry in senders):
        status = "partial"
    return standard_tool_artifact(
        tool_name="run_946_sender_aid",
        status=status,
        inputs={
            "handoffJson": str(args.handoff_json),
            "worldLog": str(args.world_log),
            "ghidraDir": str(args.ghidra_dir),
            "ghidraProjectDir": str(args.ghidra_project_dir),
            "ghidraProjectName": args.ghidra_project_name,
            "ghidraCloneRoot": str(args.ghidra_clone_root),
            "decompLogDir": str(args.decomp_log_dir),
            "manualOpcodes": sorted(set(args.opcode)),
        },
        artifacts=output_artifact_map(args.output_dir, SENDER_ANALYSIS_JSON, SENDER_ANALYSIS_MD),
        summary={
            "selectedOpcodeCount": len(selected_opcodes),
            "senderCount": len(senders),
            "cleanCount": sum(1 for entry in senders if entry["status"] == "clean"),
            "partialCount": sum(1 for entry in senders if entry["status"] != "clean"),
        },
        extra={
            "selectedOpcodes": selected_opcodes,
            "senders": sorted(senders, key=lambda entry: entry["opcode"]),
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    lines = [
        "# 946 Sender Analysis",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Selected opcodes: `{artifact.get('selectedOpcodes', [])}`",
        "",
    ]
    senders = artifact.get("senders", [])
    if not senders:
        lines.append("- No sender candidates selected.")
        lines.append("")
        return "\n".join(lines)

    for entry in senders:
        name = entry["packetName"] or entry["suggestedName"] or "UNRESOLVED"
        lines.append(f"## Opcode {entry['opcode']} `{name}`")
        lines.append("")
        lines.append(f"- Status: `{entry['status']}`")
        lines.append(f"- Error kind: `{entry['errorKind']}`")
        lines.append(f"- Sender: `{entry['senderFunction'] or 'unknown'}` `{entry['senderAddress'] or ''}`")
        if entry.get("resolvedFunctionEntry"):
            lines.append(
                f"- Resolved function: `{entry.get('resolvedFunctionName') or 'unknown'}` `{entry.get('resolvedFunctionEntry')}`"
            )
        lines.append(
            f"- Caller lookup: source=`{entry.get('callerLookupSource', '')}` target=`{entry.get('callerLookupFunction') or 'unknown'}` `{entry.get('callerLookupAddress') or ''}`"
        )
        lines.append(f"- Size/family: `{entry['size']}` `{entry['family']}`")
        lines.append(
            f"- Clone: strategy=`{entry['cloneStrategy']}` cleanup=`{entry['cloneCleanupStatus']}`"
            + (f" error=`{entry['cloneCleanupError']}`" if entry.get("cloneCleanupError") else "")
        )
        lines.append(f"- Packet-size evidence: count=`{entry['packetSizeEvidence']['observedCount']}` stages=`{entry['packetSizeEvidence']['observedStageCounts']}`")
        if entry["descriptorEvidence"]["namedTokens"]:
            lines.append(f"- Named tokens: `{entry['descriptorEvidence']['namedTokens']}`")
        if entry["descriptorEvidence"]["symbols"]:
            lines.append(f"- Symbol references: `{entry['descriptorEvidence']['symbols']}`")
        if entry["callerChain"]:
            lines.append("- Caller chain:")
            for line in entry["callerChain"][:8]:
                lines.append(f"  - `{line}`")
        if entry["decompSnippet"]:
            lines.append("- Decomp snippet:")
            for line in entry["decompSnippet"][:8]:
                lines.append(f"  - `{line}`")
        if entry["notes"]:
            lines.append("- Notes:")
            for note in entry["notes"]:
                lines.append(f"  - {note}")
        lines.append("")
    return "\n".join(lines)


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> dict[str, str]:
    ensure_directory(output_dir)
    json_path = output_dir / SENDER_ANALYSIS_JSON
    markdown_path = output_dir / SENDER_ANALYSIS_MD
    write_json(json_path, artifact)
    markdown_path.write_text(render_markdown(artifact), encoding="utf-8")
    return {
        "json": str(json_path),
        "markdown": str(markdown_path),
    }


def input_fingerprint(args: argparse.Namespace) -> str:
    phase_inputs = load_phase_inputs()
    generated_index = build_index(phase_inputs["generatedPackets"])
    verified_index = build_index(phase_inputs["verifiedPackets"])
    evidence_index = build_index(phase_inputs["evidenceIndex"])
    unresolved = unresolved_client_candidates(phase_inputs["phase3Candidates"], generated_index, verified_index)
    handoff_payload = load_sender_analysis(args.handoff_json)
    selected_opcodes = select_sender_opcodes(
        handoff_payload=handoff_payload,
        unresolved=unresolved,
        manual_opcodes=sorted(set(args.opcode)),
    )
    relevant_paths = [
        WORKSPACE / "tools" / "run_946_sender_aid.py",
        WORKSPACE / "tools" / "protocol_automation_common.py",
        WORKSPACE / "tools" / "protocol_946_debug_common.py",
        args.handoff_json,
        args.world_log,
        SHARED_DIR / "evidence-index.json",
        SHARED_DIR / "verified-packets.json",
        SHARED_DIR.parent / "phase3" / "nameCandidates.json",
        SHARED_DIR.parent / "phase5" / "generatedPackets.json",
    ]
    for opcode in selected_opcodes:
        candidate = unresolved.get(opcode) or {}
        evidence_entry = evidence_index.get(("client", opcode))
        if evidence_entry:
            sender_address, _, parser_target, _ = evidence_sender_fields(evidence_entry)
        else:
            sender_address, _, parser_target, _ = phase3_sender_fields(candidate)
        address = sender_address or parser_target
        if address:
            relevant_paths.append(args.decomp_log_dir / f"decomp-{address}.log")
            relevant_paths.append(args.decomp_log_dir / f"callers-{address}.log")
    return artifact_input_fingerprint(
        "run_946_sender_aid",
        relevant_paths,
        selected_opcodes=selected_opcodes,
        ghidra_project_dir=args.ghidra_project_dir,
        ghidra_project_name=args.ghidra_project_name,
        keep_ghidra_clone=args.keep_ghidra_clone,
    )


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = [args.output_dir / SENDER_ANALYSIS_JSON, args.output_dir / SENDER_ANALYSIS_MD]
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, SENDER_AID_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / SENDER_ANALYSIS_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0
    artifact = analyze_senders(args)
    paths = write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, SENDER_AID_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": paths}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
