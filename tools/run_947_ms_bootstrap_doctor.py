from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = WORKSPACE / "data" / "debug" / "ms-bootstrap-doctor-947-current"
DEFAULT_QUERY = "m=0&a=255&k=947&g=255&c=0&v=0"
DEFAULT_LOCAL_URL = f"http://127.0.0.1/ms?{DEFAULT_QUERY}"
DEFAULT_LIVE_URL = f"https://content.runescape.com/ms?{DEFAULT_QUERY}"
ESSENTIAL_HEADERS = (
    "server",
    "content-type",
    "cache-control",
    "content-length",
    "connection",
)


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    headers: dict[str, str]
    body_length: int
    body_sha256: str
    first_64_hex: str


def fetch(url: str) -> FetchResult:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "*/*",
            "Connection": "close",
            "User-Agent": "OpenNXT-947-ms-bootstrap-doctor/1.0",
        },
        method="GET",
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=15, context=context) as response:
        body = response.read()
        headers = {key.lower(): value for key, value in response.headers.items()}
        return FetchResult(
            url=url,
            status=int(response.status),
            headers=headers,
            body_length=len(body),
            body_sha256=hashlib.sha256(body).hexdigest(),
            first_64_hex=body[:64].hex(),
        )


def compare_headers(local_headers: dict[str, str], live_headers: dict[str, str]) -> dict[str, dict[str, str | None]]:
    diffs: dict[str, dict[str, str | None]] = {}
    for name in ESSENTIAL_HEADERS:
        local_value = local_headers.get(name)
        live_value = live_headers.get(name)
        if local_value != live_value:
            diffs[name] = {
                "local": local_value,
                "live": live_value,
            }
    return diffs


def infer_likely_blocker(local: FetchResult, live: FetchResult, header_diffs: dict[str, dict[str, str | None]]) -> str:
    if local.status != 200:
        return f"local-http-{local.status}"
    if live.status != 200:
        return f"live-http-{live.status}"
    if local.body_sha256 != live.body_sha256:
        return "ms-bootstrap-body-mismatch"
    if header_diffs:
        return "ms-bootstrap-header-mismatch"
    return "match"


def render_markdown(local: FetchResult, live: FetchResult, header_diffs: dict[str, dict[str, str | None]], likely_blocker: str) -> str:
    lines = [
        "# 947 MS Bootstrap Doctor",
        "",
        f"- Local URL: `{local.url}`",
        f"- Live URL: `{live.url}`",
        f"- Likely blocker: `{likely_blocker}`",
        "",
        "## Body Compare",
        "",
        f"- Local status: `{local.status}`",
        f"- Live status: `{live.status}`",
        f"- Local length: `{local.body_length}`",
        f"- Live length: `{live.body_length}`",
        f"- Local SHA-256: `{local.body_sha256}`",
        f"- Live SHA-256: `{live.body_sha256}`",
        f"- Local first 64 bytes: `{local.first_64_hex}`",
        f"- Live first 64 bytes: `{live.first_64_hex}`",
        "",
        "## Header Diffs",
        "",
    ]
    if not header_diffs:
        lines.append("- No essential header differences.")
    else:
        for name, payload in header_diffs.items():
            lines.append(f"- `{name}` local=`{payload['local']}` live=`{payload['live']}`")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare the 947 local /ms bootstrap response with live.")
    parser.add_argument("--local-url", default=DEFAULT_LOCAL_URL)
    parser.add_argument("--live-url", default=DEFAULT_LIVE_URL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    local = fetch(args.local_url)
    live = fetch(args.live_url)
    header_diffs = compare_headers(local.headers, live.headers)
    likely_blocker = infer_likely_blocker(local, live, header_diffs)

    artifact = {
        "tool": "run_947_ms_bootstrap_doctor",
        "schemaVersion": 1,
        "likelyBlocker": likely_blocker,
        "local": asdict(local),
        "live": asdict(live),
        "headerDiffs": header_diffs,
    }
    (output_dir / "ms-bootstrap-doctor.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    (output_dir / "ms-bootstrap-doctor.md").write_text(
        render_markdown(local, live, header_diffs, likely_blocker),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
