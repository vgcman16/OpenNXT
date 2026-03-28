import argparse
import json
import sys
import threading
import time
from pathlib import Path

import frida


HOOK_SCRIPT = r"""
'use strict';

const hooks = new Set();

function findExport(moduleNames, exportName) {
  for (const moduleName of moduleNames) {
    const moduleObject = Process.findModuleByName(moduleName);
    if (moduleObject === null) {
      continue;
    }
    try {
      return moduleObject.getExportByName(exportName);
    } catch (error) {
    }
  }
  return null;
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

function readUtf16Maybe(address) {
  if (address.isNull()) {
    return null;
  }
  try {
    return Memory.readUtf16String(address);
  } catch (error) {
    return '<unreadable-utf16>';
  }
}

function readUtf8Maybe(address) {
  if (address.isNull()) {
    return null;
  }
  try {
    return Memory.readUtf8String(address);
  } catch (error) {
    return '<unreadable-utf8>';
  }
}

function readPolicyOid(address) {
  if (address.isNull()) {
    return null;
  }
  const numeric = address.toUInt32();
  if (numeric !== 0 && numeric < 0x10000) {
    return 'oid#' + numeric;
  }
  return readUtf8Maybe(address);
}

function readChainStatus(chainContextPtr) {
  if (chainContextPtr.isNull()) {
    return null;
  }
  try {
    return {
      errorStatus: Memory.readU32(chainContextPtr.add(4)),
      infoStatus: Memory.readU32(chainContextPtr.add(8)),
      chainCount: Memory.readU32(chainContextPtr.add(12)),
    };
  } catch (error) {
    return { error: String(error) };
  }
}

function readPolicyStatus(policyStatusPtr) {
  if (policyStatusPtr.isNull()) {
    return null;
  }
  try {
    return {
      error: Memory.readU32(policyStatusPtr.add(4)),
      chainIndex: Memory.readU32(policyStatusPtr.add(8)),
      elementIndex: Memory.readU32(policyStatusPtr.add(12)),
    };
  } catch (error) {
    return { error: String(error) };
  }
}

function emitEvent(event) {
  send(event);
}

function hookExport(moduleName, exportName, callbacks) {
  const key = moduleName + '!' + exportName;
  if (hooks.has(key)) {
    return true;
  }

  const address = findExport([moduleName], exportName);
  if (address === null) {
    return false;
  }

  Interceptor.attach(address, callbacks);
  hooks.add(key);
  emitEvent({ type: 'hooked', target: key, address: ptrToHex(address) });
  return true;
}

function installHooks() {
  hookExport('secur32.dll', 'AcquireCredentialsHandleW', {
    onEnter(args) {
      this.data = {
        type: 'AcquireCredentialsHandleW',
        principal: readUtf16Maybe(args[0]),
        packageName: readUtf16Maybe(args[1]),
        credentialUse: args[2].toUInt32(),
      };
    },
    onLeave(retval) {
      this.data.status = retval.toUInt32();
      emitEvent(this.data);
    }
  });

  hookExport('secur32.dll', 'InitializeSecurityContextW', {
    onEnter(args) {
      this.data = {
        type: 'InitializeSecurityContextW',
        targetName: readUtf16Maybe(args[2]),
        contextReq: args[3].toUInt32(),
        targetDataRep: args[5].toUInt32(),
        inputDesc: ptrToHex(args[6]),
        outputDesc: ptrToHex(args[9]),
      };
    },
    onLeave(retval) {
      this.data.status = retval.toUInt32();
      emitEvent(this.data);
    }
  });

  hookExport('crypt32.dll', 'CertGetCertificateChain', {
    onEnter(args) {
      this.chainOutPtr = args[7];
      this.data = {
        type: 'CertGetCertificateChain',
        flags: args[5].toUInt32(),
        certContext: ptrToHex(args[1]),
        chainOutPtr: ptrToHex(args[7]),
      };
    },
    onLeave(retval) {
      this.data.result = retval.toInt32();
      if (!this.chainOutPtr.isNull()) {
        try {
          const chainContextPtr = Memory.readPointer(this.chainOutPtr);
          this.data.chainContext = ptrToHex(chainContextPtr);
          this.data.chainStatus = readChainStatus(chainContextPtr);
        } catch (error) {
          this.data.chainStatus = { error: String(error) };
        }
      }
      emitEvent(this.data);
    }
  });

  hookExport('crypt32.dll', 'CertVerifyCertificateChainPolicy', {
    onEnter(args) {
      this.policyStatusPtr = args[3];
      this.data = {
        type: 'CertVerifyCertificateChainPolicy',
        policyOid: readPolicyOid(args[0]),
        chainContext: ptrToHex(args[1]),
        policyStatusPtr: ptrToHex(args[3]),
      };
    },
    onLeave(retval) {
      this.data.result = retval.toInt32();
      this.data.policyStatus = readPolicyStatus(this.policyStatusPtr);
      emitEvent(this.data);
    }
  });

  hookExport('crypt32.dll', 'WinVerifyTrust', {
    onEnter(args) {
      this.data = {
        type: 'WinVerifyTrust',
        hwnd: ptrToHex(args[0]),
        actionId: ptrToHex(args[1]),
        data: ptrToHex(args[2]),
      };
    },
    onLeave(retval) {
      this.data.status = retval.toUInt32();
      emitEvent(this.data);
    }
  });
}

installHooks();
setInterval(installHooks, 1000);
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attach Frida hooks to rs2client.exe TLS and certificate validation APIs."
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
            session.detach()
        except frida.InvalidOperationError:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
