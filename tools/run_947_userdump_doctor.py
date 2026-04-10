from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_DEBUG_DIR = WORKSPACE / "data" / "debug"
DEFAULT_USERDUMP_ROOT = DEFAULT_DEBUG_DIR / "userdumps" / "947-client-only"
DEFAULT_PROBE_PATH = DEFAULT_DEBUG_DIR / "frida-crash-probe" / "latest-client-only.jsonl"
DEFAULT_OUTPUT_DIR = DEFAULT_DEBUG_DIR / "userdump-doctor-947"
DEFAULT_EXE_NAME = "rs2client.exe"
DEFAULT_STACK_QWORDS = 32
DEFAULT_MEMORY_BYTES = 64
DEFAULT_DISASM_BEFORE = 0x20
DEFAULT_DISASM_AFTER = 0x60
WAIT_MODULE_SUFFIXES = (
    "ntdll.dll",
    "kernelbase.dll",
    "kernel32.dll",
    "win32u.dll",
)


@dataclass(frozen=True)
class ModuleSpan:
    name: str
    base: int
    size: int

    @property
    def end(self) -> int:
        return self.base + self.size


def module_tail(name: str | None) -> str | None:
    if not name:
        return None
    return Path(name).name.lower()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Parse the newest 947 client ProcDump artifact, resolve the native exception, "
            "summarize register/stack state, and correlate it with the latest Frida crash probe output."
        )
    )
    parser.add_argument("--userdump-root", type=Path, default=DEFAULT_USERDUMP_ROOT)
    parser.add_argument("--probe-path", type=Path, default=DEFAULT_PROBE_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--exe-name", default=DEFAULT_EXE_NAME)
    parser.add_argument("--stack-qwords", type=int, default=DEFAULT_STACK_QWORDS)
    parser.add_argument("--memory-bytes", type=int, default=DEFAULT_MEMORY_BYTES)
    parser.add_argument("--disasm-before", type=lambda value: int(value, 0), default=DEFAULT_DISASM_BEFORE)
    parser.add_argument("--disasm-after", type=lambda value: int(value, 0), default=DEFAULT_DISASM_AFTER)
    return parser.parse_args(argv)


def format_hex(value: int | None, width: int = 16) -> str | None:
    if value is None:
        return None
    return f"0x{value:0{width}x}"


def decode_access_operation(exception_information: list[int]) -> str | None:
    if not exception_information:
        return None
    operation = int(exception_information[0])
    return {
        0: "read",
        1: "write",
        8: "execute",
    }.get(operation, f"unknown-{operation}")


def select_latest_dump(userdump_root: Path) -> Path:
    dumps = sorted(userdump_root.rglob("*.dmp"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not dumps:
        raise FileNotFoundError(f"No dump files found under {userdump_root}")
    return dumps[0]


def load_probe_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not raw_line.strip():
            continue
        try:
            events.append(json.loads(raw_line))
        except json.JSONDecodeError:
            continue
    return events


def select_latest_probe_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    interesting = ("caller-guard-skip", "state-repair-applied", "state-checkpoint", "fault-family-match")
    latest: dict[str, Any] = {}
    for action in interesting:
        for event in reversed(events):
            if event.get("action") == action:
                latest[action] = event
                break
    return latest


def build_module_spans(md, exe_name: str) -> tuple[list[ModuleSpan], ModuleSpan | None]:
    spans = [
        ModuleSpan(name=module.name, base=int(module.baseaddress), size=int(module.size))
        for module in md.modules.modules
    ]
    primary = next((span for span in spans if span.name.lower().endswith(exe_name.lower())), None)
    return spans, primary


def resolve_module_for_address(modules: list[ModuleSpan], address: int) -> ModuleSpan | None:
    for module in modules:
        if module.base <= address < module.end:
            return module
    return None


def build_context_dict(ctx: Any) -> dict[str, str | None]:
    registers = ("Rip", "Rsp", "Rbp", "Rax", "Rbx", "Rcx", "Rdx", "Rsi", "Rdi", "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15")
    return {
        name: format_hex(getattr(ctx, name))
        for name in registers
    }


def build_thread_summary(thread: Any, modules: list[ModuleSpan], primary: ModuleSpan | None) -> dict[str, Any]:
    ctx = thread.ContextObject
    rip = int(getattr(ctx, "Rip", 0))
    rsp = int(getattr(ctx, "Rsp", 0))
    module = resolve_module_for_address(modules, rip)
    summary: dict[str, Any] = {
        "threadId": int(thread.ThreadId),
        "rip": format_hex(rip),
        "rsp": format_hex(rsp),
        "moduleName": module.name if module is not None else None,
        "moduleBase": format_hex(module.base) if module is not None else None,
        "moduleRva": format_hex(rip - module.base, width=8) if module is not None else None,
    }
    if primary is not None and module is not None and module.name == primary.name:
        summary["isPrimaryModule"] = True
    return summary


def summarize_threads(threads: list[Any], modules: list[ModuleSpan], primary: ModuleSpan | None) -> list[dict[str, Any]]:
    summaries = [build_thread_summary(thread, modules, primary) for thread in threads]

    def sort_key(summary: dict[str, Any]) -> tuple[int, int, int]:
        module_name = module_tail(summary.get("moduleName"))
        return (
            0 if summary.get("isPrimaryModule") else 1,
            1 if module_name in WAIT_MODULE_SUFFIXES else 0,
            int(summary["threadId"]),
        )

    summaries.sort(key=sort_key)
    return summaries


def select_focus_thread_summary(thread_summaries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not thread_summaries:
        return None

    def sort_key(summary: dict[str, Any]) -> tuple[int, int, int]:
        module_name = module_tail(summary.get("moduleName"))
        return (
            0 if summary.get("isPrimaryModule") else 1,
            1 if module_name in WAIT_MODULE_SUFFIXES else 0,
            int(summary["threadId"]),
        )

    return min(thread_summaries, key=sort_key)


def resolve_primary_exe_path(primary: ModuleSpan | None, exe_name: str) -> Path:
    if primary is not None:
        candidate = Path(primary.name)
        if candidate.exists():
            return candidate
    return WORKSPACE / "data" / "clients" / "947" / "win64c" / "patched" / exe_name


def safe_read(reader, address: int, size: int) -> bytes | None:
    try:
        return reader.read(address, size)
    except Exception:
        return None


def safe_memory_preview(reader, address: int, size: int, modules: list[ModuleSpan], primary: ModuleSpan | None) -> dict[str, Any]:
    preview = {
        "address": format_hex(address),
        "bytesRequested": size,
    }
    data = safe_read(reader, address, size)
    if data is None:
        preview["readable"] = False
        preview["hex"] = None
        preview["ascii"] = None
        return preview

    preview["readable"] = True
    preview["hex"] = data.hex()
    preview["ascii"] = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in data)
    if len(data) >= 8:
        qword = int.from_bytes(data[:8], "little", signed=False)
        preview["qword0"] = format_hex(qword)
        module = resolve_module_for_address(modules, qword)
        if module is not None:
            preview["qword0Module"] = module.name
            if primary is not None and module.name == primary.name:
                preview["qword0Rva"] = format_hex(qword - primary.base, width=8)
    return preview


def stack_qwords_from_bytes(
    stack_base: int,
    data: bytes | None,
    modules: list[ModuleSpan],
    primary: ModuleSpan | None,
) -> list[dict[str, Any]]:
    if data is None:
        return []
    qwords: list[dict[str, Any]] = []
    for offset in range(0, len(data), 8):
        chunk = data[offset : offset + 8]
        if len(chunk) < 8:
            break
        value = int.from_bytes(chunk, "little", signed=False)
        record: dict[str, Any] = {
            "stackAddress": format_hex(stack_base + offset),
            "value": format_hex(value),
        }
        module = resolve_module_for_address(modules, value)
        if module is not None:
            record["module"] = module.name
            record["moduleBase"] = format_hex(module.base)
            if primary is not None and module.name == primary.name:
                record["rva"] = format_hex(value - primary.base, width=8)
        qwords.append(record)
    return qwords


def select_internal_stack_sites(stack_qwords: list[dict[str, Any]], primary: ModuleSpan | None, limit: int = 6) -> list[int]:
    if primary is None:
        return []
    results: list[int] = []
    seen: set[int] = set()
    for qword in stack_qwords:
        if qword.get("module") != primary.name:
            continue
        value_text = qword.get("value")
        if not isinstance(value_text, str):
            continue
        value = int(value_text, 16)
        if value in seen:
            continue
        seen.add(value)
        results.append(value)
        if len(results) >= limit:
            break
    return results


def load_pe_support() -> tuple[Any, Any]:
    try:
        import pefile  # type: ignore
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Missing PE disassembly support. Install with: python -m pip install pefile capstone"
        ) from exc
    return pefile, (Cs, CS_ARCH_X86, CS_MODE_64)


def disassemble_sites(
    exe_path: Path,
    primary: ModuleSpan | None,
    sites: list[int],
    bytes_before: int,
    bytes_after: int,
) -> list[dict[str, Any]]:
    if primary is None or not sites:
        return []

    pefile, capstone_exports = load_pe_support()
    Cs, CS_ARCH_X86, CS_MODE_64 = capstone_exports
    pe = pefile.PE(str(exe_path), fast_load=True)
    image = pe.get_memory_mapped_image()
    md = Cs(CS_ARCH_X86, CS_MODE_64)

    records: list[dict[str, Any]] = []
    for site in sites:
        rva = site - primary.base
        start_rva = max(0, rva - bytes_before)
        end_rva = min(len(image), rva + bytes_after)
        instructions: list[dict[str, Any]] = []
        for insn in md.disasm(image[start_rva:end_rva], primary.base + start_rva):
            insn_rva = int(insn.address - primary.base)
            instructions.append(
                {
                    "va": format_hex(int(insn.address)),
                    "rva": format_hex(insn_rva, width=8),
                    "mnemonic": insn.mnemonic,
                    "opStr": insn.op_str,
                    "isSite": int(insn.address) == site,
                }
            )
        records.append(
            {
                "siteVa": format_hex(site),
                "siteRva": format_hex(rva, width=8),
                "instructions": instructions,
            }
        )
    return records


def render_markdown(report: dict[str, Any]) -> str:
    exception = report["exception"]
    capture_mode = report.get("captureMode", "exception")
    focus_thread = report.get("focusThread") or {}
    lines = [
        "# 947 Userdump Doctor",
        "",
        f"- Dump: `{report['dumpPath']}`",
        f"- Capture mode: `{capture_mode}`",
        f"- Thread id: `{report['threadId']}`",
        f"- Focus RIP: `{focus_thread.get('rip', '<unknown>')}`",
        f"- Focus module: `{focus_thread.get('moduleName', '<unknown>')}`",
        f"- Focus RVA: `{focus_thread.get('moduleRva', '<unknown>')}`",
        "",
    ]
    if exception is not None:
        lines.extend(
            [
                f"- Exception code: `{exception['code']}`",
                f"- Access operation: `{exception['accessOperation'] or '<unknown>'}`",
                f"- Exception address: `{exception['address']}`",
                f"- Exception module: `{exception['moduleName'] or '<none>'}`",
                f"- Exception RVA: `{exception['moduleRva'] or '<none>'}`",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "- Exception stream: `<none>`",
                "",
            ]
        )

    thread_summaries = report.get("threadSummaries") or []
    if thread_summaries:
        lines.extend(
            [
                "## Threads",
                "",
            ]
        )
        for summary in thread_summaries[:16]:
            bits = [
                f"`tid={summary['threadId']}`",
                f"`rip={summary['rip']}`",
            ]
            if summary.get("moduleName"):
                bits.append(f"module=`{summary['moduleName']}`")
            if summary.get("moduleRva"):
                bits.append(f"rva=`{summary['moduleRva']}`")
            if summary.get("isPrimaryModule"):
                bits.append("focus=`primary-module`")
            lines.append(f"- {' '.join(bits)}")
        lines.append("")

    lines.extend(
        [
        "## Registers",
        "",
        ]
    )
    for name, value in report["context"].items():
        lines.append(f"- `{name}` = `{value}`")

    lines.extend(
        [
            "",
            "## Probe Correlation",
            "",
        ]
    )
    for action, event in report["probeSummary"].items():
        lines.append(f"- `{action}` => `{json.dumps(event, sort_keys=True)}`")

    lines.extend(
        [
            "",
            "## Stack Qwords",
            "",
        ]
    )
    for qword in report["stackQwords"]:
        bits = [f"`{qword['stackAddress']}` -> `{qword['value']}`"]
        if qword.get("module"):
            bits.append(f"module=`{qword['module']}`")
        if qword.get("rva"):
            bits.append(f"rva=`{qword['rva']}`")
        lines.append(f"- {' '.join(bits)}")

    lines.extend(
        [
            "",
            "## Internal Sites",
            "",
        ]
    )
    for site in report["internalStackSites"]:
        lines.append(f"- `{site['siteVa']}` `{site['siteRva']}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        from minidump.minidumpfile import MinidumpFile  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Missing dump parser support. Install with: python -m pip install minidump") from exc

    dump_path = select_latest_dump(args.userdump_root)
    md = MinidumpFile.parse(str(dump_path))
    reader = md.get_reader()
    modules, primary = build_module_spans(md, args.exe_name)
    thread_summaries = summarize_threads(md.threads.threads, modules, primary)
    focus_summary = select_focus_thread_summary(thread_summaries)
    if focus_summary is None:
        raise RuntimeError(f"No threads were available in dump {dump_path}")

    thread = next(thread for thread in md.threads.threads if int(thread.ThreadId) == int(focus_summary["threadId"]))
    ctx = thread.ContextObject
    context = build_context_dict(ctx)

    exception_stream = None
    exception = None
    exception_module = None
    capture_mode = "manual-hang"
    if md.exception is not None and md.exception.exception_records:
        exception_stream = md.exception.exception_records[0]
        exception = exception_stream.ExceptionRecord
        exception_address = int(exception.ExceptionAddress)
        exception_module = resolve_module_for_address(modules, exception_address)
        capture_mode = "exception"

    stack_data = safe_read(reader, int(ctx.Rsp), args.stack_qwords * 8)
    stack_qwords = stack_qwords_from_bytes(int(ctx.Rsp), stack_data, modules, primary)
    internal_sites = select_internal_stack_sites(stack_qwords, primary)
    focus_rip = int(getattr(ctx, "Rip"))
    focus_and_stack_sites = [focus_rip] + [site for site in internal_sites if site != focus_rip]

    probe_events = load_probe_events(args.probe_path)
    probe_summary = select_latest_probe_events(probe_events)

    register_previews = {
        name: safe_memory_preview(reader, int(getattr(ctx, name)), args.memory_bytes, modules, primary)
        for name in ("Rsp", "Rbp", "Rcx", "R8", "R14", "R15")
    }

    report = {
        "tool": "run_947_userdump_doctor",
        "schemaVersion": 2,
        "captureMode": capture_mode,
        "dumpPath": str(dump_path),
        "probePath": str(args.probe_path),
        "threadId": int(thread.ThreadId),
        "exception": (
            {
                "code": str(exception.ExceptionCode),
                "flags": int(exception.ExceptionFlags),
                "address": format_hex(exception_address),
                "accessOperation": decode_access_operation(list(exception.ExceptionInformation or [])),
                "exceptionInformation": [format_hex(int(value)) for value in list(exception.ExceptionInformation or [])],
                "moduleName": exception_module.name if exception_module is not None else None,
                "moduleBase": format_hex(exception_module.base) if exception_module is not None else None,
                "moduleRva": format_hex(exception_address - exception_module.base, width=8) if exception_module is not None else None,
            }
            if exception is not None
            else None
        ),
        "primaryModule": asdict(primary) if primary is not None else None,
        "focusThread": focus_summary,
        "threadSummaries": thread_summaries,
        "context": context,
        "registerPreviews": register_previews,
        "stackQwords": stack_qwords,
        "internalStackSites": disassemble_sites(
            exe_path=resolve_primary_exe_path(primary, args.exe_name),
            primary=primary,
            sites=focus_and_stack_sites,
            bytes_before=args.disasm_before,
            bytes_after=args.disasm_after,
        ),
        "probeSummary": probe_summary,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "userdump-doctor.json"
    md_path = args.output_dir / "userdump-doctor.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(str(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
