import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_connection(connection: psutil._common.sconn) -> dict:
    local = None
    remote = None

    if connection.laddr:
        local = {"ip": connection.laddr.ip, "port": connection.laddr.port}
    if connection.raddr:
        remote = {"ip": connection.raddr.ip, "port": connection.raddr.port}

    return {
        "fd": connection.fd,
        "family": str(connection.family),
        "type": str(connection.type),
        "status": connection.status,
        "local": local,
        "remote": remote,
    }


def snapshot_process(process: psutil.Process) -> dict:
    snapshot = {
        "timestamp": iso_now(),
        "pid": process.pid,
    }

    try:
        snapshot["name"] = process.name()
        snapshot["status"] = process.status()
        snapshot["exe"] = process.exe()
        snapshot["cmdline"] = process.cmdline()
        snapshot["create_time"] = process.create_time()
        snapshot["cpu_percent"] = process.cpu_percent(interval=None)
        snapshot["memory_info"] = process.memory_info()._asdict()
        snapshot["num_threads"] = process.num_threads()
        snapshot["threads"] = [
            {"id": thread.id, "user_time": thread.user_time, "system_time": thread.system_time}
            for thread in process.threads()
        ]
        snapshot["open_files"] = [item.path for item in process.open_files()]
        snapshot["interesting_memory_maps"] = sorted(
            {
                mapping.path
                for mapping in process.memory_maps()
                if mapping.path
                and any(token in mapping.path.lower() for token in ("jagex", "runescape", "js5-", "shadercache"))
            }
        )
        snapshot["connections"] = [
            serialize_connection(connection)
            for connection in process.connections(kind="inet")
        ]
        snapshot["children"] = [
            {
                "pid": child.pid,
                "name": child.name(),
                "status": child.status(),
                "exe": child.exe(),
            }
            for child in process.children(recursive=True)
        ]
    except psutil.NoSuchProcess:
        snapshot["exited"] = True
    except (psutil.AccessDenied, psutil.ZombieProcess) as exc:
        snapshot["error"] = f"{type(exc).__name__}: {exc}"

    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll a process and write runtime snapshots to JSONL.")
    parser.add_argument("--pid", type=int, required=True, help="Process id to trace")
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=250,
        help="Polling interval in milliseconds",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Maximum trace duration in seconds",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to the JSONL output file",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    process = psutil.Process(args.pid)
    process.cpu_percent(interval=None)

    deadline = time.monotonic() + args.timeout_seconds
    interval_seconds = max(args.interval_ms, 10) / 1000.0

    with args.output.open("w", encoding="utf-8") as handle:
        while time.monotonic() < deadline:
            snapshot = snapshot_process(process)
            handle.write(json.dumps(snapshot, sort_keys=True) + "\n")
            handle.flush()

            if snapshot.get("exited"):
                return 0

            time.sleep(interval_seconds)

        handle.write(
            json.dumps(
                {
                    "timestamp": iso_now(),
                    "pid": args.pid,
                    "timeout": True,
                },
                sort_keys=True,
            ) + "\n"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
