from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import urllib.request
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_URL = (
    "http://127.0.0.1:8080/jav_config.ws?"
    "binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=1&"
    "gameHostRewrite=0&gamePortOverride=43594&downloadMetadataSource=patched&"
    "worldUrlRewrite=1&codebaseRewrite=1&baseConfigSource=live&liveCache=1"
)
DEFAULT_LOCAL_DIR = WORKSPACE / "data" / "clients" / "947" / "win64c" / "patched"
DEFAULT_INSTALLED_DIR = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Jagex" / "launcher"
DEFAULT_OUTPUT_DIR = WORKSPACE / "data" / "debug" / "installed-runtime-sync-947"


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


def resolve_config_url_for_fetch(config_url: str) -> str:
    parts = urlsplit(config_url)
    if parts.hostname and parts.hostname.lower() == "rs.config.runescape.com":
        return urlunsplit(("http", "127.0.0.1:8080", "/jav_config.ws", parts.query, ""))
    return config_url


def load_config_text(config_url: str, config_file: Path | None, timeout_seconds: float) -> str:
    if config_file is not None:
        return config_file.read_text(encoding="iso-8859-1")
    return fetch_text(resolve_config_url_for_fetch(config_url), timeout_seconds)


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


def build_wrapper_launch_readiness(
    *,
    local_results: list[FileInspection],
    local_ready: bool,
    installed_ready_after: bool,
) -> dict[str, object]:
    local_mismatches = [result for result in local_results if result.status != "match"]
    local_mismatch_names = [result.name for result in local_mismatches]
    local_child_result = next(
        (
            result
            for result in local_results
            if result.name.lower() == "rs2client.exe"
        ),
        None,
    )
    local_non_child_ready = all(
        result.status == "match" or result is local_child_result for result in local_results
    )
    local_only_child_crc_mismatch = (
        local_child_result is not None
        and local_child_result.status == "crc-mismatch"
        and len(local_mismatches) == 1
        and local_mismatch_names[0].lower() == "rs2client.exe"
    )
    wrapper_local_child_override_ready = local_ready and installed_ready_after
    wrapper_installed_child_ready = (
        installed_ready_after and local_non_child_ready and local_only_child_crc_mismatch
    )
    wrapper_launch_ready = (
        wrapper_local_child_override_ready or wrapper_installed_child_ready
    )
    if wrapper_local_child_override_ready:
        wrapper_launch_reason = "local-family-ready"
    elif wrapper_installed_child_ready:
        wrapper_launch_reason = "installed-runtime-ready-local-rs2client-crc-mismatch"
    else:
        wrapper_launch_reason = "wrapper-launch-not-ready"
    return {
        "localMismatchNames": local_mismatch_names,
        "localNonChildReady": local_non_child_ready,
        "localRs2ClientStatus": None if local_child_result is None else local_child_result.status,
        "wrapperLocalChildOverrideReady": wrapper_local_child_override_ready,
        "wrapperInstalledChildReady": wrapper_installed_child_ready,
        "wrapperLaunchReady": wrapper_launch_ready,
        "wrapperLaunchReason": wrapper_launch_reason,
    }


def replace_file_verified(source: Path, destination: Path, expected_crc: int) -> tuple[int, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f"{destination.name}.opennxt-stage-",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    os.close(temp_fd)
    staged = Path(temp_name)
    try:
        shutil.copy2(source, staged)
        staged_crc = compute_crc32(staged)
        if staged_crc != expected_crc:
            raise RuntimeError(
                f"staged-copy-crc-mismatch expected-crc={expected_crc} actual-crc={staged_crc}"
            )
        os.replace(staged, destination)
        actual_crc = compute_crc32(destination)
        if actual_crc != expected_crc:
            raise RuntimeError(
                f"post-replace-crc-mismatch expected-crc={expected_crc} actual-crc={actual_crc}"
            )
        return actual_crc, destination.stat().st_size
    finally:
        try:
            if staged.exists():
                staged.unlink()
        except OSError:
            pass


def render_markdown(artifact: dict) -> str:
    def render_scope(title: str, results: list[dict]) -> list[str]:
        mismatches = sum(result["status"] != "match" for result in results)
        lines = [
            f"## {title}",
            "",
            f"- Checked files: `{len(results)}`",
            f"- Mismatches: `{mismatches}`",
            "",
        ]
        for result in results:
            line = f"- `{result['status']}` `{result['name']}` expected=`{result['expected_crc']}`"
            if result["actual_crc"] is not None:
                line += f" actual=`{result['actual_crc']}`"
            if result["size"] is not None:
                line += f" size=`{result['size']}`"
            lines.append(line)
            if result["reason"]:
                lines.append(f"  reason: `{result['reason']}`")
            if result["needs"]:
                lines.append(f"  needs: `{result['needs']}`")
        lines.append("")
        return lines

    lines = [
        "# Installed Runtime Sync",
        "",
        f"- Config URL: `{artifact['configUrl']}`" if artifact["configUrl"] else "- Config URL: `none`",
        f"- Config file: `{artifact['configFile']}`" if artifact["configFile"] else "- Config file: `none`",
        f"- Check only: `{artifact['checkOnly']}`",
        f"- Local ready: `{artifact['localReady']}`",
        f"- Installed ready before sync: `{artifact['installedReadyBefore']}`",
        f"- Installed ready after sync: `{artifact['installedReadyAfter']}`",
        f"- Planned copies: `{artifact['plannedCopyCount']}`",
        f"- Copied: `{artifact['copiedCount']}`",
        f"- Failed copies: `{artifact['failedCount']}`",
        "",
        *render_scope("Local Client Family", artifact["localResults"]),
        *render_scope("Installed Runtime Before Sync", artifact["installedResultsBefore"]),
        *render_scope("Installed Runtime After Sync", artifact["installedResultsAfter"]),
        "## Sync Actions",
        "",
    ]
    for action in artifact["entries"]:
        lines.append(
            f"- `{action['action']}` `{action['name']}` local=`{action['localStatus']}` installed=`{action['installedStatusBefore']}`"
        )
        if action["reason"]:
            lines.append(f"  reason: `{action['reason']}`")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the live 947 wrapper manifest against the staged local client family and "
            "refresh the installed ProgramData runtime files that the wrapper-spawned rs2client.exe uses."
        )
    )
    parser.add_argument("--config-url", default=DEFAULT_CONFIG_URL)
    parser.add_argument("--config-file", type=Path, default=None)
    parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL_DIR)
    parser.add_argument("--installed-dir", type=Path, default=DEFAULT_INSTALLED_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--check-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_text = load_config_text(args.config_url, args.config_file, args.timeout_seconds)
    entries = parse_download_entries(config_text)
    local_results = inspect_directory("local", args.local_dir, entries)
    installed_results_before = inspect_directory("installed", args.installed_dir, entries)

    local_by_name = {result.name: result for result in local_results}
    installed_by_name = {result.name: result for result in installed_results_before}
    local_ready = all(result.status == "match" for result in local_results)
    installed_ready_before = all(result.status == "match" for result in installed_results_before)

    sync_entries: list[dict] = []
    planned_files: list[str] = []
    copied_files: list[str] = []
    failed_files: list[str] = []
    copied_count = 0
    unchanged_count = 0

    args.installed_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        local_result = local_by_name[entry.name]
        installed_result = installed_by_name[entry.name]
        action = "unchanged"
        reason = None

        if local_result.status != "match":
            action = "blocked-local"
            reason = f"local-{local_result.status}"
        elif installed_result.status != "match":
            action = "would-copy" if args.check_only else "copied"
            reason = installed_result.reason
            planned_files.append(entry.name)
            if not args.check_only:
                source = args.local_dir / entry.name
                destination = args.installed_dir / entry.name
                try:
                    replace_file_verified(source, destination, entry.expected_crc)
                    copied_files.append(entry.name)
                    copied_count += 1
                except Exception as exc:
                    action = "copy-failed"
                    reason = str(exc)
                    failed_files.append(entry.name)
        else:
            unchanged_count += 1

        sync_entries.append(
            {
                "slot": entry.slot,
                "name": entry.name,
                "expectedCrc": entry.expected_crc,
                "localStatus": local_result.status,
                "installedStatusBefore": installed_result.status,
                "action": action,
                "reason": reason,
                "localPath": local_result.path,
                "installedPath": str(args.installed_dir / entry.name),
            }
        )

    installed_results_after = inspect_directory("installed", args.installed_dir, entries)
    installed_ready_after = all(result.status == "match" for result in installed_results_after)
    wrapper_launch_readiness = build_wrapper_launch_readiness(
        local_results=local_results,
        local_ready=local_ready,
        installed_ready_after=installed_ready_after,
    )

    artifact = {
        "tool": "sync_runescape_installed_runtime",
        "schemaVersion": 1,
        "configUrl": None if args.config_file is not None else args.config_url,
        "configFile": str(args.config_file) if args.config_file is not None else None,
        "localDir": str(args.local_dir),
        "installedDir": str(args.installed_dir),
        "checkOnly": args.check_only,
        "localReady": local_ready,
        "installedReadyBefore": installed_ready_before,
        "installedReadyAfter": installed_ready_after,
        **wrapper_launch_readiness,
        "plannedCopyCount": len(planned_files),
        "copiedCount": copied_count,
        "failedCount": len(failed_files),
        "unchangedCount": unchanged_count,
        "plannedFiles": planned_files,
        "copiedFiles": copied_files,
        "failedFiles": failed_files,
        "manifest": [asdict(entry) for entry in entries],
        "localResults": [asdict(result) for result in local_results],
        "installedResultsBefore": [asdict(result) for result in installed_results_before],
        "installedResultsAfter": [asdict(result) for result in installed_results_after],
        "entries": sync_entries,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "installed-runtime-sync.json"
    md_path = args.output_dir / "installed-runtime-sync.md"
    json_text = json.dumps(artifact, indent=2)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(render_markdown(artifact), encoding="utf-8")
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json_text, encoding="utf-8")
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
