from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageGrab


user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002
SW_RESTORE = 9
DIB_RGB_COLORS = 0
SRCCOPY = 0x00CC0020
BI_RGB = 0


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a top-level window to PNG.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pid", type=int, help="Capture the first visible top-level window for this PID.")
    group.add_argument("--handle", type=lambda value: int(value, 0), help="Capture this HWND.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--foreground", action="store_true", help="Restore and foreground the target before capture.")
    parser.add_argument(
        "--client-only",
        action="store_true",
        help="Capture only the client rect when PrintWindow supports it.",
    )
    return parser.parse_args()


def get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def enum_windows_for_pid(pid: int) -> list[int]:
    matches: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, lparam: int) -> bool:
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value != pid:
            return True
        if not user32.IsWindowVisible(hwnd):
            return True
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return True
        matches.append(hwnd)
        return True

    if not user32.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return matches


def resolve_hwnd(pid: int | None, handle: int | None) -> int:
    if handle:
        return handle
    assert pid is not None
    matches = enum_windows_for_pid(pid)
    if not matches:
        raise RuntimeError(f"Could not find a visible top-level window for pid {pid}")
    return matches[0]


def get_window_rect(hwnd: int) -> RECT:
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    return rect


def capture_with_printwindow(hwnd: int, width: int, height: int, client_only: bool) -> Image.Image:
    hwnd_dc = user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        raise ctypes.WinError(ctypes.get_last_error())

    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    if not mem_dc:
        user32.ReleaseDC(hwnd, hwnd_dc)
        raise ctypes.WinError(ctypes.get_last_error())

    bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
    if not bitmap:
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)
        raise ctypes.WinError(ctypes.get_last_error())

    old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
    try:
        flags_to_try = []
        if client_only:
            flags_to_try.append(PW_CLIENTONLY | PW_RENDERFULLCONTENT)
            flags_to_try.append(PW_CLIENTONLY)
        flags_to_try.append(PW_RENDERFULLCONTENT)
        flags_to_try.append(0)

        printed = False
        for flags in flags_to_try:
            result = user32.PrintWindow(hwnd, mem_dc, flags)
            if result:
                printed = True
                break
        if not printed:
            if not gdi32.BitBlt(mem_dc, 0, 0, width, height, hwnd_dc, 0, 0, SRCCOPY):
                raise RuntimeError("PrintWindow and BitBlt both failed")

        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = width
        bitmap_info.bmiHeader.biHeight = -height
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = BI_RGB

        buffer_len = width * height * 4
        buffer = (ctypes.c_byte * buffer_len)()
        rows = gdi32.GetDIBits(
            mem_dc,
            bitmap,
            0,
            height,
            ctypes.byref(buffer),
            ctypes.byref(bitmap_info),
            DIB_RGB_COLORS,
        )
        if rows != height:
            raise RuntimeError(f"GetDIBits returned {rows}, expected {height}")

        return Image.frombuffer("RGB", (width, height), bytes(buffer), "raw", "BGRX", 0, 1)
    finally:
        gdi32.SelectObject(mem_dc, old_bitmap)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)


def capture_with_screen_grab(rect: RECT) -> Image.Image:
    bbox = (rect.left, rect.top, rect.right, rect.bottom)
    return ImageGrab.grab(bbox=bbox, all_screens=True).convert("RGB")


def main() -> int:
    args = parse_args()
    hwnd = resolve_hwnd(args.pid, args.handle)
    if args.foreground:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
    rect = get_window_rect(hwnd)
    width = max(1, rect.right - rect.left)
    height = max(1, rect.bottom - rect.top)
    image = capture_with_printwindow(hwnd, width, height, args.client_only)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    title = get_window_text(hwnd)
    print(f"handle=0x{hwnd:x}")
    print(f"title={title}")
    print(f"bounds={rect.left},{rect.top},{rect.right},{rect.bottom}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
