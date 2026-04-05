from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import frida


DEFAULT_OUTPUT_ROOT = Path(
    r"C:\Users\skull\Documents\RuneScape\OpenNXT-mitm\data\debug\prelogin-producer-947"
)
DEFAULT_PRODUCER_RVA = 0x590220
DEFAULT_BUILDER_RVA = 0x590BC0
DEFAULT_BUILDER_MASTER_LOOKUP_RVA = 0x590C58
DEFAULT_BUILDER_POST_GATE_RVA = 0x590DE8
DEFAULT_FALLBACK_RVA = 0x591A00
DEFAULT_INDEXED_TABLE_SLOT_OFFSET = 0x30D0
DEFAULT_RECORD_STRIDE = 0x108


def archive_output_path(root: Path, when: datetime | None = None) -> Path:
    timestamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return root / f"947-prelogin-producer-{timestamp}.jsonl"


def archive_summary_path(root: Path, when: datetime | None = None) -> Path:
    timestamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return root / f"947-prelogin-producer-{timestamp}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trace the 947 pre-login producer path around 0x590220/0x590bc0/0x591a00."
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
        default=90.0,
        help="How long to keep the hooks attached",
    )
    parser.add_argument(
        "--producer-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_PRODUCER_RVA,
        help="Outer producer RVA (default: 0x590220)",
    )
    parser.add_argument(
        "--builder-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_BUILDER_RVA,
        help="Primary builder RVA (default: 0x590bc0)",
    )
    parser.add_argument(
        "--builder-master-lookup-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_BUILDER_MASTER_LOOKUP_RVA,
        help="Archive=-1 master-table lookup RVA (default: 0x590c58)",
    )
    parser.add_argument(
        "--builder-post-gate-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_BUILDER_POST_GATE_RVA,
        help="Post-builder readiness gate RVA (default: 0x590de8)",
    )
    parser.add_argument(
        "--fallback-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_FALLBACK_RVA,
        help="Fallback path RVA (default: 0x591a00)",
    )
    parser.add_argument(
        "--indexed-table-slot-offset",
        type=lambda value: int(value, 0),
        default=DEFAULT_INDEXED_TABLE_SLOT_OFFSET,
        help="Owner offset of the indexed table pointer (default: 0x30d0)",
    )
    parser.add_argument(
        "--record-stride",
        type=lambda value: int(value, 0),
        default=DEFAULT_RECORD_STRIDE,
        help="Producer record stride (default: 0x108)",
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
    producer_rva: int,
    builder_rva: int,
    builder_master_lookup_rva: int,
    builder_post_gate_rva: int,
    fallback_rva: int,
    indexed_table_slot_offset: int,
    record_stride: int,
) -> str:
    return (
        r"""
const moduleBase = Process.enumerateModules()[0].base;
const producerAddress = moduleBase.add(__PRODUCER_RVA__);
const builderAddress = moduleBase.add(__BUILDER_RVA__);
const builderMasterLookupAddress = moduleBase.add(__BUILDER_MASTER_LOOKUP_RVA__);
const builderPostGateAddress = moduleBase.add(__BUILDER_POST_GATE_RVA__);
const fallbackAddress = moduleBase.add(__FALLBACK_RVA__);
const indexedTableSlotOffset = __INDEXED_TABLE_SLOT_OFFSET__;
const recordStride = __RECORD_STRIDE__;
const eventCounts = {};
const uniqueCounts = {};

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
  try {
    return ptr(address).readPointer();
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

function safeReadS32(address) {
  try {
    return ptr(address).readS32();
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

function safeReadU64(address) {
  try {
    return ptr(address).readU64().toString();
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

function summarizeTable(tablePointer) {
  if (tablePointer === null) {
    return {
      pointer: null,
      count: null,
      entriesPointer: null
    };
  }
  const entriesPointer = safeReadPointer(ptr(tablePointer).add(0x18));
  return {
    pointer: hexPtr(tablePointer),
    header0: safeReadU32(tablePointer),
    refCount: safeReadU64(ptr(tablePointer).add(0x8)),
    count: safeReadU64(ptr(tablePointer).add(0x10)),
    entriesPointer: hexPtr(entriesPointer)
  };
}

function summarizeOwner(owner) {
  const tablePointer = safeReadPointer(ptr(owner).add(indexedTableSlotOffset));
  return {
    owner: hexPtr(owner),
    flag70: safeReadU8(ptr(owner).add(0x70)),
    flag10140: safeReadU8(ptr(owner).add(0x10140)),
    ptr90: hexPtr(safeReadPointer(ptr(owner).add(0x90))),
    table30d0: summarizeTable(tablePointer)
  };
}

function summarizeRecord(owner, resourceIndex) {
  if (resourceIndex === null || resourceIndex < 0) {
    return null;
  }
  const record = ptr(owner).add(resourceIndex * recordStride);
  return {
    pointer: hexPtr(record),
    field31f8: safeReadU32(record.add(0x31f8)),
    flag321c: safeReadU8(record.add(0x321c)),
    field3218: safeReadU32(record.add(0x3218)),
    field327c: safeReadU32(record.add(0x327c)),
    count3290: safeReadU64(record.add(0x3290)),
    ptr3298: hexPtr(safeReadPointer(record.add(0x3298))),
    count32c0: safeReadU64(record.add(0x32c0)),
    ptr32c8: hexPtr(safeReadPointer(record.add(0x32c8))),
    field7710: safeReadU32(record.add(0x7710)),
    field7730: safeReadU32(record.add(0x7730)),
    flag7734: safeReadU8(record.add(0x7734)),
    count77a8: safeReadU64(record.add(0x77a8)),
    ptr77b0: hexPtr(safeReadPointer(record.add(0x77b0))),
    count77d8: safeReadU64(record.add(0x77d8)),
    ptr77e0: hexPtr(safeReadPointer(record.add(0x77e0)))
  };
}

function summarizePathBase(pathBase, recordBase) {
  if (pathBase === null || recordBase === null) {
    return null;
  }
  try {
    return {
      pathBase: hexPtr(pathBase),
      recordBase: hexPtr(recordBase),
      offsetFromRecord: '0x' + ptr(pathBase).sub(ptr(recordBase)).toString(16),
      flag24: safeReadU8(pathBase.add(0x24)),
      field0: safeReadU32(pathBase),
      field20: safeReadU32(pathBase.add(0x20)),
      count98: safeReadU64(pathBase.add(0x98)),
      ptrA0: hexPtr(safeReadPointer(pathBase.add(0xa0))),
      countC8: safeReadU64(pathBase.add(0xc8)),
      ptrD0: hexPtr(safeReadPointer(pathBase.add(0xd0)))
    };
  } catch (_error) {
    return {
      pathBase: hexPtr(pathBase),
      recordBase: hexPtr(recordBase),
      offsetFromRecord: null
    };
  }
}

function sendMaybeUnique(eventName, payload) {
  const count = (eventCounts[eventName] || 0) + 1;
  eventCounts[eventName] = count;
  const uniqueKey = eventName + '|' + JSON.stringify(payload);
  const uniqueCount = (uniqueCounts[uniqueKey] || 0) + 1;
  uniqueCounts[uniqueKey] = uniqueCount;
  if (uniqueCount <= 5 || (uniqueCount % 25) === 0) {
    send(Object.assign({
      event: eventName,
      eventCount: count,
      uniqueCount: uniqueCount
    }, payload));
  }
}

rpc.exports = {
  snapshot() {
    return {
      moduleBase: hexPtr(moduleBase),
      producerAddress: hexPtr(producerAddress),
      builderAddress: hexPtr(builderAddress),
      builderMasterLookupAddress: hexPtr(builderMasterLookupAddress),
      builderPostGateAddress: hexPtr(builderPostGateAddress),
      fallbackAddress: hexPtr(fallbackAddress),
      indexedTableSlotOffset: indexedTableSlotOffset,
      recordStride: recordStride,
      eventCounts: eventCounts,
      uniqueKeyCount: Object.keys(uniqueCounts).length
    };
  }
};

send({
  event: 'producer-script-loaded',
  moduleBase: hexPtr(moduleBase),
  producerAddress: hexPtr(producerAddress),
  builderAddress: hexPtr(builderAddress),
  builderMasterLookupAddress: hexPtr(builderMasterLookupAddress),
  builderPostGateAddress: hexPtr(builderPostGateAddress),
  fallbackAddress: hexPtr(fallbackAddress),
  indexedTableSlotOffset: indexedTableSlotOffset,
  recordStride: recordStride
});

Interceptor.attach(producerAddress, {
  onEnter(args) {
    this.owner = args[0];
    this.item = args[1];
    this.archive = args[2].toInt32();
    this.phase = args[3].toInt32() & 0xff;
    this.resourceIndex = safeReadS32(this.item);
    this.outFlagPointer = safeReadPointer(this.context.rsp.add(0x28));
    this.returnAddressRva = callsiteRvaText(this.returnAddress);
  },
  onLeave(retval) {
    sendMaybeUnique('producer-call-unique', {
      callerRva: this.returnAddressRva,
      resourceIndex: this.resourceIndex,
      archive: this.archive,
      phase: this.phase,
      retval: hexPtr(retval),
      outFlagPointer: hexPtr(this.outFlagPointer),
      outFlagValue: this.outFlagPointer === null ? null : safeReadU8(this.outFlagPointer),
      owner: summarizeOwner(this.owner),
      record: summarizeRecord(this.owner, this.resourceIndex)
    });
  }
});

Interceptor.attach(builderAddress, {
  onEnter(args) {
    this.owner = args[0];
    this.item = args[1];
    this.archive = args[2].toInt32();
    this.phase = args[3].toInt32() & 0xff;
    this.resourceIndex = safeReadS32(this.item);
    this.returnAddressRva = callsiteRvaText(this.returnAddress);
  },
  onLeave(retval) {
    sendMaybeUnique('producer-builder-leave-unique', {
      callerRva: this.returnAddressRva,
      resourceIndex: this.resourceIndex,
      archive: this.archive,
      phase: this.phase,
      returnBool: retval.toInt32() & 0xff,
      owner: summarizeOwner(this.owner),
      record: summarizeRecord(this.owner, this.resourceIndex)
    });
  }
});

Interceptor.attach(builderMasterLookupAddress, {
  onEnter(args) {
    sendMaybeUnique('producer-builder-master-lookup-unique', {
      resourceIndex: this.context.r10.toInt32(),
      owner: summarizeOwner(this.context.rcx)
    });
  }
});

Interceptor.attach(builderPostGateAddress, {
  onEnter(args) {
    const recordBase = this.context.r15;
    sendMaybeUnique('producer-builder-post-gate-unique', {
      resourceIndex: this.context.r10.toInt32(),
      archive: this.context.rbx.toInt32(),
      owner: summarizeOwner(this.context.r14),
      record: summarizeRecord(this.context.r14, this.context.r10.toInt32()),
      gateFlag7734: safeReadU8(recordBase.add(0x7734)),
      gateCount77d8: safeReadU64(recordBase.add(0x77d8)),
      pathBase: summarizePathBase(this.context.rdi, recordBase)
    });
  }
});

Interceptor.attach(fallbackAddress, {
  onEnter(args) {
    this.owner = args[0];
    this.item = args[1];
    this.archive = args[2].toInt32();
    this.phase = args[3].toInt32() & 0xff;
    this.resourceIndex = safeReadS32(this.item);
    this.returnAddressRva = callsiteRvaText(this.returnAddress);
  },
  onLeave(retval) {
    sendMaybeUnique('producer-fallback-leave-unique', {
      callerRva: this.returnAddressRva,
      resourceIndex: this.resourceIndex,
      archive: this.archive,
      phase: this.phase,
      retval: hexPtr(retval),
      owner: summarizeOwner(this.owner)
    });
  }
});
"""
        .replace("__PRODUCER_RVA__", hex(producer_rva))
        .replace("__BUILDER_RVA__", hex(builder_rva))
        .replace("__BUILDER_MASTER_LOOKUP_RVA__", hex(builder_master_lookup_rva))
        .replace("__BUILDER_POST_GATE_RVA__", hex(builder_post_gate_rva))
        .replace("__FALLBACK_RVA__", hex(fallback_rva))
        .replace("__INDEXED_TABLE_SLOT_OFFSET__", hex(indexed_table_slot_offset))
        .replace("__RECORD_STRIDE__", hex(record_stride))
    )


def build_summary(output_path: Path, *, pid: int) -> dict[str, object]:
    event_counts: Counter[str] = Counter()
    latest_by_event: dict[str, dict] = {}
    if output_path.exists():
        for line in output_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            event = payload.get("event")
            if not isinstance(event, str):
                continue
            event_counts[event] += 1
            latest_by_event[event] = payload
    return {
        "pid": pid,
        "eventCounts": dict(event_counts),
        "latestByEvent": latest_by_event,
    }


def main() -> int:
    args = parse_args()
    pid = resolve_pid(args)

    args.output_root.mkdir(parents=True, exist_ok=True)
    output_path = archive_output_path(args.output_root)
    summary_path = archive_summary_path(args.output_root)
    latest_jsonl_path = args.output_root / "latest-client-only.jsonl"
    latest_summary_path = args.output_root / "latest-client-only.json"

    session = frida.attach(pid)
    script = session.create_script(
        build_script(
            producer_rva=args.producer_rva,
            builder_rva=args.builder_rva,
            builder_master_lookup_rva=args.builder_master_lookup_rva,
            builder_post_gate_rva=args.builder_post_gate_rva,
            fallback_rva=args.fallback_rva,
            indexed_table_slot_offset=args.indexed_table_slot_offset,
            record_stride=args.record_stride,
        )
    )

    with output_path.open("w", encoding="utf-8") as handle:
        def on_message(message: dict, data: bytes | None) -> None:
            if message.get("type") != "send":
                return
            payload = message.get("payload")
            if not isinstance(payload, dict):
                return
            payload.setdefault("timestamp", time.time())
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
            handle.flush()

        script.on("message", on_message)
        script.load()
        time.sleep(args.duration_seconds)
        session.detach()

    latest_jsonl_path.write_text(output_path.read_text(encoding="utf-8"), encoding="utf-8")
    summary = build_summary(output_path, pid=pid)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    latest_summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "pid": pid,
                "outputPath": str(output_path),
                "summaryPath": str(summary_path),
                "latestJsonlPath": str(latest_jsonl_path),
                "latestSummaryPath": str(latest_summary_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
