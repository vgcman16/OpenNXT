from __future__ import annotations

import argparse
import ctypes
import json
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from rapidocr_onnxruntime import RapidOCR

from capture_window import (
    RECT,
    SW_RESTORE,
    capture_with_screen_grab,
    capture_with_printwindow,
    get_window_rect,
    get_window_text,
    user32,
)
from inspect_runescape_screenshot import inspect_image, normalize_text


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
OCR_ENGINE: RapidOCR | None = None
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.OpenClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = ()
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE
user32.CloseClipboard.argtypes = ()
user32.CloseClipboard.restype = wintypes.BOOL
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalFree.restype = wintypes.HGLOBAL

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_A = 0x41
VK_V = 0x56
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_BACK = 0x08
VK_DELETE = 0x2E
VK_HOME = 0x24
VK_END = 0x23
SAFE_LOGIN_BUTTON_GAP_PX = 28
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040
FOREIGN_OVERLAY_MARKERS = (
    "CHEATHAPPENS",
    "CRIMSON DESERT",
    "CRIMSONDESERT",
    "SEARCHFORTRAINERS",
    "ACTIVATE TRAINER",
    "ACTIVATETRAINER",
    "SPECIAL INSTRUCTIONS",
    "SPECIALINSTRUCTIONS",
)


class UnsafeLoginSubmitError(RuntimeError):
    pass


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", INPUT_UNION),
    ]


@dataclass(frozen=True)
class OcrBox:
    text: str
    normalized: str
    left: float
    top: float
    right: float
    bottom: float

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0


def get_ocr_engine() -> RapidOCR:
    global OCR_ENGINE
    if OCR_ENGINE is None:
        OCR_ENGINE = RapidOCR()
    return OCR_ENGINE


def send_input(*inputs: INPUT) -> None:
    if not inputs:
        return
    array_type = INPUT * len(inputs)
    sent = user32.SendInput(len(inputs), array_type(*inputs), ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise ctypes.WinError(ctypes.get_last_error())


def keyboard_input(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0))


def key_down(vk: int) -> INPUT:
    return keyboard_input(vk=vk, flags=0)


def key_up(vk: int) -> INPUT:
    return keyboard_input(vk=vk, flags=KEYEVENTF_KEYUP)


def unicode_key(char: str) -> tuple[INPUT, INPUT]:
    code = ord(char)
    return (
        keyboard_input(scan=code, flags=KEYEVENTF_UNICODE),
        keyboard_input(scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
    )


def enum_windows_by_title(title: str) -> list[int]:
    matches: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        window_title = get_window_text(hwnd)
        if title.lower() in window_title.lower():
            rect = RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)) and rect.right > rect.left and rect.bottom > rect.top:
                matches.append(hwnd)
        return True

    if not user32.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return matches


def get_window_process_id(hwnd: int) -> int:
    process_id = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return int(process_id.value)


def enum_windows_by_pid(pid: int) -> list[int]:
    matches: list[tuple[int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        if get_window_process_id(hwnd) != pid:
            return True
        rect = RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)) and rect.right > rect.left and rect.bottom > rect.top:
            area = (rect.right - rect.left) * (rect.bottom - rect.top)
            matches.append((hwnd, area))
        return True

    if not user32.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    matches.sort(key=lambda item: item[1], reverse=True)
    return [hwnd for hwnd, _ in matches]


def load_pid_from_summary(summary_path: Path | None) -> int:
    if summary_path is None or not summary_path.exists():
        return 0
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    pid = payload.get("pid")
    if isinstance(pid, int) and pid > 0:
        return pid
    return 0


def resolve_hwnd(handle: int, title: str, pid: int = 0) -> int:
    if handle:
        return handle
    if pid:
        matches = enum_windows_by_pid(pid)
        if matches:
            return matches[0]
    matches = enum_windows_by_title(title)
    if not matches:
        if pid:
            raise RuntimeError(f"Could not find visible top-level window for process id {pid}")
        raise RuntimeError(f"Could not find visible top-level window containing title {title!r}")
    return matches[0]


def focus_window(hwnd: int) -> None:
    user32.ShowWindow(hwnd, SW_RESTORE)
    time.sleep(0.2)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.35)


def click_percent(hwnd: int, x_percent: float, y_percent: float) -> None:
    rect = get_window_rect(hwnd)
    x = int(rect.left + ((rect.right - rect.left) * x_percent))
    y = int(rect.top + ((rect.bottom - rect.top) * y_percent))
    click_absolute(x, y)


def click_absolute(x: int, y: int) -> None:
    user32.SetCursorPos(x, y)
    time.sleep(0.12)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.06)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.25)


def drag_absolute(start_x: int, start_y: int, end_x: int, end_y: int, *, steps: int = 8) -> None:
    user32.SetCursorPos(start_x, start_y)
    time.sleep(0.12)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    try:
        total_steps = max(2, steps)
        for step in range(1, total_steps + 1):
            progress = step / total_steps
            x = int(round(start_x + ((end_x - start_x) * progress)))
            y = int(round(start_y + ((end_y - start_y) * progress)))
            user32.SetCursorPos(x, y)
            time.sleep(0.03)
    finally:
        time.sleep(0.05)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.18)


def send_ctrl_a() -> None:
    send_input(key_down(VK_CONTROL), key_down(VK_A), key_up(VK_A), key_up(VK_CONTROL))
    time.sleep(0.08)


def send_ctrl_v() -> None:
    send_input(key_down(VK_CONTROL), key_down(VK_V), key_up(VK_V), key_up(VK_CONTROL))
    time.sleep(0.12)


def send_enter() -> None:
    send_input(key_down(VK_RETURN), key_up(VK_RETURN))
    time.sleep(0.12)


def send_tab() -> None:
    send_input(key_down(VK_TAB), key_up(VK_TAB))
    time.sleep(0.12)


def send_backspace(count: int = 1) -> None:
    for _ in range(max(1, count)):
        send_input(key_down(VK_BACK), key_up(VK_BACK))
        time.sleep(0.01)
    time.sleep(0.08)


def send_delete(count: int = 1) -> None:
    for _ in range(max(1, count)):
        send_input(key_down(VK_DELETE), key_up(VK_DELETE))
        time.sleep(0.01)
    time.sleep(0.08)


def send_home() -> None:
    send_input(key_down(VK_HOME), key_up(VK_HOME))
    time.sleep(0.08)


def send_end() -> None:
    send_input(key_down(VK_END), key_up(VK_END))
    time.sleep(0.08)


def send_text(text: str) -> None:
    for char in text:
        down, up = unicode_key(char)
        send_input(down, up)
        time.sleep(0.01)
    time.sleep(0.15)


def set_clipboard_text(text: str) -> None:
    payload = (text + "\x00").encode("utf-16-le")
    memory = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(payload))
    if not memory:
        raise ctypes.WinError(ctypes.get_last_error())

    locked = kernel32.GlobalLock(memory)
    if not locked:
        kernel32.GlobalFree(memory)
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        ctypes.memmove(locked, payload, len(payload))
    finally:
        kernel32.GlobalUnlock(memory)

    opened = False
    try:
        for _ in range(10):
            if user32.OpenClipboard(0):
                opened = True
                break
            time.sleep(0.05)
        if not opened:
            raise ctypes.WinError(ctypes.get_last_error())
        if not user32.EmptyClipboard():
            raise ctypes.WinError(ctypes.get_last_error())
        if not user32.SetClipboardData(CF_UNICODETEXT, memory):
            raise ctypes.WinError(ctypes.get_last_error())
        memory = None
    finally:
        if opened:
            user32.CloseClipboard()
        if memory:
            kernel32.GlobalFree(memory)


def enter_text(text: str) -> None:
    try:
        set_clipboard_text(text)
        send_ctrl_v()
    except Exception:
        send_text(text)


def clear_active_field(existing_length_hint: int = 0) -> None:
    clear_count = max(32, existing_length_hint + 8)
    send_ctrl_a()
    send_backspace(clear_count)
    send_delete(clear_count)
    send_end()
    send_backspace(clear_count)
    send_home()
    send_delete(clear_count)


def drag_select_box_text(hwnd: int, value_box: OcrBox | None) -> bool:
    if value_box is None:
        return False
    rect = get_window_rect(hwnd)
    window_width = max(1, rect.right - rect.left)
    width = max(12.0, value_box.right - value_box.left)
    y = int(rect.top + value_box.center_y)
    start_x_relative = min(window_width - 40.0, value_box.right + max(36.0, width * 0.85))
    end_x_relative = max(8.0, value_box.left + min(4.0, width * 0.08))
    start_x = int(rect.left + start_x_relative)
    end_x = int(rect.left + end_x_relative)
    if abs(start_x - end_x) < 6:
        return False
    drag_absolute(start_x, y, end_x, y)
    return True


def populate_login_fields(
    hwnd: int,
    username_label: OcrBox | None,
    password_label: OcrBox | None,
    username_value_box: OcrBox | None,
    password_value_box: OcrBox | None,
    username: str,
    password: str,
    *,
    direct_field_retry: bool,
    username_already_visible: bool,
    password_already_masked: bool,
) -> None:
    username_needs_fill = not username_already_visible
    password_needs_fill = not password_already_masked

    if not username_needs_fill and not password_needs_fill:
        return

    click_field_target(
        hwnd,
        username_value_box,
        username_label,
        fallback_x_percent=0.60,
        fallback_y_percent=0.41,
        y_gap=30,
    )
    if direct_field_retry:
        click_field_target(
            hwnd,
            username_value_box,
            username_label,
            fallback_x_percent=0.60,
            fallback_y_percent=0.41,
            y_gap=30,
        )
    time.sleep(0.2 if direct_field_retry else 0.12)

    if username_needs_fill:
        drag_select_box_text(hwnd, username_value_box)
        clear_active_field(len(username))
        send_text(username)

    if not password_needs_fill:
        return

    send_tab()
    time.sleep(0.18 if direct_field_retry else 0.12)

    drag_select_box_text(hwnd, password_value_box)
    clear_active_field(len(password))
    send_text(password)


def capture_window(hwnd: int, output: Path) -> Path:
    rect = get_window_rect(hwnd)
    width = max(1, rect.right - rect.left)
    height = max(1, rect.bottom - rect.top)
    output.parent.mkdir(parents=True, exist_ok=True)
    image = capture_with_printwindow(hwnd, width, height, client_only=False)
    image.save(output)

    printwindow_inspection = inspect_image(output)
    screen_output = output.with_name(f"{output.stem}-screen{output.suffix}")
    screen_image = capture_with_screen_grab(rect)
    screen_image.save(screen_output)
    screen_inspection = inspect_image(screen_output)

    if should_prefer_screen_capture(printwindow_inspection, screen_inspection):
        screen_image.save(output)
    return output


def state_priority(inspection: dict | None) -> int:
    if not inspection:
        return 0
    state = str(inspection.get("state") or "unknown")
    priorities = {
        "unknown": 0,
        "splash": 1,
        "loading": 2,
        "login-screen": 3,
        "error": 3,
    }
    return priorities.get(state, 0)


def should_prefer_screen_capture(
    printwindow_inspection: dict | None,
    screen_inspection: dict | None,
) -> bool:
    if not screen_inspection:
        return False
    if has_marker(screen_inspection, *FOREIGN_OVERLAY_MARKERS):
        return False
    if not printwindow_inspection:
        return True

    print_priority = state_priority(printwindow_inspection)
    screen_priority = state_priority(screen_inspection)
    if screen_priority > print_priority:
        return True

    print_texts = normalized_texts(printwindow_inspection)
    screen_texts = normalized_texts(screen_inspection)
    if not looks_like_runtek_surface(screen_inspection):
        return False
    if len(screen_texts) >= len(print_texts) + 2 and screen_priority >= print_priority:
        return True

    screen_has_strong_ui = has_marker(
        screen_inspection,
        "USERNAME",
        "PASSWORD",
        "LOG IN",
        "LOGIN",
        "SIGNING IN",
        "ABORT LOGIN",
        "INVALID LOGIN OR PASSWORD",
        "GRAPHICS DRIVERS",
        "GRAPHICSDRIVERS",
        "UPDATE",
        "IGNORE",
    )
    print_has_strong_ui = has_marker(
        printwindow_inspection,
        "USERNAME",
        "PASSWORD",
        "LOG IN",
        "LOGIN",
        "SIGNING IN",
        "ABORT LOGIN",
        "INVALID LOGIN OR PASSWORD",
        "GRAPHICS DRIVERS",
        "GRAPHICSDRIVERS",
        "UPDATE",
        "IGNORE",
    )
    return screen_has_strong_ui and not print_has_strong_ui


def looks_like_runtek_surface(inspection: dict | None) -> bool:
    if not inspection:
        return False
    if has_marker(inspection, *FOREIGN_OVERLAY_MARKERS):
        return False
    return has_marker(
        inspection,
        "RUNESCAPE",
        "RUNETEKAPP",
        "USERNAME",
        "PASSWORD",
        "LOG IN",
        "LOGIN",
        "SIGNING IN",
        "ABORT LOGIN",
        "INVALID LOGIN OR PASSWORD",
        "GRAPHICS DRIVERS",
        "GRAPHICSDRIVERS",
        "LOADING",
    )


def load_ocr_boxes(image_path: Path) -> list[OcrBox]:
    engine = get_ocr_engine()
    result, _ = engine(str(image_path))
    boxes: list[OcrBox] = []
    if not result:
        return boxes
    for item in result:
        if len(item) < 3:
            continue
        polygon = item[0]
        text = str(item[1] or "").strip()
        if not polygon or not text:
            continue
        xs = [float(point[0]) for point in polygon]
        ys = [float(point[1]) for point in polygon]
        boxes.append(
            OcrBox(
                text=text,
                normalized=normalize_text(text),
                left=min(xs),
                top=min(ys),
                right=max(xs),
                bottom=max(ys),
            )
        )
    return boxes


def find_box(boxes: list[OcrBox], *markers: str) -> OcrBox | None:
    normalized_markers = [normalize_text(marker) for marker in markers if marker]
    for box in boxes:
        for marker in normalized_markers:
            if not marker:
                continue
            if box.normalized == marker or marker in box.normalized:
                return box
    return None


def find_box_exact(boxes: list[OcrBox], *markers: str) -> OcrBox | None:
    normalized_markers = {normalize_text(marker) for marker in markers if marker}
    for box in boxes:
        if box.normalized in normalized_markers:
            return box
    return None


def click_box_target(hwnd: int, box: OcrBox, y_offset: int = 0) -> None:
    rect = get_window_rect(hwnd)
    x = int(rect.left + box.center_x)
    y = int(rect.top + box.center_y + y_offset)
    click_absolute(x, y)


def click_field_below_label(
    hwnd: int,
    label_box: OcrBox | None,
    *,
    fallback_x_percent: float,
    fallback_y_percent: float,
    y_gap: int,
) -> None:
    if label_box is None:
        click_percent(hwnd, fallback_x_percent, fallback_y_percent)
        return
    rect = get_window_rect(hwnd)
    label_width = max(1.0, label_box.right - label_box.left)
    x = int(rect.left + label_box.left + min(36.0, max(18.0, label_width * 0.18)))
    y = int(rect.top + label_box.bottom + max(18, y_gap - 12))
    click_absolute(x, y)


def find_field_value_box(
    boxes: list[OcrBox],
    label_box: OcrBox | None,
    next_label_box: OcrBox | None = None,
) -> OcrBox | None:
    if label_box is None:
        return None
    excluded = {
        "RECOVERACCOUNT",
        "REMEMBER",
        "HIDE",
        "LOG IN",
        "LOGIN",
        "ORLOGIN WITH",
        "ORLOGINWITH",
        "CREATEFREEACCOUNT",
        "USERNAME EMAIL",
        "PASSWORD",
    }
    upper_top = label_box.bottom + 4
    lower_bottom = (next_label_box.top - 8) if next_label_box is not None else (label_box.bottom + 72)
    candidates = [
        box
        for box in boxes
        if box.normalized
        and box.normalized not in excluded
        and box.top >= upper_top
        and box.bottom <= lower_bottom
        and box.left >= label_box.left - 12
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda box: (box.top, box.left))
    return candidates[0]


def click_field_target(
    hwnd: int,
    value_box: OcrBox | None,
    label_box: OcrBox | None,
    *,
    fallback_x_percent: float,
    fallback_y_percent: float,
    y_gap: int,
) -> None:
    if value_box is not None:
        rect = get_window_rect(hwnd)
        window_width = max(1, rect.right - rect.left)
        preferred_relative = max(
            value_box.right + 36.0,
            window_width * fallback_x_percent,
        )
        x = int(rect.left + min(window_width - 40.0, preferred_relative))
        y = int(rect.top + value_box.center_y)
        click_absolute(x, y)
        return
    click_field_below_label(
        hwnd,
        label_box,
        fallback_x_percent=fallback_x_percent,
        fallback_y_percent=fallback_y_percent,
        y_gap=y_gap,
    )


def is_login_screen_ready(inspection: dict | None) -> bool:
    if not inspection:
        return False
    if str(inspection.get("state") or "unknown") != "login-screen":
        return False
    return has_marker(inspection, "USERNAME", "PASSWORD", "LOG IN", "LOGIN")


def resolve_safe_login_button(boxes: list[OcrBox]) -> OcrBox | None:
    password_label = find_box(boxes, "PASSWORD")
    social_login = find_box(boxes, "OR LOGIN WITH", "ORLOGINWITH", "OR LOGINWITH")
    create_account = find_box(boxes, "CREATE FREE ACCOUNT", "CREATEFREEACCOUNT")

    candidates: list[OcrBox] = []
    for candidate in (
        find_box_exact(boxes, "LOG IN", "LOGIN"),
        find_box(boxes, "LOG IN", "LOGIN"),
    ):
        if candidate is not None and candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        normalized = candidate.normalized
        if normalized not in {"LOG IN", "LOGIN"} and "LOGIN" not in normalized:
            continue
        if password_label is not None and candidate.top <= password_label.bottom + 32:
            continue
        if social_login is not None and candidate.bottom > social_login.top - 4:
            continue
        if create_account is not None and candidate.bottom >= create_account.top - SAFE_LOGIN_BUTTON_GAP_PX:
            continue
        return candidate
    return None


def wait_for_login_screen(
    hwnd: int,
    capture_dir: Path,
    attempt: int,
    settle_delay_seconds: int,
    login_screen_timeout_seconds: int,
    initial_path: Path,
    initial_inspection: dict | None,
) -> tuple[Path, dict | None]:
    before_path = initial_path
    before_inspection = initial_inspection
    deadline = time.time() + max(0, login_screen_timeout_seconds)
    wait_index = 0

    while not is_login_screen_ready(before_inspection):
        if has_bad_session_id_response(before_inspection) or has_restart_required_response(before_inspection):
            return before_path, before_inspection
        if time.time() >= deadline:
            return before_path, before_inspection
        time.sleep(max(1, settle_delay_seconds))
        wait_index += 1
        before_path = capture_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-attempt{attempt:02d}-wait-login-{wait_index:02d}.png"
        capture_window(hwnd, before_path)
        before_inspection = inspect_image(before_path)
        if has_marker(before_inspection, "GRAPHICSDRIVERS", "GRAPHICS DRIVERS", "UPDATE", "IGNORE"):
            dismiss_graphics_dialog(hwnd)
            time.sleep(max(1, settle_delay_seconds))
            before_path = capture_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-attempt{attempt:02d}-after-graphics-dismiss.png"
            capture_window(hwnd, before_path)
            before_inspection = inspect_image(before_path)
        if has_invalid_login_response(before_inspection):
            dismiss_invalid_login(hwnd)
            time.sleep(max(1, settle_delay_seconds))
            before_path = capture_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-attempt{attempt:02d}-after-error-dismiss.png"
            capture_window(hwnd, before_path)
            before_inspection = inspect_image(before_path)
    return before_path, before_inspection


def normalized_texts(inspection: dict | None) -> list[str]:
    if not inspection:
        return []
    texts = inspection.get("detectedTexts") or []
    return [str(item.get("normalized") or "") for item in texts if item]


def raw_texts(inspection: dict | None) -> list[str]:
    if not inspection:
        return []
    texts = inspection.get("detectedTexts") or []
    return [str(item.get("text") or "") for item in texts if item]


def has_marker(inspection: dict | None, *markers: str) -> bool:
    texts = normalized_texts(inspection)
    combined = " | ".join(texts)
    for marker in markers:
        if marker in texts or marker in combined:
            return True
    return False


def has_visible_username(inspection: dict | None, username: str) -> bool:
    target = normalize_text(username)
    if not target:
        return False
    texts = normalized_texts(inspection)
    combined = " | ".join(texts)
    return target in texts or target in combined


def has_password_mask(inspection: dict | None) -> bool:
    for value in raw_texts(inspection):
        stripped = value.strip()
        if len(stripped) >= 3 and set(stripped) <= {"*", "\u2022", "\u25cf"}:
            return True
    return False


def has_invalid_login_response(inspection: dict | None) -> bool:
    texts = normalized_texts(inspection)
    combined = " | ".join(texts)
    return (
        "INVALID LOGIN OR PASSWORD" in combined
        or "INVALID LOGIN ORPASSWORD" in combined
        or ("INVALID LOGIN" in combined and "PASSWORD" in combined)
    )


def has_bad_session_id_response(inspection: dict | None) -> bool:
    return has_marker(inspection, "BAD SESSION ID", "UNABLE TO CONNECT BAD SESSION ID")


def has_restart_required_response(inspection: dict | None) -> bool:
    return has_marker(
        inspection,
        "RUNESCAPE HAS BEEN UPDATED",
        "PLEASE RESTART THE GAME TO RETRY",
    )


def artifact_snapshot(root: Path) -> dict:
    bootstrap = root / "data" / "debug" / "world-bootstrap-packets.jsonl"
    transport = root / "data" / "debug" / "prelogin-transport-events.jsonl"
    return {
        "bootstrapExists": bootstrap.exists(),
        "bootstrapLength": bootstrap.stat().st_size if bootstrap.exists() else 0,
        "bootstrapMtime": bootstrap.stat().st_mtime if bootstrap.exists() else 0.0,
        "transportExists": transport.exists(),
        "transportLength": transport.stat().st_size if transport.exists() else 0,
        "transportMtime": transport.stat().st_mtime if transport.exists() else 0.0,
    }


def bootstrap_advanced(before: dict, after: dict) -> bool:
    if not after.get("bootstrapExists"):
        return False
    if not before.get("bootstrapExists"):
        return True
    return int(after.get("bootstrapLength", 0)) > int(before.get("bootstrapLength", 0))


def dismiss_graphics_dialog(hwnd: int) -> None:
    click_percent(hwnd, 0.45, 0.85)
    click_percent(hwnd, 0.72, 0.92)


def dismiss_invalid_login(hwnd: int) -> None:
    click_percent(hwnd, 0.677, 0.314)


def submit_login(
    hwnd: int,
    username: str,
    password: str,
    pre_click_delay_ms: int,
    *,
    ocr_boxes: list[OcrBox],
    capture_dir: Path,
    attempt: int,
    username_already_visible: bool,
    password_already_masked: bool,
) -> tuple[Path, dict, bool, bool]:
    username_label = find_box(ocr_boxes, "USERNAME/EMAIL", "USERNAME EMAIL", "USERNAME")
    password_label = find_box(ocr_boxes, "PASSWORD")
    login_button = resolve_safe_login_button(ocr_boxes)
    username_value_box = find_field_value_box(ocr_boxes, username_label, password_label)
    password_value_box = find_field_value_box(ocr_boxes, password_label, login_button)
    if login_button is None:
        raise UnsafeLoginSubmitError("Refusing to submit because a safe LOG IN button could not be resolved.")

    time.sleep(max(0, pre_click_delay_ms) / 1000.0)
    populate_login_fields(
        hwnd,
        username_label,
        password_label,
        username_value_box,
        password_value_box,
        username,
        password,
        direct_field_retry=False,
        username_already_visible=username_already_visible,
        password_already_masked=password_already_masked,
    )
    pre_submit_path = capture_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-attempt{attempt:02d}-pre-submit.png"
    capture_window(hwnd, pre_submit_path)
    pre_submit_inspection = inspect_image(pre_submit_path)
    pre_submit_username_visible = has_visible_username(pre_submit_inspection, username)
    pre_submit_password_masked = has_password_mask(pre_submit_inspection)
    if not pre_submit_username_visible or not pre_submit_password_masked:
        focus_window(hwnd)
        retry_boxes = load_ocr_boxes(pre_submit_path)
        retry_username_label = find_box(retry_boxes, "USERNAME/EMAIL", "USERNAME EMAIL", "USERNAME")
        retry_password_label = find_box(retry_boxes, "PASSWORD")
        retry_login_button = resolve_safe_login_button(retry_boxes)
        retry_username_value_box = find_field_value_box(retry_boxes, retry_username_label, retry_password_label)
        retry_password_value_box = find_field_value_box(retry_boxes, retry_password_label, retry_login_button)
        populate_login_fields(
            hwnd,
            retry_username_label,
            retry_password_label,
            retry_username_value_box,
            retry_password_value_box,
            username,
            password,
            direct_field_retry=True,
            username_already_visible=pre_submit_username_visible,
            password_already_masked=pre_submit_password_masked,
        )
        capture_window(hwnd, pre_submit_path)
        pre_submit_inspection = inspect_image(pre_submit_path)
        pre_submit_username_visible = has_visible_username(pre_submit_inspection, username)
        pre_submit_password_masked = has_password_mask(pre_submit_inspection)
    if login_button is not None:
        click_box_target(hwnd, login_button)
    send_enter()
    send_enter()
    send_enter()
    return (
        pre_submit_path,
        pre_submit_inspection,
        pre_submit_username_visible,
        pre_submit_password_masked,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repeatedly submit RuneTek login credentials until bootstrap progress or repeated auth rejection.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--window-title", default="RuneTekApp")
    parser.add_argument("--handle", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--attempt-wait-seconds", type=int, default=18)
    parser.add_argument("--settle-delay-seconds", type=int, default=2)
    parser.add_argument("--pre-click-delay-ms", type=int, default=500)
    parser.add_argument("--login-screen-timeout-seconds", type=int, default=20)
    parser.add_argument("--stop-on-repeated-invalid", action="store_true")
    parser.add_argument(
        "--capture-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "debug" / "runtek-automation",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "debug" / "runtek-automation" / "latest-login-loop.json",
    )
    parser.add_argument(
        "--direct-patch-summary",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "debug" / "direct-rs2client-patch" / "latest-client-only.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    resolved_pid = args.pid or load_pid_from_summary(args.direct_patch_summary)
    hwnd = resolve_hwnd(args.handle, args.window_title, resolved_pid)

    results: list[dict] = []
    invalid_count = 0
    success = False
    stop_reason = "max-attempts-reached"

    for attempt in range(1, max(1, args.max_attempts) + 1):
        focus_window(hwnd)
        before_artifacts = artifact_snapshot(root)
        before_path = args.capture_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-attempt{attempt:02d}-before.png"
        capture_window(hwnd, before_path)
        before_inspection = inspect_image(before_path)

        if has_marker(before_inspection, "GRAPHICSDRIVERS", "GRAPHICS DRIVERS", "UPDATE", "IGNORE"):
            dismiss_graphics_dialog(hwnd)
            time.sleep(max(0, args.settle_delay_seconds))
            before_path = args.capture_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-attempt{attempt:02d}-after-graphics-dismiss.png"
            capture_window(hwnd, before_path)
            before_inspection = inspect_image(before_path)

        if has_invalid_login_response(before_inspection):
            dismiss_invalid_login(hwnd)
            time.sleep(max(0, args.settle_delay_seconds))
            before_path = args.capture_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-attempt{attempt:02d}-after-error-dismiss.png"
            capture_window(hwnd, before_path)
            before_inspection = inspect_image(before_path)

        before_path, before_inspection = wait_for_login_screen(
            hwnd,
            args.capture_dir,
            attempt,
            args.settle_delay_seconds,
            args.login_screen_timeout_seconds,
            before_path,
            before_inspection,
        )
        if not is_login_screen_ready(before_inspection):
            submit_error = "login-screen-not-ready"
            stop_reason = "login-screen-not-ready"
            if has_restart_required_response(before_inspection):
                submit_error = "restart-required"
                stop_reason = "restart-required"
            elif has_bad_session_id_response(before_inspection):
                submit_error = "bad-session-id"
                stop_reason = "bad-session-id"
            attempt_result = {
                "attempt": attempt,
                "beforeImage": str(before_path),
                "beforeState": before_inspection.get("state") if before_inspection else "unknown",
                "beforeUsernameVisible": False,
                "beforePasswordMasked": False,
                "preSubmitImage": None,
                "preSubmitState": None,
                "preSubmitUsernameVisible": False,
                "preSubmitPasswordMasked": False,
                "afterImage": str(before_path),
                "afterState": before_inspection.get("state") if before_inspection else "unknown",
                "afterTexts": normalized_texts(before_inspection),
                "bootstrapAdvanced": False,
                "beforeArtifacts": before_artifacts,
                "afterArtifacts": before_artifacts,
                "submitError": submit_error,
            }
            results.append(attempt_result)
            break

        username_visible = has_visible_username(before_inspection, args.username)
        password_masked = has_password_mask(before_inspection)
        try:
            (
                pre_submit_path,
                pre_submit_inspection,
                pre_submit_username_visible,
                pre_submit_password_masked,
            ) = submit_login(
                hwnd,
                args.username,
                args.password,
                args.pre_click_delay_ms,
                ocr_boxes=load_ocr_boxes(before_path),
                capture_dir=args.capture_dir,
                attempt=attempt,
                username_already_visible=username_visible,
                password_already_masked=password_masked,
            )
        except UnsafeLoginSubmitError as exc:
            attempt_result = {
                "attempt": attempt,
                "beforeImage": str(before_path),
                "beforeState": before_inspection.get("state") if before_inspection else "unknown",
                "beforeUsernameVisible": username_visible,
                "beforePasswordMasked": password_masked,
                "preSubmitImage": None,
                "preSubmitState": None,
                "preSubmitUsernameVisible": False,
                "preSubmitPasswordMasked": False,
                "afterImage": str(before_path),
                "afterState": before_inspection.get("state") if before_inspection else "unknown",
                "afterTexts": normalized_texts(before_inspection),
                "bootstrapAdvanced": False,
                "beforeArtifacts": before_artifacts,
                "afterArtifacts": before_artifacts,
                "submitError": str(exc),
            }
            results.append(attempt_result)
            stop_reason = "unsafe-submit"
            break
        time.sleep(max(0, args.attempt_wait_seconds))

        focus_window(hwnd)
        after_artifacts = artifact_snapshot(root)
        after_path = args.capture_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-attempt{attempt:02d}-after.png"
        capture_window(hwnd, after_path)
        after_inspection = inspect_image(after_path)
        after_state = str(after_inspection.get("state") or "unknown")
        after_texts = normalized_texts(after_inspection)
        observed_bootstrap = bootstrap_advanced(before_artifacts, after_artifacts)

        attempt_result = {
            "attempt": attempt,
            "beforeImage": str(before_path),
            "beforeState": before_inspection.get("state") if before_inspection else "unknown",
            "beforeUsernameVisible": username_visible,
            "beforePasswordMasked": password_masked,
            "preSubmitImage": str(pre_submit_path),
            "preSubmitState": pre_submit_inspection.get("state") if pre_submit_inspection else "unknown",
            "preSubmitUsernameVisible": pre_submit_username_visible,
            "preSubmitPasswordMasked": pre_submit_password_masked,
            "afterImage": str(after_path),
            "afterState": after_state,
            "afterTexts": after_texts,
            "bootstrapAdvanced": observed_bootstrap,
            "beforeArtifacts": before_artifacts,
            "afterArtifacts": after_artifacts,
        }
        results.append(attempt_result)

        if observed_bootstrap or after_state == "loading":
            success = True
            stop_reason = "world-bootstrap-observed" if observed_bootstrap else "loading-after-submit"
            break

        if has_invalid_login_response(after_inspection):
            invalid_count += 1
            stop_reason = "invalid-login"
            break

        if after_state == "error":
            stop_reason = "client-error"
            break

    rect = get_window_rect(hwnd)
    summary = {
        "windowHandle": hwnd,
        "windowTitle": get_window_text(hwnd),
        "windowPid": get_window_process_id(hwnd),
        "requestedPid": args.pid,
        "resolvedPid": resolved_pid,
        "success": success,
        "stopReason": stop_reason,
        "attemptCount": len(results),
        "username": args.username,
        "bounds": {
            "left": rect.left,
            "top": rect.top,
            "right": rect.right,
            "bottom": rect.bottom,
        },
        "attempts": results,
    }
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
