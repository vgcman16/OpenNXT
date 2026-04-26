from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import frida


DEFAULT_OUTPUT_ROOT = Path(
    r"C:\Users\skull\Documents\RuneScape\OpenNXT-mitm\data\debug\table-lifecycle-947"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trace 947 client 0x30d0 table lifecycle hooks with Frida.")
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
        default=60.0,
        help="How long to keep the hooks attached",
    )
    parser.add_argument(
        "--null-source-vector",
        action="store_true",
        help="Force 0x59bd00 to take its null-source/raw-copy path by zeroing param_2 and param_3",
    )
    parser.add_argument(
        "--force-length-gate-0x41",
        action="store_true",
        help="Force the 0x59c1ea gate to treat the builder blob length as 0x41",
    )
    parser.add_argument(
        "--skip-compare-failure",
        action="store_true",
        help="Redirect the 0x59c64f compare-failure path to the compare-success continuation",
    )
    parser.add_argument(
        "--mirror-compare-left-into-right",
        action="store_true",
        help="Overwrite the client-side 65-byte compare buffer so the 64-byte validation compare passes naturally",
    )
    parser.add_argument(
        "--inject-null-master-table",
        action="store_true",
        help="When FUN_140590bc0 sees owner+0x30d0 == null for archive=-1, synthesize a minimal table object",
    )
    parser.add_argument(
        "--inject-null-master-table-count",
        type=int,
        default=67,
        help="Entry count for --inject-null-master-table (default: 67 for build 947)",
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


def build_script(
    *,
    null_source_vector: bool,
    force_length_gate_0x41: bool,
    skip_compare_failure: bool,
    mirror_compare_left_into_right: bool,
    inject_null_master_table: bool,
    inject_null_master_table_count: int,
) -> str:
    null_source_vector_js = "true" if null_source_vector else "false"
    force_length_gate_js = "true" if force_length_gate_0x41 else "false"
    skip_compare_failure_js = "true" if skip_compare_failure else "false"
    mirror_compare_js = "true" if mirror_compare_left_into_right else "false"
    inject_null_master_table_js = "true" if inject_null_master_table else "false"
    return (
        r"""
const moduleBase = Process.enumerateModules()[0].base;
const NULL_SOURCE_VECTOR = __NULL_SOURCE_VECTOR__;
const FORCE_LENGTH_GATE_0X41 = __FORCE_LENGTH_GATE_0X41__;
const SKIP_COMPARE_FAILURE = __SKIP_COMPARE_FAILURE__;
const MIRROR_COMPARE_LEFT_INTO_RIGHT = __MIRROR_COMPARE_LEFT_INTO_RIGHT__;
const INJECT_NULL_MASTER_TABLE = __INJECT_NULL_MASTER_TABLE__;
const INJECT_NULL_MASTER_TABLE_COUNT = __INJECT_NULL_MASTER_TABLE_COUNT__;
const mirroredCompareThreads = {};
const injectedMasterTables = {};

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

function safeReadByteArrayHex(address, length) {
  try {
    const bytes = ptr(address).readByteArray(length);
    if (bytes === null) {
      return null;
    }
    const view = new Uint8Array(bytes);
    return Array.from(view).map((value) => ('0' + value.toString(16)).slice(-2)).join('');
  } catch (_error) {
    return null;
  }
}

function safeCopyBytes(source, destination, length) {
  try {
    const bytes = ptr(source).readByteArray(length);
    if (bytes === null) {
      return false;
    }
    ptr(destination).writeByteArray(bytes);
    return true;
  } catch (_error) {
    return false;
  }
}

function safeReadU8(address) {
  try {
    return ptr(address).readU8();
  } catch (_error) {
    return null;
  }
}

function pointerDifference(endPtr, startPtr) {
  try {
    return ptr(endPtr).sub(ptr(startPtr)).toString();
  } catch (_error) {
    return null;
  }
}

function readPointerVector(address, count) {
  const values = [];
  try {
    const base = ptr(address);
    for (let index = 0; index < count; index += 1) {
      values.push(hexPtr(base.add(index * Process.pointerSize).readPointer()));
    }
  } catch (_error) {}
  return values;
}

function dumpTable(tablePtr) {
  if (tablePtr === null) {
    return null;
  }
  const table = ptr(tablePtr);
  const entriesPtr = safeReadPointer(table.add(0x18));
  return {
    pointer: hexPtr(table),
    header0: safeReadU32(table),
    refCount: safeReadU64(table.add(0x8)),
    count: safeReadU64(table.add(0x10)),
    entriesPointer: hexPtr(entriesPtr),
  };
}

function ensureInjectedMasterTable(ownerPtr, entryCount) {
  try {
    const owner = ptr(ownerPtr);
    const ownerKey = owner.toString();
    if (injectedMasterTables[ownerKey]) {
      owner.add(0x30d0).writePointer(injectedMasterTables[ownerKey].table);
      return injectedMasterTables[ownerKey].table;
    }

    const normalizedCount = Math.max(1, entryCount >>> 0);
    const table = Memory.alloc(0x20);
    const entries = Memory.alloc(normalizedCount * Process.pointerSize);
    const entryPointers = [];

    table.writeU32(0);
    table.add(4).writeU32(0);
    table.add(8).writeU64(0);
    table.add(0x10).writeU64(normalizedCount);
    table.add(0x18).writePointer(entries);

    for (let index = 0; index < normalizedCount; index += 1) {
      const entry = Memory.alloc(8);
      entry.writeS32(-1);
      entry.add(4).writeS32(-1);
      entries.add(index * Process.pointerSize).writePointer(entry);
      entryPointers.push(entry);
    }

    owner.add(0x30d0).writePointer(table);
    injectedMasterTables[ownerKey] = {
      table,
      entries,
      entryPointers,
      count: normalizedCount,
    };
    return table;
  } catch (_error) {
    return null;
  }
}

function sendEvent(payload) {
  payload.timestamp = Date.now() / 1000.0;
  send(payload);
}

function hookRva(rva, callbacks) {
  Interceptor.attach(moduleBase.add(rva), callbacks);
}

hookRva(0x590bc0, {
  onEnter(args) {
    const owner = args[0];
    const requestHeader = args[1];
    const archiveId = args[2];
    const existingTable = safeReadPointer(ptr(owner).add(0x30d0));
    let injectedTable = null;
    if (
      INJECT_NULL_MASTER_TABLE &&
      ptr(archiveId).toUInt32() === 0xffffffff &&
      (existingTable === null || ptr(existingTable).isNull())
    ) {
      injectedTable = ensureInjectedMasterTable(owner, INJECT_NULL_MASTER_TABLE_COUNT);
    }
    sendEvent({
      event: "master-table-consumer-enter",
      functionRva: "0x590bc0",
      owner: hexPtr(owner),
      requestHeader: hexPtr(requestHeader),
      archiveId: ptr(archiveId).toUInt32(),
      tableBefore: dumpTable(existingTable),
      injectedTable: dumpTable(injectedTable),
      injectNullMasterTable: INJECT_NULL_MASTER_TABLE,
      injectNullMasterTableCount: INJECT_NULL_MASTER_TABLE_COUNT,
    });
  }
});

hookRva(0x59bd00, {
  onEnter(args) {
    mirroredCompareThreads[Process.getCurrentThreadId()] = false;
    this.allocatedTable = args[0];
    this.sourcePtr = args[1];
    this.sourceEnd = args[2];
    this.stackView = args[3];
    if (NULL_SOURCE_VECTOR) {
      args[1] = ptr(0);
      args[2] = ptr(0);
    }
    this.firstSourceEntry = safeReadPointer(this.sourcePtr);
    sendEvent({
      event: "table-builder-enter",
      functionRva: "0x59bd00",
      allocatedTable: hexPtr(this.allocatedTable),
      sourcePtr: hexPtr(this.sourcePtr),
      sourceEnd: hexPtr(this.sourceEnd),
      sourceSpanBytes: pointerDifference(this.sourceEnd, this.sourcePtr),
      stackView: hexPtr(this.stackView),
      sourceVectorPreview: readPointerVector(this.sourcePtr, 4),
      firstSourceEntry: hexPtr(this.firstSourceEntry),
      firstSourceEntryPreviewHex: safeReadByteArrayHex(this.firstSourceEntry, 96),
      sourceVectorForcedNull: NULL_SOURCE_VECTOR,
    });
  },
  onLeave(retval) {
    delete mirroredCompareThreads[Process.getCurrentThreadId()];
    sendEvent({
      event: "table-builder-leave",
      functionRva: "0x59bd00",
      allocatedTable: hexPtr(this.allocatedTable),
      returnValue: hexPtr(retval),
      table: dumpTable(retval),
    });
  }
});

hookRva(0x59c1ea, {
  onEnter(args) {
    const rbp = this.context.rbp;
    const rsp = this.context.rsp;
    if (FORCE_LENGTH_GATE_0X41) {
      this.context.r14 = ptr(0x41);
      try {
        ptr(rsp).add(0x38).writeU64(0x41);
      } catch (_error) {}
    }
    sendEvent({
      event: "table-builder-length-gate",
      functionRva: "0x59c1ea",
      localLength: FORCE_LENGTH_GATE_0X41 ? "65-forced" : safeReadU64(rsp.add(0x38)),
      localBufferPointer: hexPtr(safeReadPointer(rsp.add(0x58))),
      rawBufferPointer: hexPtr(safeReadPointer(rsp.add(0x20))),
      rawBufferLength: safeReadU64(rsp.add(0x28)),
      expectedEntryCount: safeReadU32(rbp.add(0xc8)),
      tableHeader0: safeReadU32(safeReadPointer(rsp.add(0x8))),
      allocatedTable: hexPtr(safeReadPointer(rsp.add(0x8))),
      forceLengthGate0x41: FORCE_LENGTH_GATE_0X41,
    });
  }
});

hookRva(0x59c21b, {
  onEnter(args) {
    const rbp = this.context.rbp;
    const rsp = this.context.rsp;
    sendEvent({
      event: "table-builder-length-gate-passed",
      functionRva: "0x59c21b",
      localLength: safeReadU64(rsp.add(0x38)),
      compareLeft: hexPtr(this.context.r15),
      compareRight: hexPtr(this.context.rbx),
      expectedEntryCount: safeReadU32(rbp.add(0xc8)),
    });
  }
});

hookRva(0x59c2be, {
  onEnter(args) {
    const rbp = this.context.rbp;
    sendEvent({
      event: "table-builder-compare-passed",
      functionRva: "0x59c2be",
      expectedEntryCount: safeReadU32(rbp.add(0xc8)),
      table: dumpTable(this.context.rsi),
    });
  }
});

hookRva(0x59c2a0, {
  onEnter(args) {
    if (!MIRROR_COMPARE_LEFT_INTO_RIGHT) {
      return;
    }
    const threadId = Process.getCurrentThreadId();
    if (mirroredCompareThreads[threadId]) {
      return;
    }
    const left = this.context.rcx;
    const right = this.context.rbx;
    const copied = safeCopyBytes(left, ptr(right).add(1), 64);
    mirroredCompareThreads[threadId] = copied;
    sendEvent({
      event: "table-builder-compare-buffer-mirrored",
      functionRva: "0x59c2a0",
      compareLeft: hexPtr(left),
      compareRight: hexPtr(right),
      copied,
      mirrorCompareLeftIntoRight: MIRROR_COMPARE_LEFT_INTO_RIGHT,
      leftPreviewHex: safeReadByteArrayHex(left, 64),
      rightPreviewHex: safeReadByteArrayHex(right, 65),
    });
  }
});

hookRva(0x59c322, {
  onEnter(args) {
    sendEvent({
      event: "table-builder-entry-array-ensure",
      functionRva: "0x59c322",
      requestedCount: safeReadU64(this.context.rdi),
      existingTable: dumpTable(this.context.rbx),
    });
  }
});

hookRva(0x59c373, {
  onEnter(args) {
    const rbp = this.context.rbp;
    sendEvent({
      event: "table-builder-populate-loop-enter",
      functionRva: "0x59c373",
      expectedEntryCount: safeReadU32(rbp.add(0xc8)),
      table: dumpTable(this.context.rsi),
    });
  }
});

hookRva(0x59c64f, {
  onEnter(args) {
    const left = this.context.r15;
    const right = this.context.rbx;
    if (SKIP_COMPARE_FAILURE) {
      this.context.rip = moduleBase.add(0x59c2be);
    }
    sendEvent({
      event: "table-builder-compare-failed",
      functionRva: "0x59c64f",
      compareLeft: hexPtr(left),
      compareRight: hexPtr(right),
      leftPreviewHex: safeReadByteArrayHex(left, 64),
      rightPreviewHex: safeReadByteArrayHex(right, 65),
      firstLeftByte: safeReadU8(left),
      firstRightByte: safeReadU8(right),
      skipCompareFailure: SKIP_COMPARE_FAILURE,
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
      source60: hexPtr(safeReadPointer(ptr(this.owner).add(0x60))),
      source68: hexPtr(safeReadPointer(ptr(this.owner).add(0x68))),
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
      object48: hexPtr(safeReadPointer(ptr(owner).add(0x48))),
      object88: hexPtr(safeReadPointer(ptr(owner).add(0x88))),
    });
  }
});
"""
    ).replace("__NULL_SOURCE_VECTOR__", null_source_vector_js).replace(
        "__FORCE_LENGTH_GATE_0X41__", force_length_gate_js
    ).replace("__SKIP_COMPARE_FAILURE__", skip_compare_failure_js).replace(
        "__MIRROR_COMPARE_LEFT_INTO_RIGHT__", mirror_compare_js
    ).replace("__INJECT_NULL_MASTER_TABLE__", inject_null_master_table_js).replace(
        "__INJECT_NULL_MASTER_TABLE_COUNT__", str(inject_null_master_table_count)
    )


def main() -> int:
    args = parse_args()
    pid = resolve_pid(args)
    args.output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive_path = args.output_root / f"trace-{timestamp}-pid{pid}.jsonl"
    latest_path = args.output_root / "latest-client-only.jsonl"

    device = frida.get_local_device()
    session = device.attach(pid)
    script = session.create_script(
        build_script(
            null_source_vector=args.null_source_vector,
            force_length_gate_0x41=args.force_length_gate_0x41,
            skip_compare_failure=args.skip_compare_failure,
            mirror_compare_left_into_right=args.mirror_compare_left_into_right,
            inject_null_master_table=args.inject_null_master_table,
            inject_null_master_table_count=args.inject_null_master_table_count,
        )
    )

    def on_message(message: dict, _data: bytes | None) -> None:
        with archive_path.open("a", encoding="utf-8") as handle:
            if message.get("type") != "send":
                handle.write(json.dumps(message) + "\n")
                return
            payload = message.get("payload")
            handle.write(json.dumps(payload) + "\n")

    if archive_path.exists():
        archive_path.unlink()
    script.on("message", on_message)
    script.load()
    try:
        time.sleep(args.duration_seconds)
    finally:
        try:
            script.unload()
        except frida.InvalidOperationError:
            pass
        session.detach()
    latest_path.write_text(archive_path.read_text(encoding="utf-8") if archive_path.exists() else "", encoding="utf-8")
    print(json.dumps({"pid": pid, "archivePath": str(archive_path), "latestPath": str(latest_path)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
