from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import datetime
from pathlib import Path

import frida


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_DIR = WORKSPACE / "data" / "debug" / "frida-lobby-widget-probe" / "runs"
DEFAULT_LATEST_OUTPUT = WORKSPACE / "data" / "debug" / "frida-lobby-widget-probe" / "latest-client-only.jsonl"
DEFAULT_MODULE_NAME = "rs2client.exe"

DEFAULT_HOOKS: tuple[tuple[str, int], ...] = (
    ("if_button_router", 0x1A3600),
    ("if_buttont_sender", 0x169660),
    ("if_buttond_sender", 0x1A60D0),
    ("client_opcode_27_sender", 0x0E53E0),
    ("client_opcode_94_sender", 0x147D50),
)


def archive_probe_output_path(root: Path, when: datetime | None = None) -> Path:
    timestamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return root / f"947-lobby-widget-probe-{timestamp}.jsonl"


def parse_hex_int(value: str) -> int:
    return int(value, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Attach focused Frida hooks to the 947 lobby/widget sender family and archive "
            "semantic packet-side state for the contained post-login path."
        )
    )
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--module-name", default=DEFAULT_MODULE_NAME)
    parser.add_argument("--output", type=Path, default=DEFAULT_LATEST_OUTPUT)
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--duration-seconds", type=int, default=180)
    parser.add_argument(
        "--hook",
        action="append",
        default=[],
        help="Additional hook in name=rva form. Example: custom=0x123456",
    )
    return parser.parse_args()


def resolve_hooks(values: list[str]) -> list[tuple[str, int]]:
    hooks = list(DEFAULT_HOOKS)
    for raw_value in values:
        candidate = str(raw_value or "").strip()
        if not candidate:
            continue
        if "=" not in candidate:
            raise ValueError(f"Hook must use name=rva form: {candidate!r}")
        name, rva_text = candidate.split("=", 1)
        hooks.append((name.strip(), parse_hex_int(rva_text.strip())))
    return hooks


def build_hook_script(module_name: str, hooks: list[tuple[str, int]]) -> str:
    hooks_js = json.dumps([{"name": name, "rva": rva} for name, rva in hooks])
    template = r"""
'use strict';

const moduleName = "__MODULE__";
const hookSpecs = __HOOKS__;
const moduleObject = Process.getModuleByName(moduleName);
const eventCounters = Object.create(null);

function emit(action, details) {
  const payload = {
    timestamp: Date.now() / 1000.0,
    action: action
  };
  if (details) {
    Object.keys(details).forEach((key) => {
      payload[key] = details[key];
    });
  }
  send(payload);
}

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

function rvaOf(value) {
  try {
    const absolute = ptr(value);
    const delta = absolute.sub(moduleObject.base);
    return '0x' + delta.toString(16);
  } catch (error) {
    return null;
  }
}

function safeRange(address) {
  try {
    return Process.findRangeByAddress(ptr(address));
  } catch (error) {
    return null;
  }
}

function safeReadU8(address) {
  const pointerValue = ptr(address);
  const range = safeRange(pointerValue);
  if (range === null || range.protection.indexOf('r') === -1) {
    return null;
  }
  try {
    return pointerValue.readU8();
  } catch (error) {
    return null;
  }
}

function safeReadU16(address) {
  const pointerValue = ptr(address);
  const range = safeRange(pointerValue);
  if (range === null || range.protection.indexOf('r') === -1) {
    return null;
  }
  try {
    return pointerValue.readU16();
  } catch (error) {
    return null;
  }
}

function safeReadU32(address) {
  const pointerValue = ptr(address);
  const range = safeRange(pointerValue);
  if (range === null || range.protection.indexOf('r') === -1) {
    return null;
  }
  try {
    return pointerValue.readU32();
  } catch (error) {
    return null;
  }
}

function safeReadPointer(address) {
  const pointerValue = ptr(address);
  const range = safeRange(pointerValue);
  if (range === null || range.protection.indexOf('r') === -1) {
    return null;
  }
  try {
    return pointerValue.readPointer();
  } catch (error) {
    return null;
  }
}

function safeReadUtf8(address, limit) {
  const pointerValue = ptr(address);
  const range = safeRange(pointerValue);
  if (range === null || range.protection.indexOf('r') === -1) {
    return null;
  }
  try {
    return pointerValue.readUtf8String(limit || 96);
  } catch (error) {
    return null;
  }
}

function classifyValue(value) {
  try {
    const pointerValue = ptr(value);
    if (pointerValue.isNull()) {
      return 'null';
    }
    if (pointerValue.compare(ptr('0x10000')) < 0) {
      return 'tiny-scalar';
    }
    const range = safeRange(pointerValue);
    if (range === null) {
      return 'unmapped';
    }
    if (range.protection.indexOf('r') === -1) {
      return 'unreadable';
    }
    return 'pointer';
  } catch (error) {
    return 'opaque';
  }
}

function summarizeWidgetObject(pointerValue) {
  const pointerKind = classifyValue(pointerValue);
  const summary = {
    pointer: ptrToHex(pointerValue),
    kind: pointerKind
  };
  if (pointerKind !== 'pointer') {
    return summary;
  }

  const base = ptr(pointerValue);
  const interfaceId = safeReadU16(base.add(0x4c));
  const component = safeReadU16(base.add(0x50));
  const slotish = safeReadU16(base.add(0xb0));
  const selectedHashHi = safeReadU32(base.add(0x28c));
  const selectedHashLo = safeReadU32(base.add(0x290));
  const selectedSlotish = safeReadU32(base.add(0x294));
  const nestedPtr = safeReadPointer(base.add(8));

  summary.offsets = {
    off_0x4c_u16: interfaceId,
    off_0x50_u16: component,
    off_0xb0_u16: slotish,
    off_0x28c_u32: selectedHashHi,
    off_0x290_u32: selectedHashLo,
    off_0x294_u32: selectedSlotish,
    off_0x08_ptr: nestedPtr ? ptrToHex(nestedPtr) : null
  };

  if (interfaceId !== null && component !== null) {
    summary.interfaceHash = '0x' + (((interfaceId << 16) >>> 0) | component).toString(16);
    summary.interfaceId = interfaceId;
    summary.component = component;
  }

  if (nestedPtr) {
    const textPreview = safeReadUtf8(nestedPtr, 96);
    if (textPreview) {
      summary.nestedTextPreview = textPreview;
    }
  }

  return summary;
}

function summarizeArg(argValue) {
  const pointerText = ptrToHex(argValue);
  const kind = classifyValue(argValue);
  const summary = {
    value: pointerText,
    rva: kind === 'pointer' ? rvaOf(argValue) : null,
    kind: kind
  };
  if (kind === 'tiny-scalar' || kind === 'opaque' || kind === 'null') {
    try {
      summary.u64 = ptr(argValue).toUInt64().toString();
    } catch (error) {
      summary.u64 = null;
    }
    return summary;
  }
  summary.widget = summarizeWidgetObject(argValue);
  return summary;
}

function summarizeArgs(args, limit) {
  const items = [];
  const count = limit || 6;
  for (let index = 0; index < count; index += 1) {
    try {
      items.push({
        index: index,
        summary: summarizeArg(args[index])
      });
    } catch (error) {
      items.push({
        index: index,
        error: String(error)
      });
    }
  }
  return items;
}

function instructionSummary(address) {
  try {
    const instruction = Instruction.parse(ptr(address));
    return {
      address: ptrToHex(address),
      mnemonic: instruction.mnemonic,
      opStr: instruction.opStr,
      text: instruction.toString()
    };
  } catch (error) {
    return {
      address: ptrToHex(address),
      parseError: String(error)
    };
  }
}

hookSpecs.forEach((hookSpec) => {
  const hookAddress = moduleObject.base.add(hookSpec.rva);
  eventCounters[hookSpec.name] = 0;
  Interceptor.attach(hookAddress, {
    onEnter(args) {
      eventCounters[hookSpec.name] += 1;
      const returnAddress = this.returnAddress;
      let optionIndex = null;
      try {
        optionIndex = ptr(args[4]).toInt32();
      } catch (error) {
        optionIndex = null;
      }
      emit('hook-enter', {
        hookName: hookSpec.name,
        hookRva: '0x' + hookSpec.rva.toString(16),
        callCount: eventCounters[hookSpec.name],
        threadId: this.threadId,
        returnAddress: ptrToHex(returnAddress),
        returnRva: rvaOf(returnAddress),
        returnInstruction: instructionSummary(returnAddress),
        optionIndex: optionIndex,
        args: summarizeArgs(args, 6)
      });
    }
  });
  emit('hook-installed', {
    hookName: hookSpec.name,
    hookRva: '0x' + hookSpec.rva.toString(16),
    absoluteAddress: ptrToHex(hookAddress)
  });
});
"""
    return template.replace("__MODULE__", module_name).replace("__HOOKS__", hooks_js)


def main() -> int:
    args = parse_args()
    hooks = resolve_hooks(args.hook)
    args.archive_dir.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    archive_path = archive_probe_output_path(args.archive_dir)

    stop_event = threading.Event()
    session = frida.attach(args.pid)
    script = session.create_script(build_hook_script(args.module_name, hooks))

    with args.output.open("w", encoding="utf-8") as latest_handle, archive_path.open("w", encoding="utf-8") as archive_handle:
        def write_event(payload: dict) -> None:
            line = json.dumps(payload, sort_keys=True)
            latest_handle.write(line + "\n")
            latest_handle.flush()
            archive_handle.write(line + "\n")
            archive_handle.flush()

        def on_message(message: dict, data: bytes | None) -> None:
            if message.get("type") == "send":
                payload = message.get("payload")
                if isinstance(payload, dict):
                    write_event(payload)
                else:
                    write_event({"timestamp": time.time(), "action": "unexpected-send", "payload": payload})
                return
            write_event(
                {
                    "timestamp": time.time(),
                    "action": "frida-message",
                    "message": message,
                }
            )

        script.on("message", on_message)
        script.load()

        write_event(
            {
                "timestamp": time.time(),
                "action": "probe-started",
                "pid": args.pid,
                "moduleName": args.module_name,
                "archivePath": str(archive_path),
                "hooks": [{"name": name, "rva": f"0x{rva:x}"} for name, rva in hooks],
                "durationSeconds": args.duration_seconds,
            }
        )

        if args.duration_seconds > 0:
            stop_event.wait(args.duration_seconds)
        else:
            while not stop_event.is_set():
                time.sleep(0.25)

        write_event(
            {
                "timestamp": time.time(),
                "action": "probe-stop-requested",
                "pid": args.pid,
                "archivePath": str(archive_path),
            }
        )

    session.detach()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
