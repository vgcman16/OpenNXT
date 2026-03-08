#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class PacketCandidate:
    name: str
    source_opcode: int
    size: int
    target_opcodes: List[int]
    source_named_same_size: List[str]
    has_shape_file: bool

    @property
    def target_count(self) -> int:
        return len(self.target_opcodes)

    @property
    def source_named_count(self) -> int:
        return len(self.source_named_same_size)

    @property
    def confidence(self) -> str:
        if self.target_count == 1 and self.source_named_count == 1:
            return "high"
        if self.target_count <= 2 and self.source_named_count <= 2:
            return "medium"
        if self.target_count <= 4:
            return "low"
        return "weak"


def parse_values_toml(path: Path) -> Dict[int, int | str]:
    values: Dict[int, int | str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("[") or line.startswith("#"):
            continue
        key_raw, _, value_raw = line.partition("=")
        if not _:
            continue
        key = int(key_raw.strip())
        value = value_raw.strip()
        if value.startswith('"') and value.endswith('"'):
            values[key] = value[1:-1]
        else:
            values[key] = int(value)
    return values


def bucket_by_size(sizes: Dict[int, int]) -> Dict[int, List[int]]:
    buckets: Dict[int, List[int]] = {}
    for opcode, size in sorted(sizes.items()):
        buckets.setdefault(size, []).append(opcode)
    return buckets


def named_packets(
    source_sizes: Dict[int, int],
    source_names: Dict[int, str],
    target_sizes: Dict[int, int],
    shapes_dir: Path,
) -> List[PacketCandidate]:
    target_buckets = bucket_by_size(target_sizes)
    source_named_buckets: Dict[int, List[str]] = {}
    for opcode, name in source_names.items():
        size = source_sizes.get(opcode)
        if size is None:
            continue
        source_named_buckets.setdefault(size, []).append(name)

    candidates: List[PacketCandidate] = []
    for opcode, name in sorted(source_names.items()):
        size = source_sizes.get(opcode)
        if size is None:
            continue
        candidates.append(
            PacketCandidate(
                name=name,
                source_opcode=opcode,
                size=size,
                target_opcodes=target_buckets.get(size, []),
                source_named_same_size=sorted(source_named_buckets.get(size, [])),
                has_shape_file=(shapes_dir / f"{name}.txt").exists(),
            )
        )
    return candidates


def format_opcode_list(opcodes: Iterable[int]) -> str:
    values = list(opcodes)
    if not values:
        return "-"
    return ", ".join(str(v) for v in values)


def render_candidates(title: str, candidates: List[PacketCandidate]) -> List[str]:
    lines = [f"## {title}", ""]
    if not candidates:
        lines.append("No candidates in this bucket.")
        lines.append("")
        return lines

    lines.append("| Name | 919 Opcode | Size | 946 Candidates | Shape File | Notes |")
    lines.append("| --- | ---: | ---: | --- | --- | --- |")
    for candidate in candidates:
        notes: List[str] = []
        if candidate.source_named_count > 1:
            notes.append(
                "919 same-size names: " + ", ".join(candidate.source_named_same_size)
            )
        if candidate.target_count == 1 and candidate.source_named_count == 1:
            notes.append("unique size on both sides")
        elif candidate.target_count == 0:
            notes.append("size missing in 946")
        lines.append(
            "| "
            + candidate.name
            + f" | {candidate.source_opcode} | {candidate.size} | "
            + format_opcode_list(candidate.target_opcodes)
            + " | "
            + ("yes" if candidate.has_shape_file else "no")
            + " | "
            + ("; ".join(notes) if notes else "-")
            + " |"
        )
    lines.append("")
    return lines


def render_size_bucket_summary(title: str, candidates: List[PacketCandidate]) -> List[str]:
    lines = [f"## {title}", ""]
    if not candidates:
        lines.append("No candidates available.")
        lines.append("")
        return lines

    size_to_candidates: Dict[int, List[PacketCandidate]] = {}
    for candidate in candidates:
        size_to_candidates.setdefault(candidate.size, []).append(candidate)

    lines.append("| Size | 919 Named Packets | 946 Opcodes |")
    lines.append("| ---: | --- | --- |")
    for size in sorted(size_to_candidates):
        bucket = size_to_candidates[size]
        source_names = ", ".join(candidate.name for candidate in bucket)
        target_opcodes = format_opcode_list(bucket[0].target_opcodes)
        lines.append(f"| {size} | {source_names} | {target_opcodes} |")
    lines.append("")
    return lines


def render_client_zero_size(target_sizes: Dict[int, int]) -> List[str]:
    zeroes = [opcode for opcode, size in sorted(target_sizes.items()) if size == 0]
    lines = ["## 946 Client Zero-Size Shortlist", ""]
    if zeroes:
        lines.append(
            "Size `0` client packets are strong `NO_TIMEOUT` / keepalive / tick-loop candidates:"
        )
        lines.append("")
        lines.append("- `" + "`, `".join(str(opcode) for opcode in zeroes) + "`")
        lines.append("")
    else:
        lines.append("No zero-size client packets found.")
        lines.append("")
    return lines


def build_report(repo_root: Path, source_build: str, target_build: str) -> str:
    prot_root = repo_root / "data" / "prot"
    source_root = prot_root / source_build
    target_root = prot_root / target_build

    source_client_sizes = {
        k: int(v)
        for k, v in parse_values_toml(source_root / "clientProtSizes.toml").items()
    }
    source_client_names = {
        k: str(v)
        for k, v in parse_values_toml(source_root / "clientProtNames.toml").items()
    }
    source_server_sizes = {
        k: int(v)
        for k, v in parse_values_toml(source_root / "serverProtSizes.toml").items()
    }
    source_server_names = {
        k: str(v)
        for k, v in parse_values_toml(source_root / "serverProtNames.toml").items()
    }

    target_client_sizes = {
        k: int(v)
        for k, v in parse_values_toml(target_root / "clientProtSizes.toml").items()
    }
    target_server_sizes = {
        k: int(v)
        for k, v in parse_values_toml(target_root / "serverProtSizes.toml").items()
    }

    server_candidates = named_packets(
        source_server_sizes,
        source_server_names,
        target_server_sizes,
        source_root / "serverProt",
    )
    client_candidates = named_packets(
        source_client_sizes,
        source_client_names,
        target_client_sizes,
        source_root / "clientProt",
    )

    server_high = [c for c in server_candidates if c.confidence == "high"]
    server_medium = [c for c in server_candidates if c.confidence == "medium"]
    server_shape_shortlist = [
        c for c in server_candidates if c.has_shape_file and c.target_count <= 4
    ]
    server_small_buckets = [
        c
        for c in server_candidates
        if c.target_count <= 4 and c.source_named_count <= 4 and c.confidence != "high"
    ]
    client_named = sorted(
        client_candidates,
        key=lambda c: ({"high": 0, "medium": 1, "low": 2, "weak": 3}[c.confidence], c.name),
    )

    lines = [
        f"# Protocol Size Diff Report: {source_build} -> {target_build}",
        "",
        "Generated from packet size tables and existing named packet maps.",
        "This is a shortlist generator, not a final authority. All names still need behavioral validation.",
        "",
        "## Summary",
        "",
        f"- Source named server packets: `{len(server_candidates)}`",
        f"- Source named client packets: `{len(client_candidates)}`",
        f"- Target server packet sizes: `{len(target_server_sizes)}`",
        f"- Target client packet sizes: `{len(target_client_sizes)}`",
        f"- High-confidence server size-only transfers: `{len(server_high)}`",
        "",
    ]

    lines.extend(render_candidates("High-Confidence Server Candidates", server_high))
    lines.extend(render_candidates("Medium-Confidence Server Candidates", server_medium[:20]))
    lines.extend(render_candidates("Field-Backed Server Shortlist", server_shape_shortlist))
    lines.extend(render_size_bucket_summary("Small Server Size Buckets", server_small_buckets[:40]))
    lines.extend(render_candidates("Known Client Packet Candidates", client_named))
    lines.extend(render_client_zero_size(target_client_sizes))

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff named protocol sizes between builds.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root containing data/prot/",
    )
    parser.add_argument("--source-build", default="919")
    parser.add_argument("--target-build", default="946")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output path for the markdown report.",
    )
    args = parser.parse_args()

    report = build_report(args.repo_root, args.source_build, args.target_build)
    if args.out is None:
        print(report)
    else:
        args.out.write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
