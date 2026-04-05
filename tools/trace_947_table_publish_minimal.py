from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import frida


DEFAULT_OUTPUT_ROOT = Path(
    r"C:\Users\skull\Documents\RuneScape\OpenNXT-mitm\data\debug\table-publish-minimal-947"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trace minimal 947 master-table builder/publish events with Frida."
    )
    parser.add_argument("--pid", type=int, help="Target rs2client.exe PID")
    parser.add_argument(
        "--process-name",
        default=None,
        help="Wait for the newest process with this name and attach to it",
    )
    parser.add_argument(
        "--wait-timeout-seconds",
        type=float,
        default=30.0,
        help="How long to wait for --process-name before failing",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=0.5,
        help="Polling interval for --process-name mode",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=90.0,
        help="How long to keep the hooks attached",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory for JSONL artifacts",
    )
    args = parser.parse_args()
    if args.pid is None and not args.process_name:
        parser.error("Either --pid or --process-name is required")
    return args


def query_process_ids(process_name: str | None) -> set[int]:
    if not process_name:
        return set()
    command = (
        f"Get-Process -Name '{process_name}' -ErrorAction SilentlyContinue | "
        "Sort-Object StartTime -Descending | Select-Object Id | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = completed.stdout.strip()
    if not stdout or stdout == "null":
        return set()
    payload = json.loads(stdout)
    if isinstance(payload, dict):
        return {int(payload["Id"])}
    if isinstance(payload, list):
        return {int(item["Id"]) for item in payload if isinstance(item, dict) and "Id" in item}
    return set()


def resolve_pid(args: argparse.Namespace) -> int:
    if args.pid is not None:
        return args.pid
    deadline = time.time() + args.wait_timeout_seconds
    while time.time() < deadline:
        current_pids = query_process_ids(args.process_name)
        if current_pids:
            return sorted(current_pids, reverse=True)[0]
        time.sleep(args.poll_interval_seconds)
    raise RuntimeError(
        f"Timed out waiting for process {args.process_name!r} after {args.wait_timeout_seconds:.1f}s"
    )


def build_script() -> str:
    return r"""
const moduleBase = Module.getBaseAddress("rs2client.exe");

function hookRva(rva, callbacks) {
  Interceptor.attach(moduleBase.add(rva), callbacks);
}

function hexPtr(value) {
  if (value === null || value === undefined) {
    return null;
  }
  try {
    return ptr(value).toString();
  } catch (_error) {
    return null;
  }
}

function safeReadPointer(address) {
  if (address === null || address === undefined) {
    return null;
  }
  try {
    return ptr(address).readPointer();
  } catch (_error) {
    return null;
  }
}

function safeReadU32(address) {
  if (address === null || address === undefined) {
    return null;
  }
  try {
    return ptr(address).readU32();
  } catch (_error) {
    return null;
  }
}

function safeReadU64(address) {
  if (address === null || address === undefined) {
    return null;
  }
  try {
    return ptr(address).readU64().toString();
  } catch (_error) {
    return null;
  }
}

function dumpTable(tablePtr) {
  if (tablePtr === null || tablePtr === undefined) {
    return {
      pointer: null,
      header0: null,
      refCount: null,
      count: null,
      entriesPointer: null,
    };
  }
  const pointerValue = ptr(tablePtr);
  try {
    return {
      pointer: hexPtr(pointerValue),
      header0: safeReadU32(pointerValue),
      refCount: safeReadU32(pointerValue.add(8)),
      count: safeReadU64(pointerValue.add(0x10)),
      entriesPointer: hexPtr(safeReadPointer(pointerValue.add(0x18))),
    };
  } catch (_error) {
    return {
      pointer: hexPtr(pointerValue),
      header0: null,
      refCount: null,
      count: null,
      entriesPointer: null,
    };
  }
}

function sendEvent(payload) {
  send(payload);
}

hookRva(0x59c2be, {
  onEnter(args) {
    sendEvent({
      event: "table-builder-compare-passed",
      functionRva: "0x59c2be",
      table: dumpTable(this.context.rsi),
    });
  }
});

hookRva(0x59c64f, {
  onEnter(args) {
    sendEvent({
      event: "table-builder-compare-failed",
      functionRva: "0x59c64f",
      compareLeft: hexPtr(this.context.r15),
      compareRight: hexPtr(this.context.rbx),
    });
  }
});

hookRva(0x59bd00, {
  onLeave(retval) {
    sendEvent({
      event: "table-builder-leave",
      functionRva: "0x59bd00",
      returnValue: hexPtr(retval),
      table: dumpTable(retval),
    });
  }
});

hookRva(0x592760, {
  onEnter(args) {
    this.owner = this.context.rsi;
    sendEvent({
      event: "table-swap-enter",
      functionRva: "0x592760",
      owner: hexPtr(this.owner),
      beforeTable: dumpTable(safeReadPointer(ptr(this.owner).add(0x30d0))),
    });
  },
  onLeave(retval) {
    sendEvent({
      event: "table-swap-leave",
      functionRva: "0x592760",
      owner: hexPtr(this.owner),
      afterTable: dumpTable(safeReadPointer(ptr(this.owner).add(0x30d0))),
      retval: hexPtr(retval),
    });
  }
});

hookRva(0x58fa60, {
  onEnter(args) {
    const owner = args[0];
    sendEvent({
      event: "table-consumer-enter",
      functionRva: "0x58fa60",
      owner: hexPtr(owner),
      table: dumpTable(safeReadPointer(ptr(owner).add(0x30d0))),
    });
  }
});
"""


def main() -> int:
    args = parse_args()
    pid = resolve_pid(args)

    args.output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = args.output_root / f"trace-{timestamp}-pid{pid}.jsonl"
    latest_path = args.output_root / "latest-client-only.jsonl"

    session = frida.attach(pid)
    script = session.create_script(build_script())

    with output_path.open("w", encoding="utf-8") as handle:
        def on_message(message: dict, data: bytes | None) -> None:
            if message.get("type") != "send":
                return
            payload = message.get("payload")
            if not isinstance(payload, dict):
                return
            payload.setdefault("timestamp", time.time())
            line = json.dumps(payload, ensure_ascii=True)
            handle.write(line + "\n")
            handle.flush()

        script.on("message", on_message)
        script.load()
        time.sleep(args.duration_seconds)
        session.detach()

    latest_path.write_text(output_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({"pid": pid, "outputPath": str(output_path), "latestPath": str(latest_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
