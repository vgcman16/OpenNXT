from __future__ import annotations

import argparse
import json
import os
import urllib.request
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_URL = (
    "http://127.0.0.1:8080/jav_config.ws?"
    "binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=0&"
    "gameHostRewrite=0&gamePortOverride=43594&downloadMetadataSource=patched&"
    "worldUrlRewrite=0&codebaseRewrite=0&baseConfigSource=live&liveCache=0"
)
DEFAULT_LOCAL_DIR = WORKSPACE / "data" / "clients" / "947" / "win64c" / "patched"
DEFAULT_INSTALLED_DIR = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Jagex" / "launcher"
DEFAULT_OUTPUT_DIR = WORKSPACE / "data" / "debug" / "client-resource-doctor-947"


@dataclass(frozen=True)
class DownloadEntry:
    slot: int
    name: str
    expected_crc: int
    expected_hash: str | None


@dataclass(frozen=True)
class FileInspection:
    scope: str
    name: str
    expected_crc: int
    path: str | None
    status: str
    actual_crc: int | None
    size: int | None
    reason: str | None
    needs: str | None


def fetch_text(url: str, timeout_seconds: float) -> str:
    with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
        payload = response.read()
    return payload.decode("iso-8859-1", errors="replace")


def parse_download_entries(config_text: str) -> list[DownloadEntry]:
    names: dict[int, str] = {}
    crcs: dict[int, int] = {}
    hashes: dict[int, str] = {}
    for raw_line in config_text.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.startswith("download_name_"):
            names[int(key.rsplit("_", 1)[1])] = value
        elif key.startswith("download_crc_"):
            crcs[int(key.rsplit("_", 1)[1])] = int(value)
        elif key.startswith("download_hash_"):
            hashes[int(key.rsplit("_", 1)[1])] = value
    slots = sorted(set(names) | set(crcs))
    entries: list[DownloadEntry] = []
    for slot in slots:
        name = names.get(slot)
        expected_crc = crcs.get(slot)
        if not name or expected_crc is None:
            continue
        entries.append(
            DownloadEntry(
                slot=slot,
                name=name,
                expected_crc=expected_crc,
                expected_hash=hashes.get(slot),
            )
        )
    return entries


def compute_crc32(path: Path) -> int:
    crc = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            crc = zlib.crc32(chunk, crc)
    return crc & 0xFFFFFFFF


def inspect_directory(scope: str, root: Path, entries: list[DownloadEntry]) -> list[FileInspection]:
    inspections: list[FileInspection] = []
    for entry in entries:
        candidate = root / entry.name
        if not candidate.exists():
            inspections.append(
                FileInspection(
                    scope=scope,
                    name=entry.name,
                    expected_crc=entry.expected_crc,
                    path=None,
                    status="missing",
                    actual_crc=None,
                    size=None,
                    reason="missing-file",
                    needs=f"{entry.name} in {root}",
                )
            )
            continue
        actual_crc = compute_crc32(candidate)
        size = candidate.stat().st_size
        if actual_crc != entry.expected_crc:
            inspections.append(
                FileInspection(
                    scope=scope,
                    name=entry.name,
                    expected_crc=entry.expected_crc,
                    path=str(candidate),
                    status="crc-mismatch",
                    actual_crc=actual_crc,
                    size=size,
                    reason=f"expected-crc={entry.expected_crc} actual-crc={actual_crc}",
                    needs=f"refresh {entry.name} in {root}",
                )
            )
            continue
        inspections.append(
            FileInspection(
                scope=scope,
                name=entry.name,
                expected_crc=entry.expected_crc,
                path=str(candidate),
                status="match",
                actual_crc=actual_crc,
                size=size,
                reason=None,
                needs=None,
            )
        )
    return inspections


def render_markdown(
    config_url: str,
    entries: list[DownloadEntry],
    local_results: list[FileInspection],
    installed_results: list[FileInspection],
) -> str:
    def format_scope(title: str, results: list[FileInspection]) -> list[str]:
        mismatch_count = sum(result.status != "match" for result in results)
        lines = [
            f"## {title}",
            "",
            f"- Checked files: `{len(results)}`",
            f"- Mismatches: `{mismatch_count}`",
            "",
        ]
        for result in results:
            detail = f"`{result.status}` `{result.name}` expected=`{result.expected_crc}`"
            if result.actual_crc is not None:
                detail += f" actual=`{result.actual_crc}`"
            if result.size is not None:
                detail += f" size=`{result.size}`"
            lines.append(f"- {detail}")
            if result.reason:
                lines.append(f"  reason: `{result.reason}`")
            if result.needs:
                lines.append(f"  needs: `{result.needs}`")
        lines.append("")
        return lines

    return "\n".join(
        [
            "# 947 Client Resource Doctor",
            "",
            f"- Config URL: `{config_url}`",
            f"- Manifest files: `{len(entries)}`",
            f"- Manifest names: `{', '.join(entry.name for entry in entries)}`",
            "",
            *format_scope("Local Client Family", local_results),
            *format_scope("Installed Runtime", installed_results),
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch the current 947 wrapper manifest, verify the staged local client family and "
            "the installed launcher runtime files against the advertised CRCs, and report exactly "
            "which application-resource binaries still need refresh."
        )
    )
    parser.add_argument("--config-url", default=DEFAULT_CONFIG_URL)
    parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL_DIR)
    parser.add_argument("--installed-dir", type=Path, default=DEFAULT_INSTALLED_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_text = fetch_text(args.config_url, args.timeout_seconds)
    entries = parse_download_entries(config_text)
    local_results = inspect_directory("local", args.local_dir, entries)
    installed_results = inspect_directory("installed", args.installed_dir, entries)

    artifact = {
        "tool": "run_947_client_resource_doctor",
        "schemaVersion": 1,
        "configUrl": args.config_url,
        "localDir": str(args.local_dir),
        "installedDir": str(args.installed_dir),
        "manifest": [asdict(entry) for entry in entries],
        "localResults": [asdict(result) for result in local_results],
        "installedResults": [asdict(result) for result in installed_results],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "client-resource-doctor.json"
    md_path = args.output_dir / "client-resource-doctor.md"
    json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(args.config_url, entries, local_results, installed_results), encoding="utf-8")
    print(str(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
