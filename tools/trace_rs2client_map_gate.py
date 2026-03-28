from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import frida


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Attach focused Frida hooks to rs2client.exe and capture cache index lookups plus "
            "plaintext HTTP request/response lines relevant to scene/map loading."
        )
    )
    parser.add_argument("--pid", type=int, required=True, help="Process id of rs2client.exe")
    parser.add_argument("--output", required=True, help="Path to the JSONL output file")
    parser.add_argument(
        "--summary-output",
        help="Optional path to a JSON summary artifact",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=0,
        help="Optional maximum trace duration. 0 means wait until interrupted or detached.",
    )
    parser.add_argument(
        "--max-preview-bytes",
        type=int,
        default=192,
        help="Maximum plaintext bytes to preview from TLS application-data buffers.",
    )
    parser.add_argument("--verbose", action="store_true", help="Emit higher-volume cache data read events.")
    return parser.parse_args()


def build_hook_script(max_preview_bytes: int, verbose: bool) -> str:
    max_preview_literal = max(32, int(max_preview_bytes))
    verbose_literal = "true" if verbose else "false"
    script = r"""
'use strict';

const MAX_PREVIEW_BYTES = __MAX_PREVIEW_BYTES__;
const VERBOSE = __VERBOSE__;
const hooks = new Set();
const fileHandles = Object.create(null);

function nowSeconds() {
  return Date.now() / 1000.0;
}

function emit(category, action, details) {
  const payload = {
    category: category,
    action: action,
    timestamp: nowSeconds()
  };
  if (details) {
    Object.keys(details).forEach(function (key) {
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

function hookExport(moduleNames, exportName, callbacks) {
  const key = moduleNames.join('|') + '!' + exportName;
  if (hooks.has(key)) {
    return true;
  }
  const address = findExport(moduleNames, exportName);
  if (address === null) {
    return false;
  }
  Interceptor.attach(address, callbacks);
  hooks.add(key);
  emit('client.lifecycle', 'hook-installed', {
    target: key,
    address: ptrToHex(address)
  });
  return true;
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

function normalizePath(path) {
  return path === null || path === undefined ? '' : String(path);
}

function parseCacheFile(path) {
  const normalized = normalizePath(path).replace(/\//g, '\\');
  const lowered = normalized.toLowerCase();
  const idxMatch = lowered.match(/main_file_cache\.idx(\d+)$/);
  if (idxMatch) {
    return {
      kind: 'idx',
      indexId: parseInt(idxMatch[1], 10),
      path: normalized
    };
  }
  if (lowered.endsWith('main_file_cache.dat2')) {
    return {
      kind: 'dat2',
      indexId: null,
      path: normalized
    };
  }
  if (lowered.endsWith('.jcache')) {
    return {
      kind: 'jcache',
      indexId: null,
      path: normalized
    };
  }
  return null;
}

function safeReadByteArray(address, length) {
  if (address.isNull() || length <= 0) {
    return null;
  }
  try {
    return Memory.readByteArray(address, length);
  } catch (error) {
    return null;
  }
}

function bytesToHex(bytes) {
  if (bytes === null) {
    return '';
  }
  return Array.from(new Uint8Array(bytes)).map(function (value) {
    return value.toString(16).padStart(2, '0');
  }).join('');
}

function bytesToAscii(bytes) {
  if (bytes === null) {
    return '';
  }
  let result = '';
  const view = new Uint8Array(bytes);
  for (let index = 0; index < view.length; index += 1) {
    const value = view[index];
    if (value === 0x0d || value === 0x0a || value === 0x09) {
      result += String.fromCharCode(value);
    } else if (value >= 0x20 && value <= 0x7e) {
      result += String.fromCharCode(value);
    } else {
      result += '.';
    }
  }
  return result;
}

function httpLineSummary(asciiPreview) {
  if (!asciiPreview) {
    return null;
  }
  const firstLine = asciiPreview.split(/\r?\n/, 1)[0] || '';
  if (!firstLine) {
    return null;
  }
  if (
    firstLine.startsWith('GET ') ||
    firstLine.startsWith('POST ') ||
    firstLine.startsWith('HEAD ') ||
    firstLine.startsWith('PUT ') ||
    firstLine.startsWith('DELETE ') ||
    firstLine.startsWith('OPTIONS ') ||
    firstLine.startsWith('HTTP/')
  ) {
    return firstLine;
  }
  return null;
}

function capturePlaintextBuffer(bufferPointer, byteCount) {
  const cappedLength = Math.min(byteCount, MAX_PREVIEW_BYTES);
  const raw = safeReadByteArray(bufferPointer, cappedLength);
  const asciiPreview = bytesToAscii(raw);
  return {
    bytes: byteCount,
    previewBytes: cappedLength,
    asciiPreview: asciiPreview,
    hexPreview: bytesToHex(raw),
    firstLine: httpLineSummary(asciiPreview)
  };
}

function summarizeSecBufferDesc(descPtr, includePlaintext) {
  if (descPtr.isNull()) {
    return null;
  }
  try {
    const version = Memory.readU32(descPtr);
    const bufferCount = Memory.readU32(descPtr.add(4));
    const buffersPtr = Memory.readPointer(descPtr.add(8));
    const elementSize = 8 + Process.pointerSize;
    const buffers = [];
    let totalBytes = 0;
    const cappedCount = Math.min(bufferCount, 8);
    for (let index = 0; index < cappedCount; index += 1) {
      const bufferPtr = buffersPtr.add(index * elementSize);
      const byteCount = Memory.readU32(bufferPtr);
      const bufferType = Memory.readU32(bufferPtr.add(4));
      const dataPointer = Memory.readPointer(bufferPtr.add(8));
      totalBytes += byteCount;
      const summary = {
        index: index,
        bytes: byteCount,
        bufferType: bufferType,
        dataPointer: ptrToHex(dataPointer)
      };
      if (includePlaintext && bufferType === 1 && byteCount > 0) {
        summary.plaintext = capturePlaintextBuffer(dataPointer, byteCount);
      }
      buffers.push(summary);
    }
    return {
      version: version,
      bufferCount: bufferCount,
      totalBytes: totalBytes,
      buffers: buffers
    };
  } catch (error) {
    return { error: String(error) };
  }
}

function emitHttpEvents(sourceAction, bufferSummary) {
  if (!bufferSummary || !bufferSummary.buffers) {
    return;
  }
  bufferSummary.buffers.forEach(function (buffer) {
    const plaintext = buffer.plaintext;
    if (!plaintext || !plaintext.firstLine) {
      return;
    }
    const details = {
      firstLine: plaintext.firstLine,
      asciiPreview: plaintext.asciiPreview,
      hexPreview: plaintext.hexPreview,
      bytes: buffer.bytes,
      previewBytes: plaintext.previewBytes,
      sourceAction: sourceAction
    };
    if (plaintext.firstLine.startsWith('HTTP/')) {
      emit('client.http', 'response', details);
    } else {
      emit('client.http', 'request', details);
    }
  });
}

function currentOffsetForMove(file, moveMethod, distance) {
  if (moveMethod === 0) {
    return distance;
  }
  if (moveMethod === 1) {
    const base = file.position === null || file.position === undefined ? 0 : file.position;
    return base + distance;
  }
  return null;
}

function installFileHooks() {
  hookExport(['kernel32.dll', 'kernelbase.dll'], 'CreateFileW', {
    onEnter(args) {
      this.path = readUtf16Maybe(args[0]);
    },
    onLeave(retval) {
      const handleKey = ptrToHex(retval);
      if (handleKey === '0xffffffffffffffff' || handleKey === '0xffffffff') {
        return;
      }
      const cacheFile = parseCacheFile(this.path);
      if (!cacheFile) {
        return;
      }
      fileHandles[handleKey] = {
        path: cacheFile.path,
        kind: cacheFile.kind,
        indexId: cacheFile.indexId,
        position: 0,
        bytesRead: 0
      };
      emit('client.cache', 'open', {
        handle: handleKey,
        path: cacheFile.path,
        cacheKind: cacheFile.kind,
        indexId: cacheFile.indexId
      });
    }
  });

  hookExport(['kernel32.dll', 'kernelbase.dll'], 'SetFilePointerEx', {
    onEnter(args) {
      this.handleKey = ptrToHex(args[0]);
      this.distancePtr = args[1];
      this.newPointerPtr = args[2];
      this.moveMethod = args[3].toUInt32();
    },
    onLeave(retval) {
      if (retval.toInt32() === 0) {
        return;
      }
      const file = fileHandles[this.handleKey];
      if (!file) {
        return;
      }
      let distance = 0;
      try {
        distance = Memory.readS64(this.distancePtr);
      } catch (error) {
        distance = 0;
      }
      let newPosition = null;
      try {
        if (!this.newPointerPtr.isNull()) {
          newPosition = Memory.readS64(this.newPointerPtr);
        }
      } catch (error) {
        newPosition = null;
      }
      if (newPosition === null) {
        newPosition = currentOffsetForMove(file, this.moveMethod, distance);
      }
      file.position = newPosition;
      emit('client.cache', 'seek', {
        handle: this.handleKey,
        path: file.path,
        cacheKind: file.kind,
        indexId: file.indexId,
        moveMethod: this.moveMethod,
        position: newPosition
      });
    }
  });

  hookExport(['kernel32.dll', 'kernelbase.dll'], 'SetFilePointer', {
    onEnter(args) {
      this.handleKey = ptrToHex(args[0]);
      this.lowDistance = args[1].toInt32();
      this.highDistancePtr = args[2];
      this.moveMethod = args[3].toUInt32();
    },
    onLeave(retval) {
      const file = fileHandles[this.handleKey];
      if (!file) {
        return;
      }
      let highDistance = 0;
      try {
        if (!this.highDistancePtr.isNull()) {
          highDistance = Memory.readS32(this.highDistancePtr);
        }
      } catch (error) {
        highDistance = 0;
      }
      const distance = (highDistance * 0x100000000) + (this.lowDistance >>> 0);
      const newPosition = currentOffsetForMove(file, this.moveMethod, distance);
      file.position = newPosition;
      emit('client.cache', 'seek', {
        handle: this.handleKey,
        path: file.path,
        cacheKind: file.kind,
        indexId: file.indexId,
        moveMethod: this.moveMethod,
        position: newPosition
      });
    }
  });

  hookExport(['kernel32.dll', 'kernelbase.dll'], 'ReadFile', {
    onEnter(args) {
      this.handleKey = ptrToHex(args[0]);
      this.bytesReadOut = args[3];
      this.requested = args[2].toUInt32();
    },
    onLeave(retval) {
      if (retval.toInt32() === 0) {
        return;
      }
      const file = fileHandles[this.handleKey];
      if (!file) {
        return;
      }
      let actual = 0;
      try {
        if (!this.bytesReadOut.isNull()) {
          actual = Memory.readU32(this.bytesReadOut);
        }
      } catch (error) {
        actual = this.requested;
      }
      if (actual <= 0) {
        return;
      }
      const startOffset = file.position;
      file.bytesRead += actual;
      if (startOffset !== null && startOffset !== undefined) {
        file.position = startOffset + actual;
      }
      if (
        file.kind === 'idx' &&
        startOffset !== null &&
        startOffset !== undefined &&
        actual === 6 &&
        startOffset % 6 === 0
      ) {
        emit('client.cache', 'idx-lookup', {
          handle: this.handleKey,
          path: file.path,
          cacheKind: file.kind,
          indexId: file.indexId,
          offset: startOffset,
          archiveId: startOffset / 6,
          bytes: actual
        });
        return;
      }
      if (VERBOSE) {
        emit('client.cache', 'read', {
          handle: this.handleKey,
          path: file.path,
          cacheKind: file.kind,
          indexId: file.indexId,
          offset: startOffset,
          bytes: actual,
          totalBytesRead: file.bytesRead
        });
      }
    }
  });

  hookExport(['kernel32.dll', 'kernelbase.dll'], 'CloseHandle', {
    onEnter(args) {
      this.handleKey = ptrToHex(args[0]);
      this.file = fileHandles[this.handleKey] || null;
    },
    onLeave(retval) {
      if (!this.file) {
        return;
      }
      emit('client.cache', 'close', {
        handle: this.handleKey,
        path: this.file.path,
        cacheKind: this.file.kind,
        indexId: this.file.indexId,
        totalBytesRead: this.file.bytesRead
      });
      delete fileHandles[this.handleKey];
    }
  });
}

function installTlsHooks() {
  hookExport(['secur32.dll', 'sspicli.dll'], 'EncryptMessage', {
    onEnter(args) {
      this.data = {
        bufferSummary: summarizeSecBufferDesc(args[2], true),
        sequenceNo: args[3].toUInt32(),
        api: 'EncryptMessage'
      };
      emitHttpEvents('encrypt-message', this.data.bufferSummary);
    },
    onLeave(retval) {
      this.data.status = retval.toUInt32();
      emit('client.tls', 'encrypt-message', this.data);
    }
  });

  hookExport(['secur32.dll', 'sspicli.dll'], 'DecryptMessage', {
    onEnter(args) {
      this.descPtr = args[1];
      this.qopPtr = args[3];
      this.sequenceNo = args[2].toUInt32();
    },
    onLeave(retval) {
      const data = {
        bufferSummary: summarizeSecBufferDesc(this.descPtr, true),
        sequenceNo: this.sequenceNo,
        api: 'DecryptMessage',
        status: retval.toUInt32()
      };
      if (!this.qopPtr.isNull()) {
        try {
          data.qualityOfProtection = Memory.readU32(this.qopPtr);
        } catch (error) {
          data.qualityOfProtectionError = String(error);
        }
      }
      emitHttpEvents('decrypt-message', data.bufferSummary);
      emit('client.tls', 'decrypt-message', data);
    }
  });
}

installFileHooks();
installTlsHooks();
setInterval(function () {}, 1000);
"""
    return script.replace("__MAX_PREVIEW_BYTES__", str(max_preview_literal)).replace("__VERBOSE__", verbose_literal)


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault("category", "client.unknown")
    normalized.setdefault("action", "event")
    normalized.setdefault("timestamp", time.time())
    return normalized


def empty_summary() -> dict[str, Any]:
    return {
        "eventCount": 0,
        "idxLookupCount": 0,
        "idxLookupsByIndex": Counter(),
        "idxArchiveIdsByIndex": defaultdict(set),
        "httpRequestCount": 0,
        "httpResponseCount": 0,
        "httpMsRequestCount": 0,
        "httpNonReferenceRequestCount": 0,
        "requestLines": Counter(),
    }


def update_summary(summary: dict[str, Any], payload: dict[str, Any]) -> None:
    summary["eventCount"] += 1
    category = payload.get("category")
    action = payload.get("action")
    if category == "client.cache" and action == "idx-lookup":
        index_id = str(payload.get("indexId"))
        archive_id = payload.get("archiveId")
        summary["idxLookupCount"] += 1
        summary["idxLookupsByIndex"][index_id] += 1
        if archive_id is not None:
            summary["idxArchiveIdsByIndex"][index_id].add(int(archive_id))
        return
    if category == "client.http" and action in {"request", "response"}:
        first_line = str(payload.get("firstLine") or "")
        if action == "request":
            summary["httpRequestCount"] += 1
            summary["requestLines"][first_line] += 1
            if "/ms?" in first_line:
                summary["httpMsRequestCount"] += 1
                if "a=255" not in first_line:
                    summary["httpNonReferenceRequestCount"] += 1
        else:
            summary["httpResponseCount"] += 1


def finalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventCount": summary["eventCount"],
        "idxLookupCount": summary["idxLookupCount"],
        "idxLookupsByIndex": dict(summary["idxLookupsByIndex"]),
        "idxArchiveIdsByIndex": {
            index_id: sorted(values)
            for index_id, values in summary["idxArchiveIdsByIndex"].items()
        },
        "httpRequestCount": summary["httpRequestCount"],
        "httpResponseCount": summary["httpResponseCount"],
        "httpMsRequestCount": summary["httpMsRequestCount"],
        "httpNonReferenceRequestCount": summary["httpNonReferenceRequestCount"],
        "topRequestLines": summary["requestLines"].most_common(10),
    }


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if args.summary_output:
        Path(args.summary_output).parent.mkdir(parents=True, exist_ok=True)

    stop_event = threading.Event()
    summary = empty_summary()

    with output_path.open("w", encoding="utf-8") as handle:
        def write_event(payload: dict[str, Any]) -> None:
            normalized = normalize_payload(payload)
            update_summary(summary, normalized)
            handle.write(json.dumps(normalized, sort_keys=True) + "\n")
            handle.flush()

        def on_message(message: dict[str, Any], data: Any) -> None:
            if message.get("type") == "send":
                payload = message.get("payload", {})
                if isinstance(payload, dict):
                    write_event(payload)
                else:
                    write_event({"category": "client.frida", "action": "send", "payload": payload})
                return
            write_event({"category": "client.frida", "action": "message", "message": message})

        session = frida.attach(args.pid)
        script = session.create_script(build_hook_script(args.max_preview_bytes, args.verbose))
        script.on("message", on_message)
        script.load()

        def on_detached(reason: str, crash: Any) -> None:
            write_event({"category": "client.lifecycle", "action": "detached", "reason": reason, "crash": crash})
            stop_event.set()

        session.on("detached", on_detached)

        if args.duration_seconds > 0:
            deadline = time.monotonic() + args.duration_seconds
            while not stop_event.is_set() and time.monotonic() < deadline:
                time.sleep(0.1)
        else:
            while not stop_event.is_set():
                time.sleep(0.1)

        try:
            script.unload()
        except Exception:
            pass
        try:
            session.detach()
        except Exception:
            pass

    if args.summary_output:
        Path(args.summary_output).write_text(
            json.dumps(finalize_summary(summary), indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
