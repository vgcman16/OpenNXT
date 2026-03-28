from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from protocol_automation_common import (
    DEFAULT_RUNTIME_PRIORITY_PACKETS,
    DO_NOT_TOUCH_PACKET_NAMES,
    FIELD_WIDTHS,
    GENERATED_DIR,
    PHASE_DIRS,
    PROT_DIR,
    REPO_ROOT,
    SHARED_DIR,
    WORKSPACE,
    build_fingerprint,
    collect_artifact_hashes,
    diff_hash_manifests,
    ensure_directory,
    field_width,
    file_fingerprint,
    load_json,
    manual_registered_packets,
    normalize_for_regression,
    parse_field_file,
    parse_names_toml,
    parse_sizes_toml,
    stable_json_text,
    total_field_width,
    write_json,
)
from run_946_handoff_aid import candidate_decomp_logs_for_selection


PIPELINE_PHASES = {
    1: "run_946_extraction.py",
    2: "run_946_phase2.py",
    3: "run_946_phase3.py",
    4: "run_946_phase4.py",
    5: "run_946_phase5.py",
}
PIPELINE_NAME = "946-automation-pipeline"
EXIT_BASELINE_DRIFT = 2
EXIT_RUNTIME_FAILURE = 3
EXIT_PHASE_FAILURE = 4
HANDOFF_PHASE = "handoff"
HANDOFF_SCRIPT = "run_946_handoff_aid.py"
HANDOFF_OUTPUTS = [
    SHARED_DIR / "handoff-analysis.json",
    SHARED_DIR / "handoff-analysis.md",
]
CURATED_COMPARE_PHASE = "curated-compare"
CURATED_COMPARE_SCRIPT = "run_946_curated_compare.py"
CURATED_COMPARE_LABELS = PROT_DIR / "curated-session-labels.json"
CURATED_COMPARE_OUTPUTS = [
    SHARED_DIR / "curated-compare.json",
    SHARED_DIR / "curated-compare.md",
]
OPCODE_113_PHASE = "opcode-113-verdict"
OPCODE_113_SCRIPT = "run_946_opcode_113_verdict.py"
OPCODE_113_OUTPUTS = [
    SHARED_DIR / "opcode-113-verdict.json",
    SHARED_DIR / "opcode-113-verdict.md",
]
SENDER_OUTPUTS = [
    SHARED_DIR / "sender-analysis.json",
    SHARED_DIR / "sender-analysis.md",
]
ACTIVE_SUB_OUTPUTS = [
    SHARED_DIR / "active-sub-analysis.json",
    SHARED_DIR / "active-sub-analysis.md",
]
INTERFACE_DIFF_OUTPUTS = [
    SHARED_DIR / "interface-diff.json",
    SHARED_DIR / "interface-diff.md",
]
TOOL_DOCTOR_PHASE = "tool-doctor"
TOOL_DOCTOR_SCRIPT = "run_946_tool_doctor.py"
TOOL_DOCTOR_OUTPUTS = [
    SHARED_DIR / "tool-doctor.json",
    SHARED_DIR / "tool-doctor.md",
]
SENDER_PHASE = "sender-aid"
SENDER_SCRIPT = "run_946_sender_aid.py"
ACTIVE_SUB_PHASE = "active-sub-aid"
ACTIVE_SUB_SCRIPT = "run_946_active_sub_aid.py"
INTERFACE_DIFF_PHASE = "interface-diff"
INTERFACE_DIFF_SCRIPT = "run_946_interface_diff.py"
SCENE_DELIVERY_PHASE = "scene-delivery-aid"
SCENE_DELIVERY_SCRIPT = "run_946_scene_delivery_aid.py"
SCENE_DELIVERY_OUTPUTS = [
    SHARED_DIR / "scene-delivery-analysis.json",
    SHARED_DIR / "scene-delivery-analysis.md",
]
JS5_ARCHIVE_RESOLVER_PHASE = "js5-archive-resolver"
JS5_ARCHIVE_RESOLVER_SCRIPT = "run_946_js5_archive_resolver.py"
JS5_ARCHIVE_RESOLVER_OUTPUTS = [
    SHARED_DIR / "js5-archive-resolution.json",
    SHARED_DIR / "js5-archive-resolution.md",
]
PLATEAU_DIFF_PHASE = "plateau-diff"
PLATEAU_DIFF_SCRIPT = "run_946_plateau_diff.py"
PLATEAU_DIFF_OUTPUTS = [
    SHARED_DIR / "plateau-diff.json",
    SHARED_DIR / "plateau-diff.md",
]
BLACK_SCREEN_CAPTURE_OUTPUTS = [
    SHARED_DIR / "black-screen-capture.json",
    SHARED_DIR / "black-screen-capture.md",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full RS3 build 946 automation pipeline.")
    parser.add_argument("--phase", type=int, choices=range(1, 6), action="append", default=[])
    parser.add_argument("--from-phase", type=int, choices=range(1, 6))
    parser.add_argument("--verify-runtime", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--extract-parser-fields-limit", type=int, default=0)
    return parser.parse_args()


def selected_phases(args: argparse.Namespace) -> list[int]:
    if args.phase:
        return sorted(set(args.phase))
    start = args.from_phase or 1
    return list(range(start, 6))


def phase_output_paths(phase: int) -> list[Path]:
    phase_dir = PHASE_DIRS[phase]
    mapping = {
        1: [
            phase_dir / "registrars.json",
            phase_dir / "serverProtSizes.generated.toml",
            phase_dir / "clientProtSizes.generated.toml",
        ],
        2: [
            phase_dir / "serverParsers.json",
            phase_dir / "clientParsers.json",
            phase_dir / "handlerFamilies.json",
            phase_dir / "handlerGraph.json",
            phase_dir / "helperSignatures.json",
        ],
        3: [
            phase_dir / "nameCandidates.json",
            phase_dir / "clientAmbiguousClusters.json",
            phase_dir / "serverProtNames.generated.toml",
            phase_dir / "clientProtNames.generated.toml",
        ],
        4: [
            phase_dir / "fieldGapAnalysis.json",
            phase_dir / "fieldRecoveryQueue.json",
            phase_dir / "runtimeVerificationQueue.json",
            phase_dir / "runtimeFocus.json",
            phase_dir / "parserFieldIndex.json",
        ],
        5: [
            phase_dir / "generatedPackets.json",
            phase_dir / "phase5-summary.md",
        ],
    }
    return mapping[phase]


def phase_input_fingerprint(phase: int, args: argparse.Namespace) -> str:
    relevant_paths = [
        WORKSPACE / "tools" / PIPELINE_PHASES[phase],
        WORKSPACE / "tools" / "protocol_automation_common.py",
        PROT_DIR / "serverProtNames.toml",
        PROT_DIR / "clientProtNames.toml",
    ]
    if phase >= 4:
        relevant_paths.extend((PROT_DIR / "serverProt").glob("*.txt"))
        relevant_paths.extend((PROT_DIR / "clientProt").glob("*.txt"))
        relevant_paths.append(PHASE_DIRS[4] / "manualFieldDraftOverrides.json")
    if phase >= 3:
        relevant_paths.append(SHARED_DIR / "cross-build-index.json")
    if phase == 5:
        relevant_paths.append(SHARED_DIR / "verified-packets.json")
    path_hashes = file_fingerprint(relevant_paths)
    return build_fingerprint(
        {
            "phase": str(phase),
            "extractParserFieldsLimit": str(args.extract_parser_fields_limit),
            "paths": stable_json_text(path_hashes),
        }
    )


def maybe_run_phase(phase: int, args: argparse.Namespace, cache_manifest: dict) -> dict:
    script_path = WORKSPACE / "tools" / PIPELINE_PHASES[phase]
    phase_dir = PHASE_DIRS[phase]
    ensure_directory(phase_dir)
    input_fingerprint = phase_input_fingerprint(phase, args)
    cache_entry = cache_manifest.get(str(phase), {})
    outputs = phase_output_paths(phase)

    if (
        not args.force
        and cache_entry.get("inputFingerprint") == input_fingerprint
        and all(path.exists() for path in outputs)
    ):
        return {
            "phase": phase,
            "status": "cached",
            "script": str(script_path),
            "inputFingerprint": input_fingerprint,
            "outputs": [str(path) for path in outputs],
        }

    command = [sys.executable, str(script_path)]
    if phase == 4 and args.extract_parser_fields_limit > 0:
        command.extend(["--extract-parser-fields-limit", str(args.extract_parser_fields_limit)])
    if phase == 5:
        command.extend(["--verified-input", str(SHARED_DIR / "verified-packets.json")])

    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        check=False,
    )
    duration_ms = round((time.time() - started) * 1000)

    phase_meta = {
        "phase": phase,
        "status": "ok" if completed.returncode == 0 else "failed",
        "script": str(script_path),
        "command": command,
        "inputFingerprint": input_fingerprint,
        "durationMs": duration_ms,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returnCode": completed.returncode,
        "outputs": [str(path) for path in outputs],
    }
    if completed.returncode != 0:
        raise RuntimeError(json.dumps(phase_meta, indent=2))
    cache_manifest[str(phase)] = {
        "inputFingerprint": input_fingerprint,
        "outputs": [str(path) for path in outputs],
    }
    return phase_meta


def handoff_input_fingerprint() -> str:
    world_log = WORKSPACE / "data" / "debug" / "world-bootstrap-raw.log"
    phase3_candidates = list(load_json(PHASE_DIRS[3] / "nameCandidates.json", []) or [])
    matched_decomp_logs = candidate_decomp_logs_for_selection(
        phase3_candidates=phase3_candidates,
        world_log_path=world_log,
        decomp_log_dir=REPO_ROOT / "ghidra-projects",
        manual_opcodes=[],
    )
    relevant_paths = [
        WORKSPACE / "tools" / HANDOFF_SCRIPT,
        WORKSPACE / "tools" / "protocol_automation_common.py",
        WORKSPACE / "tools" / "protocol_946_debug_common.py",
        PHASE_DIRS[3] / "nameCandidates.json",
        PHASE_DIRS[5] / "generatedPackets.json",
        SHARED_DIR / "verified-packets.json",
        SHARED_DIR / "evidence-index.json",
        world_log,
        SHARED_DIR / "sender-analysis.json",
        *matched_decomp_logs,
    ]
    path_hashes = file_fingerprint(relevant_paths)
    return build_fingerprint(
        {
            "phase": HANDOFF_PHASE,
            "worldLogExists": str(world_log.exists()),
            "matchedDecompLogs": stable_json_text([str(path) for path in matched_decomp_logs]),
            "paths": stable_json_text(path_hashes),
        }
    )


def maybe_run_handoff_aid(args: argparse.Namespace, cache_manifest: dict) -> dict:
    script_path = WORKSPACE / "tools" / HANDOFF_SCRIPT
    input_fingerprint = handoff_input_fingerprint()
    cache_entry = cache_manifest.get(HANDOFF_PHASE, {})
    if (
        not args.force
        and cache_entry.get("inputFingerprint") == input_fingerprint
        and all(path.exists() for path in HANDOFF_OUTPUTS)
    ):
        return {
            "phase": HANDOFF_PHASE,
            "status": "cached",
            "script": str(script_path),
            "inputFingerprint": input_fingerprint,
            "outputs": [str(path) for path in HANDOFF_OUTPUTS],
        }

    command = [sys.executable, str(script_path)]
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        check=False,
    )
    duration_ms = round((time.time() - started) * 1000)
    phase_meta = {
        "phase": HANDOFF_PHASE,
        "status": "ok" if completed.returncode == 0 else "failed",
        "script": str(script_path),
        "command": command,
        "inputFingerprint": input_fingerprint,
        "durationMs": duration_ms,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returnCode": completed.returncode,
        "outputs": [str(path) for path in HANDOFF_OUTPUTS],
    }
    if completed.returncode != 0:
        raise RuntimeError(json.dumps(phase_meta, indent=2))
    cache_manifest[HANDOFF_PHASE] = {
        "inputFingerprint": input_fingerprint,
        "outputs": [str(path) for path in HANDOFF_OUTPUTS],
    }
    return phase_meta


def curated_compare_input_fingerprint(labels_path: Path | None = None) -> str:
    world_log = WORKSPACE / "data" / "debug" / "world-bootstrap-raw.log"
    effective_labels = labels_path or CURATED_COMPARE_LABELS
    relevant_paths = [
        WORKSPACE / "tools" / CURATED_COMPARE_SCRIPT,
        WORKSPACE / "tools" / "protocol_automation_common.py",
        WORKSPACE / "tools" / "protocol_946_debug_common.py",
        WORKSPACE / "tools" / "run_946_interface_diff.py",
        world_log,
        effective_labels,
    ]
    path_hashes = file_fingerprint(relevant_paths)
    return build_fingerprint(
        {
            "phase": CURATED_COMPARE_PHASE,
            "labelsPath": str(effective_labels),
            "paths": stable_json_text(path_hashes),
        }
    )


def maybe_run_curated_compare(args: argparse.Namespace, cache_manifest: dict) -> dict:
    script_path = WORKSPACE / "tools" / CURATED_COMPARE_SCRIPT
    input_fingerprint = curated_compare_input_fingerprint()
    cache_entry = cache_manifest.get(CURATED_COMPARE_PHASE, {})
    if (
        not args.force
        and cache_entry.get("inputFingerprint") == input_fingerprint
        and all(path.exists() for path in CURATED_COMPARE_OUTPUTS)
    ):
        return {
            "phase": CURATED_COMPARE_PHASE,
            "status": "cached",
            "script": str(script_path),
            "inputFingerprint": input_fingerprint,
            "outputs": [str(path) for path in CURATED_COMPARE_OUTPUTS],
        }

    command = [sys.executable, str(script_path)]
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        check=False,
    )
    duration_ms = round((time.time() - started) * 1000)
    phase_meta = {
        "phase": CURATED_COMPARE_PHASE,
        "status": "ok" if completed.returncode == 0 else "failed",
        "script": str(script_path),
        "command": command,
        "inputFingerprint": input_fingerprint,
        "durationMs": duration_ms,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returnCode": completed.returncode,
        "outputs": [str(path) for path in CURATED_COMPARE_OUTPUTS],
    }
    if completed.returncode != 0:
        raise RuntimeError(json.dumps(phase_meta, indent=2))
    cache_manifest[CURATED_COMPARE_PHASE] = {
        "inputFingerprint": input_fingerprint,
        "outputs": [str(path) for path in CURATED_COMPARE_OUTPUTS],
    }
    return phase_meta


def opcode_113_input_fingerprint() -> str:
    relevant_paths = [
        WORKSPACE / "tools" / OPCODE_113_SCRIPT,
        WORKSPACE / "tools" / "protocol_automation_common.py",
        WORKSPACE / "tools" / "protocol_946_debug_common.py",
        SHARED_DIR / "sender-analysis.json",
        SHARED_DIR / "handoff-analysis.json",
        SHARED_DIR / "active-sub-analysis.json",
        WORKSPACE / "data" / "debug" / "world-bootstrap-raw.log",
    ]
    path_hashes = file_fingerprint(relevant_paths)
    return build_fingerprint(
        {
            "phase": OPCODE_113_PHASE,
            "paths": stable_json_text(path_hashes),
        }
    )


def maybe_run_opcode_113_verdict(args: argparse.Namespace, cache_manifest: dict) -> dict:
    script_path = WORKSPACE / "tools" / OPCODE_113_SCRIPT
    input_fingerprint = opcode_113_input_fingerprint()
    cache_entry = cache_manifest.get(OPCODE_113_PHASE, {})
    if (
        not args.force
        and cache_entry.get("inputFingerprint") == input_fingerprint
        and all(path.exists() for path in OPCODE_113_OUTPUTS)
    ):
        return {
            "phase": OPCODE_113_PHASE,
            "status": "cached",
            "script": str(script_path),
            "inputFingerprint": input_fingerprint,
            "outputs": [str(path) for path in OPCODE_113_OUTPUTS],
        }

    command = [sys.executable, str(script_path)]
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        check=False,
    )
    duration_ms = round((time.time() - started) * 1000)
    phase_meta = {
        "phase": OPCODE_113_PHASE,
        "status": "ok" if completed.returncode == 0 else "failed",
        "script": str(script_path),
        "command": command,
        "inputFingerprint": input_fingerprint,
        "durationMs": duration_ms,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returnCode": completed.returncode,
        "outputs": [str(path) for path in OPCODE_113_OUTPUTS],
    }
    if completed.returncode != 0:
        raise RuntimeError(json.dumps(phase_meta, indent=2))
    cache_manifest[OPCODE_113_PHASE] = {
        "inputFingerprint": input_fingerprint,
        "outputs": [str(path) for path in OPCODE_113_OUTPUTS],
    }
    return phase_meta


def parse_tool_stdout(stdout_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout_text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def run_advisory_tool(
    *,
    phase: str,
    script_name: str,
    outputs: list[Path],
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    script_path = WORKSPACE / "tools" / script_name
    command = [sys.executable, str(script_path), *(extra_args or [])]
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        check=False,
    )
    duration_ms = round((time.time() - started) * 1000)
    tool_result = parse_tool_stdout(completed.stdout)
    phase_status = tool_result.get("status") or ("ok" if completed.returncode == 0 else "failed")
    phase_meta = {
        "phase": phase,
        "status": phase_status,
        "script": str(script_path),
        "command": command,
        "durationMs": duration_ms,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returnCode": completed.returncode,
        "outputs": [str(path) for path in outputs],
    }
    if completed.returncode != 0:
        raise RuntimeError(json.dumps(phase_meta, indent=2))
    return phase_meta


def maybe_run_sender_aid() -> dict[str, Any]:
    return run_advisory_tool(
        phase=SENDER_PHASE,
        script_name=SENDER_SCRIPT,
        outputs=SENDER_OUTPUTS,
    )


def maybe_run_active_sub_aid() -> dict[str, Any]:
    return run_advisory_tool(
        phase=ACTIVE_SUB_PHASE,
        script_name=ACTIVE_SUB_SCRIPT,
        outputs=ACTIVE_SUB_OUTPUTS,
    )


def maybe_run_interface_diff(curated_compare: dict[str, Any] | None) -> dict[str, Any]:
    anchor_pair = (curated_compare or {}).get("anchorPair") or {}
    good_window = ((anchor_pair.get("goodSession") or {}).get("window"))
    bad_window = ((anchor_pair.get("badSession") or {}).get("window"))
    if not good_window or not bad_window:
        return {
            "phase": INTERFACE_DIFF_PHASE,
            "status": "skipped",
            "script": str(WORKSPACE / "tools" / INTERFACE_DIFF_SCRIPT),
            "reason": "missing-anchor-pair",
            "outputs": [str(path) for path in INTERFACE_DIFF_OUTPUTS],
        }
    return run_advisory_tool(
        phase=INTERFACE_DIFF_PHASE,
        script_name=INTERFACE_DIFF_SCRIPT,
        outputs=INTERFACE_DIFF_OUTPUTS,
        extra_args=[
            "--world-log",
            str(WORKSPACE / "data" / "debug" / "world-bootstrap-raw.log"),
            "--good-window",
            str(good_window),
            "--bad-window",
            str(bad_window),
        ],
    )


def maybe_run_tool_doctor() -> dict[str, Any]:
    return run_advisory_tool(
        phase=TOOL_DOCTOR_PHASE,
        script_name=TOOL_DOCTOR_SCRIPT,
        outputs=TOOL_DOCTOR_OUTPUTS,
    )


def maybe_run_scene_delivery_aid() -> dict[str, Any]:
    return run_advisory_tool(
        phase=SCENE_DELIVERY_PHASE,
        script_name=SCENE_DELIVERY_SCRIPT,
        outputs=SCENE_DELIVERY_OUTPUTS,
    )


def maybe_run_js5_archive_resolver() -> dict[str, Any]:
    return run_advisory_tool(
        phase=JS5_ARCHIVE_RESOLVER_PHASE,
        script_name=JS5_ARCHIVE_RESOLVER_SCRIPT,
        outputs=JS5_ARCHIVE_RESOLVER_OUTPUTS,
    )


def maybe_run_plateau_diff() -> dict[str, Any]:
    return run_advisory_tool(
        phase=PLATEAU_DIFF_PHASE,
        script_name=PLATEAU_DIFF_SCRIPT,
        outputs=PLATEAU_DIFF_OUTPUTS,
    )


def load_phase_data() -> dict:
    return {
        "phase1": {
            "registrars": load_json(PHASE_DIRS[1] / "registrars.json", {}),
            "serverSizes": parse_sizes_toml(PHASE_DIRS[1] / "serverProtSizes.generated.toml"),
            "clientSizes": parse_sizes_toml(PHASE_DIRS[1] / "clientProtSizes.generated.toml"),
        },
        "phase2": {
            "serverParsers": load_json(PHASE_DIRS[2] / "serverParsers.json", []),
            "clientParsers": load_json(PHASE_DIRS[2] / "clientParsers.json", []),
            "handlerFamilies": load_json(PHASE_DIRS[2] / "handlerFamilies.json", []),
            "handlerGraph": load_json(PHASE_DIRS[2] / "handlerGraph.json", []),
            "helperSignatures": load_json(PHASE_DIRS[2] / "helperSignatures.json", []),
        },
        "phase3": {
            "candidates": load_json(PHASE_DIRS[3] / "nameCandidates.json", []),
            "ambiguousClientClusters": load_json(PHASE_DIRS[3] / "clientAmbiguousClusters.json", []),
        },
        "phase4": {
            "fieldGapAnalysis": load_json(PHASE_DIRS[4] / "fieldGapAnalysis.json", []),
            "fieldRecoveryQueue": load_json(PHASE_DIRS[4] / "fieldRecoveryQueue.json", []),
            "runtimeVerificationQueue": load_json(PHASE_DIRS[4] / "runtimeVerificationQueue.json", []),
            "runtimeFocus": load_json(PHASE_DIRS[4] / "runtimeFocus.json", {}),
            "parserFieldIndex": load_json(PHASE_DIRS[4] / "parserFieldIndex.json", []),
        },
    }


def compute_phase1_health(phase1: dict) -> dict:
    registrars = phase1["registrars"]
    server = registrars.get("bestServerCandidate", {}) or {}
    client = registrars.get("bestClientCandidate", {}) or {}
    return {
        "programName": registrars.get("programName", ""),
        "candidateCount": registrars.get("candidateCount", 0),
        "server": {
            "entryPoint": server.get("entryPoint", ""),
            "stride": server.get("stride"),
            "contiguous": server.get("contiguous"),
            "status": "ok" if server.get("stride") == 80 and server.get("contiguous", 0) >= 160 else "suspicious",
        },
        "client": {
            "entryPoint": client.get("entryPoint", ""),
            "stride": client.get("stride"),
            "contiguous": client.get("contiguous"),
            "status": "ok" if client.get("stride") == 16 and client.get("contiguous", 0) >= 96 else "suspicious",
        },
    }


def default_cross_build_record(signature_hash: str = "") -> dict:
    return {
        "matchedFromBuild": None,
        "matchedOpcode": None,
        "matchedPacketName": "",
        "matchingBasis": "",
        "signatureHash": signature_hash,
        "confidence": 0.0,
    }


def evaluate_verification(
    *,
    size: int,
    packet_name: str,
    field_declaration: list[dict],
    draft_types: list[str],
    legacy_shape: list[str],
    runtime_verified: bool = False,
    proxy_structured: bool = False,
) -> tuple[dict, list[str], bool]:
    total_width = total_field_width(field_declaration)
    width_matches = size < 0 or (total_width is not None and total_width == size)
    draft_matches = not draft_types or draft_types == [field["type"] for field in field_declaration]
    no_unknown_fields = all(not field["type"].endswith("_unknown") for field in field_declaration) and all(
        not str(field_type).endswith("_unknown") for field_type in draft_types
    )
    legacy_compatible = not legacy_shape or len(legacy_shape) == len(field_declaration)

    conflicts: list[str] = []
    if field_declaration and not width_matches:
        conflicts.append("field-width-mismatch")
    if field_declaration and draft_types and not draft_matches:
        conflicts.append("draft-declaration-mismatch")
    if field_declaration and not no_unknown_fields:
        conflicts.append("unknown-field-types")
    if field_declaration and not legacy_compatible:
        conflicts.append("legacy-shape-conflict")

    verification = {
        "fieldDeclarationExists": bool(field_declaration),
        "widthMatches": width_matches,
        "draftMatchesDeclaration": draft_matches,
        "legacyCompatible": legacy_compatible,
        "noUnknownFields": no_unknown_fields,
        "runtimeVerified": runtime_verified,
        "proxyStructured": proxy_structured,
    }
    prelim_verified = bool(packet_name) and bool(field_declaration) and not conflicts and packet_name not in DO_NOT_TOUCH_PACKET_NAMES
    return verification, conflicts, prelim_verified


def build_cross_build_index(phase_data: dict, evidence_index: list[dict]) -> dict:
    registrars = phase_data["phase1"]["registrars"]
    phase1_payload = {
        "serverEntryPoint": registrars.get("bestServerCandidate", {}).get("entryPoint", ""),
        "serverStride": registrars.get("bestServerCandidate", {}).get("stride"),
        "serverContiguous": registrars.get("bestServerCandidate", {}).get("contiguous"),
        "clientEntryPoint": registrars.get("bestClientCandidate", {}).get("entryPoint", ""),
        "clientStride": registrars.get("bestClientCandidate", {}).get("stride"),
        "clientContiguous": registrars.get("bestClientCandidate", {}).get("contiguous"),
    }
    build_fp = build_fingerprint(
        {
            "build": "946",
            "phase1": stable_json_text(phase1_payload),
            "handlerGraph": stable_json_text(phase_data["phase2"]["handlerGraph"]),
            "helperSignatures": stable_json_text(phase_data["phase2"]["helperSignatures"]),
        }
    )

    helper_by_entry = {
        (entry.get("side", ""), entry.get("entryPoint", "")): entry
        for entry in phase_data["phase2"]["helperSignatures"]
        if entry.get("entryPoint")
    }

    packets: list[dict] = []
    for row in evidence_index:
        targets = row.get("targets", {})
        entry_point = (
            targets.get("parserTarget")
            or targets.get("primarySender")
            or targets.get("setupFunction")
            or ""
        )
        helper = helper_by_entry.get((row["side"], entry_point), {})
        cross_build = default_cross_build_record(helper.get("signatureHash", ""))
        packets.append(
            {
                "build": row["build"],
                "buildFingerprint": build_fp,
                "side": row["side"],
                "opcode": row["opcode"],
                "packetName": row["packetName"],
                "family": row["family"],
                "entryPoint": entry_point,
                "handlerGraph": targets,
                "signatureHash": helper.get("signatureHash", ""),
                "matchingBasis": "scaffold-only",
                "crossBuild": cross_build,
            }
        )

    packets.sort(key=lambda item: (item["side"], item["opcode"]))
    return {
        "sourceBuild": 946,
        "sourceBuildFingerprint": build_fp,
        "packets": packets,
    }


def build_evidence_index(phase_data: dict) -> list[dict]:
    server_names = parse_names_toml(PROT_DIR / "serverProtNames.toml")
    client_names = parse_names_toml(PROT_DIR / "clientProtNames.toml")
    parser_index = {row["packetName"]: row for row in phase_data["phase4"]["parserFieldIndex"]}
    gap_index = {(row["side"], row["opcode"]): row for row in phase_data["phase4"]["fieldGapAnalysis"]}
    server_parser_index = {row["opcode"]: row for row in phase_data["phase2"]["serverParsers"]}
    client_parser_index = {row["opcode"]: row for row in phase_data["phase2"]["clientParsers"]}
    helper_signature_index = {
        (row.get("side", ""), row.get("entryPoint", "")): row
        for row in phase_data["phase2"]["helperSignatures"]
        if row.get("entryPoint")
    }
    manual_packets = manual_registered_packets(WORKSPACE / "src" / "main" / "kotlin" / "com" / "opennxt" / "net" / "game" / "PacketRegistry.kt")

    records: list[dict] = []
    for candidate in phase_data["phase3"]["candidates"]:
        side = candidate["side"]
        opcode = candidate["opcode"]
        names = server_names if side == "server" else client_names
        packet_name = candidate["suggestedName"] or names.get(opcode, "")
        gap = gap_index.get((side, opcode), {})
        draft = parser_index.get(packet_name, {})
        parser_row = (
            server_parser_index.get(opcode, {})
            if side == "server"
            else client_parser_index.get(opcode, {})
        )
        field_path = PROT_DIR / ("serverProt" if side == "server" else "clientProt") / f"{packet_name}.txt"
        field_declaration = parse_field_file(field_path)
        total_width = total_field_width(field_declaration)
        draft_types = draft.get("candidateTypes", [])
        verification, conflicts, prelim_verified = evaluate_verification(
            size=candidate["size"],
            packet_name=packet_name,
            field_declaration=field_declaration,
            draft_types=draft_types,
            legacy_shape=gap.get("legacyShape", []) if gap.get("legacyReferenceAvailable") else [],
        )
        cross_build = dict(candidate.get("crossBuild") or default_cross_build_record())
        targets = {
            "setupFunction": parser_row.get("setupFunction", ""),
            "setupFunctionName": parser_row.get("setupFunctionName", ""),
            "dispatchMethod": parser_row.get("dispatchMethod", ""),
            "dispatchName": parser_row.get("dispatchName", ""),
            "parserTarget": parser_row.get("parserTarget", candidate.get("evidence", {}).get("parserTarget", "")),
            "parserName": parser_row.get("parserName", candidate.get("evidence", {}).get("parserName", "")),
            "primarySender": parser_row.get("primarySender", candidate.get("evidence", {}).get("primarySender", "")),
            "primarySenderName": parser_row.get("primarySenderName", candidate.get("evidence", {}).get("primarySenderName", "")),
        }
        entry_point = targets["parserTarget"] or targets["primarySender"] or targets["setupFunction"]
        helper_signature = helper_signature_index.get((side, entry_point), {})
        if not cross_build.get("signatureHash"):
            cross_build["signatureHash"] = helper_signature.get("signatureHash", "")
        status = "draft"
        if packet_name in DO_NOT_TOUCH_PACKET_NAMES:
            status = "blacklisted"
        elif prelim_verified:
            status = "verified"
        elif candidate["exactCandidateNames"] or candidate["familyLabel"]:
            status = "candidate"

        review_source = "manual"
        if draft:
            review_source = draft.get("reviewSource", "heuristic")

        record = {
            "build": 946,
            "side": side,
            "opcode": opcode,
            "size": candidate["size"],
            "packetName": packet_name,
            "family": candidate["familyLabel"],
            "registrar": {
                "serverEntryPoint": phase_data["phase1"]["registrars"].get("bestServerCandidate", {}).get("entryPoint", ""),
                "clientEntryPoint": phase_data["phase1"]["registrars"].get("bestClientCandidate", {}).get("entryPoint", ""),
            },
            "targets": targets,
            "fieldDraft": draft,
            "fieldDeclaration": {
                "path": str(field_path),
                "exists": field_path.exists(),
                "fields": field_declaration,
                "totalWidth": total_width,
            },
            "candidateNames": candidate["exactCandidateNames"],
            "confidence": {
                "label": candidate["confidence"],
                "score": candidate.get("confidenceScore", 0.0),
                "breakdown": candidate.get("scoreBreakdown", {}),
            },
            "provenance": [candidate["source"], candidate["familySource"], candidate["exactCandidateSource"]],
            "reviewSource": review_source,
            "crossBuild": cross_build,
            "status": status,
            "blacklistReason": DO_NOT_TOUCH_PACKET_NAMES.get(packet_name, ""),
            "conflicts": conflicts,
            "runtimePriority": packet_name in DEFAULT_RUNTIME_PRIORITY_PACKETS,
            "verification": verification,
            "proofGates": dict(verification),
            "hasManualRegistration": (side, packet_name) in manual_packets,
            "phase5Eligible": prelim_verified,
        }
        records.append(record)

    records.sort(key=lambda row: (row["side"], row["opcode"]))
    return records


def build_verified_entries(evidence_index: list[dict]) -> list[dict]:
    entries: list[dict] = []
    for row in evidence_index:
        if not row["phase5Eligible"]:
            continue
        entries.append(
            {
                "build": row["build"],
                "side": row["side"],
                "opcode": row["opcode"],
                "packetName": row["packetName"],
                "family": row["family"],
                "fieldDeclaration": row["fieldDeclaration"],
                "runtimePriority": row["runtimePriority"],
                "hasManualRegistration": row["hasManualRegistration"],
                "confidence": row["confidence"],
                "status": row["status"],
                "reviewSource": row["reviewSource"],
                "verification": row["verification"],
                "crossBuild": row["crossBuild"],
            }
        )
    entries.sort(key=lambda row: (row["side"], row["opcode"]))
    return entries


def build_promotion_status(evidence_index: list[dict], runtime_results: dict | None = None) -> list[dict]:
    runtime_index = {item["packetName"]: item for item in (runtime_results or {}).get("packets", [])}
    statuses: list[dict] = []
    for row in evidence_index:
        runtime_row = runtime_index.get(row["packetName"], {})
        status = row["status"]
        if status != "blacklisted" and runtime_row.get("runtimeVerified") and runtime_row.get("proxyStructured"):
            status = "promoted"
        statuses.append(
            {
                "side": row["side"],
                "opcode": row["opcode"],
                "packetName": row["packetName"],
                "status": status,
                "phase5Eligible": row["phase5Eligible"],
                "runtimePriority": row["runtimePriority"],
                "runtimeVerified": runtime_row.get("runtimeVerified", False),
                "proxyStructured": runtime_row.get("proxyStructured", False),
                "reviewSource": row["reviewSource"],
                "conflicts": row["conflicts"],
            }
        )
    return statuses


def apply_runtime_results(evidence_index: list[dict], runtime_results: dict | None) -> list[dict]:
    runtime_index = {item["packetName"]: item for item in (runtime_results or {}).get("packets", [])}
    for row in evidence_index:
        runtime_row = runtime_index.get(row["packetName"])
        if runtime_row:
            row["proofGates"]["runtimeVerified"] = runtime_row.get("runtimeVerified", False)
            row["proofGates"]["proxyStructured"] = runtime_row.get("proxyStructured", False)
            row["verification"] = dict(row["proofGates"])
    return evidence_index


def readiness_level(*, artifact: dict | None, production_gate: bool = False) -> str:
    if not artifact:
        return "experimental"
    if production_gate:
        return "production-ready" if artifact.get("status") == "ok" else "near-ready"
    return "near-ready" if artifact.get("status") in {"ok", "partial", "cached"} else "experimental"


def build_readiness_scorecard(
    *,
    runtime_results: dict | None,
    handoff_analysis: dict | None,
    sender_analysis: dict | None,
    curated_compare: dict | None,
    active_sub_analysis: dict | None,
    interface_diff: dict | None,
    scene_delivery: dict | None,
    js5_archive_resolution: dict | None,
    plateau_diff: dict | None,
    black_screen_capture: dict | None,
    tool_doctor: dict | None,
) -> list[dict[str, str]]:
    return [
        {
            "tool": "run_946_runtime_verifier",
            "level": readiness_level(artifact=runtime_results, production_gate=True),
            "reason": "Passing runtime verification is the strongest contract for this tool."
            if runtime_results
            else "Run with --verify-runtime to populate runtime verification.",
        },
        {
            "tool": "run_946_handoff_aid",
            "level": "near-ready" if handoff_analysis else "experimental",
            "reason": "Pipeline advisory artifact present." if handoff_analysis else "Artifact missing.",
        },
        {
            "tool": "run_946_sender_aid",
            "level": readiness_level(artifact=sender_analysis),
            "reason": "Standard artifact present." if sender_analysis else "Artifact missing.",
        },
        {
            "tool": "run_946_active_sub_aid",
            "level": readiness_level(artifact=active_sub_analysis),
            "reason": "Standard artifact present." if active_sub_analysis else "Artifact missing.",
        },
        {
            "tool": "run_946_interface_diff",
            "level": readiness_level(artifact=interface_diff),
            "reason": "Standard artifact present." if interface_diff else "Artifact missing or anchor pair unavailable.",
        },
        {
            "tool": "run_946_scene_delivery_aid",
            "level": readiness_level(artifact=scene_delivery),
            "reason": "Standard artifact present." if scene_delivery else "Artifact missing or no JS5/runtime correlation yet.",
        },
        {
            "tool": "run_946_js5_archive_resolver",
            "level": readiness_level(artifact=js5_archive_resolution),
            "reason": "Structured JS5 archive labels present." if js5_archive_resolution else "Artifact missing.",
        },
        {
            "tool": "run_946_plateau_diff",
            "level": readiness_level(artifact=plateau_diff),
            "reason": "Post-interfaces plateau comparison present." if plateau_diff else "Artifact missing.",
        },
        {
            "tool": "run_946_black_screen_capture",
            "level": readiness_level(artifact=black_screen_capture),
            "reason": "Capture bundle present." if black_screen_capture else "Capture bundle not created yet.",
        },
        {
            "tool": "run_946_curated_compare",
            "level": "production-ready" if (curated_compare or {}).get("advisoryReady") else ("near-ready" if curated_compare else "experimental"),
            "reason": "Labeled advisory-ready compare." if (curated_compare or {}).get("advisoryReady") else "Needs stronger labeled coverage.",
        },
        {
            "tool": "run_946_tool_doctor",
            "level": "production-ready" if (tool_doctor or {}).get("status") == "ok" else ("near-ready" if tool_doctor else "experimental"),
            "reason": "Doctor can validate current trust surfaces." if tool_doctor else "Doctor artifact missing.",
        },
    ]


def write_pipeline_manifest(
    shared_dir: Path,
    phase_runs: list[dict],
    phase1_health: dict,
    evidence_index: list[dict],
    cross_build_index: dict,
    handoff_analysis: dict | None,
    sender_analysis: dict | None,
    curated_compare: dict | None = None,
    opcode_113_verdict: dict | None = None,
    active_sub_analysis: dict | None = None,
    interface_diff: dict | None = None,
    scene_delivery: dict | None = None,
    js5_archive_resolution: dict | None = None,
    plateau_diff: dict | None = None,
    black_screen_capture: dict | None = None,
    tool_doctor: dict | None = None,
    runtime_results: dict | None = None,
    drift_summary: dict[str, Any] | None = None,
) -> dict:
    readiness_scorecard = build_readiness_scorecard(
        runtime_results=runtime_results,
        handoff_analysis=handoff_analysis,
        sender_analysis=sender_analysis,
        curated_compare=curated_compare,
        active_sub_analysis=active_sub_analysis,
        interface_diff=interface_diff,
        scene_delivery=scene_delivery,
        js5_archive_resolution=js5_archive_resolution,
        plateau_diff=plateau_diff,
        black_screen_capture=black_screen_capture,
        tool_doctor=tool_doctor,
    )
    manifest = {
        "pipeline": PIPELINE_NAME,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "phaseRuns": phase_runs,
        "phase1Health": phase1_health,
        "counts": {
            "totalPackets": len(evidence_index),
            "phase5Eligible": sum(1 for row in evidence_index if row["phase5Eligible"]),
            "runtimePriority": sum(1 for row in evidence_index if row["runtimePriority"]),
            "blacklisted": sum(1 for row in evidence_index if row["status"] == "blacklisted"),
            "crossBuildPackets": len(cross_build_index.get("packets", [])),
            "handoffSuspects": len((handoff_analysis or {}).get("suspects", [])),
            "handoffTopTargets": len((handoff_analysis or {}).get("topTargets", [])),
            "senderArtifacts": len((sender_analysis or {}).get("senders", [])),
            "activeSubTargets": len((active_sub_analysis or {}).get("targets", [])),
            "interfaceDiffFindings": len((interface_diff or {}).get("topFindings", [])),
            "sceneDeliveryPresent": bool(scene_delivery),
            "sceneDeliveryRelevantSessions": int((scene_delivery or {}).get("summary", {}).get("relevantJs5SessionCount", 0) or 0),
            "sceneDeliveryState": (scene_delivery or {}).get("summary", {}).get("sceneDeliveryState"),
            "js5ArchiveResolutionPresent": bool(js5_archive_resolution),
            "js5ArchiveResolvedCount": len((js5_archive_resolution or {}).get("resolutions", [])),
            "plateauDiffPresent": bool(plateau_diff),
            "blackScreenCapturePresent": bool(black_screen_capture),
            "curatedComparePresent": bool(curated_compare),
            "curatedCompareAdvisoryReady": bool((curated_compare or {}).get("advisoryReady", False)),
            "curatedCompareLabelsApplied": int((curated_compare or {}).get("labels", {}).get("appliedCount", 0) or 0),
            "curatedCompareRecommendedFeatures": len((curated_compare or {}).get("bestKnownBaseline", {}).get("recommendedFeatures", [])),
            "opcode113VerdictPresent": bool(opcode_113_verdict),
            "toolDoctorPresent": bool(tool_doctor),
        },
        "artifacts": {
            "crossBuildIndex": str(shared_dir / "cross-build-index.json"),
            "handoffAnalysisJson": str(shared_dir / "handoff-analysis.json"),
            "handoffAnalysisMarkdown": str(shared_dir / "handoff-analysis.md"),
            "senderAnalysisJson": str(shared_dir / "sender-analysis.json"),
            "senderAnalysisMarkdown": str(shared_dir / "sender-analysis.md"),
            "runtimeVerificationJson": str(shared_dir / "runtime-verification-results.json"),
            "runtimeVerificationMarkdown": str(shared_dir / "runtime-verification-results.md"),
            "curatedCompareJson": str(shared_dir / "curated-compare.json"),
            "curatedCompareMarkdown": str(shared_dir / "curated-compare.md"),
            "opcode113VerdictPresent": bool(opcode_113_verdict),
            "opcode113VerdictJson": str(shared_dir / "opcode-113-verdict.json"),
            "opcode113VerdictMarkdown": str(shared_dir / "opcode-113-verdict.md"),
            "activeSubAnalysisJson": str(shared_dir / "active-sub-analysis.json"),
            "activeSubAnalysisMarkdown": str(shared_dir / "active-sub-analysis.md"),
            "interfaceDiffJson": str(shared_dir / "interface-diff.json"),
            "interfaceDiffMarkdown": str(shared_dir / "interface-diff.md"),
            "sceneDeliveryJson": str(shared_dir / "scene-delivery-analysis.json"),
            "sceneDeliveryMarkdown": str(shared_dir / "scene-delivery-analysis.md"),
            "js5ArchiveResolutionJson": str(shared_dir / "js5-archive-resolution.json"),
            "js5ArchiveResolutionMarkdown": str(shared_dir / "js5-archive-resolution.md"),
            "plateauDiffJson": str(shared_dir / "plateau-diff.json"),
            "plateauDiffMarkdown": str(shared_dir / "plateau-diff.md"),
            "blackScreenCaptureJson": str(shared_dir / "black-screen-capture.json"),
            "blackScreenCaptureMarkdown": str(shared_dir / "black-screen-capture.md"),
            "toolDoctorJson": str(shared_dir / "tool-doctor.json"),
            "toolDoctorMarkdown": str(shared_dir / "tool-doctor.md"),
        },
        "curatedCompare": {
            "confidence": (curated_compare or {}).get("confidence"),
            "advisoryReady": (curated_compare or {}).get("advisoryReady"),
            "labelsPresent": (curated_compare or {}).get("labelsPresent"),
            "labelsApplied": (curated_compare or {}).get("labels", {}).get("appliedCount"),
            "seedSource": (curated_compare or {}).get("seedSource"),
            "anchorPairSource": (curated_compare or {}).get("anchorPairSource"),
        },
        "toolReadiness": readiness_scorecard,
    }
    if drift_summary:
        manifest["baselineDrift"] = drift_summary
    write_json(shared_dir / "pipeline-manifest.json", manifest)
    return manifest


def write_run_report(
    shared_dir: Path,
    phase_runs: list[dict],
    baseline_drift: list[dict],
    drift_summary: dict[str, Any],
    runtime_results: dict | None,
    handoff_analysis: dict | None,
    sender_analysis: dict | None,
    curated_compare: dict | None,
    opcode_113_verdict: dict | None,
    active_sub_analysis: dict | None,
    interface_diff: dict | None,
    scene_delivery: dict | None,
    js5_archive_resolution: dict | None,
    plateau_diff: dict | None,
    black_screen_capture: dict | None,
    tool_doctor: dict | None,
) -> None:
    readiness_scorecard = build_readiness_scorecard(
        runtime_results=runtime_results,
        handoff_analysis=handoff_analysis,
        sender_analysis=sender_analysis,
        curated_compare=curated_compare,
        active_sub_analysis=active_sub_analysis,
        interface_diff=interface_diff,
        scene_delivery=scene_delivery,
        js5_archive_resolution=js5_archive_resolution,
        plateau_diff=plateau_diff,
        black_screen_capture=black_screen_capture,
        tool_doctor=tool_doctor,
    )
    lines = [
        "# 946 Pipeline Run Report",
        "",
        f"- Generated: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "## Phase Runs",
        "",
    ]
    for row in phase_runs:
        lines.append(
            f"- Phase `{row['phase']}` status=`{row['status']}` durationMs=`{row.get('durationMs', 0)}`"
        )
    lines.extend(["", "## Baseline", ""])
    if baseline_drift:
        lines.append(f"- Drift detected: `{len(baseline_drift)}` artifact(s)")
        lines.append(f"- Informational only: `{drift_summary.get('informationalOnly', False)}`")
        if drift_summary.get("categories"):
            lines.append(f"- Drift categories: `{drift_summary['categories']}`")
        for item in baseline_drift[:12]:
            lines.append(f"- `{item['path']}`")
    else:
        lines.append("- No drift detected")
    lines.extend(["", "## Runtime Verification", ""])
    if runtime_results:
        lines.append(f"- Gradle tests passed: `{runtime_results.get('testsPassed', False)}`")
        lines.append(f"- Runtime verified packets: `{sum(1 for row in runtime_results.get('packets', []) if row.get('runtimeVerified'))}`")
        lines.append(f"- Structured proxy packets: `{sum(1 for row in runtime_results.get('packets', []) if row.get('proxyStructured'))}`")
    else:
        lines.append("- Runtime verification not requested")
    lines.extend(["", "## Handoff Aid", ""])
    if handoff_analysis:
        lines.append(f"- Status: `{handoff_analysis.get('status', 'missing')}`")
        lines.append(f"- Suspects: `{len(handoff_analysis.get('suspects', []))}`")
        lines.append(f"- Top targets: `{len(handoff_analysis.get('topTargets', []))}`")
        player_info = handoff_analysis.get("playerInfo", {})
        lines.append(f"- PLAYER_INFO needs review: `{player_info.get('needsReview', False)}`")
    else:
        lines.append("- Handoff analysis not available")
    lines.extend(["", "## Sender Aid", ""])
    if sender_analysis:
        lines.append(f"- Status: `{sender_analysis.get('status', 'missing')}`")
        lines.append(f"- Sender entries: `{len(sender_analysis.get('senders', []))}`")
    else:
        lines.append("- Sender analysis not available")
    lines.extend(["", "## Active-Sub Aid", ""])
    if active_sub_analysis:
        lines.append(f"- Status: `{active_sub_analysis.get('status', 'missing')}`")
        lines.append(f"- Targets: `{len(active_sub_analysis.get('targets', []))}`")
    else:
        lines.append("- Active-sub analysis not available")
    lines.extend(["", "## Interface Diff", ""])
    if interface_diff:
        lines.append(f"- Status: `{interface_diff.get('status', 'missing')}`")
        lines.append(f"- Findings: `{len(interface_diff.get('topFindings', []))}`")
        lines.append(f"- Verdict: `{(interface_diff.get('verdict') or {}).get('handoffOutcomeChanged', 'missing')}`")
    else:
        lines.append("- Interface diff not available")
    lines.extend(["", "## Scene Delivery Aid", ""])
    if scene_delivery:
        lines.append(f"- Status: `{scene_delivery.get('status', 'missing')}`")
        lines.append(f"- Relevant JS5 sessions: `{(scene_delivery.get('summary') or {}).get('relevantJs5SessionCount', 0)}`")
        lines.append(f"- Scene delivery state: `{(scene_delivery.get('summary') or {}).get('sceneDeliveryState', 'unknown')}`")
        lines.append(f"- Likely blocker: `{(scene_delivery.get('verdict') or {}).get('likelyBlocker', 'unknown')}`")
    else:
        lines.append("- Scene delivery aid not available")
    lines.extend(["", "## JS5 Archive Resolver", ""])
    if js5_archive_resolution:
        lines.append(f"- Status: `{js5_archive_resolution.get('status', 'missing')}`")
        lines.append(f"- Resolved archives: `{len(js5_archive_resolution.get('resolutions', []))}`")
    else:
        lines.append("- JS5 archive resolver not available")
    lines.extend(["", "## Plateau Diff", ""])
    if plateau_diff:
        lines.append(f"- Status: `{plateau_diff.get('status', 'missing')}`")
        lines.append(f"- Top hypothesis: `{((plateau_diff.get('hypotheses') or [{}])[0]).get('kind', 'unknown')}`")
    else:
        lines.append("- Plateau diff not available")
    lines.extend(["", "## Black Screen Capture", ""])
    if black_screen_capture:
        lines.append(f"- Status: `{black_screen_capture.get('status', 'missing')}`")
        lines.append(f"- World window: `{(black_screen_capture.get('summary') or {}).get('worldWindowSelected', '')}`")
        lines.append(f"- Overlap achieved: `{(black_screen_capture.get('summary') or {}).get('overlapAchieved', False)}`")
    else:
        lines.append("- Black-screen capture not available")
    lines.extend(["", "## Curated Compare", ""])
    if curated_compare:
        lines.append(f"- Status: `{curated_compare.get('status', 'missing')}`")
        lines.append(f"- Confidence: `{curated_compare.get('confidence', 'missing')}`")
        lines.append(f"- Advisory ready: `{curated_compare.get('advisoryReady', False)}`")
        lines.append(f"- Labels applied: `{curated_compare.get('labels', {}).get('appliedCount', 0)}`")
        lines.append(f"- Seed source: `{curated_compare.get('seedSource', 'missing')}`")
        lines.append(f"- Anchor pair source: `{curated_compare.get('anchorPairSource', 'missing')}`")
        lines.append(f"- Recommendation rationale: `{curated_compare.get('recommendationRationale', 'missing')}`")
    else:
        lines.append("- Curated compare not available")
    lines.extend(["", "## Opcode 113 Verdict", ""])
    if opcode_113_verdict:
        lines.append(f"- Status: `{opcode_113_verdict.get('status', 'missing')}`")
        lines.append(f"- Verdict: `{opcode_113_verdict.get('verdict', 'missing')}`")
        next_lead = opcode_113_verdict.get("nextLead") or {}
        if next_lead:
            lines.append(f"- Next lead: `{next_lead.get('opcode')}` `{next_lead.get('side', '')}`")
    else:
        lines.append("- Opcode 113 verdict not available")
    lines.extend(["", "## Tool Doctor", ""])
    if tool_doctor:
        lines.append(f"- Status: `{tool_doctor.get('status', 'missing')}`")
        lines.append(f"- Blocked: `{(tool_doctor.get('summary') or {}).get('blockedCount', 0)}`")
        lines.append(f"- Partial: `{(tool_doctor.get('summary') or {}).get('partialCount', 0)}`")
    else:
        lines.append("- Tool doctor not available")
    lines.extend(["", "## Tool Readiness", ""])
    for row in readiness_scorecard:
        lines.append(f"- `{row['tool']}` `{row['level']}` {row['reason']}")
    lines.append("")
    (shared_dir / "run-report.md").write_text("\n".join(lines), encoding="utf-8")


def regression_artifacts() -> list[Path]:
    artifacts = [
        PHASE_DIRS[1] / "registrars.json",
        PHASE_DIRS[1] / "serverProtSizes.generated.toml",
        PHASE_DIRS[1] / "clientProtSizes.generated.toml",
        PHASE_DIRS[2] / "serverParsers.json",
        PHASE_DIRS[2] / "clientParsers.json",
        PHASE_DIRS[2] / "handlerFamilies.json",
        PHASE_DIRS[2] / "handlerGraph.json",
        PHASE_DIRS[2] / "helperSignatures.json",
        PHASE_DIRS[3] / "nameCandidates.json",
        PHASE_DIRS[3] / "clientAmbiguousClusters.json",
        PHASE_DIRS[4] / "fieldGapAnalysis.json",
        PHASE_DIRS[4] / "parserFieldIndex.json",
        SHARED_DIR / "cross-build-index.json",
        SHARED_DIR / "evidence-index.json",
        SHARED_DIR / "handoff-analysis.json",
        SHARED_DIR / "handoff-analysis.md",
        SHARED_DIR / "sender-analysis.json",
        SHARED_DIR / "sender-analysis.md",
        SHARED_DIR / "runtime-verification-results.json",
        SHARED_DIR / "runtime-verification-results.md",
        SHARED_DIR / "curated-compare.json",
        SHARED_DIR / "curated-compare.md",
        SHARED_DIR / "opcode-113-verdict.json",
        SHARED_DIR / "opcode-113-verdict.md",
        SHARED_DIR / "active-sub-analysis.json",
        SHARED_DIR / "active-sub-analysis.md",
        SHARED_DIR / "interface-diff.json",
        SHARED_DIR / "interface-diff.md",
        SHARED_DIR / "scene-delivery-analysis.json",
        SHARED_DIR / "scene-delivery-analysis.md",
        SHARED_DIR / "js5-archive-resolution.json",
        SHARED_DIR / "js5-archive-resolution.md",
        SHARED_DIR / "plateau-diff.json",
        SHARED_DIR / "plateau-diff.md",
        SHARED_DIR / "black-screen-capture.json",
        SHARED_DIR / "black-screen-capture.md",
        SHARED_DIR / "tool-doctor.json",
        SHARED_DIR / "tool-doctor.md",
        SHARED_DIR / "promotion-status.json",
        SHARED_DIR / "verified-packets.json",
    ]
    return [path for path in artifacts if path.exists()]


def normalized_artifact_hashes() -> dict[str, dict]:
    manifest: dict[str, dict] = {}
    for path in regression_artifacts():
        if path.suffix == ".json":
            payload = normalize_for_regression(load_json(path))
            digest = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        else:
            digest = path.read_text(encoding="utf-8")
        manifest[str(path)] = {
            "sha256": build_fingerprint({"path": str(path), "content": digest}),
            "size": path.stat().st_size,
        }
    return manifest


def classify_drift_category(path_text: str) -> str:
    name = Path(path_text).name
    if name in {"verified-packets.json", "promotion-status.json", "generatedPackets.json"}:
        return "promotion-surface"
    if "runtime" in name:
        return "runtime-results"
    if name in {
        "handoff-analysis.json",
        "handoff-analysis.md",
        "handoff-diff.json",
        "handoff-diff.md",
        "sender-analysis.json",
        "sender-analysis.md",
        "curated-compare.json",
        "curated-compare.md",
        "opcode-113-verdict.json",
        "opcode-113-verdict.md",
        "active-sub-analysis.json",
        "active-sub-analysis.md",
        "interface-diff.json",
        "interface-diff.md",
        "scene-delivery-analysis.json",
        "scene-delivery-analysis.md",
        "js5-archive-resolution.json",
        "js5-archive-resolution.md",
        "plateau-diff.json",
        "plateau-diff.md",
        "black-screen-capture.json",
        "black-screen-capture.md",
        "tool-doctor.json",
        "tool-doctor.md",
        "pipeline-manifest.json",
        "run-report.md",
    }:
        return "shared-evidence"
    return "generated-analysis"


def summarize_drift_categories(baseline_drift: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    for item in baseline_drift:
        counts[classify_drift_category(item["path"])] += 1
    informational_categories = {"shared-evidence", "runtime-results"}
    return {
        "categories": dict(sorted(counts.items())),
        "informationalOnly": bool(baseline_drift)
        and set(counts).issubset(informational_categories),
    }


def main() -> int:
    args = parse_args()
    ensure_directory(SHARED_DIR)
    phases = selected_phases(args)
    cache_manifest_path = SHARED_DIR / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}

    phase_runs: list[dict] = []
    try:
        for phase in [phase for phase in phases if phase < 5]:
            phase_runs.append(maybe_run_phase(phase, args, cache_manifest))
            if phase == 4:
                phase_data = load_phase_data()
                evidence_index = build_evidence_index(phase_data)
                cross_build_index = build_cross_build_index(phase_data, evidence_index)
                write_json(SHARED_DIR / "cross-build-index.json", cross_build_index)
                write_json(SHARED_DIR / "evidence-index.json", evidence_index)
                write_json(SHARED_DIR / "verified-packets.json", {"entries": build_verified_entries(evidence_index)})
                write_json(SHARED_DIR / "phase1-health.json", compute_phase1_health(phase_data["phase1"]))
        if 5 in phases:
            phase_data = load_phase_data()
            evidence_index = build_evidence_index(phase_data)
            cross_build_index = build_cross_build_index(phase_data, evidence_index)
            write_json(SHARED_DIR / "cross-build-index.json", cross_build_index)
            write_json(SHARED_DIR / "evidence-index.json", evidence_index)
            write_json(SHARED_DIR / "verified-packets.json", {"entries": build_verified_entries(evidence_index)})
            phase_runs.append(maybe_run_phase(5, args, cache_manifest))
    except RuntimeError as exc:
        (SHARED_DIR / "run-meta.json").write_text(str(exc), encoding="utf-8")
        return EXIT_PHASE_FAILURE

    phase_data = load_phase_data()
    evidence_index = build_evidence_index(phase_data)
    cross_build_index = build_cross_build_index(phase_data, evidence_index)
    phase1_health = compute_phase1_health(phase_data["phase1"])
    write_json(SHARED_DIR / "cross-build-index.json", cross_build_index)
    write_json(SHARED_DIR / "evidence-index.json", evidence_index)
    write_json(SHARED_DIR / "verified-packets.json", {"entries": build_verified_entries(evidence_index)})

    runtime_results = None
    if args.verify_runtime:
        runtime_command = [sys.executable, str(WORKSPACE / "tools" / "run_946_runtime_verifier.py")]
        completed = subprocess.run(
            runtime_command,
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            check=False,
        )
        phase_runs.append(
            {
                "phase": "runtime",
                "status": "ok" if completed.returncode == 0 else "failed",
                "command": runtime_command,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "returnCode": completed.returncode,
            }
        )
        runtime_results = load_json(SHARED_DIR / "runtime-verification-results.json", {})
        if completed.returncode != 0:
            evidence_index = apply_runtime_results(evidence_index, runtime_results)
            write_json(SHARED_DIR / "evidence-index.json", evidence_index)
            write_json(cache_manifest_path, cache_manifest)
            write_json(SHARED_DIR / "promotion-status.json", build_promotion_status(evidence_index, runtime_results))
            write_pipeline_manifest(
                SHARED_DIR,
                phase_runs,
                phase1_health,
                evidence_index,
                cross_build_index,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                runtime_results,
            )
            return EXIT_RUNTIME_FAILURE

    evidence_index = apply_runtime_results(evidence_index, runtime_results)
    write_json(SHARED_DIR / "evidence-index.json", evidence_index)
    write_json(SHARED_DIR / "promotion-status.json", build_promotion_status(evidence_index, runtime_results))
    handoff_analysis = None
    sender_analysis = load_json(SHARED_DIR / "sender-analysis.json", {})
    curated_compare = load_json(SHARED_DIR / "curated-compare.json", {})
    opcode_113_verdict = load_json(SHARED_DIR / "opcode-113-verdict.json", {})
    active_sub_analysis = load_json(SHARED_DIR / "active-sub-analysis.json", {})
    interface_diff = load_json(SHARED_DIR / "interface-diff.json", {})
    scene_delivery = load_json(SHARED_DIR / "scene-delivery-analysis.json", {})
    js5_archive_resolution = load_json(SHARED_DIR / "js5-archive-resolution.json", {})
    plateau_diff = load_json(SHARED_DIR / "plateau-diff.json", {})
    black_screen_capture = load_json(SHARED_DIR / "black-screen-capture.json", {})
    tool_doctor = load_json(SHARED_DIR / "tool-doctor.json", {})
    if (PHASE_DIRS[5] / "generatedPackets.json").exists():
        try:
            phase_runs.append(maybe_run_handoff_aid(args, cache_manifest))
            handoff_analysis = load_json(SHARED_DIR / "handoff-analysis.json", {})
            phase_runs.append(maybe_run_sender_aid())
            sender_analysis = load_json(SHARED_DIR / "sender-analysis.json", {})
            phase_runs.append(maybe_run_curated_compare(args, cache_manifest))
            curated_compare = load_json(SHARED_DIR / "curated-compare.json", {})
            phase_runs.append(maybe_run_active_sub_aid())
            active_sub_analysis = load_json(SHARED_DIR / "active-sub-analysis.json", {})
            phase_runs.append(maybe_run_interface_diff(curated_compare))
            interface_diff = load_json(SHARED_DIR / "interface-diff.json", {})
            phase_runs.append(maybe_run_scene_delivery_aid())
            scene_delivery = load_json(SHARED_DIR / "scene-delivery-analysis.json", {})
            phase_runs.append(maybe_run_js5_archive_resolver())
            js5_archive_resolution = load_json(SHARED_DIR / "js5-archive-resolution.json", {})
            phase_runs.append(maybe_run_plateau_diff())
            plateau_diff = load_json(SHARED_DIR / "plateau-diff.json", {})
            phase_runs.append(maybe_run_opcode_113_verdict(args, cache_manifest))
            phase_runs.append(maybe_run_tool_doctor())
            tool_doctor = load_json(SHARED_DIR / "tool-doctor.json", {})
        except RuntimeError as exc:
            (SHARED_DIR / "run-meta.json").write_text(str(exc), encoding="utf-8")
            return EXIT_PHASE_FAILURE
        curated_compare = load_json(SHARED_DIR / "curated-compare.json", {})
        opcode_113_verdict = load_json(SHARED_DIR / "opcode-113-verdict.json", {})
        scene_delivery = load_json(SHARED_DIR / "scene-delivery-analysis.json", {})
        js5_archive_resolution = load_json(SHARED_DIR / "js5-archive-resolution.json", {})
        plateau_diff = load_json(SHARED_DIR / "plateau-diff.json", {})
        black_screen_capture = load_json(SHARED_DIR / "black-screen-capture.json", {})
    manifest = write_pipeline_manifest(
        SHARED_DIR,
        phase_runs,
        phase1_health,
        evidence_index,
        cross_build_index,
        handoff_analysis,
        sender_analysis,
        curated_compare,
        opcode_113_verdict,
        active_sub_analysis,
        interface_diff,
        scene_delivery,
        js5_archive_resolution,
        plateau_diff,
        black_screen_capture,
        tool_doctor,
        runtime_results,
    )

    artifact_hashes = normalized_artifact_hashes()
    baseline_path = SHARED_DIR / "regression-baseline.json"
    baseline = load_json(baseline_path, {}) or {}
    baseline_drift = diff_hash_manifests(artifact_hashes, baseline.get("artifacts", {})) if baseline else []
    drift_summary = summarize_drift_categories(baseline_drift)
    if args.update_baseline or not baseline:
        write_json(
            baseline_path,
            {
                "pipeline": PIPELINE_NAME,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "manifestFingerprint": build_fingerprint({"manifest": stable_json_text(normalize_for_regression(manifest))}),
                "artifacts": artifact_hashes,
            },
        )
        baseline_drift = []
        drift_summary = summarize_drift_categories(baseline_drift)

    write_pipeline_manifest(
        SHARED_DIR,
        phase_runs,
        phase1_health,
        evidence_index,
        cross_build_index,
        handoff_analysis,
        sender_analysis,
        curated_compare,
        opcode_113_verdict,
        active_sub_analysis,
        interface_diff,
        scene_delivery,
        js5_archive_resolution,
        plateau_diff,
        black_screen_capture,
        tool_doctor,
        runtime_results,
        drift_summary,
    )
    write_run_report(
        SHARED_DIR,
        phase_runs,
        baseline_drift,
        drift_summary,
        runtime_results,
        handoff_analysis,
        sender_analysis,
        curated_compare,
        opcode_113_verdict,
        active_sub_analysis,
        interface_diff,
        scene_delivery,
        js5_archive_resolution,
        plateau_diff,
        black_screen_capture,
        tool_doctor,
    )
    write_json(cache_manifest_path, cache_manifest)
    write_json(
        SHARED_DIR / "run-meta.json",
        {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "phaseRuns": phase_runs,
            "baselineDriftCount": len(baseline_drift),
        },
    )

    print(
        json.dumps(
            {
                "sharedDir": str(SHARED_DIR),
                "evidenceIndex": str(SHARED_DIR / "evidence-index.json"),
                "promotionStatus": str(SHARED_DIR / "promotion-status.json"),
                "verifiedPackets": str(SHARED_DIR / "verified-packets.json"),
                "crossBuildIndex": str(SHARED_DIR / "cross-build-index.json"),
                "handoffAnalysisJson": str(SHARED_DIR / "handoff-analysis.json"),
                "handoffAnalysisMarkdown": str(SHARED_DIR / "handoff-analysis.md"),
                "curatedComparePresent": bool(curated_compare),
                "curatedCompareJson": str(SHARED_DIR / "curated-compare.json"),
                "curatedCompareMarkdown": str(SHARED_DIR / "curated-compare.md"),
                "opcode113VerdictPresent": bool(opcode_113_verdict),
                "opcode113VerdictJson": str(SHARED_DIR / "opcode-113-verdict.json"),
                "opcode113VerdictMarkdown": str(SHARED_DIR / "opcode-113-verdict.md"),
                "activeSubAnalysisJson": str(SHARED_DIR / "active-sub-analysis.json"),
                "activeSubAnalysisMarkdown": str(SHARED_DIR / "active-sub-analysis.md"),
                "interfaceDiffJson": str(SHARED_DIR / "interface-diff.json"),
                "interfaceDiffMarkdown": str(SHARED_DIR / "interface-diff.md"),
                "sceneDeliveryJson": str(SHARED_DIR / "scene-delivery-analysis.json"),
                "sceneDeliveryMarkdown": str(SHARED_DIR / "scene-delivery-analysis.md"),
                "js5ArchiveResolutionJson": str(SHARED_DIR / "js5-archive-resolution.json"),
                "js5ArchiveResolutionMarkdown": str(SHARED_DIR / "js5-archive-resolution.md"),
                "plateauDiffJson": str(SHARED_DIR / "plateau-diff.json"),
                "plateauDiffMarkdown": str(SHARED_DIR / "plateau-diff.md"),
                "blackScreenCaptureJson": str(SHARED_DIR / "black-screen-capture.json"),
                "blackScreenCaptureMarkdown": str(SHARED_DIR / "black-screen-capture.md"),
                "toolDoctorJson": str(SHARED_DIR / "tool-doctor.json"),
                "toolDoctorMarkdown": str(SHARED_DIR / "tool-doctor.md"),
                "pipelineManifest": str(SHARED_DIR / "pipeline-manifest.json"),
                "regressionBaseline": str(baseline_path),
                "runReport": str(SHARED_DIR / "run-report.md"),
                "baselineDriftCount": len(baseline_drift),
                "baselineDriftCategories": drift_summary.get("categories", {}),
                "baselineDriftInformationalOnly": drift_summary.get("informationalOnly", False),
            },
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
