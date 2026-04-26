from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import tomllib
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any, Callable

try:
    import frida
    FRIDA_IMPORT_ERROR = None
except Exception as frida_import_error:  # pragma: no cover - exercised on locked-down Windows hosts
    frida = None
    FRIDA_IMPORT_ERROR = frida_import_error
from ctypes import wintypes

try:
    from tools.trace_rs2client_live import build_hook_script as build_child_live_hook_script
    from tools.trace_rs2client_live import normalize_payload as normalize_child_live_payload
    CHILD_LIVE_TRACE_IMPORT_ERROR = None
except Exception:
    try:
        from trace_rs2client_live import build_hook_script as build_child_live_hook_script
        from trace_rs2client_live import normalize_payload as normalize_child_live_payload
        CHILD_LIVE_TRACE_IMPORT_ERROR = None
    except Exception as child_live_trace_import_error:  # pragma: no cover - exercised on locked-down Windows hosts
        build_child_live_hook_script = None
        normalize_child_live_payload = None
        CHILD_LIVE_TRACE_IMPORT_ERROR = child_live_trace_import_error


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_BASIC_INFORMATION_CLASS = 0
PEB_PROCESS_PARAMETERS_OFFSET_X64 = 0x20
RTL_USER_PROCESS_PARAMETERS_COMMAND_LINE_OFFSET_X64 = 0x70
PAGE_EXECUTE_READWRITE = 0x40
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
ERROR_PARTIAL_COPY = 299
PROCESS_IMAGE_LAYOUT_RETRY_ATTEMPTS = 20
PROCESS_IMAGE_LAYOUT_RETRY_DELAY_SECONDS = 0.05
DEFAULT_NULL_READ_BLOCK = bytes.fromhex("44 8B 04 25 00 00 00 00 48 8B CE")
DISABLED_JUMP_BYPASS_SPECS = {
    # This bypass jumps directly to 0x5910eb and skips the
    # `r15 = r14 + index * 0x108` setup in FUN_140590bc0, which leaves r15 as
    # a tiny scalar and reproduces the pre-login AV at +0x7734 on current 947
    # WIN64 builds.
    (0x590F92, 0x5910EB),
    # This compare-block skip forces FUN_140590220 straight onto the fallback
    # `call 0x590bc0` lane and bypasses the live selector/compare state at
    # 0x3218/0x321c/0x3298 and 0x7730/0x77e0. On current contained 947 startup
    # it correlates with later bogus control flow and execute AVs once the
    # client starts touching the js5-26 cache lane.
    (0x59034D, 0x5903C6),
    # This family forces the later cache/index path to keep sentinel values
    # instead of consuming direct or indexed values from `rsi`, which traps the
    # 947 client on the loading bar in a repeated JS5 255/* reference-table
    # loop on current WIN64C builds.
    (0x594A88, 0x594AA1),
    (0x594A91, 0x594AA1),
    (0x594AA6, 0x594ABA),
    (0x594AAF, 0x594ABA),
    # These stale offsets were carried forward as if they were a second copy of
    # the 0x594a88/0x594aa6 bounds checks. In the current 947 WIN64C image they
    # land inside a different gs:[0x58] loop, so treating them as loading-gate
    # compare blocks targets the wrong basic block entirely.
    (0x594DA8, 0x594DC1),
    (0x594DC6, 0x594DDA),
    # These late-state bypasses skip a real callback/flag-clear path on the
    # `[rdi + 0x1b0]` object and leave the current 947 WIN64C client parked on
    # the loading screen after JS5 reference-table validation.
    (0x72AD28, 0x72AD46),
    (0x72B3A8, 0x72B3C6),
    # The broad compare-failure bypass at 0x59c64f keeps the builder on a fake
    # success path after the 64/65-byte validation fails. Prefer the narrower
    # 0x59c2a0 compare-mirroring guard and drop this stale jump entirely.
    (0x59C64F, 0x59C2BE),
}
DISABLED_INLINE_PATCH_OFFSETS = {
    # Replacing the direct CALL at 0x58ff0f with `mov al, 1` skips
    # FUN_140590bc0 entirely and distorts the real pre-login control flow on
    # current 947 WIN64C builds. Keep this offset filtered out even if a stale
    # launcher still passes it.
    0x58FF0F,
    # This patch forces the `je 0x594a82` fallback path and pairs with the
    # disabled 0x594a* jump-bypass family above, which keeps the client in the
    # checksum/reference-table phase instead of progressing toward login.
    0x594A41,
}
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
    0x590CF4: {
        "expected": bytes.fromhex("0F 84 D1 00 00 00"),
        # When the first two metadata values happen to match, the client skips
        # the 0x590d5e refresh and can publish a structurally stale +0xbc28
        # slot straight to 0x594a10. NOP the `je 0x590dcb` so the refresh path
        # still runs during controlled smoke tests.
        "replacement": bytes.fromhex("90 90 90 90 90 90"),
    },
    0x594A41: {
        "expected": bytes.fromhex("80 7E 24 00"),
        "replacement": bytes.fromhex("31 C0 90 90"),
    },
    0x594D61: {
        "expected": bytes.fromhex("80 7E 24 00"),
        "replacement": bytes.fromhex("31 C0 90 90"),
    },
    0x5966FB: {
        # Extend the post-select accepted-status bitmask from 0x05420800 to
        # 0x05620800 so status code 21 can follow the same success path as the
        # nearby accepted values instead of falling back onto the splash loop.
        "expected": bytes.fromhex("41 BE 00 08 42 05"),
        "replacement": bytes.fromhex("41 BE 00 08 62 05"),
    },
    0x596649: {
        # Mode-0 queued items currently fall straight into the 0x598370
        # fallback lane. Redirect that short branch to the recordState entry at
        # 0x596676 so we can test whether the real publication path is simply
        # being skipped for the hot queued record.
        "expected": bytes.fromhex("74 3A"),
        "replacement": bytes.fromhex("74 2B"),
    },
    0x59687F: {
        # The accepted-slot fast path currently marks slotBase+0x28, which maps
        # to recordBase+0x20 in the traced structure. Redirect it to
        # slotBase+0x29 so the earlier queue scan sees the publication byte.
        "expected": bytes.fromhex("C6 43 28 01"),
        "replacement": bytes.fromhex("C6 43 29 01"),
    },
    0x5955A2: {
        # When recordBase+0x20 stays clear, resource-dispatch never calls the
        # publication helper at 0x595370. NOP the short `je` so the helper
        # still runs on the hot record during smoke tests.
        "expected": bytes.fromhex("74 0B"),
        "replacement": bytes.fromhex("90 90"),
    },
    0x5953E4: {
        # The helper at 0x595370 immediately bails again on the same
        # recordBase+0x20 gate. NOP the inner `je` so it can continue into the
        # queue/publication body once the outer dispatcher forces the call.
        "expected": bytes.fromhex("0F 84 B2 00 00 00"),
        "replacement": bytes.fromhex("90 90 90 90 90 90"),
    },
    0x5967E5: {
        # Once the owner scan has latched queueFlag11468[index], the later
        # idle-selector revisit can bail out on the same stale latch before it
        # ever re-enters the 0x5967eb..0x5968d1 post-select lane. NOP that
        # reject so the hot record can continue through the normal follow-on
        # path instead of looping forever at queued=1 / ptr1c8=0.
        "expected": bytes.fromhex("0F 85 4D FD FF FF"),
        "replacement": bytes.fromhex("90 90 90 90 90 90"),
    },
    0x597DB1: {
        # Accepted-mask statuses currently mark recordBase+0x20, but the
        # downstream type-3 publisher gates on recordBase+0x21. Redirect this
        # canonical accepted-path write onto the publish byte for smoke tests.
        "expected": bytes.fromhex("C6 45 20 01"),
        "replacement": bytes.fromhex("C6 45 21 01"),
    },
}
SPECIAL_GUARDED_JUMP_BYPASS_SPECS = {
    # Keep the original serialization/materialization block when `rbx` holds a
    # real entry pointer, but skip to the caller's fallback when the client
    # reaches 0x59002d with a null/sentinel `rbx`. The old broad bypass jumped
    # over the whole block and strands 947 on the loading screen.
    (0x59002D, 0x5900A5): {
        "expected": bytes.fromhex("48 8B 53 10 48 8D 4C 24 40 4C 89 64 24 48"),
        "resumeOffset": 0x59003B,
        "builder": "guard-59002d",
    },
    # FUN_140590220 can early-return on a stale state==1 marker before it ever
    # re-runs the normal 0x7710/0x7734/0x77d8 readiness checks or calls
    # FUN_140590bc0. Keep the state==1 fast path only when the normal-path data
    # buffers are actually populated; otherwise fall through to the original
    # readiness path at 0x5902e2.
    (0x5902D5, 0x5903BD): {
        "expected": bytes.fromhex("41 80 FA 01 0F 84 DE 00 00 00 49 8B 00"),
        "resumeOffset": 0x5902E2,
        "builder": "guard-5902d5",
    },
    # Some 947 runs now advance into the param_3 == -1 master-table lookup
    # immediately after `/ms`, but the lookup base is still unstable there.
    # Reuse the proven `-1` sentinel continuation at 0x590c81 instead of
    # attempting to dereference the pre-login master table at all.
    (0x590C58, 0x590C81): {
        "expected": bytes.fromhex("48 8B 91 D0 30 00 00 4C 3B 52 10 73 0D"),
        "resumeOffset": 0x590C65,
        "builder": "guard-590c58",
    },
    # After FUN_140592760 publishes or skips a master-table update, the client
    # immediately re-enters FUN_14058fa60 and dereferences owner+0x30d0.
    # When there is still no live table, skip the enrichment loop instead of
    # null-faulting on [rax].
    (0x58FA83, 0x58FB29): {
        "expected": bytes.fromhex("48 8B 81 D0 30 00 00 41 8B D5 44 8B 20"),
        "resumeOffset": 0x58FA90,
        "builder": "guard-58fa83",
    },
    # The 947 master-table builder bails out unless its local blob-length state
    # lands on 0x41. Mirror the proven Frida smoke-test here by forcing both
    # the live register and stack-local length slot to 0x41 before resuming at
    # the length-gate success continuation.
    (0x59C1EA, 0x59C21B): {
        "expected": bytes.fromhex("49 83 FE 41 74 2B 48 85 DB 74 0D 4D 85 F6 74 08"),
        "resumeOffset": 0x59C21B,
        "builder": "force-length-59c1ea",
    },
    # Copy the 64-byte left compare buffer into the right-side payload area on
    # the first validation iteration, then let the client's own compare/fail
    # logic keep running. This preserves the real cleanup path at 0x59c64f.
    (0x59C2A0, 0x59C64F): {
        "expected": bytes.fromhex("41 0F B6 44 08 01 38 01 0F 85 A1 03 00 00"),
        "resumeOffset": 0x59C2AE,
        "builder": "mirror-compare-59c2a0",
    },
    # This site null-faults while trying to load primary/secondary sentinels for
    # the param_3 == -1 / out-of-range case. Preserve the normal 0xbc28 path by
    # injecting the `-1` sentinels directly and resuming at 0x590c81.
    (0x590C72, 0x590DBA): {
        "expected": bytes.fromhex("44 8B 04 25 00 00 00 00 48 8B CE 44 8B 49 04"),
        "resumeOffset": 0x590C81,
        "builder": "sentinel-590c72",
    },
    # The master-table swap path publishes any non-null FUN_14059bd00 result,
    # even when the builder leaves it structurally empty. Only install tables
    # that match the healthy invariant; otherwise keep the previous table live
    # and release the bad candidate.
    (0x5927F2, 0x592826): {
        "expected": bytes.fromhex("48 8B 38 4C 89 38 48 85 FF 74 29 48 8D 4F 08"),
        "resumeOffset": 0x592801,
        "builder": "guarded-publish-5927f2",
    },
    # Current contained 947 runs can still stall in the logged-out 255/*
    # reference-table loop even after the master table exists. Force the first
    # per-entry value compare down its normal success continuation while
    # preserving the original `dl`-based branch that chooses between the inline
    # value and the indexed array lookup.
    (0x590CCB, 0x590CF1): {
        "expected": bytes.fromhex("41 3B C0 75 2A 84 D2 74 05 8B 47 20 EB 18"),
        "resumeOffset": 0x590CD9,
        "builder": "force-compare-590ccb",
    },
    # If the second per-entry compare still misses, the client falls back into
    # the request-scheduling path at 0x590cfa and keeps reloading the same
    # logged-out reference tables. Mirror the success jump to 0x590dcb.
    (0x590CF1, 0x590DCB): {
        "expected": bytes.fromhex("41 3B C1 0F 84 D1 00 00 00 0F 57 C0"),
        "resumeOffset": 0x590DCB,
        "builder": "force-compare-590cf1",
    },
    # Some contained 947 runs now reach the builder post-gate with a real
    # record base but an empty record-side vector pair. Two pre-login cases
    # can still legitimately advance here:
    # 1. both the record and the companion path-base are structurally empty, so
    #    the normal -1/-1 compare path should still run; or
    # 2. the path-base already carries a valid direct primary/secondary pair,
    #    but the record-side 0x7710/0x7730/0x7734 slot was never promoted.
    # Preserve the original failure branch to 0x590ec6 for everything else.
    (0x590DE8, 0x590EC6): {
        "expected": bytes.fromhex("450fb68f347700004d8d87107700004584c9750d4939b7d87700000f84bd000000"),
        "resumeOffset": 0x590E09,
        "builder": "guard-590de8",
    },
    # Once the post-gate compare path stays alive long enough to request the
    # logged-out 255/* reference-table burst, some 947 runs still reach the
    # archive-state slot lookup with an empty or sentinel slot pointer. Treat
    # that as an "unknown state" byte instead of AV'ing on the slot deref so
    # the normal scheduler can keep driving startup work forward.
    (0x590EC9, 0x590EDA): {
        "expected": bytes.fromhex("48c1e0054a8b8418100c01000fb6541801"),
        "resumeOffset": 0x590EDA,
        "builder": "guard-590ec9",
    },
    # After contained `/ms` succeeds, some login-path packets still funnel a
    # sentinel object into FUN_1402ab680 while the backing manager is not
    # ready. That leaves param_2+0x8 null, and the helper AVs at 0x2ab6ad on
    # [rsi+0x40]. Keep the real path when param_2+0x8 is live; otherwise return
    # through the normal epilogue and skip only the stale sentinel update.
    (0x2AB698, 0x2AB7F7): {
        "expected": bytes.fromhex("48 8B 72 08 4C 8B FA 4C 8B F1 49 8D 53 A8 48 83 C1 20 41 8B F8"),
        "resumeOffset": 0x2AB6AD,
        "builder": "guard-2ab698",
    },
    # Once contained lobby login completes, some runs now open the follow-on
    # world socket and immediately enter FUN_140369980 with a poisoned
    # `*param_1` base. Guard the `[r10+0x18]` metadata walk and fall back to a
    # conservative zero result instead of AV'ing before the first world byte.
    (0x3699B2, 0x3699F2): {
        "expected": bytes.fromhex("4C 8B 11 44 89 41 0C 49 8B 5A 18 33 C9 8B C1"),
        "resumeOffset": 0x3699C1,
        "builder": "guard-3699b2",
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
    # Current 947 builds moved the second readiness/compare fast-path inside
    # FUN_140590220. Jumping over it should now continue at 0x5903c6, which is
    # the block that falls back into FUN_140590bc0 instead of returning
    # success mid-compare.
    0x59034D: bytes.fromhex(
        "31 00 00 EB 18 48 3B 8A 90 32 00 00 73 0C 48 8B 82 98 32 00 00 8B 04 88 EB 03 41 8B C0 "
        "44 3B D0 75 57 45 84 C9 74 09 44 8B 8A 30 77 00 00 EB 19 48 3B 8A D8 77 00 00 73 0D 48 8B "
        "82 E0 77 00 00 44 8B 0C 88 EB 03 45 8B C8 45 84 DB 74 09 44 8B 82 18 32 00 00 EB 14 48 3B "
        "8A C0 32 00 00 73 0B 48 8B 82 C8 32 00 00 44 8B 04 88 45 3B C8 75 09 48 8D 05 5C 10 6B 00 EB 3B"
    ),
    0x590C72: DEFAULT_NULL_READ_BLOCK,
    0x590F92: DEFAULT_NULL_READ_BLOCK,
    0x594A91: bytes.fromhex("48 8B 86 A0 00 00 00"),
    0x594AAF: bytes.fromhex("48 8B 86 D0 00 00 00"),
    0x594A88: bytes.fromhex("48 3B AE 98 00 00 00 73 10"),
    0x594AA6: bytes.fromhex("48 3B AE C8 00 00 00 73 0B"),
    # Once the 0x59c1ea length gate is forced, some 947 runs still fail the
    # subsequent 64/65-byte validation compare and fall back into an endless
    # 255/* reference-table reload loop. This matches the validated Frida
    # smoke-test that resumes at the compare-success continuation.
    0x59C64F: bytes.fromhex("4D 85 FF 74 08 49 8B CF E8 A4 A6 20 00"),
    # The type-3 helper at 0x597070 immediately returns success when
    # recordBase+0x21 is still zero, which prevents the real queue publication
    # body at 0x597087 from ever running. Skip the short epilogue block and
    # force execution into the live publication path for smoke testing.
    0x59707D: bytes.fromhex("75 08 B0 01 48 83 C4 70 5B C3"),
    # After the contained login handshake lands, some runs advance into
    # FUN_1407a3ad0 with stale vector-slot bookkeeping in r14+0x78/0x80. The
    # direct slot write path then AVs on a null/stale destination pointer.
    # Force the function's own slow-path allocator/helper branch at 0x7a3bff.
    0x7A3BC2: bytes.fromhex("49 8B 7E 78 49 3B BE 80 00 00 00 73 30"),
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
kernel32.VirtualAllocEx.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    ctypes.c_size_t,
    wintypes.DWORD,
    wintypes.DWORD,
]
kernel32.VirtualAllocEx.restype = wintypes.LPVOID
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
        "--rewrite-config-file",
        help=(
            "Optional explicit jav_config.ws snapshot to use for child command-line rewrites. "
            "When provided, the wrapper still receives --config-uri unchanged, but the rewrite map "
            "and auto redirects are derived from this file instead of refetching config-uri."
        ),
    )
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
        "--js5-rsa-source-exe",
        help=(
            "Optional rs2client.exe path whose embedded 4096-bit JS5 modulus should be restored "
            "into the spawned child instead of using the local rsa.toml JS5 modulus."
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
        "--force-secure-retail-startup-redirects",
        action="store_true",
        help=(
            "Opt back into localhost resolve redirects for the default 947 secure-retail startup contract. "
            "By default, 947 startup keeps retail world/content/lobby hosts untouched until login."
        ),
    )
    parser.add_argument(
        "--child-exe-override",
        help=(
            "Optional local rs2client.exe path to force into the wrapper's child CreateProcess call. "
            "Useful when the visible RuneScape.exe wrapper would otherwise spawn the stale ProgramData child."
        ),
    )
    parser.add_argument(
        "--accepted-child-exe",
        action="append",
        default=[],
        help=(
            "Optional repeatable child rs2client.exe path that should be accepted even when "
            "--child-exe-override does not win the final executable path."
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


def load_rewrite_jav_config(
    config_uri: str,
    rewrite_config_file: str | None = None,
    fetcher: Callable[[str], str] | None = None,
) -> tuple[str, dict[str, str | None]]:
    if rewrite_config_file:
        rewrite_path = Path(rewrite_config_file).expanduser()
        text = rewrite_path.read_text(encoding="utf-8", errors="replace")
        return (
            text,
            {
                "source": "file",
                "path": str(rewrite_path),
                "fetchUri": None,
            },
        )

    fetch_uri = resolve_fetch_config_uri(config_uri)
    effective_fetcher = fetcher or (lambda uri: fetch_jav_config(uri))
    return (
        effective_fetcher(fetch_uri),
        {
            "source": "fetch",
            "path": None,
            "fetchUri": fetch_uri,
        },
    )


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


def should_auto_redirect_route_hosts(
    config_uri: str,
    force_secure_retail_startup_redirects: bool = False,
) -> bool:
    if is_secure_retail_startup_contract(config_uri):
        return force_secure_retail_startup_redirects
    parsed = urllib.parse.urlsplit(config_uri)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    for flag_name in LOCAL_REWRITE_QUERY_FLAGS:
        value = str(query.get(flag_name) or "").strip().lower()
        if value in TRUE_QUERY_VALUES:
            return True
    return False


def is_secure_retail_startup_contract(config_uri: str) -> bool:
    parsed = urllib.parse.urlsplit(config_uri)
    hostname = (parsed.hostname or "").lower()
    return hostname == "rs.config.runescape.com" and not requests_local_rewrite_contract(config_uri)


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


def extract_codebase_value(jav_config_text: str) -> str | None:
    for raw_line in jav_config_text.splitlines():
        line = raw_line.strip()
        if line.startswith("codebase="):
            return line[len("codebase=") :].strip()
    return None


def build_secure_retail_world_fleet_hosts(max_world: int = 100) -> list[str]:
    del max_world
    # Wildcard matching now happens inside the Frida resolve hook, which keeps
    # secure-retail startup containment broad without blowing up launcher argv size.
    return [
        "content*.runescape.com",
        "world*.runescape.com",
        "lobby*.runescape.com",
    ]


def build_route_resolve_redirects(
    param_map: dict[str, str],
    redirect_target: str = "localhost",
    jav_config_text: str | None = None,
    include_secure_retail_world_fleet: bool = False,
    include_content_hosts: bool = True,
) -> dict[str, str]:
    redirects: dict[str, str] = {}

    def add_host(raw_host: str | None) -> None:
        host = str(raw_host or "").strip().lower()
        if not host or host in {"localhost", "127.0.0.1", "::1", "rs.config.runescape.com"}:
            return
        redirects[host] = redirect_target

    def add_candidate_value(raw_value: str | None) -> None:
        candidate = str(raw_value or "").strip()
        if not candidate:
            return
        try:
            parsed = urllib.parse.urlsplit(candidate)
        except ValueError:
            parsed = urllib.parse.SplitResult("", "", "", "", "")
        add_host(parsed.hostname or candidate)

    add_host(param_map.get("3"))
    if include_content_hosts:
        add_host(param_map.get("37"))
        add_host(param_map.get("49"))

    for key in ("35", "40"):
        add_candidate_value(param_map.get(key))
    if jav_config_text:
        add_candidate_value(extract_codebase_value(jav_config_text))
    if include_secure_retail_world_fleet:
        for host in build_secure_retail_world_fleet_hosts():
            add_host(host)

    return redirects


def build_connect_redirects(
    resolve_redirects: dict[str, str],
    resolver: Callable[..., Any] | None = None,
) -> dict[str, str]:
    ip_redirects: dict[str, str] = {}
    lookup = resolver or socket.getaddrinfo
    for source_host, redirect_target in resolve_redirects.items():
        if "*" in str(source_host):
            continue
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


def build_wrapper_spawn_script(
    child_exe_override: str | None,
    traced_child_targets: list[str] | tuple[str, ...] | None = None,
) -> str:
    child_path = str(child_exe_override or "").strip()
    child_dir = str(Path(child_path).parent) if child_path else ""
    traced_targets = [
        str(Path(value).resolve(strict=False)).replace("/", "\\").lower()
        for value in (traced_child_targets or [])
        if str(value or "").strip()
    ]
    return f"""
const childExeOverride = {json.dumps(child_path)};
const childDirOverride = {json.dumps(child_dir)};
const tracedChildTargets = {json.dumps(traced_targets)};
const overrideState = {{ consumed: false }};

function normalizePathValue(value) {{
  return (value || "").replace(/\\//g, "\\\\").toLowerCase();
}}

function pathMentionsTrackedTarget(value) {{
  const normalized = normalizePathValue(value);
  if (!normalized) {{
    return false;
  }}
  for (const target of tracedChildTargets) {{
    if (normalized.indexOf(target) !== -1) {{
      return true;
    }}
  }}
  return false;
}}

function sendObservedProcessEvent(action, api, applicationName, commandLine, currentDirectory, matchKind) {{
  const haystack = ((applicationName || "") + "\\n" + (commandLine || "") + "\\n" + (currentDirectory || "")).toLowerCase();
  if (
    haystack.indexOf("rs2client.exe") === -1 &&
    !pathMentionsTrackedTarget(applicationName) &&
    !pathMentionsTrackedTarget(commandLine) &&
    !pathMentionsTrackedTarget(currentDirectory)
  ) {{
    return;
  }}
  send({{
    action: action,
    api: api,
    applicationName: applicationName,
    commandLine: commandLine,
    currentDirectory: currentDirectory,
    matchKind: matchKind,
    timestamp: Date.now() / 1000.0
  }});
}}

function sendTrackedFileEvent(action, payload) {{
  if (!tracedChildTargets.length) {{
    return;
  }}
  const candidateValues = [
    payload.path,
    payload.existingPath,
    payload.newPath,
    payload.replacedPath,
    payload.replacementPath,
    payload.backupPath
  ];
  let matched = false;
  for (const candidate of candidateValues) {{
    if (pathMentionsTrackedTarget(candidate)) {{
      matched = true;
      break;
    }}
  }}
  if (!matched) {{
    return;
  }}
  payload.action = action;
  payload.timestamp = Date.now() / 1000.0;
  send(payload);
}}

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
      let originalDir = null;
      try {{
        if (dirIndex >= 0) {{
          originalDir = args[dirIndex].isNull() ? null : (encoding === "ansi" ? args[dirIndex].readAnsiString() : args[dirIndex].readUtf16String());
        }}
      }} catch (_error) {{}}

      const matchKind = classifyRewriteTarget(originalApp, originalCmd);
      sendObservedProcessEvent("wrapper-child-createprocess-observed", exportName, originalApp, originalCmd, originalDir, matchKind);
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
        originalCurrentDirectory: originalDir,
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
      sendObservedProcessEvent("wrapper-child-shellexecute-observed", exportName, originalFile, originalParameters, originalDirectory, matchKind);
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
      sendObservedProcessEvent("wrapper-child-shellexecuteex-observed", exportName, originalFile, originalParameters, originalDirectory, matchKind);
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
      sendObservedProcessEvent("wrapper-child-ntcreateuserprocess-observed", "NtCreateUserProcess", originalImagePath, originalCommandLine, null, matchKind);
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

function installCreateFileHook(moduleName, exportName, pathIndex, accessIndex, shareIndex, dispositionIndex, encoding) {{
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
      let originalPath = null;
      try {{
        originalPath = args[pathIndex].isNull() ? null : (encoding === "ansi" ? args[pathIndex].readAnsiString() : args[pathIndex].readUtf16String());
      }} catch (_error) {{}}
      sendTrackedFileEvent("wrapper-file-create-observed", {{
        api: exportName,
        path: originalPath,
        desiredAccess: args[accessIndex].toUInt32(),
        shareMode: args[shareIndex].toUInt32(),
        creationDisposition: args[dispositionIndex].toUInt32()
      }});
    }}
  }});
}}

function installMoveFileHook(moduleName, exportName, existingIndex, newIndex, flagsIndex, encoding) {{
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
      let existingPath = null;
      let newPath = null;
      try {{
        existingPath = args[existingIndex].isNull() ? null : (encoding === "ansi" ? args[existingIndex].readAnsiString() : args[existingIndex].readUtf16String());
      }} catch (_error) {{}}
      try {{
        newPath = args[newIndex].isNull() ? null : (encoding === "ansi" ? args[newIndex].readAnsiString() : args[newIndex].readUtf16String());
      }} catch (_error) {{}}
      sendTrackedFileEvent("wrapper-file-move-observed", {{
        api: exportName,
        existingPath: existingPath,
        newPath: newPath,
        flags: flagsIndex >= 0 ? args[flagsIndex].toUInt32() : null
      }});
    }}
  }});
}}

function installCopyFileHook(moduleName, exportName, existingIndex, newIndex, encoding) {{
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
      let existingPath = null;
      let newPath = null;
      try {{
        existingPath = args[existingIndex].isNull() ? null : (encoding === "ansi" ? args[existingIndex].readAnsiString() : args[existingIndex].readUtf16String());
      }} catch (_error) {{}}
      try {{
        newPath = args[newIndex].isNull() ? null : (encoding === "ansi" ? args[newIndex].readAnsiString() : args[newIndex].readUtf16String());
      }} catch (_error) {{}}
      sendTrackedFileEvent("wrapper-file-copy-observed", {{
        api: exportName,
        existingPath: existingPath,
        newPath: newPath
      }});
    }}
  }});
}}

function installReplaceFileHook(moduleName, exportName, replacedIndex, replacementIndex, backupIndex, encoding) {{
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
      let replacedPath = null;
      let replacementPath = null;
      let backupPath = null;
      try {{
        replacedPath = args[replacedIndex].isNull() ? null : (encoding === "ansi" ? args[replacedIndex].readAnsiString() : args[replacedIndex].readUtf16String());
      }} catch (_error) {{}}
      try {{
        replacementPath = args[replacementIndex].isNull() ? null : (encoding === "ansi" ? args[replacementIndex].readAnsiString() : args[replacementIndex].readUtf16String());
      }} catch (_error) {{}}
      try {{
        backupPath = args[backupIndex].isNull() ? null : (encoding === "ansi" ? args[backupIndex].readAnsiString() : args[backupIndex].readUtf16String());
      }} catch (_error) {{}}
      sendTrackedFileEvent("wrapper-file-replace-observed", {{
        api: exportName,
        replacedPath: replacedPath,
        replacementPath: replacementPath,
        backupPath: backupPath
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
installCreateFileHook("kernel32.dll", "CreateFileW", 0, 1, 2, 4, "wide");
installCreateFileHook("kernelbase.dll", "CreateFileW", 0, 1, 2, 4, "wide");
installCreateFileHook("kernel32.dll", "CreateFileA", 0, 1, 2, 4, "ansi");
installCreateFileHook("kernelbase.dll", "CreateFileA", 0, 1, 2, 4, "ansi");
installMoveFileHook("kernel32.dll", "MoveFileExW", 0, 1, 2, "wide");
installMoveFileHook("kernelbase.dll", "MoveFileExW", 0, 1, 2, "wide");
installMoveFileHook("kernel32.dll", "MoveFileW", 0, 1, -1, "wide");
installMoveFileHook("kernelbase.dll", "MoveFileW", 0, 1, -1, "wide");
installCopyFileHook("kernel32.dll", "CopyFileW", 0, 1, "wide");
installCopyFileHook("kernelbase.dll", "CopyFileW", 0, 1, "wide");
installCopyFileHook("kernel32.dll", "CopyFileA", 0, 1, "ansi");
installCopyFileHook("kernelbase.dll", "CopyFileA", 0, 1, "ansi");
installCopyFileHook("kernel32.dll", "CopyFileExW", 0, 1, "wide");
installCopyFileHook("kernelbase.dll", "CopyFileExW", 0, 1, "wide");
installReplaceFileHook("kernel32.dll", "ReplaceFileW", 0, 1, 2, "wide");
installReplaceFileHook("kernelbase.dll", "ReplaceFileW", 0, 1, 2, "wide");
"""


def paths_equal(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return str(Path(left).resolve(strict=False)).lower() == str(Path(right).resolve(strict=False)).lower()


def path_matches_any(path_value: str | None, candidates: list[str] | tuple[str, ...] | None) -> bool:
    for candidate in candidates or []:
        if paths_equal(path_value, candidate):
            return True
    return False


def files_equal(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    if paths_equal(left, right):
        return True

    left_path = Path(left)
    right_path = Path(right)
    if not left_path.exists() or not right_path.exists():
        return False

    try:
        if left_path.stat().st_size != right_path.stat().st_size:
            return False
    except OSError:
        return False

    def sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    try:
        return sha256_file(left_path) == sha256_file(right_path)
    except OSError:
        return False


def refresh_accepted_child_exe(source: str | Path, destination: str | Path) -> dict[str, Any] | None:
    source_path = Path(source)
    destination_path = Path(destination)
    if files_equal(str(source_path), str(destination_path)):
        return None

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f"{destination_path.name}.opennxt-stage-",
        suffix=".tmp",
        dir=str(destination_path.parent),
    )
    os.close(temp_fd)
    staged_path = Path(temp_name)
    try:
        shutil.copy2(source_path, staged_path)
        if not files_equal(str(source_path), str(staged_path)):
            raise RuntimeError("staged-copy-content-mismatch")
        os.replace(staged_path, destination_path)
        if not files_equal(str(source_path), str(destination_path)):
            raise RuntimeError("post-replace-content-mismatch")
        return {
            "source": str(source_path),
            "destination": str(destination_path),
            "size": destination_path.stat().st_size,
        }
    finally:
        try:
            if staged_path.exists():
                staged_path.unlink()
        except OSError:
            pass


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
        offset = int(value, 0)
        if offset in DISABLED_INLINE_PATCH_OFFSETS:
            continue
        normalized.append(offset)
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
        spec = (int(parts[0], 0), int(parts[1], 0))
        if spec in DISABLED_JUMP_BYPASS_SPECS:
            continue
        normalized.append(spec)
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


def _is_retryable_process_image_error(exc: BaseException) -> bool:
    if isinstance(exc, OSError):
        return getattr(exc, "errno", None) == ERROR_PARTIAL_COPY
    if isinstance(exc, ValueError):
        text = str(exc)
        return (
            "missing DOS header" in text
            or "missing PE header" in text
            or "reported invalid size" in text
        )
    return False


def _retry_process_image_operation(operation: Callable[[], Any]) -> Any:
    last_error: BaseException | None = None
    for attempt in range(PROCESS_IMAGE_LAYOUT_RETRY_ATTEMPTS):
        try:
            return operation()
        except Exception as exc:
            if not _is_retryable_process_image_error(exc):
                raise
            last_error = exc
            if attempt == PROCESS_IMAGE_LAYOUT_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(PROCESS_IMAGE_LAYOUT_RETRY_DELAY_SECONDS)
    if last_error is not None:
        raise last_error
    raise RuntimeError("process image retry loop exited without a result")


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


def _allocate_process_memory(handle: wintypes.HANDLE, size: int) -> int:
    address = kernel32.VirtualAllocEx(
        handle,
        None,
        size,
        MEM_COMMIT | MEM_RESERVE,
        PAGE_EXECUTE_READWRITE,
    )
    if not address:
        raise OSError(ctypes.get_last_error(), f"VirtualAllocEx failed for size {size}")
    return int(ctypes.cast(address, ctypes.c_void_p).value)


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


def _read_remote_process_image_base_once(pid: int) -> int:
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


def read_remote_process_image_base(pid: int) -> int:
    return int(_retry_process_image_operation(lambda: _read_remote_process_image_base_once(pid)))


def _read_remote_process_image_layout_once(pid: int) -> tuple[int, int]:
    handle = _open_process(pid)
    try:
        image_base = _read_remote_process_image_base_once(pid)
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


def read_remote_process_image_layout(pid: int) -> tuple[int, int]:
    image_base, image_size = _retry_process_image_operation(lambda: _read_remote_process_image_layout_once(pid))
    return int(image_base), int(image_size)


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
    js5_rsa_source_exe: Path | None = None,
) -> dict[str, Any]:
    executable_bytes = executable_path.read_bytes()
    target_moduli = load_rsa_moduli(rsa_config_path)
    results: dict[str, Any] = {
        "executablePath": str(executable_path),
        "rsaConfigPath": str(rsa_config_path),
        "js5RsaSourceExe": str(js5_rsa_source_exe) if js5_rsa_source_exe is not None else None,
    }

    for name, bits in (("login", 1024), ("js5", 4096)):
        embedded_offset, original_modulus = find_embedded_rsa_key(executable_bytes, bits)
        if original_modulus is None:
            results[name] = {
                "foundInExecutable": False,
                "embeddedOffset": None,
                "replacementSource": None,
                "patch": None,
            }
            continue
        replacement_source = "rsa-config"
        replacement_modulus = target_moduli[name]
        if name == "js5" and js5_rsa_source_exe is not None:
            js5_source_bytes = js5_rsa_source_exe.read_bytes()
            _, source_modulus = find_embedded_rsa_key(js5_source_bytes, bits)
            if source_modulus is None:
                results[name] = {
                    "foundInExecutable": True,
                    "embeddedOffset": f"0x{embedded_offset:x}",
                    "originalModulusPreview": original_modulus[:32],
                    "replacementSource": str(js5_rsa_source_exe),
                    "patch": {
                        "applied": False,
                        "reason": "js5-source-modulus-not-found",
                    },
                }
                continue
            replacement_modulus = source_modulus
            replacement_source = str(js5_rsa_source_exe)
        patch_result = patch_remote_ascii_literal_occurrences(pid, original_modulus, replacement_modulus)
        results[name] = {
            "foundInExecutable": True,
            "embeddedOffset": f"0x{embedded_offset:x}",
            "originalModulusPreview": original_modulus[:32],
            "replacementModulusPreview": replacement_modulus[:32],
            "replacementSource": replacement_source,
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


def _encode_absolute_jump(target_address: int, patch_size: int | None = None) -> bytes:
    encoded = b"\x48\xB8" + int(target_address).to_bytes(8, "little", signed=False) + b"\xFF\xE0"
    if patch_size is not None:
        if patch_size < len(encoded):
            raise ValueError(f"Patch size {patch_size} is too small for an absolute jump")
        encoded += b"\x90" * (patch_size - len(encoded))
    return encoded


def _encode_absolute_call(target_address: int) -> bytes:
    return b"\x49\xBB" + int(target_address).to_bytes(8, "little", signed=False) + b"\x41\xFF\xD3"


def _encode_rel32_conditional_jump(opcode: bytes, source_address: int, target_address: int) -> bytes:
    displacement = target_address - (source_address + len(opcode) + 4)
    if not -(2**31) <= displacement <= (2**31 - 1):
        raise ValueError(
            f"Conditional jump displacement out of range: source=0x{source_address:x} target=0x{target_address:x}"
        )
    return opcode + int(displacement).to_bytes(4, "little", signed=True)


def _build_59002d_guard_trampoline(
    *,
    trampoline_address: int,
    skip_target_address: int,
    return_address: int,
    overwritten_bytes: bytes,
) -> bytes:
    stub = bytearray()
    stub.extend(b"\x48\x85\xDB")  # test rbx, rbx
    je_zero_address = trampoline_address + len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(b"\x4C\x39\xE3")  # cmp rbx, r12
    je_r12_address = trampoline_address + len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(overwritten_bytes)
    stub.extend(_encode_absolute_jump(return_address))
    skip_address = trampoline_address + len(stub)
    stub.extend(_encode_absolute_jump(skip_target_address))

    stub[3:9] = _encode_rel32_conditional_jump(b"\x0F\x84", je_zero_address, skip_address)
    stub[12:18] = _encode_rel32_conditional_jump(b"\x0F\x84", je_r12_address, skip_address)
    return bytes(stub)


def _build_590c58_master_table_guard_trampoline(
    *,
    trampoline_address: int,
    skip_target_address: int,
    return_address: int,
) -> bytes:
    stub = bytearray()
    stub.extend(bytes.fromhex("48 8B 91 D0 30 00 00"))  # mov rdx, [rcx+0x30d0]
    stub.extend(bytes.fromhex("48 85 D2"))  # test rdx, rdx
    je_skip_offset = len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("4C 3B 52 10"))  # cmp r10, [rdx+0x10]
    jae_skip_offset = len(stub)
    stub.extend(b"\x0F\x83\x00\x00\x00\x00")
    stub.extend(_encode_absolute_jump(return_address))
    skip_address = trampoline_address + len(stub)
    stub.extend(bytes.fromhex("41 B8 FF FF FF FF"))  # mov r8d, -1
    stub.extend(bytes.fromhex("41 B9 FF FF FF FF"))  # mov r9d, -1
    stub.extend(_encode_absolute_jump(skip_target_address))
    stub[je_skip_offset : je_skip_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        trampoline_address + je_skip_offset,
        skip_address,
    )
    stub[jae_skip_offset : jae_skip_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x83",
        trampoline_address + jae_skip_offset,
        skip_address,
    )
    return bytes(stub)


def _build_58fa83_master_table_presence_guard_trampoline(
    *,
    trampoline_address: int,
    skip_target_address: int,
    return_address: int,
) -> bytes:
    stub = bytearray()
    stub.extend(bytes.fromhex("48 8B 81 D0 30 00 00"))  # mov rax, [rcx+0x30d0]
    stub.extend(bytes.fromhex("48 85 C0"))  # test rax, rax
    je_skip_offset = len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("41 8B D5"))  # mov edx, r13d
    stub.extend(bytes.fromhex("44 8B 20"))  # mov r12d, [rax]
    stub.extend(_encode_absolute_jump(return_address))
    skip_address = trampoline_address + len(stub)
    stub.extend(_encode_absolute_jump(skip_target_address))
    stub[je_skip_offset : je_skip_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        trampoline_address + je_skip_offset,
        skip_address,
    )
    return bytes(stub)


def _build_59c1ea_force_length_gate_trampoline(*, skip_target_address: int) -> bytes:
    stub = bytearray()
    stub.extend(bytes.fromhex("41 BE 41 00 00 00"))  # mov r14d, 0x41
    stub.extend(bytes.fromhex("48 C7 44 24 38 41 00 00 00"))  # mov qword ptr [rsp+0x38], 0x41
    stub.extend(_encode_absolute_jump(skip_target_address))
    return bytes(stub)


def _build_59c2a0_compare_mirror_trampoline(
    *,
    trampoline_address: int,
    fail_target_address: int,
    return_address: int,
) -> bytes:
    stub = bytearray()
    stub.extend(bytes.fromhex("85 D2"))  # test edx, edx
    jne_compare_offset = len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("41 51"))  # push r9
    stub.extend(bytes.fromhex("41 52"))  # push r10
    stub.extend(bytes.fromhex("41 53"))  # push r11
    stub.extend(bytes.fromhex("4C 8D 5B 01"))  # lea r11, [rbx+1]
    stub.extend(bytes.fromhex("49 89 C9"))  # mov r9, rcx
    stub.extend(bytes.fromhex("41 BA 40 00 00 00"))  # mov r10d, 0x40
    copy_loop_address = trampoline_address + len(stub)
    stub.extend(bytes.fromhex("41 8A 01"))  # mov al, [r9]
    stub.extend(bytes.fromhex("41 88 03"))  # mov [r11], al
    stub.extend(bytes.fromhex("49 FF C1"))  # inc r9
    stub.extend(bytes.fromhex("49 FF C3"))  # inc r11
    stub.extend(bytes.fromhex("41 83 EA 01"))  # sub r10d, 1
    jne_copy_loop_offset = len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("41 5B"))  # pop r11
    stub.extend(bytes.fromhex("41 5A"))  # pop r10
    stub.extend(bytes.fromhex("41 59"))  # pop r9
    compare_address = trampoline_address + len(stub)
    stub.extend(bytes.fromhex("41 0F B6 44 08 01"))  # movzx eax, byte ptr [r8+rcx+1]
    stub.extend(bytes.fromhex("38 01"))  # cmp byte ptr [rcx], al
    jne_fail_offset = len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")
    stub.extend(_encode_absolute_jump(return_address))
    fail_address = trampoline_address + len(stub)
    stub.extend(_encode_absolute_jump(fail_target_address))

    stub[jne_compare_offset : jne_compare_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x85",
        trampoline_address + jne_compare_offset,
        compare_address,
    )
    stub[jne_copy_loop_offset : jne_copy_loop_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x85",
        trampoline_address + jne_copy_loop_offset,
        copy_loop_address,
    )
    stub[jne_fail_offset : jne_fail_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x85",
        trampoline_address + jne_fail_offset,
        fail_address,
    )
    return bytes(stub)


def _build_590c72_sentinel_trampoline(*, return_address: int) -> bytes:
    stub = bytearray()
    stub.extend(bytes.fromhex("41 B8 FF FF FF FF"))  # mov r8d, -1
    stub.extend(bytes.fromhex("41 B9 FF FF FF FF"))  # mov r9d, -1
    stub.extend(_encode_absolute_jump(return_address))
    return bytes(stub)


def _build_5927f2_master_table_publish_guard_trampoline(
    *,
    trampoline_address: int,
    skip_target_address: int,
    return_address: int,
) -> bytes:
    del return_address

    stub = bytearray()
    stub.extend(bytes.fromhex("4D 85 FF"))  # test r15, r15
    je_skip_offset = len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("41 83 3F 42"))  # cmp dword ptr [r15], 0x42
    jne_skip3_offset = len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("49 83 7F 10 43"))  # cmp qword ptr [r15+0x10], 0x43
    jne_skip4_offset = len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("49 83 7F 18 00"))  # cmp qword ptr [r15+0x18], 0
    je_skip5_offset = len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("4C 89 38"))  # mov [rax], r15

    skip_address = trampoline_address + len(stub)
    stub.extend(_encode_absolute_jump(skip_target_address))

    stub[je_skip_offset : je_skip_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        trampoline_address + je_skip_offset,
        skip_address,
    )
    stub[jne_skip3_offset : jne_skip3_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x85",
        trampoline_address + jne_skip3_offset,
        skip_address,
    )
    stub[jne_skip4_offset : jne_skip4_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x85",
        trampoline_address + jne_skip4_offset,
        skip_address,
    )
    stub[je_skip5_offset : je_skip5_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        trampoline_address + je_skip5_offset,
        skip_address,
    )
    return bytes(stub)


def _build_590ccb_force_first_compare_trampoline(
    *,
    trampoline_address: int,
    return_address: int,
    success_target_address: int,
) -> bytes:
    stub = bytearray()
    stub.extend(bytes.fromhex("89 D9"))  # mov ecx, ebx
    stub.extend(bytes.fromhex("44 89 C0"))  # mov eax, r8d
    stub.extend(bytes.fromhex("84 D2"))  # test dl, dl
    je_indexed_offset = len(stub)
    je_indexed_address = trampoline_address + je_indexed_offset
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("8B 47 20"))  # mov eax, dword ptr [rdi+0x20]
    stub.extend(_encode_absolute_jump(success_target_address))
    indexed_address = trampoline_address + len(stub)
    stub.extend(_encode_absolute_jump(return_address))
    stub[je_indexed_offset : je_indexed_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        je_indexed_address,
        indexed_address,
    )
    return bytes(stub)


def _build_590cf1_force_second_compare_trampoline(*, success_target_address: int) -> bytes:
    stub = bytearray()
    stub.extend(bytes.fromhex("44 89 C8"))  # mov eax, r9d
    stub.extend(_encode_absolute_jump(success_target_address))
    return bytes(stub)


def _build_590de8_empty_compare_guard_trampoline(
    *,
    trampoline_address: int,
    skip_target_address: int,
    return_address: int,
) -> bytes:
    stub = bytearray()
    stub.extend(bytes.fromhex("45 0F B6 8F 34 77 00 00"))  # movzx r9d, byte ptr [r15+0x7734]
    stub.extend(bytes.fromhex("4D 8D 87 10 77 00 00"))  # lea r8, [r15+0x7710]
    stub.extend(bytes.fromhex("45 84 C9"))  # test r9b, r9b
    jne_continue_offset = len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("49 83 BF D8 77 00 00 00"))  # cmp qword ptr [r15+0x77d8], 0
    jne_continue2_offset = len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("48 85 FF"))  # test rdi, rdi
    je_skip_offset = len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("80 7F 24 00"))  # cmp byte ptr [rdi+0x24], 0
    je_empty_path_offset = len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("83 3F 00"))  # cmp dword ptr [rdi], 0
    je_skip2_offset = len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("83 7F 20 00"))  # cmp dword ptr [rdi+0x20], 0
    je_skip3_offset = len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("8B 07"))  # mov eax, dword ptr [rdi]
    stub.extend(bytes.fromhex("41 89 87 10 77 00 00"))  # mov dword ptr [r15+0x7710], eax
    stub.extend(bytes.fromhex("8B 47 20"))  # mov eax, dword ptr [rdi+0x20]
    stub.extend(bytes.fromhex("41 89 87 30 77 00 00"))  # mov dword ptr [r15+0x7730], eax
    stub.extend(bytes.fromhex("41 C6 87 34 77 00 00 01"))  # mov byte ptr [r15+0x7734], 1

    empty_path_address = trampoline_address + len(stub)
    stub.extend(bytes.fromhex("48 83 BF 98 00 00 00 00"))  # cmp qword ptr [rdi+0x98], 0
    jne_skip4_offset = len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("48 83 BF C8 00 00 00 00"))  # cmp qword ptr [rdi+0xc8], 0
    jne_skip5_offset = len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")

    continue_address = trampoline_address + len(stub)
    stub.extend(_encode_absolute_jump(return_address))
    skip_address = trampoline_address + len(stub)
    stub.extend(_encode_absolute_jump(skip_target_address))

    stub[jne_continue_offset : jne_continue_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x85",
        trampoline_address + jne_continue_offset,
        continue_address,
    )
    stub[jne_continue2_offset : jne_continue2_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x85",
        trampoline_address + jne_continue2_offset,
        continue_address,
    )
    stub[je_skip_offset : je_skip_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        trampoline_address + je_skip_offset,
        skip_address,
    )
    stub[je_empty_path_offset : je_empty_path_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        trampoline_address + je_empty_path_offset,
        empty_path_address,
    )
    stub[je_skip2_offset : je_skip2_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        trampoline_address + je_skip2_offset,
        skip_address,
    )
    stub[je_skip3_offset : je_skip3_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        trampoline_address + je_skip3_offset,
        skip_address,
    )
    stub[jne_skip4_offset : jne_skip4_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x85",
        trampoline_address + jne_skip4_offset,
        skip_address,
    )
    stub[jne_skip5_offset : jne_skip5_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x85",
        trampoline_address + jne_skip5_offset,
        skip_address,
    )
    return bytes(stub)


def _build_590ec9_archive_state_slot_guard_trampoline(
    *,
    trampoline_address: int,
    return_address: int,
) -> bytes:
    stub = bytearray()
    stub.extend(bytes.fromhex("48 C1 E0 05"))  # shl rax, 5
    stub.extend(bytes.fromhex("4A 8B 84 18 10 0C 01 00"))  # mov rax, [rax+r11+0x10c10]
    stub.extend(bytes.fromhex("48 85 C0"))  # test rax, rax
    je_missing_offset = len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("48 83 F8 FF"))  # cmp rax, -1
    je_missing2_offset = len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("48 3D 00 00 01 00"))  # cmp rax, 0x10000
    jb_missing_offset = len(stub)
    stub.extend(b"\x0F\x82\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("0F B6 54 18 01"))  # movzx edx, byte ptr [rax+rbx+1]
    stub.extend(_encode_absolute_jump(return_address))

    missing_address = trampoline_address + len(stub)
    stub.extend(bytes.fromhex("31 D2"))  # xor edx, edx
    stub.extend(_encode_absolute_jump(return_address))

    stub[je_missing_offset : je_missing_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        trampoline_address + je_missing_offset,
        missing_address,
    )
    stub[je_missing2_offset : je_missing2_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        trampoline_address + je_missing2_offset,
        missing_address,
    )
    stub[jb_missing_offset : jb_missing_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x82",
        trampoline_address + jb_missing_offset,
        missing_address,
    )
    return bytes(stub)


def _build_2ab698_null_param2_guard_trampoline(
    *,
    trampoline_address: int,
    skip_target_address: int,
    return_address: int,
) -> bytes:
    stub = bytearray()
    stub.extend(bytes.fromhex("48 8B 72 08"))  # mov rsi, [rdx+0x8]
    stub.extend(bytes.fromhex("48 85 F6"))  # test rsi, rsi
    je_skip_offset = len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("4C 8B FA"))  # mov r15, rdx
    stub.extend(bytes.fromhex("4C 8B F1"))  # mov r14, rcx
    stub.extend(bytes.fromhex("49 8D 53 A8"))  # lea rdx, [r11-0x58]
    stub.extend(bytes.fromhex("48 83 C1 20"))  # add rcx, 0x20
    stub.extend(bytes.fromhex("41 8B F8"))  # mov edi, r8d
    stub.extend(_encode_absolute_jump(return_address))

    skip_address = trampoline_address + len(stub)
    stub.extend(_encode_absolute_jump(skip_target_address))
    stub[je_skip_offset : je_skip_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        trampoline_address + je_skip_offset,
        skip_address,
    )
    return bytes(stub)


def _build_3699b2_world_metadata_guard_trampoline(
    *,
    trampoline_address: int,
    skip_target_address: int,
    return_address: int,
) -> bytes:
    stub = bytearray()
    stub.extend(bytes.fromhex("4C 8B 11"))  # mov r10, [rcx]
    stub.extend(bytes.fromhex("44 89 41 0C"))  # mov [rcx+0xc], r8d
    stub.extend(bytes.fromhex("4D 85 D2"))  # test r10, r10
    je_bad1_offset = len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("49 81 FA 00 00 01 00"))  # cmp r10, 0x10000
    jb_bad2_offset = len(stub)
    stub.extend(b"\x0F\x82\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("4C 89 D0"))  # mov rax, r10
    stub.extend(bytes.fromhex("48 C1 E0 10"))  # shl rax, 16
    stub.extend(bytes.fromhex("48 C1 F8 10"))  # sar rax, 16
    stub.extend(bytes.fromhex("4C 39 D0"))  # cmp rax, r10
    jne_bad3_offset = len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("49 8B 5A 18"))  # mov rbx, [r10+0x18]
    stub.extend(bytes.fromhex("48 85 DB"))  # test rbx, rbx
    je_bad4_offset = len(stub)
    stub.extend(b"\x0F\x84\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("48 81 FB 00 00 01 00"))  # cmp rbx, 0x10000
    jb_bad5_offset = len(stub)
    stub.extend(b"\x0F\x82\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("48 89 D8"))  # mov rax, rbx
    stub.extend(bytes.fromhex("48 C1 E0 10"))  # shl rax, 16
    stub.extend(bytes.fromhex("48 C1 F8 10"))  # sar rax, 16
    stub.extend(bytes.fromhex("48 39 D8"))  # cmp rax, rbx
    jne_bad6_offset = len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("33 C9"))  # xor ecx, ecx
    stub.extend(bytes.fromhex("8B C1"))  # mov eax, ecx
    stub.extend(_encode_absolute_jump(return_address))

    bad_address = trampoline_address + len(stub)
    stub.extend(bytes.fromhex("31 C0"))  # xor eax, eax
    stub.extend(bytes.fromhex("89 41 10"))  # mov [rcx+0x10], eax
    stub.extend(_encode_absolute_jump(skip_target_address))

    stub[je_bad1_offset : je_bad1_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        trampoline_address + je_bad1_offset,
        bad_address,
    )
    stub[jb_bad2_offset : jb_bad2_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x82",
        trampoline_address + jb_bad2_offset,
        bad_address,
    )
    stub[jne_bad3_offset : jne_bad3_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x85",
        trampoline_address + jne_bad3_offset,
        bad_address,
    )
    stub[je_bad4_offset : je_bad4_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x84",
        trampoline_address + je_bad4_offset,
        bad_address,
    )
    stub[jb_bad5_offset : jb_bad5_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x82",
        trampoline_address + jb_bad5_offset,
        bad_address,
    )
    stub[jne_bad6_offset : jne_bad6_offset + 6] = _encode_rel32_conditional_jump(
        b"\x0F\x85",
        trampoline_address + jne_bad6_offset,
        bad_address,
    )
    return bytes(stub)


def _build_5902d5_state_guard_trampoline(
    *,
    trampoline_address: int,
    skip_target_address: int,
    return_address: int,
) -> bytes:
    stub = bytearray()
    stub.extend(bytes.fromhex("41 80 FA 01"))  # cmp r10b, 1
    jne_continue_address = trampoline_address + len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("44 0F B6 8A 34 77 00 00"))  # movzx r9d, byte ptr [rdx+0x7734]
    stub.extend(bytes.fromhex("45 84 C9"))  # test r9b, r9b
    jne_skip_address = trampoline_address + len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")
    stub.extend(bytes.fromhex("48 83 BA D8 77 00 00 00"))  # cmp qword ptr [rdx+0x77d8], 0
    jne_skip2_address = trampoline_address + len(stub)
    stub.extend(b"\x0F\x85\x00\x00\x00\x00")
    continue_address = trampoline_address + len(stub)
    stub.extend(bytes.fromhex("49 8B 00"))  # mov rax, [r8]
    stub.extend(_encode_absolute_jump(return_address))
    skip_address = trampoline_address + len(stub)
    stub.extend(_encode_absolute_jump(skip_target_address))
    stub[4:10] = _encode_rel32_conditional_jump(b"\x0F\x85", jne_continue_address, continue_address)
    stub[21:27] = _encode_rel32_conditional_jump(b"\x0F\x85", jne_skip_address, skip_address)
    stub[35:41] = _encode_rel32_conditional_jump(b"\x0F\x85", jne_skip2_address, skip_address)
    return bytes(stub)


def patch_remote_jump_bypass_blocks(pid: int, jump_specs: list[tuple[int, int]]) -> list[dict[str, Any]]:
    if not jump_specs:
        return []

    image_base = read_remote_process_image_base(pid)
    results: list[dict[str, Any]] = []

    handle = _open_process(pid)
    try:
        for source_offset, target_offset in jump_specs:
            special_guard = SPECIAL_GUARDED_JUMP_BYPASS_SPECS.get((source_offset, target_offset))
            if special_guard is not None:
                expected = special_guard["expected"]
                source_address = image_base + source_offset
                target_address = image_base + target_offset
                return_address = image_base + int(special_guard["resumeOffset"])
                original = _read_process_memory(handle, source_address, len(expected))
                matched = original == expected
                patched = None
                trampoline = None
                trampoline_address = None
                if matched:
                    trampoline_address = _allocate_process_memory(handle, 256)
                    if special_guard["builder"] == "guard-59002d":
                        trampoline = _build_59002d_guard_trampoline(
                            trampoline_address=trampoline_address,
                            skip_target_address=target_address,
                            return_address=return_address,
                            overwritten_bytes=expected,
                        )
                    elif special_guard["builder"] == "guard-5902d5":
                        trampoline = _build_5902d5_state_guard_trampoline(
                            trampoline_address=trampoline_address,
                            skip_target_address=target_address,
                            return_address=return_address,
                        )
                    elif special_guard["builder"] == "guard-590c58":
                        trampoline = _build_590c58_master_table_guard_trampoline(
                            trampoline_address=trampoline_address,
                            skip_target_address=target_address,
                            return_address=return_address,
                        )
                    elif special_guard["builder"] == "guard-58fa83":
                        trampoline = _build_58fa83_master_table_presence_guard_trampoline(
                            trampoline_address=trampoline_address,
                            skip_target_address=target_address,
                            return_address=return_address,
                        )
                    elif special_guard["builder"] == "force-length-59c1ea":
                        trampoline = _build_59c1ea_force_length_gate_trampoline(
                            skip_target_address=target_address,
                        )
                    elif special_guard["builder"] == "mirror-compare-59c2a0":
                        trampoline = _build_59c2a0_compare_mirror_trampoline(
                            trampoline_address=trampoline_address,
                            fail_target_address=target_address,
                            return_address=return_address,
                        )
                    elif special_guard["builder"] == "sentinel-590c72":
                        trampoline = _build_590c72_sentinel_trampoline(return_address=return_address)
                    elif special_guard["builder"] == "guarded-publish-5927f2":
                        trampoline = _build_5927f2_master_table_publish_guard_trampoline(
                            trampoline_address=trampoline_address,
                            skip_target_address=target_address,
                            return_address=return_address,
                        )
                    elif special_guard["builder"] == "force-compare-590ccb":
                        trampoline = _build_590ccb_force_first_compare_trampoline(
                            trampoline_address=trampoline_address,
                            return_address=return_address,
                            success_target_address=target_address,
                        )
                    elif special_guard["builder"] == "force-compare-590cf1":
                        trampoline = _build_590cf1_force_second_compare_trampoline(
                            success_target_address=target_address,
                        )
                    elif special_guard["builder"] == "guard-590de8":
                        trampoline = _build_590de8_empty_compare_guard_trampoline(
                            trampoline_address=trampoline_address,
                            skip_target_address=target_address,
                            return_address=return_address,
                        )
                    elif special_guard["builder"] == "guard-590ec9":
                        trampoline = _build_590ec9_archive_state_slot_guard_trampoline(
                            trampoline_address=trampoline_address,
                            return_address=return_address,
                        )
                    elif special_guard["builder"] == "guard-2ab698":
                        trampoline = _build_2ab698_null_param2_guard_trampoline(
                            trampoline_address=trampoline_address,
                            skip_target_address=target_address,
                            return_address=return_address,
                        )
                    elif special_guard["builder"] == "guard-3699b2":
                        trampoline = _build_3699b2_world_metadata_guard_trampoline(
                            trampoline_address=trampoline_address,
                            skip_target_address=target_address,
                            return_address=return_address,
                        )
                    else:
                        raise ValueError(
                            f"Unsupported guarded jump-bypass builder {special_guard['builder']!r} "
                            f"for 0x{source_offset:x}:0x{target_offset:x}"
                        )
                    _write_process_memory(handle, trampoline_address, trampoline)
                    patched = _encode_absolute_jump(trampoline_address, len(expected))
                    _write_process_memory(handle, source_address, patched)
                results.append(
                    {
                        "sourceOffset": f"0x{source_offset:x}",
                        "targetOffset": f"0x{target_offset:x}",
                        "sourceAddress": f"0x{source_address:x}",
                        "targetAddress": f"0x{target_address:x}",
                        "returnOffset": f"0x{int(special_guard['resumeOffset']):x}",
                        "returnAddress": f"0x{return_address:x}",
                        "matched": matched,
                        "expectedHex": expected.hex(),
                        "originalHex": original.hex(),
                        "patchedHex": patched.hex() if patched is not None else None,
                        "patchKind": "guarded-trampoline",
                        "builder": special_guard["builder"],
                        "trampolineAddress": f"0x{trampoline_address:x}" if trampoline_address is not None else None,
                        "trampolineHex": trampoline.hex() if trampoline is not None else None,
                    }
                )
                continue
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
                    "patchKind": "relative-jump-bypass",
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
    js5_rsa_source_exe = Path(args.js5_rsa_source_exe) if args.js5_rsa_source_exe else None
    child_exe_override = Path(args.child_exe_override) if args.child_exe_override else None
    accepted_child_exes = [str(Path(value).resolve(strict=False)) for value in (args.accepted_child_exe or []) if str(value or "").strip()]
    wrapper_exe = Path(args.wrapper_exe)
    trace_output = Path(args.trace_output)
    trace_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output = Path(args.summary_output) if args.summary_output else None
    if summary_output is not None:
        summary_output.parent.mkdir(parents=True, exist_ok=True)
    child_hook_output = Path(args.child_hook_output) if args.child_hook_output else None
    if child_hook_output is not None:
        child_hook_output.parent.mkdir(parents=True, exist_ok=True)

    jav_config_text, rewrite_config_details = load_rewrite_jav_config(
        args.config_uri,
        rewrite_config_file=args.rewrite_config_file,
    )
    param_map = extract_param_map(jav_config_text)
    rewrite_map = build_effective_rewrite_map(jav_config_text, rewrite_scope=args.rewrite_scope)
    resolve_redirects = (
        build_route_resolve_redirects(
            param_map,
            jav_config_text=jav_config_text,
            include_secure_retail_world_fleet=(
                args.force_secure_retail_startup_redirects
                and is_secure_retail_startup_contract(args.config_uri)
            ),
            include_content_hosts=not (
                args.force_secure_retail_startup_redirects
                and is_secure_retail_startup_contract(args.config_uri)
            ),
        )
        if should_auto_redirect_route_hosts(
            args.config_uri,
            force_secure_retail_startup_redirects=args.force_secure_retail_startup_redirects,
        )
        else {}
    )
    resolve_redirects.update(explicit_resolve_redirects)
    connect_redirects = (
        {}
        if is_secure_retail_startup_contract(args.config_uri)
        else build_connect_redirects(resolve_redirects)
    )
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
        accepted_child_refresh_stop = threading.Event()
        accepted_child_refresh_state: dict[str, Any] = {
            "enabled": child_exe_override is not None and bool(accepted_child_exes),
            "started": False,
            "copies": 0,
            "lastRefreshTimestamp": None,
            "lastDestination": None,
            "lastResult": None,
            "errors": [],
        }
        accepted_child_refresh_thread: threading.Thread | None = None

        def refresh_accepted_children_once() -> None:
            if child_exe_override is None:
                return
            for accepted_child_exe in accepted_child_exes:
                refresh_result = refresh_accepted_child_exe(child_exe_override, accepted_child_exe)
                if refresh_result is None:
                    continue
                accepted_child_refresh_state["copies"] = int(accepted_child_refresh_state["copies"]) + 1
                accepted_child_refresh_state["lastRefreshTimestamp"] = round(time.time(), 6)
                accepted_child_refresh_state["lastDestination"] = accepted_child_exe
                accepted_child_refresh_state["lastResult"] = refresh_result
                write_event(
                    {
                        "action": "accepted-child-exe-refreshed",
                        "source": str(child_exe_override),
                        "destination": accepted_child_exe,
                        "result": refresh_result,
                        "timestamp": time.time(),
                    }
                )

        def run_accepted_child_refresh_guard() -> None:
            accepted_child_refresh_state["started"] = True
            while (
                not accepted_child_refresh_stop.is_set()
                and not child_created.is_set()
                and not detached.is_set()
            ):
                try:
                    refresh_accepted_children_once()
                except Exception as error:
                    error_record = {"message": str(error), "timestamp": round(time.time(), 6)}
                    accepted_child_refresh_state["errors"].append(error_record)
                    accepted_child_refresh_state["errors"] = accepted_child_refresh_state["errors"][-8:]
                    write_event(
                        {
                            "action": "accepted-child-exe-refresh-failed",
                            "source": str(child_exe_override) if child_exe_override is not None else None,
                            "destinations": accepted_child_exes,
                            "error": str(error),
                            "timestamp": time.time(),
                        }
                    )
                accepted_child_refresh_stop.wait(0.25)

        if frida is None:
            raise RuntimeError(
                "Frida is required for wrapper spawn rewrite, but it could not be imported: "
                f"{FRIDA_IMPORT_ERROR}"
            )

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
            wrapper_script = session.create_script(
                build_wrapper_spawn_script(str(child_exe_override), accepted_child_exes)
            )
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
            if accepted_child_exes:
                refresh_accepted_children_once()
                accepted_child_refresh_thread = threading.Thread(
                    target=run_accepted_child_refresh_guard,
                    name="accepted-child-exe-refresh",
                    daemon=True,
                )
                accepted_child_refresh_thread.start()
                write_event(
                    {
                        "action": "accepted-child-exe-refresh-guard-armed",
                        "processId": wrapper_pid,
                        "source": str(child_exe_override),
                        "destinations": accepted_child_exes,
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
                    rsa_patch_results = patch_remote_embedded_rsa_moduli(
                        child_pid,
                        executable_path,
                        rsa_config_path,
                        js5_rsa_source_exe=js5_rsa_source_exe,
                    )
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
            override_content_equivalent = files_equal(
                str(child_exe_override) if child_exe_override is not None else None,
                child_path,
            )
            override_accepted = (
                override_verified
                or path_matches_any(child_path, accepted_child_exes)
                or override_content_equivalent
            )
            accepted_child_matched = None
            if not override_verified and override_accepted and child_path:
                accepted_child_matched = next(
                    (candidate for candidate in accepted_child_exes if paths_equal(child_path, candidate)),
                    None,
                )
            if override_requested and not override_accepted:
                write_event(
                    {
                        "action": "child-exe-override-mismatch",
                        "requestedChildExe": str(child_exe_override),
                        "actualChildExe": child_path,
                        "overrideMechanism": override_mechanism,
                        "overrideContentEquivalent": override_content_equivalent,
                        "acceptedChildExes": accepted_child_exes,
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
            if override_requested and accepted_child_matched is not None:
                write_event(
                    {
                        "action": "child-exe-override-accepted",
                        "requestedChildExe": str(child_exe_override),
                        "actualChildExe": child_path,
                        "acceptedChildExe": accepted_child_matched,
                        "overrideMechanism": override_mechanism,
                        "processId": child_process_id,
                        "timestamp": time.time(),
                    }
                )
            if override_requested and override_content_equivalent and not override_verified:
                write_event(
                    {
                        "action": "child-exe-override-content-match-accepted",
                        "requestedChildExe": str(child_exe_override),
                        "actualChildExe": child_path,
                        "overrideMechanism": override_mechanism,
                        "processId": child_process_id,
                        "timestamp": time.time(),
                    }
                )
            wrapper_cleanup_result = cleanup_wrapper_after_child_ready(wrapper_pid, child_process_id, write_event)

            summary = {
                "wrapperPid": wrapper_pid,
                "wrapperArgv": wrapper_argv,
                "configUri": args.config_uri,
                "rewriteConfigFile": args.rewrite_config_file,
                "rewriteConfigSource": rewrite_config_details["source"],
                "rewriteConfigPath": rewrite_config_details["path"],
                "rewriteConfigFetchUri": rewrite_config_details["fetchUri"],
                "childExeOverride": str(child_exe_override) if child_exe_override is not None else None,
                "acceptedChildExes": accepted_child_exes,
                "overrideRequested": override_requested,
                "overrideApplied": override_applied,
                "overrideVerified": override_verified,
                "overrideContentEquivalent": override_content_equivalent,
                "overrideAccepted": override_accepted,
                "acceptedChildMatched": accepted_child_matched,
                "overrideMechanism": override_mechanism,
                "childPid": child_process_id,
                "childPath": child_path,
                "childCommandLine": child_command_line,
                "rewrittenCommandLine": last_rewritten_command_line,
                "acceptedChildRefresh": accepted_child_refresh_state,
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
                "forceSecureRetailStartupRedirects": bool(args.force_secure_retail_startup_redirects),
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
            accepted_child_refresh_stop.set()
            if accepted_child_refresh_thread is not None:
                accepted_child_refresh_thread.join(timeout=2.0)
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
