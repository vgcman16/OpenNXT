from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import frida


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attach deep live Frida hooks to rs2client.exe and write normalized JSONL events."
    )
    parser.add_argument("--pid", type=int, required=True, help="Process id of rs2client.exe")
    parser.add_argument("--output", required=True, help="Path to the JSONL output file")
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=0,
        help="Optional maximum trace duration. 0 means wait until interrupted or detached.",
    )
    parser.add_argument("--verbose", action="store_true", help="Emit higher-volume read/send/recv events.")
    return parser.parse_args()


def build_hook_script(
    verbose: bool,
    resolve_redirects: dict[str, str] | None = None,
    connect_redirects: dict[str, str] | None = None,
) -> str:
    verbose_literal = "true" if verbose else "false"
    normalized_redirects = {
        str(key).strip().lower(): str(value).strip()
        for key, value in (resolve_redirects or {}).items()
        if str(key).strip() and str(value).strip()
    }
    normalized_connect_redirects = {
        str(key).strip().lower(): str(value).strip()
        for key, value in (connect_redirects or {}).items()
        if str(key).strip() and str(value).strip()
    }
    script = r"""
'use strict';

const VERBOSE = __VERBOSE__;
const RESOLVE_REDIRECTS = __RESOLVE_REDIRECTS__;
const CONNECT_REDIRECTS = __CONNECT_REDIRECTS__;
const hooks = new Set();
const fileHandles = Object.create(null);
const socketStats = Object.create(null);
const emittedModuleKeys = new Set();
const emittedSnapshotBases = new Set();

function nowSeconds() {{
  return Date.now() / 1000.0;
}}

function normalizeRedirectHost(value) {{
  if (!value) {{
    return null;
  }}
  return String(value).trim().toLowerCase();
}}

function lookupResolveRedirect(hostValue) {{
  const normalized = normalizeRedirectHost(hostValue);
  if (!normalized) {{
    return null;
  }}
  if (Object.prototype.hasOwnProperty.call(RESOLVE_REDIRECTS, normalized)) {{
    return RESOLVE_REDIRECTS[normalized];
  }}
  return null;
}}

function maybeRewriteResolveArgument(args, index, wide, hostValue) {{
  const redirectTarget = lookupResolveRedirect(hostValue);
  if (!redirectTarget) {{
    return null;
  }}
  const redirectPointer = wide
    ? Memory.allocUtf16String(redirectTarget)
    : Memory.allocUtf8String(redirectTarget);
  args[index] = redirectPointer;
  return {{
    originalHost: hostValue,
    redirectedHost: redirectTarget,
    redirectPointer: redirectPointer
  }};
}}

function normalizeConnectTarget(value, family) {{
  if (!value) {{
    return null;
  }}
  const text = String(value).trim();
  if (!text) {{
    return null;
  }}
  if (text.toLowerCase() === 'localhost') {{
    return family === 'AF_INET6' ? '::1' : '127.0.0.1';
  }}
  return text;
}}

function lookupConnectRedirect(hostValue) {{
  const normalized = normalizeRedirectHost(hostValue);
  if (!normalized) {{
    return null;
  }}
  if (Object.prototype.hasOwnProperty.call(CONNECT_REDIRECTS, normalized)) {{
    return CONNECT_REDIRECTS[normalized];
  }}
  return null;
}}

function parseIpv4Address(value) {{
  const text = String(value || '').trim();
  if (!text) {{
    return null;
  }}
  const parts = text.split('.');
  if (parts.length !== 4) {{
    return null;
  }}
  const octets = [];
  for (let index = 0; index < parts.length; index += 1) {{
    const numeric = parseInt(parts[index], 10);
    if (!Number.isFinite(numeric) || numeric < 0 || numeric > 255) {{
      return null;
    }}
    octets.push(numeric);
  }}
  return octets;
}}

function maybeRewriteConnectSockaddr(sockaddrPointer, endpoint) {{
  if (!endpoint || !endpoint.host || !endpoint.family) {{
    return null;
  }}
  const redirectTarget = lookupConnectRedirect(endpoint.host);
  if (!redirectTarget) {{
    return null;
  }}
  const native = toNativePointer(sockaddrPointer);
  if (native === null || native.isNull()) {{
    return null;
  }}

  if (endpoint.family === 'AF_INET') {{
    const ipv4Target = normalizeConnectTarget(redirectTarget, endpoint.family);
    const octets = parseIpv4Address(ipv4Target);
    if (!octets) {{
      return null;
    }}
    try {{
      for (let index = 0; index < octets.length; index += 1) {{
        native.add(4 + index).writeU8(octets[index]);
      }}
      return {{
        originalHost: endpoint.host,
        redirectedHost: octets.join('.'),
        port: endpoint.port,
        family: endpoint.family
      }};
    }} catch (error) {{
      return null;
    }}
  }}

  if (endpoint.family === 'AF_INET6') {{
    const ipv6Target = normalizeConnectTarget(redirectTarget, endpoint.family);
    if (ipv6Target !== '::1') {{
      return null;
    }}
    try {{
      for (let index = 0; index < 16; index += 1) {{
        native.add(8 + index).writeU8(index === 15 ? 1 : 0);
      }}
      return {{
        originalHost: endpoint.host,
        redirectedHost: '::1',
        port: endpoint.port,
        family: endpoint.family
      }};
    }} catch (error) {{
      return null;
    }}
  }}

  return null;
}}

function emit(category, action, details) {{
  const payload = {{
    category: category,
    action: action,
    timestamp: nowSeconds()
  }};

  if (details) {{
    Object.keys(details).forEach(function (key) {{
      payload[key] = details[key];
    }});
  }}

  send(payload);
}}

function normalizeModuleName(path) {{
  if (!path) {{
    return null;
  }}
  const normalized = String(path).replace(/\//g, '\\');
  const segments = normalized.split('\\');
  return segments.length > 0 ? segments[segments.length - 1] : normalized;
}}

function moduleInteresting(name) {{
  if (!name) {{
    return false;
  }}
  const text = String(name).toLowerCase();
  return (
    text === 'rs2client.exe' ||
    text.indexOf('cef') !== -1 ||
    text.indexOf('chrome') !== -1 ||
    text.indexOf('ssl') !== -1 ||
    text.indexOf('crypto') !== -1 ||
    text.indexOf('curl') !== -1 ||
    text.indexOf('winhttp') !== -1 ||
    text.indexOf('wininet') !== -1 ||
    text.indexOf('schannel') !== -1 ||
    text.indexOf('secur32') !== -1 ||
    text.indexOf('sspicli') !== -1 ||
    text.indexOf('crypt32') !== -1 ||
    text.indexOf('libeay') !== -1 ||
    text.indexOf('ssleay') !== -1 ||
    text.indexOf('nss3') !== -1 ||
    text.indexOf('boringssl') !== -1 ||
    text.indexOf('d3d') !== -1 ||
    text.indexOf('dxgi') !== -1 ||
    text.indexOf('opengl') !== -1 ||
    text.indexOf('angle') !== -1 ||
    text.indexOf('nv') !== -1 ||
    text.indexOf('igd') !== -1 ||
    text.indexOf('igc') !== -1 ||
    text.indexOf('intel') !== -1 ||
    text.indexOf('gles') !== -1
  );
}}

function ptrToHex(value) {{
  if (value === null || value === undefined) {{
    return '0x0';
  }}

  try {{
    return ptr(value).toString();
  }} catch (error) {{
    return String(value);
  }}
}}

function toNativePointer(value) {{
  try {{
    return ptr(value);
  }} catch (error) {{
    return null;
  }}
}}

function findExport(moduleNames, exportName) {{
  for (const moduleName of moduleNames) {{
    const moduleObject = Process.findModuleByName(moduleName);
    if (moduleObject === null) {{
      continue;
    }}
    try {{
      return moduleObject.getExportByName(exportName);
    }} catch (error) {{
    }}
  }}
  return null;
}}

function readPointerMaybe(address) {{
  const native = toNativePointer(address);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    return native.readPointer();
  }} catch (error) {{
    return null;
  }}
}}

function readU8Maybe(address) {{
  const native = toNativePointer(address);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    return native.readU8();
  }} catch (error) {{
    return null;
  }}
}}

function readU16Maybe(address) {{
  const native = toNativePointer(address);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    return native.readU16();
  }} catch (error) {{
    return null;
  }}
}}

function readU32Maybe(address) {{
  const native = toNativePointer(address);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    return native.readU32();
  }} catch (error) {{
    return null;
  }}
}}

function readBoundedBytes(address, maxBytes) {{
  const native = toNativePointer(address);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    const range = Process.findRangeByAddress(native);
    if (range === null) {{
      return null;
    }}
    const end = ptr(range.base).add(range.size);
    let available = end.sub(native).toInt32();
    if (available <= 0) {{
      return null;
    }}
    if (available > maxBytes) {{
      available = maxBytes;
    }}
    return native.readByteArray(available);
  }} catch (error) {{
    return null;
  }}
}}

function decodeUtf16LeBytes(rawBytes) {{
  if (rawBytes === null) {{
    return null;
  }}
  const typed = new Uint8Array(rawBytes);
  const bytes = [];
  for (let index = 0; index < typed.length; index += 1) {{
    bytes.push(typed[index]);
  }}
  if (bytes.length < 2) {{
    return '';
  }}
  const chars = [];
  for (let index = 0; index + 1 < bytes.length; index += 2) {{
    const codeUnit = bytes[index] | (bytes[index + 1] << 8);
    if (codeUnit === 0) {{
      break;
    }}
    chars.push(String.fromCharCode(codeUnit));
  }}
  return chars.join('');
}}

function decodeUtf8Bytes(rawBytes) {{
  if (rawBytes === null) {{
    return null;
  }}
  const typed = new Uint8Array(rawBytes);
  const bytes = [];
  for (let index = 0; index < typed.length; index += 1) {{
    bytes.push(typed[index]);
  }}
  if (bytes.length === 0) {{
    return '';
  }}
  const codeUnits = [];
  for (let index = 0; index < bytes.length; index += 1) {{
    const value = bytes[index];
    if (value === 0) {{
      break;
    }}
    codeUnits.push(value);
  }}
  if (codeUnits.length === 0) {{
    return '';
  }}
  try {{
    return decodeURIComponent(escape(String.fromCharCode.apply(null, codeUnits)));
  }} catch (error) {{
    return String.fromCharCode.apply(null, codeUnits);
  }}
}}

function byteArrayToHex(rawBytes, maxBytes) {{
  if (rawBytes === null) {{
    return null;
  }}
  const typed = new Uint8Array(rawBytes);
  const limit = Math.min(typed.length, maxBytes);
  const hex = [];
  for (let index = 0; index < limit; index += 1) {{
    const value = typed[index].toString(16);
    hex.push(value.length === 1 ? '0' + value : value);
  }}
  return hex.join('');
}}

function byteArrayToPreviewText(rawBytes, maxBytes) {{
  if (rawBytes === null) {{
    return null;
  }}
  const typed = new Uint8Array(rawBytes);
  const limit = Math.min(typed.length, maxBytes);
  const chars = [];
  for (let index = 0; index < limit; index += 1) {{
    const value = typed[index];
    if (value === 0) {{
      break;
    }}
    if (value === 9 || value === 10 || value === 13 || (value >= 32 && value <= 126)) {{
      chars.push(String.fromCharCode(value));
    }} else {{
      chars.push('.');
    }}
  }}
  return chars.join('');
}}

function summarizeSocketChunk(bufferPointer, byteCount, previewLimit) {{
  const limit = previewLimit && previewLimit > 0 ? previewLimit : 256;
  const size = Math.max(0, Math.min(byteCount, limit));
  if (size <= 0) {{
    return null;
  }}
  const rawBytes = readBoundedBytes(bufferPointer, size);
  if (rawBytes === null) {{
    return null;
  }}
  const previewText = byteArrayToPreviewText(rawBytes, 256);
  const summary = {{
    previewHex: byteArrayToHex(rawBytes, 256),
    previewText: previewText
  }};
  if (previewText) {{
    const firstLine = previewText.split('\r\n', 1)[0].split('\n', 1)[0];
    if (firstLine) {{
      summary.firstLine = firstLine;
      if (
        firstLine.indexOf('GET ') === 0 ||
        firstLine.indexOf('POST ') === 0 ||
        firstLine.indexOf('HEAD ') === 0 ||
        firstLine.indexOf('CONNECT ') === 0 ||
        firstLine.indexOf('HTTP/') === 0
      ) {{
        summary.looksHttp = true;
      }}
    }}
  }}
  return summary;
}}

function readUtf16Direct(address) {{
  const native = toNativePointer(address);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    return native.readUtf16String();
  }} catch (error) {{
  }}

  const rawBytes = readBoundedBytes(native, 4096);
  const decoded = decodeUtf16LeBytes(rawBytes);
  if (decoded !== null && decoded.length > 0) {{
    return decoded;
  }}
  return null;
}}

function readUtf16Maybe(address) {{
  const native = toNativePointer(address);
  if (native === null || native.isNull()) {{
    return null;
  }}

  const direct = readUtf16Direct(native);
  if (direct !== null) {{
    return direct;
  }}

  let current = native;
  for (let depth = 0; depth < 2; depth += 1) {{
    const dereferenced = readPointerMaybe(current);
    if (dereferenced === null || dereferenced.isNull() || dereferenced.equals(current)) {{
      break;
    }}
    const indirect = readUtf16Direct(dereferenced);
    if (indirect !== null) {{
      return indirect;
    }}
    current = dereferenced;
  }}

  return '<unreadable-utf16@' + ptrToHex(native) + '>';
}}

function readUtf8Direct(address) {{
  const native = toNativePointer(address);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    return native.readUtf8String();
  }} catch (error) {{
  }}

  const rawBytes = readBoundedBytes(native, 2048);
  const decoded = decodeUtf8Bytes(rawBytes);
  if (decoded !== null && decoded.length > 0) {{
    return decoded;
  }}
  return null;
}}

function readUtf8Maybe(address) {{
  const native = toNativePointer(address);
  if (native === null || native.isNull()) {{
    return null;
  }}

  const direct = readUtf8Direct(native);
  if (direct !== null) {{
    return direct;
  }}

  let current = native;
  for (let depth = 0; depth < 2; depth += 1) {{
    const dereferenced = readPointerMaybe(current);
    if (dereferenced === null || dereferenced.isNull() || dereferenced.equals(current)) {{
      break;
    }}
    const indirect = readUtf8Direct(dereferenced);
    if (indirect !== null) {{
      return indirect;
    }}
    current = dereferenced;
  }}

  return '<unreadable-utf8@' + ptrToHex(native) + '>';
}}

function pathLooksUnreadable(path) {{
  if (path === null || path === undefined) {{
    return false;
  }}
  const text = String(path);
  return text.indexOf('<unreadable-utf16@') === 0 || text.indexOf('<unreadable-utf8@') === 0;
}}

function cleanResolvedPath(path) {{
  if (!path) {{
    return path;
  }}
  let text = String(path);
  if (text.indexOf('\\\\?\\UNC\\') === 0) {{
    text = '\\\\' + text.substring(8);
  }} else if (text.indexOf('\\\\?\\') === 0) {{
    text = text.substring(4);
  }}
  return text;
}}

const getFinalPathNameByHandleWAddress = findExport(['kernel32.dll', 'kernelbase.dll'], 'GetFinalPathNameByHandleW');
const getFinalPathNameByHandleW = getFinalPathNameByHandleWAddress !== null
  ? new NativeFunction(getFinalPathNameByHandleWAddress, 'uint32', ['pointer', 'pointer', 'uint32', 'uint32'])
  : null;

function resolveHandlePath(handleValue) {{
  if (getFinalPathNameByHandleW === null || handleValue.isNull()) {{
    return null;
  }}
  try {{
    const capacityChars = 2048;
    const buffer = Memory.alloc(capacityChars * 2);
    const copiedChars = getFinalPathNameByHandleW(handleValue, buffer, capacityChars, 0);
    if (!copiedChars || copiedChars >= capacityChars) {{
      return null;
    }}
    return cleanResolvedPath(buffer.readUtf16String());
  }} catch (error) {{
    return null;
  }}
}}

function moduleFromAddress(address) {{
  if (address.isNull()) {{
    return null;
  }}
  try {{
    return Process.findModuleByAddress(address);
  }} catch (error) {{
    return null;
  }}
}}

function emitModuleEvent(action, moduleObject, extraDetails) {{
  if (moduleObject === null) {{
    return;
  }}
  const moduleName = moduleObject.name || normalizeModuleName(moduleObject.path) || '<unknown>';
  if (action === 'snapshot') {{
    const snapshotKey = moduleObject.base.toString();
    if (emittedSnapshotBases.has(snapshotKey)) {{
      return;
    }}
    emittedSnapshotBases.add(snapshotKey);
  }} else {{
    const key = moduleObject.base.toString() + '|' + moduleName + '|' + action;
    if (emittedModuleKeys.has(key)) {{
      return;
    }}
    emittedModuleKeys.add(key);
  }}
  const details = {{
    moduleName: moduleName,
    path: moduleObject.path || moduleName,
    base: ptrToHex(moduleObject.base),
    size: moduleObject.size || 0,
    interesting: moduleInteresting(moduleName)
  }};
  if (extraDetails) {{
    Object.keys(extraDetails).forEach(function (keyName) {{
      details[keyName] = extraDetails[keyName];
    }});
  }}
  emit('client.module', action, details);
}}

function emitModuleSnapshot() {{
  try {{
    const modules = Process.enumerateModules();
    modules.forEach(function (moduleObject) {{
      const moduleName = moduleObject.name || normalizeModuleName(moduleObject.path);
      if (!moduleInteresting(moduleName)) {{
        return;
      }}
      emitModuleEvent('snapshot', moduleObject, null);
    }});
  }} catch (error) {{
    emit('client.module', 'snapshot-error', {{
      error: String(error)
    }});
  }}
}}

function readPolicyOid(address) {{
  if (address.isNull()) {{
    return null;
  }}
  try {{
    const numeric = address.toUInt32();
    if (numeric !== 0 && numeric < 0x10000) {{
      return 'oid#' + numeric;
    }}
  }} catch (error) {{
  }}
  return readUtf8Maybe(address);
}}

function normalizePath(path) {{
  if (path === null || path === undefined) {{
    return '';
  }}
  return String(path);
}}

function classifyPath(path) {{
  const text = normalizePath(path).toLowerCase();
  if (!text) {{
    return 'unknown';
  }}
  if (text.indexOf('shadercache') !== -1 || text.indexOf('dxcache') !== -1) {{
    return 'shadercache';
  }}
  if (
    text.indexOf('\\jagex\\') !== -1 ||
    text.indexOf('/jagex/') !== -1 ||
    text.indexOf('.jcache') !== -1 ||
    text.indexOf('objcache') !== -1
  ) {{
    return 'cache';
  }}
  if (
    text.indexOf('driverstore') !== -1 ||
    text.indexOf('d3dcompiler_47.dll') !== -1 ||
    text.indexOf('libegl.dll') !== -1 ||
    text.indexOf('libglesv2.dll') !== -1 ||
    text.indexOf('opengl32.dll') !== -1 ||
    text.indexOf('dxgi.dll') !== -1 ||
    text.indexOf('d3d11.dll') !== -1 ||
    text.indexOf('igd') !== -1 ||
    text.indexOf('nv') !== -1
  ) {{
    return 'graphics';
  }}
  if (text.indexOf('runescape') !== -1 || text.indexOf('rs2client') !== -1) {{
    return 'assets';
  }}
  if (text.indexOf('\\temp\\') !== -1 || text.indexOf('/temp/') !== -1 || text.indexOf('appdata\\\\local\\\\temp') !== -1) {{
    return 'temp';
  }}
  return 'unknown';
}}

function shouldEmitPathCategory(category) {{
  return VERBOSE || category !== 'unknown';
}}

function socketKey(value) {{
  try {{
    return String(value.toUInt32());
  }} catch (error) {{
    return ptrToHex(value);
  }}
}}

function ntohs(value) {{
  const masked = value & 0xffff;
  return ((masked & 0xff) << 8) | ((masked >> 8) & 0xff);
}}

function parseSockaddr(address) {{
  const native = toNativePointer(address);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    const family = native.readU16();
    if (family === 2) {{
      const portNetworkOrder = native.add(2).readU16();
      const octets = [];
      for (let i = 0; i < 4; i++) {{
        octets.push(native.add(4 + i).readU8());
      }}
      return {{
        family: 'AF_INET',
        host: octets.join('.'),
        port: ntohs(portNetworkOrder)
      }};
    }}
    if (family === 23) {{
      const portNetworkOrder = native.add(2).readU16();
      const segments = [];
      for (let i = 0; i < 16; i += 2) {{
        segments.push(native.add(8 + i).readU16().toString(16));
      }}
      return {{
        family: 'AF_INET6',
        host: segments.join(':'),
        port: ntohs(portNetworkOrder)
      }};
    }}
    return {{
      family: 'AF_' + family,
      host: null,
      port: null
    }};
  }} catch (error) {{
    return {{
      family: 'error',
      host: null,
      port: null,
      address: ptrToHex(native),
      error: String(error)
    }};
  }}
}}

function socketRecord(socketValue) {{
  const key = socketKey(socketValue);
  if (!socketStats[key]) {{
    socketStats[key] = {{
      socket: key,
      bytesSent: 0,
      bytesReceived: 0,
      remoteHost: null,
      remotePort: null,
      firstSendCaptured: false,
      firstRecvCaptured: false
    }};
  }}
  return socketStats[key];
}}

function emitSocketSummary(action, socketValue, details) {{
  const record = socketRecord(socketValue);
  const payload = {{
    socket: record.socket,
    remoteHost: record.remoteHost,
    remotePort: record.remotePort,
    bytesSent: record.bytesSent,
    bytesReceived: record.bytesReceived
  }};
  if (details) {{
    Object.keys(details).forEach(function (key) {{
      payload[key] = details[key];
    }});
  }}
  emit('client.net', action, payload);
}}

function readWsabuf(bufferPointer) {{
  const native = toNativePointer(bufferPointer);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    const length = native.readU32();
    const pointer = native.add(Process.pointerSize === 8 ? 8 : 4).readPointer();
    return {{
      length: length,
      pointer: pointer
    }};
  }} catch (error) {{
    return null;
  }}
}}

function readChainStatus(chainContextPtr) {{
  const native = toNativePointer(chainContextPtr);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    return {{
      errorStatus: native.add(4).readU32(),
      infoStatus: native.add(8).readU32(),
      chainCount: native.add(12).readU32()
    }};
  }} catch (error) {{
    return {{ error: String(error) }};
  }}
}}

function readPolicyStatus(policyStatusPtr) {{
  const native = toNativePointer(policyStatusPtr);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    return {{
      error: native.add(4).readU32(),
      chainIndex: native.add(8).readU32(),
      elementIndex: native.add(12).readU32()
    }};
  }} catch (error) {{
    return {{ error: String(error) }};
  }}
}}

function secPkgAttributeName(attribute) {{
  const lookup = {{
    0: 'SECPKG_ATTR_SIZES',
    1: 'SECPKG_ATTR_NAMES',
    2: 'SECPKG_ATTR_LIFESPAN',
    4: 'SECPKG_ATTR_STREAM_SIZES',
    14: 'SECPKG_ATTR_FLAGS',
    83: 'SECPKG_ATTR_REMOTE_CERT_CONTEXT',
    90: 'SECPKG_ATTR_CONNECTION_INFO'
  }};
  return lookup[attribute] || ('SECPKG_ATTR_' + attribute);
}}

function secBufferTypeName(bufferType) {{
  const dataType = bufferType & 0x0fffffff;
  const lookup = {{
    0: 'SECBUFFER_EMPTY',
    1: 'SECBUFFER_DATA',
    2: 'SECBUFFER_TOKEN',
    3: 'SECBUFFER_PKG_PARAMS',
    4: 'SECBUFFER_MISSING',
    5: 'SECBUFFER_EXTRA',
    6: 'SECBUFFER_STREAM_TRAILER',
    7: 'SECBUFFER_STREAM_HEADER',
    8: 'SECBUFFER_NEGOTIATION_INFO',
    9: 'SECBUFFER_PADDING',
    10: 'SECBUFFER_STREAM',
    11: 'SECBUFFER_MECHLIST',
    12: 'SECBUFFER_MECHLIST_SIGNATURE',
    13: 'SECBUFFER_TARGET',
    14: 'SECBUFFER_CHANNEL_BINDINGS',
    15: 'SECBUFFER_CHANGE_PASS_RESPONSE',
    16: 'SECBUFFER_TARGET_HOST'
  }};
  return lookup[dataType] || ('SECBUFFER_' + dataType);
}}

function readStreamSizes(attributeBufferPtr) {{
  const native = toNativePointer(attributeBufferPtr);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    return {{
      headerBytes: native.readU32(),
      trailerBytes: native.add(4).readU32(),
      maximumMessageBytes: native.add(8).readU32(),
      bufferCount: native.add(12).readU32(),
      blockSize: native.add(16).readU32()
    }};
  }} catch (error) {{
    return {{ error: String(error) }};
  }}
}}

function readConnectionInfo(attributeBufferPtr) {{
  const native = toNativePointer(attributeBufferPtr);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    return {{
      protocol: native.readU32(),
      cipherAlgorithm: native.add(4).readU32(),
      cipherStrength: native.add(8).readU32(),
      hashAlgorithm: native.add(12).readU32(),
      hashStrength: native.add(16).readU32(),
      exchangeAlgorithm: native.add(20).readU32(),
      exchangeStrength: native.add(24).readU32()
    }};
  }} catch (error) {{
    return {{ error: String(error) }};
  }}
}}

function readQueryContextAttribute(attribute, attributeBufferPtr, reader) {{
  if (attributeBufferPtr.isNull()) {{
    return null;
  }}
  try {{
    if (attribute === 1) {{
      const stringPointer = attributeBufferPtr.readPointer();
      return {{
        value: reader(stringPointer),
        valuePointer: ptrToHex(stringPointer)
      }};
    }}
    if (attribute === 4) {{
      return readStreamSizes(attributeBufferPtr);
    }}
    if (attribute === 83) {{
      const remoteCertContext = attributeBufferPtr.readPointer();
      return {{
        certContext: ptrToHex(remoteCertContext)
      }};
    }}
    if (attribute === 90) {{
      return readConnectionInfo(attributeBufferPtr);
    }}
    return {{
      attributeBuffer: ptrToHex(attributeBufferPtr)
    }};
  }} catch (error) {{
    return {{ error: String(error) }};
  }}
}}

function summarizeSecBufferDesc(descPtr) {{
  const native = toNativePointer(descPtr);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    const bufferCount = native.add(4).readU32();
    const buffersPtr = native.add(8).readPointer();
    const elementSize = 8 + Process.pointerSize;
    const buffers = [];
    let totalBytes = 0;
    const cappedCount = Math.min(bufferCount, 8);
    for (let index = 0; index < cappedCount; index += 1) {{
      const bufferPtr = buffersPtr.add(index * elementSize);
      const byteCount = bufferPtr.readU32();
      const bufferType = bufferPtr.add(4).readU32();
      const dataPointer = bufferPtr.add(8).readPointer();
      totalBytes += byteCount;
      buffers.push({{
        index: index,
        bytes: byteCount,
        bufferType: bufferType,
        bufferTypeName: secBufferTypeName(bufferType),
        dataPointer: ptrToHex(dataPointer)
      }});
    }}
    return {{
      version: native.readU32(),
      bufferCount: bufferCount,
      totalBytes: totalBytes,
      buffers: buffers
    }};
  }} catch (error) {{
    return {{ error: String(error) }};
  }}
}}

function summarizeSecBufferPayload(descPtr) {{
  const native = toNativePointer(descPtr);
  if (native === null || native.isNull()) {{
    return null;
  }}
  try {{
    const bufferCount = native.add(4).readU32();
    const buffersPtr = native.add(8).readPointer();
    const elementSize = 8 + Process.pointerSize;
    const previews = [];
    const cappedCount = Math.min(bufferCount, 8);
    for (let index = 0; index < cappedCount; index += 1) {{
      const bufferPtr = buffersPtr.add(index * elementSize);
      const byteCount = bufferPtr.readU32();
      const bufferType = bufferPtr.add(4).readU32();
      const dataType = bufferType & 0x0fffffff;
      if (byteCount <= 0 || (dataType !== 1 && dataType !== 2 && dataType !== 10)) {{
        continue;
      }}
      const dataPointer = bufferPtr.add(8).readPointer();
      const preview = summarizeSocketChunk(dataPointer, Math.min(byteCount, 256));
      previews.push({{
        index: index,
        bytes: byteCount,
        bufferType: bufferType,
        bufferTypeName: secBufferTypeName(bufferType),
        dataPointer: ptrToHex(dataPointer),
        preview: preview
      }});
      if (previews.length >= 2) {{
        break;
      }}
    }}
    if (previews.length === 0) {{
      return null;
    }}
    return previews;
  }} catch (error) {{
    return {{ error: String(error) }};
  }}
}}

function collectContext(context) {{
  const registers = [
    'rip', 'rsp', 'rbp',
    'rax', 'rbx', 'rcx', 'rdx',
    'rsi', 'rdi',
    'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15'
  ];
  const snapshot = {{}};
  for (const registerName of registers) {{
    if (context[registerName] !== undefined) {{
      snapshot[registerName] = ptrToHex(context[registerName]);
    }}
  }}
  return snapshot;
}}

function formatFrame(address) {{
  const pointerValue = ptr(address);
  const symbol = DebugSymbol.fromAddress(pointerValue);
  return {{
    address: ptrToHex(pointerValue),
    symbol: symbol !== null ? symbol.toString() : null
  }};
}}

function hookExport(moduleNames, exportName, callbacks) {{
  const key = moduleNames.join('|') + '!' + exportName;
  if (hooks.has(key)) {{
    return true;
  }}
  const address = findExport(moduleNames, exportName);
  if (address === null) {{
    return false;
  }}
  Interceptor.attach(address, callbacks);
  hooks.add(key);
  emit('client.lifecycle', 'hook-installed', {{
    target: key,
    address: ptrToHex(address)
  }});
  return true;
}}

function installFileHooks() {{
  hookExport(['kernel32.dll', 'kernelbase.dll'], 'CreateFileW', {{
    onEnter(args) {{
      this.path = readUtf16Maybe(args[0]);
    }},
    onLeave(retval) {{
      const handleKey = ptrToHex(retval);
      const requestedPath = this.path;
      const requestedCategory = classifyPath(requestedPath);
      if (handleKey === '0xffffffffffffffff' || handleKey === '0xffffffff') {{
        if (shouldEmitPathCategory(requestedCategory)) {{
          emit('client.file', 'open-failed', {{
            handle: handleKey,
            path: requestedPath,
            fileCategory: requestedCategory,
            requestedPath: requestedPath,
            lastError: this.lastError >>> 0
          }});
        }}
        return;
      }}
      const resolvedPath = resolveHandlePath(retval);
      const effectivePath = resolvedPath || requestedPath;
      const category = classifyPath(effectivePath);
      fileHandles[handleKey] = {{
        path: effectivePath,
        requestedPath: requestedPath,
        resolvedPath: resolvedPath,
        category: category,
        bytesRead: 0,
        bytesWritten: 0
      }};
      if (shouldEmitPathCategory(category)) {{
        const details = {{
          handle: handleKey,
          path: effectivePath,
          fileCategory: category
        }};
        if (resolvedPath) {{
          details.resolvedPath = resolvedPath;
        }}
        if (requestedPath && requestedPath !== effectivePath && !pathLooksUnreadable(requestedPath)) {{
          details.requestedPath = requestedPath;
        }}
        emit('client.file', 'open', details);
      }}
    }}
  }});

  hookExport(['kernel32.dll', 'kernelbase.dll'], 'CreateFileA', {{
    onEnter(args) {{
      this.path = readUtf8Maybe(args[0]);
    }},
    onLeave(retval) {{
      const handleKey = ptrToHex(retval);
      const requestedPath = this.path;
      const requestedCategory = classifyPath(requestedPath);
      if (handleKey === '0xffffffffffffffff' || handleKey === '0xffffffff') {{
        if (shouldEmitPathCategory(requestedCategory)) {{
          emit('client.file', 'open-failed', {{
            handle: handleKey,
            path: requestedPath,
            fileCategory: requestedCategory,
            requestedPath: requestedPath,
            lastError: this.lastError >>> 0
          }});
        }}
        return;
      }}
      const resolvedPath = resolveHandlePath(retval);
      const effectivePath = resolvedPath || requestedPath;
      const category = classifyPath(effectivePath);
      fileHandles[handleKey] = {{
        path: effectivePath,
        requestedPath: requestedPath,
        resolvedPath: resolvedPath,
        category: category,
        bytesRead: 0,
        bytesWritten: 0
      }};
      if (shouldEmitPathCategory(category)) {{
        const details = {{
          handle: handleKey,
          path: effectivePath,
          fileCategory: category
        }};
        if (resolvedPath) {{
          details.resolvedPath = resolvedPath;
        }}
        if (requestedPath && requestedPath !== effectivePath && !pathLooksUnreadable(requestedPath)) {{
          details.requestedPath = requestedPath;
        }}
        emit('client.file', 'open', details);
      }}
    }}
  }});

  hookExport(['kernel32.dll', 'kernelbase.dll'], 'ReadFile', {{
    onEnter(args) {{
      this.handleKey = ptrToHex(args[0]);
      this.bytesReadOut = args[3];
      this.requested = args[2].toUInt32();
    }},
    onLeave(retval) {{
      const file = fileHandles[this.handleKey];
      if (!file) {{
        return;
      }}
      let actual = 0;
      try {{
        if (!this.bytesReadOut.isNull()) {{
          actual = this.bytesReadOut.readU32();
        }}
      }} catch (error) {{
        actual = this.requested;
      }}
      file.bytesRead += actual;
      if (VERBOSE && actual > 0) {{
        emit('client.file', 'read', {{
          handle: this.handleKey,
          path: file.path,
          fileCategory: file.category,
          bytes: actual,
          totalBytesRead: file.bytesRead
        }});
      }}
    }}
  }});

  hookExport(['kernel32.dll', 'kernelbase.dll'], 'WriteFile', {{
    onEnter(args) {{
      this.handleKey = ptrToHex(args[0]);
      this.bytesWrittenOut = args[3];
      this.requested = args[2].toUInt32();
    }},
    onLeave(retval) {{
      const file = fileHandles[this.handleKey];
      if (!file) {{
        return;
      }}
      let actual = 0;
      try {{
        if (!this.bytesWrittenOut.isNull()) {{
          actual = this.bytesWrittenOut.readU32();
        }}
      }} catch (error) {{
        actual = this.requested;
      }}
      file.bytesWritten += actual;
      if (actual > 0 && (VERBOSE || file.category === 'cache' || file.category === 'shadercache')) {{
        emit('client.file', 'write', {{
          handle: this.handleKey,
          path: file.path,
          fileCategory: file.category,
          bytes: actual,
          totalBytesRead: file.bytesRead,
          totalBytesWritten: file.bytesWritten
        }});
      }}
    }}
  }});

  hookExport(['kernel32.dll', 'kernelbase.dll'], 'CloseHandle', {{
    onEnter(args) {{
      this.handleKey = ptrToHex(args[0]);
      this.file = fileHandles[this.handleKey] || null;
    }},
    onLeave(retval) {{
      if (!this.file) {{
        return;
      }}
      emit('client.file', 'close', {{
        handle: this.handleKey,
        path: this.file.path,
        fileCategory: this.file.category,
        totalBytesRead: this.file.bytesRead,
        totalBytesWritten: this.file.bytesWritten
      }});
      delete fileHandles[this.handleKey];
    }}
  }});

  function onModuleLoaded(retval, requestedPath, apiName) {{
    if (retval.isNull()) {{
      return;
    }}
    const moduleObject = moduleFromAddress(retval);
    if (moduleObject !== null) {{
      const details = {{
        api: apiName
      }};
      if (requestedPath && !pathLooksUnreadable(requestedPath) && requestedPath !== moduleObject.path) {{
        details.requestedPath = requestedPath;
      }}
      emitModuleEvent('load', moduleObject, details);
      return;
    }}
    const modulePath = requestedPath || '<unknown>';
    const details = {{
      path: modulePath,
      handle: ptrToHex(retval),
      api: apiName,
      interesting: moduleInteresting(normalizeModuleName(modulePath))
    }};
    if (requestedPath && !pathLooksUnreadable(requestedPath)) {{
      details.requestedPath = requestedPath;
    }}
    emit('client.module', 'load', details);
  }}

  hookExport(['kernel32.dll', 'kernelbase.dll'], 'LoadLibraryW', {{
    onEnter(args) {{
      this.path = readUtf16Maybe(args[0]);
    }},
    onLeave(retval) {{
      onModuleLoaded(retval, this.path, 'LoadLibraryW');
    }}
  }});

  hookExport(['kernel32.dll', 'kernelbase.dll'], 'LoadLibraryA', {{
    onEnter(args) {{
      this.path = readUtf8Maybe(args[0]);
    }},
    onLeave(retval) {{
      onModuleLoaded(retval, this.path, 'LoadLibraryA');
    }}
  }});

  hookExport(['kernel32.dll', 'kernelbase.dll'], 'LoadLibraryExW', {{
    onEnter(args) {{
      this.path = readUtf16Maybe(args[0]);
    }},
    onLeave(retval) {{
      onModuleLoaded(retval, this.path, 'LoadLibraryExW');
    }}
  }});

  hookExport(['kernel32.dll', 'kernelbase.dll'], 'LoadLibraryExA', {{
    onEnter(args) {{
      this.path = readUtf8Maybe(args[0]);
    }},
    onLeave(retval) {{
      onModuleLoaded(retval, this.path, 'LoadLibraryExA');
    }}
  }});
}}

function installNetworkHooks() {{
  function emitResolve(action, hostValue, serviceValue, apiName) {{
    emit('client.net', action, {{
      host: hostValue,
      service: serviceValue,
      api: apiName
    }});
  }}

  hookExport(['ws2_32.dll'], 'GetAddrInfoW', {{
    onEnter(args) {{
      this.host = readUtf16Maybe(args[0]);
      this.service = readUtf16Maybe(args[1]);
      this.redirect = maybeRewriteResolveArgument(args, 0, true, this.host);
    }},
    onLeave(retval) {{
      emit('client.net', 'resolve', {{
        host: this.host,
        service: this.service,
        api: 'GetAddrInfoW',
        status: retval.toInt32()
      }});
      if (this.redirect) {{
        emit('client.net', 'resolve-redirect', {{
          host: this.redirect.originalHost,
          redirectedHost: this.redirect.redirectedHost,
          service: this.service,
          api: 'GetAddrInfoW'
        }});
      }}
    }}
  }});

  hookExport(['ws2_32.dll'], 'GetAddrInfoA', {{
    onEnter(args) {{
      this.host = readUtf8Maybe(args[0]);
      this.service = readUtf8Maybe(args[1]);
      this.redirect = maybeRewriteResolveArgument(args, 0, false, this.host);
    }},
    onLeave(retval) {{
      emit('client.net', 'resolve', {{
        host: this.host,
        service: this.service,
        api: 'GetAddrInfoA',
        status: retval.toInt32()
      }});
      if (this.redirect) {{
        emit('client.net', 'resolve-redirect', {{
          host: this.redirect.originalHost,
          redirectedHost: this.redirect.redirectedHost,
          service: this.service,
          api: 'GetAddrInfoA'
        }});
      }}
    }}
  }});

  hookExport(['ws2_32.dll'], 'GetAddrInfoExW', {{
    onEnter(args) {{
      this.host = readUtf16Maybe(args[0]);
      this.service = readUtf16Maybe(args[1]);
      this.redirect = maybeRewriteResolveArgument(args, 0, true, this.host);
    }},
    onLeave(retval) {{
      emit('client.net', 'resolve', {{
        host: this.host,
        service: this.service,
        api: 'GetAddrInfoExW',
        status: retval.toInt32()
      }});
      if (this.redirect) {{
        emit('client.net', 'resolve-redirect', {{
          host: this.redirect.originalHost,
          redirectedHost: this.redirect.redirectedHost,
          service: this.service,
          api: 'GetAddrInfoExW'
        }});
      }}
    }}
  }});

  hookExport(['ws2_32.dll'], 'GetAddrInfoExA', {{
    onEnter(args) {{
      this.host = readUtf8Maybe(args[0]);
      this.service = readUtf8Maybe(args[1]);
      this.redirect = maybeRewriteResolveArgument(args, 0, false, this.host);
    }},
    onLeave(retval) {{
      emit('client.net', 'resolve', {{
        host: this.host,
        service: this.service,
        api: 'GetAddrInfoExA',
        status: retval.toInt32()
      }});
      if (this.redirect) {{
        emit('client.net', 'resolve-redirect', {{
          host: this.redirect.originalHost,
          redirectedHost: this.redirect.redirectedHost,
          service: this.service,
          api: 'GetAddrInfoExA'
        }});
      }}
    }}
  }});

  hookExport(['ws2_32.dll'], 'connect', {{
    onEnter(args) {{
      this.socketValue = args[0];
      this.endpoint = parseSockaddr(args[1]);
      this.connectRedirect = maybeRewriteConnectSockaddr(args[1], this.endpoint);
      if (this.connectRedirect) {{
        this.endpoint = parseSockaddr(args[1]);
      }}
      const record = socketRecord(this.socketValue);
      if (this.endpoint) {{
        record.remoteHost = this.endpoint.host;
        record.remotePort = this.endpoint.port;
      }}
    }},
    onLeave(retval) {{
      if (this.connectRedirect) {{
        emit('client.net', 'connect-redirect', {{
          api: 'connect',
          family: this.connectRedirect.family,
          host: this.connectRedirect.originalHost,
          redirectedHost: this.connectRedirect.redirectedHost,
          port: this.connectRedirect.port
        }});
      }}
      emitSocketSummary('connect', this.socketValue, {{
        family: this.endpoint ? this.endpoint.family : null,
        status: retval.toInt32()
      }});
    }}
  }});

  hookExport(['ws2_32.dll'], 'WSAConnect', {{
    onEnter(args) {{
      this.socketValue = args[0];
      this.endpoint = parseSockaddr(args[1]);
      this.connectRedirect = maybeRewriteConnectSockaddr(args[1], this.endpoint);
      if (this.connectRedirect) {{
        this.endpoint = parseSockaddr(args[1]);
      }}
      const record = socketRecord(this.socketValue);
      if (this.endpoint) {{
        record.remoteHost = this.endpoint.host;
        record.remotePort = this.endpoint.port;
      }}
    }},
    onLeave(retval) {{
      if (this.connectRedirect) {{
        emit('client.net', 'connect-redirect', {{
          api: 'WSAConnect',
          family: this.connectRedirect.family,
          host: this.connectRedirect.originalHost,
          redirectedHost: this.connectRedirect.redirectedHost,
          port: this.connectRedirect.port
        }});
      }}
      emitSocketSummary('connect', this.socketValue, {{
        family: this.endpoint ? this.endpoint.family : null,
        status: retval.toInt32(),
        api: 'WSAConnect'
      }});
    }}
  }});

  hookExport(['ws2_32.dll'], 'WSAConnectByNameW', {{
    onEnter(args) {{
      this.socketValue = args[0];
      this.host = readUtf16Maybe(args[1]);
      this.service = readUtf16Maybe(args[2]);
      this.redirect = maybeRewriteResolveArgument(args, 1, true, this.host);
      if (this.redirect) {{
        this.host = this.redirect.redirectedHost;
      }}
      const record = socketRecord(this.socketValue);
      record.remoteHost = this.host;
      record.remotePort = this.service ? parseInt(this.service, 10) : null;
    }},
    onLeave(retval) {{
      if (this.redirect) {{
        emit('client.net', 'connect-redirect', {{
          api: 'WSAConnectByNameW',
          host: this.redirect.originalHost,
          redirectedHost: this.redirect.redirectedHost,
          port: this.service
        }});
      }}
      emitSocketSummary('connect', this.socketValue, {{
        api: 'WSAConnectByNameW',
        family: null,
        status: retval.toInt32()
      }});
    }}
  }});

  hookExport(['ws2_32.dll'], 'WSAConnectByNameA', {{
    onEnter(args) {{
      this.socketValue = args[0];
      this.host = readUtf8Maybe(args[1]);
      this.service = readUtf8Maybe(args[2]);
      this.redirect = maybeRewriteResolveArgument(args, 1, false, this.host);
      if (this.redirect) {{
        this.host = this.redirect.redirectedHost;
      }}
      const record = socketRecord(this.socketValue);
      record.remoteHost = this.host;
      record.remotePort = this.service ? parseInt(this.service, 10) : null;
    }},
    onLeave(retval) {{
      if (this.redirect) {{
        emit('client.net', 'connect-redirect', {{
          api: 'WSAConnectByNameA',
          host: this.redirect.originalHost,
          redirectedHost: this.redirect.redirectedHost,
          port: this.service
        }});
      }}
      emitSocketSummary('connect', this.socketValue, {{
        api: 'WSAConnectByNameA',
        family: null,
        status: retval.toInt32()
      }});
    }}
  }});

  hookExport(['ws2_32.dll'], 'send', {{
    onEnter(args) {{
      this.socketValue = args[0];
      this.bufferPointer = args[1];
      this.requested = args[2].toInt32();
    }},
    onLeave(retval) {{
      const actual = retval.toInt32();
      if (actual <= 0) {{
        return;
      }}
      const record = socketRecord(this.socketValue);
      record.bytesSent += actual;
      if (!record.firstSendCaptured) {{
        record.firstSendCaptured = true;
        const chunkSummary = summarizeSocketChunk(this.bufferPointer, actual);
        emitSocketSummary('send-first-chunk', this.socketValue, Object.assign({{
          bytes: actual
        }}, chunkSummary || {{}}));
      }}
      if (VERBOSE) {{
        const chunkSummary = summarizeSocketChunk(this.bufferPointer, actual, 64);
        emitSocketSummary('send', this.socketValue, Object.assign({{
          bytes: actual
        }}, chunkSummary || {{}}));
      }}
    }}
  }});

  hookExport(['ws2_32.dll'], 'WSASend', {{
    onEnter(args) {{
      this.socketValue = args[0];
      this.wsabuf = readWsabuf(args[1]);
      this.bytesSentPointer = args[3];
    }},
    onLeave(retval) {{
      const status = retval.toInt32();
      let actual = 0;
      const bytesPointer = toNativePointer(this.bytesSentPointer);
      if (bytesPointer !== null && !bytesPointer.isNull()) {{
        try {{
          actual = bytesPointer.readU32();
        }} catch (error) {{
          actual = 0;
        }}
      }}
      if (actual <= 0 || this.wsabuf === null) {{
        if (VERBOSE) {{
          emitSocketSummary('send', this.socketValue, {{
            api: 'WSASend',
            bytes: actual,
            status: status
          }});
        }}
        return;
      }}
      const record = socketRecord(this.socketValue);
      record.bytesSent += actual;
      if (!record.firstSendCaptured) {{
        record.firstSendCaptured = true;
        const chunkSummary = summarizeSocketChunk(this.wsabuf.pointer, actual);
        emitSocketSummary('send-first-chunk', this.socketValue, Object.assign({{
          api: 'WSASend',
          bytes: actual,
          status: status
        }}, chunkSummary || {{}}));
      }}
      if (VERBOSE) {{
        const chunkSummary = summarizeSocketChunk(this.wsabuf.pointer, actual, 64);
        emitSocketSummary('send', this.socketValue, Object.assign({{
          api: 'WSASend',
          bytes: actual,
          status: status
        }}, chunkSummary || {{}}));
      }}
    }}
  }});

  hookExport(['ws2_32.dll'], 'recv', {{
    onEnter(args) {{
      this.socketValue = args[0];
      this.bufferPointer = args[1];
    }},
    onLeave(retval) {{
      const actual = retval.toInt32();
      if (actual <= 0) {{
        return;
      }}
      const record = socketRecord(this.socketValue);
      record.bytesReceived += actual;
      if (!record.firstRecvCaptured) {{
        record.firstRecvCaptured = true;
        const chunkSummary = summarizeSocketChunk(this.bufferPointer, actual);
        emitSocketSummary('recv-first-chunk', this.socketValue, Object.assign({{
          bytes: actual
        }}, chunkSummary || {{}}));
      }}
      if (VERBOSE) {{
        const chunkSummary = summarizeSocketChunk(this.bufferPointer, actual, 64);
        emitSocketSummary('recv', this.socketValue, Object.assign({{
          bytes: actual
        }}, chunkSummary || {{}}));
      }}
    }}
  }});

  hookExport(['ws2_32.dll'], 'WSARecv', {{
    onEnter(args) {{
      this.socketValue = args[0];
      this.wsabuf = readWsabuf(args[1]);
      this.bytesRecvPointer = args[3];
    }},
    onLeave(retval) {{
      const status = retval.toInt32();
      let actual = 0;
      const bytesPointer = toNativePointer(this.bytesRecvPointer);
      if (bytesPointer !== null && !bytesPointer.isNull()) {{
        try {{
          actual = bytesPointer.readU32();
        }} catch (error) {{
          actual = 0;
        }}
      }}
      if (actual <= 0 || this.wsabuf === null) {{
        if (VERBOSE) {{
          emitSocketSummary('recv', this.socketValue, {{
            api: 'WSARecv',
            bytes: actual,
            status: status
          }});
        }}
        return;
      }}
      const record = socketRecord(this.socketValue);
      record.bytesReceived += actual;
      if (!record.firstRecvCaptured) {{
        record.firstRecvCaptured = true;
        const chunkSummary = summarizeSocketChunk(this.wsabuf.pointer, actual);
        emitSocketSummary('recv-first-chunk', this.socketValue, Object.assign({{
          api: 'WSARecv',
          bytes: actual,
          status: status
        }}, chunkSummary || {{}}));
      }}
      if (VERBOSE) {{
        const chunkSummary = summarizeSocketChunk(this.wsabuf.pointer, actual, 64);
        emitSocketSummary('recv', this.socketValue, Object.assign({{
          api: 'WSARecv',
          bytes: actual,
          status: status
        }}, chunkSummary || {{}}));
      }}
    }}
  }});

  hookExport(['ws2_32.dll'], 'closesocket', {{
    onEnter(args) {{
      this.socketValue = args[0];
    }},
    onLeave(retval) {{
      emitSocketSummary('close', this.socketValue, {{
        status: retval.toInt32()
      }});
      delete socketStats[socketKey(this.socketValue)];
    }}
  }});
}}

function installTlsHooks() {{
  function hookAcquireCredentials(exportName, reader, apiName) {{
    hookExport(['secur32.dll', 'sspicli.dll'], exportName, {{
      onEnter(args) {{
        this.data = {{
          packageName: reader(args[1]),
          credentialUse: args[2].toUInt32(),
          api: apiName
        }};
      }},
      onLeave(retval) {{
        this.data.status = retval.toUInt32();
        emit('client.tls', 'acquire-credentials', this.data);
      }}
    }});
  }}

  hookAcquireCredentials('AcquireCredentialsHandleW', readUtf16Maybe, 'AcquireCredentialsHandleW');
  hookAcquireCredentials('AcquireCredentialsHandleA', readUtf8Maybe, 'AcquireCredentialsHandleA');

  function hookInitializeSecurityContext(exportName, reader, apiName) {{
    hookExport(['secur32.dll', 'sspicli.dll'], exportName, {{
      onEnter(args) {{
        this.data = {{
          targetName: reader(args[2]),
          contextReq: args[3].toUInt32(),
          targetDataRep: args[5].toUInt32(),
          api: apiName
        }};
      }},
      onLeave(retval) {{
        this.data.status = retval.toUInt32();
        emit('client.tls', 'initialize-security-context', this.data);
      }}
    }});
  }}

  hookInitializeSecurityContext('InitializeSecurityContextW', readUtf16Maybe, 'InitializeSecurityContextW');
  hookInitializeSecurityContext('InitializeSecurityContextA', readUtf8Maybe, 'InitializeSecurityContextA');

  function hookQueryContextAttributes(exportName, reader, apiName) {{
    hookExport(['secur32.dll', 'sspicli.dll'], exportName, {{
      onEnter(args) {{
        this.attribute = args[1].toUInt32();
        this.attributeBufferPtr = args[2];
        this.data = {{
          attribute: this.attribute,
          attributeName: secPkgAttributeName(this.attribute),
          attributeBuffer: ptrToHex(this.attributeBufferPtr),
          api: apiName
        }};
      }},
      onLeave(retval) {{
        this.data.status = retval.toUInt32();
        if (this.data.status === 0) {{
          this.data.attributeValue = readQueryContextAttribute(this.attribute, this.attributeBufferPtr, reader);
        }}
        emit('client.tls', 'query-context-attributes', this.data);
      }}
    }});
  }}

  hookQueryContextAttributes('QueryContextAttributesW', readUtf16Maybe, 'QueryContextAttributesW');
  hookQueryContextAttributes('QueryContextAttributesA', readUtf8Maybe, 'QueryContextAttributesA');

  hookExport(['secur32.dll', 'sspicli.dll'], 'EncryptMessage', {{
    onEnter(args) {{
      this.data = {{
        qualityOfProtection: args[1].toUInt32(),
        bufferSummary: summarizeSecBufferDesc(args[2]),
        sequenceNo: args[3].toUInt32(),
        api: 'EncryptMessage'
      }};
    }},
    onLeave(retval) {{
      this.data.status = retval.toUInt32();
      if (VERBOSE) {{
        this.data.payloadPreview = summarizeSecBufferPayload(args[2]);
      }}
      emit('client.tls', 'encrypt-message', this.data);
    }}
  }});

  hookExport(['secur32.dll', 'sspicli.dll'], 'DecryptMessage', {{
    onEnter(args) {{
      this.qopPtr = args[3];
      this.data = {{
        bufferSummary: summarizeSecBufferDesc(args[1]),
        sequenceNo: args[2].toUInt32(),
        api: 'DecryptMessage'
      }};
    }},
    onLeave(retval) {{
      this.data.status = retval.toUInt32();
      if (!this.qopPtr.isNull()) {{
        try {{
          this.data.qualityOfProtection = this.qopPtr.readU32();
        }} catch (error) {{
          this.data.qualityOfProtectionError = String(error);
        }}
      }}
      if (VERBOSE) {{
        this.data.payloadPreview = summarizeSecBufferPayload(args[1]);
      }}
      emit('client.tls', 'decrypt-message', this.data);
    }}
  }});

  hookExport(['secur32.dll', 'sspicli.dll'], 'DeleteSecurityContext', {{
    onEnter(args) {{
      this.data = {{
        contextHandle: ptrToHex(args[0]),
        api: 'DeleteSecurityContext'
      }};
    }},
    onLeave(retval) {{
      this.data.status = retval.toUInt32();
      emit('client.tls', 'delete-security-context', this.data);
    }}
  }});

  hookExport(['secur32.dll', 'sspicli.dll'], 'FreeCredentialsHandle', {{
    onEnter(args) {{
      this.data = {{
        credentialsHandle: ptrToHex(args[0]),
        api: 'FreeCredentialsHandle'
      }};
    }},
    onLeave(retval) {{
      this.data.status = retval.toUInt32();
      emit('client.tls', 'free-credentials-handle', this.data);
    }}
  }});

  hookExport(['crypt32.dll'], 'CertGetCertificateChain', {{
    onEnter(args) {{
      this.chainOutPtr = args[7];
      this.data = {{
        flags: args[5].toUInt32(),
        certContext: ptrToHex(args[1])
      }};
    }},
    onLeave(retval) {{
      this.data.result = retval.toInt32();
      if (!this.chainOutPtr.isNull()) {{
        try {{
          const chainContextPtr = Memory.readPointer(this.chainOutPtr);
          this.data.chainContext = ptrToHex(chainContextPtr);
          this.data.chainStatus = readChainStatus(chainContextPtr);
        }} catch (error) {{
          this.data.chainStatus = {{ error: String(error) }};
        }}
      }}
      emit('client.tls', 'cert-get-chain', this.data);
    }}
  }});

  hookExport(['crypt32.dll'], 'CertVerifyCertificateChainPolicy', {{
    onEnter(args) {{
      this.policyStatusPtr = args[3];
      this.data = {{
        policyOid: readPolicyOid(args[0]),
        chainContext: ptrToHex(args[1])
      }};
    }},
    onLeave(retval) {{
      this.data.result = retval.toInt32();
      this.data.policyStatus = readPolicyStatus(this.policyStatusPtr);
      emit('client.tls', 'cert-verify-policy', this.data);
    }}
  }});

  hookExport(['crypt32.dll'], 'WinVerifyTrust', {{
    onEnter(args) {{
      this.data = {{
        hwnd: ptrToHex(args[0]),
        actionId: ptrToHex(args[1])
      }};
    }},
    onLeave(retval) {{
      this.data.status = retval.toUInt32();
      emit('client.tls', 'win-verify-trust', this.data);
    }}
  }});
}}

function installExceptionHook() {{
  emit('client.lifecycle', 'exception-handler-installed', {{ ok: true }});
  Process.setExceptionHandler(function (details) {{
    const event = {{
      exceptionType: details.type,
      address: ptrToHex(details.address),
      context: collectContext(details.context)
    }};

    if (details.memory !== undefined && details.memory !== null) {{
      event.memory = {{
        operation: details.memory.operation,
        address: ptrToHex(details.memory.address)
      }};
    }}

    try {{
      event.backtrace = Thread.backtrace(details.context, Backtracer.ACCURATE).map(formatFrame);
    }} catch (accurateError) {{
      event.backtraceError = String(accurateError);
      try {{
        event.backtrace = Thread.backtrace(details.context, Backtracer.FUZZY).map(formatFrame);
        event.backtraceMode = 'fuzzy';
      }} catch (fuzzyError) {{
        event.backtrace = [];
        event.backtraceFallbackError = String(fuzzyError);
      }}
    }}

    emit('client.exception', 'fault', event);
    return false;
  }});
}

function installHooks() {{
  installFileHooks();
  installNetworkHooks();
  installTlsHooks();
  emitModuleSnapshot();
}}

installHooks();
installExceptionHook();
setInterval(installHooks, 1000);
"""
    return (
        script.replace("__VERBOSE__", verbose_literal)
        .replace("__RESOLVE_REDIRECTS__", json.dumps(normalized_redirects, sort_keys=True))
        .replace("__CONNECT_REDIRECTS__", json.dumps(normalized_connect_redirects, sort_keys=True))
        .replace("{{", "{")
        .replace("}}", "}")
    )


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault("category", "client.unknown")
    normalized.setdefault("action", "event")
    timestamp = normalized.get("timestamp")
    if isinstance(timestamp, (int, float)):
        normalized["timestamp"] = round(float(timestamp), 6)
    return normalized


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stop_event = threading.Event()

    with output_path.open("w", encoding="utf-8") as handle:
        def write_event(event: dict[str, Any]) -> None:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
            handle.flush()

        def on_message(message: dict[str, Any], _data: Any) -> None:
            if message.get("type") == "send":
                payload = message.get("payload", {})
                if isinstance(payload, dict):
                    write_event(normalize_payload(payload))
                else:
                    write_event(
                        {
                            "timestamp": round(time.time(), 6),
                            "category": "client.unknown",
                            "action": "message",
                            "payload": payload,
                        }
                    )
                return

            write_event(
                {
                    "timestamp": round(time.time(), 6),
                    "category": "client.unknown",
                    "action": "frida-message",
                    "message": message,
                }
            )

        session = frida.attach(args.pid)
        script = session.create_script(build_hook_script(args.verbose))
        script.on("message", on_message)
        script.load()
        write_event(
            {
                "timestamp": round(time.time(), 6),
                "category": "client.lifecycle",
                "action": "attached",
                "pid": args.pid,
                "verbose": bool(args.verbose),
            }
        )

        def on_detached(reason: str, crash: Any) -> None:
            event = {
                "timestamp": round(time.time(), 6),
                "category": "client.lifecycle",
                "action": "detached",
                "reason": reason,
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
