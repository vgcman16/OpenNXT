from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

from protocol_automation_common import (
    DEFAULT_RUNTIME_PRIORITY_PACKETS,
    PHASE_DIRS,
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


RUNTIME_VERIFICATION_JSON = "runtime-verification-results.json"
RUNTIME_VERIFICATION_MD = "runtime-verification-results.md"
RUNTIME_VERIFIER_CACHE_KEY = "runtime-verifier"
SCENE_DELIVERY_JSON = "scene-delivery-analysis.json"
JS5_ARCHIVE_RESOLUTION_JSON = "js5-archive-resolution.json"
PLATEAU_DIFF_JSON = "plateau-diff.json"
BLACK_SCREEN_CAPTURE_JSON = "black-screen-capture.json"
DEFAULT_TESTS = [
    "com.opennxt.net.game.golden.GoldenPacketProtocolTest",
    "com.opennxt.model.lobby.LobbyBootstrapTest",
    "com.opennxt.net.game.generated.GeneratedPacketCatalogTest",
    "com.opennxt.net.game.generated.ConnectedClientInspectionDumpTest",
    "com.opennxt.net.game.generated.PriorityPacketInspectionDumpTest",
    "com.opennxt.net.game.generated.ProxyFallbackDumpTest",
]
DEFAULT_PYTHON_FIXTURE_TESTS = [
    "tools/test_946_phase4_fixtures.py",
    "tools/test_946_promotion_fixtures.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run targeted runtime verification for the 946 pipeline.")
    parser.add_argument("--shared-dir", type=Path, default=SHARED_DIR)
    parser.add_argument("--run-tests", action="store_true", default=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def output_paths(shared_dir: Path) -> list[Path]:
    return [
        shared_dir / RUNTIME_VERIFICATION_JSON,
        shared_dir / RUNTIME_VERIFICATION_MD,
    ]


def input_fingerprint(args: argparse.Namespace) -> str:
    relevant_paths = [
        WORKSPACE / "tools" / "run_946_runtime_verifier.py",
        WORKSPACE / "tools" / "protocol_automation_common.py",
        args.shared_dir / "evidence-index.json",
        PHASE_DIRS[5] / "generatedPackets.json",
        args.shared_dir / SCENE_DELIVERY_JSON,
        args.shared_dir / JS5_ARCHIVE_RESOLUTION_JSON,
        args.shared_dir / PLATEAU_DIFF_JSON,
        args.shared_dir / BLACK_SCREEN_CAPTURE_JSON,
        *[WORKSPACE / path for path in DEFAULT_PYTHON_FIXTURE_TESTS],
    ]
    return artifact_input_fingerprint(
        "run_946_runtime_verifier",
        relevant_paths,
        gradle_tests=DEFAULT_TESTS,
        python_fixture_tests=DEFAULT_PYTHON_FIXTURE_TESTS,
    )


def run_python_fixture_tests() -> tuple[bool, list[dict[str, Any]]]:
    python_results = []
    python_tests_passed = True
    for relative_path in DEFAULT_PYTHON_FIXTURE_TESTS:
        command = [sys.executable, str(WORKSPACE / relative_path)]
        completed = subprocess.run(
            command,
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            check=False,
        )
        python_results.append(
            {
                "command": command,
                "returnCode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        python_tests_passed = python_tests_passed and completed.returncode == 0
    return python_tests_passed, python_results


def gradle_test_command() -> list[str]:
    command = [
        ".\\gradlew.bat",
        "--no-daemon",
        "compileKotlin",
        "test",
    ]
    for test_name in DEFAULT_TESTS:
        command.extend(["--tests", test_name])
    return command


def run_gradle_runtime_suite() -> dict[str, Any]:
    command = gradle_test_command()
    completed = subprocess.run(
        command,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": command,
        "returnCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "passed": completed.returncode == 0,
    }


def runtime_packets(
    *,
    evidence_index: list[dict[str, Any]],
    generated_packets: list[dict[str, Any]],
    tests_passed: bool,
) -> list[dict[str, Any]]:
    generated_names = {entry["packetName"] for entry in generated_packets if isinstance(entry, dict) and entry.get("packetName")}
    packets = []
    for row in evidence_index:
        if row["packetName"] not in DEFAULT_RUNTIME_PRIORITY_PACKETS:
            continue
        gates = row.get("verification", row["proofGates"])
        generated_or_manual = row["hasManualRegistration"] or row["packetName"] in generated_names
        runtime_verified = (
            tests_passed
            and gates["fieldDeclarationExists"]
            and gates["widthMatches"]
            and gates["draftMatchesDeclaration"]
            and gates["legacyCompatible"]
            and gates["noUnknownFields"]
            and generated_or_manual
        )
        packets.append(
            {
                "packetName": row["packetName"],
                "side": row["side"],
                "opcode": row["opcode"],
                "fieldDeclarationExists": gates["fieldDeclarationExists"],
                "widthMatches": gates["widthMatches"],
                "draftMatchesDeclaration": gates["draftMatchesDeclaration"],
                "legacyCompatible": gates["legacyCompatible"],
                "noUnknownFields": gates["noUnknownFields"],
                "generatedOrManual": generated_or_manual,
                "runtimeVerified": runtime_verified,
                "proxyStructured": runtime_verified,
            }
        )
    return packets


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    evidence_index = load_json(args.shared_dir / "evidence-index.json", [])
    generated_packets = load_json(PHASE_DIRS[5] / "generatedPackets.json", [])
    scene_delivery = load_json(args.shared_dir / SCENE_DELIVERY_JSON, {}) or {}
    js5_archive_resolution = load_json(args.shared_dir / JS5_ARCHIVE_RESOLUTION_JSON, {}) or {}
    plateau_diff = load_json(args.shared_dir / PLATEAU_DIFF_JSON, {}) or {}
    black_screen_capture = load_json(args.shared_dir / BLACK_SCREEN_CAPTURE_JSON, {}) or {}
    python_tests_passed, python_results = run_python_fixture_tests()
    gradle_results = run_gradle_runtime_suite()
    tests_passed = python_tests_passed and gradle_results["passed"]
    packets = runtime_packets(
        evidence_index=evidence_index,
        generated_packets=generated_packets,
        tests_passed=tests_passed,
    )
    priority_verified_count = sum(1 for item in packets if item["runtimeVerified"])
    priority_proxy_count = sum(1 for item in packets if item["proxyStructured"])
    all_priority_verified = priority_verified_count == len(DEFAULT_RUNTIME_PRIORITY_PACKETS)
    all_priority_proxy = priority_proxy_count == len(DEFAULT_RUNTIME_PRIORITY_PACKETS)
    final_pass = tests_passed and all_priority_verified and all_priority_proxy
    status = "ok" if final_pass else "partial"
    return standard_tool_artifact(
        tool_name="run_946_runtime_verifier",
        status=status,
        inputs={
            "sharedDir": str(args.shared_dir),
            "runTests": bool(args.run_tests),
            "inputFingerprint": input_fingerprint(args),
            "gradleTests": DEFAULT_TESTS,
            "pythonFixtureTests": DEFAULT_PYTHON_FIXTURE_TESTS,
        },
        artifacts=output_artifact_map(args.shared_dir, RUNTIME_VERIFICATION_JSON, RUNTIME_VERIFICATION_MD),
        summary={
            "testsPassed": final_pass,
            "pythonFixturesPassed": python_tests_passed,
            "gradleTestsPassed": gradle_results["passed"],
            "priorityVerifiedCount": priority_verified_count,
            "priorityProxyStructuredCount": priority_proxy_count,
            "allPriorityVerified": all_priority_verified,
            "allPriorityProxyStructured": all_priority_proxy,
            "sceneDeliveryState": (scene_delivery.get("summary") or {}).get("sceneDeliveryState"),
            "sceneOverlapConfidence": (scene_delivery.get("summary") or {}).get("overlapConfidence"),
            "js5ResolutionStatus": js5_archive_resolution.get("status"),
            "plateauDiffStatus": plateau_diff.get("status"),
            "blackScreenCaptureStatus": black_screen_capture.get("status"),
        },
        extra={
            "pythonFixtures": python_results,
            "gradle": gradle_results,
            "packets": packets,
            "sceneJs5": {
                "sceneDelivery": {
                    "status": scene_delivery.get("status"),
                    "summary": scene_delivery.get("summary", {}),
                    "verdict": scene_delivery.get("verdict", {}),
                },
                "js5ArchiveResolution": {
                    "status": js5_archive_resolution.get("status"),
                    "summary": js5_archive_resolution.get("summary", {}),
                },
                "plateauDiff": {
                    "status": plateau_diff.get("status"),
                    "summary": plateau_diff.get("summary", {}),
                    "topHypothesis": ((plateau_diff.get("hypotheses") or [{}])[0] if plateau_diff.get("hypotheses") else {}),
                },
                "blackScreenCapture": {
                    "status": black_screen_capture.get("status"),
                    "summary": black_screen_capture.get("summary", {}),
                },
            },
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    lines = [
        "# 946 Runtime Verification",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Tests passed: `{artifact['summary']['testsPassed']}`",
        f"- Python fixtures passed: `{artifact['summary']['pythonFixturesPassed']}`",
        f"- Gradle tests passed: `{artifact['summary']['gradleTestsPassed']}`",
        f"- Priority verified count: `{artifact['summary']['priorityVerifiedCount']}`",
        f"- Priority proxy structured count: `{artifact['summary']['priorityProxyStructuredCount']}`",
        "",
        "## Scene/JS5",
        "",
        f"- Scene delivery state: `{artifact['summary'].get('sceneDeliveryState')}`",
        f"- Scene overlap confidence: `{artifact['summary'].get('sceneOverlapConfidence')}`",
        f"- JS5 archive resolution status: `{artifact['summary'].get('js5ResolutionStatus')}`",
        f"- Plateau diff status: `{artifact['summary'].get('plateauDiffStatus')}`",
        f"- Black-screen capture status: `{artifact['summary'].get('blackScreenCaptureStatus')}`",
        "",
        "## Packets",
        "",
    ]
    packets = artifact.get("packets", [])
    if not packets:
        lines.append("- No runtime packets evaluated.")
    else:
        for packet in packets:
            lines.append(
                f"- `{packet['packetName']}` opcode=`{packet['opcode']}` verified=`{packet['runtimeVerified']}` proxyStructured=`{packet['proxyStructured']}`"
            )
    lines.append("")
    return "\n".join(lines)


def write_artifacts(shared_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(shared_dir)
    write_json(shared_dir / RUNTIME_VERIFICATION_JSON, artifact)
    (shared_dir / RUNTIME_VERIFICATION_MD).write_text(render_markdown(artifact), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.shared_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    fingerprint = input_fingerprint(args)
    outputs = output_paths(args.shared_dir)
    if cache_hit(cache_manifest, RUNTIME_VERIFIER_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.shared_dir / RUNTIME_VERIFICATION_JSON, {})
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0 if artifact.get("summary", {}).get("testsPassed") else 1

    artifact = build_artifact(args)
    write_artifacts(args.shared_dir, artifact)
    record_cache_entry(cache_manifest, RUNTIME_VERIFIER_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0 if artifact["summary"]["testsPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
