from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from protocol_automation_common import (
    PROT_DIR,
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
from protocol_946_debug_common import DECOMP_LOG_DIR_DEFAULT, DEFAULT_GHIDRA_DIR, WORLD_LOG_DEFAULT
from run_946_curated_compare import DEFAULT_LABELS_PATH


TOOL_DOCTOR_JSON = "tool-doctor.json"
TOOL_DOCTOR_MD = "tool-doctor.md"
TOOL_DOCTOR_CACHE_KEY = "tool-doctor"
PHASE3_CANDIDATES = PROT_DIR / "generated" / "phase3" / "nameCandidates.json"
PHASE5_PACKETS = PROT_DIR / "generated" / "phase5" / "generatedPackets.json"
VERIFIED_PACKETS = SHARED_DIR / "verified-packets.json"
EVIDENCE_INDEX = SHARED_DIR / "evidence-index.json"
CURATED_COMPARE_JSON = SHARED_DIR / "curated-compare.json"
SENDER_ANALYSIS_JSON = SHARED_DIR / "sender-analysis.json"
ACTIVE_SUB_JSON = SHARED_DIR / "active-sub-analysis.json"
INTERFACE_DIFF_JSON = SHARED_DIR / "interface-diff.json"
SCENE_DELIVERY_JSON = SHARED_DIR / "scene-delivery-analysis.json"
RUNTIME_VERIFIER_JSON = SHARED_DIR / "runtime-verification-results.json"
JS5_ARCHIVE_RESOLUTION_JSON = SHARED_DIR / "js5-archive-resolution.json"
PLATEAU_DIFF_JSON = SHARED_DIR / "plateau-diff.json"
BLACK_SCREEN_CAPTURE_JSON = SHARED_DIR / "black-screen-capture.json"
CLIENT_LIVE_WATCH_JSON = WORKSPACE / "data" / "debug" / "client-live-watch" / "latest-summary.json"
LOOPBACK_DOCTOR_JSON = SHARED_DIR / "loopback-doctor.json"
ATTEMPT_DIFF_JSON = SHARED_DIR / "attempt-diff.json"
READY_SIGNAL_DOCTOR_JSON = SHARED_DIR / "ready-signal-doctor.json"
POST_READY_CADENCE_DOCTOR_JSON = SHARED_DIR / "post-ready-cadence-doctor.json"
DISCONNECT_PIVOT_DOCTOR_JSON = SHARED_DIR / "disconnect-pivot-doctor.json"
SCRIPT_BURST_DOCTOR_JSON = SHARED_DIR / "script-burst-doctor.json"
SCENE_START_DOCTOR_JSON = SHARED_DIR / "scene-start-doctor.json"
POST_SCENE_OPCODE_DOCTOR_JSON = SHARED_DIR / "post-scene-opcode-doctor.json"
LIVE_VAR_PACKET_DOCTOR_JSON = SHARED_DIR / "live-var-packet-doctor.json"
FORCED_FALLBACK_PARITY_DOCTOR_JSON = SHARED_DIR / "forced-fallback-parity-doctor.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the active RS3 946 tooling prerequisites and advisory artifact freshness.")
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_PATH)
    parser.add_argument("--decomp-log-dir", type=Path, default=DECOMP_LOG_DIR_DEFAULT)
    parser.add_argument("--ghidra-dir", type=Path, default=DEFAULT_GHIDRA_DIR)
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def output_paths(output_dir: Path) -> list[Path]:
    return [
        output_dir / TOOL_DOCTOR_JSON,
        output_dir / TOOL_DOCTOR_MD,
    ]


def age_status(reference: Path, artifact: Path) -> str:
    if not reference.exists() or not artifact.exists():
        return "unknown"
    return "fresh" if artifact.stat().st_mtime >= reference.stat().st_mtime else "stale"


def requirement(
    name: str,
    path: Path,
    *,
    required: bool,
    kind: str,
    note: str = "",
    world_log: Path | None = None,
) -> dict[str, Any]:
    present = path.exists()
    status = "ok" if present else ("blocked" if required else "partial")
    result = {
        "name": name,
        "path": str(path),
        "kind": kind,
        "required": required,
        "present": present,
        "status": status,
        "note": note,
    }
    if present:
        result["size"] = path.stat().st_size
        if world_log is not None and path != world_log:
            result["freshness"] = age_status(world_log, path)
            if required and result["freshness"] == "stale":
                result["status"] = "partial"
    return result


def tool_readiness(world_log: Path) -> list[dict[str, Any]]:
    curated_compare = load_json(CURATED_COMPARE_JSON, {}) or {}
    sender = load_json(SENDER_ANALYSIS_JSON, {}) or {}
    active_sub = load_json(ACTIVE_SUB_JSON, {}) or {}
    interface_diff = load_json(INTERFACE_DIFF_JSON, {}) or {}
    scene_delivery = load_json(SCENE_DELIVERY_JSON, {}) or {}
    runtime = load_json(RUNTIME_VERIFIER_JSON, {}) or {}
    js5_archive_resolution = load_json(JS5_ARCHIVE_RESOLUTION_JSON, {}) or {}
    plateau_diff = load_json(PLATEAU_DIFF_JSON, {}) or {}
    black_screen_capture = load_json(BLACK_SCREEN_CAPTURE_JSON, {}) or {}
    client_live_watch = load_json(CLIENT_LIVE_WATCH_JSON, {}) or {}
    loopback_doctor = load_json(LOOPBACK_DOCTOR_JSON, {}) or {}
    attempt_diff = load_json(ATTEMPT_DIFF_JSON, {}) or {}
    ready_signal_doctor = load_json(READY_SIGNAL_DOCTOR_JSON, {}) or {}
    post_ready_cadence_doctor = load_json(POST_READY_CADENCE_DOCTOR_JSON, {}) or {}
    disconnect_pivot_doctor = load_json(DISCONNECT_PIVOT_DOCTOR_JSON, {}) or {}
    script_burst_doctor = load_json(SCRIPT_BURST_DOCTOR_JSON, {}) or {}
    scene_start_doctor = load_json(SCENE_START_DOCTOR_JSON, {}) or {}
    post_scene_opcode_doctor = load_json(POST_SCENE_OPCODE_DOCTOR_JSON, {}) or {}
    live_var_packet_doctor = load_json(LIVE_VAR_PACKET_DOCTOR_JSON, {}) or {}
    forced_fallback_parity_doctor = load_json(FORCED_FALLBACK_PARITY_DOCTOR_JSON, {}) or {}
    tool_rows = [
        {
            "tool": "run_946_pipeline",
            "level": "production-ready" if (SHARED_DIR / "pipeline-manifest.json").exists() else "near-ready",
            "reason": "Pipeline manifest present." if (SHARED_DIR / "pipeline-manifest.json").exists() else "Pipeline manifest missing.",
        },
        {
            "tool": "run_946_curated_compare",
            "level": "production-ready" if curated_compare.get("advisoryReady") else ("near-ready" if curated_compare else "experimental"),
            "reason": "Advisory-ready labeled compare." if curated_compare.get("advisoryReady") else "Needs stronger advisory coverage or labels.",
        },
        {
            "tool": "run_946_runtime_verifier",
            "level": "production-ready" if runtime.get("status") == "ok" else ("near-ready" if runtime else "experimental"),
            "reason": (
                "Standard artifact, passing verification, and scene/JS5 summary present."
                if runtime.get("status") == "ok"
                else "Artifact missing or not fully green."
            ),
        },
        {
            "tool": "run_946_sender_aid",
            "level": "near-ready" if sender else "experimental",
            "reason": "Standard artifact present." if sender else "Artifact missing.",
        },
        {
            "tool": "run_946_active_sub_aid",
            "level": "near-ready" if active_sub else "experimental",
            "reason": "Standard artifact present." if active_sub else "Artifact missing.",
        },
        {
            "tool": "run_946_interface_diff",
            "level": "near-ready" if interface_diff else "experimental",
            "reason": "Standard artifact present." if interface_diff else "Artifact missing.",
        },
        {
            "tool": "run_946_scene_delivery_aid",
            "level": "near-ready" if scene_delivery else "experimental",
            "reason": (
                "Artifact present, but the latest capture indicates a pre-login MITM route regression."
                if scene_delivery.get("verdict", {}).get("likelyBlocker") == "prelogin-route-regression"
                else (
                "Artifact present, but the latest canonical launch still bypassed the local content MITM route."
                if scene_delivery.get("verdict", {}).get("likelyBlocker") == "content-route-bypassed-local-mitm"
                else (
                "Artifact present, but the latest world session still needs overlapping JS5 capture."
                if scene_delivery.get("verdict", {}).get("likelyBlocker") == "capture-missing"
                else ("Standard artifact present." if scene_delivery else "Artifact missing.")
                )
                )
            ),
        },
        {
            "tool": "run_946_js5_archive_resolver",
            "level": "near-ready" if js5_archive_resolution else "experimental",
            "reason": "Structured JS5 archive labeling present." if js5_archive_resolution else "Artifact missing.",
        },
        {
            "tool": "run_946_plateau_diff",
            "level": "near-ready" if plateau_diff else "experimental",
            "reason": "Post-interfaces plateau comparison present." if plateau_diff else "Artifact missing.",
        },
        {
            "tool": "run_946_black_screen_capture",
            "level": "near-ready" if black_screen_capture else "experimental",
            "reason": (
                "Capture bundle present, but the latest run regressed before login."
                if ((black_screen_capture.get("summary") or {}).get("statusReason") == "prelogin-route-regression")
                else (
                "Capture bundle present, but the latest canonical run still bypassed the local content MITM route."
                if ((black_screen_capture.get("summary") or {}).get("statusReason") == "content-route-bypassed-local-mitm")
                else ("Capture bundle present." if black_screen_capture else "No capture bundle has been produced yet.")
                )
            ),
        },
        {
            "tool": "run_946_loopback_doctor",
            "level": "near-ready" if loopback_doctor else "experimental",
            "reason": (
                "Attempt-level loopback diagnosis is present."
                if loopback_doctor
                else "No loopback doctor artifact has been produced yet."
            ),
        },
        {
            "tool": "run_946_attempt_diff",
            "level": "near-ready" if attempt_diff else "experimental",
            "reason": (
                "Exact attempt-tail diffing is present."
                if attempt_diff
                else "No attempt diff artifact has been produced yet."
            ),
        },
        {
            "tool": "run_946_ready_signal_doctor",
            "level": "near-ready" if ready_signal_doctor else "experimental",
            "reason": (
                "Ready-signal latch/skip analysis is present."
                if ready_signal_doctor
                else "No ready-signal doctor artifact has been produced yet."
            ),
        },
        {
            "tool": "run_946_post_ready_cadence_doctor",
            "level": "near-ready" if post_ready_cadence_doctor else "experimental",
            "reason": (
                "Accepted-ready post-bootstrap cadence analysis is present."
                if post_ready_cadence_doctor
                else "No post-ready cadence doctor artifact has been produced yet."
            ),
        },
        {
            "tool": "run_946_disconnect_pivot_doctor",
            "level": "near-ready" if disconnect_pivot_doctor else "experimental",
            "reason": (
                "Disconnect-window dominant packet-family analysis is present."
                if disconnect_pivot_doctor
                else "No disconnect pivot doctor artifact has been produced yet."
            ),
        },
        {
            "tool": "run_946_script_burst_doctor",
            "level": "near-ready" if script_burst_doctor else "experimental",
            "reason": (
                "RUNCLIENTSCRIPT-family burst analysis is present."
                if script_burst_doctor
                else "No script burst doctor artifact has been produced yet."
            ),
        },
        {
            "tool": "run_946_scene_start_doctor",
            "level": "near-ready" if scene_start_doctor else "experimental",
            "reason": (
                "Accepted-ready plateau analysis is present with rebuild/ready/control ordering."
                if scene_start_doctor
                else "No scene-start doctor artifact has been produced yet."
            ),
        },
        {
            "tool": "run_946_post_scene_opcode_doctor",
            "level": "near-ready" if post_scene_opcode_doctor else "experimental",
            "reason": (
                "Late accepted-ready unresolved client opcode analysis is present."
                if post_scene_opcode_doctor
                else "No post-scene opcode doctor artifact has been produced yet."
            ),
        },
        {
            "tool": "run_946_live_var_packet_doctor",
            "level": "near-ready" if live_var_packet_doctor else "experimental",
            "reason": (
                "Latest plateau session is correlated against golden VARP traffic and candidate loading vars."
                if live_var_packet_doctor
                else "No live var packet doctor artifact has been produced yet."
            ),
        },
        {
            "tool": "run_946_forced_fallback_parity_doctor",
            "level": "near-ready" if forced_fallback_parity_doctor else "experimental",
            "reason": (
                "Forced fallback is compared against the stable/full WorldPlayer bootstrap families."
                if forced_fallback_parity_doctor
                else "No forced fallback parity doctor artifact has been produced yet."
            ),
        },
        {
            "tool": "watch_rs2client_live",
            "level": "near-ready" if client_live_watch else "experimental",
            "reason": (
                "Live watcher summary present with deep client-side evidence."
                if client_live_watch
                else "No live watcher summary has been produced yet."
            ),
        },
    ]
    freshness_paths = {
        "run_946_curated_compare": CURATED_COMPARE_JSON,
        "run_946_runtime_verifier": RUNTIME_VERIFIER_JSON,
        "run_946_sender_aid": SENDER_ANALYSIS_JSON,
        "run_946_active_sub_aid": ACTIVE_SUB_JSON,
        "run_946_interface_diff": INTERFACE_DIFF_JSON,
        "run_946_scene_delivery_aid": SCENE_DELIVERY_JSON,
        "run_946_js5_archive_resolver": JS5_ARCHIVE_RESOLUTION_JSON,
        "run_946_plateau_diff": PLATEAU_DIFF_JSON,
        "run_946_black_screen_capture": BLACK_SCREEN_CAPTURE_JSON,
        "run_946_loopback_doctor": LOOPBACK_DOCTOR_JSON,
        "run_946_attempt_diff": ATTEMPT_DIFF_JSON,
        "run_946_ready_signal_doctor": READY_SIGNAL_DOCTOR_JSON,
        "run_946_post_ready_cadence_doctor": POST_READY_CADENCE_DOCTOR_JSON,
        "run_946_disconnect_pivot_doctor": DISCONNECT_PIVOT_DOCTOR_JSON,
        "run_946_script_burst_doctor": SCRIPT_BURST_DOCTOR_JSON,
        "run_946_scene_start_doctor": SCENE_START_DOCTOR_JSON,
        "run_946_post_scene_opcode_doctor": POST_SCENE_OPCODE_DOCTOR_JSON,
        "run_946_live_var_packet_doctor": LIVE_VAR_PACKET_DOCTOR_JSON,
        "run_946_forced_fallback_parity_doctor": FORCED_FALLBACK_PARITY_DOCTOR_JSON,
        "watch_rs2client_live": CLIENT_LIVE_WATCH_JSON,
    }
    for row in tool_rows:
        artifact_path = freshness_paths.get(row["tool"])
        if artifact_path and artifact_path.exists():
            row["freshness"] = age_status(world_log, artifact_path)
    return tool_rows


def analyze_doctor(args: argparse.Namespace) -> dict[str, Any]:
    requirements = [
        requirement("world-log", args.world_log, required=True, kind="input", note="Primary historical session source."),
        requirement("phase3-name-candidates", PHASE3_CANDIDATES, required=True, kind="phase-output", world_log=args.world_log),
        requirement("phase5-generated-packets", PHASE5_PACKETS, required=True, kind="phase-output", world_log=args.world_log),
        requirement("shared-verified-packets", VERIFIED_PACKETS, required=True, kind="shared-output", world_log=args.world_log),
        requirement("shared-evidence-index", EVIDENCE_INDEX, required=True, kind="shared-output", world_log=args.world_log),
        requirement("curated-labels", args.labels, required=False, kind="labels"),
        requirement("decomp-log-dir", args.decomp_log_dir, required=False, kind="ghidra"),
        requirement("ghidra-headless", args.ghidra_dir / "support" / "analyzeHeadless.bat", required=False, kind="ghidra"),
        requirement("curated-compare", CURATED_COMPARE_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("sender-aid", SENDER_ANALYSIS_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("active-sub-aid", ACTIVE_SUB_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("interface-diff", INTERFACE_DIFF_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("scene-delivery-aid", SCENE_DELIVERY_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("js5-archive-resolver", JS5_ARCHIVE_RESOLUTION_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("plateau-diff", PLATEAU_DIFF_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("black-screen-capture", BLACK_SCREEN_CAPTURE_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("loopback-doctor", LOOPBACK_DOCTOR_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("attempt-diff", ATTEMPT_DIFF_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("ready-signal-doctor", READY_SIGNAL_DOCTOR_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("disconnect-pivot-doctor", DISCONNECT_PIVOT_DOCTOR_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("script-burst-doctor", SCRIPT_BURST_DOCTOR_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("scene-start-doctor", SCENE_START_DOCTOR_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("post-scene-opcode-doctor", POST_SCENE_OPCODE_DOCTOR_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("live-var-packet-doctor", LIVE_VAR_PACKET_DOCTOR_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("forced-fallback-parity-doctor", FORCED_FALLBACK_PARITY_DOCTOR_JSON, required=False, kind="advisory", world_log=args.world_log),
        requirement("client-live-watch", CLIENT_LIVE_WATCH_JSON, required=False, kind="advisory", world_log=args.world_log, note="Deep client-side live watch summary."),
        requirement("runtime-verifier", RUNTIME_VERIFIER_JSON, required=False, kind="verification", world_log=args.world_log),
    ]
    blocked_count = sum(1 for row in requirements if row["status"] == "blocked")
    partial_count = sum(1 for row in requirements if row["status"] == "partial")
    status = "blocked" if blocked_count else ("partial" if partial_count else "ok")
    return standard_tool_artifact(
        tool_name="run_946_tool_doctor",
        status=status,
        inputs={
            "worldLog": str(args.world_log),
            "labels": str(args.labels),
            "decompLogDir": str(args.decomp_log_dir),
            "ghidraDir": str(args.ghidra_dir),
        },
        artifacts=output_artifact_map(args.output_dir, TOOL_DOCTOR_JSON, TOOL_DOCTOR_MD),
        summary={
            "blockedCount": blocked_count,
            "partialCount": partial_count,
            "okCount": sum(1 for row in requirements if row["status"] == "ok"),
        },
        extra={
            "requirements": requirements,
            "toolReadiness": tool_readiness(args.world_log),
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    lines = [
        "# 946 Tool Doctor",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Blocked: `{artifact['summary']['blockedCount']}`",
        f"- Partial: `{artifact['summary']['partialCount']}`",
        "",
        "## Requirements",
        "",
    ]
    for row in artifact.get("requirements", []):
        freshness = f" freshness=`{row['freshness']}`" if row.get("freshness") else ""
        lines.append(
            f"- `{row['name']}` status=`{row['status']}` present=`{row['present']}`{freshness} path=`{row['path']}`"
        )
    lines.extend(["", "## Readiness", ""])
    for row in artifact.get("toolReadiness", []):
        freshness = f" freshness=`{row['freshness']}`" if row.get("freshness") else ""
        lines.append(f"- `{row['tool']}` `{row['level']}`{freshness} {row['reason']}")
    lines.append("")
    return "\n".join(lines)


def input_fingerprint(args: argparse.Namespace) -> str:
    return artifact_input_fingerprint(
        "run_946_tool_doctor",
        [
            WORKSPACE / "tools" / "run_946_tool_doctor.py",
            WORKSPACE / "tools" / "protocol_automation_common.py",
            args.world_log,
            args.labels,
            PHASE3_CANDIDATES,
            PHASE5_PACKETS,
            VERIFIED_PACKETS,
            EVIDENCE_INDEX,
            CURATED_COMPARE_JSON,
            SENDER_ANALYSIS_JSON,
            ACTIVE_SUB_JSON,
            INTERFACE_DIFF_JSON,
            SCENE_DELIVERY_JSON,
            JS5_ARCHIVE_RESOLUTION_JSON,
            PLATEAU_DIFF_JSON,
            BLACK_SCREEN_CAPTURE_JSON,
            LOOPBACK_DOCTOR_JSON,
            ATTEMPT_DIFF_JSON,
            READY_SIGNAL_DOCTOR_JSON,
            POST_SCENE_OPCODE_DOCTOR_JSON,
            SCRIPT_BURST_DOCTOR_JSON,
            SCENE_START_DOCTOR_JSON,
            LIVE_VAR_PACKET_DOCTOR_JSON,
            FORCED_FALLBACK_PARITY_DOCTOR_JSON,
            CLIENT_LIVE_WATCH_JSON,
            RUNTIME_VERIFIER_JSON,
            args.ghidra_dir / "support" / "analyzeHeadless.bat",
        ],
    )


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(output_dir)
    write_json(output_dir / TOOL_DOCTOR_JSON, artifact)
    (output_dir / TOOL_DOCTOR_MD).write_text(render_markdown(artifact), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = output_paths(args.output_dir)
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, TOOL_DOCTOR_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / TOOL_DOCTOR_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0 if artifact.get("status") != "blocked" else 1

    artifact = analyze_doctor(args)
    write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, TOOL_DOCTOR_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0 if artifact["status"] != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
