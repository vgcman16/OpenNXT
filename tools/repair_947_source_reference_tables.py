from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

try:
    from tools.run_947_reference_table_doctor import (
        decode_checksum_table_payload,
        decode_container,
        load_local_reference_table_info,
        parse_jav_config_token,
        parse_js5_reply,
        replay_reference_request,
    )
except ImportError:
    from run_947_reference_table_doctor import (
        decode_checksum_table_payload,
        decode_container,
        load_local_reference_table_info,
        parse_jav_config_token,
        parse_js5_reply,
        replay_reference_request,
    )


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_DOCTOR_JSON = WORKSPACE / "data" / "debug" / "reference-table-doctor-947" / "reference-table-doctor.json"
DEFAULT_CACHE_DIR = WORKSPACE / "data" / "cache"
DEFAULT_TOKEN_URL = "http://127.0.0.1:8080/jav_config.ws"
DEFAULT_FALLBACK_JAV_CONFIG = WORKSPACE / "data" / "clients" / "947" / "win64c" / "original" / "jav_config.ws"
DEFAULT_OUTPUT_ROOT = WORKSPACE / "data" / "debug" / "source-reference-table-repair-947"


@dataclass(frozen=True)
class RepairPlanEntry:
    archive: int
    flags: list[str]


@dataclass(frozen=True)
class RepairResult:
    archive: int
    cache_path: str
    backup_path: str | None
    fetched_crc32: int
    fetched_crc32_hex: str
    fetched_bytes: int
    stored_version: int
    master_crc32: int
    master_crc32_hex: str
    applied: bool


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Repair the mismatched 947 source reference tables in data/cache by fetching live retail "
            "255/x reference-table bodies and updating only the cache_index rows flagged by the latest doctor run."
        )
    )
    parser.add_argument("--doctor-json", type=Path, default=DEFAULT_DOCTOR_JSON)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--token-url", default=DEFAULT_TOKEN_URL)
    parser.add_argument("--fallback-jav-config", type=Path, default=DEFAULT_FALLBACK_JAV_CONFIG)
    parser.add_argument("--live-host", default="content.runescape.com")
    parser.add_argument("--live-port", type=int, default=43594)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--archives")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def parse_archive_csv(value: str | None) -> list[int] | None:
    if value is None:
        return None
    archives = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        archives.append(int(token, 10))
    return archives or None


def load_repair_plan(doctor_json: Path, override_archives: list[int] | None = None) -> list[RepairPlanEntry]:
    if override_archives:
        return [RepairPlanEntry(archive=archive, flags=["manual-override"]) for archive in override_archives]

    artifact = json.loads(doctor_json.read_text(encoding="utf-8"))
    results = artifact.get("results") or artifact.get("archiveResults") or []
    plan: list[RepairPlanEntry] = []
    for result in results:
        archive = int(result["archive"])
        if archive == 255:
            continue
        flags = list(result.get("mismatch_flags") or result.get("mismatchFlags") or [])
        if not flags:
            continue
        if (
            "local-reference-table-body-disagrees-with-retail" in flags
            or "local-master-entry-disagrees-with-local-table" in flags
            or "response-header-mismatch" in flags
        ):
            plan.append(RepairPlanEntry(archive=archive, flags=flags))
    if not plan:
        raise ValueError(f"No mismatched 947 reference tables were found in {doctor_json}")
    return sorted(plan, key=lambda item: item.archive)


def resolve_build_and_token(token_url: str, fallback_jav_config: Path) -> tuple[int, str, str]:
    try:
        from urllib.request import urlopen

        with urlopen(token_url, timeout=10) as response:
            text = response.read().decode("iso-8859-1", "replace")
        build, token = parse_jav_config_token(text)
        return build, token, f"url:{token_url}"
    except Exception:
        if not fallback_jav_config.is_file():
            raise
        text = fallback_jav_config.read_text(encoding="iso-8859-1", errors="replace")
        build = None
        static_token = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("server_version="):
                build = int(line.split("=", 1)[1])
            elif line.startswith("param=10="):
                static_token = line.split("=", 2)[2]
        if build is None or static_token is None:
            raise ValueError(f"Fallback jav_config is missing server_version or param=10: {fallback_jav_config}")
        return build, static_token, f"file:{fallback_jav_config}"


def fetch_master_entries(host: str, port: int, build: int, token: str, timeout_seconds: float) -> dict[int, object]:
    reply = replay_reference_request(host, port, build, token, 255, timeout_seconds)
    parsed = parse_js5_reply(reply)
    dump = decode_checksum_table_payload(decode_container(parsed.payload_bytes).payload_bytes)
    return dump.entries


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def backup_existing_reference_table(cache_path: Path, backup_dir: Path, archive: int) -> tuple[Path | None, int | None]:
    if not cache_path.is_file():
        return None, None

    connection = sqlite3.connect(cache_path)
    try:
        row = connection.execute(
            "SELECT DATA, VERSION, CRC FROM cache_index WHERE KEY = 1"
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None, None

    backup_path = backup_dir / f"js5-{archive}.cache_index.bin"
    ensure_parent(backup_path)
    backup_path.write_bytes(bytes(row[0]))

    metadata_path = backup_dir / f"js5-{archive}.cache_index.json"
    metadata_path.write_text(
        json.dumps(
            {
                "archive": archive,
                "cachePath": str(cache_path),
                "storedVersion": int(row[1]) if row[1] is not None else None,
                "storedCrc32": int(row[2]) if row[2] is not None else None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return backup_path, (int(row[1]) if row[1] is not None else None)


def write_reference_table(cache_path: Path, payload_bytes: bytes, stored_version: int, crc32_value: int) -> None:
    ensure_parent(cache_path)
    connection = sqlite3.connect(cache_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_index(
              KEY INTEGER PRIMARY KEY,
              DATA BLOB,
              VERSION INTEGER,
              CRC INTEGER
            )
            """
        )
        connection.execute(
            """
            INSERT INTO cache_index(KEY, DATA, VERSION, CRC)
            VALUES(1, ?, ?, ?)
            ON CONFLICT(KEY) DO UPDATE SET
              DATA = excluded.DATA,
              VERSION = excluded.VERSION,
              CRC = excluded.CRC
            """,
            (sqlite3.Binary(payload_bytes), stored_version, crc32_value),
        )
        connection.commit()
    finally:
        connection.close()


def repair_archive(
    archive: int,
    *,
    cache_dir: Path,
    backup_dir: Path,
    host: str,
    port: int,
    build: int,
    token: str,
    timeout_seconds: float,
    master_entries: dict[int, object],
    dry_run: bool,
) -> RepairResult:
    cache_path = cache_dir / f"js5-{archive}.jcache"
    retail_reply = replay_reference_request(host, port, build, token, archive, timeout_seconds)
    parsed = parse_js5_reply(retail_reply)
    if parsed.handshake_response != 0:
        raise ValueError(f"Retail handshake for archive {archive} returned {parsed.handshake_response}")
    if parsed.header.index != 255 or parsed.header.archive != archive:
        raise ValueError(
            f"Retail archive {archive} returned unexpected header index={parsed.header.index} archive={parsed.header.archive}"
        )

    payload_bytes = parsed.payload_bytes
    fetched_crc32 = zlib.crc32(payload_bytes) & 0xFFFFFFFF
    container = decode_container(payload_bytes)
    stored_version = container.version if container.version is not None else -1

    master_entry = master_entries.get(archive)
    if master_entry is None:
        raise ValueError(f"Retail master table did not contain archive {archive}")
    master_crc32 = int(master_entry.crc)
    if fetched_crc32 != master_crc32:
        raise ValueError(
            f"Retail payload crc mismatch for archive {archive}: fetched={fetched_crc32:08x} master={master_crc32:08x}"
        )

    backup_path, _ = backup_existing_reference_table(cache_path, backup_dir, archive)
    if not dry_run:
        write_reference_table(cache_path, payload_bytes, stored_version, fetched_crc32)

    verified = load_local_reference_table_info(cache_dir, archive) if not dry_run else None
    applied = True
    if not dry_run and verified is not None:
        applied = verified.raw_crc32 == fetched_crc32 and verified.raw_bytes == len(payload_bytes)

    return RepairResult(
        archive=archive,
        cache_path=str(cache_path),
        backup_path=str(backup_path) if backup_path is not None else None,
        fetched_crc32=fetched_crc32,
        fetched_crc32_hex=f"{fetched_crc32:08x}",
        fetched_bytes=len(payload_bytes),
        stored_version=stored_version,
        master_crc32=master_crc32,
        master_crc32_hex=f"{master_crc32:08x}",
        applied=applied,
    )


def render_markdown(
    *,
    plan: list[RepairPlanEntry],
    results: list[RepairResult],
    token_source: str,
    backup_dir: Path,
    dry_run: bool,
) -> str:
    lines = [
        "# 947 Source Reference Table Repair",
        "",
        f"- Dry run: `{dry_run}`",
        f"- Token source: `{token_source}`",
        f"- Planned archives: `{','.join(str(item.archive) for item in plan)}`",
        f"- Backup dir: `{backup_dir}`",
        "",
        "## Results",
        "",
    ]
    for result in results:
        lines.append(
            "- archive `{archive}` bytes=`{bytes}` crc=`{crc}` storedVersion=`{version}` applied=`{applied}` backup=`{backup}`".format(
                archive=result.archive,
                bytes=result.fetched_bytes,
                crc=result.fetched_crc32_hex,
                version=result.stored_version,
                applied=result.applied,
                backup=result.backup_path or "none",
            )
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = load_repair_plan(args.doctor_json, override_archives=parse_archive_csv(args.archives))
    build, token, token_source = resolve_build_and_token(args.token_url, args.fallback_jav_config)
    master_entries = fetch_master_entries(args.live_host, args.live_port, build, token, args.timeout_seconds)

    run_id = time.strftime("%Y%m%d-%H%M%S")
    output_dir = args.output_root / run_id
    backup_dir = output_dir / "backups"
    output_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    results = [
        repair_archive(
            entry.archive,
            cache_dir=args.cache_dir,
            backup_dir=backup_dir,
            host=args.live_host,
            port=args.live_port,
            build=build,
            token=token,
            timeout_seconds=args.timeout_seconds,
            master_entries=master_entries,
            dry_run=args.dry_run,
        )
        for entry in plan
    ]

    payload = {
        "tool": "repair_947_source_reference_tables",
        "schemaVersion": 1,
        "build": build,
        "tokenSource": token_source,
        "dryRun": bool(args.dry_run),
        "doctorJson": str(args.doctor_json),
        "cacheDir": str(args.cache_dir),
        "backupDir": str(backup_dir),
        "plannedArchives": [asdict(entry) for entry in plan],
        "results": [asdict(result) for result in results],
    }
    json_path = output_dir / "repair-947-source-reference-tables.json"
    md_path = output_dir / "repair-947-source-reference-tables.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(
        render_markdown(
            plan=plan,
            results=results,
            token_source=token_source,
            backup_dir=backup_dir,
            dry_run=bool(args.dry_run),
        ),
        encoding="utf-8",
    )

    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
