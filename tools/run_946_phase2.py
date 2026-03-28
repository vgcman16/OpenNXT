from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from protocol_automation_common import helper_signature_hash


DEFAULT_GHIDRA = Path.home() / "Tools" / "ghidra" / "ghidra_12.0.4_PUBLIC"
DEFAULT_WORKSPACE = Path(r"C:\Users\Demon\Documents\New project")
DEFAULT_PROJECT_DIR = DEFAULT_WORKSPACE / "ghidra-projects"
DEFAULT_GHIDRA_SCRIPTS = DEFAULT_WORKSPACE / "ghidra-scripts"
DEFAULT_OUTPUT_DIR = DEFAULT_WORKSPACE / "OpenNXT" / "data" / "prot" / "946" / "generated" / "phase2"
DEFAULT_PROGRAM = "rs2client.exe"
DEFAULT_SERVER_REGISTRAR = "140301280"
DEFAULT_CLIENT_REGISTRAR = "140301100"
DEFAULT_ASSIGN_HELPER = "1400292e0"
PROJECT_CANDIDATES = [
    "OpenNXT946Scratch2",
    "OpenNXT946",
    "OpenNXT946ClientProtVerify",
]


@dataclass
class ExtractionPaths:
    project_dir: Path
    project_name: str
    ghidra_dir: Path
    ghidra_scripts: Path
    output_dir: Path
    program_name: str


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Phase 2 of the RS3 build 946 extraction pipeline."
    )
    parser.add_argument("--ghidra-dir", type=Path, default=DEFAULT_GHIDRA)
    parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT_DIR)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--ghidra-scripts", type=Path, default=DEFAULT_GHIDRA_SCRIPTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--program-name", default=DEFAULT_PROGRAM)
    parser.add_argument("--server-registrar-address", default=DEFAULT_SERVER_REGISTRAR)
    parser.add_argument("--client-registrar-address", default=DEFAULT_CLIENT_REGISTRAR)
    parser.add_argument("--assign-helper-address", default=DEFAULT_ASSIGN_HELPER)
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run Ghidra auto-analysis before the export. Off by default for already analyzed projects.",
    )
    return parser.parse_args()


def resolve_project_name(project_dir: Path, requested: str | None) -> str:
    if requested:
        return requested

    for candidate in PROJECT_CANDIDATES:
        if (project_dir / f"{candidate}.gpr").exists() or (project_dir / candidate / f"{candidate}.gpr").exists():
            return candidate

    raise FileNotFoundError(
        "Could not auto-detect a Ghidra project. Pass --project-name explicitly."
    )


def ensure_paths(args: argparse.Namespace) -> ExtractionPaths:
    project_name = resolve_project_name(args.project_dir, args.project_name)
    project_location = resolve_project_location(args.project_dir, project_name)
    ghidra_dir = args.ghidra_dir.resolve()
    analyze_headless = ghidra_dir / "support" / "analyzeHeadless.bat"
    if not analyze_headless.exists():
        raise FileNotFoundError(f"analyzeHeadless.bat not found at {analyze_headless}")
    if not args.ghidra_scripts.exists():
        raise FileNotFoundError(f"Ghidra scripts directory not found: {args.ghidra_scripts}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    return ExtractionPaths(
        project_dir=project_location.resolve(),
        project_name=project_name,
        ghidra_dir=ghidra_dir,
        ghidra_scripts=args.ghidra_scripts.resolve(),
        output_dir=args.output_dir.resolve(),
        program_name=args.program_name,
    )


def run_export(paths: ExtractionPaths, args: argparse.Namespace) -> dict:
    analyze_headless = paths.ghidra_dir / "support" / "analyzeHeadless.bat"
    export_json = paths.output_dir / "handler-assignments.json"
    stdout_log = paths.output_dir / "headless-phase2.stdout.log"
    stderr_log = paths.output_dir / "headless-phase2.stderr.log"

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
        "ExportHandlerAssignments.java",
        str(export_json),
        str(args.server_registrar_address),
        str(args.client_registrar_address),
        str(args.assign_helper_address),
    ])

    completed = subprocess.run(
        command,
        cwd=str(DEFAULT_WORKSPACE),
        capture_output=True,
        text=True,
        check=False,
    )

    stdout_log.write_text(completed.stdout, encoding="utf-8")
    stderr_log.write_text(completed.stderr, encoding="utf-8")

    if completed.returncode != 0:
        raise RuntimeError(
            f"analyzeHeadless failed with exit code {completed.returncode}. "
            f"See {stdout_log} and {stderr_log}."
        )

    if not export_json.exists():
        raise FileNotFoundError(f"Expected export JSON was not written: {export_json}")

    return json.loads(export_json.read_text(encoding="utf-8"))


def run_client_export(paths: ExtractionPaths, args: argparse.Namespace) -> dict:
    analyze_headless = paths.ghidra_dir / "support" / "analyzeHeadless.bat"
    export_json = paths.output_dir / "client-sender-candidates.json"
    stdout_log = paths.output_dir / "headless-phase2-client.stdout.log"
    stderr_log = paths.output_dir / "headless-phase2-client.stderr.log"

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
        "ExportClientProtSenders.java",
        str(export_json),
        str(args.client_registrar_address),
    ])

    completed = subprocess.run(
        command,
        cwd=str(DEFAULT_WORKSPACE),
        capture_output=True,
        text=True,
        check=False,
    )

    stdout_log.write_text(completed.stdout, encoding="utf-8")
    stderr_log.write_text(completed.stderr, encoding="utf-8")

    if completed.returncode != 0:
        raise RuntimeError(
            f"ExportClientProtSenders.java failed with exit code {completed.returncode}. "
            f"See {stdout_log} and {stderr_log}."
        )

    if not export_json.exists():
        raise FileNotFoundError(f"Expected client export JSON was not written: {export_json}")

    return json.loads(export_json.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def split_assignments(assignments: list[dict]) -> tuple[list[dict], list[dict]]:
    server = [assignment for assignment in assignments if assignment["family"] == "server"]
    client = [assignment for assignment in assignments if assignment["family"] == "client"]
    server.sort(key=lambda assignment: assignment["opcode"])
    client.sort(key=lambda assignment: assignment["opcode"])
    return server, client


def build_server_families(assignments: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for assignment in assignments:
        key = (
            assignment["family"],
            assignment.get("setupFunction", ""),
            assignment.get("setupFunctionName", ""),
        )
        grouped[key].append(assignment)

    families: list[dict] = []
    for (family, setup_function, setup_name), rows in grouped.items():
        rows.sort(key=lambda row: row["opcode"])
        families.append(
            {
                "family": family,
                "kind": "server-handler",
                "setupFunction": setup_function,
                "setupFunctionName": setup_name,
                "count": len(rows),
                "opcodeMin": rows[0]["opcode"],
                "opcodeMax": rows[-1]["opcode"],
                "dispatchMethods": sorted({row.get("dispatchMethod", "") for row in rows if row.get("dispatchMethod")}),
                "parserTargets": sorted({row.get("parserTarget", "") for row in rows if row.get("parserTarget")}),
            }
        )

    families.sort(key=lambda family: (family["family"], -family["count"], family["setupFunction"]))
    return families


def build_client_families(mappings: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for mapping in mappings:
        sender = mapping.get("primarySender", "")
        sender_name = mapping.get("primarySenderName", "")
        if not sender:
            continue
        grouped[(sender, sender_name)].append(mapping)

    families: list[dict] = []
    for (sender, sender_name), rows in grouped.items():
        rows.sort(key=lambda row: row["opcode"])
        families.append(
            {
                "family": "client",
                "kind": "client-sender",
                "setupFunction": sender,
                "setupFunctionName": sender_name,
                "count": len(rows),
                "opcodeMin": rows[0]["opcode"],
                "opcodeMax": rows[-1]["opcode"],
                "dispatchMethods": [],
                "parserTargets": [],
            }
        )

    families.sort(key=lambda family: (family["family"], -family["count"], family["setupFunction"]))
    return families


def build_handler_graph(server: list[dict], client_mappings: list[dict]) -> list[dict]:
    graph: list[dict] = []
    for row in server:
        graph.append(
            {
                "side": "server",
                "opcode": row["opcode"],
                "packetRef": row.get("inlineBase", ""),
                "setupFunction": row.get("setupFunction", ""),
                "setupFunctionName": row.get("setupFunctionName", ""),
                "dispatchMethod": row.get("dispatchMethod", ""),
                "dispatchName": row.get("dispatchName", ""),
                "parserTarget": row.get("parserTarget", ""),
                "parserName": row.get("parserName", ""),
                "helperChain": [
                    value
                    for value in [
                        row.get("setupFunction", ""),
                        row.get("dispatchMethod", ""),
                        row.get("parserTarget", ""),
                    ]
                    if value
                ],
            }
        )
    for row in client_mappings:
        graph.append(
            {
                "side": "client",
                "opcode": row["opcode"],
                "packetRef": row.get("packet", ""),
                "setupFunction": row.get("primarySender", ""),
                "setupFunctionName": row.get("primarySenderName", ""),
                "dispatchMethod": "",
                "dispatchName": "",
                "parserTarget": row.get("primarySender", ""),
                "parserName": row.get("primarySenderName", ""),
                "helperChain": [row.get("primarySender", "")] if row.get("primarySender") else [],
            }
        )
    graph.sort(key=lambda item: (item["side"], item["opcode"]))
    return graph


def build_helper_signatures(server: list[dict], client_mappings: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], dict] = {}

    for row in server:
        key = ("server", row.get("parserTarget", ""), row.get("parserName", ""))
        entry = grouped.setdefault(
            key,
            {
                "side": "server",
                "entryPoint": row.get("parserTarget", ""),
                "name": row.get("parserName", ""),
                "kind": "parser",
                "opcodes": [],
                "setupFunctions": set(),
                "dispatchMethods": set(),
            },
        )
        entry["opcodes"].append(row["opcode"])
        if row.get("setupFunction"):
            entry["setupFunctions"].add(row["setupFunction"])
        if row.get("dispatchMethod"):
            entry["dispatchMethods"].add(row["dispatchMethod"])

    for row in client_mappings:
        key = ("client", row.get("primarySender", ""), row.get("primarySenderName", ""))
        entry = grouped.setdefault(
            key,
            {
                "side": "client",
                "entryPoint": row.get("primarySender", ""),
                "name": row.get("primarySenderName", ""),
                "kind": "sender",
                "opcodes": [],
                "roles": set(),
                "candidateScores": [],
            },
        )
        entry["opcodes"].append(row["opcode"])
        for candidate in row.get("senderCandidates", []):
            if candidate.get("role"):
                entry["roles"].add(candidate["role"])
            if candidate.get("score") is not None:
                entry["candidateScores"].append(candidate["score"])

    signatures: list[dict] = []
    for entry in grouped.values():
        signature = {
            "side": entry["side"],
            "entryPoint": entry["entryPoint"],
            "name": entry["name"],
            "kind": entry["kind"],
            "opcodeCount": len(entry["opcodes"]),
            "opcodes": sorted(entry["opcodes"]),
        }
        if entry["side"] == "server":
            signature["setupFunctions"] = sorted(entry["setupFunctions"])
            signature["dispatchMethods"] = sorted(entry["dispatchMethods"])
        else:
            signature["roles"] = sorted(entry["roles"])
            signature["maxCandidateScore"] = max(entry["candidateScores"]) if entry["candidateScores"] else 0
        signature["signatureHash"] = helper_signature_hash(signature)
        signatures.append(signature)

    signatures.sort(key=lambda item: (item["side"], -item["opcodeCount"], item["entryPoint"]))
    return signatures


def write_summary(path: Path, payload: dict, server: list[dict], client: list[dict], families: list[dict]) -> None:
    server_families = [family for family in families if family["kind"] == "server-handler"]
    client_families = [family for family in families if family["kind"] == "client-sender"]
    lines = [
        "# Phase 2 Parser Recovery Summary",
        "",
        f"- Program: `{payload['programName']}`",
        f"- Generated: `{payload['generatedAt']}`",
        f"- Total server assignments: `{payload['assignmentCount']}`",
        f"- Server parser mappings: `{len(server)}`",
        f"- Client sender mappings: `{len(client)}`",
        f"- Setup families: `{len(families)}`",
        "",
        "## Largest server setup families",
        "",
    ]

    for family in server_families[:6]:
        lines.append(
            f"- `{family['kind']}` `{family['family']}` via `{family['setupFunctionName']}` at "
            f"`{family['setupFunction']}`: `{family['count']}` opcode(s), "
            f"`{family['opcodeMin']}`..`{family['opcodeMax']}`"
        )

    lines.extend([
        "",
        "## Largest client sender families",
        "",
    ])

    for family in client_families[:6]:
        lines.append(
            f"- `{family['kind']}` `{family['family']}` via `{family['setupFunctionName']}` at "
            f"`{family['setupFunction']}`: `{family['count']}` opcode(s), "
            f"`{family['opcodeMin']}`..`{family['opcodeMax']}`"
        )

    lines.extend([
        "",
        "## Outputs",
        "",
        "- `handler-assignments.json`",
        "- `serverParsers.json`",
        "- `clientParsers.json`",
        "- `handlerFamilies.json`",
        "- `handlerGraph.json`",
        "- `helperSignatures.json`",
        "- `phase2-summary.md`",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    paths = ensure_paths(args)
    export = run_export(paths, args)
    client_export = run_client_export(paths, args)

    assignments = export["assignments"]
    server, client = split_assignments(assignments)
    client_mappings = client_export["mappings"]
    families = build_server_families(assignments) + build_client_families(client_mappings)
    handler_graph = build_handler_graph(server, client_mappings)
    helper_signatures = build_helper_signatures(server, client_mappings)
    families.sort(key=lambda family: (-family["count"], family["kind"], family["setupFunction"]))
    generated_at = datetime.now(timezone.utc).isoformat()

    payload = {
        "generatedAt": generated_at,
        "programName": export["programName"],
        "assignHelper": export["assignHelper"],
        "assignmentCount": len(assignments),
    }

    write_json(paths.output_dir / "serverParsers.json", server)
    write_json(paths.output_dir / "clientParsers.json", client_mappings)
    write_json(paths.output_dir / "handlerFamilies.json", families)
    write_json(paths.output_dir / "handlerGraph.json", handler_graph)
    write_json(paths.output_dir / "helperSignatures.json", helper_signatures)
    write_summary(paths.output_dir / "phase2-summary.md", payload, server, client_mappings, families)

    print(json.dumps(
        {
            "outputDir": str(paths.output_dir),
            "serverParsers": str(paths.output_dir / "serverParsers.json"),
            "clientParsers": str(paths.output_dir / "clientParsers.json"),
            "handlerFamilies": str(paths.output_dir / "handlerFamilies.json"),
            "handlerGraph": str(paths.output_dir / "handlerGraph.json"),
            "helperSignatures": str(paths.output_dir / "helperSignatures.json"),
            "summary": str(paths.output_dir / "phase2-summary.md"),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
