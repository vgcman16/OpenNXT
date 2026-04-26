from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import frida


DEFAULT_OUTPUT_ROOT = Path(
    r"C:\Users\skull\Documents\RuneScape\OpenNXT-mitm\data\debug\application-resource-bridge-947"
)
DEFAULT_BRIDGE_SCAN_RVA = 0x5963CF
DEFAULT_DISPATCH_RVA = 0x595530
DEFAULT_SEED_DISPATCH_RVA = 0x597230
DEFAULT_RECORD_STATE_RVA = 0x597D10
DEFAULT_RECORD_FINALIZE_RVA = 0x597FD0
DEFAULT_STATE1_WRITE_RVA = 0x590B96
DEFAULT_STATE2_WRITE_RVA = 0x5954C1
DEFAULT_STATE34_WRITE_RVA = 0x597C73
DEFAULT_SCHEDULER_GLOBAL_RVA = 0xE57B60


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trace the 947 application-resource loop-state bridge and state writers with Frida."
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
        "--bridge-scan-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_BRIDGE_SCAN_RVA,
        help="Loop-state bridge scan RVA (default: 0x5963CF)",
    )
    parser.add_argument(
        "--dispatch-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_DISPATCH_RVA,
        help="Direct-dispatch function RVA (default: 0x595530)",
    )
    parser.add_argument(
        "--seed-dispatch-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_SEED_DISPATCH_RVA,
        help="Seed-dispatch function RVA (default: 0x597230)",
    )
    parser.add_argument(
        "--record-state-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RECORD_STATE_RVA,
        help="Type-1 record-state handler RVA (default: 0x597d10)",
    )
    parser.add_argument(
        "--record-finalize-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RECORD_FINALIZE_RVA,
        help="Record finalize handler RVA (default: 0x597fd0)",
    )
    parser.add_argument(
        "--state1-write-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_STATE1_WRITE_RVA,
        help="Loop-state write-to-1 RVA (default: 0x590B96)",
    )
    parser.add_argument(
        "--state2-write-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_STATE2_WRITE_RVA,
        help="Loop-state write-to-2 RVA (default: 0x5954C1)",
    )
    parser.add_argument(
        "--state34-write-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_STATE34_WRITE_RVA,
        help="Loop-state write-to-3/4 RVA (default: 0x597C73)",
    )
    parser.add_argument(
        "--scheduler-global-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_SCHEDULER_GLOBAL_RVA,
        help="Global qword compared against owner+0x11b38 inside the dispatch path",
    )
    parser.add_argument(
        "--force-state1-on-ptr178",
        action="store_true",
        help="One-shot smoke test: write loop-state=1 for ptr178-backed records before the bridge scan reads them",
    )
    parser.add_argument(
        "--force-selector-ready-on-ptr178",
        action="store_true",
        help="Smoke test: satisfy the idle-selector progress gate for ptr178-backed state=1 records before the bridge scan",
    )
    parser.add_argument(
        "--force-owner-11d4a-open-on-special20",
        action="store_true",
        help="Smoke test: reopen owner+0x11d4a once a selected record reaches special20 but the bridge stays idle",
    )
    parser.add_argument(
        "--force-seed-dispatch-on-state1",
        action="store_true",
        help="Smoke test: directly invoke the native seed-dispatch helper for the selected ptr178-backed state=1 record",
    )
    parser.add_argument(
        "--force-recordstate-on-state1",
        action="store_true",
        help="Smoke test: directly invoke the native type-1 record-state handler for ptr178-backed state=1 records lacking ptr1c8",
    )
    parser.add_argument(
        "--force-direct-dispatch-on-state1",
        action="store_true",
        help="Smoke test: directly invoke the native dispatch path for ptr1c8-backed state=1 records when the owner stays idle",
    )
    parser.add_argument(
        "--force-finalize-on-state1",
        action="store_true",
        help="Smoke test: directly invoke the native finalize path for the selected ptr178-backed state=1 record when field170 is still 0",
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
    bridge_scan_rva: int,
    dispatch_rva: int,
    seed_dispatch_rva: int,
    record_state_rva: int,
    record_finalize_rva: int,
    state1_write_rva: int,
    state2_write_rva: int,
    state34_write_rva: int,
    scheduler_global_rva: int,
    force_state1_on_ptr178: bool,
    force_selector_ready_on_ptr178: bool,
    force_owner_11d4a_open_on_special20: bool,
    force_seed_dispatch_on_state1: bool,
    force_recordstate_on_state1: bool,
    force_direct_dispatch_on_state1: bool,
    force_finalize_on_state1: bool,
) -> str:
    return (
        r"""
const moduleBase = Process.enumerateModules()[0].base;
const bridgeScanAddress = moduleBase.add(__BRIDGE_SCAN_RVA__);
const dispatchAddress = moduleBase.add(__DISPATCH_RVA__);
const seedDispatchAddress = moduleBase.add(__SEED_DISPATCH_RVA__);
const recordStateAddress = moduleBase.add(__RECORD_STATE_RVA__);
const recordFinalizeAddress = moduleBase.add(__RECORD_FINALIZE_RVA__);
const state1WriteAddress = moduleBase.add(__STATE1_WRITE_RVA__);
const state2WriteAddress = moduleBase.add(__STATE2_WRITE_RVA__);
const state34WriteAddress = moduleBase.add(__STATE34_WRITE_RVA__);
const schedulerGlobalAddress = moduleBase.add(__SCHEDULER_GLOBAL_RVA__);
const RESOURCE_COUNT = 67;
const directDispatch = new NativeFunction(dispatchAddress, 'void', ['pointer', 'int']);
const seedDispatch = new NativeFunction(seedDispatchAddress, 'void', ['pointer', 'int']);
const recordState = new NativeFunction(recordStateAddress, 'void', ['pointer', 'pointer']);
const recordFinalize = new NativeFunction(recordFinalizeAddress, 'void', ['pointer', 'pointer']);

const bridgeCounts = {};
const seedDispatchCounts = {};
const stateWriteCounts = {};
const latest = {
  bridgeScan: null,
  seedDispatch: null,
  stateWrite: null
};
let bridgeHits = 0;
let seedDispatchHits = 0;
let stateWriteHits = 0;
let latestBridgeKey = null;
let totalForcedState1Promotions = 0;
let totalForcedSelectorReadyPromotions = 0;
let totalForcedOwner11d4aOpen = 0;
let totalForcedSeedDispatches = 0;
let totalForcedRecordStateDispatches = 0;
let totalForcedDirectDispatches = 0;
let totalForcedFinalizeDispatches = 0;
let state1ForceInProgress = false;
let selectorReadyForceInProgress = false;
let owner11d4aForceInProgress = false;
let seedDispatchForceInProgress = false;
let recordStateForceInProgress = false;
let directDispatchForceInProgress = false;
let finalizeForceInProgress = false;
const forcedState1Indices = {};
const forcedSelectorReadyIndices = {};
const forcedSeedDispatchIndices = {};
const forcedRecordStateIndices = {};
const forcedDirectDispatchIndices = {};
const forcedFinalizeIndices = {};

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
  const selectorEligibleIndices = [];
  const selectorPtr178Details = [];
  const selectorReasonCounts = {
    ptr178Missing: 0,
    busy: 0,
    totalZero: 0,
    doneZero: 0,
    pctBelow5: 0,
    eligible: 0
  };

  for (let index = 0; index < RESOURCE_COUNT; index += 1) {
    const record = ptr(owner).add(8 + (index * 0x1d8));
    const flagD = safeReadU8(record.add(0x0d));
    const flagE = safeReadU8(record.add(0x0e));
    const flag20 = safeReadU8(record.add(0x20));
    const flag21 = safeReadU8(record.add(0x21));
    const field1c = safeReadS32(record.add(0x1c));
    const total164 = safeReadU32(record.add(0x164));
    const done168 = safeReadU32(record.add(0x168));
    const busy16c = safeReadU8(record.add(0x16c));
    const field170 = safeReadU32(record.add(0x170));
    const ptr178 = hexPtr(safeReadPointer(record.add(0x178)));
    const ptr180 = hexPtr(safeReadPointer(record.add(0x180)));
    const ptr188 = hexPtr(safeReadPointer(record.add(0x188)));
    const ptr1c8 = hexPtr(safeReadPointer(record.add(0x1c8)));
    const queued = safeReadU8(ptr(owner).add(0x11468 + index));
    const stateValue = safeReadU32(ptr(owner).add(0x119e4 + (index * 4)));
    const hasPtr178 = ptr178 && ptr178 !== "0x0";
    let selectorPct = null;
    if (total164 !== null && total164 !== 0 && done168 !== null) {
      selectorPct = Math.floor((done168 * 100) / total164);
    }

    let selectorReason = "eligible";
    if (!hasPtr178) {
      selectorReason = "ptr178Missing";
    } else if (busy16c !== 0) {
      selectorReason = "busy";
    } else if (total164 === null || total164 === 0) {
      selectorReason = "totalZero";
    } else if (done168 === null || done168 === 0) {
      selectorReason = "doneZero";
    } else if (selectorPct === null || selectorPct < 5) {
      selectorReason = "pctBelow5";
    }

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
    if (hasPtr178) {
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
    if (selectorReason === "eligible") {
      selectorEligibleIndices.push(index);
    }
    selectorReasonCounts[selectorReason] += 1;
    if (hasPtr178) {
      selectorPtr178Details.push({
        index: index,
        state: stateValue,
        total164: total164,
        done168: done168,
        pct: selectorPct,
        busy16c: busy16c,
        field170: field170,
        flagD: flagD,
        flagE: flagE,
        ptr180: ptr180,
        ptr188: ptr188,
        ptr1c8: ptr1c8,
        queued: queued,
        selectorReason: selectorReason
      });
    }
  }

  return {
    owner: hexPtr(owner),
    flag11b48: safeReadU8(ptr(owner).add(0x11b48)),
    flag11d48: safeReadU8(ptr(owner).add(0x11d48)),
    flag11d49: safeReadU8(ptr(owner).add(0x11d49)),
    flag11d4a: safeReadU8(ptr(owner).add(0x11d4a)),
    flag11508: safeReadU8(ptr(owner).add(0x11508)),
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
    selectorEligibleCount: selectorEligibleIndices.length,
    selectorEligibleIndices: selectorEligibleIndices,
    selectorReasonCounts: selectorReasonCounts,
    selectorPtr178Details: selectorPtr178Details,
    queuedCount: queuedIndices.length,
    queuedIndices: queuedIndices,
    stateCount: stateIndices.length,
    stateIndices: stateIndices
  };
}

function countByKey(map, key) {
  if (!(key in map)) {
    map[key] = 0;
  }
  map[key] += 1;
}

function sendUniqueByKey(map, key, payload) {
  if (key in map) {
    return;
  }
  map[key] = 1;
  send(payload);
}

function allocateSyntheticRecordStateItem(index) {
  const item = Memory.alloc(0x30);
  item.writeS32(1);
  item.add(4).writeS32(index);
  item.add(8).writeS32(-1);
  item.add(0x0c).writeS32(-1);
  item.add(0x10).writeS32(-1);
  item.add(0x14).writeU8(0);
  item.add(0x15).writeU8(1);
  item.add(0x16).writeU8(0);
  item.add(0x17).writeU8(0);
  item.add(0x18).writeS32(1);
  item.add(0x1c).writeS32(403);
  item.add(0x20).writeU64(0);
  item.add(0x28).writeU64(0);
  return item;
}

function tryForceState1OnPtr178(owner, reason) {
  if (!__FORCE_STATE1_ON_PTR178__ || state1ForceInProgress) {
    return {
      forced: false
    };
  }
  const before = summarizeOwner(owner);
  const seededIndices = before && before.ptr178SetIndices ? before.ptr178SetIndices.slice() : [];
  const existingStateIndices = before && before.stateIndices ? before.stateIndices.map(item => item.index) : [];
  const promotableIndices = seededIndices.filter(index => !(index in forcedState1Indices) && existingStateIndices.indexOf(index) === -1);
  if (
    !before ||
    before.queuedCount !== 0 ||
    promotableIndices.length === 0
  ) {
    return {
      forced: false,
      before: before
    };
  }
  state1ForceInProgress = true;
  try {
    for (const index of promotableIndices) {
      ptr(owner).add(0x119e4 + (index * 4)).writeU32(1);
      forcedState1Indices[index] = true;
    }
    totalForcedState1Promotions += promotableIndices.length;
    const after = summarizeOwner(owner);
    const event = {
      event: "force-state1-on-ptr178",
      reason: reason,
      owner: after.owner,
      promotedIndices: promotableIndices,
      before: before,
      after: after,
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: true,
      before: before,
      after: after,
      promotedIndices: promotableIndices
    };
  } catch (_error) {
    const event = {
      event: "force-state1-on-ptr178-error",
      reason: reason,
      before: before,
      promotedIndices: promotableIndices,
      error: String(_error),
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: false,
      before: before,
      promotedIndices: promotableIndices,
      error: String(_error)
    };
  } finally {
    state1ForceInProgress = false;
  }
}

function tryForceSelectorReadyOnPtr178(owner, reason) {
  if (!__FORCE_SELECTOR_READY_ON_PTR178__ || selectorReadyForceInProgress) {
    return {
      forced: false
    };
  }
  const before = summarizeOwner(owner);
  const stateByIndex = {};
  if (before && before.stateIndices) {
    before.stateIndices.forEach(item => {
      stateByIndex[item.index] = item.state;
    });
  }
  const eligibleIndices = before && before.selectorEligibleIndices ? before.selectorEligibleIndices.slice() : [];
  const promotableIndices = before && before.ptr178SetIndices
    ? before.ptr178SetIndices.filter(index =>
        !(index in forcedSelectorReadyIndices) &&
        eligibleIndices.indexOf(index) === -1 &&
        stateByIndex[index] === 1
      )
    : [];
  if (
    !before ||
    before.queuedCount !== 0 ||
    promotableIndices.length === 0
  ) {
    return {
      forced: false,
      before: before
    };
  }
  selectorReadyForceInProgress = true;
  try {
    for (const index of promotableIndices) {
      const record = ptr(owner).add(8 + (index * 0x1d8));
      const total164 = safeReadU32(record.add(0x164));
      const done168 = safeReadU32(record.add(0x168));
      const effectiveTotal = (total164 === null || total164 === 0) ? 100 : total164;
      const requiredDone = Math.max(1, Math.ceil((effectiveTotal * 5) / 100));
      record.add(0x16c).writeU8(0);
      if (total164 === null || total164 === 0) {
        record.add(0x164).writeU32(effectiveTotal);
      }
      if (done168 === null || done168 < requiredDone) {
        record.add(0x168).writeU32(requiredDone);
      }
      forcedSelectorReadyIndices[index] = true;
    }
    totalForcedSelectorReadyPromotions += promotableIndices.length;
    const after = summarizeOwner(owner);
    const event = {
      event: "force-selector-ready-on-ptr178",
      reason: reason,
      owner: after.owner,
      promotedIndices: promotableIndices,
      before: before,
      after: after,
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: true,
      before: before,
      after: after,
      promotedIndices: promotableIndices
    };
  } catch (_error) {
    const event = {
      event: "force-selector-ready-on-ptr178-error",
      reason: reason,
      before: before,
      promotedIndices: promotableIndices,
      error: String(_error),
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: false,
      before: before,
      promotedIndices: promotableIndices,
      error: String(_error)
    };
  } finally {
    selectorReadyForceInProgress = false;
  }
}

function tryForceOwner11d4aOpenOnSpecial20(owner, reason) {
  if (!__FORCE_OWNER_11D4A_OPEN_ON_SPECIAL20__ || owner11d4aForceInProgress) {
    return {
      forced: false
    };
  }
  const before = summarizeOwner(owner);
  if (
    !before ||
    before.special20Count === 0 ||
    before.flag11d4a === 1
  ) {
    return {
      forced: false,
      before: before
    };
  }
  owner11d4aForceInProgress = true;
  try {
    ptr(owner).add(0x11d4a).writeU8(1);
    totalForcedOwner11d4aOpen += 1;
    const after = summarizeOwner(owner);
    const event = {
      event: "force-owner-11d4a-open-on-special20",
      reason: reason,
      owner: after.owner,
      before: before,
      after: after,
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: true,
      before: before,
      after: after
    };
  } catch (_error) {
    const event = {
      event: "force-owner-11d4a-open-on-special20-error",
      reason: reason,
      before: before,
      error: String(_error),
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: false,
      before: before,
      error: String(_error)
    };
  } finally {
    owner11d4aForceInProgress = false;
  }
}

function tryForceSeedDispatchOnState1(owner, reason) {
  if (!__FORCE_SEED_DISPATCH_ON_STATE1__ || seedDispatchForceInProgress) {
    return {
      forced: false
    };
  }
  const before = summarizeOwner(owner);
  const stateByIndex = {};
  if (before && before.stateIndices) {
    before.stateIndices.forEach(item => {
      stateByIndex[item.index] = item.state;
    });
  }
  const special20Indices = before && before.special20Indices ? before.special20Indices.slice() : [];
  const ptr178State1Indices = before && before.ptr178SetIndices
    ? before.ptr178SetIndices.filter(index => stateByIndex[index] === 1)
    : [];
  const preferredIndices = special20Indices.filter(index => ptr178State1Indices.indexOf(index) !== -1);
  const candidateIndices = (preferredIndices.length !== 0 ? preferredIndices : ptr178State1Indices)
    .filter(index => !(index in forcedSeedDispatchIndices));
  if (
    !before ||
    before.queuedCount !== 0 ||
    before.activeCount !== 0 ||
    before.inProgressCount !== 0 ||
    candidateIndices.length === 0
  ) {
    return {
      forced: false,
      before: before
    };
  }
  seedDispatchForceInProgress = true;
  try {
    const dispatchedIndices = [];
    for (const index of candidateIndices.slice(0, 1)) {
      seedDispatch(ptr(owner), index);
      forcedSeedDispatchIndices[index] = true;
      dispatchedIndices.push(index);
    }
    totalForcedSeedDispatches += dispatchedIndices.length;
    const after = summarizeOwner(owner);
    const event = {
      event: "force-seed-dispatch-on-state1",
      reason: reason,
      owner: after.owner,
      dispatchedIndices: dispatchedIndices,
      before: before,
      after: after,
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: true,
      before: before,
      after: after,
      dispatchedIndices: dispatchedIndices
    };
  } catch (_error) {
    const event = {
      event: "force-seed-dispatch-on-state1-error",
      reason: reason,
      before: before,
      candidateIndices: candidateIndices,
      error: String(_error),
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: false,
      before: before,
      candidateIndices: candidateIndices,
      error: String(_error)
    };
  } finally {
    seedDispatchForceInProgress = false;
  }
}

function tryForceRecordStateOnState1(owner, reason) {
  if (!__FORCE_RECORDSTATE_ON_STATE1__ || recordStateForceInProgress) {
    return {
      forced: false
    };
  }
  const before = summarizeOwner(owner);
  const ptr1c8Indices = before && before.ptr1c8SetIndices ? before.ptr1c8SetIndices.slice() : [];
  const stateByIndex = {};
  if (before && before.stateIndices) {
    before.stateIndices.forEach(item => {
      stateByIndex[item.index] = item.state;
    });
  }
  const promotableIndices = before && before.ptr178SetIndices
    ? before.ptr178SetIndices.filter(index =>
        !(index in forcedRecordStateIndices) &&
        ptr1c8Indices.indexOf(index) === -1 &&
        stateByIndex[index] === 1
      )
    : [];
  if (
    !before ||
    before.queuedCount !== 0 ||
    promotableIndices.length === 0
  ) {
    return {
      forced: false,
      before: before
    };
  }
  recordStateForceInProgress = true;
  try {
    const dispatchedIndices = [];
    for (const index of promotableIndices.slice(0, 1)) {
      const item = allocateSyntheticRecordStateItem(index);
      recordState(ptr(owner), item);
      forcedRecordStateIndices[index] = true;
      dispatchedIndices.push(index);
    }
    totalForcedRecordStateDispatches += dispatchedIndices.length;
    const after = summarizeOwner(owner);
    const event = {
      event: "force-recordstate-on-state1",
      reason: reason,
      owner: after.owner,
      dispatchedIndices: dispatchedIndices,
      before: before,
      after: after,
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: true,
      before: before,
      after: after,
      dispatchedIndices: dispatchedIndices
    };
  } catch (_error) {
    const event = {
      event: "force-recordstate-on-state1-error",
      reason: reason,
      before: before,
      promotableIndices: promotableIndices,
      error: String(_error),
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: false,
      before: before,
      promotableIndices: promotableIndices,
      error: String(_error)
    };
  } finally {
    recordStateForceInProgress = false;
  }
}

function tryForceDirectDispatchOnState1(owner, reason) {
  if (!__FORCE_DIRECT_DISPATCH_ON_STATE1__ || directDispatchForceInProgress) {
    return {
      forced: false
    };
  }
  const before = summarizeOwner(owner);
  const stateByIndex = {};
  if (before && before.stateIndices) {
    before.stateIndices.forEach(item => {
      stateByIndex[item.index] = item.state;
    });
  }
  const dispatchableIndices = before && before.ptr1c8SetIndices
    ? before.ptr1c8SetIndices.filter(index =>
        !(index in forcedDirectDispatchIndices) &&
        stateByIndex[index] === 1
      )
    : [];
  if (
    !before ||
    before.queuedCount !== 0 ||
    before.activeCount !== 0 ||
    before.inProgressCount !== 0 ||
    dispatchableIndices.length === 0
  ) {
    return {
      forced: false,
      before: before
    };
  }
  directDispatchForceInProgress = true;
  try {
    const dispatchedIndices = dispatchableIndices.slice(0, 1);
    for (const index of dispatchedIndices) {
      directDispatch(ptr(owner), index);
      forcedDirectDispatchIndices[index] = true;
    }
    totalForcedDirectDispatches += dispatchedIndices.length;
    const after = summarizeOwner(owner);
    const event = {
      event: "force-direct-dispatch-on-state1",
      reason: reason,
      owner: after.owner,
      dispatchedIndices: dispatchedIndices,
      before: before,
      after: after,
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: true,
      before: before,
      after: after,
      dispatchedIndices: dispatchedIndices
    };
  } catch (_error) {
    const event = {
      event: "force-direct-dispatch-on-state1-error",
      reason: reason,
      before: before,
      dispatchableIndices: dispatchableIndices,
      error: String(_error),
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: false,
      before: before,
      dispatchableIndices: dispatchableIndices,
      error: String(_error)
    };
  } finally {
    directDispatchForceInProgress = false;
  }
}

function tryForceFinalizeOnState1(owner, reason) {
  if (!__FORCE_FINALIZE_ON_STATE1__ || finalizeForceInProgress) {
    return {
      forced: false
    };
  }
  const before = summarizeOwner(owner);
  const stateByIndex = {};
  const detailByIndex = {};
  if (before && before.stateIndices) {
    before.stateIndices.forEach(item => {
      stateByIndex[item.index] = item.state;
    });
  }
  if (before && before.selectorPtr178Details) {
    before.selectorPtr178Details.forEach(item => {
      detailByIndex[item.index] = item;
    });
  }
  const special20Indices = before && before.special20Indices ? before.special20Indices.slice() : [];
  const state1Indices = before && before.ptr178SetIndices
    ? before.ptr178SetIndices.filter(index => stateByIndex[index] === 1)
    : [];
  const preferredIndices = special20Indices.filter(index => state1Indices.indexOf(index) !== -1);
  const candidateIndices = (preferredIndices.length !== 0 ? preferredIndices : state1Indices).filter(index => {
    if (index in forcedFinalizeIndices) {
      return false;
    }
    const detail = detailByIndex[index];
    if (!detail) {
      return false;
    }
    return detail.field170 === 0 && detail.ptr180 === "0x0" && detail.ptr188 === "0x0";
  });
  if (
    !before ||
    before.queuedCount !== 0 ||
    before.activeCount !== 0 ||
    before.inProgressCount !== 0 ||
    candidateIndices.length === 0
  ) {
    return {
      forced: false,
      before: before
    };
  }
  finalizeForceInProgress = true;
  try {
    const dispatchedIndices = [];
    for (const index of candidateIndices.slice(0, 1)) {
      const recordBase = ptr(owner).add(8 + (index * 0x1d8));
      recordFinalize(ptr(owner), recordBase);
      forcedFinalizeIndices[index] = true;
      dispatchedIndices.push(index);
    }
    totalForcedFinalizeDispatches += dispatchedIndices.length;
    const after = summarizeOwner(owner);
    const event = {
      event: "force-finalize-on-state1",
      reason: reason,
      owner: after.owner,
      dispatchedIndices: dispatchedIndices,
      before: before,
      after: after,
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: true,
      before: before,
      after: after,
      dispatchedIndices: dispatchedIndices
    };
  } catch (_error) {
    const event = {
      event: "force-finalize-on-state1-error",
      reason: reason,
      before: before,
      candidateIndices: candidateIndices,
      error: String(_error),
      timestamp: Date.now() / 1000.0
    };
    send(event);
    return {
      forced: false,
      before: before,
      candidateIndices: candidateIndices,
      error: String(_error)
    };
  } finally {
    finalizeForceInProgress = false;
  }
}

Interceptor.attach(bridgeScanAddress, {
  onEnter(args) {
    bridgeHits += 1;
    const owner = this.context.rdi;
    const state1Force = tryForceState1OnPtr178(owner, "bridge-enter");
    const selectorReadyForce = tryForceSelectorReadyOnPtr178(owner, "bridge-enter");
    const owner11d4aForce = tryForceOwner11d4aOpenOnSpecial20(owner, "bridge-enter");
    const seedDispatchForce = tryForceSeedDispatchOnState1(owner, "bridge-enter");
    const recordStateForce = tryForceRecordStateOnState1(owner, "bridge-enter");
    const directDispatchForce = tryForceDirectDispatchOnState1(owner, "bridge-enter");
    const finalizeForce = tryForceFinalizeOnState1(owner, "bridge-enter");
    const summary = summarizeOwner(owner);
    const event = {
      event: "bridge-scan",
      owner: summary.owner,
      forcedState1OnPtr178: state1Force.forced === true,
      forceState1Before: state1Force.before || null,
      forceState1After: state1Force.after || null,
      promotedIndices: state1Force.promotedIndices || [],
      forcedSelectorReadyOnPtr178: selectorReadyForce.forced === true,
      forceSelectorReadyBefore: selectorReadyForce.before || null,
      forceSelectorReadyAfter: selectorReadyForce.after || null,
      selectorReadyPromotedIndices: selectorReadyForce.promotedIndices || [],
      forcedOwner11d4aOpenOnSpecial20: owner11d4aForce.forced === true,
      forceOwner11d4aBefore: owner11d4aForce.before || null,
      forceOwner11d4aAfter: owner11d4aForce.after || null,
      forcedSeedDispatchOnState1: seedDispatchForce.forced === true,
      forceSeedDispatchBefore: seedDispatchForce.before || null,
      forceSeedDispatchAfter: seedDispatchForce.after || null,
      seedDispatchIndices: seedDispatchForce.dispatchedIndices || [],
      forcedRecordStateOnState1: recordStateForce.forced === true,
      forceRecordStateBefore: recordStateForce.before || null,
      forceRecordStateAfter: recordStateForce.after || null,
      recordStateDispatchedIndices: recordStateForce.dispatchedIndices || [],
      forcedDirectDispatchOnState1: directDispatchForce.forced === true,
      forceDirectDispatchBefore: directDispatchForce.before || null,
      forceDirectDispatchAfter: directDispatchForce.after || null,
      directDispatchIndices: directDispatchForce.dispatchedIndices || [],
      forcedFinalizeOnState1: finalizeForce.forced === true,
      forceFinalizeBefore: finalizeForce.before || null,
      forceFinalizeAfter: finalizeForce.after || null,
      finalizeIndices: finalizeForce.dispatchedIndices || [],
      summary: summary,
      timestamp: Date.now() / 1000.0
    };
    latest.bridgeScan = event;
    const key = JSON.stringify({
      owner: summary.owner,
      queuedCount: summary.queuedCount,
      stateCount: summary.stateCount,
      ptr178SetCount: summary.ptr178SetCount,
      selectorEligibleCount: summary.selectorEligibleCount,
      activeCount: summary.activeCount,
      inProgressCount: summary.inProgressCount
    });
    countByKey(bridgeCounts, key);
    if (key !== latestBridgeKey) {
      latestBridgeKey = key;
      send(event);
    }
  }
});

Interceptor.attach(seedDispatchAddress, {
  onEnter(args) {
    this.owner = args[0];
    this.index = args[1].toInt32();
    this.before = summarizeOwner(this.owner);
  },
  onLeave(_retval) {
    seedDispatchHits += 1;
    const after = summarizeOwner(this.owner);
    const event = {
      event: "seed-dispatch-call",
      owner: after.owner,
      index: this.index,
      before: this.before,
      after: after,
      timestamp: Date.now() / 1000.0
    };
    latest.seedDispatch = event;
    const key = JSON.stringify({
      owner: after.owner,
      index: this.index,
      beforeQueuedCount: this.before ? this.before.queuedCount : null,
      afterQueuedCount: after.queuedCount,
      beforeStateCount: this.before ? this.before.stateCount : null,
      afterStateCount: after.stateCount,
      afterPtr178SetCount: after.ptr178SetCount,
      afterSelectorEligibleCount: after.selectorEligibleCount
    });
    countByKey(seedDispatchCounts, key);
    sendUniqueByKey(seedDispatchCounts, "event:" + key, event);
  }
});

function emitStateWrite(site, owner, index, value) {
  stateWriteHits += 1;
  const summary = summarizeOwner(owner);
  const event = {
    event: "loop-state-write",
    site: site,
    owner: summary.owner,
    index: index,
    value: value,
    summary: summary,
    timestamp: Date.now() / 1000.0
  };
  latest.stateWrite = event;
  const key = JSON.stringify({
    site: site,
    owner: summary.owner,
    index: index,
      value: value,
      queuedCount: summary.queuedCount,
      stateCount: summary.stateCount,
      ptr178SetCount: summary.ptr178SetCount,
      selectorEligibleCount: summary.selectorEligibleCount
    });
  countByKey(stateWriteCounts, key);
  sendUniqueByKey(stateWriteCounts, "event:" + key, event);
}

Interceptor.attach(state1WriteAddress, {
  onEnter(args) {
    emitStateWrite("state1-write", this.context.rcx, this.context.rax.toInt32(), 1);
  }
});

Interceptor.attach(state2WriteAddress, {
  onEnter(args) {
    emitStateWrite("state2-write", this.context.rsi, this.context.rax.toInt32(), 2);
  }
});

Interceptor.attach(state34WriteAddress, {
  onEnter(args) {
    emitStateWrite("state34-write", this.context.rsi, this.context.r12.toInt32(), this.context.rax.toInt32());
  }
});
"""
        .replace("__BRIDGE_SCAN_RVA__", hex(bridge_scan_rva))
        .replace("__DISPATCH_RVA__", hex(dispatch_rva))
        .replace("__SEED_DISPATCH_RVA__", hex(seed_dispatch_rva))
        .replace("__RECORD_STATE_RVA__", hex(record_state_rva))
        .replace("__RECORD_FINALIZE_RVA__", hex(record_finalize_rva))
        .replace("__STATE1_WRITE_RVA__", hex(state1_write_rva))
        .replace("__STATE2_WRITE_RVA__", hex(state2_write_rva))
        .replace("__STATE34_WRITE_RVA__", hex(state34_write_rva))
        .replace("__SCHEDULER_GLOBAL_RVA__", hex(scheduler_global_rva))
        .replace("__FORCE_STATE1_ON_PTR178__", "true" if force_state1_on_ptr178 else "false")
        .replace(
            "__FORCE_SELECTOR_READY_ON_PTR178__",
            "true" if force_selector_ready_on_ptr178 else "false",
        )
        .replace(
            "__FORCE_OWNER_11D4A_OPEN_ON_SPECIAL20__",
            "true" if force_owner_11d4a_open_on_special20 else "false",
        )
        .replace(
            "__FORCE_SEED_DISPATCH_ON_STATE1__",
            "true" if force_seed_dispatch_on_state1 else "false",
        )
        .replace(
            "__FORCE_RECORDSTATE_ON_STATE1__",
            "true" if force_recordstate_on_state1 else "false",
        )
        .replace(
            "__FORCE_DIRECT_DISPATCH_ON_STATE1__",
            "true" if force_direct_dispatch_on_state1 else "false",
        )
        .replace(
            "__FORCE_FINALIZE_ON_STATE1__",
            "true" if force_finalize_on_state1 else "false",
        )
    )


def archive_output_path(output_root: Path, timestamp: datetime) -> Path:
    return output_root / f"947-application-resource-bridge-{timestamp.strftime('%Y%m%d-%H%M%S')}.jsonl"


def archive_summary_path(output_root: Path, timestamp: datetime) -> Path:
    return output_root / f"947-application-resource-bridge-{timestamp.strftime('%Y%m%d-%H%M%S')}.json"


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
            bridge_scan_rva=args.bridge_scan_rva,
            dispatch_rva=args.dispatch_rva,
            seed_dispatch_rva=args.seed_dispatch_rva,
            record_state_rva=args.record_state_rva,
            record_finalize_rva=args.record_finalize_rva,
            state1_write_rva=args.state1_write_rva,
            state2_write_rva=args.state2_write_rva,
            state34_write_rva=args.state34_write_rva,
            scheduler_global_rva=args.scheduler_global_rva,
            force_state1_on_ptr178=args.force_state1_on_ptr178,
            force_selector_ready_on_ptr178=args.force_selector_ready_on_ptr178,
            force_owner_11d4a_open_on_special20=args.force_owner_11d4a_open_on_special20,
            force_seed_dispatch_on_state1=args.force_seed_dispatch_on_state1,
            force_recordstate_on_state1=args.force_recordstate_on_state1,
            force_direct_dispatch_on_state1=args.force_direct_dispatch_on_state1,
            force_finalize_on_state1=args.force_finalize_on_state1,
        )
    )

    bridge_hits = 0
    seed_dispatch_hits = 0
    state_write_hits = 0
    event_counts: dict[str, int] = {}
    latest_bridge = None
    latest_seed_dispatch = None
    latest_state_write = None

    with archive_path.open("w", encoding="utf-8") as archive_file, latest_path.open(
        "w", encoding="utf-8"
    ) as latest_file:

        def handle_message(message: dict, _data) -> None:
            nonlocal bridge_hits, seed_dispatch_hits, state_write_hits
            nonlocal latest_bridge, latest_seed_dispatch, latest_state_write
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
            if event_name == "bridge-scan":
                bridge_hits += 1
                latest_bridge = payload
            elif event_name == "seed-dispatch-call":
                seed_dispatch_hits += 1
                latest_seed_dispatch = payload
            elif event_name == "loop-state-write":
                state_write_hits += 1
                latest_state_write = payload
            if event_name is not None:
                event_counts[event_name] = event_counts.get(event_name, 0) + 1
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
        "bridgeScanRva": hex(args.bridge_scan_rva),
        "dispatchRva": hex(args.dispatch_rva),
        "seedDispatchRva": hex(args.seed_dispatch_rva),
        "recordStateRva": hex(args.record_state_rva),
        "state1WriteRva": hex(args.state1_write_rva),
        "state2WriteRva": hex(args.state2_write_rva),
        "state34WriteRva": hex(args.state34_write_rva),
        "schedulerGlobalRva": hex(args.scheduler_global_rva),
        "forceState1OnPtr178": args.force_state1_on_ptr178,
        "forceSelectorReadyOnPtr178": args.force_selector_ready_on_ptr178,
        "forceOwner11d4aOpenOnSpecial20": args.force_owner_11d4a_open_on_special20,
        "forceRecordStateOnState1": args.force_recordstate_on_state1,
        "forceDirectDispatchOnState1": args.force_direct_dispatch_on_state1,
        "archivePath": str(archive_path),
        "latestPath": str(latest_path),
        "durationSeconds": args.duration_seconds,
        "snapshot": {
            "bridgeHits": bridge_hits,
            "seedDispatchHits": seed_dispatch_hits,
            "stateWriteHits": state_write_hits,
            "eventCounts": event_counts,
            "latest": {
                "bridgeScan": latest_bridge,
                "seedDispatch": latest_seed_dispatch,
                "stateWrite": latest_state_write,
            },
        },
    }
    archive_summary.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    latest_summary.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    print(json.dumps({"archivePath": str(archive_path), "summaryPath": str(archive_summary), "pid": pid}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
