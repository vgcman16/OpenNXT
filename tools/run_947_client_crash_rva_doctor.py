from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_DEBUG_DIR = WORKSPACE / "data" / "debug"
DEFAULT_CLIENTERROR_DIR = DEFAULT_DEBUG_DIR / "clienterror"
DEFAULT_HOOK_DIR = DEFAULT_DEBUG_DIR / "direct-rs2client-patch"
DEFAULT_TRANSPORT_PATH = DEFAULT_DEBUG_DIR / "prelogin-transport-events.jsonl"
DEFAULT_EXE_PATH = WORKSPACE / "data" / "clients" / "947" / "win64c" / "patched" / "rs2client.exe"
DEFAULT_OUTPUT_DIR = DEFAULT_DEBUG_DIR / "client-crash-rva-doctor-947"
DEFAULT_MAX_QWORDS = 16
DEFAULT_DISASM_BYTES_BEFORE = 0x40
DEFAULT_DISASM_BYTES_AFTER = 0xC0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Decode the latest 947 nxtclienterror crash bundle, correlate it with the current rs2client hook trace, "
            "disassemble the faulting RVA in the patched client, and summarize the nearby 43596 transport events."
        )
    )
    parser.add_argument("--clienterror-dir", type=Path, default=DEFAULT_CLIENTERROR_DIR)
    parser.add_argument("--hook-dir", type=Path, default=DEFAULT_HOOK_DIR)
    parser.add_argument("--transport-events", type=Path, default=DEFAULT_TRANSPORT_PATH)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--fault-rva", type=lambda value: int(value, 0), default=None)
    parser.add_argument("--max-qwords", type=int, default=DEFAULT_MAX_QWORDS)
    parser.add_argument("--disasm-bytes-before", type=lambda value: int(value, 0), default=DEFAULT_DISASM_BYTES_BEFORE)
    parser.add_argument("--disasm-bytes-after", type=lambda value: int(value, 0), default=DEFAULT_DISASM_BYTES_AFTER)
    return parser.parse_args(argv)


@dataclass(frozen=True)
class ClientErrorBundle:
    stem: str
    summary_path: Path
    correlation_path: Path | None
    decoded_path: Path | None
    data_path: Path | None


@dataclass(frozen=True)
class DecodedReport:
    message: str
    qwords: list[str]
    printable_tail: str
    raw_length: int


@dataclass(frozen=True)
class FaultEvent:
    timestamp: str | None
    address: str | None
    exception_type: str | None
    memory_address: str | None
    operation: str | None
    context: dict[str, str]
    backtrace: list[dict[str, str]]


def parse_key_value_lines(lines: Iterable[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    return data


def load_key_value_file(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    return parse_key_value_lines(path.read_text(encoding="utf-8").splitlines())


def select_latest_clienterror_bundle(clienterror_dir: Path) -> ClientErrorBundle:
    summaries = sorted(clienterror_dir.glob("*.summary.txt"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not summaries:
        raise FileNotFoundError(f"No clienterror summary files found under {clienterror_dir}")
    summary_path = summaries[0]
    stem = summary_path.name.removesuffix(".summary.txt")
    correlation_path = clienterror_dir / f"{stem}.correlation.txt"
    decoded_path = clienterror_dir / f"{stem}.decoded.bin"
    data_path = clienterror_dir / f"{stem}.data.txt"
    return ClientErrorBundle(
        stem=stem,
        summary_path=summary_path,
        correlation_path=correlation_path if correlation_path.exists() else None,
        decoded_path=decoded_path if decoded_path.exists() else None,
        data_path=data_path if data_path.exists() else None,
    )


def parse_iso_instant(value: str | None) -> datetime | None:
    if not value or value == "<none>" or value == "<unknown>":
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_fault_events(path: Path) -> list[FaultEvent]:
    if not path.exists():
        return []
    events: list[FaultEvent] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        is_fault = payload.get("action") == "fault" or payload.get("category") == "client.exception"
        if not is_fault:
            continue
        memory = payload.get("memory") or {}
        context = {str(key): str(value) for key, value in (payload.get("context") or {}).items()}
        backtrace = [
            {
                "address": str(frame.get("address")),
                "symbol": str(frame.get("symbol")),
            }
            for frame in (payload.get("backtrace") or [])
        ]
        timestamp_value = payload.get("timestamp")
        timestamp = None
        if isinstance(timestamp_value, (int, float)):
            timestamp = datetime.fromtimestamp(float(timestamp_value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
        events.append(
            FaultEvent(
                timestamp=timestamp,
                address=str(payload.get("address")) if payload.get("address") is not None else None,
                exception_type=str(payload.get("exceptionType")) if payload.get("exceptionType") is not None else None,
                memory_address=str(memory.get("address")) if memory.get("address") is not None else None,
                operation=str(memory.get("operation")) if memory.get("operation") is not None else None,
                context=context,
                backtrace=backtrace,
            )
        )
    return events


def normalize_hook_path_text(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("/", "\\").casefold()


def find_runtime_module_base(hook_path: Path, exe_path: Path) -> int | None:
    if not hook_path.exists():
        return None

    target_name = exe_path.name.casefold()
    target_path = normalize_hook_path_text(str(exe_path.resolve()))
    best_match: int | None = None

    for raw_line in hook_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        if payload.get("category") != "client.module":
            continue
        base_text = payload.get("base")
        if not isinstance(base_text, str):
            continue
        module_name = str(payload.get("moduleName") or "").casefold()
        module_path = normalize_hook_path_text(str(payload.get("path") or ""))
        if module_name != target_name and module_path != target_path:
            continue
        try:
            best_match = int(base_text, 16)
        except ValueError:
            continue

    return best_match


def resolve_hook_path(hook_dir: Path, correlation: dict[str, str]) -> Path:
    source = correlation.get("hookFaultSource")
    if source:
        candidate = hook_dir / source
        if candidate.exists():
            return candidate
    candidates = sorted(hook_dir.glob("latest-*-hook.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No hook traces found under {hook_dir}")
    return candidates[0]


def find_matching_fault_event(events: list[FaultEvent], correlation: dict[str, str]) -> FaultEvent | None:
    if not events:
        return None
    target_timestamp = correlation.get("hookFaultTimestamp")
    target_address = correlation.get("hookFaultAddress")
    target_exception = correlation.get("hookFaultExceptionType")
    for event in events:
        if target_timestamp and event.timestamp != target_timestamp:
            continue
        if target_address and event.address != target_address:
            continue
        if target_exception and event.exception_type != target_exception:
            continue
        return event
    return events[-1]


def decode_clienterror_report(path: Path, max_qwords: int) -> DecodedReport:
    payload = path.read_bytes()
    message_raw, separator, remainder = payload.partition(b"\x00")
    message = message_raw.decode("ascii", errors="replace")
    qwords: list[str] = []
    for offset in range(0, min(len(remainder), max_qwords * 8), 8):
        chunk = remainder[offset : offset + 8]
        if len(chunk) < 8:
            break
        qword_value = int.from_bytes(chunk, byteorder="little", signed=False)
        qwords.append(f"0x{qword_value:016x}")
    printable_tail = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in remainder)
    return DecodedReport(
        message=message,
        qwords=qwords,
        printable_tail=printable_tail,
        raw_length=len(payload),
    )


def load_transport_tail(path: Path, count: int = 8) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines[-count:]]


def load_pe_support() -> tuple[Any, Any]:
    try:
        import pefile  # type: ignore
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised via runtime only
        raise RuntimeError(
            "Missing PE disassembly support. Install with: python -m pip install pefile capstone"
        ) from exc
    return pefile, (Cs, CS_ARCH_X86, CS_MODE_64)


def disassemble_fault_region(
    exe_path: Path,
    fault_rva: int,
    bytes_before: int,
    bytes_after: int,
) -> dict[str, Any]:
    pefile, capstone_exports = load_pe_support()
    Cs, CS_ARCH_X86, CS_MODE_64 = capstone_exports

    pe = pefile.PE(str(exe_path), fast_load=True)
    image_base = int(pe.OPTIONAL_HEADER.ImageBase)
    size_of_image = int(pe.OPTIONAL_HEADER.SizeOfImage)
    image = pe.get_memory_mapped_image()
    start_rva = max(0, fault_rva - bytes_before)
    end_rva = min(len(image), fault_rva + bytes_after)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    disassembly: list[dict[str, Any]] = []
    for instruction in md.disasm(image[start_rva:end_rva], image_base + start_rva):
        rva = int(instruction.address - image_base)
        disassembly.append(
            {
                "rva": f"0x{rva:08x}",
                "va": f"0x{instruction.address:016x}",
                "mnemonic": instruction.mnemonic,
                "op_str": instruction.op_str,
                "isFault": rva == fault_rva,
            }
        )
    return {
        "imageBase": f"0x{image_base:016x}",
        "sizeOfImage": size_of_image,
        "faultRva": f"0x{fault_rva:08x}",
        "faultVa": f"0x{image_base + fault_rva:016x}",
        "disassembly": disassembly,
    }


def va_to_rva(va_text: str | None, image_base: int, size_of_image: int) -> int | None:
    if not va_text:
        return None
    value = int(va_text, 16)
    rva = value - image_base
    if rva < 0 or rva >= size_of_image:
        return None
    return rva


def summarize_backtrace_rvas(backtrace: list[dict[str, str]], image_base: int, size_of_image: int) -> list[dict[str, str]]:
    internal_frames: list[dict[str, str]] = []
    for frame in backtrace:
        rva = va_to_rva(frame.get("address"), image_base, size_of_image)
        if rva is None:
            continue
        internal_frames.append(
            {
                "address": frame.get("address") or "<none>",
                "rva": f"0x{rva:08x}",
                "symbol": frame.get("symbol") or "<none>",
            }
        )
    return internal_frames


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    correlation = report["correlation"]
    decoded = report["decodedReport"]
    disassembly = report["disassembly"]
    lines = [
        "# 947 Client Crash RVA Doctor",
        "",
        f"- Clienterror bundle: `{report['clienterrorBundle']}`",
        f"- Hook source: `{report['hookPath']}`",
        f"- Fault RVA: `{disassembly['faultRva']}`",
        f"- Fault VA: `{disassembly['faultVa']}`",
        f"- Message: `{decoded['message']}`",
        f"- Decode variant: `{summary.get('decodeVariant', '<none>')}`",
        f"- Hook exception type: `{correlation.get('hookFaultExceptionType', '<unknown>')}`",
        f"- Hook address: `{correlation.get('hookFaultAddress', '<unknown>')}`",
        "",
        "## Disassembly",
        "",
    ]
    for instruction in disassembly["disassembly"]:
        marker = ">>" if instruction["isFault"] else "  "
        lines.append(
            f"- {marker} `{instruction['rva']}` `{instruction['mnemonic']}` `{instruction['op_str']}`"
        )
    lines.extend(
        [
            "",
            "## Backtrace RVAs",
            "",
        ]
    )
    for frame in report["internalBacktrace"]:
        lines.append(f"- `{frame['rva']}` from `{frame['address']}` `{frame['symbol']}`")
    lines.extend(
        [
            "",
            "## Decoded Report",
            "",
            f"- Raw bytes: `{decoded['rawLength']}`",
            f"- Message: `{decoded['message']}`",
            f"- Qwords: `{', '.join(decoded['qwords']) if decoded['qwords'] else '<none>'}`",
            f"- Printable tail: `{decoded['printableTail']}`",
            "",
            "## Nearby Transport",
            "",
        ]
    )
    for event in report["transportTail"]:
        lines.append(
            f"- `{event.get('timestamp', '<unknown>')}` `{event.get('event', '<unknown>')}` "
            f"`{event.get('remoteAddress', '<unknown>')}` preview=`{event.get('previewHex', '<none>')}` "
            f"handshake=`{event.get('handshakeType', '<none>')}`"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bundle = select_latest_clienterror_bundle(args.clienterror_dir)
    summary = load_key_value_file(bundle.summary_path)
    correlation = load_key_value_file(bundle.correlation_path)
    hook_path = resolve_hook_path(args.hook_dir, correlation)
    fault_event = find_matching_fault_event(load_fault_events(hook_path), correlation)
    decoded_report = decode_clienterror_report(bundle.decoded_path, args.max_qwords) if bundle.decoded_path else None

    pefile, _ = load_pe_support()
    pe = pefile.PE(str(args.exe), fast_load=True)
    preferred_image_base = int(pe.OPTIONAL_HEADER.ImageBase)
    size_of_image = int(pe.OPTIONAL_HEADER.SizeOfImage)
    runtime_module_base = find_runtime_module_base(hook_path, args.exe)

    if args.fault_rva is not None:
        fault_rva = args.fault_rva
    else:
        hook_fault_address = correlation.get("hookFaultAddress")
        if not hook_fault_address:
            raise ValueError("No hookFaultAddress was found in the correlation artifact.")
        fault_va = int(hook_fault_address, 16)
        fault_rva = None
        if runtime_module_base is not None:
            candidate_rva = fault_va - runtime_module_base
            if 0 <= candidate_rva < size_of_image:
                fault_rva = candidate_rva
        if fault_rva is None:
            fault_rva = fault_va - preferred_image_base

    disassembly = disassemble_fault_region(
        exe_path=args.exe,
        fault_rva=fault_rva,
        bytes_before=args.disasm_bytes_before,
        bytes_after=args.disasm_bytes_after,
    )
    image_base = int(disassembly["imageBase"], 16)
    size_of_image = int(disassembly["sizeOfImage"])
    internal_backtrace = summarize_backtrace_rvas(fault_event.backtrace if fault_event else [], image_base, size_of_image)

    decoded_payload = None
    if decoded_report is not None:
        decoded_payload = {
            "message": decoded_report.message,
            "qwords": decoded_report.qwords,
            "printableTail": decoded_report.printable_tail,
            "rawLength": decoded_report.raw_length,
        }

    report = {
        "tool": "run_947_client_crash_rva_doctor",
        "schemaVersion": 1,
        "clienterrorBundle": bundle.stem,
        "summaryPath": str(bundle.summary_path),
        "correlationPath": str(bundle.correlation_path) if bundle.correlation_path else None,
        "decodedPath": str(bundle.decoded_path) if bundle.decoded_path else None,
        "hookPath": str(hook_path),
        "summary": summary,
        "correlation": correlation,
        "decodedReport": decoded_payload,
        "faultEvent": asdict(fault_event) if fault_event else None,
        "runtimeModuleBase": f"0x{runtime_module_base:016x}" if runtime_module_base is not None else None,
        "disassembly": disassembly,
        "internalBacktrace": internal_backtrace,
        "transportTail": load_transport_tail(args.transport_events),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "client-crash-rva-doctor.json"
    md_path = args.output_dir / "client-crash-rva-doctor.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(str(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
