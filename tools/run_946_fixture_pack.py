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
from protocol_946_debug_common import WORLD_LOG_DEFAULT, load_all_sessions
from run_946_curated_compare import DEFAULT_LABELS_PATH, load_labels, session_window


FIXTURE_PACK_JSON = "fixture-pack.json"
FIXTURE_PACK_MD = "fixture-pack.md"
FIXTURE_PACK_CACHE_KEY = "fixture-pack"
DEFAULT_FIXTURE_DIR = PROT_DIR / "fixtures"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract labeled world-log windows into checked-in 946 fixture bundles.")
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_PATH)
    parser.add_argument("--window", action="append", default=[])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_FIXTURE_DIR)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def output_paths(output_dir: Path) -> list[Path]:
    return [
        output_dir / FIXTURE_PACK_JSON,
        output_dir / FIXTURE_PACK_MD,
    ]


def sanitize_window(window: str) -> str:
    return window.replace(":", "_")


def write_fixture(path: Path, session: dict[str, Any], label_entry: dict[str, Any]) -> None:
    write_json(
        path,
        {
            "window": session_window(session),
            "label": label_entry.get("label"),
            "normalizedOutcome": label_entry.get("normalizedOutcome"),
            "role": label_entry.get("role"),
            "note": label_entry.get("note"),
            "session": session,
        },
    )


def analyze_fixture_pack(args: argparse.Namespace) -> dict[str, Any]:
    labels_meta = load_labels(args.labels)
    sessions = {session_window(session): session for session in load_all_sessions(args.world_log)}
    requested_windows = set(args.window)
    fixtures: list[dict[str, Any]] = []
    blocked = False

    if not labels_meta["entries"]:
        blocked = True

    for window, label_entry in sorted(labels_meta["entries"].items()):
        if requested_windows and window not in requested_windows:
            continue
        session = sessions.get(window)
        if not session:
            fixtures.append(
                {
                    "window": window,
                    "status": "missing-session",
                    "label": label_entry.get("label"),
                    "normalizedOutcome": label_entry.get("normalizedOutcome"),
                }
            )
            blocked = True
            continue
        normalized = label_entry["normalizedOutcome"]
        fixture_path = args.output_dir / normalized / f"session_{sanitize_window(window)}.json"
        ensure_directory(fixture_path.parent)
        write_fixture(fixture_path, session, label_entry)
        fixtures.append(
            {
                "window": window,
                "status": "ok",
                "label": label_entry.get("label"),
                "normalizedOutcome": normalized,
                "role": label_entry.get("role"),
                "path": str(fixture_path),
                "eventCount": session.get("eventCount", 0),
            }
        )

    status = "blocked" if blocked else ("partial" if not fixtures else "ok")
    return standard_tool_artifact(
        tool_name="run_946_fixture_pack",
        status=status,
        inputs={
            "worldLog": str(args.world_log),
            "labels": str(args.labels),
            "requestedWindows": sorted(requested_windows),
        },
        artifacts=output_artifact_map(args.output_dir, FIXTURE_PACK_JSON, FIXTURE_PACK_MD),
        summary={
            "fixtureCount": sum(1 for row in fixtures if row["status"] == "ok"),
            "missingCount": sum(1 for row in fixtures if row["status"] != "ok"),
        },
        extra={
            "labels": {
                "path": labels_meta["path"],
                "format": labels_meta["format"],
                "present": labels_meta["present"],
                "appliedCount": len(fixtures),
            },
            "fixtures": fixtures,
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    lines = [
        "# 946 Fixture Pack",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Fixture count: `{artifact['summary']['fixtureCount']}`",
        f"- Missing count: `{artifact['summary']['missingCount']}`",
        "",
    ]
    for fixture in artifact.get("fixtures", []):
        if fixture["status"] == "ok":
            lines.append(
                f"- `{fixture['window']}` `{fixture['normalizedOutcome']}` role=`{fixture.get('role')}` path=`{fixture['path']}`"
            )
        else:
            lines.append(
                f"- `{fixture['window']}` missing session for label `{fixture['label']}`"
            )
    lines.append("")
    return "\n".join(lines)


def input_fingerprint(args: argparse.Namespace) -> str:
    return artifact_input_fingerprint(
        "run_946_fixture_pack",
        [
            WORKSPACE / "tools" / "run_946_fixture_pack.py",
            WORKSPACE / "tools" / "protocol_automation_common.py",
            args.world_log,
            args.labels,
        ],
        requested_windows=sorted(set(args.window)),
    )


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(output_dir)
    write_json(output_dir / FIXTURE_PACK_JSON, artifact)
    (output_dir / FIXTURE_PACK_MD).write_text(render_markdown(artifact), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cache_manifest_path = SHARED_DIR / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = output_paths(args.output_dir)
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, FIXTURE_PACK_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / FIXTURE_PACK_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0 if artifact.get("status") != "blocked" else 1

    artifact = analyze_fixture_pack(args)
    write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, FIXTURE_PACK_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0 if artifact["status"] != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
