from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image

with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:  # pragma: no cover - machine-specific native import failures
        RapidOCR = None  # type: ignore[assignment]


OCR_ENGINE: RapidOCR | None = None


@dataclass(frozen=True)
class DetectedText:
    text: str
    confidence: float


def get_ocr_engine() -> RapidOCR:
    global OCR_ENGINE
    if RapidOCR is None:
        raise RuntimeError("RapidOCR is unavailable on this machine")
    if OCR_ENGINE is None:
        OCR_ENGINE = RapidOCR()
    return OCR_ENGINE


def normalize_text(value: str) -> str:
    value = value.upper()
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def load_detected_texts(image_path: Path) -> list[DetectedText]:
    try:
        engine = get_ocr_engine()
        result, _ = engine(str(image_path))
    except Exception:
        return []
    if not result:
        return []
    detected: list[DetectedText] = []
    for item in result:
        if len(item) < 3:
            continue
        text = str(item[1] or "").strip()
        if not text:
            continue
        confidence = float(item[2] or 0.0)
        detected.append(DetectedText(text=text, confidence=confidence))
    return detected


def estimate_progress_ratio(image_path: Path) -> float | None:
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    pixels = image.load()

    def measure_region(
        top_ratio: float,
        bottom_ratio: float,
        left_ratio: float = 0.12,
        right_ratio: float = 0.88,
    ) -> float | None:
        bar_top = int(height * top_ratio)
        bar_bottom = int(height * bottom_ratio)
        bar_left = int(width * left_ratio)
        bar_right = int(width * right_ratio)
        if bar_bottom <= bar_top or bar_right <= bar_left:
            return None

        orange_columns = 0
        total_columns = bar_right - bar_left
        if total_columns <= 0:
            return None

        for x in range(bar_left, bar_right):
            orange_hits = 0
            samples = 0
            for y in range(bar_top, bar_bottom):
                r, g, b = pixels[x, y]
                samples += 1
                if r >= 180 and 70 <= g <= 220 and b <= 120:
                    orange_hits += 1
            if samples and orange_hits / samples >= 0.06:
                orange_columns += 1

        if orange_columns == 0:
            return 0.0
        return orange_columns / total_columns

    candidates = [
        measure_region(0.50, 0.68),
        measure_region(0.76, 0.94),
        measure_region(0.80, 0.96, left_ratio=0.10, right_ratio=0.90),
    ]
    measured = [candidate for candidate in candidates if candidate is not None]
    if not measured:
        return None
    return round(max(measured), 4)


def estimate_visual_signals(image_path: Path) -> dict[str, float]:
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    pixels = image.load()

    regions = {
        "loginButtonYellowRatio": (0.49, 0.62, 0.76, 0.73),
        "createButtonBlueRatio": (0.46, 0.89, 0.82, 0.98),
        "cardDarkRatio": (0.44, 0.20, 0.82, 0.89),
    }

    metrics: dict[str, float] = {}
    for key, (left_ratio, top_ratio, right_ratio, bottom_ratio) in regions.items():
        left = int(width * left_ratio)
        top = int(height * top_ratio)
        right = int(width * right_ratio)
        bottom = int(height * bottom_ratio)
        total = max(1, (right - left) * (bottom - top))
        matched = 0
        for y in range(top, bottom):
            for x in range(left, right):
                red, green, blue = pixels[x, y]
                avg = (red + green + blue) / 3.0
                if key == "loginButtonYellowRatio":
                    if red >= 170 and green >= 110 and blue <= 120:
                        matched += 1
                elif key == "createButtonBlueRatio":
                    if blue >= 120 and green >= 120 and red <= 180:
                        matched += 1
                elif key == "cardDarkRatio":
                    if avg <= 90:
                        matched += 1
        metrics[key] = round(matched / total, 4)
    return metrics


def classify_state(
    detected_texts: Iterable[DetectedText],
    progress_ratio: float | None,
    visual_signals: dict[str, float] | None = None,
) -> str:
    normalized = [normalize_text(item.text) for item in detected_texts]
    combined = " | ".join(text for text in normalized if text)

    error_markers = (
        "INVALID LOGIN OR PASSWORD",
        "SORRY WE HAD TROUBLE LOGGING YOU IN",
        "THE RUNESCAPE CLIENT SUFFERED FROM AN ERROR",
        "UNABLE TO CONNECT BAD SESSION ID",
        "BAD SESSION ID",
        "RUNESCAPE HAS BEEN UPDATED",
        "PLEASE RESTART THE GAME TO RETRY",
        "PLEASE TRY AGAIN",
    )
    login_markers = (
        "USERNAME",
        "PASSWORD",
        "LOG IN",
        "LOGIN",
        "FORGOTTEN YOUR PASSWORD",
        "NEW USER",
        "EXISTING USER",
    )
    loading_markers = (
        "LOADING APPLICATION RESOURCES",
        "LOADING APPLICATION",
        "LOADING CONFIGURATION",
        "LOADING",
    )

    if any(marker in combined for marker in error_markers):
        return "error"
    if any(marker in combined for marker in login_markers):
        return "login-screen"
    if any(marker in combined for marker in loading_markers):
        return "loading"

    login_button_yellow = 0.0
    create_button_blue = 0.0
    card_dark = 0.0
    if visual_signals:
        login_button_yellow = float(visual_signals.get("loginButtonYellowRatio", 0.0))
        create_button_blue = float(visual_signals.get("createButtonBlueRatio", 0.0))
        card_dark = float(visual_signals.get("cardDarkRatio", 0.0))
        if login_button_yellow >= 0.18 and create_button_blue >= 0.35 and card_dark >= 0.55:
            return "login-screen"

    if "RUNETEKAPP" in combined or "RUNESCAPE" in combined:
        if progress_ratio is not None and progress_ratio > 0.0:
            return "loading"
        return "splash"

    if progress_ratio is not None and progress_ratio >= 0.08:
        return "loading"

    if card_dark >= 0.55 and login_button_yellow >= 0.18:
        return "login-screen"

    return "unknown"


def inspect_image(image_path: Path) -> dict:
    detected_texts = load_detected_texts(image_path)
    progress_ratio = estimate_progress_ratio(image_path)
    visual_signals = estimate_visual_signals(image_path)
    state = classify_state(detected_texts, progress_ratio, visual_signals)
    return {
        "imagePath": str(image_path),
        "state": state,
        "progressRatio": progress_ratio,
        "visualSignals": visual_signals,
        "detectedTexts": [
            {
                "text": item.text,
                "normalized": normalize_text(item.text),
                "confidence": round(item.confidence, 4),
            }
            for item in detected_texts
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect a RuneScape client screenshot and classify the visible state.")
    parser.add_argument("image_path", help="Path to the screenshot image")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the JSON result")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image_path = Path(args.image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Screenshot not found: {image_path}")

    payload = inspect_image(image_path)
    if args.pretty:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
