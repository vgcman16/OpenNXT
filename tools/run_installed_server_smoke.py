from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


WORKSPACE = Path(__file__).resolve().parents[1]
SERVER_CONFIG = WORKSPACE / "data" / "config" / "server.toml"
DEFAULT_SERVER_BAT = WORKSPACE / "build" / "install" / "OpenNXT" / "bin" / "OpenNXT.bat"
DEFAULT_STDOUT = WORKSPACE / "tmp-installed-server-smoke.out.log"
DEFAULT_STDERR = WORKSPACE / "tmp-installed-server-smoke.err.log"
NO_CLASS_DEF_MARKER = "NoClassDefFoundError"
CANONICAL_QUERY_PARAMS = {
    "binaryType": "6",
    "hostRewrite": "0",
    "lobbyHostRewrite": "0",
    "contentRouteRewrite": "1",
    "gameHostOverride": "lobby45a.runescape.com",
    "downloadMetadataSource": "patched",
    "worldUrlRewrite": "0",
    "codebaseRewrite": "0",
    "baseConfigSource": "live",
    "liveCache": "1",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test the installed OpenNXT server runtime.")
    parser.add_argument("--server-bat", type=Path, default=DEFAULT_SERVER_BAT)
    parser.add_argument("--server-config", type=Path, default=SERVER_CONFIG)
    parser.add_argument("--stdout-log", type=Path, default=DEFAULT_STDOUT)
    parser.add_argument("--stderr-log", type=Path, default=DEFAULT_STDERR)
    parser.add_argument("--startup-timeout-seconds", type=int, default=60)
    parser.add_argument("--request-timeout-seconds", type=int, default=10)
    return parser.parse_args()


def wait_for_port(port: int, *, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            try:
                sock.connect(("127.0.0.1", port))
                return True
            except OSError:
                time.sleep(0.25)
    return False


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def contains_no_class_def(stderr_path: Path) -> bool:
    return NO_CLASS_DEF_MARKER in read_text(stderr_path)


def load_server_ports(server_config: Path) -> dict[str, int]:
    with server_config.open("rb") as handle:
        data = tomllib.load(handle)
    ports = ((data.get("networking") or {}).get("ports")) or {}
    return {
        "http": int(ports.get("http", 8081)),
        "game": int(ports.get("gameBackend", ports.get("game", 43596))),
    }


def build_canonical_query(http_port: int) -> str:
    return f"http://localhost:{http_port}/jav_config.ws?{urlencode(CANONICAL_QUERY_PARAMS)}"


def stop_process_tree(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        check=False,
    )


def fetch_canonical_jav_config(query_url: str, *, timeout_seconds: int) -> tuple[int, str]:
    try:
        with urlopen(query_url, timeout=timeout_seconds) as response:
            return response.status, response.read().decode("iso-8859-1", errors="ignore")
    except HTTPError as error:
        body = error.read().decode("iso-8859-1", errors="ignore")
        return error.code, body
    except URLError as error:
        return 0, str(error)


def main() -> int:
    args = parse_args()
    args.stdout_log.parent.mkdir(parents=True, exist_ok=True)
    args.stderr_log.parent.mkdir(parents=True, exist_ok=True)
    if not args.server_bat.exists():
        print(f"missing-server-bat: {args.server_bat}", file=sys.stderr)
        return 1
    if not args.server_config.exists():
        print(f"missing-server-config: {args.server_config}", file=sys.stderr)
        return 1
    ports = load_server_ports(args.server_config)
    canonical_query = build_canonical_query(ports["http"])

    args.stdout_log.write_text("", encoding="utf-8")
    args.stderr_log.write_text("", encoding="utf-8")

    stdout_handle = args.stdout_log.open("w", encoding="utf-8")
    stderr_handle = args.stderr_log.open("w", encoding="utf-8")
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            [str(args.server_bat), "run-server"],
            cwd=str(WORKSPACE),
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            shell=False,
        )

        for port in (ports["http"], ports["game"]):
            if not wait_for_port(port, timeout_seconds=args.startup_timeout_seconds):
                print(f"port-timeout: {port}", file=sys.stderr)
                return 1
            if contains_no_class_def(args.stderr_log):
                print("startup-no-class-def", file=sys.stderr)
                return 1

        status, body = fetch_canonical_jav_config(canonical_query, timeout_seconds=args.request_timeout_seconds)
        if status != 200:
            print(f"bad-jav-config-status: {status}", file=sys.stderr)
            return 1
        if "param=37=localhost" not in body or "param=49=localhost" not in body:
            print("content-route-rewrite-missing", file=sys.stderr)
            return 1
        if "param=35=http://localhost:" not in body or "codebase=http://localhost:" not in body:
            print("world-or-codebase-rewrite-missing", file=sys.stderr)
            return 1
        if contains_no_class_def(args.stderr_log):
            print("request-no-class-def", file=sys.stderr)
            return 1
        print("installed-server-smoke-ok")
        return 0
    finally:
        stop_process_tree(process)
        stdout_handle.close()
        stderr_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
