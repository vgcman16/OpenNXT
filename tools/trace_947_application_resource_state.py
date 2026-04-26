from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import frida


DEFAULT_OUTPUT_ROOT = Path(
    r"C:\Users\skull\Documents\RuneScape\OpenNXT-mitm\data\debug\application-resource-state-947"
)
DEFAULT_GATE_RVA = 0x59671F
DEFAULT_DISPATCH_RVA = 0x595530
DEFAULT_SELECT_NEXT_RVA = 0x594270
DEFAULT_SCHEDULER_GLOBAL_RVA = 0xE57B60


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trace the 947 application-resource splash gate and dispatch path with Frida."
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
        default=20.0,
        help="How long to keep the hooks attached",
    )
    parser.add_argument(
        "--gate-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_GATE_RVA,
        help="Splash resource gate RVA (default: 0x59671F)",
    )
    parser.add_argument(
        "--dispatch-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_DISPATCH_RVA,
        help="Resource dispatch RVA (default: 0x595530)",
    )
    parser.add_argument(
        "--select-next-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_SELECT_NEXT_RVA,
        help="Resource next-index selector RVA (default: 0x594270)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory for JSON artifacts",
    )
    parser.add_argument(
        "--scheduler-global-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_SCHEDULER_GLOBAL_RVA,
        help="Global qword compared against owner+0x11b38 inside the dispatch path",
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


def build_script(*, gate_rva: int, dispatch_rva: int, select_next_rva: int, scheduler_global_rva: int) -> str:
    return (
        r"""
const moduleBase = Process.enumerateModules()[0].base;
const gateAddress = moduleBase.add(__GATE_RVA__);
const dispatchAddress = moduleBase.add(__DISPATCH_RVA__);
const selectNextAddress = moduleBase.add(__SELECT_NEXT_RVA__);
const schedulerGlobalAddress = moduleBase.add(__SCHEDULER_GLOBAL_RVA__);
const RESOURCE_COUNT = 67;
const dispatchCounts = {};
const selectCounts = {};
const latest = {
  gate: null,
  dispatch: null,
  selectNext: null
};
let gateHits = 0;
let dispatchHits = 0;
let selectHits = 0;
let lastDispatchIndex = null;
let lastSelectIndex = null;

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

function safeReadS32(address) {
  try {
    return ptr(address).readS32();
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

function safeReadU64(address) {
  try {
    return ptr(address).readU64().toString();
  } catch (_error) {
    return null;
  }
}

function summarizeOwner(owner) {
  const activeIndices = [];
  const inProgressIndices = [];
  const special20Indices = [];
  const special21Indices = [];
  const queuedIndices = [];
  const stateIndices = [];
  const field1cNonZeroIndices = [];
  const ptr178SetIndices = [];
  const ptr1c8SetIndices = [];

  for (let index = 0; index < RESOURCE_COUNT; index += 1) {
    const record = ptr(owner).add(8 + (index * 0x1d8));
    const flagD = safeReadU8(record.add(0x0d));
    const flagE = safeReadU8(record.add(0x0e));
    const flag20 = safeReadU8(record.add(0x20));
    const flag21 = safeReadU8(record.add(0x21));
    const field1c = safeReadS32(record.add(0x1c));
    const ptr178 = hexPtr(safeReadPointer(record.add(0x178)));
    const ptr1c8 = hexPtr(safeReadPointer(record.add(0x1c8)));
    const queued = safeReadU8(ptr(owner).add(0x11468 + index));
    const stateValue = safeReadU32(ptr(owner).add(0x119e4 + (index * 4)));
    if (flagD) {
      activeIndices.push(index);
    }
    if (flagE) {
      inProgressIndices.push(index);
    }
    if (flag20) {
      special20Indices.push(index);
    }
    if (flag21) {
      special21Indices.push(index);
    }
    if (field1c) {
      field1cNonZeroIndices.push(index);
    }
    if (ptr178 && ptr178 !== "0x0") {
      ptr178SetIndices.push(index);
    }
    if (ptr1c8 && ptr1c8 !== "0x0") {
      ptr1c8SetIndices.push(index);
    }
    if (queued) {
      queuedIndices.push(index);
    }
    if (stateValue) {
      stateIndices.push({ index: index, state: stateValue });
    }
  }

  return {
    owner: hexPtr(owner),
    flag11b48: safeReadU8(ptr(owner).add(0x11b48)),
    flag11d48: safeReadU8(ptr(owner).add(0x11d48)),
    flag11d49: safeReadU8(ptr(owner).add(0x11d49)),
    flag11d4a: safeReadU8(ptr(owner).add(0x11d4a)),
    flag114e0: safeReadU8(ptr(owner).add(0x114e0)),
    owner11b38: safeReadU64(ptr(owner).add(0x11b38)),
    owner11b40: safeReadU64(ptr(owner).add(0x11b40)),
    schedulerGlobal: safeReadU64(schedulerGlobalAddress),
    queueBegin: hexPtr(safeReadPointer(ptr(owner).add(0x11558))),
    queueCurrent: hexPtr(safeReadPointer(ptr(owner).add(0x11560))),
    queueEnd: hexPtr(safeReadPointer(ptr(owner).add(0x11568))),
    activeCount: activeIndices.length,
    activeIndices: activeIndices,
    inProgressCount: inProgressIndices.length,
    inProgressIndices: inProgressIndices,
    special20Count: special20Indices.length,
    special20Indices: special20Indices,
    special21Count: special21Indices.length,
    special21Indices: special21Indices,
    field1cNonZeroCount: field1cNonZeroIndices.length,
    field1cNonZeroIndices: field1cNonZeroIndices,
    ptr178SetCount: ptr178SetIndices.length,
    ptr178SetIndices: ptr178SetIndices,
    ptr1c8SetCount: ptr1c8SetIndices.length,
    ptr1c8SetIndices: ptr1c8SetIndices,
    queuedCount: queuedIndices.length,
    queuedIndices: queuedIndices,
    stateCount: stateIndices.length,
    stateIndices: stateIndices
  };
}

function countByIndex(map, index) {
  const key = index.toString();
  if (!(key in map)) {
    map[key] = 0;
  }
  map[key] += 1;
}

let latestGateKey = null;
Interceptor.attach(gateAddress, {
  onEnter(args) {
    gateHits += 1;
    const owner = this.context.rdi;
    const summary = summarizeOwner(owner);
    const event = {
      event: "resource-gate",
      owner: summary.owner,
      summary: summary,
      timestamp: Date.now() / 1000.0
    };
    latest.gate = event;
    const key = JSON.stringify(summary);
    if (key !== latestGateKey) {
      latestGateKey = key;
      send(event);
    }
  }
});

Interceptor.attach(dispatchAddress, {
  onEnter(args) {
    dispatchHits += 1;
    const owner = args[0];
    const index = args[1].toInt32();
    countByIndex(dispatchCounts, index);
    const summary = summarizeOwner(owner);
    const event = {
      event: "resource-dispatch",
      owner: summary.owner,
      index: index,
      summary: summary,
      timestamp: Date.now() / 1000.0
    };
    latest.dispatch = event;
    if (index !== lastDispatchIndex) {
      lastDispatchIndex = index;
      send(event);
    }
  }
});

Interceptor.attach(selectNextAddress, {
  onEnter(args) {
    this.owner = args[0];
  },
  onLeave(retval) {
    selectHits += 1;
    const index = retval.toInt32();
    countByIndex(selectCounts, index);
    const summary = summarizeOwner(this.owner);
    const event = {
      event: "resource-select-next",
      owner: summary.owner,
      index: index,
      summary: summary,
      timestamp: Date.now() / 1000.0
    };
    latest.selectNext = event;
    if (index !== lastSelectIndex) {
      lastSelectIndex = index;
      send(event);
    }
  }
});
"""
        .replace("__GATE_RVA__", hex(gate_rva))
        .replace("__DISPATCH_RVA__", hex(dispatch_rva))
        .replace("__SELECT_NEXT_RVA__", hex(select_next_rva))
        .replace("__SCHEDULER_GLOBAL_RVA__", hex(scheduler_global_rva))
    )


def archive_output_path(output_root: Path, timestamp: datetime) -> Path:
    return output_root / f"947-application-resource-state-{timestamp.strftime('%Y%m%d-%H%M%S')}.jsonl"


def archive_summary_path(output_root: Path, timestamp: datetime) -> Path:
    return output_root / f"947-application-resource-state-{timestamp.strftime('%Y%m%d-%H%M%S')}.json"


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
    script = session.create_script(
        build_script(
            gate_rva=args.gate_rva,
            dispatch_rva=args.dispatch_rva,
            select_next_rva=args.select_next_rva,
            scheduler_global_rva=args.scheduler_global_rva,
        )
    )

    gate_hits = 0
    dispatch_hits = 0
    select_hits = 0
    dispatch_counts: dict[str, int] = {}
    select_counts: dict[str, int] = {}
    latest_gate = None
    latest_dispatch = None
    latest_select = None

    with archive_path.open("w", encoding="utf-8") as archive_file, latest_path.open(
        "w", encoding="utf-8"
    ) as latest_file:

        def handle_message(message: dict, _data) -> None:
            nonlocal gate_hits, dispatch_hits, select_hits, latest_gate, latest_dispatch, latest_select
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
            event_name = payload.get("event")
            if event_name == "resource-gate":
                gate_hits += 1
                latest_gate = payload
            elif event_name == "resource-dispatch":
                dispatch_hits += 1
                latest_dispatch = payload
                index = str(payload.get("index"))
                dispatch_counts[index] = dispatch_counts.get(index, 0) + 1
            elif event_name == "resource-select-next":
                select_hits += 1
                latest_select = payload
                index = str(payload.get("index"))
                select_counts[index] = select_counts.get(index, 0) + 1
            line = json.dumps(payload, ensure_ascii=True)
            archive_file.write(line + "\n")
            archive_file.flush()
            latest_file.write(line + "\n")
            latest_file.flush()

        script.on("message", handle_message)
        script.load()
        try:
            time.sleep(args.duration_seconds)
        finally:
            try:
                script.unload()
            finally:
                session.detach()

    summary_payload = {
        "pid": pid,
        "gateRva": hex(args.gate_rva),
        "dispatchRva": hex(args.dispatch_rva),
        "selectNextRva": hex(args.select_next_rva),
        "schedulerGlobalRva": hex(args.scheduler_global_rva),
        "archivePath": str(archive_path),
        "latestPath": str(latest_path),
        "durationSeconds": args.duration_seconds,
        "snapshot": {
            "gateRva": hex(args.gate_rva),
            "dispatchRva": hex(args.dispatch_rva),
            "selectNextRva": hex(args.select_next_rva),
            "schedulerGlobalRva": hex(args.scheduler_global_rva),
            "gateHits": gate_hits,
            "dispatchHits": dispatch_hits,
            "selectHits": select_hits,
            "dispatchCounts": dispatch_counts,
            "selectCounts": select_counts,
            "latest": {
                "gate": latest_gate,
                "dispatch": latest_dispatch,
                "selectNext": latest_select,
            },
        },
    }
    archive_summary.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    latest_summary.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    print(json.dumps({"archivePath": str(archive_path), "summaryPath": str(archive_summary), "pid": pid}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
