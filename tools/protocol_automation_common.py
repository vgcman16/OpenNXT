from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


WORKSPACE = Path(r"C:\Users\Demon\Documents\New project\OpenNXT")
REPO_ROOT = WORKSPACE.parent
PROT_DIR = WORKSPACE / "data" / "prot" / "946"
GENERATED_DIR = PROT_DIR / "generated"
SHARED_DIR = GENERATED_DIR / "shared"
PHASE_DIRS = {
    1: GENERATED_DIR / "phase1",
    2: GENERATED_DIR / "phase2",
    3: GENERATED_DIR / "phase3",
    4: GENERATED_DIR / "phase4",
    5: GENERATED_DIR / "phase5",
}

DEFAULT_RUNTIME_PRIORITY_PACKETS = [
    "IF_SETEVENTS",
    "IF_SETTEXT",
    "IF_SETCOLOUR",
    "IF_SETSCROLLPOS",
    "IF_SETRETEX",
    "OBJ_REVEAL",
    "OBJ_ADD",
    "OBJ_DEL",
    "OBJ_COUNT",
    "RESUME_P_COUNTDIALOG",
]

DEFAULT_UNRESOLVED_PROXY_PACKET = {
    "side": "server",
    "opcode": 211,
    "packetName": "UNRESOLVED_SAMPLE",
    "payloadHex": "01020304a0",
}

DO_NOT_TOUCH_PACKET_NAMES = {
    "PLAYER_INFO": "bit-packed sync packet; keep hand-crafted parser and field handling",
    "NPC_INFO": "bit-packed sync packet; keep hand-crafted parser and field handling",
    "REBUILD_NORMAL": "region rebuild packet; keep hand-crafted field handling",
    "MAP_PROJANIM": "projectile map update packet; keep hand-crafted field handling",
    "MAP_PROJANIM_HALFSQ": "projectile map update packet; keep hand-crafted field handling",
}

FIELD_WIDTHS: dict[str, int | None] = {
    "string": None,
    "ubyte": 1,
    "ubyte128": 1,
    "u128byte": 1,
    "ubytec": 1,
    "sbyte": 1,
    "sbyte128": 1,
    "s128byte": 1,
    "sbytec": 1,
    "ushort": 2,
    "ushort128": 2,
    "ushortle": 2,
    "ushortle128": 2,
    "umedium": 3,
    "umediumle": 3,
    "int": 4,
    "intle": 4,
    "intv1": 4,
    "intv2": 4,
    "long": 8,
}

KOTLIN_TYPE_MAP = {
    "string": "String",
    "long": "Long",
}

IDENTIFIER_RE = re.compile(r"^[A-Za-z_]\w*$")
TOML_NAME_RE = re.compile(r"^(\d+)\s*=\s*\"([^\"]+)\"", re.M)
TOML_SIZE_RE = re.compile(r"^(\d+)\s*=\s*(-?\d+)", re.M)
REGISTER_RE = re.compile(r'register\(\s*Side\.(SERVER|CLIENT),\s*"([^"]+)"', re.S)
VOLATILE_KEYS = {
    "generatedAt",
    "generated_at",
    "timestamp",
    "createdAt",
    "updatedAt",
    "runStartedAt",
    "runFinishedAt",
    "durationMs",
    "durationSeconds",
    "stdoutLog",
    "stderrLog",
    "command",
    "commands",
    "meta",
}


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def stable_json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def write_json(path: Path, payload: Any) -> None:
    ensure_directory(path.parent)
    path.write_text(stable_json_text(payload), encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def parse_names_toml(path: Path) -> dict[int, str]:
    text = path.read_text(encoding="utf-8")
    return {int(opcode): name for opcode, name in TOML_NAME_RE.findall(text)}


def parse_sizes_toml(path: Path) -> dict[int, int]:
    text = path.read_text(encoding="utf-8")
    return {int(opcode): int(size) for opcode, size in TOML_SIZE_RE.findall(text)}


def parse_field_file(path: Path) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    if not path.exists():
        return fields
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        fields.append({"name": parts[0], "type": parts[1], "raw": line})
    return fields


def field_width(field_type: str) -> int | None:
    return FIELD_WIDTHS.get(field_type)


def total_field_width(fields: Iterable[dict[str, str]] | Iterable[str]) -> int | None:
    total = 0
    for field in fields:
        field_type = field["type"] if isinstance(field, dict) else field
        width = field_width(field_type)
        if width is None:
            return None
        total += width
    return total


def sanitize_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not cleaned:
        cleaned = "field"
    if cleaned[0].isdigit():
        cleaned = f"field_{cleaned}"
    return cleaned


def kotlin_property_name(value: str) -> str:
    name = sanitize_identifier(value)
    if IDENTIFIER_RE.match(name):
        return name
    return f"`{name}`"


def camel_case_packet_name(packet_name: str) -> str:
    parts = [part for part in packet_name.lower().split("_") if part]
    return "".join(part[:1].upper() + part[1:] for part in parts)


def packet_class_name(packet_name: str) -> str:
    return f"{camel_case_packet_name(packet_name)}GeneratedPacket"


def kotlin_type_for_field(field_type: str) -> str:
    return KOTLIN_TYPE_MAP.get(field_type, "Int")


def normalize_for_regression(payload: Any) -> Any:
    if isinstance(payload, dict):
        normalized = {}
        for key, value in payload.items():
            if key in VOLATILE_KEYS:
                continue
            normalized[key] = normalize_for_regression(value)
        return normalized
    if isinstance(payload, list):
        return [normalize_for_regression(item) for item in payload]
    return payload


def collect_artifact_hashes(paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    hashes: dict[str, dict[str, Any]] = {}
    for path in paths:
        if not path.exists():
            continue
        hashes[str(path)] = {
            "sha256": sha256_text(stable_json_text(normalize_for_regression(load_json(path))))
            if path.suffix == ".json"
            else sha256_text(path.read_text(encoding="utf-8")),
            "size": path.stat().st_size,
        }
    return hashes


def diff_hash_manifests(current: dict[str, dict[str, Any]], baseline: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    all_keys = sorted(set(current) | set(baseline))
    for key in all_keys:
        current_value = current.get(key)
        baseline_value = baseline.get(key)
        if current_value == baseline_value:
            continue
        changed.append(
            {
                "path": key,
                "current": current_value,
                "baseline": baseline_value,
            }
        )
    return changed


def manual_registered_packets(packet_registry_path: Path) -> set[tuple[str, str]]:
    text = packet_registry_path.read_text(encoding="utf-8")
    return {(side.lower(), name) for side, name in REGISTER_RE.findall(text)}


def build_fingerprint(parts: dict[str, str]) -> str:
    payload = stable_json_text(parts)
    return sha256_text(payload)


def file_fingerprint(paths: Iterable[Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in paths:
        if path.exists():
            result[str(path)] = sha256_file(path)
    return result


def helper_signature_hash(payload: dict[str, Any]) -> str:
    return build_fingerprint({"helperSignature": stable_json_text(normalize_for_regression(payload))})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def output_artifact_map(output_dir: Path, *names: str) -> dict[str, str]:
    return {Path(name).stem.replace("-", "_"): str(output_dir / name) for name in names}


def standard_tool_artifact(
    *,
    tool_name: str,
    status: str,
    inputs: dict[str, Any],
    artifacts: dict[str, str],
    summary: dict[str, Any] | None = None,
    build: int | str = 946,
    schema_version: int = 1,
    advisory: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tool": tool_name,
        "schemaVersion": schema_version,
        "generatedAt": utc_now_iso(),
        "build": build,
        "status": status,
        "advisoryOnly": advisory,
        "inputs": inputs,
        "artifacts": artifacts,
    }
    if summary:
        payload["summary"] = summary
    if extra:
        payload.update(extra)
    return payload


def artifact_input_fingerprint(tool_name: str, paths: Iterable[Path], **extras: Any) -> str:
    normalized_extras = {key: stable_json_text(normalize_for_regression(value)) if isinstance(value, (dict, list)) else str(value) for key, value in extras.items()}
    return build_fingerprint(
        {
            "tool": tool_name,
            "paths": stable_json_text(file_fingerprint(paths)),
            **normalized_extras,
        }
    )


def cache_hit(cache_manifest: dict[str, Any], key: str, input_fingerprint: str, outputs: Iterable[Path], *, force: bool = False) -> bool:
    cache_entry = cache_manifest.get(key, {}) if isinstance(cache_manifest, dict) else {}
    return (
        not force
        and cache_entry.get("inputFingerprint") == input_fingerprint
        and all(path.exists() for path in outputs)
    )


def record_cache_entry(cache_manifest: dict[str, Any], key: str, input_fingerprint: str, outputs: Iterable[Path]) -> None:
    cache_manifest[key] = {
        "inputFingerprint": input_fingerprint,
        "outputs": [str(path) for path in outputs],
    }
