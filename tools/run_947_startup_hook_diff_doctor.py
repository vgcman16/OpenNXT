from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_OFFICIAL_HOOK = WORKSPACE / "data" / "debug" / "direct-rs2client-patch" / "official-live-startup-hook-20260324.jsonl"
DEFAULT_LOCAL_HOOK = WORKSPACE / "data" / "debug" / "direct-rs2client-patch" / "latest-live-hook.jsonl"
DEFAULT_OUTPUT_DIR = WORKSPACE / "data" / "debug" / "startup-hook-diff-doctor-947-current"
HOT_SPLASH_JS5_SLOTS = {2, 3, 12, 16, 17, 18, 19, 21, 22, 24, 26, 28, 29, 49, 57, 58, 60, 61, 62, 65, 66}
JS5_CACHE_PATH = re.compile(r"js5-(\d+)\.jcache$", re.IGNORECASE)


@dataclass(frozen=True)
class StartupMarker:
    ordinal: int
    action: str
    label: str
    source_line: int


@dataclass(frozen=True)
class HookSummary:
    path: str
    marker_count: int
    markers: list[StartupMarker]
    resolved_hosts: list[str]
    tls_ready_targets: list[str]
    raw_bootstrap_count: int
    http_master_table_fetch_count: int
    http_master_table_success_count: int
    hot_cache_slots_touched: list[int]
    hot_cache_slots_written: list[int]


@dataclass(frozen=True)
class DiffSummary:
    common_prefix_length: int
    first_official_only: str | None
    first_local_only: str | None
    official_terminal_stage: str | None
    local_terminal_stage: str | None
    likely_blocker: str


def append_marker(markers: list[StartupMarker], action: str, label: str, source_line: int) -> None:
    if markers and markers[-1].label == label:
        return
    markers.append(
        StartupMarker(
            ordinal=len(markers) + 1,
            action=action,
            label=label,
            source_line=source_line,
        )
    )


def classify_resolve_label(host: str, service: str | None) -> str | None:
    normalized_host = host.strip().lower()
    normalized_service = (service or "").strip()
    if not normalized_host:
        return None
    if normalized_host == "rs.config.runescape.com":
        return "resolve:config-secure"
    if normalized_host.startswith("world") and normalized_host.endswith(".runescape.com"):
        return "resolve:world-secure"
    if normalized_host.startswith("lobby") and normalized_host.endswith(".runescape.com"):
        return "resolve:lobby-secure"
    if normalized_host == "content.runescape.com":
        return "resolve:content-secure"
    if normalized_host == "localhost" and normalized_service == "443":
        return "resolve:local-secure-bootstrap"
    if normalized_host == "localhost" and normalized_service == "80":
        return "resolve:local-http-content"
    return f"resolve:{normalized_host}:{normalized_service or '?'}"


def classify_tls_ready_label(target_name: str) -> str | None:
    normalized_target = target_name.strip().lower()
    if not normalized_target:
        return None
    if normalized_target == "rs.config.runescape.com":
        return "tls-ready:config-secure"
    if normalized_target.startswith("world") and normalized_target.endswith(".runescape.com"):
        return "tls-ready:world-secure"
    if normalized_target.startswith("lobby") and normalized_target.endswith(".runescape.com"):
        return "tls-ready:lobby-secure"
    if normalized_target == "content.runescape.com":
        return "tls-ready:content-secure"
    if normalized_target == "localhost":
        return "tls-ready:local-secure-bootstrap"
    return f"tls-ready:{normalized_target}"


def parse_cache_slot(path: str) -> int | None:
    match = JS5_CACHE_PATH.search(path.strip())
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def coerce_int(value: object, default: int = -1) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def looks_like_tls_client_hello(preview_hex: str) -> bool:
    normalized = preview_hex.strip().lower()
    if len(normalized) < 12:
        return False
    # TLS record header:
    #   16      handshake
    #   03 xx   TLS version
    # followed by a ClientHello handshake type (01)
    if not normalized.startswith("16"):
        return False
    if normalized[2:4] != "03":
        return False
    return normalized[10:12] == "01"


def parse_hook_markers(path: Path) -> HookSummary:
    markers: list[StartupMarker] = []
    resolved_hosts: list[str] = []
    tls_ready_targets: list[str] = []
    hot_cache_slots_touched: list[int] = []
    hot_cache_slots_written: list[int] = []
    touched_seen: set[int] = set()
    written_seen: set[int] = set()
    hot_touch_marker_emitted = False
    hot_write_marker_emitted = False
    raw_bootstrap_count = 0
    http_master_table_fetch_count = 0
    http_master_table_success_count = 0

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for source_line, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            event = json.loads(raw_line)
            action = str(event.get("action", ""))

            if action == "resolve":
                host = str(event.get("host", ""))
                service = event.get("service")
                if host:
                    resolved_hosts.append(host)
                label = classify_resolve_label(host, None if service is None else str(service))
                if label is not None:
                    append_marker(markers, action, label, source_line)
                continue

            if action == "initialize-security-context":
                target = str(event.get("targetName", ""))
                status = int(event.get("status", -1))
                if status == 0 and target:
                    tls_ready_targets.append(target)
                    label = classify_tls_ready_label(target)
                    if label is not None:
                        append_marker(markers, action, label, source_line)
                continue

            if action == "send-first-chunk":
                remote_port = coerce_int(event.get("remotePort", -1))
                looks_http = bool(event.get("looksHttp", False))
                first_line = str(event.get("firstLine", ""))
                preview_hex = str(event.get("previewHex", ""))
                if remote_port == 443 and not looks_http:
                    if looks_like_tls_client_hello(preview_hex):
                        append_marker(markers, action, "send:tls-client-hello", source_line)
                        continue
                    raw_bootstrap_count += 1
                    append_marker(markers, action, "send:raw-bootstrap", source_line)
                    continue
                if looks_http and first_line.startswith("GET /ms?m=0&a=255"):
                    http_master_table_fetch_count += 1
                    append_marker(markers, action, "send:http-master-table", source_line)
                    continue

            if action == "recv-first-chunk":
                remote_port = coerce_int(event.get("remotePort", -1))
                looks_http = bool(event.get("looksHttp", False))
                first_line = str(event.get("firstLine", ""))
                if remote_port in {80, 8080} and looks_http and first_line.startswith("HTTP/1.1 200"):
                    http_master_table_success_count += 1
                    append_marker(markers, action, "recv:http-master-table-200", source_line)
                    continue

            if action in {"open", "write"}:
                file_category = str(event.get("fileCategory", ""))
                if file_category != "cache":
                    continue
                slot = parse_cache_slot(str(event.get("path", "")))
                if slot is None or slot not in HOT_SPLASH_JS5_SLOTS:
                    continue
                if slot not in touched_seen:
                    touched_seen.add(slot)
                    hot_cache_slots_touched.append(slot)
                if not hot_touch_marker_emitted:
                    hot_touch_marker_emitted = True
                    append_marker(markers, action, "cache:hot-js5-touch", source_line)
                if action == "write":
                    if slot not in written_seen:
                        written_seen.add(slot)
                        hot_cache_slots_written.append(slot)
                    if not hot_write_marker_emitted:
                        hot_write_marker_emitted = True
                        append_marker(markers, action, "cache:hot-js5-write", source_line)

    return HookSummary(
        path=str(path),
        marker_count=len(markers),
        markers=markers,
        resolved_hosts=resolved_hosts,
        tls_ready_targets=tls_ready_targets,
        raw_bootstrap_count=raw_bootstrap_count,
        http_master_table_fetch_count=http_master_table_fetch_count,
        http_master_table_success_count=http_master_table_success_count,
        hot_cache_slots_touched=sorted(hot_cache_slots_touched),
        hot_cache_slots_written=sorted(hot_cache_slots_written),
    )


def compare_markers(official: HookSummary, local: HookSummary) -> DiffSummary:
    prefix = 0
    max_prefix = min(len(official.markers), len(local.markers))
    while prefix < max_prefix and official.markers[prefix].label == local.markers[prefix].label:
        prefix += 1

    first_official = official.markers[prefix].label if prefix < len(official.markers) else None
    first_local = local.markers[prefix].label if prefix < len(local.markers) else None
    official_terminal = official.markers[-1].label if official.markers else None
    local_terminal = local.markers[-1].label if local.markers else None

    official_labels = {marker.label for marker in official.markers}
    local_labels = {marker.label for marker in local.markers}

    if "tls-ready:content-secure" in official_labels and "recv:http-master-table-200" in local_labels:
        blocker = "content-bootstrap-transport-diverged"
    elif "recv:http-master-table-200" in local_labels and local.http_master_table_success_count > 0 and local.raw_bootstrap_count > 0:
        blocker = "startup-stalls-after-local-master-table-bridge"
    elif official.hot_cache_slots_touched and local.hot_cache_slots_written:
        blocker = "local-startup-refreshes-hot-cache-while-official-reads-existing-cache"
    elif first_official == first_local:
        blocker = "no-diff-detected"
    elif first_official and first_official.startswith("resolve:") and first_local and first_local.startswith("resolve:"):
        blocker = "startup-host-bootstrap-diverged"
    elif first_official and first_official.startswith("tls-ready:") and first_local and first_local.startswith("tls-ready:"):
        blocker = "startup-tls-bootstrap-diverged"
    elif first_official and not first_local:
        blocker = "local-startup-truncated-early"
    elif first_local and not first_official:
        blocker = "local-startup-extra-stage"
    else:
        blocker = "startup-sequence-diverged"

    return DiffSummary(
        common_prefix_length=prefix,
        first_official_only=first_official,
        first_local_only=first_local,
        official_terminal_stage=official_terminal,
        local_terminal_stage=local_terminal,
        likely_blocker=blocker,
    )


def render_marker_list(markers: list[StartupMarker], limit: int = 24) -> list[str]:
    return [f"- `{marker.ordinal}` `{marker.label}` (line `{marker.source_line}`)" for marker in markers[:limit]]


def render_markdown(official: HookSummary, local: HookSummary, diff: DiffSummary) -> str:
    return "\n".join(
        [
            "# 947 Startup Hook Diff Doctor",
            "",
            f"- Official hook: `{official.path}`",
            f"- Local hook: `{local.path}`",
            f"- Official markers: `{official.marker_count}`",
            f"- Local markers: `{local.marker_count}`",
            f"- Common prefix length: `{diff.common_prefix_length}`",
            f"- First official-only marker: `{diff.first_official_only}`",
            f"- First local-only marker: `{diff.first_local_only}`",
            f"- Official terminal stage: `{diff.official_terminal_stage}`",
            f"- Local terminal stage: `{diff.local_terminal_stage}`",
            f"- Likely blocker: `{diff.likely_blocker}`",
            "",
            "## Official Startup Markers",
            "",
            *render_marker_list(official.markers),
            "",
            "## Local Startup Markers",
            "",
            *render_marker_list(local.markers),
            "",
            "## Official Summary",
            "",
            f"- Resolved hosts: `{', '.join(official.resolved_hosts)}`",
            f"- TLS-ready targets: `{', '.join(official.tls_ready_targets)}`",
            f"- Raw bootstrap sends: `{official.raw_bootstrap_count}`",
            f"- HTTP master-table fetches: `{official.http_master_table_fetch_count}`",
            f"- HTTP master-table 200s: `{official.http_master_table_success_count}`",
            f"- Hot cache slots touched: `{', '.join(str(slot) for slot in official.hot_cache_slots_touched)}`",
            f"- Hot cache slots written: `{', '.join(str(slot) for slot in official.hot_cache_slots_written)}`",
            "",
            "## Local Summary",
            "",
            f"- Resolved hosts: `{', '.join(local.resolved_hosts)}`",
            f"- TLS-ready targets: `{', '.join(local.tls_ready_targets)}`",
            f"- Raw bootstrap sends: `{local.raw_bootstrap_count}`",
            f"- HTTP master-table fetches: `{local.http_master_table_fetch_count}`",
            f"- HTTP master-table 200s: `{local.http_master_table_success_count}`",
            f"- Hot cache slots touched: `{', '.join(str(slot) for slot in local.hot_cache_slots_touched)}`",
            f"- Hot cache slots written: `{', '.join(str(slot) for slot in local.hot_cache_slots_written)}`",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare the meaningful startup stages between an official 947 hook trace and a "
            "localhost-routed local 947 hook trace, including raw bootstrap, HTTP master-table "
            "bridge, and hot splash-cache population."
        )
    )
    parser.add_argument("--official-hook", type=Path, default=DEFAULT_OFFICIAL_HOOK)
    parser.add_argument("--local-hook", type=Path, default=DEFAULT_LOCAL_HOOK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    official = parse_hook_markers(args.official_hook)
    local = parse_hook_markers(args.local_hook)
    diff = compare_markers(official, local)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "official": asdict(official),
        "local": asdict(local),
        "diff": asdict(diff),
    }
    (args.output_dir / "startup-hook-diff-doctor.json").write_text(
        json.dumps(artifact, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "startup-hook-diff-doctor.md").write_text(
        render_markdown(official, local, diff),
        encoding="utf-8",
    )
    print(json.dumps(asdict(diff), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
