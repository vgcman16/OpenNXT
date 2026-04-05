from __future__ import annotations

import argparse
import ctypes
import json
import os
import time
from pathlib import Path
from typing import Any


ERROR_MORE_DATA = 234
RM_SESSION_KEY_LEN = 32
CCH_RM_MAX_APP_NAME = 255
CCH_RM_MAX_SVC_NAME = 63
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_uint32),
        ("dwHighDateTime", ctypes.c_uint32),
    ]


class RM_UNIQUE_PROCESS(ctypes.Structure):
    _fields_ = [
        ("dwProcessId", ctypes.c_uint32),
        ("ProcessStartTime", FILETIME),
    ]


class RM_PROCESS_INFO(ctypes.Structure):
    _fields_ = [
        ("Process", RM_UNIQUE_PROCESS),
        ("strAppName", ctypes.c_wchar * (CCH_RM_MAX_APP_NAME + 1)),
        ("strServiceShortName", ctypes.c_wchar * (CCH_RM_MAX_SVC_NAME + 1)),
        ("ApplicationType", ctypes.c_uint32),
        ("AppStatus", ctypes.c_uint32),
        ("TSSessionId", ctypes.c_uint32),
        ("bRestartable", ctypes.c_bool),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
rstrtmgr = ctypes.WinDLL("rstrtmgr", use_last_error=True)

RmStartSession = rstrtmgr.RmStartSession
RmStartSession.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32, ctypes.c_wchar_p]
RmStartSession.restype = ctypes.c_uint32

RmRegisterResources = rstrtmgr.RmRegisterResources
RmRegisterResources.argtypes = [
    ctypes.c_uint32,
    ctypes.c_uint32,
    ctypes.POINTER(ctypes.c_wchar_p),
    ctypes.c_uint32,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.c_void_p,
]
RmRegisterResources.restype = ctypes.c_uint32

RmGetList = rstrtmgr.RmGetList
RmGetList.argtypes = [
    ctypes.c_uint32,
    ctypes.POINTER(ctypes.c_uint32),
    ctypes.POINTER(ctypes.c_uint32),
    ctypes.POINTER(RM_PROCESS_INFO),
    ctypes.POINTER(ctypes.c_uint32),
]
RmGetList.restype = ctypes.c_uint32

RmEndSession = rstrtmgr.RmEndSession
RmEndSession.argtypes = [ctypes.c_uint32]
RmEndSession.restype = ctypes.c_uint32

OpenProcess = kernel32.OpenProcess
OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
OpenProcess.restype = ctypes.c_void_p

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [ctypes.c_void_p]
CloseHandle.restype = ctypes.c_bool

QueryFullProcessImageNameW = kernel32.QueryFullProcessImageNameW
QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
QueryFullProcessImageNameW.restype = ctypes.c_bool


def query_process_image_path(pid: int) -> str | None:
    handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        capacity = ctypes.c_uint32(32768)
        buffer = ctypes.create_unicode_buffer(capacity.value)
        if not QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(capacity)):
            return None
        return buffer.value
    finally:
        CloseHandle(handle)


def get_file_holders(path: str) -> list[dict[str, Any]]:
    session_handle = ctypes.c_uint32()
    session_key = ctypes.create_unicode_buffer(RM_SESSION_KEY_LEN + 1)
    result = RmStartSession(ctypes.byref(session_handle), 0, session_key)
    if result != 0:
        raise RuntimeError(f"RmStartSession failed: {result}")
    try:
        resources = (ctypes.c_wchar_p * 1)(path)
        result = RmRegisterResources(session_handle.value, 1, resources, 0, None, 0, None)
        if result != 0:
            raise RuntimeError(f"RmRegisterResources failed: {result}")

        needed = ctypes.c_uint32(0)
        count = ctypes.c_uint32(0)
        reasons = ctypes.c_uint32(0)
        result = RmGetList(session_handle.value, ctypes.byref(needed), ctypes.byref(count), None, ctypes.byref(reasons))
        if result not in (0, ERROR_MORE_DATA):
            raise RuntimeError(f"RmGetList probe failed: {result}")
        if needed.value == 0:
            return []

        entries = (RM_PROCESS_INFO * needed.value)()
        count = ctypes.c_uint32(needed.value)
        result = RmGetList(session_handle.value, ctypes.byref(needed), ctypes.byref(count), entries, ctypes.byref(reasons))
        if result != 0:
            raise RuntimeError(f"RmGetList failed: {result}")

        holders: list[dict[str, Any]] = []
        for entry in entries[: count.value]:
            pid = int(entry.Process.dwProcessId)
            holders.append(
                {
                    "pid": pid,
                    "appName": entry.strAppName,
                    "serviceShortName": entry.strServiceShortName,
                    "applicationType": int(entry.ApplicationType),
                    "appStatus": int(entry.AppStatus),
                    "restartable": bool(entry.bRestartable),
                    "imagePath": query_process_image_path(pid),
                }
            )
        return holders
    finally:
        RmEndSession(session_handle.value)


def serialize_holders(holders: list[dict[str, Any]]) -> str:
    normalized = []
    for holder in holders:
        normalized.append(
            {
                "pid": int(holder.get("pid", 0)),
                "appName": holder.get("appName"),
                "serviceShortName": holder.get("serviceShortName"),
                "applicationType": int(holder.get("applicationType", 0)),
                "appStatus": int(holder.get("appStatus", 0)),
                "restartable": bool(holder.get("restartable", False)),
                "imagePath": holder.get("imagePath"),
            }
        )
    return json.dumps(sorted(normalized, key=lambda item: (item["pid"], item.get("imagePath") or "")), sort_keys=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trace which processes hold a target runtime file during wrapper startup."
    )
    parser.add_argument("--path", required=True, help="File path to trace.")
    parser.add_argument("--duration-seconds", type=float, default=20.0)
    parser.add_argument("--interval-seconds", type=float, default=0.2)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--emit-empty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target_path = str(Path(args.path).resolve(strict=False))
    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    previous_signature: str | None = None
    deadline = time.time() + max(0.1, args.duration_seconds)

    with output_path.open("w", encoding="utf-8") as handle:
        while time.time() < deadline:
            timestamp = round(time.time(), 6)
            try:
                holders = get_file_holders(target_path)
                signature = serialize_holders(holders)
                if args.emit_empty or signature != previous_signature:
                    handle.write(
                        json.dumps(
                            {
                                "timestamp": timestamp,
                                "path": target_path,
                                "holders": holders,
                            },
                            sort_keys=True,
                        )
                        + "\n"
                    )
                    handle.flush()
                    previous_signature = signature
            except Exception as error:
                handle.write(
                    json.dumps(
                        {
                            "timestamp": timestamp,
                            "path": target_path,
                            "error": str(error),
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
                handle.flush()
                previous_signature = None
            time.sleep(max(0.05, args.interval_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
