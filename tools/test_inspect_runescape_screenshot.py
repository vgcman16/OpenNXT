from __future__ import annotations

import unittest
from pathlib import Path

try:
    from tools.inspect_runescape_screenshot import DetectedText, classify_state, inspect_image
except ModuleNotFoundError:
    from inspect_runescape_screenshot import DetectedText, classify_state, inspect_image


class InspectRuneScapeScreenshotTest(unittest.TestCase):
    def test_classify_loading_from_text(self) -> None:
        state = classify_state(
            [DetectedText(text="Loading application resources", confidence=0.99)],
            0.22,
        )
        self.assertEqual(state, "loading")

    def test_classify_login_screen_from_text(self) -> None:
        state = classify_state(
            [
                DetectedText(text="Username", confidence=0.95),
                DetectedText(text="Password", confidence=0.96),
            ],
            0.0,
        )
        self.assertEqual(state, "login-screen")

    def test_classify_error_from_text(self) -> None:
        state = classify_state(
            [DetectedText(text="Sorry, we had trouble logging you in. Please try again.", confidence=0.97)],
            0.0,
        )
        self.assertEqual(state, "error")

    def test_classify_bad_session_id_as_error(self) -> None:
        state = classify_state(
            [DetectedText(text="Unable to connect: bad session id.", confidence=0.97)],
            0.0,
        )
        self.assertEqual(state, "error")

    def test_classify_restart_required_as_error(self) -> None:
        state = classify_state(
            [
                DetectedText(text="RuneScape has been updated.", confidence=0.97),
                DetectedText(text="Please restart the game to retry.", confidence=0.96),
            ],
            0.2,
        )
        self.assertEqual(state, "error")

    def test_classify_loading_from_progress_without_text(self) -> None:
        state = classify_state(
            [
                DetectedText(text="RuneTekApp", confidence=0.99),
                DetectedText(text="RuneScape", confidence=0.92),
            ],
            0.31,
        )
        self.assertEqual(state, "loading")

    def test_classify_login_screen_from_visual_signals_without_ocr(self) -> None:
        state = classify_state(
            [],
            0.0,
            {
                "loginButtonYellowRatio": 0.41,
                "createButtonBlueRatio": 0.57,
                "cardDarkRatio": 0.72,
            },
        )
        self.assertEqual(state, "login-screen")

    def test_inspect_image_uses_visual_heuristics_when_ocr_is_unavailable(self) -> None:
        image_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "debug"
            / "runtek-automation"
            / "20260405-094708-attempt01-before-screen.png"
        )
        payload = inspect_image(image_path)
        self.assertEqual(payload["state"], "login-screen")
        self.assertGreater(payload["visualSignals"]["loginButtonYellowRatio"], 0.18)
        self.assertGreater(payload["visualSignals"]["createButtonBlueRatio"], 0.35)


if __name__ == "__main__":
    unittest.main()
