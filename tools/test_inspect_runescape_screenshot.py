from __future__ import annotations

import unittest

from tools.inspect_runescape_screenshot import DetectedText, classify_state


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

    def test_classify_loading_from_progress_without_text(self) -> None:
        state = classify_state(
            [
                DetectedText(text="RuneTekApp", confidence=0.99),
                DetectedText(text="RuneScape", confidence=0.92),
            ],
            0.31,
        )
        self.assertEqual(state, "loading")


if __name__ == "__main__":
    unittest.main()
