from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_IMM, X86_OP_MEM


DEFAULT_BINARY = Path(
    r"C:\Users\skull\Documents\RuneScape\OpenNXT-mitm\data\clients\947\win64c\patched\rs2client.exe"
)
DEFAULT_OUTPUT_ROOT = Path(
    r"C:\Users\skull\Documents\RuneScape\OpenNXT-mitm\data\debug\field-ref-scan-947"
)


@dataclass(frozen=True)
class DisassembledInstruction:
    address: int
    rva: int
    size: int
    mnemonic: str
    op_str: str
    bytes_hex: str
    section_name: str
    mem_displacements: tuple[int, ...]
    imm_values: tuple[int, ...]


@dataclass(frozen=True)
class ExecutableSection:
    name: str
    virtual_address: int
    rva: int
    data: bytes


def _parse_int(value: str) -> int:
    return int(value, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan the 947 rs2client.exe for references to a structure field offset."
    )
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY, help="Target rs2client.exe")
    parser.add_argument("--offset", required=True, type=_parse_int, help="Field offset to search for")
    parser.add_argument(
        "--include-immediates",
        action="store_true",
        help="Also match immediate operands equal to the requested value",
    )
    parser.add_argument(
        "--context",
        type=int,
        default=4,
        help="Instructions of context before/after each match",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory where JSON/Markdown reports are written",
    )
    return parser.parse_args()


def load_executable_sections(binary_path: Path) -> tuple[int, list[ExecutableSection]]:
    pe = pefile.PE(str(binary_path))
    image_base = pe.OPTIONAL_HEADER.ImageBase
    sections: list[ExecutableSection] = []
    for section in pe.sections:
        if not (section.Characteristics & 0x20000000):
            continue
        sections.append(
            ExecutableSection(
                name=section.Name.rstrip(b"\x00").decode("ascii", errors="replace"),
                virtual_address=image_base + section.VirtualAddress,
                rva=int(section.VirtualAddress),
                data=section.get_data(),
            )
        )
    return image_base, sections


def _disassembler() -> Cs:
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    return md


def _decode_instruction(
    *,
    image_base: int,
    section: ExecutableSection,
    start_index: int,
) -> DisassembledInstruction | None:
    md = _disassembler()
    window = section.data[start_index : start_index + 15]
    for insn in md.disasm(window, section.virtual_address + start_index):
        if int(insn.address) != section.virtual_address + start_index:
            continue
        mem_displacements: list[int] = []
        imm_values: list[int] = []
        for operand in insn.operands:
            if operand.type == X86_OP_MEM:
                mem_displacements.append(int(operand.mem.disp))
            elif operand.type == X86_OP_IMM:
                imm_values.append(int(operand.imm))
        return DisassembledInstruction(
            address=int(insn.address),
            rva=int(insn.address - image_base),
            size=int(insn.size),
            mnemonic=insn.mnemonic,
            op_str=insn.op_str,
            bytes_hex=bytes(insn.bytes).hex(),
            section_name=section.name,
            mem_displacements=tuple(mem_displacements),
            imm_values=tuple(imm_values),
        )
    return None


def _decode_forward_context(
    *,
    image_base: int,
    section: ExecutableSection,
    start_index: int,
    instruction_count: int,
) -> list[dict[str, Any]]:
    md = _disassembler()
    entries: list[dict[str, Any]] = []
    window = section.data[start_index : start_index + max(64, instruction_count * 15)]
    for insn in md.disasm(window, section.virtual_address + start_index):
        entries.append(
            {
                "address": f"0x{int(insn.address):016x}",
                "rva": f"0x{int(insn.address - image_base):08x}",
                "mnemonic": insn.mnemonic,
                "opStr": insn.op_str,
                "bytesHex": bytes(insn.bytes).hex(),
            }
        )
        if len(entries) >= instruction_count:
            break
    return entries


def scan_field_refs(
    *,
    image_base: int,
    sections: list[ExecutableSection],
    offset: int,
    include_immediates: bool,
    context: int,
) -> list[dict[str, Any]]:
    candidate_matches: dict[int, tuple[DisassembledInstruction, ExecutableSection, int]] = {}
    needle = offset.to_bytes(4, "little", signed=False)

    for section in sections:
        search_from = 0
        while True:
            hit_index = section.data.find(needle, search_from)
            if hit_index < 0:
                break
            hit_candidates: list[tuple[DisassembledInstruction, ExecutableSection, int]] = []
            start_floor = max(0, hit_index - 10)
            for start_index in range(start_floor, hit_index + 1):
                instruction = _decode_instruction(
                    image_base=image_base,
                    section=section,
                    start_index=start_index,
                )
                if instruction is None:
                    continue
                end_index = start_index + instruction.size
                if not (start_index <= hit_index < end_index):
                    continue
                matched_mem = [value for value in instruction.mem_displacements if value == offset]
                matched_imm = [value for value in instruction.imm_values if value == offset] if include_immediates else []
                if not matched_mem and not matched_imm:
                    continue
                hit_candidates.append((instruction, section, start_index))
            if hit_candidates:
                instruction, hit_section, start_index = max(
                    hit_candidates,
                    key=lambda item: (item[0].size, -item[2]),
                )
                candidate_matches[instruction.address] = (instruction, hit_section, start_index)
            search_from = hit_index + 1

    matches: list[dict[str, Any]] = []
    for instruction_address in sorted(candidate_matches):
        instruction, section, start_index = candidate_matches[instruction_address]
        matched_mem = [value for value in instruction.mem_displacements if value == offset]
        matched_imm = [value for value in instruction.imm_values if value == offset] if include_immediates else []
        raw_start = max(0, start_index - 16)
        raw_end = min(len(section.data), start_index + instruction.size + 32)
        matches.append(
            {
                "address": f"0x{instruction.address:016x}",
                "rva": f"0x{instruction.rva:08x}",
                "mnemonic": instruction.mnemonic,
                "opStr": instruction.op_str,
                "bytesHex": instruction.bytes_hex,
                "section": instruction.section_name,
                "matchedMemoryDisplacements": [f"0x{value:x}" for value in matched_mem],
                "matchedImmediates": [f"0x{value:x}" for value in matched_imm],
                "rawWindowStartRva": f"0x{section.rva + raw_start:08x}",
                "rawWindowHex": section.data[raw_start:raw_end].hex(),
                "context": _decode_forward_context(
                    image_base=image_base,
                    section=section,
                    start_index=start_index,
                    instruction_count=max(1, context + 1),
                ),
            }
        )
    return matches


def build_markdown(binary_path: Path, offset: int, include_immediates: bool, matches: list[dict[str, Any]]) -> str:
    lines = [
        "# 947 Field Reference Scan",
        "",
        f"- Binary: `{binary_path}`",
        f"- Offset: `0x{offset:x}`",
        f"- Include immediates: `{include_immediates}`",
        f"- Match count: `{len(matches)}`",
        "",
    ]
    for index, match in enumerate(matches, start=1):
        lines.append(f"## Match {index}")
        lines.append("")
        lines.append(f"- Address: `{match['address']}`")
        lines.append(f"- RVA: `{match['rva']}`")
        lines.append(f"- Instruction: `{match['mnemonic']} {match['opStr']}`")
        lines.append(f"- Bytes: `{match['bytesHex']}`")
        lines.append(f"- Section: `{match['section']}`")
        if match["matchedMemoryDisplacements"]:
            lines.append(f"- Memory displacements: `{', '.join(match['matchedMemoryDisplacements'])}`")
        if match["matchedImmediates"]:
            lines.append(f"- Immediate values: `{', '.join(match['matchedImmediates'])}`")
        lines.append(f"- Raw window start RVA: `{match['rawWindowStartRva']}`")
        lines.append(f"- Raw window hex: `{match['rawWindowHex']}`")
        lines.append("")
        lines.append("```text")
        for context_entry in match["context"]:
            marker = ">>" if context_entry["address"] == match["address"] else "  "
            lines.append(f"{marker} {context_entry['address']}  {context_entry['mnemonic']} {context_entry['opStr']}".rstrip())
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    image_base, sections = load_executable_sections(args.binary)
    matches = scan_field_refs(
        image_base=image_base,
        sections=sections,
        offset=args.offset,
        include_immediates=args.include_immediates,
        context=args.context,
    )
    output_dir = args.output_root / f"offset-{args.offset:08x}"
    output_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "tool": "find_947_field_refs",
        "binary": str(args.binary),
        "offset": f"0x{args.offset:x}",
        "includeImmediates": args.include_immediates,
        "matchCount": len(matches),
        "matches": matches,
    }
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(
        build_markdown(args.binary, args.offset, args.include_immediates, matches),
        encoding="utf-8",
    )
    print(json.dumps({"jsonPath": str(json_path), "markdownPath": str(markdown_path), "matchCount": len(matches)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
