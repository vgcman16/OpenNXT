from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import datetime
from pathlib import Path

import frida


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_DIR = WORKSPACE / "data" / "debug" / "frida-crash-probe" / "runs"
DEFAULT_LATEST_OUTPUT = WORKSPACE / "data" / "debug" / "frida-crash-probe" / "latest-client-only.jsonl"
DEFAULT_MODULE_NAME = "rs2client.exe"
DEFAULT_FUNCTION_START_RVA = 0x590BC0
DEFAULT_FAULT_RVA = 0x590DE8
DEFAULT_STATE_CAPTURE_RVA = 0x590DCB
DEFAULT_GUARD_CALLER_SITE_RVA = 0x58FF0F
DEFAULT_GUARD_RESUME_RVA = 0x58FF14
DEFAULT_EXTRA_CHECKPOINTS = (
    ("bad-path-edge", 0x590DB5),
    ("release-prep", 0x594B4C),
    ("release-call-8", 0x594B6F),
    ("release-call-10", 0x594B84),
    ("epilogue-prep", 0x5910F9),
)
DEFAULT_TRACKED_OFFSETS = (0x7710, 0x7730, 0x7734, 0x77D8, 0x77E0)
DEFAULT_INDEXED_TABLE_SLOT_OFFSET = 0x30D0
DEFAULT_UNSAFE_CALLER_SITE_RVAS = frozenset(
    {
        0x4488D7,
        0x58FF0F,
    }
)
DEFAULT_CALLER_SITE_RVAS = (
    0x29F226,
    0x2B1227,
    0x2B1308,
    0x2C1F14,
    0x2C3660,
    0x448593,
    0x5901CF,
    0x5903D7,
    0x5905E1,
    0x5906EC,
    0x590AC2,
)
DEFAULT_FORCE_SUCCESS_CALLER_SITE_RVAS: tuple[int, ...] = ()
DEFAULT_REPAIR_EPILOGUE_FRAME_CALLER_SITE_RVAS = (
    0x58FF0F,
)
DEFAULT_REPAIR_RELEASE_FRAME_CALLER_SITE_RVAS = (
    0x58FF0F,
)


def archive_probe_output_path(root: Path, when: datetime | None = None) -> Path:
    timestamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return root / f"947-client-only-crash-probe-{timestamp}.jsonl"


def parse_hex_int(value: str) -> int:
    return int(value, 0)


def validate_probe_configuration(args: argparse.Namespace) -> None:
    if not args.enable_missing_indexed_table_guard:
        return

    if args.guard_caller_site_rva in DEFAULT_UNSAFE_CALLER_SITE_RVAS:
        raise ValueError(
            "The requested guard caller site is known-unsafe for WIN64 Frida interception: "
            f"0x{args.guard_caller_site_rva:x}"
        )

    if args.guard_caller_site_rva not in DEFAULT_CALLER_SITE_RVAS:
        raise ValueError(
            "The requested guard caller site is not part of the active caller-site probe list: "
            f"0x{args.guard_caller_site_rva:x}"
        )


def build_hook_script(
    *,
    module_name: str,
    function_start_rva: int,
    fault_rva: int,
    state_capture_rva: int,
    tracked_offsets: tuple[int, ...],
    indexed_table_slot_offset: int = DEFAULT_INDEXED_TABLE_SLOT_OFFSET,
    repair_r15_at_state_capture: bool = False,
    repair_epilogue_frame: bool = False,
    repair_release_frame: bool = False,
    enable_missing_indexed_table_guard: bool = False,
    guard_caller_site_rva: int = DEFAULT_GUARD_CALLER_SITE_RVA,
    guard_resume_rva: int = DEFAULT_GUARD_RESUME_RVA,
    caller_site_rvas: tuple[int, ...] = DEFAULT_CALLER_SITE_RVAS,
    force_success_caller_site_rvas: tuple[int, ...] = DEFAULT_FORCE_SUCCESS_CALLER_SITE_RVAS,
    repair_epilogue_frame_caller_site_rvas: tuple[int, ...] = DEFAULT_REPAIR_EPILOGUE_FRAME_CALLER_SITE_RVAS,
    repair_release_frame_caller_site_rvas: tuple[int, ...] = DEFAULT_REPAIR_RELEASE_FRAME_CALLER_SITE_RVAS,
    extra_checkpoints: tuple[tuple[str, int], ...] = DEFAULT_EXTRA_CHECKPOINTS,
) -> str:
    offsets_js = "[" + ", ".join(f"0x{offset:x}" for offset in tracked_offsets) + "]"
    caller_sites_js = "[" + ", ".join(f"0x{offset:x}" for offset in caller_site_rvas) + "]"
    force_success_sites_js = "[" + ", ".join(f"0x{offset:x}" for offset in force_success_caller_site_rvas) + "]"
    repair_epilogue_frame_sites_js = (
        "[" + ", ".join(f"0x{offset:x}" for offset in repair_epilogue_frame_caller_site_rvas) + "]"
    )
    repair_release_frame_sites_js = (
        "[" + ", ".join(f"0x{offset:x}" for offset in repair_release_frame_caller_site_rvas) + "]"
    )
    extra_checkpoints_js = (
        "["
        + ", ".join(
            "{ name: "
            + json.dumps(name)
            + ", rva: "
            + f"0x{rva:x}"
            + " }"
            for name, rva in extra_checkpoints
        )
        + "]"
    )
    template = r"""
'use strict';

const moduleName = "__MODULE__";
const functionStartRva = __FUNCTION_START__;
const faultRva = __FAULT_RVA__;
const stateCaptureRva = __STATE_CAPTURE_RVA__;
const trackedOffsets = __TRACKED_OFFSETS__;
const indexedTableSlotOffset = __INDEXED_TABLE_SLOT_OFFSET__;
const repairR15AtStateCapture = __REPAIR_R15__;
const repairEpilogueFrame = __REPAIR_EPILOGUE_FRAME__;
const repairReleaseFrame = __REPAIR_RELEASE_FRAME__;
const enableMissingIndexedTableGuard = __ENABLE_MISSING_INDEXED_TABLE_GUARD__;
const guardCallerSiteRva = __GUARD_CALLER_SITE_RVA__;
const guardResumeRva = __GUARD_RESUME_RVA__;
const callerSiteRvas = __CALLER_SITES__;
const forceSuccessCallerSiteRvas = __FORCE_SUCCESS_CALLER_SITES__;
const forceSuccessCallerSiteSet = {};
forceSuccessCallerSiteRvas.forEach((rva) => {
  forceSuccessCallerSiteSet['0x' + rva.toString(16)] = true;
});
const repairEpilogueFrameCallerSiteRvas = __REPAIR_EPILOGUE_FRAME_CALLER_SITES__;
const repairEpilogueFrameCallerSiteSet = {};
repairEpilogueFrameCallerSiteRvas.forEach((rva) => {
  repairEpilogueFrameCallerSiteSet['0x' + rva.toString(16)] = true;
});
const repairReleaseFrameCallerSiteRvas = __REPAIR_RELEASE_FRAME_CALLER_SITES__;
const repairReleaseFrameCallerSiteSet = {};
repairReleaseFrameCallerSiteRvas.forEach((rva) => {
  repairReleaseFrameCallerSiteSet['0x' + rva.toString(16)] = true;
});
const extraCheckpoints = __EXTRA_CHECKPOINTS__;

const moduleObject = Process.getModuleByName(moduleName);
const functionStart = moduleObject.base.add(functionStartRva);
const faultAddress = moduleObject.base.add(faultRva);
const stateCaptureAddress = moduleObject.base.add(stateCaptureRva);
const guardCallerSiteAddress = moduleObject.base.add(guardCallerSiteRva);
const guardResumeAddress = moduleObject.base.add(guardResumeRva);
const callerSiteAddresses = callerSiteRvas.map((rva) => moduleObject.base.add(rva));
const extraCheckpointAddresses = extraCheckpoints.map((entry) => ({
  name: entry.name,
  rva: entry.rva,
  address: moduleObject.base.add(entry.rva)
}));
const threadSnapshots = {};

function ptrToHex(value) {
  if (value === null || value === undefined) {
    return '0x0';
  }
  try {
    return ptr(value).toString();
  } catch (error) {
    return String(value);
  }
}

function pointerToRvaString(value) {
  try {
    const absolute = BigInt(ptrToHex(value));
    const base = BigInt(ptrToHex(moduleObject.base));
    if (absolute < base) {
      return null;
    }
    return '0x' + (absolute - base).toString(16);
  } catch (error) {
    return null;
  }
}

function describeInstruction(address) {
  try {
    const instruction = Instruction.parse(ptr(address));
    return {
      address: ptrToHex(address),
      mnemonic: instruction.mnemonic,
      opStr: instruction.opStr,
      next: ptrToHex(instruction.next),
      text: instruction.toString()
    };
  } catch (error) {
    return {
      address: ptrToHex(address),
      parseError: String(error)
    };
  }
}

function nowMs() {
  return Date.now();
}

function safeRange(address) {
  try {
    return Process.findRangeByAddress(ptr(address));
  } catch (error) {
    return null;
  }
}

function safeReadOffset(baseAddress, offset) {
  const address = ptr(baseAddress).add(offset);
  const range = safeRange(address);
  if (range === null || range.protection.indexOf('r') === -1) {
    return {
      address: ptrToHex(address),
      offset: '0x' + offset.toString(16),
      readable: false
    };
  }
  const result = {
    address: ptrToHex(address),
    offset: '0x' + offset.toString(16),
    readable: true
  };
  try {
    result.u8 = address.readU8();
  } catch (error) {
    result.u8Error = String(error);
  }
  try {
    result.pointer = ptrToHex(address.readPointer());
  } catch (error) {
    result.pointerError = String(error);
  }
  return result;
}

function classifyPointer(value) {
  const pointerValue = ptr(value);
  const record = {
    value: ptrToHex(pointerValue),
    kind: 'unknown',
    readable: false,
    offsetReads: []
  };

  if (pointerValue.isNull()) {
    record.kind = 'null';
    return record;
  }

  if (pointerValue.compare(ptr('0x10000')) < 0) {
    record.kind = 'tiny-scalar';
    return record;
  }

  const range = safeRange(pointerValue);
  if (range === null || range.protection.indexOf('r') === -1) {
    record.kind = 'unreadable';
    return record;
  }

  record.kind = 'likely-pointer';
  record.readable = true;
  record.rangeBase = ptrToHex(range.base);
  record.rangeSize = range.size;
  record.rangeProtection = range.protection;
  record.offsetReads = trackedOffsets.map((offset) => safeReadOffset(pointerValue, offset));
  return record;
}

function safeReadU32(address) {
  const pointerValue = ptr(address);
  const range = safeRange(pointerValue);
  const result = {
    address: ptrToHex(pointerValue),
    readable: false
  };

  if (range === null || range.protection.indexOf('r') === -1) {
    return result;
  }

  result.readable = true;
  try {
    result.u32 = pointerValue.readU32();
  } catch (error) {
    result.u32Error = String(error);
  }
  return result;
}

function safeReadU64(address) {
  const pointerValue = ptr(address);
  const range = safeRange(pointerValue);
  const result = {
    address: ptrToHex(pointerValue),
    readable: false
  };

  if (range === null || range.protection.indexOf('r') === -1) {
    return result;
  }

  result.readable = true;
  try {
    result.u64 = pointerValue.readU64().toString();
  } catch (error) {
    result.u64Error = String(error);
  }
  return result;
}

function safeReadPointerValue(address) {
  const pointerValue = ptr(address);
  const range = safeRange(pointerValue);
  const result = {
    address: ptrToHex(pointerValue),
    readable: false
  };

  if (range === null || range.protection.indexOf('r') === -1) {
    return result;
  }

  result.readable = true;
  try {
    result.pointer = ptrToHex(pointerValue.readPointer());
  } catch (error) {
    result.pointerError = String(error);
  }
  return result;
}

function describeVtableObject(value) {
  const result = {
    objectState: classifyPointer(value)
  };
  if (!result.objectState.readable) {
    return result;
  }
  const objectPointer = ptr(value);
  const vtableRead = safeReadPointerValue(objectPointer);
  result.vtablePointerRead = vtableRead;
  if (!vtableRead.readable || !vtableRead.pointer) {
    return result;
  }
  const vtablePointer = ptr(vtableRead.pointer);
  result.vtableState = classifyPointer(vtablePointer);
  result.slot8Read = safeReadPointerValue(vtablePointer.add(0x8));
  result.slot10Read = safeReadPointerValue(vtablePointer.add(0x10));
  return result;
}

function collectStackObjectDetails(context, offsets) {
  const result = {};
  offsets.forEach((offset) => {
    const key = 'rspPlus' + offset.toString(16);
    const slotAddress = ptr(context.rsp).add(offset);
    const slotPointerRead = safeReadPointerValue(slotAddress);
    result[key] = {
      stackSlotAddress: ptrToHex(slotAddress),
      stackSlotPointerRead: slotPointerRead
    };
    if (slotPointerRead.readable && slotPointerRead.pointer) {
      result[key].objectDetails = describeVtableObject(ptr(slotPointerRead.pointer));
    }
  });
  return result;
}

function stackOffsetsForCheckpoint(checkpointName) {
  if (checkpointName === 'epilogue-prep') {
    return [0x0, 0x160, 0x168, 0x170, 0x178, 0x180, 0x188, 0x190, 0x198, 0x1b0];
  }
  return [0x40, 0x70, 0x78];
}

function safeReadBytes(address, count) {
  const pointerValue = ptr(address);
  const range = safeRange(pointerValue);
  const result = {
    address: ptrToHex(pointerValue),
    readable: false,
    requestedBytes: count
  };

  if (range === null || range.protection.indexOf('r') === -1) {
    return result;
  }

  result.readable = true;
  try {
    const bytes = pointerValue.readByteArray(count);
    const array = new Uint8Array(bytes);
    result.hex = Array.prototype.map.call(array, (value) => ('0' + value.toString(16)).slice(-2)).join(' ');
  } catch (error) {
    result.readError = String(error);
  }
  return result;
}

function describeIndexedTable(param1Value, param2Value) {
  const result = {
    slotOffset: '0x' + indexedTableSlotOffset.toString(16),
    requestedIndex: safeReadU32(param2Value),
    tablePointerRead: safeReadPointerValue(ptr(param1Value).add(indexedTableSlotOffset))
  };

  if (result.tablePointerRead.pointer === undefined) {
    return result;
  }

  const tablePointer = ptr(result.tablePointerRead.pointer);
  result.tableState = classifyPointer(tablePointer);
  result.countRead = safeReadU64(tablePointer.add(0x10));
  result.entriesPointerRead = safeReadPointerValue(tablePointer.add(0x18));

  if (result.requestedIndex.u32 === undefined || result.countRead.u64 === undefined) {
    return result;
  }

  const requestedIndex = result.requestedIndex.u32;
  const entryCount = parseInt(result.countRead.u64, 10);
  result.entryCount = entryCount;
  result.indexInRange = requestedIndex < entryCount;

  if (!result.indexInRange || result.entriesPointerRead.pointer === undefined) {
    return result;
  }

  const entriesPointer = ptr(result.entriesPointerRead.pointer);
  const entryPointerRead = safeReadPointerValue(entriesPointer.add(requestedIndex * Process.pointerSize));
  result.entryPointerRead = entryPointerRead;
  if (entryPointerRead.pointer === undefined) {
    return result;
  }

  const entryPointer = ptr(entryPointerRead.pointer);
  result.entryState = classifyPointer(entryPointer);
  result.entryFirstU32 = safeReadU32(entryPointer);
  result.entrySecondU32 = safeReadU32(entryPointer.add(4));
  return result;
}

function parseReadableU64(readResult) {
  if (!readResult || readResult.u64 === undefined) {
    return null;
  }
  try {
    return parseInt(String(readResult.u64), 10);
  } catch (error) {
    return null;
  }
}

function decideMissingIndexedTableGuard(argumentsSnapshot) {
  const indexedTable = argumentsSnapshot.param1IndexedTable30d0 || {};
  const requestedIndex = indexedTable.requestedIndex && indexedTable.requestedIndex.u32 !== undefined
    ? indexedTable.requestedIndex.u32
    : null;
  const countValue = parseReadableU64(indexedTable.countRead);
  const tablePointer = indexedTable.tablePointerRead && indexedTable.tablePointerRead.pointer !== undefined
    ? indexedTable.tablePointerRead.pointer
    : null;
  const entriesPointer = indexedTable.entriesPointerRead && indexedTable.entriesPointerRead.pointer !== undefined
    ? indexedTable.entriesPointerRead.pointer
    : null;
  const reasons = [];

  if (tablePointer === '0x0') {
    reasons.push('null-table');
  }
  if (entriesPointer === '0x0') {
    reasons.push('null-entries');
  }
  if (countValue !== null && requestedIndex !== null && requestedIndex >= countValue) {
    reasons.push('index-out-of-range');
  }

  return {
    enabled: enableMissingIndexedTableGuard,
    shouldSkip: reasons.length > 0,
    reasons: reasons,
    requestedIndex: requestedIndex,
    countValue: countValue,
    tablePointer: tablePointer,
    entriesPointer: entriesPointer,
    guardCallerSiteAddress: ptrToHex(guardCallerSiteAddress),
    guardCallerSiteRva: '0x' + guardCallerSiteRva.toString(16),
    guardResumeAddress: ptrToHex(guardResumeAddress),
    guardResumeRva: '0x' + guardResumeRva.toString(16)
  };
}

function safeReadStackValue(context, stackOffset) {
  const address = ptr(context.rsp).add(stackOffset);
  const range = safeRange(address);
  const result = {
    address: ptrToHex(address),
    offset: '0x' + stackOffset.toString(16),
    readable: false
  };

  if (range === null || range.protection.indexOf('r') === -1) {
    return result;
  }

  result.readable = true;
  try {
    result.pointer = ptrToHex(address.readPointer());
  } catch (error) {
    result.pointerError = String(error);
  }
  try {
    result.u8 = address.readU8();
  } catch (error) {
    result.u8Error = String(error);
  }
  try {
    result.u32 = address.readU32();
  } catch (error) {
    result.u32Error = String(error);
  }
  return result;
}

function collectEntryArguments(context) {
  const returnAddress = safeReadStackValue(context, 0);
  const stackArg5 = safeReadStackValue(context, 0x28);
  const argumentsSnapshot = {
    param1: ptrToHex(context.rcx),
    param1State: classifyPointer(context.rcx),
    param1IndexedTable30d0: describeIndexedTable(context.rcx, context.rdx),
    param2: ptrToHex(context.rdx),
    param2State: classifyPointer(context.rdx),
    param2U32: safeReadU32(context.rdx),
    param3: ptr(context.r8).toUInt32(),
    param4: ptr(context.r9).toUInt32() & 0xff,
    returnAddressRead: returnAddress,
    stackArg5: stackArg5
  };

  if (returnAddress.pointer !== undefined) {
    argumentsSnapshot.returnAddress = returnAddress.pointer;
    try {
      const callerCallSite = ptr(returnAddress.pointer).sub(5);
      argumentsSnapshot.callerCallSite = ptrToHex(callerCallSite);
      argumentsSnapshot.callerCallSiteRva = pointerToRvaString(callerCallSite);
    } catch (error) {
      argumentsSnapshot.callerCallSiteError = String(error);
    }
  }

  return argumentsSnapshot;
}

function collectCallArguments(context) {
  return {
    param1: ptrToHex(context.rcx),
    param1State: classifyPointer(context.rcx),
    param1IndexedTable30d0: describeIndexedTable(context.rcx, context.rdx),
    param2: ptrToHex(context.rdx),
    param2State: classifyPointer(context.rdx),
    param2U32: safeReadU32(context.rdx),
    param3: ptr(context.r8).toUInt32(),
    param4: ptr(context.r9).toUInt32() & 0xff,
    stackArg5: safeReadStackValue(context, 0x28)
  };
}

function collectRegisters(context, names) {
  const snapshot = {};
  for (const name of names) {
    if (context[name] !== undefined) {
      snapshot[name] = ptrToHex(context[name]);
    }
  }
  return snapshot;
}

function collectRegisterU32(context, names) {
  const snapshot = {};
  for (const name of names) {
    if (context[name] !== undefined) {
      snapshot[name] = ptr(context[name]).toUInt32();
    }
  }
  return snapshot;
}

function formatFrame(address) {
  const symbol = DebugSymbol.fromAddress(ptr(address));
  return {
    address: ptrToHex(address),
    symbol: symbol !== null ? symbol.toString() : null
  };
}

function collectBacktrace(context) {
  try {
    return Thread.backtrace(context, Backtracer.ACCURATE).slice(0, 12).map(formatFrame);
  } catch (error) {
    return [{ address: '0x0', symbol: '<backtrace-error> ' + String(error) }];
  }
}

function maybeRepairR15(context) {
  if (!repairR15AtStateCapture) {
    return null;
  }

  const r14State = classifyPointer(context.r14);
  const r15State = classifyPointer(context.r15);
  if (r14State.kind !== 'likely-pointer' || r15State.kind !== 'tiny-scalar') {
    return null;
  }

  const index = ptr(context.r10).toUInt32();
  if (index > 0x100000) {
    return null;
  }

  const repaired = ptr(context.r14).add(index * 0x108);
  context.r15 = repaired;
  return {
    index: index,
    oldR15: r15State.value,
    repairedR15: ptrToHex(repaired),
    repairedR15State: classifyPointer(repaired)
  };
}

function maybeRepairEpilogueFrame(context, threadSnapshot) {
  if (!repairEpilogueFrame) {
    return null;
  }

  const entrySnapshot = threadSnapshot || null;
  if (entrySnapshot === null || !entrySnapshot.arguments || !entrySnapshot.registers) {
    return null;
  }

  const callerCallSite = entrySnapshot.arguments.callerCallSite || null;
  const callerCallSiteRva = entrySnapshot.arguments.callerCallSiteRva || null;
  if (callerCallSiteRva === null || repairEpilogueFrameCallerSiteSet[callerCallSiteRva] !== true) {
    return null;
  }

  const expectedSlots = [
    { name: 'savedR15', offset: 0x160, expectedPointer: entrySnapshot.registers.r15 || null },
    { name: 'savedR12', offset: 0x168, expectedPointer: entrySnapshot.registers.r12 || null },
    { name: 'savedRdi', offset: 0x170, expectedPointer: entrySnapshot.registers.rdi || null },
    { name: 'savedR14', offset: 0x178, expectedPointer: entrySnapshot.registers.r14 || null },
    { name: 'savedR13', offset: 0x180, expectedPointer: entrySnapshot.registers.r13 || null },
    { name: 'savedRbx', offset: 0x188, expectedPointer: entrySnapshot.registers.rbx || null },
    { name: 'savedRbp', offset: 0x190, expectedPointer: entrySnapshot.registers.rbp || null },
    { name: 'returnAddress', offset: 0x198, expectedPointer: entrySnapshot.arguments.returnAddressRead
      ? (entrySnapshot.arguments.returnAddressRead.pointer || null)
      : null },
    { name: 'savedRsi', offset: 0x1b0, expectedPointer: entrySnapshot.registers.rsi || null }
  ];

  const repairs = [];
  expectedSlots.forEach((slot) => {
    if (slot.expectedPointer === null) {
      return;
    }
    const slotAddress = ptr(context.rsp).add(slot.offset);
    const slotRead = safeReadPointerValue(slotAddress);
    if (!slotRead.readable || slotRead.pointer === undefined || slotRead.pointer === slot.expectedPointer) {
      return;
    }
    try {
      slotAddress.writePointer(ptr(slot.expectedPointer));
      repairs.push({
        name: slot.name,
        offset: '0x' + slot.offset.toString(16),
        slotAddress: ptrToHex(slotAddress),
        before: slotRead.pointer,
        after: slot.expectedPointer
      });
    } catch (error) {
      repairs.push({
        name: slot.name,
        offset: '0x' + slot.offset.toString(16),
        slotAddress: ptrToHex(slotAddress),
        before: slotRead.pointer,
        after: slot.expectedPointer,
        writeError: String(error)
      });
    }
  });

  if (repairs.length === 0) {
    return null;
  }

  return {
    callerCallSite: callerCallSite,
    callerCallSiteRva: callerCallSiteRva,
    repairs: repairs
  };
}

function pointerLooksImplausibleForSavedFrame(pointerValue) {
  if (pointerValue === null || pointerValue === undefined) {
    return true;
  }

  const normalized = String(pointerValue).toLowerCase();
  if (normalized === '0x0' || normalized === '0xffffffff' || normalized === '0xffffffffffffffff') {
    return true;
  }

  let candidate = null;
  try {
    candidate = ptr(pointerValue);
  } catch (error) {
    return true;
  }

  if (candidate.compare(ptr('0x10000')) < 0) {
    return true;
  }

  const range = safeRange(candidate);
  return range === null;
}

function maybeRepairReleaseFrame(context, threadSnapshot) {
  if (!repairReleaseFrame) {
    return null;
  }

  const entrySnapshot = threadSnapshot || null;
  if (entrySnapshot === null || !entrySnapshot.arguments || !entrySnapshot.registers) {
    return null;
  }

  const callerCallSite = entrySnapshot.arguments.callerCallSite || null;
  const callerCallSiteRva = entrySnapshot.arguments.callerCallSiteRva || null;
  if (callerCallSiteRva === null || repairReleaseFrameCallerSiteSet[callerCallSiteRva] !== true) {
    return null;
  }

  const expectedSlots = [
    { name: 'savedRbx', offset: 0x70, expectedPointer: entrySnapshot.registers.rbx || null },
    { name: 'savedRbp', offset: 0x78, expectedPointer: entrySnapshot.registers.rbp || null }
  ];

  const repairs = [];
  expectedSlots.forEach((slot) => {
    if (slot.expectedPointer === null) {
      return;
    }
    const slotAddress = ptr(context.rsp).add(slot.offset);
    const slotRead = safeReadPointerValue(slotAddress);
    const currentPointer = slotRead.pointer !== undefined ? slotRead.pointer : null;
    if (!pointerLooksImplausibleForSavedFrame(currentPointer) || currentPointer === slot.expectedPointer) {
      return;
    }
    try {
      slotAddress.writePointer(ptr(slot.expectedPointer));
      repairs.push({
        name: slot.name,
        offset: '0x' + slot.offset.toString(16),
        slotAddress: ptrToHex(slotAddress),
        before: currentPointer,
        after: slot.expectedPointer
      });
    } catch (error) {
      repairs.push({
        name: slot.name,
        offset: '0x' + slot.offset.toString(16),
        slotAddress: ptrToHex(slotAddress),
        before: currentPointer,
        after: slot.expectedPointer,
        writeError: String(error)
      });
    }
  });

  if (repairs.length === 0) {
    return null;
  }

  return {
    callerCallSite: callerCallSite,
    callerCallSiteRva: callerCallSiteRva,
    repairs: repairs
  };
}

send({
  category: 'client.crash-probe',
  action: 'handler-installed',
  moduleName: moduleName,
  functionStart: ptrToHex(functionStart),
  faultAddress: ptrToHex(faultAddress),
  stateCaptureAddress: ptrToHex(stateCaptureAddress),
  enableMissingIndexedTableGuard: enableMissingIndexedTableGuard,
  guardCallerSiteAddress: ptrToHex(guardCallerSiteAddress),
  guardCallerSiteRva: '0x' + guardCallerSiteRva.toString(16),
  guardResumeAddress: ptrToHex(guardResumeAddress),
  guardResumeRva: '0x' + guardResumeRva.toString(16),
  callerSiteAddresses: callerSiteAddresses.map(ptrToHex),
  forceSuccessCallerSiteRvas: forceSuccessCallerSiteRvas.map((rva) => '0x' + rva.toString(16)),
  repairEpilogueFrame: repairEpilogueFrame,
  repairEpilogueFrameCallerSiteRvas: repairEpilogueFrameCallerSiteRvas.map((rva) => '0x' + rva.toString(16)),
  repairReleaseFrame: repairReleaseFrame,
  repairReleaseFrameCallerSiteRvas: repairReleaseFrameCallerSiteRvas.map((rva) => '0x' + rva.toString(16)),
  repairR15AtStateCapture: repairR15AtStateCapture,
  extraCheckpointAddresses: extraCheckpointAddresses.map((entry) => ({
    name: entry.name,
    rva: '0x' + entry.rva.toString(16),
    address: ptrToHex(entry.address)
  }))
});

function tryAttach(address, tag, details, callbacks) {
  const instruction = describeInstruction(address);
  if (tag === 'caller-site' && instruction.mnemonic && instruction.mnemonic.toLowerCase() === 'call') {
    send({
      category: 'client.crash-probe',
      action: 'hook-skipped',
      hookTag: tag,
      address: ptrToHex(address),
      details: details,
      reason: 'direct-call-opcode',
      instruction: instruction,
      timestampMs: nowMs()
    });
    return false;
  }
  try {
    Interceptor.attach(address, callbacks);
    send({
      category: 'client.crash-probe',
      action: 'hook-installed',
      hookTag: tag,
      address: ptrToHex(address),
      details: details,
      instruction: instruction,
      timestampMs: nowMs()
    });
    return true;
  } catch (error) {
    send({
      category: 'client.crash-probe',
      action: 'hook-install-failed',
      hookTag: tag,
      address: ptrToHex(address),
      details: details,
      instruction: instruction,
      error: String(error),
      timestampMs: nowMs()
    });
    return false;
  }
}

callerSiteAddresses.forEach(function(address, index) {
  tryAttach(address, 'caller-site', {
    callerSiteIndex: index,
    callerSiteRva: '0x' + callerSiteRvas[index].toString(16)
  }, {
    onEnter(args) {
      const threadId = Process.getCurrentThreadId();
      const snapshot = {
        category: 'client.crash-probe',
        action: 'caller-site-hit',
        threadId: threadId,
        timestampMs: nowMs(),
        callerSiteIndex: index,
        callerSiteRva: '0x' + callerSiteRvas[index].toString(16),
        callerSiteAddress: ptrToHex(address),
        registers: collectRegisters(this.context, ['rcx', 'rdx', 'r8', 'r9', 'rsp']),
        arguments: collectCallArguments(this.context)
      };
      if (enableMissingIndexedTableGuard && callerSiteRvas[index] === guardCallerSiteRva) {
        snapshot.guardDecision = decideMissingIndexedTableGuard(snapshot.arguments);
      }
      const threadSnapshot = threadSnapshots[threadId] || {};
      threadSnapshot.latestCallerSite = snapshot;
      threadSnapshots[threadId] = threadSnapshot;
      send(snapshot);
      if (snapshot.guardDecision && snapshot.guardDecision.shouldSkip) {
        send({
          category: 'client.crash-probe',
          action: 'caller-guard-skip',
          threadId: threadId,
          timestampMs: nowMs(),
          callerSiteIndex: index,
          callerSiteRva: snapshot.callerSiteRva,
          callerSiteAddress: snapshot.callerSiteAddress,
          guardDecision: snapshot.guardDecision,
          arguments: snapshot.arguments
        });
        this.context.rax = ptr('0x1');
        if (this.context.rip !== undefined) {
          this.context.rip = guardResumeAddress;
        }
        if (this.context.pc !== undefined) {
          this.context.pc = guardResumeAddress;
        }
      }
    }
  });
});

tryAttach(functionStart, 'function-start', {
  functionStartRva: '0x' + functionStartRva.toString(16)
}, {
  onEnter(args) {
    const threadId = Process.getCurrentThreadId();
    const threadSnapshot = threadSnapshots[threadId] || {};
    const snapshot = {
      category: 'client.crash-probe',
      action: 'function-enter',
      threadId: threadId,
      timestampMs: nowMs(),
      functionStart: ptrToHex(functionStart),
      registers: collectRegisters(this.context, ['rcx', 'rdx', 'r8', 'r9', 'r12', 'r13', 'r14', 'r15', 'rbx', 'rsi', 'rdi', 'rsp', 'rbp']),
      arguments: collectEntryArguments(this.context),
      latestCallerSite: threadSnapshot.latestCallerSite || null,
      backtrace: collectBacktrace(this.context)
    };
    const callerCallSiteRva = snapshot.arguments.callerCallSiteRva || null;
    snapshot.forceSuccessEligible = callerCallSiteRva !== null && forceSuccessCallerSiteSet[callerCallSiteRva] === true;
    this.forceSuccessCallerSite = snapshot.forceSuccessEligible ? callerCallSiteRva : null;
    threadSnapshots[threadId] = snapshot;
    send(snapshot);
  },
  onLeave(retval) {
    const threadId = Process.getCurrentThreadId();
    const threadSnapshot = threadSnapshots[threadId] || null;
    const returnValueBefore = ptrToHex(retval);
    const returnValueBeforeU32 = ptr(retval).toUInt32();
    const callerCallSite = threadSnapshot && threadSnapshot.arguments
      ? (threadSnapshot.arguments.callerCallSite || null)
      : null;
    const callerCallSiteRva = threadSnapshot && threadSnapshot.arguments
      ? (threadSnapshot.arguments.callerCallSiteRva || null)
      : null;

    send({
      category: 'client.crash-probe',
      action: 'function-leave',
      threadId: threadId,
      timestampMs: nowMs(),
      functionStart: ptrToHex(functionStart),
      callerCallSite: callerCallSite,
      callerCallSiteRva: callerCallSiteRva,
      returnValueBefore: returnValueBefore,
      returnValueBeforeU32: returnValueBeforeU32
    });

    if (this.forceSuccessCallerSite !== null && returnValueBeforeU32 === 0) {
      retval.replace(ptr('0x1'));
      send({
        category: 'client.crash-probe',
        action: 'forced-success-return',
        threadId: threadId,
        timestampMs: nowMs(),
        functionStart: ptrToHex(functionStart),
        callerCallSite: this.forceSuccessCallerSite,
        callerCallSiteRva: this.forceSuccessCallerSite,
        returnValueBefore: returnValueBefore,
        returnValueBeforeU32: returnValueBeforeU32,
        returnValueAfter: '0x1',
        returnValueAfterU32: 1
      });
    }
  }
});

tryAttach(stateCaptureAddress, 'state-capture', {
  stateCaptureRva: '0x' + stateCaptureRva.toString(16)
}, {
  onEnter(args) {
    const threadId = Process.getCurrentThreadId();
    const repair = maybeRepairR15(this.context);
    const snapshot = {
      category: 'client.crash-probe',
      action: 'state-checkpoint',
      threadId: threadId,
      timestampMs: nowMs(),
      stateCaptureAddress: ptrToHex(stateCaptureAddress),
      registers: collectRegisters(this.context, ['r10', 'r11', 'r14', 'r15', 'rdi', 'rbx', 'rsi', 'rsp', 'rbp']),
      r14State: classifyPointer(this.context.r14),
      r15State: classifyPointer(this.context.r15)
    };
    const threadSnapshot = threadSnapshots[threadId] || {};
    threadSnapshot.latestStateCheckpoint = snapshot;
    threadSnapshots[threadId] = threadSnapshot;
    if (repair !== null) {
      send({
        category: 'client.crash-probe',
        action: 'state-repair-applied',
        threadId: threadId,
        timestampMs: nowMs(),
        stateCaptureAddress: ptrToHex(stateCaptureAddress),
        repair: repair
      });
    }
    send(snapshot);
  }
});

extraCheckpointAddresses.forEach(function(entry) {
  tryAttach(entry.address, 'extra-checkpoint', {
    checkpointName: entry.name,
    checkpointRva: '0x' + entry.rva.toString(16)
  }, {
    onEnter(args) {
      const threadId = Process.getCurrentThreadId();
      const threadSnapshot = threadSnapshots[threadId] || {};
      const epilogueRepair = entry.name === 'epilogue-prep'
        ? maybeRepairEpilogueFrame(this.context, threadSnapshot)
        : null;
      const releaseRepair = entry.name === 'release-prep'
        ? maybeRepairReleaseFrame(this.context, threadSnapshot)
        : null;
      const snapshot = {
        category: 'client.crash-probe',
        action: 'branch-checkpoint',
        checkpointName: entry.name,
        checkpointRva: '0x' + entry.rva.toString(16),
        checkpointAddress: ptrToHex(entry.address),
        threadId: threadId,
        timestampMs: nowMs(),
        registers: collectRegisters(this.context, ['rax', 'rbx', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r12', 'r14', 'r15', 'rdi', 'rsi', 'rsp', 'rbp']),
        registerU32: collectRegisterU32(this.context, ['rax', 'rbx', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r12', 'r14', 'r15']),
        r14State: classifyPointer(this.context.r14),
        r15State: classifyPointer(this.context.r15),
        rcxState: classifyPointer(this.context.rcx),
        rdxState: classifyPointer(this.context.rdx),
        stackObjectDetails: collectStackObjectDetails(this.context, stackOffsetsForCheckpoint(entry.name))
      };
      if (epilogueRepair !== null) {
        snapshot.epilogueFrameRepair = epilogueRepair;
      }
      if (releaseRepair !== null) {
        snapshot.releaseFrameRepair = releaseRepair;
      }
      threadSnapshot['checkpoint:' + entry.name] = snapshot;
      threadSnapshots[threadId] = threadSnapshot;
      if (epilogueRepair !== null) {
        send({
          category: 'client.crash-probe',
          action: 'epilogue-frame-repair-applied',
          threadId: threadId,
          timestampMs: nowMs(),
          checkpointName: entry.name,
          checkpointRva: '0x' + entry.rva.toString(16),
          repair: epilogueRepair
        });
      }
      if (releaseRepair !== null) {
        send({
          category: 'client.crash-probe',
          action: 'release-frame-repair-applied',
          threadId: threadId,
          timestampMs: nowMs(),
          checkpointName: entry.name,
          checkpointRva: '0x' + entry.rva.toString(16),
          repair: releaseRepair
        });
      }
      send(snapshot);
    }
  });
});

Process.setExceptionHandler(function(details) {
  const threadId = Process.getCurrentThreadId();
  const genericEvent = {
    category: 'client.exception',
    action: 'fault',
    threadId: threadId,
    exceptionType: details.type,
    address: ptrToHex(details.address),
    context: collectRegisters(
      details.context,
      ['rip', 'rsp', 'rbp', 'rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15']
    ),
    backtrace: collectBacktrace(details.context)
  };

  if (details.memory !== undefined && details.memory !== null) {
    genericEvent.memory = {
      operation: details.memory.operation,
      address: ptrToHex(details.memory.address)
    };
  }
  genericEvent.instruction = describeInstruction(details.address);
  genericEvent.instructionBytes = safeReadBytes(details.address, 16);

  send(genericEvent);

  const entrySnapshot = threadSnapshots[threadId] || null;

  if (entrySnapshot !== null) {
    send({
      category: 'client.crash-probe',
      action: 'inflight-function-fault',
      threadId: threadId,
      exceptionType: details.type,
      address: ptrToHex(details.address),
      functionStart: ptrToHex(functionStart),
      deltaMsFromEntry: entrySnapshot.timestampMs !== undefined ? (nowMs() - entrySnapshot.timestampMs) : null,
      entrySnapshot: entrySnapshot,
      latestStateCheckpoint: entrySnapshot.latestStateCheckpoint || null,
      latestCallerSite: entrySnapshot.latestCallerSite || null,
      checkpointBadPathEdge: entrySnapshot['checkpoint:bad-path-edge'] || null,
      checkpointReleasePrep: entrySnapshot['checkpoint:release-prep'] || null,
      checkpointReleaseCall8: entrySnapshot['checkpoint:release-call-8'] || null,
      checkpointReleaseCall10: entrySnapshot['checkpoint:release-call-10'] || null,
      checkpointEpiloguePrep: entrySnapshot['checkpoint:epilogue-prep'] || null,
      liveR14State: classifyPointer(details.context.r14),
      liveR15State: classifyPointer(details.context.r15)
    });
  }

  if (ptr(details.address).equals(faultAddress)) {
    send({
      category: 'client.crash-probe',
      action: 'fault-family-match',
      threadId: threadId,
      exceptionType: details.type,
      address: ptrToHex(details.address),
      faultAddress: ptrToHex(faultAddress),
      deltaMsFromEntry: entrySnapshot !== null ? (nowMs() - entrySnapshot.timestampMs) : null,
      entrySnapshot: entrySnapshot,
      latestStateCheckpoint: entrySnapshot !== null ? (entrySnapshot.latestStateCheckpoint || null) : null,
      liveR14State: classifyPointer(details.context.r14),
      liveR15State: classifyPointer(details.context.r15)
    });
  }

  return false;
});
"""
    return (
        template.replace("__MODULE__", module_name)
        .replace("__FUNCTION_START__", f"0x{function_start_rva:x}")
        .replace("__FAULT_RVA__", f"0x{fault_rva:x}")
        .replace("__STATE_CAPTURE_RVA__", f"0x{state_capture_rva:x}")
        .replace("__TRACKED_OFFSETS__", offsets_js)
        .replace("__INDEXED_TABLE_SLOT_OFFSET__", f"0x{indexed_table_slot_offset:x}")
        .replace("__REPAIR_R15__", "true" if repair_r15_at_state_capture else "false")
        .replace("__REPAIR_EPILOGUE_FRAME__", "true" if repair_epilogue_frame else "false")
        .replace("__REPAIR_RELEASE_FRAME__", "true" if repair_release_frame else "false")
        .replace("__ENABLE_MISSING_INDEXED_TABLE_GUARD__", "true" if enable_missing_indexed_table_guard else "false")
        .replace("__GUARD_CALLER_SITE_RVA__", f"0x{guard_caller_site_rva:x}")
        .replace("__GUARD_RESUME_RVA__", f"0x{guard_resume_rva:x}")
        .replace("__CALLER_SITES__", caller_sites_js)
        .replace("__FORCE_SUCCESS_CALLER_SITES__", force_success_sites_js)
        .replace("__REPAIR_EPILOGUE_FRAME_CALLER_SITES__", repair_epilogue_frame_sites_js)
        .replace("__REPAIR_RELEASE_FRAME_CALLER_SITES__", repair_release_frame_sites_js)
        .replace("__EXTRA_CHECKPOINTS__", extra_checkpoints_js)
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attach a focused Frida crash probe to the known 947 pre-login crash family."
    )
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--latest-output", type=Path, default=DEFAULT_LATEST_OUTPUT)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--module-name", default=DEFAULT_MODULE_NAME)
    parser.add_argument("--function-start-rva", type=parse_hex_int, default=DEFAULT_FUNCTION_START_RVA)
    parser.add_argument("--fault-rva", type=parse_hex_int, default=DEFAULT_FAULT_RVA)
    parser.add_argument("--state-capture-rva", type=parse_hex_int, default=DEFAULT_STATE_CAPTURE_RVA)
    parser.add_argument("--repair-r15-at-state-capture", action="store_true")
    parser.add_argument(
        "--repair-epilogue-frame",
        action="store_true",
        help=(
            "At the 0x5910f9 epilogue checkpoint, restore the corrupted nonvolatile-frame slots "
            "and return address from the function-entry snapshot for approved caller sites."
        ),
    )
    parser.add_argument(
        "--repair-release-frame",
        action="store_true",
        help=(
            "At the 0x594b4c release-prep checkpoint, restore implausible saved RBX/RBP slots "
            "from the function-entry snapshot for approved caller sites."
        ),
    )
    parser.add_argument("--enable-missing-indexed-table-guard", action="store_true")
    parser.add_argument("--guard-caller-site-rva", type=parse_hex_int, default=DEFAULT_GUARD_CALLER_SITE_RVA)
    parser.add_argument("--guard-resume-rva", type=parse_hex_int, default=DEFAULT_GUARD_RESUME_RVA)
    parser.add_argument(
        "--force-success-caller-site-rva",
        type=parse_hex_int,
        action="append",
        default=[],
        help="Optional caller-site RVA(s) for which a false return from FUN_140590bc0 should be rewritten to success.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    validate_probe_configuration(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.latest_output.parent.mkdir(parents=True, exist_ok=True)

    script_source = build_hook_script(
        module_name=args.module_name,
        function_start_rva=args.function_start_rva,
        fault_rva=args.fault_rva,
        state_capture_rva=args.state_capture_rva,
        tracked_offsets=DEFAULT_TRACKED_OFFSETS,
        indexed_table_slot_offset=DEFAULT_INDEXED_TABLE_SLOT_OFFSET,
        repair_r15_at_state_capture=args.repair_r15_at_state_capture,
        repair_epilogue_frame=args.repair_epilogue_frame,
        repair_release_frame=args.repair_release_frame,
        enable_missing_indexed_table_guard=args.enable_missing_indexed_table_guard,
        guard_caller_site_rva=args.guard_caller_site_rva,
        guard_resume_rva=args.guard_resume_rva,
        caller_site_rvas=DEFAULT_CALLER_SITE_RVAS,
        force_success_caller_site_rvas=tuple(args.force_success_caller_site_rva),
        extra_checkpoints=DEFAULT_EXTRA_CHECKPOINTS,
    )

    stop_event = threading.Event()
    output_paths = [args.output]
    if args.latest_output != args.output:
        output_paths.append(args.latest_output)

    handles = [path.open("w", encoding="utf-8") for path in output_paths]
    try:
        def write_event(event: dict[str, object]) -> None:
            line = json.dumps(event, sort_keys=True)
            for handle in handles:
                handle.write(line + "\n")
                handle.flush()

        def on_message(message, data) -> None:
            if message.get("type") == "send":
                payload = message.get("payload", {})
                if isinstance(payload, dict):
                    payload.setdefault("timestamp", time.time())
                    write_event(payload)
                else:
                    write_event(
                        {
                            "category": "frida",
                            "action": "send",
                            "payload": payload,
                            "timestamp": time.time(),
                        }
                    )
                return

            write_event(
                {
                    "category": "frida",
                    "action": "message",
                    "message": message,
                    "timestamp": time.time(),
                }
            )

        session = frida.attach(args.pid)
        script = session.create_script(script_source)
        script.on("message", on_message)
        script.load()
        write_event(
            {
                "category": "client.lifecycle",
                "action": "attached",
                "pid": args.pid,
                "timestamp": time.time(),
            }
        )

        def on_detached(reason, crash) -> None:
            event: dict[str, object] = {
                "category": "client.lifecycle",
                "action": "detached",
                "reason": reason,
                "timestamp": time.time(),
            }
            if crash is not None:
                event["crash"] = crash
            write_event(event)
            stop_event.set()

        session.on("detached", on_detached)

        if args.duration_seconds > 0:
            stop_event.wait(args.duration_seconds)
        else:
            while not stop_event.is_set():
                time.sleep(0.25)

        try:
            script.unload()
        except frida.InvalidOperationError:
            pass

        try:
            session.detach()
        except frida.InvalidOperationError:
            pass
    finally:
        for handle in handles:
            handle.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
