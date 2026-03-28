from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


WORKSPACE = Path(r"C:\Users\Demon\Documents\New project\OpenNXT")
REPO_ROOT = WORKSPACE.parent
PROT_DIR = WORKSPACE / "data" / "prot" / "946"
LEGACY_PROT_DIR = PROT_DIR.parent / "919"
PHASE3_DIR = PROT_DIR / "generated" / "phase3"
OUTPUT_DIR = PROT_DIR / "generated" / "phase4"
MANUAL_FIELD_OVERRIDE_PATH = OUTPUT_DIR / "manualFieldDraftOverrides.json"

DEFAULT_GHIDRA = Path.home() / "Tools" / "ghidra" / "ghidra_12.0.4_PUBLIC"
DEFAULT_PROJECT_DIR = REPO_ROOT / "ghidra-projects"
DEFAULT_GHIDRA_SCRIPTS = REPO_ROOT / "ghidra-scripts"
DEFAULT_PROGRAM = "rs2client.exe"
PROJECT_CANDIDATES = [
    "OpenNXT946Scratch2",
    "OpenNXT946",
    "OpenNXT946ClientProtVerify",
]

SERVER_FIELD_PRIORITIES = {
    "VAR": 100,
    "IF": 96,
    "SYNC": 92,
    "WORLD": 88,
    "SESSION": 84,
    "SCRIPT": 76,
}

CLIENT_FIELD_PRIORITIES = {
    "RESUME": 100,
    "RESUME_STRING": 100,
    "RAW_TEXT": 94,
    "TEXT_ENTRY": 90,
    "UI_RESET": 88,
    "IF_BUTTON": 86,
    "WALK": 82,
    "MAP_BUILD_COMPLETE": 80,
}

SERVER_RUNTIME_PRIORITIES = {
    "VAR": 92,
    "IF": 90,
    "SYNC": 88,
    "WORLD": 84,
    "SESSION": 80,
}

CLIENT_RUNTIME_PRIORITIES = {
    "RESUME": 100,
    "RESUME_STRING": 100,
    "RAW_TEXT": 92,
    "TEXT_ENTRY": 86,
    "UI_RESET": 84,
    "IF_BUTTON": 80,
}

BOOTSTRAP_NAMES = {
    "UPDATE_STAT",
    "VARP_SMALL",
    "VARP_LARGE",
    "CLIENT_SETVARC_SMALL",
    "CLIENT_SETVARC_LARGE",
    "CLIENT_SETVARCSTR_SMALL",
    "RESET_CLIENT_VARCACHE",
    "IF_OPENTOP",
    "IF_OPENSUB",
    "REBUILD_NORMAL",
    "WORLDLIST_FETCH",
}

DO_NOT_TOUCH_PACKET_NAMES = {
    "PLAYER_INFO": "bit-packed sync packet; keep hand-crafted parser and field handling",
    "NPC_INFO": "bit-packed sync packet; keep hand-crafted parser and field handling",
    "REBUILD_NORMAL": "region rebuild packet; keep hand-crafted field handling",
    "MAP_PROJANIM": "projectile map update packet; keep hand-crafted field handling",
    "MAP_PROJANIM_HALFSQ": "projectile map update packet; keep hand-crafted field handling",
}


@dataclass
class QueueItem:
    side: str
    opcode: int
    size: int
    kind: str
    priority: int
    packet_name: str
    family_label: str
    reason: str
    recommended_action: str
    source: str
    field_file: str
    parser_target: str
    parser_name: str
    exact_candidate_names: list[str]
    legacy_name: str
    legacy_size: int | None
    legacy_field_file: str
    legacy_field_count: int
    legacy_field_types: list[str]
    legacy_shape: list[str]
    legacy_reference_available: bool
    blacklist_reason: str
    evidence: dict


@dataclass
class ExtractionPaths:
    project_dir: Path
    project_name: str
    ghidra_dir: Path
    ghidra_scripts: Path
    output_dir: Path
    parser_fields_dir: Path
    program_name: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Phase 4 of the RS3 build 946 extraction pipeline."
    )
    parser.add_argument("--ghidra-dir", type=Path, default=DEFAULT_GHIDRA)
    parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT_DIR)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--ghidra-scripts", type=Path, default=DEFAULT_GHIDRA_SCRIPTS)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--program-name", default=DEFAULT_PROGRAM)
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run Ghidra auto-analysis before the export. Off by default for already analyzed projects.",
    )
    parser.add_argument(
        "--extract-parser-fields-limit",
        type=int,
        default=0,
        help="Sequentially export parser/sender field drafts for the top N safe field-recovery targets.",
    )
    parser.add_argument(
        "--extract-packet",
        action="append",
        default=[],
        help="Explicit packet name to export with ExportParserFields.java. May be repeated.",
    )
    return parser.parse_args()


def resolve_project_location(project_dir: Path, project_name: str) -> Path:
    direct = project_dir / f"{project_name}.gpr"
    if direct.exists():
        return project_dir

    nested = project_dir / project_name / f"{project_name}.gpr"
    if nested.exists():
        return project_dir / project_name

    raise FileNotFoundError(
        f"Could not find {project_name}.gpr under {project_dir}"
    )


def resolve_project_name(project_dir: Path, requested: str | None) -> str:
    if requested:
        return requested

    for candidate in PROJECT_CANDIDATES:
        if (project_dir / f"{candidate}.gpr").exists() or (project_dir / candidate / f"{candidate}.gpr").exists():
            return candidate

    raise FileNotFoundError(
        "Could not auto-detect a Ghidra project. Pass --project-name explicitly."
    )


def ensure_extraction_paths(args: argparse.Namespace) -> ExtractionPaths:
    project_name = resolve_project_name(args.project_dir, args.project_name)
    project_location = resolve_project_location(args.project_dir, project_name)
    ghidra_dir = args.ghidra_dir.resolve()
    analyze_headless = ghidra_dir / "support" / "analyzeHeadless.bat"
    if not analyze_headless.exists():
        raise FileNotFoundError(f"analyzeHeadless.bat not found at {analyze_headless}")
    if not args.ghidra_scripts.exists():
        raise FileNotFoundError(f"Ghidra scripts directory not found: {args.ghidra_scripts}")

    output_dir = args.output_dir.resolve()
    parser_fields_dir = output_dir / "parserFields"
    parser_fields_dir.mkdir(parents=True, exist_ok=True)
    return ExtractionPaths(
        project_dir=project_location.resolve(),
        project_name=project_name,
        ghidra_dir=ghidra_dir,
        ghidra_scripts=args.ghidra_scripts.resolve(),
        output_dir=output_dir,
        parser_fields_dir=parser_fields_dir.resolve(),
        program_name=args.program_name,
    )


def parse_names_toml(path: Path) -> dict[int, str]:
    text = path.read_text(encoding="utf-8")
    return {int(opcode): name for opcode, name in re.findall(r"^(\d+)\s*=\s*\"([^\"]+)\"", text, re.M)}


def parse_sizes_toml(path: Path) -> dict[int, int]:
    text = path.read_text(encoding="utf-8")
    return {int(opcode): int(size) for opcode, size in re.findall(r"^(\d+)\s*=\s*(-?\d+)", text, re.M)}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def field_file_path(side: str, packet_name: str) -> Path:
    directory = PROT_DIR / ("serverProt" if side == "server" else "clientProt")
    return directory / f"{packet_name}.txt"


def parse_field_file(path: Path) -> list[dict]:
    fields: list[dict] = []
    if not path.exists():
        return fields

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            fields.append({"raw": line, "name": "", "type": line})
            continue
        fields.append({"raw": line, "name": parts[0], "type": parts[1]})
    return fields


def get_legacy_fields(side: str, packet_name: str) -> list[str]:
    legacy_path = LEGACY_PROT_DIR / f"{side}Prot" / f"{packet_name}.txt"
    if not legacy_path.exists():
        return []

    fields: list[str] = []
    for raw_line in legacy_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            fields.append(parts[1])
    return fields


def build_legacy_lookup(side: str) -> dict[str, dict]:
    names = parse_names_toml(LEGACY_PROT_DIR / f"{side}ProtNames.toml")
    sizes = parse_sizes_toml(LEGACY_PROT_DIR / f"{side}ProtSizes.toml")
    prot_dir = LEGACY_PROT_DIR / f"{side}Prot"

    lookup: dict[str, dict] = {}
    for opcode, packet_name in names.items():
        field_path = prot_dir / f"{packet_name}.txt"
        fields = parse_field_file(field_path)
        legacy_shape = get_legacy_fields(side, packet_name)
        lookup[packet_name] = {
            "opcode": opcode,
            "size": sizes.get(opcode),
            "fieldFile": str(field_path) if field_path.exists() else "",
            "fieldCount": len(fields),
            "fieldTypes": [field["type"] for field in fields],
            "legacyShape": legacy_shape,
            "referenceAvailable": field_path.exists(),
            "fields": fields,
        }
    return lookup


def build_field_gap_analysis(candidates: list[dict], legacy_lookup_by_side: dict[str, dict[str, dict]]) -> list[dict]:
    analysis: list[dict] = []
    for candidate in candidates:
        packet_name = candidate.get("suggestedName", "")
        if not packet_name:
            continue

        side = candidate["side"]
        field_path = field_file_path(side, packet_name)
        legacy = legacy_lookup_by_side.get(side, {}).get(packet_name, {})
        blacklist_reason = DO_NOT_TOUCH_PACKET_NAMES.get(packet_name, "")
        needs_field_declaration = (candidate["size"] != 0) and (not field_path.exists()) and (not blacklist_reason)
        analysis.append(
            {
                "side": side,
                "opcode": candidate["opcode"],
                "size": candidate["size"],
                "packetName": packet_name,
                "parserTarget": candidate.get("evidence", {}).get("parserTarget", ""),
                "parserName": candidate.get("evidence", {}).get("parserName", ""),
                "familyLabel": candidate.get("familyLabel", ""),
                "fieldFile": str(field_path),
                "fieldFileExists": field_path.exists(),
                "needsFieldDeclaration": needs_field_declaration,
                "blacklistReason": blacklist_reason,
                "legacyName": packet_name if legacy else "",
                "legacyOpcode": legacy.get("opcode"),
                "legacySize": legacy.get("size"),
                "legacyFieldFile": legacy.get("fieldFile", ""),
                "legacyFieldCount": legacy.get("fieldCount", 0),
                "legacyFieldTypes": legacy.get("fieldTypes", []),
                "legacyShape": legacy.get("legacyShape", []),
                "legacyReferenceAvailable": legacy.get("referenceAvailable", False),
                "legacyShapeStatus": (
                    "available" if legacy.get("referenceAvailable", False) else "missing"
                ),
            }
        )

    analysis.sort(key=lambda item: (item["side"], item["opcode"]))
    return analysis


def build_field_recovery_queue(candidates: list[dict], field_gap_analysis: list[dict]) -> list[QueueItem]:
    gap_by_key = {(item["side"], item["opcode"]): item for item in field_gap_analysis}
    queue: list[QueueItem] = []
    for candidate in candidates:
        packet_name = candidate.get("suggestedName", "")
        if not packet_name:
            continue
        gap = gap_by_key[(candidate["side"], candidate["opcode"])]
        if not gap["needsFieldDeclaration"]:
            continue

        family_label = candidate.get("familyLabel", "")
        side = candidate["side"]
        priorities = SERVER_FIELD_PRIORITIES if side == "server" else CLIENT_FIELD_PRIORITIES
        priority = priorities.get(family_label, 70)
        if candidate["size"] >= 0:
            priority += 4
        if packet_name in BOOTSTRAP_NAMES:
            priority += 8
        if gap["legacyFieldCount"] > 0:
            priority += 6

        layout_shape = "fixed-length" if candidate["size"] >= 0 else "variable-length"
        queue.append(
            QueueItem(
                side=side,
                opcode=candidate["opcode"],
                size=candidate["size"],
                kind="field-recovery",
                priority=priority,
                packet_name=packet_name,
                family_label=family_label,
                reason="named packet has no build 946 field declaration yet",
                recommended_action=f"recover {layout_shape} field layout and emit {packet_name}.txt",
                source=candidate.get("source", ""),
                field_file=gap["fieldFile"],
                parser_target=gap["parserTarget"],
                parser_name=gap["parserName"],
                exact_candidate_names=candidate.get("exactCandidateNames", []),
                legacy_name=gap["legacyName"],
                legacy_size=gap["legacySize"],
                legacy_field_file=gap["legacyFieldFile"],
                legacy_field_count=gap["legacyFieldCount"],
                legacy_field_types=gap["legacyFieldTypes"],
                legacy_shape=gap["legacyShape"],
                legacy_reference_available=gap["legacyReferenceAvailable"],
                blacklist_reason=gap["blacklistReason"],
                evidence=candidate.get("evidence", {}),
            )
        )

    queue.sort(key=lambda item: (-item.priority, item.side, item.opcode))
    return queue


def build_all_named_field_targets(candidates: list[dict], field_gap_analysis: list[dict]) -> list[QueueItem]:
    gap_by_key = {(item["side"], item["opcode"]): item for item in field_gap_analysis}
    targets: list[QueueItem] = []
    for candidate in candidates:
        packet_name = candidate.get("suggestedName", "")
        if not packet_name:
            continue

        gap = gap_by_key[(candidate["side"], candidate["opcode"])]
        if gap["blacklistReason"] or candidate["size"] == 0:
            continue

        family_label = candidate.get("familyLabel", "")
        side = candidate["side"]
        priorities = SERVER_FIELD_PRIORITIES if side == "server" else CLIENT_FIELD_PRIORITIES
        priority = priorities.get(family_label, 70)
        if candidate["size"] >= 0:
            priority += 4
        if packet_name in BOOTSTRAP_NAMES:
            priority += 8
        if gap["legacyFieldCount"] > 0:
            priority += 6

        has_field_file = Path(gap["fieldFile"]).exists()
        layout_shape = "fixed-length" if candidate["size"] >= 0 else "variable-length"
        reason = (
            "named packet already has a build 946 field declaration and can be re-extracted for verification"
            if has_field_file
            else "named packet has no build 946 field declaration yet"
        )
        recommended_action = (
            f"refresh {layout_shape} field draft and keep the emitted {packet_name}.txt in sync"
            if has_field_file
            else f"recover {layout_shape} field layout and emit {packet_name}.txt"
        )

        targets.append(
            QueueItem(
                side=side,
                opcode=candidate["opcode"],
                size=candidate["size"],
                kind="field-recovery",
                priority=priority,
                packet_name=packet_name,
                family_label=family_label,
                reason=reason,
                recommended_action=recommended_action,
                source=candidate.get("source", ""),
                field_file=gap["fieldFile"],
                parser_target=gap["parserTarget"],
                parser_name=gap["parserName"],
                exact_candidate_names=candidate.get("exactCandidateNames", []),
                legacy_name=gap["legacyName"],
                legacy_size=gap["legacySize"],
                legacy_field_file=gap["legacyFieldFile"],
                legacy_field_count=gap["legacyFieldCount"],
                legacy_field_types=gap["legacyFieldTypes"],
                legacy_shape=gap["legacyShape"],
                legacy_reference_available=gap["legacyReferenceAvailable"],
                blacklist_reason=gap["blacklistReason"],
                evidence=candidate.get("evidence", {}),
            )
        )

    targets.sort(key=lambda item: (-item.priority, item.side, item.opcode))
    return targets


def build_runtime_verification_queue(candidates: list[dict]) -> list[QueueItem]:
    queue: list[QueueItem] = []
    for candidate in candidates:
        if candidate.get("suggestedName"):
            continue

        exact_candidate_names = candidate.get("exactCandidateNames", [])
        family_label = candidate.get("familyLabel", "")
        if not exact_candidate_names and not family_label:
            continue

        side = candidate["side"]
        priorities = SERVER_RUNTIME_PRIORITIES if side == "server" else CLIENT_RUNTIME_PRIORITIES
        priority = priorities.get(family_label, 64)
        if exact_candidate_names:
            priority += 12 if len(exact_candidate_names) == 1 else 8
        if candidate.get("evidence", {}).get("dispatchCluster"):
            priority += 10

        if exact_candidate_names:
            if len(exact_candidate_names) == 1:
                reason = "unique exact-name candidate is ready to prove against runtime behavior"
                action = "verify the exact semantic name against a live boot/login/runtime trace"
            else:
                reason = "ambiguous exact-name candidates still need runtime or callsite proof"
                action = "separate the candidate names using runtime behavior or deeper caller context"
        else:
            reason = "family classification exists but no exact semantic name is proven yet"
            action = "trace the family bucket through runtime behavior before promoting any name"

        queue.append(
            QueueItem(
                side=side,
                opcode=candidate["opcode"],
                size=candidate["size"],
                kind="runtime-verification",
                priority=priority,
                packet_name=candidate.get("suggestedName", ""),
                family_label=family_label,
                reason=reason,
                recommended_action=action,
                source=candidate.get("exactCandidateSource") or candidate.get("familySource") or candidate.get("source", ""),
                field_file="",
                parser_target=candidate.get("evidence", {}).get("parserTarget", ""),
                parser_name=candidate.get("evidence", {}).get("parserName", ""),
                exact_candidate_names=exact_candidate_names,
                legacy_name="",
                legacy_size=None,
                legacy_field_file="",
                legacy_field_count=0,
                legacy_field_types=[],
                legacy_shape=[],
                legacy_reference_available=False,
                blacklist_reason="",
                evidence=candidate.get("evidence", {}),
            )
        )

    queue.sort(key=lambda item: (-item.priority, item.side, item.opcode))
    return queue


def build_runtime_focus(field_queue: list[QueueItem], runtime_queue: list[QueueItem]) -> dict:
    return {
        "fieldRecoveryTop": [item.__dict__ for item in field_queue[:20]],
        "runtimeVerificationTop": [item.__dict__ for item in runtime_queue[:20]],
        "recommendedHelpers": [
            str(WORKSPACE / "tools" / "trace_process_runtime.py"),
            str(WORKSPACE / "tools" / "trace-win64c-runtime.ps1"),
        ],
    }


def resolve_field_target(item: QueueItem) -> tuple[str, str]:
    if item.parser_target:
        return item.parser_target, "parser"

    evidence = item.evidence or {}
    for key in ("primarySender", "parserTarget", "senderTarget"):
        value = evidence.get(key, "")
        if value:
            return value, "sender"

    return "", ""


def select_field_exports(
    all_named_targets: list[QueueItem],
    field_queue: list[QueueItem],
    args: argparse.Namespace,
) -> list[QueueItem]:
    selected: list[QueueItem] = []
    seen: set[str] = set()
    by_name = {item.packet_name.upper(): item for item in all_named_targets}

    for packet_name in args.extract_packet:
        item = by_name.get(packet_name.upper())
        if item is None:
            continue
        if not resolve_field_target(item)[0]:
            continue
        if item.packet_name in seen:
            continue
        selected.append(item)
        seen.add(item.packet_name)

    if args.extract_parser_fields_limit <= 0:
        return selected

    for item in field_queue:
        if len(selected) >= args.extract_parser_fields_limit:
            break
        if item.packet_name in seen:
            continue
        if not resolve_field_target(item)[0]:
            continue
        selected.append(item)
        seen.add(item.packet_name)

    return selected


def run_parser_field_export(paths: ExtractionPaths, args: argparse.Namespace, item: QueueItem) -> dict:
    target_address, target_kind = resolve_field_target(item)
    if not target_address:
        raise ValueError(f"No parser or sender target available for {item.packet_name}")

    analyze_headless = paths.ghidra_dir / "support" / "analyzeHeadless.bat"
    logs_dir = paths.parser_fields_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    output_json = paths.parser_fields_dir / f"{item.packet_name}.json"
    stdout_log = logs_dir / f"{item.packet_name}.stdout.log"
    stderr_log = logs_dir / f"{item.packet_name}.stderr.log"

    command = [
        str(analyze_headless),
        str(paths.project_dir),
        paths.project_name,
        "-process",
        paths.program_name,
    ]

    if not args.analyze:
        command.append("-noanalysis")

    command.extend([
        "-scriptPath",
        str(paths.ghidra_scripts),
        "-postScript",
        "ExportParserFields.java",
        str(output_json),
        str(target_address),
        item.packet_name,
    ])

    if item.legacy_shape:
        command.append(",".join(item.legacy_shape))

    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    stdout_log.write_text(completed.stdout, encoding="utf-8")
    stderr_log.write_text(completed.stderr, encoding="utf-8")

    if completed.returncode != 0:
        raise RuntimeError(
            f"ExportParserFields.java failed for {item.packet_name} with exit code "
            f"{completed.returncode}. See {stdout_log} and {stderr_log}."
        )

    if not output_json.exists():
        raise FileNotFoundError(f"Expected parser field export was not written: {output_json}")

    payload = load_json(output_json)
    payload = apply_helper_semantic_reconciliation(payload)
    payload["phase4TargetKind"] = target_kind
    payload["phase4QueuePriority"] = item.priority
    payload["phase4QueueOpcode"] = item.opcode
    payload["phase4Side"] = item.side
    write_json(output_json, payload)
    return payload


def apply_helper_semantic_reconciliation(payload: dict) -> dict:
    packet_name = payload.get("packetName", "")
    if packet_name != "OBJ_ADD":
        return payload

    decompiled_c = payload.get("decompiledC", "")
    if "FUN_1403526d0" not in decompiled_c:
        return payload

    helper_semantics = {
        "helperFunction": "FUN_1403526d0",
        "helperFieldOrder": ["id", "count"],
        "semanticFieldNames": ["count", "packedCoord", "id"],
        "proofRule": (
            "Use raw read order as packet order, then map the last FUN_1403526d0 short argument to count "
            "and the first helper short argument to id based on the verified OBJ_REVEAL sibling."
        ),
    }
    payload["helperSemanticHints"] = helper_semantics
    payload.setdefault("notes", [])
    if helper_semantics["proofRule"] not in payload["notes"]:
        payload["notes"].append(helper_semantics["proofRule"])
    return payload


def build_parser_field_index(extracted: list[dict], field_targets: list[QueueItem]) -> list[dict]:
    queue_by_name = {item.packet_name: item for item in field_targets}
    index: list[dict] = []
    for export in extracted:
        packet_name = export.get("packetName", "")
        item = queue_by_name.get(packet_name)
        target_address, target_kind = resolve_field_target(item) if item else ("", "")
        field_types = [field.get("candidateType", "") for field in export.get("fields", [])]
        index.append(
            {
                "packetName": packet_name,
                "side": export.get("phase4Side", item.side if item else ""),
                "opcode": export.get("phase4QueueOpcode", item.opcode if item else None),
                "priority": export.get("phase4QueuePriority", item.priority if item else None),
                "targetAddress": export.get("targetAddress", target_address),
                "targetKind": export.get("phase4TargetKind", target_kind),
                "functionName": export.get("functionName", ""),
                "status": export.get("status", ""),
                "fieldCount": export.get("fieldCount", 0),
                "bufferParam": export.get("bufferParam", ""),
                "legacyShape": export.get("legacyShape", []),
                "candidateTypes": field_types,
                "reviewSource": "heuristic",
                "manualOverride": False,
                "semanticFieldNames": export.get("helperSemanticHints", {}).get("semanticFieldNames", []),
                "helperSemanticHints": export.get("helperSemanticHints", {}),
                "notes": export.get("notes", []),
                "outputFile": str(OUTPUT_DIR / "parserFields" / f"{packet_name}.json"),
            }
        )

    index.sort(key=lambda item: (-int(item["priority"] or 0), item["side"], int(item["opcode"] or 0)))
    return index


def load_parser_field_exports(parser_fields_dir: Path) -> list[dict]:
    if not parser_fields_dir.exists():
        return []

    exports: list[dict] = []
    for path in sorted(parser_fields_dir.glob("*.json")):
        exports.append(load_json(path))
    return exports


def load_manual_field_overrides(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = load_json(path)
    if isinstance(payload, list):
        return payload
    return payload.get("overrides", [])


def apply_manual_field_overrides(
    parser_field_index: list[dict],
    field_targets: list[QueueItem],
    overrides: list[dict],
) -> list[dict]:
    if not overrides:
        return parser_field_index

    queue_by_name = {item.packet_name: item for item in field_targets}
    index_by_name = {item["packetName"]: dict(item) for item in parser_field_index}

    for override in overrides:
        packet_name = override.get("packetName", "")
        if not packet_name:
            continue
        item = queue_by_name.get(packet_name)
        existing = index_by_name.get(packet_name, {})
        target_address, target_kind = resolve_field_target(item) if item else ("", "")

        merged = {
            "packetName": packet_name,
            "side": override.get("side", existing.get("side", item.side if item else "")),
            "opcode": override.get("opcode", existing.get("opcode", item.opcode if item else None)),
            "priority": override.get("priority", existing.get("priority", item.priority if item else None)),
            "targetAddress": override.get("targetAddress", existing.get("targetAddress", target_address)),
            "targetKind": override.get("targetKind", existing.get("targetKind", target_kind)),
            "functionName": override.get("functionName", existing.get("functionName", "")),
            "status": override.get("status", "reviewed-override"),
            "fieldCount": override.get("fieldCount", len(override.get("candidateTypes", existing.get("candidateTypes", [])))),
            "bufferParam": override.get("bufferParam", existing.get("bufferParam", "")),
            "legacyShape": override.get("legacyShape", existing.get("legacyShape", [])),
            "candidateTypes": override.get("candidateTypes", existing.get("candidateTypes", [])),
            "reviewSource": override.get("reviewSource", "reviewed-override"),
            "outputFile": override.get("outputFile", existing.get("outputFile", str(MANUAL_FIELD_OVERRIDE_PATH))),
            "manualOverride": True,
            "semanticFieldNames": override.get("semanticFieldNames", existing.get("semanticFieldNames", [])),
            "helperSemanticHints": override.get("helperSemanticHints", existing.get("helperSemanticHints", {})),
            "notes": override.get("notes", []),
        }
        index_by_name[packet_name] = merged

    merged_index = list(index_by_name.values())
    merged_index.sort(key=lambda item: (-int(item["priority"] or 0), item["side"], int(item["opcode"] or 0)))
    return merged_index


def write_summary(
    path: Path,
    field_gap_analysis: list[dict],
    field_queue: list[QueueItem],
    runtime_queue: list[QueueItem],
    ambiguous_client_clusters: list[dict],
    parser_field_index: list[dict],
) -> None:
    field_by_side = Counter(item.side for item in field_queue)
    runtime_by_side = Counter(item.side for item in runtime_queue)
    blacklisted_named = [item for item in field_gap_analysis if item["blacklistReason"]]
    legacy_supported_field_gaps = [item for item in field_gap_analysis if item["needsFieldDeclaration"] and item["legacyFieldCount"] > 0]
    runtime_exact = sum(1 for item in runtime_queue if item.exact_candidate_names)
    runtime_ambiguous = sum(1 for item in runtime_queue if len(item.exact_candidate_names) > 1)
    runtime_unique = sum(1 for item in runtime_queue if len(item.exact_candidate_names) == 1)

    lines = [
        "# Phase 4 Verification Summary",
        "",
        "Phase 4 begins here: it consumes the Phase 3 name candidates and turns them",
        "into concrete work queues and safe parser-field extraction targets:",
        "",
        "- field layout recovery for already named packets that still lack `946` field files",
        "- runtime verification for unresolved packets that already have family or exact-name evidence",
        "- sequential parser/sender field exports for the top safe recovery targets",
        "",
        "## Queue Counts",
        "",
        f"- Field recovery targets: `{len(field_queue)}`",
        f"  - server: `{field_by_side.get('server', 0)}`",
        f"  - client: `{field_by_side.get('client', 0)}`",
        f"- Named packets skipped by do-not-touch blacklist: `{len(blacklisted_named)}`",
        f"- Field gaps with a usable 919 reference file: `{len(legacy_supported_field_gaps)}`",
        f"- Runtime verification targets: `{len(runtime_queue)}`",
        f"  - server: `{runtime_by_side.get('server', 0)}`",
        f"  - client: `{runtime_by_side.get('client', 0)}`",
        f"- Runtime targets with exact-name candidates: `{runtime_exact}`",
        f"- Runtime targets with unique exact-name candidates: `{runtime_unique}`",
        f"- Runtime targets with ambiguous exact-name candidates: `{runtime_ambiguous}`",
        f"- Ambiguous client clusters carried forward from Phase 3: `{len(ambiguous_client_clusters)}`",
        f"- Parser field exports generated: `{len(parser_field_index)}`",
        "",
        "## Top Field Recovery Targets",
        "",
    ]

    if field_queue:
        for item in field_queue[:12]:
            legacy_suffix = ""
            if item.legacy_field_count > 0:
                legacy_suffix = f" legacy-fields `{item.legacy_field_count}`"
            lines.append(
                f"- `{item.side}:{item.opcode}` `{item.packet_name}`"
                f" family `{item.family_label or 'unclassified'}`"
                f" size `{item.size}` priority `{item.priority}`{legacy_suffix}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Parser Field Drafts", ""])
    if parser_field_index:
        for item in parser_field_index[:12]:
            lines.append(
                f"- `{item['side']}:{item['opcode']}` `{item['packetName']}`"
                f" via `{item['targetKind']}` `{item['targetAddress']}`"
                f" fields `{item['fieldCount']}`"
                f" types `{', '.join(item['candidateTypes']) if item['candidateTypes'] else '<none>'}`"
            )
    else:
        lines.append("- none generated on this run")

    lines.extend(["", "## Do Not Touch", ""])
    if blacklisted_named:
        for item in blacklisted_named[:12]:
            lines.append(
                f"- `{item['side']}:{item['opcode']}` `{item['packetName']}`"
                f" skipped: {item['blacklistReason']}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Top Runtime Verification Targets", ""])
    if runtime_queue:
        for item in runtime_queue[:12]:
            exact_suffix = ""
            if item.exact_candidate_names:
                exact_suffix = f" candidates `{', '.join(item.exact_candidate_names)}`"
            dispatch_suffix = ""
            if item.evidence.get("dispatchSelectorHex"):
                dispatch_suffix = (
                    f" [dispatcher {item.evidence.get('dispatcherFunctionName', '')}"
                    f", selector {item.evidence.get('dispatchSelectorHex', '')}]"
                )
            lines.append(
                f"- `{item.side}:{item.opcode}` family `{item.family_label or 'unclassified'}`"
                f" priority `{item.priority}`{exact_suffix}{dispatch_suffix}"
            )
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Recommended Runtime Helpers",
            "",
            f"- `{WORKSPACE / 'tools' / 'trace_process_runtime.py'}`",
            f"- `{WORKSPACE / 'tools' / 'trace-win64c-runtime.ps1'}`",
            "",
            "## Outputs",
            "",
            "- `fieldGapAnalysis.json`",
            "- `fieldRecoveryQueue.json`",
            "- `runtimeVerificationQueue.json`",
            "- `runtimeFocus.json`",
            "- `parserFieldIndex.json`",
            "- `parserFields/*.json`",
            "- `phase4-summary.md`",
            "",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    parse_names_toml(PROT_DIR / "serverProtNames.toml")
    parse_names_toml(PROT_DIR / "clientProtNames.toml")

    candidates = load_json(PHASE3_DIR / "nameCandidates.json")
    ambiguous_client_clusters = load_json(PHASE3_DIR / "clientAmbiguousClusters.json")
    legacy_lookup = {
        "server": build_legacy_lookup("server"),
        "client": build_legacy_lookup("client"),
    }

    field_gap_analysis = build_field_gap_analysis(candidates, legacy_lookup)
    all_named_field_targets = build_all_named_field_targets(candidates, field_gap_analysis)
    field_queue = build_field_recovery_queue(candidates, field_gap_analysis)
    runtime_queue = build_runtime_verification_queue(candidates)
    runtime_focus = build_runtime_focus(field_queue, runtime_queue)

    manual_field_overrides = load_manual_field_overrides(MANUAL_FIELD_OVERRIDE_PATH)
    parser_field_index: list[dict] = []
    if args.extract_parser_fields_limit > 0 or args.extract_packet:
        paths = ensure_extraction_paths(args)
        extracted = []
        for item in select_field_exports(all_named_field_targets, field_queue, args):
            extracted.append(run_parser_field_export(paths, args, item))
        parser_field_index = build_parser_field_index(load_parser_field_exports(paths.parser_fields_dir), all_named_field_targets)
        parser_field_index = apply_manual_field_overrides(parser_field_index, all_named_field_targets, manual_field_overrides)
        write_json(paths.output_dir / "parserFieldIndex.json", parser_field_index)
    else:
        parser_field_index = build_parser_field_index(load_parser_field_exports(args.output_dir / "parserFields"), all_named_field_targets)
        parser_field_index = apply_manual_field_overrides(parser_field_index, all_named_field_targets, manual_field_overrides)
        if parser_field_index:
            write_json(args.output_dir / "parserFieldIndex.json", parser_field_index)

    write_json(args.output_dir / "fieldGapAnalysis.json", field_gap_analysis)
    write_json(args.output_dir / "fieldRecoveryQueue.json", [item.__dict__ for item in field_queue])
    write_json(args.output_dir / "runtimeVerificationQueue.json", [item.__dict__ for item in runtime_queue])
    write_json(args.output_dir / "runtimeFocus.json", runtime_focus)
    write_summary(
        args.output_dir / "phase4-summary.md",
        field_gap_analysis,
        field_queue,
        runtime_queue,
        ambiguous_client_clusters,
        parser_field_index,
    )

    print(
        json.dumps(
            {
                "fieldGapAnalysis": str(args.output_dir / "fieldGapAnalysis.json"),
                "fieldRecoveryQueue": str(args.output_dir / "fieldRecoveryQueue.json"),
                "runtimeVerificationQueue": str(args.output_dir / "runtimeVerificationQueue.json"),
                "runtimeFocus": str(args.output_dir / "runtimeFocus.json"),
                "parserFieldIndex": str(args.output_dir / "parserFieldIndex.json"),
                "summary": str(args.output_dir / "phase4-summary.md"),
                "fieldRecoveryCount": len(field_queue),
                "runtimeVerificationCount": len(runtime_queue),
                "parserFieldExportCount": len(parser_field_index),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
