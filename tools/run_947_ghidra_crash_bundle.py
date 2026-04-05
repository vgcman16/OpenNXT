from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[1]
TOOLS_DIR = WORKSPACE / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

try:
    from tools.protocol_946_debug_common import (
        classify_headless_error,
        cleanup_ghidra_project_clone,
        clone_ghidra_project,
        resolve_project_location,
        run_headless_postscript,
    )
    from tools.run_947_client_crash_rva_doctor import (
        DEFAULT_CLIENTERROR_DIR,
        DEFAULT_DEBUG_DIR,
        DEFAULT_EXE_PATH,
        DEFAULT_HOOK_DIR,
        DecodedReport,
        FaultEvent,
        decode_clienterror_report,
        find_runtime_module_base,
        find_matching_fault_event,
        load_fault_events,
        load_key_value_file,
        load_pe_support,
        resolve_hook_path,
        select_latest_clienterror_bundle,
        va_to_rva,
    )
except ModuleNotFoundError:
    from protocol_946_debug_common import (
        classify_headless_error,
        cleanup_ghidra_project_clone,
        clone_ghidra_project,
        resolve_project_location,
        run_headless_postscript,
    )
    from run_947_client_crash_rva_doctor import (
        DEFAULT_CLIENTERROR_DIR,
        DEFAULT_DEBUG_DIR,
        DEFAULT_EXE_PATH,
        DEFAULT_HOOK_DIR,
        DecodedReport,
        FaultEvent,
        decode_clienterror_report,
        find_runtime_module_base,
        find_matching_fault_event,
        load_fault_events,
        load_key_value_file,
        load_pe_support,
        resolve_hook_path,
        select_latest_clienterror_bundle,
        va_to_rva,
    )
DEFAULT_GHIDRA_DIR = Path.home() / "Tools" / "ghidra" / "ghidra_12.0.4_PUBLIC"
DEFAULT_PROJECT_DIR = DEFAULT_DEBUG_DIR / "ghidra"
DEFAULT_PROJECT_NAME = "rs2client-947-headless"
DEFAULT_PROGRAM_NAME = "rs2client.exe"
DEFAULT_OUTPUT_DIR = DEFAULT_DEBUG_DIR / "ghidra-crash-bundle-947"
DEFAULT_SCRIPT_PATH = WORKSPACE / "tools"
DEFAULT_SCRIPT_NAME = "GhidraCrashSiteBundle947.java"
DEFAULT_INSTRUCTIONS_BEFORE = 12
DEFAULT_INSTRUCTIONS_AFTER = 24
DEFAULT_ANALYSIS_TIMEOUT = 1800


@dataclass(frozen=True)
class FaultTarget:
    fault_rva: int
    fault_va: str
    image_base: int
    size_of_image: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a headless Ghidra crash-site bundle for the latest 947 nxtclienterror artifact, "
            "bootstrapping a local project if needed."
        )
    )
    parser.add_argument("--clienterror-dir", type=Path, default=DEFAULT_CLIENTERROR_DIR)
    parser.add_argument("--hook-dir", type=Path, default=DEFAULT_HOOK_DIR)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE_PATH)
    parser.add_argument("--ghidra-dir", type=Path, default=DEFAULT_GHIDRA_DIR)
    parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT_DIR)
    parser.add_argument("--project-name", default=DEFAULT_PROJECT_NAME)
    parser.add_argument("--program-name", default=DEFAULT_PROGRAM_NAME)
    parser.add_argument("--script-path", type=Path, default=DEFAULT_SCRIPT_PATH)
    parser.add_argument("--script-name", default=DEFAULT_SCRIPT_NAME)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--fault-rva", type=lambda value: int(value, 0), default=None)
    parser.add_argument("--instructions-before", type=int, default=DEFAULT_INSTRUCTIONS_BEFORE)
    parser.add_argument("--instructions-after", type=int, default=DEFAULT_INSTRUCTIONS_AFTER)
    parser.add_argument(
        "--extra-address",
        action="append",
        default=[],
        help="Extra virtual addresses to inspect in the same headless bundle.",
    )
    parser.add_argument("--analysis-timeout-seconds", type=int, default=DEFAULT_ANALYSIS_TIMEOUT)
    parser.add_argument("--keep-ghidra-clone", action="store_true")
    parser.add_argument("--no-bootstrap-project", action="store_true")
    return parser.parse_args(argv)


def ghidra_project_exists(project_dir: Path, project_name: str) -> bool:
    try:
        resolve_project_location(project_dir, project_name)
        return True
    except FileNotFoundError:
        return False


def run_headless_import(
    *,
    ghidra_dir: Path,
    project_dir: Path,
    project_name: str,
    exe_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    analyze_headless = ghidra_dir / "support" / "analyzeHeadless.bat"
    if not analyze_headless.exists():
        raise FileNotFoundError(f"analyzeHeadless.bat not found at {analyze_headless}")

    project_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(analyze_headless),
        str(project_dir),
        project_name,
        "-import",
        str(exe_path),
        "-overwrite",
        "-analysisTimeoutPerFile",
        str(timeout_seconds),
    ]
    process = subprocess.Popen(
        command,
        cwd=str(WORKSPACE),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = process.communicate(timeout=timeout_seconds + 120)
        timed_out = False
        return_code = process.returncode
    except subprocess.TimeoutExpired:
        process.kill()
        stdout_bytes, stderr_bytes = process.communicate()
        stderr_bytes = (stderr_bytes or b"") + f"\nTIMEOUT after {timeout_seconds + 120} seconds".encode("utf-8")
        timed_out = True
        return_code = -1

    stdout_text = (stdout_bytes or b"").decode("utf-8", errors="replace")
    stderr_text = (stderr_bytes or b"").decode("utf-8", errors="replace")
    return {
        "returnCode": return_code,
        "timedOut": timed_out,
        "command": command,
        "stdoutText": stdout_text,
        "stderrText": stderr_text,
    }


def resolve_fault_target(
    *,
    correlation: dict[str, str],
    image_base: int,
    size_of_image: int,
    explicit_rva: int | None = None,
    fault_event: FaultEvent | None = None,
    runtime_image_base: int | None = None,
) -> FaultTarget:
    if explicit_rva is not None:
        fault_rva = explicit_rva
    else:
        address_text = correlation.get("hookFaultAddress") or (fault_event.address if fault_event else None)
        if not address_text:
            raise ValueError("Could not resolve a hook fault address from the crash artifacts.")
        fault_rva = None
        if runtime_image_base is not None:
            fault_rva = va_to_rva(address_text, runtime_image_base, size_of_image)
        if fault_rva is None:
            fault_rva = va_to_rva(address_text, image_base, size_of_image)
        if fault_rva is None:
            raise ValueError(f"Fault address {address_text} is outside the image range.")

    fault_va = f"0x{image_base + fault_rva:016x}"
    return FaultTarget(
        fault_rva=fault_rva,
        fault_va=fault_va,
        image_base=image_base,
        size_of_image=size_of_image,
    )


def render_markdown(report: dict[str, Any]) -> str:
    ghidra_raw = report.get("ghidraRaw") or {}
    function = ghidra_raw.get("function") or {}
    callers = function.get("callers") or []
    inspected_addresses = ghidra_raw.get("inspectedAddresses") or []
    return "\n".join(
        [
            "# 947 Ghidra Crash Bundle",
            "",
            f"- Clienterror bundle: `{report['clienterrorBundle']}`",
            f"- Hook path: `{report['hookPath']}`",
            f"- Fault RVA: `{report['faultTarget']['faultRva']}`",
            f"- Fault VA: `{report['faultTarget']['faultVa']}`",
            f"- Ghidra raw bundle: `{report['ghidraRawPath']}`",
            f"- Bootstrap performed: `{report['bootstrap']['performed']}`",
            f"- Project: `{report['project']['projectDir']}` / `{report['project']['projectName']}`",
            "",
            "## Function",
            "",
            f"- Name: `{function.get('name', '<none>')}`",
            f"- Entry: `{function.get('entryPoint', '<none>')}`",
            f"- Body: `{function.get('body', '<none>')}`",
            f"- Caller count: `{len(callers)}`",
            "",
            "## Target",
            "",
            f"- Address: `{ghidra_raw.get('targetAddress', '<none>')}`",
            f"- Instruction window entries: `{len(ghidra_raw.get('instructionWindow') or [])}`",
            f"- Exact target refs: `{len(ghidra_raw.get('targetReferences') or [])}`",
            f"- Extra inspected addresses: `{len(inspected_addresses)}`",
            "",
            "## Crash Report",
            "",
            f"- Message: `{(report.get('decodedReport') or {}).get('message', '<none>')}`",
            f"- Decode variant: `{report['summary'].get('decodeVariant', '<none>')}`",
            f"- Hook exception type: `{report['correlation'].get('hookFaultExceptionType', '<none>')}`",
        ]
    ) + "\n"


def collect_module_backtrace_addresses(
    *,
    fault_event: FaultEvent | None,
    image_base: int,
    size_of_image: int,
    fault_va: str,
    explicit_addresses: list[str],
    limit: int = 6,
) -> list[str]:
    unique_addresses: list[str] = []
    seen: set[str] = set()

    def add_address(address_text: str | None) -> None:
        if not address_text:
            return
        try:
            normalized = f"0x{int(address_text, 0):016x}"
        except ValueError:
            return
        if normalized == fault_va or normalized in seen:
            return
        if va_to_rva(normalized, image_base, size_of_image) is None:
            return
        seen.add(normalized)
        unique_addresses.append(normalized)

    for address in explicit_addresses:
        add_address(address)

    if fault_event is not None:
        for frame in fault_event.backtrace:
            add_address(frame.get("address"))
            if len(unique_addresses) >= limit:
                break

    return unique_addresses[:limit]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    bundle = select_latest_clienterror_bundle(args.clienterror_dir)
    summary = load_key_value_file(bundle.summary_path)
    correlation = load_key_value_file(bundle.correlation_path)
    hook_path = resolve_hook_path(args.hook_dir, correlation)
    fault_event = find_matching_fault_event(load_fault_events(hook_path), correlation)
    decoded_report = decode_clienterror_report(bundle.decoded_path, max_qwords=16) if bundle.decoded_path else None

    pefile, _ = load_pe_support()
    pe = pefile.PE(str(args.exe), fast_load=True)
    image_base = int(pe.OPTIONAL_HEADER.ImageBase)
    size_of_image = int(pe.OPTIONAL_HEADER.SizeOfImage)
    runtime_module_base = find_runtime_module_base(hook_path, args.exe)
    fault_target = resolve_fault_target(
        correlation=correlation,
        image_base=image_base,
        size_of_image=size_of_image,
        explicit_rva=args.fault_rva,
        fault_event=fault_event,
        runtime_image_base=runtime_module_base,
    )
    extra_addresses = collect_module_backtrace_addresses(
        fault_event=fault_event,
        image_base=image_base,
        size_of_image=size_of_image,
        fault_va=fault_target.fault_va,
        explicit_addresses=list(args.extra_address or []),
    )

    bootstrap_stdout = args.output_dir / "bootstrap.stdout.log"
    bootstrap_stderr = args.output_dir / "bootstrap.stderr.log"
    headless_stdout = args.output_dir / "headless.stdout.log"
    headless_stderr = args.output_dir / "headless.stderr.log"
    ghidra_raw_path = args.output_dir / "ghidra-raw.json"

    bootstrap_result: dict[str, Any] = {"performed": False, "errorType": None}
    if not ghidra_project_exists(args.project_dir, args.project_name):
        if args.no_bootstrap_project:
            raise FileNotFoundError(
                f"Ghidra project {args.project_name!r} is missing under {args.project_dir}, and bootstrap is disabled."
            )
        bootstrap_result = run_headless_import(
            ghidra_dir=args.ghidra_dir,
            project_dir=args.project_dir,
            project_name=args.project_name,
            exe_path=args.exe,
            timeout_seconds=args.analysis_timeout_seconds,
        )
        bootstrap_stdout.write_text(bootstrap_result["stdoutText"], encoding="utf-8")
        bootstrap_stderr.write_text(bootstrap_result["stderrText"], encoding="utf-8")
        bootstrap_result["performed"] = True
        bootstrap_result["errorType"] = classify_headless_error(
            bootstrap_result["stdoutText"],
            bootstrap_result["stderrText"],
            int(bootstrap_result["returnCode"]),
            output_exists=ghidra_project_exists(args.project_dir, args.project_name),
        )
        if bootstrap_result["returnCode"] != 0 or not ghidra_project_exists(args.project_dir, args.project_name):
            raise RuntimeError(
                f"Ghidra project bootstrap failed ({bootstrap_result['errorType'] or 'unknown-error'}). "
                f"See {bootstrap_stdout} and {bootstrap_stderr}."
            )

    clone_info = clone_ghidra_project(
        project_dir=args.project_dir,
        project_name=args.project_name,
        clone_label="947-crash-bundle",
    )
    try:
        headless_result = run_headless_postscript(
            ghidra_dir=args.ghidra_dir,
            project_dir=Path(clone_info["cloneProjectDir"]),
            project_name=args.project_name,
            script_name=args.script_name,
            script_args=[
                str(ghidra_raw_path),
                fault_target.fault_va,
                str(args.instructions_before),
                str(args.instructions_after),
                *extra_addresses,
            ],
            script_path=args.script_path,
            program_name=args.program_name,
            analyze=False,
            timeout_seconds=max(300, args.analysis_timeout_seconds),
        )
        headless_stdout.write_text(headless_result["stdoutText"], encoding="utf-8")
        headless_stderr.write_text(headless_result["stderrText"], encoding="utf-8")
        headless_result["errorType"] = classify_headless_error(
            headless_result["stdoutText"],
            headless_result["stderrText"],
            int(headless_result["returnCode"]),
            output_exists=ghidra_raw_path.exists(),
        )
        if headless_result["returnCode"] != 0 or not ghidra_raw_path.exists():
            raise RuntimeError(
                f"Ghidra crash bundle failed ({headless_result['errorType'] or 'unknown-error'}). "
                f"See {headless_stdout} and {headless_stderr}."
            )

        ghidra_raw = json.loads(ghidra_raw_path.read_text(encoding="utf-8"))
        cleanup_result = cleanup_ghidra_project_clone(clone_info, keep_clone=args.keep_ghidra_clone)
        report = {
            "tool": "run_947_ghidra_crash_bundle",
            "schemaVersion": 1,
            "generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "clienterrorBundle": bundle.stem,
            "summaryPath": str(bundle.summary_path),
            "correlationPath": str(bundle.correlation_path) if bundle.correlation_path else None,
            "decodedPath": str(bundle.decoded_path) if bundle.decoded_path else None,
            "hookPath": str(hook_path),
            "summary": summary,
            "correlation": correlation,
            "decodedReport": asdict(decoded_report) if isinstance(decoded_report, DecodedReport) else None,
            "faultEvent": asdict(fault_event) if isinstance(fault_event, FaultEvent) else None,
            "runtimeModuleBase": f"0x{runtime_module_base:016x}" if runtime_module_base is not None else None,
            "faultTarget": {
                "faultRva": f"0x{fault_target.fault_rva:08x}",
                "faultVa": fault_target.fault_va,
                "imageBase": f"0x{fault_target.image_base:016x}",
                "sizeOfImage": fault_target.size_of_image,
            },
            "extraAddresses": extra_addresses,
            "project": {
                "projectDir": str(args.project_dir),
                "projectName": args.project_name,
                "programName": args.program_name,
                "cloneInfo": clone_info,
            },
            "bootstrap": bootstrap_result,
            "headless": headless_result,
            "cleanup": cleanup_result,
            "ghidraRawPath": str(ghidra_raw_path),
            "ghidraRaw": ghidra_raw,
        }
        json_path = args.output_dir / "bundle.json"
        md_path = args.output_dir / "bundle.md"
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        md_path.write_text(render_markdown(report), encoding="utf-8")
        print(str(json_path))
        return 0
    finally:
        if not ghidra_raw_path.exists():
            cleanup_ghidra_project_clone(clone_info, keep_clone=args.keep_ghidra_clone)


if __name__ == "__main__":
    raise SystemExit(main())
