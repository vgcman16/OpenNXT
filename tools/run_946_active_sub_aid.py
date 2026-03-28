from __future__ import annotations

import argparse
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
    parse_field_file,
    record_cache_entry,
    stable_json_text,
    standard_tool_artifact,
    write_json,
)
from protocol_946_debug_common import (
    DEFAULT_GHIDRA_DIR,
    GHIDRA_CLONE_ROOT_DEFAULT,
    GHIDRA_PROJECT_DIR_DEFAULT,
    GHIDRA_PROJECT_NAME_DEFAULT,
    GHIDRA_PROGRAM_NAME_DEFAULT,
    GHIDRA_SCRIPTS_DEFAULT,
    build_index,
    classify_headless_error,
    cleanup_ghidra_project_clone,
    clone_ghidra_project,
    load_phase_inputs,
    resolve_project_location,
    run_headless_postscript,
    unresolved_server_candidates,
)


ACTIVE_SUB_JSON = "active-sub-analysis.json"
ACTIVE_SUB_MD = "active-sub-analysis.md"
ACTIVE_SUB_HEADLESS_TIMEOUT_SECONDS = 120
ACTIVE_SUB_CACHE_KEY = "active-sub-aid"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect unresolved IF_OPENSUB_ACTIVE_* server packets for build 946.")
    parser.add_argument("--opcode", type=int, action="append", default=[])
    parser.add_argument("--packet-name", action="append", default=[])
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    parser.add_argument("--ghidra-dir", type=Path, default=DEFAULT_GHIDRA_DIR)
    parser.add_argument("--ghidra-project-dir", type=Path, default=GHIDRA_PROJECT_DIR_DEFAULT)
    parser.add_argument("--ghidra-project-name", default=GHIDRA_PROJECT_NAME_DEFAULT)
    parser.add_argument("--ghidra-scripts", type=Path, default=GHIDRA_SCRIPTS_DEFAULT)
    parser.add_argument("--program-name", default=GHIDRA_PROGRAM_NAME_DEFAULT)
    parser.add_argument("--ghidra-clone-root", type=Path, default=GHIDRA_CLONE_ROOT_DEFAULT)
    parser.add_argument("--headless-timeout-seconds", type=int, default=ACTIVE_SUB_HEADLESS_TIMEOUT_SECONDS)
    parser.add_argument("--keep-ghidra-clone", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def active_sub_candidate_names(candidate: dict[str, Any]) -> list[str]:
    names: list[str] = []
    suggested = str(candidate.get("suggestedName", "") or "")
    if suggested:
        names.append(suggested)
    for name in candidate.get("exactCandidateNames", []):
        if isinstance(name, str) and name:
            names.append(name)
    return sorted(dict.fromkeys(name for name in names if name.startswith("IF_OPENSUB_ACTIVE_")))


def select_targets(args: argparse.Namespace) -> list[dict[str, Any]]:
    inputs = load_phase_inputs()
    generated_index = build_index(inputs["generatedPackets"])
    verified_index = build_index(inputs["verifiedPackets"])
    unresolved = unresolved_server_candidates(inputs["phase3Candidates"], generated_index, verified_index)

    manual_names = {name.upper() for name in args.packet_name}
    selected: list[dict[str, Any]] = []
    for opcode, candidate in sorted(unresolved.items()):
        candidate_names = active_sub_candidate_names(candidate)
        if not candidate_names and opcode not in {67, 116}:
            continue
        if args.opcode and opcode not in set(args.opcode):
            continue
        if manual_names and not manual_names.intersection(name.upper() for name in candidate_names):
            continue
        if opcode in {67, 116} or candidate_names:
            selected.append(candidate)
    return selected


def parser_target_for_candidate(candidate: dict[str, Any]) -> tuple[str, str]:
    evidence = candidate.get("evidence", {}) if isinstance(candidate.get("evidence"), dict) else {}
    target = str(evidence.get("parserTarget") or evidence.get("primarySender") or "")
    name = str(evidence.get("parserName") or evidence.get("primarySenderName") or "")
    return target, name


def known_sibling_field_types() -> dict[str, list[str]]:
    siblings: dict[str, list[str]] = {}
    sibling_specs = {
        "IF_OPENSUB_ACTIVE_OBJ": SHARED_DIR.parent.parent / "serverProt" / "IF_OPENSUB_ACTIVE_OBJ.txt",
        "IF_OPENSUB_ACTIVE_LOC": SHARED_DIR.parent / "phase4" / "parserFields" / "IF_OPENSUB_ACTIVE_LOC.json",
    }
    for name, path in sibling_specs.items():
        if path.suffix == ".txt" and path.exists():
            siblings[name] = [field["type"] for field in parse_field_file(path)]
        elif path.suffix == ".json" and path.exists():
            payload = load_json(path, {})
            siblings[name] = [field.get("candidateType", "") for field in payload.get("fields", []) if field.get("candidateType")]
    return siblings


def legacy_field_types(packet_name: str) -> list[str]:
    legacy_path = SHARED_DIR.parent.parent.parent / "919" / "serverProt" / f"{packet_name}.txt"
    if not legacy_path.exists():
        return []
    return [field["type"] for field in parse_field_file(legacy_path)]


def export_target(candidate: dict[str, Any], args: argparse.Namespace, export_root: Path) -> dict[str, Any]:
    opcode = int(candidate["opcode"])
    candidate_names = active_sub_candidate_names(candidate)
    packet_label = candidate_names[0] if candidate_names else f"OPCODE_{opcode}"
    parser_target, parser_name = parser_target_for_candidate(candidate)
    export_base = f"opcode-{opcode}_{packet_label}"
    export_json = export_root / "parserFields" / f"{export_base}.json"
    logs_dir = export_root / "parserFields" / "logs"
    ensure_directory(logs_dir)

    result = {
        "opcode": opcode,
        "packetNames": candidate_names,
        "parserTarget": parser_target,
        "parserName": parser_name,
        "exportedFieldTypes": [],
        "recoveryMode": "",
        "decompileAttempted": False,
        "decompileCompleted": False,
        "analysisNotes": [],
        "status": "missing-parser-target" if not parser_target else "pending",
        "errorKind": "missing-parser-target" if not parser_target else "",
        "cloneStrategy": "disposable-project-clone",
        "cloneCleanupStatus": "not-used",
        "cloneCleanupError": "",
        "notes": [],
        "artifacts": {
            "exportJson": str(export_json),
            "stdoutLog": str(logs_dir / f"{export_base}.stdout.log"),
            "stderrLog": str(logs_dir / f"{export_base}.stderr.log"),
        },
    }
    if not parser_target:
        result["notes"].append("No parser target was recovered for this opcode.")
        return result

    clone_info: dict[str, Any] | None = None
    try:
        resolve_project_location(args.ghidra_project_dir, args.ghidra_project_name)
    except FileNotFoundError:
        result["status"] = "export-failed"
        result["errorKind"] = "missing-source-project"
        result["notes"].append("Unlocked Ghidra project is missing.")
        return result

    if not (args.ghidra_dir / "support" / "analyzeHeadless.bat").exists():
        result["status"] = "export-failed"
        result["errorKind"] = "headless-failure"
        result["notes"].append("analyzeHeadless.bat is missing.")
        return result

    if export_json.exists():
        export_json.unlink()

    try:
        clone_info = clone_ghidra_project(
            project_dir=args.ghidra_project_dir,
            project_name=args.ghidra_project_name,
            clone_root=args.ghidra_clone_root,
            clone_label=f"active-sub-opcode-{opcode}",
        )
        result["cloneStrategy"] = str(clone_info.get("cloneStrategy", result["cloneStrategy"]))
        completed = run_headless_postscript(
            ghidra_dir=args.ghidra_dir,
            project_dir=Path(clone_info["cloneProjectDir"]),
            project_name=str(clone_info["cloneProjectName"]),
            script_name="ExportParserFields.java",
            script_args=[str(export_json), parser_target, packet_label],
            script_path=args.ghidra_scripts,
            program_name=args.program_name,
            analyze=args.analyze,
            timeout_seconds=args.headless_timeout_seconds,
        )
        Path(result["artifacts"]["stdoutLog"]).write_text(completed["stdoutText"], encoding="utf-8")
        Path(result["artifacts"]["stderrLog"]).write_text(completed["stderrText"], encoding="utf-8")
        error_kind = classify_headless_error(
            completed["stdoutText"],
            completed["stderrText"],
            completed["returnCode"],
            output_exists=export_json.exists(),
        )
        if error_kind:
            result["errorKind"] = error_kind
        if completed["returnCode"] != 0 or not export_json.exists():
            result["status"] = "export-failed"
            result["notes"].append(f"ExportParserFields.java returned {completed['returnCode']}.")
            if completed.get("timedOut"):
                result["notes"].append(
                    f"ExportParserFields.java exceeded the {args.headless_timeout_seconds}-second headless timeout."
                )
            return result
    except OSError as exc:
        result["status"] = "export-failed"
        result["errorKind"] = "project-lock" if "lock" in str(exc).lower() else "headless-failure"
        result["notes"].append(f"Failed to create disposable Ghidra clone: {exc}")
        return result
    finally:
        cleanup = cleanup_ghidra_project_clone(clone_info, keep_clone=args.keep_ghidra_clone)
        result["cloneCleanupStatus"] = cleanup["status"]
        result["cloneCleanupError"] = cleanup.get("error", "")
        if result["cloneCleanupStatus"] == "cleanup-failed" and result["cloneCleanupError"]:
            result["notes"].append(f"Ghidra clone cleanup failed: {result['cloneCleanupError']}")

    payload = load_json(export_json, {})
    result["recoveryMode"] = str(payload.get("recoveryMode", "") or "")
    result["decompileAttempted"] = bool(payload.get("decompileAttempted", False))
    result["decompileCompleted"] = bool(payload.get("decompileCompleted", False))
    result["analysisNotes"] = [str(note) for note in payload.get("analysisNotes", []) if isinstance(note, str)]
    field_types = [field.get("candidateType", "") for field in payload.get("fields", []) if field.get("candidateType")]
    result["exportedFieldTypes"] = field_types
    result["fieldCount"] = len(field_types)
    if field_types:
        result["status"] = "ok"
    else:
        result["status"] = "export-failed"
        if not result["errorKind"]:
            result["errorKind"] = "no-field-candidates"
    return result


def confidence_and_notes(field_types: list[str], sibling_types: dict[str, list[str]], legacy_types: list[str]) -> tuple[str, list[str]]:
    notes: list[str] = []
    if not field_types:
        return "low", ["No field candidates were recovered from ExportParserFields.java."]
    for sibling_name, sibling in sibling_types.items():
        if sibling and sibling == field_types:
            notes.append(f"Recovered field order matches named sibling {sibling_name}.")
            return "high", notes
        if sibling and len(sibling) == len(field_types):
            notes.append(f"Recovered field count matches named sibling {sibling_name}.")
    if legacy_types:
        if legacy_types == field_types:
            notes.append("Recovered field order matches the older-build declaration.")
            return "high", notes
        if len(legacy_types) == len(field_types):
            notes.append("Recovered field count matches the older-build declaration.")
            return "medium", notes
    if any(notes):
        return "medium", notes
    return "medium", ["Field recovery is structurally consistent but semantics remain inferred."]


def write_draft_field_file(draft_dir: Path, opcode: int, candidate_names: list[str], field_types: list[str]) -> str:
    ensure_directory(draft_dir)
    label = "__OR__".join(candidate_names) if candidate_names else f"OPCODE_{opcode}"
    path = draft_dir / f"opcode-{opcode}_{label}.txt"
    lines = [f"# opcode={opcode}", f"# candidates={','.join(candidate_names) if candidate_names else 'unknown'}"]
    for index, field_type in enumerate(field_types):
        lines.append(f"value{index} {field_type}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def analyze_active_sub(args: argparse.Namespace) -> dict[str, Any]:
    export_root = args.output_dir / "active-sub-exports"
    draft_dir = args.output_dir / "active-sub-drafts"
    sibling_types = known_sibling_field_types()
    targets = select_targets(args)
    entries: list[dict[str, Any]] = []
    for candidate in targets:
        exported = export_target(candidate, args, export_root)
        legacy_types = []
        for name in exported["packetNames"]:
            legacy_types = legacy_field_types(name)
            if legacy_types:
                break
        confidence, notes = confidence_and_notes(exported["exportedFieldTypes"], sibling_types, legacy_types)
        exported["confidence"] = confidence
        exported["comparison"] = {
            "namedSiblings": sibling_types,
            "legacyFieldTypes": legacy_types,
        }
        exported["notes"].extend(notes)
        exported["recommendedNextAction"] = (
            "Use this draft as evidence only; compare it against IF_OPENSUB_ACTIVE_OBJ/LOC and decide whether the opcode is PLAYER or NPC bound."
            if exported["status"] == "ok"
            else "Recover a valid parser export before drafting server field declarations."
        )
        exported["draftFieldFile"] = write_draft_field_file(
            draft_dir,
            exported["opcode"],
            exported["packetNames"],
            exported["exportedFieldTypes"],
        )
        entries.append(exported)

    status = "ok"
    if any(entry["status"] != "ok" for entry in entries):
        status = "partial"
    return standard_tool_artifact(
        tool_name="run_946_active_sub_aid",
        status=status,
        inputs={
            "phase3NameCandidates": str(SHARED_DIR.parent / "phase3" / "nameCandidates.json"),
            "phase5GeneratedPackets": str(SHARED_DIR.parent / "phase5" / "generatedPackets.json"),
            "sharedVerifiedPackets": str(SHARED_DIR / "verified-packets.json"),
            "sharedEvidenceIndex": str(SHARED_DIR / "evidence-index.json"),
            "manualOpcodes": sorted(set(args.opcode)),
            "packetNames": sorted(set(args.packet_name)),
            "analyze": bool(args.analyze),
            "headlessTimeoutSeconds": args.headless_timeout_seconds,
        },
        artifacts=output_artifact_map(args.output_dir, ACTIVE_SUB_JSON, ACTIVE_SUB_MD),
        summary={
            "targetCount": len(entries),
            "okCount": sum(1 for entry in entries if entry["status"] == "ok"),
            "failedCount": sum(1 for entry in entries if entry["status"] != "ok"),
        },
        extra={"targets": entries},
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    lines = [
        "# 946 Active-Sub Analysis",
        "",
        f"- Status: `{artifact['status']}`",
        "",
    ]
    targets = artifact.get("targets", [])
    if not targets:
        lines.append("- No active-sub targets matched the current filters.")
        lines.append("")
        return "\n".join(lines)
    for entry in targets:
        lines.append(f"## Opcode {entry['opcode']}")
        lines.append("")
        lines.append(f"- Candidate names: `{entry['packetNames']}`")
        lines.append(f"- Parser target: `{entry['parserTarget']}` `{entry['parserName']}`")
        lines.append(f"- Status/confidence: `{entry['status']}` `{entry['confidence']}`")
        lines.append(f"- Error kind: `{entry['errorKind']}`")
        lines.append(
            f"- Recovery: mode=`{entry['recoveryMode']}` decompileAttempted=`{entry['decompileAttempted']}` decompileCompleted=`{entry['decompileCompleted']}`"
        )
        lines.append(
            f"- Clone: strategy=`{entry['cloneStrategy']}` cleanup=`{entry['cloneCleanupStatus']}`"
            + (f" error=`{entry['cloneCleanupError']}`" if entry.get("cloneCleanupError") else "")
        )
        lines.append(f"- Exported field types: `{entry['exportedFieldTypes']}`")
        lines.append(f"- Draft field file: `{entry['draftFieldFile']}`")
        lines.append(f"- Next action: {entry['recommendedNextAction']}")
        for note in entry.get("analysisNotes", []):
            lines.append(f"- Analysis: {note}")
        for note in entry.get("notes", []):
            lines.append(f"- Note: {note}")
        lines.append("")
    return "\n".join(lines)


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> dict[str, str]:
    ensure_directory(output_dir)
    json_path = output_dir / ACTIVE_SUB_JSON
    markdown_path = output_dir / ACTIVE_SUB_MD
    write_json(json_path, artifact)
    markdown_path.write_text(render_markdown(artifact), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def input_fingerprint(args: argparse.Namespace) -> str:
    relevant_paths = [
        WORKSPACE / "tools" / "run_946_active_sub_aid.py",
        WORKSPACE / "tools" / "protocol_automation_common.py",
        WORKSPACE / "tools" / "protocol_946_debug_common.py",
        SHARED_DIR.parent / "phase3" / "nameCandidates.json",
        SHARED_DIR.parent / "phase5" / "generatedPackets.json",
        SHARED_DIR / "verified-packets.json",
        SHARED_DIR / "evidence-index.json",
    ]
    return artifact_input_fingerprint(
        "run_946_active_sub_aid",
        relevant_paths,
        manual_opcodes=sorted(set(args.opcode)),
        packet_names=sorted(set(args.packet_name)),
        analyze=args.analyze,
        ghidra_project_dir=args.ghidra_project_dir,
        ghidra_project_name=args.ghidra_project_name,
        headless_timeout_seconds=args.headless_timeout_seconds,
    )


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = [args.output_dir / ACTIVE_SUB_JSON, args.output_dir / ACTIVE_SUB_MD]
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, ACTIVE_SUB_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / ACTIVE_SUB_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0
    artifact = analyze_active_sub(args)
    paths = write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, ACTIVE_SUB_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": paths}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
