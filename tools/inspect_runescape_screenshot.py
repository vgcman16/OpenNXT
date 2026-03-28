from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image
from rapidocr_onnxruntime import RapidOCR


OCR_ENGINE: RapidOCR | None = None


@dataclass(frozen=True)
class DetectedText:
    text: str
    confidence: float


def get_ocr_engine() -> RapidOCR:
    global OCR_ENGINE
    if OCR_ENGINE is None:
        OCR_ENGINE = RapidOCR()
    return OCR_ENGINE


def normalize_text(value: str) -> str:
    value = value.upper()
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def load_detected_texts(image_path: Path) -> list[DetectedText]:
    engine = get_ocr_engine()
    result, _ = engine(str(image_path))
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
    bar_top = int(height * 0.50)
    bar_bottom = int(height * 0.68)
    bar_left = int(width * 0.12)
    bar_right = int(width * 0.88)
    if bar_bottom <= bar_top or bar_right <= bar_left:
        return None

    pixels = image.load()
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
    return round(orange_columns / total_columns, 4)


def classify_state(detected_texts: Iterable[DetectedText], progress_ratio: float | None) -> str:
    normalized = [normalize_text(item.text) for item in detected_texts]
    combined = " | ".join(text for text in normalized if text)

    error_markers = (
        "INVALID LOGIN OR PASSWORD",
        "SORRY WE HAD TROUBLE LOGGING YOU IN",
        "THE RUNESCAPE CLIENT SUFFERED FROM AN ERROR",
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

    if "RUNETEKAPP" in combined or "RUNESCAPE" in combined:
        if progress_ratio is not None and progress_ratio > 0.0:
            return "loading"
        return "splash"

    return "unknown"


def inspect_image(image_path: Path) -> dict:
    detected_texts = load_detected_texts(image_path)
    progress_ratio = estimate_progress_ratio(image_path)
    state = classify_state(detected_texts, progress_ratio)
    return {
        "imagePath": str(image_path),
        "state": state,
        "progressRatio": progress_ratio,
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
