from __future__ import annotations

import argparse
import ctypes
import json
import re
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from rapidocr_onnxruntime import RapidOCR

from capture_window import RECT, SW_RESTORE, capture_with_printwindow, get_window_rect, get_window_text, user32
from inspect_runescape_screenshot import normalize_text


OCR_ENGINE: RapidOCR | None = None
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
SWP_NOZORDER = 0x0004
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2


@dataclass(frozen=True)
class DetectedBox:
    text: str
    normalized: str
    confidence: float
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center_x(self) -> int:
        return (self.left + self.right) // 2

    @property
    def center_y(self) -> int:
        return (self.top + self.bottom) // 2


def get_ocr_engine() -> RapidOCR:
    global OCR_ENGINE
    if OCR_ENGINE is None:
        OCR_ENGINE = RapidOCR()
    return OCR_ENGINE


def load_detected_boxes(image_path: Path) -> list[DetectedBox]:
    engine = get_ocr_engine()
    result, _ = engine(str(image_path))
    if not result:
        return []

    detected: list[DetectedBox] = []
    for item in result:
        if len(item) < 3:
            continue
        text = str(item[1] or "").strip()
        if not text:
            continue
        points = item[0] or []
        if not points:
            continue
        xs = [int(round(point[0])) for point in points]
        ys = [int(round(point[1])) for point in points]
        detected.append(
            DetectedBox(
                text=text,
                normalized=normalize_text(text),
                confidence=float(item[2] or 0.0),
                left=min(xs),
                top=min(ys),
                right=max(xs),
                bottom=max(ys),
            )
        )
    return detected


def enum_windows_by_title(title: str) -> list[int]:
    matches: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        window_title = get_window_text(hwnd)
        if title.lower() not in window_title.lower():
            return True
        rect = RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)) and rect.right > rect.left and rect.bottom > rect.top:
            matches.append(hwnd)
        return True

    if not user32.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return matches


def resolve_hwnd(handle: int, title: str) -> int:
    if handle:
        return handle
    matches = enum_windows_by_title(title)
    if not matches:
        raise RuntimeError(f"Could not find visible top-level window containing title {title!r}")
    return matches[0]


def focus_window(hwnd: int) -> None:
    user32.ShowWindow(hwnd, SW_RESTORE)
    time.sleep(0.2)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.35)


def ensure_window_size(hwnd: int, min_width: int, min_height: int) -> None:
    rect = get_window_rect(hwnd)
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width >= min_width and height >= min_height:
        return
    user32.SetWindowPos(hwnd, 0, max(40, rect.left), max(40, rect.top), min_width, min_height, SWP_NOZORDER)
    time.sleep(0.8)


def capture_window(hwnd: int, output: Path) -> Path:
    rect = get_window_rect(hwnd)
    width = max(1, rect.right - rect.left)
    height = max(1, rect.bottom - rect.top)
    image = capture_with_printwindow(hwnd, width, height, client_only=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return output


def click_window_point(hwnd: int, x: int, y: int) -> None:
    rect = get_window_rect(hwnd)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    time.sleep(0.15)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    user32.SetCursorPos(rect.left + x, rect.top + y)
    time.sleep(0.12)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.35)
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)


def find_best_box(
    boxes: list[DetectedBox],
    *,
    texts: tuple[str, ...] = (),
    regex: str | None = None,
    min_y_ratio: float | None = None,
    max_y_ratio: float | None = None,
    image_height: int | None = None,
) -> DetectedBox | None:
    candidates: list[DetectedBox] = []
    compiled = re.compile(regex) if regex else None
    for box in boxes:
        if min_y_ratio is not None and image_height is not None and box.center_y < int(image_height * min_y_ratio):
            continue
        if max_y_ratio is not None and image_height is not None and box.center_y > int(image_height * max_y_ratio):
            continue
        if texts and box.normalized in texts:
            candidates.append(box)
            continue
        if compiled and (compiled.search(box.text) or compiled.search(box.normalized)):
            candidates.append(box)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item.center_y, item.confidence), reverse=True)[0]


def parse_cache_status(boxes: list[DetectedBox]) -> dict | None:
    for box in boxes:
        lowered = box.text.lower().replace(" ", "")
        if "preparingcache" not in lowered:
            continue
        match = re.search(r"(\d{1,3})%.*?(\d+)mb/?(\d+)mb", lowered)
        speed_match = re.search(r"\((\d+)kb/s\)", lowered)
        payload = {"text": box.text}
        if match:
            payload["percent"] = int(match.group(1))
            payload["downloadedMb"] = int(match.group(2))
            payload["totalMb"] = int(match.group(3))
        if speed_match:
            payload["speedKbPerSec"] = int(speed_match.group(1))
        return payload
    return None


def parse_world_label(boxes: list[DetectedBox], image_height: int) -> str | None:
    box = find_best_box(boxes, regex=r"WORLD\s*\d+", min_y_ratio=0.70, image_height=image_height)
    if not box:
        return None
    return box.text.replace(" ", "")


def has_lobby_marker(boxes: list[DetectedBox]) -> bool:
    return any(box.normalized == "LOBBY" for box in boxes)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Drive the authenticated RuneScape lobby until it leaves the lobby and enters world/loading.")
    parser.add_argument("--window-title", default="RuneScape")
    parser.add_argument("--handle", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--min-width", type=int, default=1280)
    parser.add_argument("--min-height", type=int, default=900)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--click-cooldown-seconds", type=int, default=30)
    parser.add_argument("--max-seconds", type=int, default=7200)
    parser.add_argument(
        "--capture-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "debug" / "authenticated-world-entry",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "debug" / "authenticated-world-entry" / "latest-summary.json",
    )
    parser.add_argument(
        "--jsonl-output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "debug" / "authenticated-world-entry" / "latest-world-entry.jsonl",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = time.time()
    last_click_at = 0.0
    latest_summary: dict[str, object] = {}
    args.capture_dir.mkdir(parents=True, exist_ok=True)
    args.jsonl_output.parent.mkdir(parents=True, exist_ok=True)

    while True:
        if time.time() - started_at > max(1, args.max_seconds):
            latest_summary["success"] = False
            latest_summary["stopReason"] = "timeout"
            break

        hwnd = resolve_hwnd(args.handle, args.window_title)
        focus_window(hwnd)
        ensure_window_size(hwnd, args.min_width, args.min_height)

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        capture_path = args.capture_dir / f"{timestamp}.png"
        capture_window(hwnd, capture_path)
        rect = get_window_rect(hwnd)
        image_width = rect.right - rect.left
        image_height = rect.bottom - rect.top
        boxes = load_detected_boxes(capture_path)
        lobby_present = has_lobby_marker(boxes)
        cache_status = parse_cache_status(boxes)
        world_label = parse_world_label(boxes, image_height)
        bottom_play = find_best_box(
            boxes,
            texts=("PLAY NOW", "PLAYNOW"),
            min_y_ratio=0.70,
            image_height=image_height,
        )

        iteration = {
            "timestamp": timestamp,
            "image": str(capture_path),
            "windowHandle": hwnd,
            "windowTitle": get_window_text(hwnd),
            "bounds": {
                "left": rect.left,
                "top": rect.top,
                "right": rect.right,
                "bottom": rect.bottom,
            },
            "lobbyPresent": lobby_present,
            "cacheStatus": cache_status,
            "worldLabel": world_label,
            "bottomPlayNow": {
                "text": bottom_play.text,
                "left": bottom_play.left,
                "top": bottom_play.top,
                "right": bottom_play.right,
                "bottom": bottom_play.bottom,
            }
            if bottom_play
            else None,
        }
        with args.jsonl_output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(iteration) + "\n")

        latest_summary = {
            "success": False,
            "stopReason": "monitoring",
            "lastIteration": iteration,
        }

        if not lobby_present:
            latest_summary["success"] = True
            latest_summary["stopReason"] = "lobby-disappeared"
            break

        now = time.time()
        if bottom_play and (now - last_click_at) >= max(1, args.click_cooldown_seconds):
            click_window_point(hwnd, bottom_play.center_x, bottom_play.center_y)
            last_click_at = now
            latest_summary["lastIteration"]["clickedBottomPlayNow"] = True
        else:
            latest_summary["lastIteration"]["clickedBottomPlayNow"] = False

        args.summary_output.write_text(json.dumps(latest_summary, indent=2), encoding="utf-8")
        time.sleep(max(1, args.poll_seconds))

    args.summary_output.write_text(json.dumps(latest_summary, indent=2), encoding="utf-8")
    print(json.dumps(latest_summary, indent=2))
    return 0 if bool(latest_summary.get("success")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
