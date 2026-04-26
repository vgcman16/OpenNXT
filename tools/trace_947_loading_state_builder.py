from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import frida
    FRIDA_IMPORT_ERROR = None
except Exception as frida_import_error:  # pragma: no cover - exercised on locked-down Windows hosts
    frida = None
    FRIDA_IMPORT_ERROR = frida_import_error


DEFAULT_OUTPUT_ROOT = Path(
    r"C:\Users\skull\Documents\RuneScape\OpenNXT-mitm\data\debug\loading-state-builder-947"
)
DEFAULT_STATE_COPY_RVA = 0x593010
DEFAULT_LOADING_GATE_RVA = 0x594A10
DEFAULT_LOADING_CALLSITE_RVA = 0x59109C
DEFAULT_RECORD_STRIDE = 0x108


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trace the 947 loading-state copy path at 0x593010 and correlate it with 0x594a10."
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
        default=30.0,
        help="How long to keep the hooks attached",
    )
    parser.add_argument(
        "--state-copy-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_STATE_COPY_RVA,
        help="Target state-copy RVA (default: 0x593010)",
    )
    parser.add_argument(
        "--loading-gate-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_LOADING_GATE_RVA,
        help="Target loading-gate RVA to correlate with copied state blobs (default: 0x594A10)",
    )
    parser.add_argument(
        "--loading-callsite-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_LOADING_CALLSITE_RVA,
        help="Pre-callsite RVA inside 0x590bc0 that prepares the 0x594A10 call (default: 0x59109C)",
    )
    parser.add_argument(
        "--record-stride",
        type=lambda value: int(value, 0),
        default=DEFAULT_RECORD_STRIDE,
        help="Owner record stride used for the sibling slot summaries (default: 0x108)",
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


def build_script(
    *,
    state_copy_rva: int,
    loading_gate_rva: int,
    loading_callsite_rva: int,
    record_stride: int,
) -> str:
    return (
        r"""
const moduleBase = Process.enumerateModules()[0].base;
const stateCopyRva = __STATE_COPY_RVA__;
const loadingGateRva = __LOADING_GATE_RVA__;
const loadingCallsiteRva = __LOADING_CALLSITE_RVA__;
const recordStride = __RECORD_STRIDE__;
const stateCopyAddress = moduleBase.add(__STATE_COPY_RVA__);
const loadingGateAddress = moduleBase.add(__LOADING_GATE_RVA__);
const loadingCallsiteAddress = moduleBase.add(__LOADING_CALLSITE_RVA__);
const comboCounts = {};
let totalStateCopyCalls = 0;
let totalLoadingGateCalls = 0;
let totalLoadingCallsiteHits = 0;

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

function safeReadU64Text(address) {
  try {
    return ptr(address).readU64().toString();
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

function callsiteRvaText(returnAddress) {
  if (returnAddress === null || returnAddress === undefined) {
    return null;
  }
  try {
    return '0x' + ptr(returnAddress).sub(moduleBase).toString(16);
  } catch (_error) {
    return null;
  }
}

function summarizeState(statePointer) {
  if (statePointer === null || statePointer === undefined) {
    return {
      statePointer: null
    };
  }
  const pointerValue = ptr(statePointer);
  return {
    statePointer: hexPtr(pointerValue),
    directPrimary: safeReadU32(pointerValue),
    directSecondary: safeReadU32(pointerValue.add(0x20)),
    flag24: safeReadU8(pointerValue.add(0x24)),
    field28: safeReadU32(pointerValue.add(0x28)),
    block90Pointer: hexPtr(safeReadPointer(pointerValue.add(0x90))),
    block98Count: safeReadCount(pointerValue.add(0x98)),
    vectorA0: hexPtr(safeReadPointer(pointerValue.add(0xa0))),
    blockA8Pointer: hexPtr(safeReadPointer(pointerValue.add(0xa8))),
    blockC0Pointer: hexPtr(safeReadPointer(pointerValue.add(0xc0))),
    blockC8Count: safeReadCount(pointerValue.add(0xc8)),
    vectorD0: hexPtr(safeReadPointer(pointerValue.add(0xd0))),
    blockD8Pointer: hexPtr(safeReadPointer(pointerValue.add(0xd8))),
    blockF0Pointer: hexPtr(safeReadPointer(pointerValue.add(0xf0))),
    raw90: safeReadU64Text(pointerValue.add(0x90)),
    raw98: safeReadU64Text(pointerValue.add(0x98)),
    rawA0: safeReadU64Text(pointerValue.add(0xa0)),
    rawA8: safeReadU64Text(pointerValue.add(0xa8)),
    rawC0: safeReadU64Text(pointerValue.add(0xc0)),
    rawC8: safeReadU64Text(pointerValue.add(0xc8)),
    rawD0: safeReadU64Text(pointerValue.add(0xd0)),
    rawD8: safeReadU64Text(pointerValue.add(0xd8)),
    rawF0: safeReadU64Text(pointerValue.add(0xf0))
  };
}

function summarizeOwnerSlot(ownerPointer, resourceIndex, baseOffset) {
  if (ownerPointer === null || ownerPointer === undefined || resourceIndex === null) {
    return {
      slotPointer: null
    };
  }
  try {
    const pointerValue = ptr(ownerPointer).add(baseOffset + (resourceIndex * recordStride));
    const state = summarizeState(pointerValue);
    state.slotPointer = state.statePointer;
    state.baseOffset = '0x' + baseOffset.toString(16);
    state.resourceIndex = resourceIndex;
    return state;
  } catch (_error) {
    return {
      slotPointer: null,
      baseOffset: '0x' + baseOffset.toString(16),
      resourceIndex: resourceIndex
    };
  }
}

function emitUnique(eventName, payload) {
  const key = eventName + '|' + JSON.stringify(payload);
  const uniqueCount = (comboCounts[key] || 0) + 1;
  comboCounts[key] = uniqueCount;
  if (uniqueCount === 1 || uniqueCount % 25 === 0) {
    send(Object.assign({
      event: eventName,
      uniqueCount: uniqueCount
    }, payload));
  }
}

Interceptor.attach(stateCopyAddress, {
  onEnter(args) {
    totalStateCopyCalls += 1;
    this.targetState = args[0];
    this.sourceState = args[1];
    this.callerRva = callsiteRvaText(this.returnAddress);
    this.beforeTarget = summarizeState(this.targetState);
    this.beforeSource = summarizeState(this.sourceState);
  },
  onLeave(retval) {
    emitUnique('loading-state-copy-leave-unique', {
      callerRva: this.callerRva,
      returnValue: hexPtr(retval),
      targetStatePointer: hexPtr(this.targetState),
      sourceStatePointer: hexPtr(this.sourceState),
      beforeTarget: this.beforeTarget,
      beforeSource: this.beforeSource,
      afterTarget: summarizeState(this.targetState),
      afterSource: summarizeState(this.sourceState),
      timestamp: Date.now() / 1000.0
    });
  }
});

Interceptor.attach(loadingCallsiteAddress, {
  onEnter(args) {
    totalLoadingCallsiteHits += 1;
    const owner = this.context.r14;
    const resourceIndex = safeReadU32(this.context.rbp.add(0xa0));
    const archive = this.context.rbx.toUInt32();
    const chosenPointer = this.context.rdi;
    const slot31f8 = summarizeOwnerSlot(owner, resourceIndex, 0x31f8);
    const slot7710 = summarizeOwnerSlot(owner, resourceIndex, 0x7710);
    const slotbc28 = summarizeOwnerSlot(owner, resourceIndex, 0xbc28);
    emitUnique('loading-state-callsite-unique', {
      callsiteRva: '0x' + loadingCallsiteRva.toString(16),
      owner: hexPtr(owner),
      session: hexPtr(this.context.rcx),
      inputId: resourceIndex,
      archiveIndex: archive,
      chosenStatePointer: hexPtr(chosenPointer),
      chosenState: summarizeState(chosenPointer),
      chosenMatches31f8: slot31f8.slotPointer === hexPtr(chosenPointer),
      chosenMatches7710: slot7710.slotPointer === hexPtr(chosenPointer),
      chosenMatchesBc28: slotbc28.slotPointer === hexPtr(chosenPointer),
      slot31f8: slot31f8,
      slot7710: slot7710,
      slotBc28: slotbc28,
      timestamp: Date.now() / 1000.0
    });
  }
});

Interceptor.attach(loadingGateAddress, {
  onEnter(args) {
    totalLoadingGateCalls += 1;
    emitUnique('loading-state-gate-unique', {
      callerRva: callsiteRvaText(this.returnAddress),
      owner: hexPtr(this.context.rcx),
      inputId: this.context.rdx.toUInt32(),
      index: this.context.r8.toUInt32(),
      statePointer: hexPtr(this.context.r9),
      state: summarizeState(this.context.r9),
      timestamp: Date.now() / 1000.0
    });
  }
});

rpc.exports = {
  snapshot() {
    const eventCounts = {};
    for (const key in comboCounts) {
      const eventName = key.split('|', 1)[0];
      eventCounts[eventName] = (eventCounts[eventName] || 0) + comboCounts[key];
    }
    return {
      stateCopyRva: "0x" + stateCopyRva.toString(16),
      loadingGateRva: "0x" + loadingGateRva.toString(16),
      loadingCallsiteRva: "0x" + loadingCallsiteRva.toString(16),
      totalStateCopyCalls: totalStateCopyCalls,
      totalLoadingGateCalls: totalLoadingGateCalls,
      totalLoadingCallsiteHits: totalLoadingCallsiteHits,
      uniqueKeyCount: Object.keys(comboCounts).length,
      eventCounts: eventCounts
    };
  }
};
"""
        .replace("__STATE_COPY_RVA__", hex(state_copy_rva))
        .replace("__LOADING_GATE_RVA__", hex(loading_gate_rva))
        .replace("__LOADING_CALLSITE_RVA__", hex(loading_callsite_rva))
        .replace("__RECORD_STRIDE__", hex(record_stride))
    )


def archive_output_path(output_root: Path, timestamp: datetime) -> Path:
    return output_root / f"947-loading-state-builder-{timestamp.strftime('%Y%m%d-%H%M%S')}.jsonl"


def archive_summary_path(output_root: Path, timestamp: datetime) -> Path:
    return output_root / f"947-loading-state-builder-{timestamp.strftime('%Y%m%d-%H%M%S')}.json"


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
            state_copy_rva=args.state_copy_rva,
            loading_gate_rva=args.loading_gate_rva,
            loading_callsite_rva=args.loading_callsite_rva,
            record_stride=args.record_stride,
        )
    )

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
        time.sleep(args.duration_seconds)
        snapshot = script.exports_sync.snapshot()
        session.detach()

    summary = {
        "pid": pid,
        "stateCopyRva": hex(args.state_copy_rva),
        "loadingGateRva": hex(args.loading_gate_rva),
        "loadingCallsiteRva": hex(args.loading_callsite_rva),
        "recordStride": hex(args.record_stride),
        "archivePath": str(archive_path),
        "latestPath": str(latest_path),
        "durationSeconds": args.duration_seconds,
        "snapshot": snapshot,
    }
    archive_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    latest_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
