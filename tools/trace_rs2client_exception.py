import argparse
import json
import threading
import time
from pathlib import Path

import frida


HOOK_SCRIPT = r"""
'use strict';

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

function collectContext(context) {
  const registers = [
    'rip', 'rsp', 'rbp',
    'rax', 'rbx', 'rcx', 'rdx',
    'rsi', 'rdi',
    'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15'
  ];
  const snapshot = {};

  for (const registerName of registers) {
    if (context[registerName] !== undefined) {
      snapshot[registerName] = ptrToHex(context[registerName]);
    }
  }

  return snapshot;
}

function formatFrame(address) {
  const pointerValue = ptr(address);
  const symbol = DebugSymbol.fromAddress(pointerValue);
  return {
    address: ptrToHex(pointerValue),
    symbol: symbol !== null ? symbol.toString() : null
  };
}

send({ type: 'handler-installed' });

Process.setExceptionHandler(function (details) {
  const event = {
    type: 'exception',
    exceptionType: details.type,
    address: ptrToHex(details.address),
    context: collectContext(details.context)
  };

  if (details.memory !== undefined && details.memory !== null) {
    event.memory = {
      operation: details.memory.operation,
      address: ptrToHex(details.memory.address)
    };
  }

  try {
    event.backtrace = Thread.backtrace(details.context, Backtracer.ACCURATE).map(formatFrame);
  } catch (accurateError) {
    event.backtraceError = String(accurateError);
    try {
      event.backtrace = Thread.backtrace(details.context, Backtracer.FUZZY).map(formatFrame);
      event.backtraceMode = 'fuzzy';
    } catch (fuzzyError) {
      event.backtrace = [];
      event.backtraceFallbackError = String(fuzzyError);
    }
  }

  send(event);
  return false;
});
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attach a Frida exception handler to rs2client.exe and record crash details."
    )
    parser.add_argument("--pid", type=int, required=True, help="Process id of rs2client.exe")
    parser.add_argument("--output", required=True, help="Path to the trace output file")
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=0,
        help="Optional maximum trace duration. 0 means wait until interrupted or the target exits.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    stop_event = threading.Event()

    with output_path.open("w", encoding="utf-8") as handle:
        def write_event(event: dict) -> None:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
            handle.flush()

        def on_message(message, data) -> None:
            if message.get("type") == "send":
                payload = message.get("payload", {})
                if isinstance(payload, dict):
                    payload.setdefault("timestamp", time.time())
                    write_event(payload)
                else:
                    write_event({"type": "frida-send", "payload": payload, "timestamp": time.time()})
                return

            write_event({"type": "frida-message", "message": message, "timestamp": time.time()})

        session = frida.attach(args.pid)
        script = session.create_script(HOOK_SCRIPT)
        script.on("message", on_message)
        script.load()
        write_event({"type": "attached", "pid": args.pid, "timestamp": time.time()})

        def on_detached(reason, crash):
            event = {"type": "detached", "reason": reason, "timestamp": time.time()}
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
