from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import frida


DEFAULT_OUTPUT_ROOT = Path(
    r"C:\Users\skull\Documents\RuneScape\OpenNXT-mitm\data\debug\loading-gate-947"
)
DEFAULT_FUNCTION_RVA = 0x594A10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trace the 947 loading-screen gate at FUN_140594a10 with Frida."
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
        "--ignore-existing-processes",
        action="store_true",
        help="Only attach to a process that appears after this tracer starts",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=10.0,
        help="How long to keep the hooks attached",
    )
    parser.add_argument(
        "--function-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_FUNCTION_RVA,
        help="Target loading-gate function RVA (default: 0x594A10)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory for JSON artifacts",
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
    ignored_pids: set[int] = set()
    if args.ignore_existing_processes:
        ignored_pids = query_process_ids(args.process_name)
    deadline = time.time() + args.wait_timeout_seconds
    while time.time() < deadline:
        current_pids = query_process_ids(args.process_name)
        attachable_pids = [pid for pid in current_pids if pid not in ignored_pids]
        if attachable_pids:
            return attachable_pids[0]
        time.sleep(args.poll_interval_seconds)
    raise RuntimeError(
        f"Timed out waiting for process {args.process_name!r} after {args.wait_timeout_seconds:.1f}s"
    )


def build_script(*, function_rva: int) -> str:
    return (
        r"""
const moduleBase = Process.enumerateModules()[0].base;
const functionRva = __FUNCTION_RVA__;
const functionAddress = moduleBase.add(functionRva);
const comboCounts = {};
let totalCalls = 0;

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

function safeReadU8(address) {
  try {
    return ptr(address).readU8();
  } catch (_error) {
    return null;
  }
}

function safeReadU32(address) {
  try {
    return ptr(address).readU32();
  } catch (_error) {
    return null;
  }
}

function safeReadCount(address) {
  try {
    return parseInt(ptr(address).readU64().toString(), 10);
  } catch (_error) {
    return null;
  }
}

function safeReadPointer(address) {
  try {
    return ptr(address).readPointer();
  } catch (_error) {
    return null;
  }
}

function safeReadIndexedU32(vectorPtr, index, count) {
  if (vectorPtr === null || count === null || index === null || index >= count) {
    return null;
  }
  try {
    return ptr(vectorPtr).add(index * 4).readU32();
  } catch (_error) {
    return null;
  }
}

function selectValue(flag, directValue, indexedValue) {
  if (flag === null) {
    return null;
  }
  return flag !== 0 ? directValue : indexedValue;
}

Interceptor.attach(functionAddress, {
  onEnter(args) {
    totalCalls += 1;

    const owner = this.context.rcx;
    const inputId = this.context.rdx.toUInt32();
    const index = this.context.r8.toUInt32();
    const statePtr = this.context.r9;

    const flag24 = safeReadU8(statePtr.add(0x24));
    const directPrimary = safeReadU32(statePtr);
    const directSecondary = safeReadU32(statePtr.add(0x20));
    const count98 = safeReadCount(statePtr.add(0x98));
    const vectorA0 = safeReadPointer(statePtr.add(0xa0));
    const countC8 = safeReadCount(statePtr.add(0xc8));
    const vectorD0 = safeReadPointer(statePtr.add(0xd0));
    const indexedPrimary = safeReadIndexedU32(vectorA0, index, count98);
    const indexedSecondary = safeReadIndexedU32(vectorD0, index, countC8);
    const path = flag24 === null ? "unknown" : (flag24 !== 0 ? "direct" : "indexed");
    const selectedPrimary = selectValue(flag24, directPrimary, indexedPrimary);
    const selectedSecondary = selectValue(flag24, directSecondary, indexedSecondary);

    const event = {
      event: "loading-gate-unique",
      functionRva: "0x" + functionRva.toString(16),
      owner: hexPtr(owner),
      statePointer: hexPtr(statePtr),
      inputId: inputId,
      index: index,
      flag24: flag24,
      path: path,
      directPrimary: directPrimary,
      directSecondary: directSecondary,
      count98: count98,
      vectorA0: hexPtr(vectorA0),
      indexedPrimary: indexedPrimary,
      countC8: countC8,
      vectorD0: hexPtr(vectorD0),
      indexedSecondary: indexedSecondary,
      selectedPrimary: selectedPrimary,
      selectedSecondary: selectedSecondary,
      timestamp: Date.now() / 1000.0
    };

    const key = JSON.stringify([
      event.inputId,
      event.index,
      event.flag24,
      event.path,
      event.directPrimary,
      event.directSecondary,
      event.count98,
      event.indexedPrimary,
      event.countC8,
      event.indexedSecondary,
      event.selectedPrimary,
      event.selectedSecondary
    ]);

    if (!(key in comboCounts)) {
      comboCounts[key] = {
        count: 0,
        event: event
      };
      send(event);
    }
    comboCounts[key].count += 1;
  }
});

rpc.exports = {
  snapshot() {
    const combos = [];
    for (const key in comboCounts) {
      combos.push({
        count: comboCounts[key].count,
        event: comboCounts[key].event
      });
    }
    combos.sort((left, right) => right.count - left.count);
    return {
      functionRva: "0x" + functionRva.toString(16),
      totalCalls: totalCalls,
      comboCount: combos.length,
      combos: combos
    };
  }
};
"""
        .replace("__FUNCTION_RVA__", hex(function_rva))
    )


def archive_output_path(output_root: Path, timestamp: datetime) -> Path:
    return output_root / f"947-loading-gate-{timestamp.strftime('%Y%m%d-%H%M%S')}.jsonl"


def archive_summary_path(output_root: Path, timestamp: datetime) -> Path:
    return output_root / f"947-loading-gate-{timestamp.strftime('%Y%m%d-%H%M%S')}.json"


def main() -> int:
    args = parse_args()
    pid = resolve_pid(args)
    args.output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).astimezone()
    archive_path = archive_output_path(args.output_root, timestamp)
    latest_path = args.output_root / "latest-client-only.jsonl"
    archive_summary = archive_summary_path(args.output_root, timestamp)
    latest_summary = args.output_root / "latest-client-only.json"

    session = frida.attach(pid)
    script = session.create_script(build_script(function_rva=args.function_rva))

    with archive_path.open("w", encoding="utf-8") as archive_file, latest_path.open(
        "w", encoding="utf-8"
    ) as latest_file:

        def handle_message(message: dict, _data) -> None:
            if message.get("type") != "send":
                payload = {
                    "event": "frida-message",
                    "messageType": message.get("type"),
                    "payload": message.get("payload"),
                    "stack": message.get("stack"),
                    "description": message.get("description"),
                }
            else:
                payload = message.get("payload")
            if payload is None:
                return
            line = json.dumps(payload, ensure_ascii=True)
            archive_file.write(line + "\n")
            archive_file.flush()
            latest_file.write(line + "\n")
            latest_file.flush()

        script.on("message", handle_message)
        script.load()
        try:
            time.sleep(args.duration_seconds)
            snapshot = script.exports_sync.snapshot()
        finally:
            try:
                script.unload()
            finally:
                session.detach()

    summary_payload = {
        "pid": pid,
        "functionRva": hex(args.function_rva),
        "archivePath": str(archive_path),
        "latestPath": str(latest_path),
        "durationSeconds": args.duration_seconds,
        "snapshot": snapshot,
    }
    archive_summary.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    latest_summary.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    print(json.dumps({"archivePath": str(archive_path), "summaryPath": str(archive_summary), "pid": pid}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
