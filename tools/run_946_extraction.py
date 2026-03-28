from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_GHIDRA = Path.home() / "Tools" / "ghidra" / "ghidra_12.0.4_PUBLIC"
DEFAULT_WORKSPACE = Path(r"C:\Users\Demon\Documents\New project")
DEFAULT_PROJECT_DIR = DEFAULT_WORKSPACE / "ghidra-projects"
DEFAULT_GHIDRA_SCRIPTS = DEFAULT_WORKSPACE / "ghidra-scripts"
DEFAULT_OUTPUT_DIR = DEFAULT_WORKSPACE / "OpenNXT" / "data" / "prot" / "946" / "generated" / "phase1"
DEFAULT_PROGRAM = "rs2client.exe"
DEFAULT_SERVER_REGISTRAR = "140301280"
DEFAULT_CLIENT_REGISTRAR = "140301100"
PROJECT_CANDIDATES = [
    "OpenNXT946Scratch2",
    "OpenNXT946",
    "OpenNXT946ClientProtVerify",
]
CALLREF_LINE_RE = re.compile(
    r"INFO\s+([0-9A-Fa-f]+),([0-9A-Fa-f]+),(-?\d+|\?),(-?\d+|\?)"
)


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
        description="Run Phase 1 of the RS3 build 946 extraction pipeline."
    )
    parser.add_argument("--ghidra-dir", type=Path, default=DEFAULT_GHIDRA)
    parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT_DIR)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--ghidra-scripts", type=Path, default=DEFAULT_GHIDRA_SCRIPTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--program-name", default=DEFAULT_PROGRAM)
    parser.add_argument("--server-registrar-address", default=DEFAULT_SERVER_REGISTRAR)
    parser.add_argument("--client-registrar-address", default=DEFAULT_CLIENT_REGISTRAR)
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run Ghidra auto-analysis before the export. Off by default for already analyzed projects.",
    )
    parser.add_argument("--server-min", type=int, default=160)
    parser.add_argument("--client-min", type=int, default=96)
    parser.add_argument("--client-max", type=int, default=160)
    parser.add_argument("--min-call-refs", type=int, default=24)
    parser.add_argument("--max-call-refs", type=int, default=320)
    parser.add_argument("--min-contiguous", type=int, default=32)
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
    export_json = paths.output_dir / "registrar-candidates.json"
    stdout_log = paths.output_dir / "headless-export.stdout.log"
    stderr_log = paths.output_dir / "headless-export.stderr.log"

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
        "ExportProtocolRegistrars.java",
        str(export_json),
        str(args.server_min),
        str(args.client_min),
        str(args.client_max),
        str(args.min_call_refs),
        str(args.max_call_refs),
        str(args.min_contiguous),
        str(args.server_registrar_address),
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
            f"analyzeHeadless failed with exit code {completed.returncode}. "
            f"See {stdout_log} and {stderr_log}."
        )

    if not export_json.exists():
        raise FileNotFoundError(f"Expected export JSON was not written: {export_json}")

    return json.loads(export_json.read_text(encoding="utf-8"))


def run_callref_dump(
    paths: ExtractionPaths,
    args: argparse.Namespace,
    target_address: str,
    output_stem: str,
) -> str:
    analyze_headless = paths.ghidra_dir / "support" / "analyzeHeadless.bat"
    stdout_log = paths.output_dir / f"{output_stem}.stdout.log"
    stderr_log = paths.output_dir / f"{output_stem}.stderr.log"

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
        "DumpCallRefsForTarget.java",
        str(target_address),
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
            f"DumpCallRefsForTarget.java failed with exit code {completed.returncode}. "
            f"See {stdout_log} and {stderr_log}."
        )

    return completed.stdout


def synthesize_candidate_from_callrefs(
    dump_stdout: str,
    entry_point: str,
    packet_register: str = "RCX",
    opcode_register: str = "RDX",
    size_register: str = "R8",
) -> dict | None:
    recovered: dict[int, dict] = {}
    call_refs = 0

    for line in dump_stdout.splitlines():
        match = CALLREF_LINE_RE.search(line)
        if not match:
            continue

        call_site, packet, opcode_text, size_text = match.groups()
        call_refs += 1
        if opcode_text == "?" or size_text == "?":
            continue

        opcode = int(opcode_text)
        size = int(size_text)
        sample = {
            "opcode": opcode,
            "size": size,
            "packet": packet.lower(),
            "callSite": call_site.lower(),
        }

        prior = recovered.get(opcode)
        if prior is not None and (prior["packet"] != sample["packet"] or prior["size"] != sample["size"]):
            return None
        recovered[opcode] = sample

    contiguous = 0
    while contiguous in recovered:
        contiguous += 1
    if contiguous == 0:
        return None

    samples = [recovered[i] for i in range(contiguous)]
    stride = 0
    if len(samples) >= 2:
        stride = int(samples[1]["packet"], 16) - int(samples[0]["packet"], 16)
        for index in range(2, len(samples)):
            next_stride = int(samples[index]["packet"], 16) - int(samples[index - 1]["packet"], 16)
            if next_stride != stride:
                return None

    return {
        "entryPoint": entry_point.lower(),
        "name": f"FUN_{entry_point.lower()}",
        "packetRegister": packet_register,
        "opcodeRegister": opcode_register,
        "sizeRegister": size_register,
        "contiguous": contiguous,
        "stride": stride,
        "callRefs": call_refs,
        "samples": samples,
    }


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_sizes_toml(path: Path, samples: list[dict], comment: str) -> None:
    lines = [f"# {comment}", ""]
    for sample in samples:
        lines.append(f"{sample['opcode']} = {sample['size']}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_summary(path: Path, payload: dict) -> None:
    server = payload.get("bestServerCandidate")
    client = payload.get("bestClientCandidate")
    lines = [
        "# Phase 1 Extraction Summary",
        "",
        f"- Program: `{payload['programName']}`",
        f"- Generated: `{payload['generatedAt']}`",
        f"- Candidate count: `{payload['candidateCount']}`",
        "",
        "## Best server candidate",
        "",
        format_candidate_markdown(server),
        "",
        "## Best client candidate",
        "",
        format_candidate_markdown(client),
        "",
        "## Outputs",
        "",
        "- `registrar-candidates.json`",
        "- `registrars.json`",
        "- `build-info.json`",
        "- `serverProtSizes.generated.toml`",
        "- `clientProtSizes.generated.toml`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def format_candidate_markdown(candidate: dict | None) -> str:
    if not candidate:
        return "- not found"
    return "\n".join(
        [
            f"- Entry point: `{candidate['entryPoint']}`",
            f"- Name: `{candidate['name']}`",
            f"- Registers: `{candidate['packetRegister']}/{candidate['opcodeRegister']}/{candidate['sizeRegister']}`",
            f"- Contiguous opcodes: `{candidate['contiguous']}`",
            f"- Stride: `{candidate['stride']}`",
            f"- Call refs: `{candidate['callRefs']}`",
        ]
    )


def main() -> int:
    args = parse_args()
    paths = ensure_paths(args)
    export = run_export(paths, args)
    if not export.get("bestClientCandidate") and args.client_registrar_address:
        client_dump = run_callref_dump(
            paths,
            args,
            args.client_registrar_address,
            "client-callrefs",
        )
        export["bestClientCandidate"] = synthesize_candidate_from_callrefs(
            client_dump,
            args.client_registrar_address,
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    build_info = {
        "generatedAt": generated_at,
        "programName": export["programName"],
        "projectDir": str(paths.project_dir),
        "projectName": paths.project_name,
        "ghidraDir": str(paths.ghidra_dir),
        "ghidraScripts": str(paths.ghidra_scripts),
        "outputDir": str(paths.output_dir),
        "driver": str(Path(__file__).resolve()),
        "exportScript": "ExportProtocolRegistrars.java",
    }

    registrars = {
        "generatedAt": generated_at,
        "programName": export["programName"],
        "candidateCount": len(export["candidates"]),
        "bestServerCandidate": export.get("bestServerCandidate"),
        "bestClientCandidate": export.get("bestClientCandidate"),
    }

    payload = {
        "generatedAt": generated_at,
        "programName": export["programName"],
        "candidateCount": len(export["candidates"]),
        "bestServerCandidate": export.get("bestServerCandidate"),
        "bestClientCandidate": export.get("bestClientCandidate"),
    }

    write_json(paths.output_dir / "build-info.json", build_info)
    write_json(paths.output_dir / "registrars.json", registrars)

    if export.get("bestServerCandidate"):
        write_sizes_toml(
            paths.output_dir / "serverProtSizes.generated.toml",
            export["bestServerCandidate"]["samples"],
            "Draft server packet sizes generated from the best Phase 1 registrar candidate",
        )
    if export.get("bestClientCandidate"):
        write_sizes_toml(
            paths.output_dir / "clientProtSizes.generated.toml",
            export["bestClientCandidate"]["samples"],
            "Draft client packet sizes generated from the best Phase 1 registrar candidate",
        )

    write_summary(paths.output_dir / "phase1-summary.md", payload)

    print(json.dumps(
        {
            "outputDir": str(paths.output_dir),
            "registrars": str(paths.output_dir / "registrars.json"),
            "buildInfo": str(paths.output_dir / "build-info.json"),
            "serverSizesToml": str(paths.output_dir / "serverProtSizes.generated.toml"),
            "clientSizesToml": str(paths.output_dir / "clientProtSizes.generated.toml"),
            "summary": str(paths.output_dir / "phase1-summary.md"),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
