from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[1]
DIRECT_DEBUG_DIR = WORKSPACE / "data" / "debug" / "direct-rs2client-patch"
FALLBACK_HOOK_PATH = WORKSPACE / "data" / "debug" / "wrapper-spawn-rewrite" / "manual-wrapper-947-child-hook-20260326.jsonl"
DEFAULT_OUTPUT_DIR = WORKSPACE / "data" / "debug" / "codebase-bootstrap-doctor-947-current"
TARGET_PORTS = {80, 8080}


@dataclass(frozen=True)
class ChunkPreview:
    timestamp: float
    socket: str
    remote_host: str | None
    remote_port: int | None
    bytes: int
    preview_hex: str
    preview_text: str
    first_line: str | None
    looks_http: bool


@dataclass(frozen=True)
class SocketExchange:
    socket: str
    remote_host: str | None
    remote_port: int | None
    connect_status: int | None
    close_status: int | None
    bytes_sent_total: int
    bytes_received_total: int
    first_send: ChunkPreview | None
    first_recv: ChunkPreview | None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else str(value).strip().lower() == "true"


def parse_hook_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                events.append(payload)
    return events


def resolve_default_hook_path(
    direct_debug_dir: Path = DIRECT_DEBUG_DIR,
    fallback_hook_path: Path = FALLBACK_HOOK_PATH,
) -> Path:
    if direct_debug_dir.exists():
        candidates = sorted(direct_debug_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        for summary_path in candidates:
            try:
                payload = json.loads(summary_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            hook_path = payload.get("startupHookOutput")
            if not hook_path:
                continue
            live_process_path = str(payload.get("liveProcessPath") or payload.get("clientExe") or "").lower()
            if "win64c\\patched" not in live_process_path:
                continue
            candidate = Path(str(hook_path))
            if candidate.exists():
                return candidate
    return fallback_hook_path


def build_socket_exchanges(events: list[dict[str, Any]]) -> list[SocketExchange]:
    by_socket: dict[str, dict[str, Any]] = {}

    for event in events:
        if event.get("category") != "client.net":
            continue
        socket = str(event.get("socket", "") or "")
        if not socket:
            continue
        state = by_socket.setdefault(
            socket,
            {
                "socket": socket,
                "remoteHost": None,
                "remotePort": None,
                "connectStatus": None,
                "closeStatus": None,
                "bytesSentTotal": 0,
                "bytesReceivedTotal": 0,
                "firstSend": None,
                "firstRecv": None,
                "lastTimestamp": 0.0,
            },
        )

        remote_host = event.get("remoteHost")
        remote_port = _parse_int(event.get("remotePort"))
        if remote_host is not None:
            state["remoteHost"] = str(remote_host)
        if remote_port is not None:
            state["remotePort"] = remote_port
        if _parse_int(event.get("bytesSent")) is not None:
            state["bytesSentTotal"] = max(int(state["bytesSentTotal"]), _parse_int(event.get("bytesSent")) or 0)
        if _parse_int(event.get("bytesReceived")) is not None:
            state["bytesReceivedTotal"] = max(int(state["bytesReceivedTotal"]), _parse_int(event.get("bytesReceived")) or 0)
        state["lastTimestamp"] = max(float(state["lastTimestamp"]), float(event.get("timestamp", 0.0) or 0.0))

        action = str(event.get("action", ""))
        if action == "connect":
            state["connectStatus"] = _parse_int(event.get("status"))
        elif action == "close":
            state["closeStatus"] = _parse_int(event.get("status"))
        elif action in {"send-first-chunk", "recv-first-chunk"}:
            preview = ChunkPreview(
                timestamp=float(event.get("timestamp", 0.0) or 0.0),
                socket=socket,
                remote_host=str(remote_host) if remote_host is not None else None,
                remote_port=remote_port,
                bytes=_parse_int(event.get("bytes")) or 0,
                preview_hex=str(event.get("previewHex", "") or ""),
                preview_text=str(event.get("previewText", "") or ""),
                first_line=str(event.get("firstLine")) if event.get("firstLine") is not None else None,
                looks_http=_parse_bool(event.get("looksHttp")),
            )
            if action == "send-first-chunk" and state["firstSend"] is None:
                state["firstSend"] = preview
            elif action == "recv-first-chunk" and state["firstRecv"] is None:
                state["firstRecv"] = preview

    exchanges = [
        SocketExchange(
            socket=str(state["socket"]),
            remote_host=state["remoteHost"],
            remote_port=state["remotePort"],
            connect_status=state["connectStatus"],
            close_status=state["closeStatus"],
            bytes_sent_total=int(state["bytesSentTotal"]),
            bytes_received_total=int(state["bytesReceivedTotal"]),
            first_send=state["firstSend"],
            first_recv=state["firstRecv"],
        )
        for state in sorted(by_socket.values(), key=lambda entry: float(entry["lastTimestamp"]))
    ]
    return exchanges


def choose_codebase_exchange(exchanges: list[SocketExchange]) -> SocketExchange | None:
    candidates = [
        exchange
        for exchange in exchanges
        if exchange.remote_port in TARGET_PORTS
        and (
            exchange.first_send is not None
            or exchange.bytes_sent_total > 0
            or exchange.bytes_received_total > 0
        )
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda exchange: (
            exchange.first_send is not None,
            exchange.first_send.timestamp if exchange.first_send is not None else 0.0,
            exchange.bytes_sent_total,
            exchange.bytes_received_total,
        ),
        reverse=True,
    )
    return candidates[0]


def infer_likely_blocker(exchange: SocketExchange | None) -> str:
    if exchange is None:
        return "no-codebase-bootstrap-exchange-captured"
    if exchange.first_send is None:
        return "codebase-bootstrap-send-missing"
    if not exchange.first_send.looks_http:
        return "codebase-bootstrap-non-http-request"
    if exchange.first_recv is None:
        return "codebase-bootstrap-response-missing"
    if exchange.first_recv.looks_http:
        first_line = exchange.first_recv.first_line or ""
        if " 404" in first_line:
            return "codebase-bootstrap-http-404"
        if " 403" in first_line:
            return "codebase-bootstrap-http-403"
        if " 500" in first_line:
            return "codebase-bootstrap-http-500"
        if " 200" in first_line:
            return "codebase-bootstrap-http-200-no-progress"
    return "codebase-bootstrap-opaque-response"


def render_markdown(hook_path: Path, exchanges: list[SocketExchange], selected: SocketExchange | None, likely_blocker: str) -> str:
    lines = [
        "# 947 Codebase Bootstrap Doctor",
        "",
        f"- Hook path: `{hook_path}`",
        f"- Socket exchanges parsed: `{len(exchanges)}`",
        f"- Likely blocker: `{likely_blocker}`",
        "",
    ]
    if selected is None:
        lines.extend(
            [
                "## Selected Exchange",
                "",
                "- No codebase bootstrap exchange was captured on port `80` or `8080`.",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "## Selected Exchange",
            "",
            f"- Socket: `{selected.socket}`",
            f"- Remote: `{selected.remote_host}:{selected.remote_port}`",
            f"- Connect status: `{selected.connect_status}`",
            f"- Close status: `{selected.close_status}`",
            f"- Total sent: `{selected.bytes_sent_total}`",
            f"- Total received: `{selected.bytes_received_total}`",
            "",
            "## First Request",
            "",
            f"- Bytes: `{selected.first_send.bytes if selected.first_send else 0}`",
            f"- First line: `{selected.first_send.first_line if selected.first_send and selected.first_send.first_line else 'n/a'}`",
            f"- Preview text: `{selected.first_send.preview_text if selected.first_send else ''}`",
            f"- Preview hex: `{selected.first_send.preview_hex if selected.first_send else ''}`",
            "",
            "## First Response",
            "",
            f"- Bytes: `{selected.first_recv.bytes if selected.first_recv else 0}`",
            f"- First line: `{selected.first_recv.first_line if selected.first_recv and selected.first_recv.first_line else 'n/a'}`",
            f"- Preview text: `{selected.first_recv.preview_text if selected.first_recv else ''}`",
            f"- Preview hex: `{selected.first_recv.preview_hex if selected.first_recv else ''}`",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize the first splash-stage codebase bootstrap socket exchange for the 947 RuneScape client."
    )
    parser.add_argument("--hook-path", type=Path, default=resolve_default_hook_path())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    events = parse_hook_events(args.hook_path)
    exchanges = build_socket_exchanges(events)
    selected = choose_codebase_exchange(exchanges)
    likely_blocker = infer_likely_blocker(selected)

    artifact = {
        "tool": "run_947_codebase_bootstrap_doctor",
        "schemaVersion": 1,
        "hookPath": str(args.hook_path),
        "likelyBlocker": likely_blocker,
        "selectedExchange": asdict(selected) if selected is not None else None,
        "exchanges": [asdict(exchange) for exchange in exchanges],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "codebase-bootstrap-doctor.json"
    md_path = args.output_dir / "codebase-bootstrap-doctor.md"
    json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(args.hook_path, exchanges, selected, likely_blocker), encoding="utf-8")
    print(str(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
