from __future__ import annotations

import argparse
import ctypes
import json
import socket
import subprocess
import threading
import time
import tomllib
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any, Callable

import frida
from ctypes import wintypes

try:
    from tools.trace_rs2client_live import build_hook_script as build_child_live_hook_script
    from tools.trace_rs2client_live import normalize_payload as normalize_child_live_payload
except ImportError:
    from trace_rs2client_live import build_hook_script as build_child_live_hook_script
    from trace_rs2client_live import normalize_payload as normalize_child_live_payload


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_BASIC_INFORMATION_CLASS = 0
PEB_PROCESS_PARAMETERS_OFFSET_X64 = 0x20
RTL_USER_PROCESS_PARAMETERS_COMMAND_LINE_OFFSET_X64 = 0x70
PAGE_EXECUTE_READWRITE = 0x40
DEFAULT_NULL_READ_BLOCK = bytes.fromhex("44 8B 04 25 00 00 00 00 48 8B CE")
KNOWN_INLINE_PATCHES = {
    0x590001: {
        "expected": bytes.fromhex("8B 09"),
        "replacement": bytes.fromhex("33 C9"),
    },
    0x590321: {
        "expected": bytes.fromhex("8B 09"),
        "replacement": bytes.fromhex("33 C9"),
    },
    0x5916C3: {
        "expected": bytes.fromhex("8B 09"),
        "replacement": bytes.fromhex("33 C9"),
    },
    0x5916F0: {
        "expected": bytes.fromhex("48 8B 53 10"),
        "replacement": bytes.fromhex("48 31 D2 90"),
    },
    0x591712: {
        "expected": bytes.fromhex("4C 8B 43 10"),
        "replacement": bytes.fromhex("4D 31 C0 90"),
    },
    0x591719: {
        "expected": bytes.fromhex("48 8B 53 18"),
        "replacement": bytes.fromhex("48 31 D2 90"),
    },
    0x5919E3: {
        "expected": bytes.fromhex("8B 09"),
        "replacement": bytes.fromhex("33 C9"),
    },
    0x591A10: {
        "expected": bytes.fromhex("48 8B 53 10"),
        "replacement": bytes.fromhex("48 31 D2 90"),
    },
    0x591A32: {
        "expected": bytes.fromhex("4C 8B 43 10"),
        "replacement": bytes.fromhex("4D 31 C0 90"),
    },
    0x591A39: {
        "expected": bytes.fromhex("48 8B 53 18"),
        "replacement": bytes.fromhex("48 31 D2 90"),
    },
    0x594A41: {
        "expected": bytes.fromhex("80 7E 24 00"),
        "replacement": bytes.fromhex("31 C0 90 90"),
    },
    0x594D61: {
        "expected": bytes.fromhex("80 7E 24 00"),
        "replacement": bytes.fromhex("31 C0 90 90"),
    },
}
KNOWN_JUMP_BYPASS_BLOCKS = {
    0x59002D: bytes.fromhex(
        "48 8B 53 10 48 8D 4C 24 40 4C 89 64 24 48 4C 89 64 24 50 "
        "4C 89 64 24 58 E8 56 98 A9 FF 48 8B 74 24 50 4C 8B 43 10 "
        "48 8B CE 48 8B 53 18 E8 31 9C 22 00 48 8B 5C 24 48 4C 8B "
        "A4 24 90 00 00 00 48 85 DB 74 2A 48 85 F6 74 21 48 8B 4F "
        "38 48 8B D6 48 8B 47 28 48 2B C1 48 3B C3 48 0F 42 D8 48 "
        "03 4F 30 4C 8B C3 E8 F9 9B 22 00 48 01 5F 38 48 8D 4C 24 "
        "40 E8 0B DC A9 FF"
    ),
    0x59034D: bytes.fromhex(
        "48 8B 53 10 48 8D 4C 24 40 4C 89 64 24 48 4C 89 64 24 50 "
        "4C 89 64 24 58 E8 66 95 A9 FF 48 8B 74 24 50 4C 8B 43 10 "
        "48 8B CE 48 8B 53 18 E8 D1 F8 24 00 48 8B 5C 24 48 4C 8B "
        "A4 24 90 00 00 00 48 85 DB 74 2A 48 85 F6 74 21 48 8B 4F "
        "38 48 8B D6 48 8B 47 28 48 2B C1 48 3B C3 48 0F 42 D8 48 "
        "03 4F 30 4C 8B C3 E8 99 F8 24 00 48 01 5F 38 48 8D 4C 24 "
        "40 E8 1B D9 A9 FF"
    ),
    0x590C72: DEFAULT_NULL_READ_BLOCK,
    0x590F92: DEFAULT_NULL_READ_BLOCK,
    0x594A91: bytes.fromhex("48 8B 86 A0 00 00 00"),
    0x594AAF: bytes.fromhex("48 8B 86 D0 00 00 00"),
    0x594A88: bytes.fromhex("48 3B AE 98 00 00 00 73 10"),
    0x594AA6: bytes.fromhex("48 3B AE C8 00 00 00 73 0B"),
    0x594DA8: bytes.fromhex("48 3B AE 98 00 00 00 73 10"),
    0x594DC6: bytes.fromhex("48 3B AE C8 00 00 00 73 0B"),
    0x72AD28: bytes.fromhex("80 7B 08 00 74 18 48 8B 0D DB 1B 52 00 48 85 C9 74 0C 48 8B D3 E8 7E 13 00 00 C6 43 08 00"),
    0x72B3A8: bytes.fromhex("80 7B 08 00 74 18 48 8B 0D 2B 45 58 00 48 85 C9 74 0C 48 8B D3 E8 3E 14 00 00 C6 43 08 00"),
}
LOCAL_REWRITE_QUERY_FLAGS = (
    "contentRouteRewrite",
    "worldUrlRewrite",
    "codebaseRewrite",
    "hostRewrite",
    "lobbyHostRewrite",
    "gameHostRewrite",
)
TRUE_QUERY_VALUES = {"1", "true", "yes", "on"}


class PROCESS_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Reserved1", ctypes.c_void_p),
        ("PebBaseAddress", ctypes.c_void_p),
        ("Reserved2_0", ctypes.c_void_p),
        ("Reserved2_1", ctypes.c_void_p),
        ("UniqueProcessId", ctypes.c_void_p),
        ("Reserved3", ctypes.c_void_p),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll", use_last_error=True)

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
kernel32.WriteProcessMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.LPCVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.WriteProcessMemory.restype = wintypes.BOOL
kernel32.VirtualProtectEx.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    ctypes.c_size_t,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.VirtualProtectEx.restype = wintypes.BOOL

ntdll.NtQueryInformationProcess.argtypes = [
    wintypes.HANDLE,
    wintypes.ULONG,
    wintypes.LPVOID,
    wintypes.ULONG,
    ctypes.POINTER(wintypes.ULONG),
]
ntdll.NtQueryInformationProcess.restype = wintypes.LONG


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Launch RuneScape.exe under Frida and rewrite the spawned rs2client.exe "
            "parameter pairs from a supplied jav_config.ws payload before the child starts."
        )
    )
    parser.add_argument("--wrapper-exe", required=True, help="Path to RuneScape.exe")
    parser.add_argument("--config-uri", required=True, help="Local jav_config.ws URL to hand to the wrapper")
    parser.add_argument(
        "--wrapper-extra-arg",
        action="append",
        default=[],
        help="Extra argument to append to the RuneScape.exe wrapper invocation before spawn",
    )
    parser.add_argument(
        "--trace-output",
        required=True,
        help="JSONL file to write hook/launch events into",
    )
    parser.add_argument(
        "--summary-output",
        help="Optional JSON summary file",
    )
    parser.add_argument(
        "--child-hook-output",
        help=(
            "Optional JSONL file to attach deep rs2client startup hooks before the child resumes. "
            "Useful for splash-stage tracing."
        ),
    )
    parser.add_argument(
        "--child-hook-verbose",
        action="store_true",
        help="Emit higher-volume child startup hook events when --child-hook-output is enabled.",
    )
    parser.add_argument(
        "--child-hook-duration-seconds",
        type=int,
        default=0,
        help=(
            "Optional time to keep the child startup hook attached after resume. "
            "0 preserves the original fire-and-exit behavior."
        ),
    )
    parser.add_argument(
        "--spawn-timeout-seconds",
        type=int,
        default=20,
        help="Maximum time to wait for the wrapper to spawn rs2client.exe",
    )
    parser.add_argument(
        "--rsa-config",
        help=(
            "Optional rsa.toml path. When provided, the tool patches the spawned rs2client.exe "
            "embedded login/js5 public-key literals to the local OpenNXT moduli before resume."
        ),
    )
    parser.add_argument(
        "--patch-null-read-offset",
        action="append",
        default=[],
        help=(
            "Optional rs2client.exe offset to patch before resuming the child. "
            "The tool only patches when the original bytes match the known null-read instruction."
        ),
    )
    parser.add_argument(
        "--patch-jump-bypass",
        action="append",
        default=[],
        help=(
            "Optional rs2client.exe block bypass patch in source:target form. "
            "The tool writes a relative JMP at the source when the original bytes "
            "match the known null-read fallback block."
        ),
    )
    parser.add_argument(
        "--patch-inline-offset",
        action="append",
        default=[],
        help=(
            "Optional rs2client.exe inline replacement offset. "
            "The tool only patches when the original bytes match a known guarded replacement."
        ),
    )
    parser.add_argument(
        "--resolve-redirect",
        action="append",
        default=[],
        help="Repeatable host=target redirect applied inside GetAddrInfo* before resuming the child",
    )
    parser.add_argument(
        "--rewrite-scope",
        choices=("all", "routes"),
        default="all",
        help="Choose whether to rewrite the full param map or only route-bearing params in the spawned child command line.",
    )
    parser.add_argument(
        "--child-exe-override",
        help=(
            "Optional local rs2client.exe path to force into the wrapper's child CreateProcess call. "
            "Useful when the visible RuneScape.exe wrapper would otherwise spawn the stale ProgramData child."
        ),
    )
    return parser.parse_args()


def parse_resolve_redirect_specs(values: list[str] | None) -> dict[str, str]:
    redirects: dict[str, str] = {}
    for raw_value in values or []:
        text = str(raw_value or "").strip()
        if not text or "=" not in text:
            raise ValueError(f"Invalid resolve redirect spec: {raw_value!r}")
        host, target = text.split("=", 1)
        normalized_host = host.strip().lower()
        normalized_target = target.strip()
        if not normalized_host or not normalized_target:
            raise ValueError(f"Invalid resolve redirect spec: {raw_value!r}")
        redirects[normalized_host] = normalized_target
    return redirects


def fetch_jav_config(config_uri: str) -> str:
    with urllib.request.urlopen(resolve_fetch_config_uri(config_uri), timeout=10) as response:
        raw = response.read()
    return raw.decode("utf-8", "replace")


def requests_local_rewrite_contract(config_uri: str) -> bool:
    parsed = urllib.parse.urlsplit(config_uri)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    for flag_name in LOCAL_REWRITE_QUERY_FLAGS:
        value = str(query.get(flag_name) or "").strip().lower()
        if value in TRUE_QUERY_VALUES:
            return True
    return False


def resolve_fetch_config_uri(config_uri: str) -> str:
    parsed = urllib.parse.urlsplit(config_uri)
    hostname = (parsed.hostname or "").lower()
    if hostname == "rs.config.runescape.com" and requests_local_rewrite_contract(config_uri):
        # Only explicit loopback/local-rewrite contracts fetch the startup
        # payload from the local HTTP bridge. The default secure 947 wrapper
        # path must fetch the retail config directly.
        return urllib.parse.urlunsplit(
            (
                "http",
                "localhost:8080",
                "/jav_config.ws",
                parsed.query,
                "",
            )
        )
    return config_uri


def should_auto_redirect_route_hosts(config_uri: str) -> bool:
    parsed = urllib.parse.urlsplit(config_uri)
    hostname = (parsed.hostname or "").lower()
    if hostname == "rs.config.runescape.com" and not requests_local_rewrite_contract(config_uri):
        # Keep the secure retail-shaped startup contract intact through the
        # application-resource splash phase. The caller can still provide
        # explicit world/lobby resolve redirects when localhost fallback is
        # required, but automatically redirecting the fetched route hosts here
        # recreates the 255/* reference-table loop before login.
        return False
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    for flag_name in LOCAL_REWRITE_QUERY_FLAGS:
        value = str(query.get(flag_name) or "").strip().lower()
        if value in TRUE_QUERY_VALUES:
            return True
    return False


def extract_param_map(jav_config_text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in jav_config_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("param="):
            continue
        payload = line[6:]
        separator = payload.find("=")
        if separator <= 0:
            continue
        key = payload[:separator]
        value = payload[separator + 1 :]
        result[key] = value
    return result


def build_route_rewrite_map(param_map: dict[str, str]) -> dict[str, str]:
    route_keys = ["3", "35", "37", "40", "41", "42", "43", "44", "45", "46", "47", "48", "49"]
    return {key: param_map[key] for key in route_keys if key in param_map}


def build_param_rewrite_map(param_map: dict[str, str]) -> dict[str, str]:
    return dict(param_map)


def build_effective_rewrite_map(jav_config_text: str, rewrite_scope: str = "all") -> dict[str, str]:
    param_map = extract_param_map(jav_config_text)
    if rewrite_scope == "routes":
        return build_route_rewrite_map(param_map)
    # The 947 wrapper hands a full param-pair command line to rs2client.exe.
    # Route-only rewrites leave the child on live retail splash/login metadata
    # (for example 18/27/29/31/34), which can strand the client in the
    # application-resource bootstrap even when the local JS5 wire is correct.
    return build_param_rewrite_map(param_map)


def build_route_resolve_redirects(param_map: dict[str, str], redirect_target: str = "localhost") -> dict[str, str]:
    redirects: dict[str, str] = {}

    def add_host(raw_host: str | None) -> None:
        host = str(raw_host or "").strip().lower()
        if not host or host in {"localhost", "127.0.0.1", "::1"}:
            return
        redirects[host] = redirect_target

    add_host(param_map.get("3"))
    add_host(param_map.get("37"))
    add_host(param_map.get("49"))

    for key in ("35", "40"):
        raw_url = str(param_map.get(key) or "").strip()
        if not raw_url:
            continue
        try:
            parsed = urllib.parse.urlsplit(raw_url)
        except ValueError:
            continue
        add_host(parsed.hostname)

    return redirects


def build_connect_redirects(
    resolve_redirects: dict[str, str],
    resolver: Callable[..., Any] | None = None,
) -> dict[str, str]:
    ip_redirects: dict[str, str] = {}
    lookup = resolver or socket.getaddrinfo
    for source_host, redirect_target in resolve_redirects.items():
        try:
            results = lookup(source_host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except OSError:
            continue
        for result in results:
            sockaddr = result[4] if len(result) >= 5 else None
            if not isinstance(sockaddr, tuple) or not sockaddr:
                continue
            ip_address = str(sockaddr[0]).strip()
            if not ip_address:
                continue
            ip_redirects[ip_address] = redirect_target
    return ip_redirects


def build_wrapper_spawn_script(child_exe_override: str | None) -> str:
    child_path = str(child_exe_override or "").strip()
    child_dir = str(Path(child_path).parent) if child_path else ""
    return f"""
const childExeOverride = {json.dumps(child_path)};
const childDirOverride = {json.dumps(child_dir)};
const overrideState = {{ consumed: false }};

function classifyRewriteTarget(pathValue, commandLineValue) {{
  const haystack = ((pathValue || "") + "\\n" + (commandLineValue || "")).toLowerCase();
  if (haystack.indexOf("rs2client.exe") !== -1) {{
    return "direct-match";
  }}
  if (!childExeOverride || overrideState.consumed) {{
    return null;
  }}
  if (haystack.indexOf("runescape.exe") !== -1 || haystack.indexOf("jagexlauncher") !== -1) {{
    return null;
  }}
  if (!pathValue && !commandLineValue) {{
    return null;
  }}
  if (haystack.indexOf(".exe") !== -1 || haystack.indexOf("--configuri") !== -1) {{
    return "one-shot";
  }}
  return null;
}}

function readUnicodeString(structPtr) {{
  if (structPtr.isNull()) {{
    return null;
  }}
  const length = structPtr.readU16();
  const buffer = structPtr.add(8).readPointer();
  if (buffer.isNull()) {{
    return null;
  }}
  if (length === 0) {{
    return "";
  }}
  return buffer.readUtf16String(length / 2);
}}

function writeUnicodeString(structPtr, text) {{
  const value = text || "";
  const buffer = Memory.allocUtf16String(value);
  structPtr.writeU16(value.length * 2);
  structPtr.add(2).writeU16((value.length + 1) * 2);
  structPtr.add(8).writePointer(buffer);
  return buffer;
}}

function buildOverriddenCommandLine(commandLineValue) {{
  const quotedExe = childExeOverride.indexOf(" ") !== -1 ? '"' + childExeOverride + '"' : childExeOverride;
  if (!commandLineValue) {{
    return quotedExe;
  }}
  const match = /^(?:"[^"]+"|\\S+)([\\s\\S]*)$/.exec(commandLineValue);
  const suffix = match ? match[1] : "";
  return quotedExe + suffix;
}}

function installCreateProcessHook(moduleName, exportName, appIndex, cmdIndex, dirIndex, encoding) {{
  let address = null;
  try {{
    if (typeof Module.findExportByName === "function") {{
      address = Module.findExportByName(moduleName, exportName);
    }} else if (typeof Module.getExportByName === "function") {{
      address = Module.getExportByName(moduleName, exportName);
    }}
  }} catch (_error) {{
    address = null;
  }}
  if (address === null) {{
    return;
  }}

  Interceptor.attach(address, {{
    onEnter(args) {{
      if (!childExeOverride) {{
        return;
      }}

      let originalApp = null;
      let originalCmd = null;
      try {{
        originalApp = args[appIndex].isNull() ? null : (encoding === "ansi" ? args[appIndex].readAnsiString() : args[appIndex].readUtf16String());
      }} catch (_error) {{}}
      try {{
        originalCmd = args[cmdIndex].isNull() ? null : (encoding === "ansi" ? args[cmdIndex].readAnsiString() : args[cmdIndex].readUtf16String());
      }} catch (_error) {{}}

      const matchKind = classifyRewriteTarget(originalApp, originalCmd);
      if (!matchKind) {{
        return;
      }}

      const replacementApp = encoding === "ansi"
        ? Memory.allocAnsiString(childExeOverride)
        : Memory.allocUtf16String(childExeOverride);
      const replacementCmdText = buildOverriddenCommandLine(originalCmd);
      const replacementCmd = encoding === "ansi"
        ? Memory.allocAnsiString(replacementCmdText)
        : Memory.allocUtf16String(replacementCmdText);
      const replacementDir = childDirOverride
        ? (encoding === "ansi" ? Memory.allocAnsiString(childDirOverride) : Memory.allocUtf16String(childDirOverride))
        : ptr(0);

      args[appIndex] = replacementApp;
      args[cmdIndex] = replacementCmd;
      if (dirIndex >= 0) {{
        args[dirIndex] = replacementDir;
      }}
      overrideState.consumed = true;

      send({{
        action: "wrapper-child-createprocess-rewritten",
        api: exportName,
        matchKind: matchKind,
        originalApplicationName: originalApp,
        originalCommandLine: originalCmd,
        rewrittenApplicationName: childExeOverride,
        rewrittenCommandLine: replacementCmdText,
        rewrittenCurrentDirectory: childDirOverride || null,
        timestamp: Date.now() / 1000.0
      }});
    }}
  }});
}}

function installShellExecuteHook(moduleName, exportName, fileIndex, paramsIndex, dirIndex, encoding) {{
  let address = null;
  try {{
    if (typeof Module.findExportByName === "function") {{
      address = Module.findExportByName(moduleName, exportName);
    }} else if (typeof Module.getExportByName === "function") {{
      address = Module.getExportByName(moduleName, exportName);
    }}
  }} catch (_error) {{
    address = null;
  }}
  if (address === null) {{
    return;
  }}

  Interceptor.attach(address, {{
    onEnter(args) {{
      if (!childExeOverride) {{
        return;
      }}

      let originalFile = null;
      let originalParameters = null;
      let originalDirectory = null;
      try {{
        originalFile = args[fileIndex].isNull() ? null : (encoding === "ansi" ? args[fileIndex].readAnsiString() : args[fileIndex].readUtf16String());
      }} catch (_error) {{}}
      try {{
        originalParameters = args[paramsIndex].isNull() ? null : (encoding === "ansi" ? args[paramsIndex].readAnsiString() : args[paramsIndex].readUtf16String());
      }} catch (_error) {{}}
      try {{
        originalDirectory = args[dirIndex].isNull() ? null : (encoding === "ansi" ? args[dirIndex].readAnsiString() : args[dirIndex].readUtf16String());
      }} catch (_error) {{}}

      const matchKind = classifyRewriteTarget(originalFile, originalParameters);
      if (!matchKind) {{
        return;
      }}

      const replacementFile = encoding === "ansi"
        ? Memory.allocAnsiString(childExeOverride)
        : Memory.allocUtf16String(childExeOverride);
      const replacementDirectory = childDirOverride
        ? (encoding === "ansi" ? Memory.allocAnsiString(childDirOverride) : Memory.allocUtf16String(childDirOverride))
        : ptr(0);

      args[fileIndex] = replacementFile;
      if (dirIndex >= 0) {{
        args[dirIndex] = replacementDirectory;
      }}
      overrideState.consumed = true;

      send({{
        action: "wrapper-child-shellexecute-rewritten",
        api: exportName,
        matchKind: matchKind,
        originalFile: originalFile,
        originalParameters: originalParameters,
        originalDirectory: originalDirectory,
        rewrittenFile: childExeOverride,
        rewrittenParameters: originalParameters,
        rewrittenDirectory: childDirOverride || null,
        timestamp: Date.now() / 1000.0
      }});
    }}
  }});
}}

function installShellExecuteExHook(moduleName, exportName, encoding) {{
  let address = null;
  try {{
    if (typeof Module.findExportByName === "function") {{
      address = Module.findExportByName(moduleName, exportName);
    }} else if (typeof Module.getExportByName === "function") {{
      address = Module.getExportByName(moduleName, exportName);
    }}
  }} catch (_error) {{
    address = null;
  }}
  if (address === null) {{
    return;
  }}

  const fileOffset = Process.pointerSize === 8 ? 0x20 : 0x14;
  const paramsOffset = Process.pointerSize === 8 ? 0x28 : 0x18;
  const dirOffset = Process.pointerSize === 8 ? 0x30 : 0x1c;

  Interceptor.attach(address, {{
    onEnter(args) {{
      if (!childExeOverride) {{
        return;
      }}

      const executeInfo = args[0];
      if (executeInfo.isNull()) {{
        return;
      }}

      let originalFile = null;
      let originalParameters = null;
      let originalDirectory = null;
      try {{
        const filePointer = executeInfo.add(fileOffset).readPointer();
        originalFile = filePointer.isNull() ? null : (encoding === "ansi" ? filePointer.readAnsiString() : filePointer.readUtf16String());
      }} catch (_error) {{}}
      try {{
        const paramsPointer = executeInfo.add(paramsOffset).readPointer();
        originalParameters = paramsPointer.isNull() ? null : (encoding === "ansi" ? paramsPointer.readAnsiString() : paramsPointer.readUtf16String());
      }} catch (_error) {{}}
      try {{
        const dirPointer = executeInfo.add(dirOffset).readPointer();
        originalDirectory = dirPointer.isNull() ? null : (encoding === "ansi" ? dirPointer.readAnsiString() : dirPointer.readUtf16String());
      }} catch (_error) {{}}

      const matchKind = classifyRewriteTarget(originalFile, originalParameters);
      if (!matchKind) {{
        return;
      }}

      const replacementFile = encoding === "ansi"
        ? Memory.allocAnsiString(childExeOverride)
        : Memory.allocUtf16String(childExeOverride);
      const replacementDirectory = childDirOverride
        ? (encoding === "ansi" ? Memory.allocAnsiString(childDirOverride) : Memory.allocUtf16String(childDirOverride))
        : ptr(0);

      executeInfo.add(fileOffset).writePointer(replacementFile);
      if (dirOffset >= 0) {{
        executeInfo.add(dirOffset).writePointer(replacementDirectory);
      }}
      overrideState.consumed = true;

      send({{
        action: "wrapper-child-shellexecuteex-rewritten",
        api: exportName,
        matchKind: matchKind,
        originalFile: originalFile,
        originalParameters: originalParameters,
        originalDirectory: originalDirectory,
        rewrittenFile: childExeOverride,
        rewrittenParameters: originalParameters,
        rewrittenDirectory: childDirOverride || null,
        timestamp: Date.now() / 1000.0
      }});
    }}
  }});
}}

function installNtCreateUserProcessHook() {{
  let address = null;
  try {{
    if (typeof Module.findExportByName === "function") {{
      address = Module.findExportByName("ntdll.dll", "NtCreateUserProcess");
    }} else if (typeof Module.getExportByName === "function") {{
      address = Module.getExportByName("ntdll.dll", "NtCreateUserProcess");
    }}
  }} catch (_error) {{
    address = null;
  }}
  if (address === null) {{
    return;
  }}

  Interceptor.attach(address, {{
    onEnter(args) {{
      if (!childExeOverride) {{
        return;
      }}

      const processParameters = args[8];
      if (processParameters.isNull()) {{
        return;
      }}

      const imagePathStruct = processParameters.add(0x60);
      const commandLineStruct = processParameters.add(0x70);
      const originalImagePath = readUnicodeString(imagePathStruct);
      const originalCommandLine = readUnicodeString(commandLineStruct);
      const matchKind = classifyRewriteTarget(originalImagePath, originalCommandLine);
      if (!matchKind) {{
        return;
      }}

      const rewrittenCommandLine = buildOverriddenCommandLine(originalCommandLine);
      writeUnicodeString(imagePathStruct, childExeOverride);
      writeUnicodeString(commandLineStruct, rewrittenCommandLine);
      overrideState.consumed = true;

      send({{
        action: "wrapper-child-ntcreateuserprocess-rewritten",
        matchKind: matchKind,
        originalImagePath: originalImagePath,
        originalCommandLine: originalCommandLine,
        rewrittenImagePath: childExeOverride,
        rewrittenCommandLine: rewrittenCommandLine,
        timestamp: Date.now() / 1000.0
      }});
    }}
  }});
}}

installCreateProcessHook("kernel32.dll", "CreateProcessW", 0, 1, 7, "wide");
installCreateProcessHook("kernelbase.dll", "CreateProcessW", 0, 1, 7, "wide");
installCreateProcessHook("kernelbase.dll", "CreateProcessInternalW", 1, 2, 8, "wide");
installCreateProcessHook("kernel32.dll", "CreateProcessA", 0, 1, 7, "ansi");
installCreateProcessHook("kernelbase.dll", "CreateProcessA", 0, 1, 7, "ansi");
installCreateProcessHook("advapi32.dll", "CreateProcessAsUserW", 1, 2, 8, "wide");
installCreateProcessHook("advapi32.dll", "CreateProcessAsUserA", 1, 2, 8, "ansi");
installCreateProcessHook("advapi32.dll", "CreateProcessWithTokenW", 2, 3, 6, "wide");
installCreateProcessHook("advapi32.dll", "CreateProcessWithTokenA", 2, 3, 6, "ansi");
installCreateProcessHook("advapi32.dll", "CreateProcessWithLogonW", 4, 5, 8, "wide");
installShellExecuteHook("shell32.dll", "ShellExecuteA", 2, 3, 4, "ansi");
installShellExecuteHook("shell32.dll", "ShellExecuteW", 2, 3, 4, "wide");
installShellExecuteExHook("shell32.dll", "ShellExecuteExA", "ansi");
installShellExecuteExHook("shell32.dll", "ShellExecuteExW", "wide");
installNtCreateUserProcessHook();
"""


def paths_equal(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return str(Path(left).resolve(strict=False)).lower() == str(Path(right).resolve(strict=False)).lower()


def tokenize_windows_command_line(command_line: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    in_quotes = False
    token_started = False
    index = 0
    length = len(command_line)
    while index < length:
        character = command_line[index]
        if character == '"':
            in_quotes = not in_quotes
            token_started = True
            index += 1
            continue
        if character.isspace() and not in_quotes:
            if token_started:
                tokens.append("".join(current))
                current.clear()
                token_started = False
            index += 1
            continue
        current.append(character)
        token_started = True
        index += 1
    if token_started:
        tokens.append("".join(current))
    return tokens


def quote_windows_argument(argument: str) -> str:
    escaped = argument.replace('"', r"\"")
    return f'"{escaped}"'


def format_windows_argument(argument: str) -> str:
    if argument == "":
        return '""'
    if any(character.isspace() for character in argument) or '"' in argument:
        return quote_windows_argument(argument)
    return argument


def rebuild_windows_command_line(arguments: list[str]) -> str:
    return " ".join(format_windows_argument(argument) for argument in arguments)


def rewrite_param_tokens(arguments: list[str], rewrite_map: dict[str, str]) -> tuple[list[str], list[dict[str, str]]]:
    rewritten = list(arguments)
    changes: list[dict[str, str]] = []
    index = 1 if rewritten and rewritten[0].lower().endswith(".exe") else 0
    while index + 1 < len(rewritten):
        key = rewritten[index]
        if not key.isdigit():
            break
        old_value = rewritten[index + 1]
        if key in rewrite_map:
            new_value = rewrite_map[key]
            if old_value != new_value:
                rewritten[index + 1] = new_value
                changes.append({"param": key, "old": old_value, "new": new_value})
        index += 2
    return rewritten, changes


def rewrite_command_line_text(command_line: str, rewrite_map: dict[str, str]) -> tuple[str, list[dict[str, str]]]:
    arguments = tokenize_windows_command_line(command_line)
    rewritten, changes = rewrite_param_tokens(arguments, rewrite_map)
    return rebuild_windows_command_line(rewritten), changes


def normalize_patch_offsets(raw_offsets: list[str]) -> list[int]:
    normalized: list[int] = []
    for raw in raw_offsets:
        if raw is None:
            continue
        value = raw.strip()
        if not value:
            continue
        normalized.append(int(value, 0))
    return normalized


def normalize_jump_bypass_specs(raw_specs: list[str]) -> list[tuple[int, int]]:
    normalized: list[tuple[int, int]] = []
    for raw in raw_specs:
        if raw is None:
            continue
        value = raw.strip()
        if not value:
            continue
        parts = value.split(":", 1)
        if len(parts) != 2:
            raise ValueError(f"Jump bypass spec must be source:target, got {raw!r}")
        normalized.append((int(parts[0], 0), int(parts[1], 0)))
    return normalized


def load_rsa_moduli(rsa_config_path: Path) -> dict[str, str]:
    raw = tomllib.loads(rsa_config_path.read_text(encoding="utf-8"))
    result: dict[str, str] = {}
    for section in ("login", "js5"):
        section_data = raw.get(section)
        if not isinstance(section_data, dict):
            raise ValueError(f"Missing [{section}] section in {rsa_config_path}")
        modulus = section_data.get("modulus")
        if not isinstance(modulus, str) or not modulus.strip():
            raise ValueError(f"Missing {section}.modulus in {rsa_config_path}")
        result[section] = modulus.strip().lower()
    return result


def find_embedded_rsa_key(data: bytes, bits: int) -> tuple[int | None, str | None]:
    size = bits // 4
    for index in range(1, len(data) - size - 2):
        if data[index] == 0:
            continue
        if data[index - 1] != 0:
            continue
        if data[index + size + 1] != 0 or data[index + size + 2] != 0:
            continue
        candidate = data[index : index + size]
        try:
            text = candidate.decode("ascii")
            int(text, 16)
            return index, text
        except (UnicodeDecodeError, ValueError):
            continue
    return None, None


def _open_process(pid: int) -> wintypes.HANDLE:
    handle = kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE,
        False,
        pid,
    )
    if not handle:
        raise OSError(ctypes.get_last_error(), f"OpenProcess failed for pid {pid}")
    return handle


def _read_process_memory(handle: wintypes.HANDLE, address: int, size: int) -> bytes:
    buffer = (ctypes.c_ubyte * size)()
    bytes_read = ctypes.c_size_t()
    ok = kernel32.ReadProcessMemory(handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(bytes_read))
    if not ok:
        raise OSError(ctypes.get_last_error(), f"ReadProcessMemory failed at 0x{address:x}")
    return bytes(buffer[: bytes_read.value])


def _write_process_memory(handle: wintypes.HANDLE, address: int, data: bytes) -> None:
    buffer = ctypes.create_string_buffer(data)
    bytes_written = ctypes.c_size_t()
    old_protection = wintypes.DWORD()
    protect_ok = kernel32.VirtualProtectEx(
        handle,
        ctypes.c_void_p(address),
        len(data),
        PAGE_EXECUTE_READWRITE,
        ctypes.byref(old_protection),
    )
    if not protect_ok:
        raise OSError(ctypes.get_last_error(), f"VirtualProtectEx failed at 0x{address:x}")
    try:
        ok = kernel32.WriteProcessMemory(handle, ctypes.c_void_p(address), buffer, len(data), ctypes.byref(bytes_written))
        if not ok or bytes_written.value != len(data):
            raise OSError(ctypes.get_last_error(), f"WriteProcessMemory failed at 0x{address:x}")
    finally:
        restored_protection = wintypes.DWORD()
        kernel32.VirtualProtectEx(
            handle,
            ctypes.c_void_p(address),
            len(data),
            old_protection.value,
            ctypes.byref(restored_protection),
        )


def read_remote_process_command_line(pid: int) -> tuple[str, int, int, int]:
    handle = _open_process(pid)
    try:
        pbi = PROCESS_BASIC_INFORMATION()
        return_length = wintypes.ULONG()
        status = ntdll.NtQueryInformationProcess(
            handle,
            PROCESS_BASIC_INFORMATION_CLASS,
            ctypes.byref(pbi),
            ctypes.sizeof(pbi),
            ctypes.byref(return_length),
        )
        if status != 0:
            raise OSError(status, f"NtQueryInformationProcess failed for pid {pid}")

        peb_bytes = _read_process_memory(handle, int(pbi.PebBaseAddress), 0x30)
        process_parameters_address = int.from_bytes(
            peb_bytes[PEB_PROCESS_PARAMETERS_OFFSET_X64 : PEB_PROCESS_PARAMETERS_OFFSET_X64 + 8],
            "little",
        )
        params_bytes = _read_process_memory(
            handle,
            process_parameters_address + RTL_USER_PROCESS_PARAMETERS_COMMAND_LINE_OFFSET_X64,
            16,
        )
        length = int.from_bytes(params_bytes[0:2], "little")
        maximum_length = int.from_bytes(params_bytes[2:4], "little")
        buffer_address = int.from_bytes(params_bytes[8:16], "little")
        command_line_bytes = _read_process_memory(handle, buffer_address, length)
        text = command_line_bytes.decode("utf-16-le", "replace")
        return text, process_parameters_address, buffer_address, maximum_length
    finally:
        kernel32.CloseHandle(handle)


def read_remote_process_image_base(pid: int) -> int:
    handle = _open_process(pid)
    try:
        pbi = PROCESS_BASIC_INFORMATION()
        return_length = wintypes.ULONG()
        status = ntdll.NtQueryInformationProcess(
            handle,
            PROCESS_BASIC_INFORMATION_CLASS,
            ctypes.byref(pbi),
            ctypes.sizeof(pbi),
            ctypes.byref(return_length),
        )
        if status != 0:
            raise OSError(status, f"NtQueryInformationProcess failed for pid {pid}")

        peb_bytes = _read_process_memory(handle, int(pbi.PebBaseAddress), 0x18)
        return int.from_bytes(peb_bytes[0x10:0x18], "little")
    finally:
        kernel32.CloseHandle(handle)


def read_remote_process_image_layout(pid: int) -> tuple[int, int]:
    handle = _open_process(pid)
    try:
        image_base = read_remote_process_image_base(pid)
        header = _read_process_memory(handle, image_base, 0x400)
        if header[:2] != b"MZ":
            raise ValueError(f"Process image at 0x{image_base:x} is missing DOS header")
        e_lfanew = int.from_bytes(header[0x3C:0x40], "little")
        minimum_nt_header = e_lfanew + 0x58
        if minimum_nt_header > len(header):
            header = _read_process_memory(handle, image_base, minimum_nt_header)
        if header[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
            raise ValueError(f"Process image at 0x{image_base:x} is missing PE header")
        size_of_image = int.from_bytes(header[e_lfanew + 0x50 : e_lfanew + 0x54], "little")
        if size_of_image <= 0:
            raise ValueError(f"Process image at 0x{image_base:x} reported invalid size {size_of_image}")
        return image_base, size_of_image
    finally:
        kernel32.CloseHandle(handle)


def patch_remote_ascii_literal_occurrences(pid: int, original_text: str, replacement_text: str) -> dict[str, Any]:
    original = original_text.encode("ascii")
    replacement = replacement_text.encode("ascii")
    if len(original) != len(replacement):
        raise ValueError(
            f"Replacement length mismatch: original={len(original)} bytes replacement={len(replacement)} bytes"
        )

    image_base, image_size = read_remote_process_image_layout(pid)
    handle = _open_process(pid)
    try:
        image = _read_process_memory(handle, image_base, image_size)
        occurrences: list[dict[str, Any]] = []
        cursor = 0
        while True:
            found = image.find(original, cursor)
            if found == -1:
                break
            address = image_base + found
            current = _read_process_memory(handle, address, len(original))
            matched = current == original
            if matched:
                _write_process_memory(handle, address, replacement)
            occurrences.append(
                {
                    "address": f"0x{address:x}",
                    "matched": matched,
                    "originalHexPreview": current[:16].hex(),
                    "replacementHexPreview": replacement[:16].hex() if matched else None,
                }
            )
            cursor = found + len(original)
        return {
            "imageBase": f"0x{image_base:x}",
            "imageSize": image_size,
            "occurrences": occurrences,
        }
    finally:
        kernel32.CloseHandle(handle)


def patch_remote_embedded_rsa_moduli(
    pid: int,
    executable_path: Path,
    rsa_config_path: Path,
) -> dict[str, Any]:
    executable_bytes = executable_path.read_bytes()
    target_moduli = load_rsa_moduli(rsa_config_path)
    results: dict[str, Any] = {
        "executablePath": str(executable_path),
        "rsaConfigPath": str(rsa_config_path),
    }

    for name, bits in (("login", 1024), ("js5", 4096)):
        embedded_offset, original_modulus = find_embedded_rsa_key(executable_bytes, bits)
        replacement_modulus = target_moduli[name]
        if original_modulus is None:
            results[name] = {
                "foundInExecutable": False,
                "embeddedOffset": None,
                "patch": None,
            }
            continue
        patch_result = patch_remote_ascii_literal_occurrences(pid, original_modulus, replacement_modulus)
        results[name] = {
            "foundInExecutable": True,
            "embeddedOffset": f"0x{embedded_offset:x}",
            "originalModulusPreview": original_modulus[:32],
            "replacementModulusPreview": replacement_modulus[:32],
            "patch": patch_result,
        }

    return results


def patch_remote_process_command_line(pid: int, rewritten_command_line: str) -> dict[str, Any]:
    handle = _open_process(pid)
    try:
        original_text, process_parameters_address, buffer_address, maximum_length = read_remote_process_command_line(pid)
        encoded = rewritten_command_line.encode("utf-16-le")
        if len(encoded) + 2 > maximum_length:
            raise ValueError(
                f"Rewritten command line requires {len(encoded) + 2} bytes but only {maximum_length} are available"
            )
        _write_process_memory(handle, buffer_address, encoded + b"\x00\x00")
        _write_process_memory(
            handle,
            process_parameters_address + RTL_USER_PROCESS_PARAMETERS_COMMAND_LINE_OFFSET_X64,
            int(len(encoded)).to_bytes(2, "little"),
        )
        patched_text, _, _, _ = read_remote_process_command_line(pid)
        return {
            "original": original_text,
            "patched": patched_text,
            "bufferAddress": f"0x{buffer_address:x}",
            "maximumLength": maximum_length,
        }
    finally:
        kernel32.CloseHandle(handle)


def patch_remote_null_read_offsets(pid: int, offsets: list[int]) -> list[dict[str, Any]]:
    if not offsets:
        return []

    image_base = read_remote_process_image_base(pid)
    expected = bytes.fromhex("44 8B 04 25 00 00 00 00")
    replacement = bytes.fromhex("45 33 C0 90 90 90 90 90")
    results: list[dict[str, Any]] = []

    handle = _open_process(pid)
    try:
        for offset in offsets:
            address = image_base + offset
            original = _read_process_memory(handle, address, len(expected))
            matched = original == expected
            if matched:
                _write_process_memory(handle, address, replacement)
            results.append(
                {
                    "offset": f"0x{offset:x}",
                    "address": f"0x{address:x}",
                    "matched": matched,
                    "originalHex": original.hex(),
                    "patchedHex": replacement.hex() if matched else None,
                }
            )
    finally:
        kernel32.CloseHandle(handle)

    return results


def patch_remote_inline_offsets(pid: int, offsets: list[int]) -> list[dict[str, Any]]:
    if not offsets:
        return []

    image_base = read_remote_process_image_base(pid)
    results: list[dict[str, Any]] = []

    handle = _open_process(pid)
    try:
        for offset in offsets:
            patch_spec = KNOWN_INLINE_PATCHES.get(offset)
            if patch_spec is None:
                results.append(
                    {
                        "offset": f"0x{offset:x}",
                        "address": f"0x{image_base + offset:x}",
                        "matched": False,
                        "expectedHex": None,
                        "originalHex": None,
                        "patchedHex": None,
                        "reason": "unknown-inline-patch-offset",
                    }
                )
                continue

            expected = patch_spec["expected"]
            replacement = patch_spec["replacement"]
            address = image_base + offset
            original = _read_process_memory(handle, address, len(expected))
            matched = original == expected
            if matched:
                _write_process_memory(handle, address, replacement)
            results.append(
                {
                    "offset": f"0x{offset:x}",
                    "address": f"0x{address:x}",
                    "matched": matched,
                    "expectedHex": expected.hex(),
                    "originalHex": original.hex(),
                    "patchedHex": replacement.hex() if matched else None,
                }
            )
    finally:
        kernel32.CloseHandle(handle)

    return results


def _encode_relative_jump(source_address: int, target_address: int, patch_size: int) -> bytes:
    displacement = target_address - (source_address + 5)
    if not -(2**31) <= displacement <= (2**31 - 1):
        raise ValueError(
            f"Relative jump displacement out of range: source=0x{source_address:x} target=0x{target_address:x}"
        )
    return b"\xE9" + int(displacement).to_bytes(4, "little", signed=True) + (b"\x90" * (patch_size - 5))


def patch_remote_jump_bypass_blocks(pid: int, jump_specs: list[tuple[int, int]]) -> list[dict[str, Any]]:
    if not jump_specs:
        return []

    image_base = read_remote_process_image_base(pid)
    results: list[dict[str, Any]] = []

    handle = _open_process(pid)
    try:
        for source_offset, target_offset in jump_specs:
            expected = KNOWN_JUMP_BYPASS_BLOCKS.get(source_offset, DEFAULT_NULL_READ_BLOCK)
            source_address = image_base + source_offset
            target_address = image_base + target_offset
            original = _read_process_memory(handle, source_address, len(expected))
            matched = original == expected
            patched = None
            if matched:
                patched = _encode_relative_jump(source_address, target_address, len(expected))
                _write_process_memory(handle, source_address, patched)
            results.append(
                {
                    "sourceOffset": f"0x{source_offset:x}",
                    "targetOffset": f"0x{target_offset:x}",
                    "sourceAddress": f"0x{source_address:x}",
                    "targetAddress": f"0x{target_address:x}",
                    "matched": matched,
                    "expectedHex": expected.hex(),
                    "originalHex": original.hex(),
                    "patchedHex": patched.hex() if patched is not None else None,
                }
            )
    finally:
        kernel32.CloseHandle(handle)

    return results


def query_process_command_line(pid: int) -> str | None:
    command = (
        "Get-CimInstance Win32_Process -Filter "
        f"\"ProcessId = {pid}\" | Select-Object -ExpandProperty CommandLine"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def query_process_path(pid: int) -> str | None:
    command = (
        "Get-CimInstance Win32_Process -Filter "
        f"\"ProcessId = {pid}\" | Select-Object -ExpandProperty ExecutablePath"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def terminate_process_tree(pid: int) -> dict[str, Any]:
    completed = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    alive_after_taskkill = query_process_path(pid) is not None or query_process_command_line(pid) is not None
    fallback_completed: subprocess.CompletedProcess[str] | None = None
    if alive_after_taskkill:
        fallback_completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        time.sleep(0.25)
    alive_after_fallback = query_process_path(pid) is not None or query_process_command_line(pid) is not None
    return {
        "pid": pid,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "aliveAfterTaskkill": alive_after_taskkill,
        "fallbackReturncode": fallback_completed.returncode if fallback_completed is not None else None,
        "fallbackStdout": fallback_completed.stdout.strip() if fallback_completed is not None else "",
        "fallbackStderr": fallback_completed.stderr.strip() if fallback_completed is not None else "",
        "aliveAfterFallback": alive_after_fallback,
    }


def terminate_process_only(pid: int) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    time.sleep(0.25)
    alive_after = query_process_path(pid) is not None or query_process_command_line(pid) is not None
    return {
        "pid": pid,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "aliveAfterStopProcess": alive_after,
    }


def cleanup_spawned_processes(
    wrapper_pid: int | None,
    child_pid: int | None,
    reason: str,
    write_event: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    targets: list[int] = []
    for pid in (child_pid, wrapper_pid):
        if pid is None or pid in targets:
            continue
        targets.append(pid)

    if not targets:
        return []

    cleanup_results = []
    if write_event is not None:
        write_event(
            {
                "timestamp": round(time.time(), 6),
                "category": "client.lifecycle",
                "action": "spawn-cleanup-start",
                "reason": reason,
                "wrapperPid": wrapper_pid,
                "childPid": child_pid,
                "targetPids": targets,
            }
        )

    for pid in targets:
        cleanup_results.append(terminate_process_tree(pid))

    if write_event is not None:
        write_event(
            {
                "timestamp": round(time.time(), 6),
                "category": "client.lifecycle",
                "action": "spawn-cleanup-done",
                "reason": reason,
                "wrapperPid": wrapper_pid,
                "childPid": child_pid,
                "cleanupResults": cleanup_results,
            }
        )

    return cleanup_results


def cleanup_wrapper_after_child_ready(
    wrapper_pid: int | None,
    child_pid: int | None,
    write_event: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any] | None:
    if wrapper_pid is None or child_pid is None or wrapper_pid == child_pid:
        return None

    wrapper_path = query_process_path(wrapper_pid)
    child_path = query_process_path(child_pid)
    if wrapper_path is None or child_path is None:
        return None
    if not wrapper_path.lower().endswith("runescape.exe"):
        return None
    if not child_path.lower().endswith("rs2client.exe"):
        return None

    # Keep the wrapper alive. On the local 947 RuneScape.exe path, terminating the
    # wrapper tears down the spawned child as well, which makes the faithful wrapper
    # bootstrap path unusable even when the child has already been patched/resumed.
    if write_event is not None:
        write_event(
            {
                "timestamp": round(time.time(), 6),
                "category": "client.lifecycle",
                "action": "wrapper-cleanup-skipped",
                "wrapperPid": wrapper_pid,
                "childPid": child_pid,
                "wrapperPath": wrapper_path,
                "childPath": child_path,
                "reason": "preserve-wrapper-child-lifetime",
            }
        )

    return {
        "pid": wrapper_pid,
        "skipped": True,
        "reason": "preserve-wrapper-child-lifetime",
        "childAliveAfterSkip": query_process_path(child_pid) is not None or query_process_command_line(child_pid) is not None,
    }


def main() -> int:
    args = parse_args()
    inline_patch_offsets = normalize_patch_offsets(args.patch_inline_offset)
    patch_offsets = normalize_patch_offsets(args.patch_null_read_offset)
    jump_bypass_specs = normalize_jump_bypass_specs(args.patch_jump_bypass)
    explicit_resolve_redirects = parse_resolve_redirect_specs(args.resolve_redirect)
    rsa_config_path = Path(args.rsa_config) if args.rsa_config else None
    child_exe_override = Path(args.child_exe_override) if args.child_exe_override else None
    wrapper_exe = Path(args.wrapper_exe)
    trace_output = Path(args.trace_output)
    trace_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output = Path(args.summary_output) if args.summary_output else None
    if summary_output is not None:
        summary_output.parent.mkdir(parents=True, exist_ok=True)
    child_hook_output = Path(args.child_hook_output) if args.child_hook_output else None
    if child_hook_output is not None:
        child_hook_output.parent.mkdir(parents=True, exist_ok=True)

    jav_config_text = fetch_jav_config(args.config_uri)
    param_map = extract_param_map(jav_config_text)
    rewrite_map = build_effective_rewrite_map(jav_config_text, rewrite_scope=args.rewrite_scope)
    resolve_redirects = (
        build_route_resolve_redirects(param_map)
        if should_auto_redirect_route_hosts(args.config_uri)
        else {}
    )
    resolve_redirects.update(explicit_resolve_redirects)
    connect_redirects = build_connect_redirects(resolve_redirects)
    child_created = threading.Event()
    detached = threading.Event()
    child_process_id: int | None = None
    last_rewritten_command_line: str | None = None
    last_inline_patch_results: list[dict[str, Any]] = []
    last_null_patch_results: list[dict[str, Any]] = []
    last_jump_patch_results: list[dict[str, Any]] = []
    last_rsa_patch_results: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []
    child_trace_lock = threading.Lock()
    child_trace_sessions: list[frida.core.Session] = []
    child_trace_scripts: list[frida.core.Script] = []
    wrapper_script: frida.core.Script | None = None
    wrapper_pid: int | None = None

    with trace_output.open("w", encoding="utf-8") as handle:
        child_hook_handle = child_hook_output.open("w", encoding="utf-8") if child_hook_output is not None else None
        def write_event(event: dict[str, Any]) -> None:
            handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")
            handle.flush()
            events.append(event)

        def write_child_event(event: dict[str, Any]) -> None:
            if child_hook_handle is None:
                return
            with child_trace_lock:
                child_hook_handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")
                child_hook_handle.flush()

        def make_child_hook_message_handler(child_pid: int):
            def on_child_message(message: dict[str, Any], _data: bytes | None) -> None:
                if message.get("type") == "send":
                    payload = message.get("payload", {})
                    if isinstance(payload, dict):
                        normalized = normalize_child_live_payload(payload)
                        normalized.setdefault("pid", child_pid)
                        write_child_event(normalized)
                    else:
                        write_child_event(
                            {
                                "timestamp": round(time.time(), 6),
                                "category": "client.unknown",
                                "action": "message",
                                "pid": child_pid,
                                "payload": payload,
                            }
                        )
                    return

                write_child_event(
                    {
                        "timestamp": round(time.time(), 6),
                        "category": "client.unknown",
                        "action": "frida-message",
                        "pid": child_pid,
                        "message": message,
                    }
                )

            return on_child_message

        def on_message(message: dict[str, Any], data: bytes | None) -> None:
            if message.get("type") == "send":
                payload = message.get("payload", {})
                if isinstance(payload, dict):
                    write_event(payload)
                    if payload.get("action") in {
                        "wrapper-child-createprocess-rewritten",
                        "wrapper-child-shellexecute-rewritten",
                        "wrapper-child-shellexecuteex-rewritten",
                        "wrapper-child-ntcreateuserprocess-rewritten",
                    }:
                        nonlocal_vars["override_mechanism"] = payload.get("action")
                    if payload.get("action") == "child-command-line-rewritten":
                        rewritten = payload.get("rewrittenCommandLine")
                        if isinstance(rewritten, str) and rewritten:
                            nonlocal_vars["last_rewritten_command_line"] = rewritten
                else:
                    write_event({"type": "frida-send", "payload": payload, "timestamp": time.time()})
                return
            write_event({"type": "frida-message", "message": message, "timestamp": time.time()})

        nonlocal_vars: dict[str, Any] = {
            "child_process_id": None,
            "last_rewritten_command_line": None,
            "override_mechanism": None,
        }

        device = frida.get_local_device()
        wrapper_argv = [str(wrapper_exe), f"--configURI={args.config_uri}", *args.wrapper_extra_arg]
        wrapper_pid = device.spawn(wrapper_argv, cwd=str(wrapper_exe.parent))
        write_event(
            {
                "action": "wrapper-spawned",
                "processId": wrapper_pid,
                "path": str(wrapper_exe),
                "argv": wrapper_argv,
                "timestamp": time.time(),
            }
        )
        session = device.attach(wrapper_pid)
        session.enable_child_gating()
        if child_exe_override is not None:
            wrapper_script = session.create_script(build_wrapper_spawn_script(str(child_exe_override)))
            wrapper_script.on("message", on_message)
            wrapper_script.load()
            write_event(
                {
                    "action": "wrapper-child-exe-override-armed",
                    "processId": wrapper_pid,
                    "childExeOverride": str(child_exe_override),
                    "timestamp": time.time(),
                }
            )

        def on_child_added(child: Any) -> None:
            nonlocal last_inline_patch_results
            nonlocal last_jump_patch_results
            nonlocal last_null_patch_results
            nonlocal last_rsa_patch_results
            child_pid = getattr(child, "pid", None)
            child_identifier = getattr(child, "identifier", None)
            child_path = getattr(child, "path", None)
            write_event(
                {
                    "action": "child-added",
                    "processId": child_pid,
                    "identifier": child_identifier,
                    "path": child_path,
                    "timestamp": time.time(),
                }
            )
            if child_pid is None:
                return
            if "rs2client.exe" not in json.dumps({"identifier": child_identifier, "path": child_path}).lower():
                device.resume(child_pid)
                return
            nonlocal_vars["child_process_id"] = child_pid
            original_command_line, _, _, _ = read_remote_process_command_line(child_pid)
            rewritten_command_line, changes = rewrite_command_line_text(original_command_line, rewrite_map)
            if changes:
                patch_result = patch_remote_process_command_line(child_pid, rewritten_command_line)
                nonlocal_vars["last_rewritten_command_line"] = patch_result["patched"]
                write_event(
                    {
                        "action": "child-command-line-rewritten",
                        "processId": child_pid,
                        "changes": changes,
                        "originalCommandLine": patch_result["original"],
                        "rewrittenCommandLine": patch_result["patched"],
                        "bufferAddress": patch_result["bufferAddress"],
                        "maximumLength": patch_result["maximumLength"],
                        "timestamp": time.time(),
                    }
                )
            else:
                write_event(
                    {
                        "action": "child-command-line-unchanged",
                        "processId": child_pid,
                        "commandLine": original_command_line,
                        "timestamp": time.time(),
                    }
                )
            if inline_patch_offsets:
                inline_patch_results = patch_remote_inline_offsets(child_pid, inline_patch_offsets)
                last_inline_patch_results = inline_patch_results
                write_event(
                    {
                        "action": "child-inline-offset-patched",
                        "processId": child_pid,
                        "results": inline_patch_results,
                        "timestamp": time.time(),
                    }
                )
            if patch_offsets:
                patch_results = patch_remote_null_read_offsets(child_pid, patch_offsets)
                last_null_patch_results = patch_results
                write_event(
                    {
                        "action": "child-null-read-offset-patched",
                        "processId": child_pid,
                        "results": patch_results,
                        "timestamp": time.time(),
                    }
                )
            if jump_bypass_specs:
                jump_patch_results = patch_remote_jump_bypass_blocks(child_pid, jump_bypass_specs)
                last_jump_patch_results = jump_patch_results
                write_event(
                    {
                        "action": "child-jump-bypass-patched",
                        "processId": child_pid,
                        "results": jump_patch_results,
                        "timestamp": time.time(),
                    }
                )
            if rsa_config_path is not None:
                executable_path = None
                if isinstance(child_path, str) and child_path:
                    executable_path = Path(child_path)
                else:
                    queried_child_path = query_process_path(child_pid)
                    if queried_child_path:
                        executable_path = Path(queried_child_path)
                if executable_path is None:
                    write_event(
                        {
                            "action": "child-rsa-patch-skipped",
                            "processId": child_pid,
                            "reason": "child-path-unavailable",
                            "timestamp": time.time(),
                        }
                    )
                else:
                    rsa_patch_results = patch_remote_embedded_rsa_moduli(child_pid, executable_path, rsa_config_path)
                    last_rsa_patch_results = rsa_patch_results
                    write_event(
                        {
                            "action": "child-rsa-moduli-patched",
                            "processId": child_pid,
                            "results": rsa_patch_results,
                            "timestamp": time.time(),
                        }
                    )
            if child_hook_handle is not None or resolve_redirects:
                try:
                    child_session = device.attach(child_pid)
                    child_script = child_session.create_script(
                        build_child_live_hook_script(
                            args.child_hook_verbose,
                            resolve_redirects=resolve_redirects,
                            connect_redirects=connect_redirects,
                        )
                    )
                    child_script.on("message", make_child_hook_message_handler(child_pid))
                    child_script.load()
                    child_trace_sessions.append(child_session)
                    child_trace_scripts.append(child_script)
                    write_event(
                        {
                            "action": "child-hook-pre-resume-attached",
                            "processId": child_pid,
                            "verbose": bool(args.child_hook_verbose),
                            "resolveRedirects": resolve_redirects,
                            "connectRedirects": connect_redirects,
                            "timestamp": time.time(),
                        }
                    )
                    write_child_event(
                        {
                            "timestamp": round(time.time(), 6),
                            "category": "client.lifecycle",
                            "action": "pre-resume-attached",
                            "pid": child_pid,
                            "verbose": bool(args.child_hook_verbose),
                            "resolveRedirects": resolve_redirects,
                            "connectRedirects": connect_redirects,
                        }
                    )

                    def on_child_detached(reason: str, crash: Any, traced_pid: int = child_pid) -> None:
                        event = {
                            "timestamp": round(time.time(), 6),
                            "category": "client.lifecycle",
                            "action": "detached",
                            "pid": traced_pid,
                            "reason": reason,
                        }
                        if crash is not None:
                            event["crash"] = crash
                        write_child_event(event)

                    child_session.on("detached", on_child_detached)
                except Exception as error:
                    write_event(
                        {
                            "action": "child-hook-attach-failed",
                            "processId": child_pid,
                            "error": str(error),
                            "resolveRedirects": resolve_redirects,
                            "connectRedirects": connect_redirects,
                            "timestamp": time.time(),
                        }
                    )
            device.resume(child_pid)
            child_created.set()

        device.on("child-added", on_child_added)

        def on_detached(reason: str, crash: Any) -> None:
            write_event({"action": "wrapper-detached", "reason": reason, "crash": crash, "timestamp": time.time()})
            detached.set()

        session.on("detached", on_detached)
        try:
            device.resume(wrapper_pid)
            write_event({"action": "wrapper-resumed", "processId": wrapper_pid, "timestamp": time.time()})

            deadline = time.time() + max(1, args.spawn_timeout_seconds)
            while time.time() < deadline and not child_created.is_set() and not detached.is_set():
                time.sleep(0.1)

            child_process_id = nonlocal_vars["child_process_id"]
            if not child_created.is_set() or child_process_id is None:
                cleanup_spawned_processes(wrapper_pid, child_process_id, "child-spawn-missing", write_event)
                raise RuntimeError("Wrapper launch completed without spawning a live rs2client.exe child.")

            rewrite_deadline = time.time() + 5.0
            while time.time() < rewrite_deadline and nonlocal_vars["last_rewritten_command_line"] is None and not detached.is_set():
                time.sleep(0.1)
            last_rewritten_command_line = nonlocal_vars["last_rewritten_command_line"]
            time.sleep(0.75)

            child_command_line = query_process_command_line(child_process_id)
            child_path = query_process_path(child_process_id)
            override_requested = child_exe_override is not None
            override_mechanism = nonlocal_vars["override_mechanism"]
            override_applied = override_mechanism is not None
            override_verified = paths_equal(
                str(child_exe_override) if child_exe_override is not None else None,
                child_path,
            )
            if override_requested and not override_verified:
                write_event(
                    {
                        "action": "child-exe-override-mismatch",
                        "requestedChildExe": str(child_exe_override),
                        "actualChildExe": child_path,
                        "overrideMechanism": override_mechanism,
                        "processId": child_process_id,
                        "timestamp": time.time(),
                    }
                )
                cleanup_spawned_processes(
                    wrapper_pid,
                    child_process_id,
                    "requested child executable override was not applied",
                    write_event,
                )
                raise RuntimeError(
                    "Requested child executable override was not applied."
                )
            wrapper_cleanup_result = cleanup_wrapper_after_child_ready(wrapper_pid, child_process_id, write_event)

            summary = {
                "wrapperPid": wrapper_pid,
                "wrapperArgv": wrapper_argv,
                "childExeOverride": str(child_exe_override) if child_exe_override is not None else None,
                "overrideRequested": override_requested,
                "overrideApplied": override_applied,
                "overrideVerified": override_verified,
                "overrideMechanism": override_mechanism,
                "childPid": child_process_id,
                "childPath": child_path,
                "childCommandLine": child_command_line,
                "rewrittenCommandLine": last_rewritten_command_line,
                "rewriteMap": rewrite_map,
                "inlinePatchOffsets": [f"0x{offset:x}" for offset in inline_patch_offsets],
                "inlinePatchResults": last_inline_patch_results,
                "nullReadPatchOffsets": [f"0x{offset:x}" for offset in patch_offsets],
                "nullReadPatchResults": last_null_patch_results,
                "jumpBypassSpecs": [
                    {"sourceOffset": f"0x{source:x}", "targetOffset": f"0x{target:x}"}
                    for source, target in jump_bypass_specs
                ],
                "jumpBypassResults": last_jump_patch_results,
                "resolveRedirects": resolve_redirects,
                "connectRedirects": connect_redirects,
                "rsaConfigPath": str(rsa_config_path) if rsa_config_path is not None else None,
                "rsaPatchResults": last_rsa_patch_results,
                "traceOutput": str(trace_output),
                "childHookOutput": str(child_hook_output) if child_hook_output is not None else None,
                "childHookVerbose": bool(args.child_hook_verbose),
                "childHookDurationSeconds": max(0, int(args.child_hook_duration_seconds)),
                "wrapperCleanupResult": wrapper_cleanup_result,
                "spawnTimedOut": not child_created.is_set(),
                "rewriteScope": args.rewrite_scope,
            }
            write_event({"action": "summary", "summary": summary, "timestamp": time.time()})

            if summary_output is not None:
                summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

            if child_hook_handle is not None and args.child_hook_duration_seconds > 0 and child_process_id:
                hook_deadline = time.time() + max(0, args.child_hook_duration_seconds)
                while time.time() < hook_deadline:
                    if query_process_path(child_process_id) is None:
                        break
                    time.sleep(0.25)
        except Exception as error:
            cleanup_spawned_processes(wrapper_pid, nonlocal_vars["child_process_id"], str(error), write_event)
            raise
        finally:
            try:
                session.detach()
            except frida.InvalidOperationError:
                pass
            if wrapper_script is not None:
                try:
                    wrapper_script.unload()
                except frida.InvalidOperationError:
                    pass

            for child_script in child_trace_scripts:
                try:
                    child_script.unload()
                except frida.InvalidOperationError:
                    pass
            for child_session in child_trace_sessions:
                try:
                    child_session.detach()
                except frida.InvalidOperationError:
                    pass
            if child_hook_handle is not None:
                child_hook_handle.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
