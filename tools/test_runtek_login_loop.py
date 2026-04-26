from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_runtek_login_loop as login_loop


class RuntekLoginLoopTests(unittest.TestCase):
    def test_is_login_screen_ready_requires_login_markers(self) -> None:
        self.assertTrue(
            login_loop.is_login_screen_ready(
                {
                    "state": "login-screen",
                    "detectedTexts": [
                        {"text": "Username/Email", "normalized": "USERNAME EMAIL"},
                        {"text": "Password", "normalized": "PASSWORD"},
                        {"text": "LOG IN", "normalized": "LOG IN"},
                    ],
                }
            )
        )
        self.assertFalse(
            login_loop.is_login_screen_ready(
                {
                    "state": "loading",
                    "detectedTexts": [
                        {"text": "Loading application resources", "normalized": "LOADING APPLICATION RESOURCES"}
                    ],
                }
            )
        )

    def test_resolve_safe_login_button_prefers_upper_login_button(self) -> None:
        boxes = [
            login_loop.OcrBox("PASSWORD", "PASSWORD", 340.0, 350.0, 470.0, 371.0),
            login_loop.OcrBox("LOG IN", "LOG IN", 464.0, 441.0, 575.0, 469.0),
            login_loop.OcrBox("Orloginwith:", "ORLOGINWITH", 469.0, 484.0, 570.0, 504.0),
            login_loop.OcrBox("CREATEFREEACCOUNT", "CREATEFREEACCOUNT", 420.0, 623.0, 621.0, 638.0),
        ]
        button = login_loop.resolve_safe_login_button(boxes)
        self.assertIsNotNone(button)
        self.assertEqual(button.normalized, "LOG IN")

    def test_resolve_safe_login_button_rejects_create_account_region(self) -> None:
        boxes = [
            login_loop.OcrBox("PASSWORD", "PASSWORD", 340.0, 350.0, 470.0, 371.0),
            login_loop.OcrBox("CREATEFREEACCOUNT", "CREATEFREEACCOUNT", 420.0, 623.0, 621.0, 638.0),
        ]
        self.assertIsNone(login_loop.resolve_safe_login_button(boxes))

    def test_should_prefer_screen_capture_when_it_reaches_login(self) -> None:
        printwindow = {
            "state": "loading",
            "detectedTexts": [
                {"text": "RuneTekApp", "normalized": "RUNETEKAPP"},
                {"text": "RuneScape", "normalized": "RUNESCAPE"},
            ],
        }
        screen = {
            "state": "login-screen",
            "detectedTexts": [
                {"text": "Username/Email", "normalized": "USERNAME EMAIL"},
                {"text": "Password", "normalized": "PASSWORD"},
                {"text": "LOG IN", "normalized": "LOG IN"},
            ],
        }
        self.assertTrue(login_loop.should_prefer_screen_capture(printwindow, screen))

    def test_should_keep_printwindow_when_screen_capture_is_weaker(self) -> None:
        printwindow = {
            "state": "login-screen",
            "detectedTexts": [
                {"text": "Username/Email", "normalized": "USERNAME EMAIL"},
                {"text": "Password", "normalized": "PASSWORD"},
                {"text": "LOG IN", "normalized": "LOG IN"},
            ],
        }
        screen = {
            "state": "splash",
            "detectedTexts": [
                {"text": "RuneScape", "normalized": "RUNESCAPE"},
            ],
        }
        self.assertFalse(login_loop.should_prefer_screen_capture(printwindow, screen))

    def test_should_reject_screen_capture_that_does_not_look_like_runtek(self) -> None:
        printwindow = {
            "state": "loading",
            "detectedTexts": [
                {"text": "RuneScape", "normalized": "RUNESCAPE"},
                {"text": "RuneTekApp", "normalized": "RUNETEKAPP"},
            ],
        }
        screen = {
            "state": "loading",
            "detectedTexts": [
                {"text": "Manage Comrades", "normalized": "MANAGE COMRADES"},
                {"text": "Ronald", "normalized": "RONALD"},
            ],
        }
        self.assertFalse(login_loop.should_prefer_screen_capture(printwindow, screen))

    def test_should_reject_screen_capture_with_foreign_overlay_markers(self) -> None:
        printwindow = {
            "state": "login-screen",
            "detectedTexts": [
                {"text": "RuneTekApp", "normalized": "RUNETEKAPP"},
                {"text": "Username/Email", "normalized": "USERNAME EMAIL"},
                {"text": "Password", "normalized": "PASSWORD"},
                {"text": "LOG IN", "normalized": "LOG IN"},
            ],
        }
        screen = {
            "state": "loading",
            "detectedTexts": [
                {"text": "RuneTekApp", "normalized": "RUNETEKAPP"},
                {"text": "Cheat Happens", "normalized": "CHEATHAPPENS"},
                {"text": "Crimson Desert", "normalized": "CRIMSON DESERT"},
                {"text": "Activate Trainer", "normalized": "ACTIVATE TRAINER"},
            ],
        }
        self.assertFalse(login_loop.should_prefer_screen_capture(printwindow, screen))

    def test_load_pid_from_summary_reads_numeric_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "summary.json"
            path.write_text(json.dumps({"pid": 24972}), encoding="utf-8")
            self.assertEqual(login_loop.load_pid_from_summary(path), 24972)

    def test_load_pid_from_summary_ignores_missing_or_invalid_files(self) -> None:
        self.assertEqual(login_loop.load_pid_from_summary(Path("Z:/does-not-exist.json")), 0)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "summary.json"
            path.write_text("{not-json", encoding="utf-8")
            self.assertEqual(login_loop.load_pid_from_summary(path), 0)

    def test_submit_login_prefers_direct_keystroke_entry_before_submit(self) -> None:
        actions: list[tuple[str, object]] = []
        boxes = [
            login_loop.OcrBox("USERNAME/EMAIL", "USERNAME EMAIL", 470.0, 200.0, 680.0, 226.0),
            login_loop.OcrBox("PASSWORD", "PASSWORD", 470.0, 314.0, 600.0, 336.0),
            login_loop.OcrBox("LOG IN", "LOG IN", 594.0, 405.0, 701.0, 430.0),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            capture_dir = Path(tmpdir)

            def fake_capture_window(hwnd: int, output: Path) -> Path:
                output.write_bytes(b"")
                actions.append(("capture", output.name))
                return output

            with (
                patch.object(login_loop, "click_field_target", side_effect=lambda *args, **kwargs: actions.append(("click-field", None))),
                patch.object(login_loop, "drag_select_box_text", side_effect=lambda *args, **kwargs: actions.append(("drag-select", None))),
                patch.object(login_loop, "send_ctrl_a", side_effect=lambda: actions.append(("ctrl-a", None))),
                patch.object(login_loop, "send_backspace", side_effect=lambda count=1: actions.append(("backspace", count))),
                patch.object(login_loop, "send_delete", side_effect=lambda count=1: actions.append(("delete", count))),
                patch.object(login_loop, "send_home", side_effect=lambda: actions.append(("home", None))),
                patch.object(login_loop, "send_end", side_effect=lambda: actions.append(("end", None))),
                patch.object(login_loop, "enter_text", side_effect=lambda text: actions.append(("enter-text", text))),
                patch.object(login_loop, "send_text", side_effect=lambda text: actions.append(("send-text", text))),
                patch.object(login_loop, "send_tab", side_effect=lambda: actions.append(("tab", None))),
                patch.object(login_loop, "capture_window", side_effect=fake_capture_window),
                patch.object(login_loop, "inspect_image", return_value={"state": "login-screen", "detectedTexts": []}),
                patch.object(login_loop, "has_visible_username", return_value=True),
                patch.object(login_loop, "has_password_mask", return_value=True),
                patch.object(login_loop, "click_box_target", side_effect=lambda *args, **kwargs: actions.append(("click-login", None))),
                patch.object(login_loop, "send_enter", side_effect=lambda: actions.append(("enter", None))),
            ):
                login_loop.submit_login(
                    123,
                    "demon",
                    "ecko13",
                    0,
                    ocr_boxes=boxes,
                    capture_dir=capture_dir,
                    attempt=1,
                    username_already_visible=False,
                    password_already_masked=False,
                )

        self.assertIn(("send-text", "demon"), actions)
        self.assertIn(("send-text", "ecko13"), actions)
        self.assertIn(("tab", None), actions)
        self.assertIn(("click-login", None), actions)
        self.assertEqual(3, sum(1 for action, _ in actions if action == "enter"))

    def test_submit_login_skips_retyping_prefilled_fields(self) -> None:
        actions: list[tuple[str, object]] = []
        boxes = [
            login_loop.OcrBox("USERNAME/EMAIL", "USERNAME EMAIL", 470.0, 200.0, 680.0, 226.0),
            login_loop.OcrBox("PASSWORD", "PASSWORD", 470.0, 314.0, 600.0, 336.0),
            login_loop.OcrBox("LOG IN", "LOG IN", 594.0, 405.0, 701.0, 430.0),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            capture_dir = Path(tmpdir)

            def fake_capture_window(hwnd: int, output: Path) -> Path:
                output.write_bytes(b"")
                return output

            with (
                patch.object(login_loop, "click_field_target", side_effect=lambda *args, **kwargs: actions.append(("click-field", None))),
                patch.object(login_loop, "drag_select_box_text", side_effect=lambda *args, **kwargs: actions.append(("drag-select", None))),
                patch.object(login_loop, "send_ctrl_a", side_effect=lambda: actions.append(("ctrl-a", None))),
                patch.object(login_loop, "send_backspace", side_effect=lambda count=1: actions.append(("backspace", count))),
                patch.object(login_loop, "send_delete", side_effect=lambda count=1: actions.append(("delete", count))),
                patch.object(login_loop, "send_home", side_effect=lambda: actions.append(("home", None))),
                patch.object(login_loop, "send_end", side_effect=lambda: actions.append(("end", None))),
                patch.object(login_loop, "enter_text", side_effect=lambda text: actions.append(("enter-text", text))),
                patch.object(login_loop, "send_text", side_effect=lambda text: actions.append(("send-text", text))),
                patch.object(login_loop, "capture_window", side_effect=fake_capture_window),
                patch.object(login_loop, "inspect_image", return_value={"state": "login-screen", "detectedTexts": [{"text": "demon"}, {"text": "***"}]}),
                patch.object(login_loop, "has_visible_username", return_value=True),
                patch.object(login_loop, "has_password_mask", return_value=True),
                patch.object(login_loop, "click_box_target", side_effect=lambda *args, **kwargs: actions.append(("click-login", None))),
                patch.object(login_loop, "send_enter", side_effect=lambda: actions.append(("enter", None))),
            ):
                login_loop.submit_login(
                    123,
                    "demon",
                    "ecko13",
                    0,
                    ocr_boxes=boxes,
                    capture_dir=capture_dir,
                    attempt=1,
                    username_already_visible=True,
                    password_already_masked=True,
                )

        self.assertNotIn(("enter-text", "demon"), actions)
        self.assertNotIn(("enter-text", "ecko13"), actions)
        self.assertNotIn(("send-text", "demon"), actions)
        self.assertNotIn(("send-text", "ecko13"), actions)
        self.assertNotIn(("click-field", None), actions)
        self.assertIn(("click-login", None), actions)

    def test_retry_populates_password_by_reanchoring_on_username_then_tab(self) -> None:
        actions: list[tuple[str, object]] = []
        boxes = [
            login_loop.OcrBox("USERNAME/EMAIL", "USERNAME EMAIL", 470.0, 200.0, 680.0, 226.0),
            login_loop.OcrBox("PASSWORD", "PASSWORD", 470.0, 314.0, 600.0, 336.0),
            login_loop.OcrBox("LOG IN", "LOG IN", 594.0, 405.0, 701.0, 430.0),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            capture_dir = Path(tmpdir)
            inspections = iter(
                [
                    {"state": "login-screen", "detectedTexts": []},
                    {"state": "login-screen", "detectedTexts": []},
                ]
            )
            username_visible = iter([False, True, True])
            password_masked = iter([False, False, True])
            retry_boxes = [
                login_loop.OcrBox("USERNAME/EMAIL", "USERNAME EMAIL", 470.0, 200.0, 680.0, 226.0),
                login_loop.OcrBox("demon", "DEMON", 492.0, 246.0, 560.0, 270.0),
                login_loop.OcrBox("PASSWORD", "PASSWORD", 470.0, 314.0, 600.0, 336.0),
                login_loop.OcrBox("*****", "", 492.0, 358.0, 560.0, 382.0),
                login_loop.OcrBox("LOG IN", "LOG IN", 594.0, 405.0, 701.0, 430.0),
            ]

            def fake_capture_window(hwnd: int, output: Path) -> Path:
                output.write_bytes(b"")
                return output

            def fake_click_field(hwnd: int, value_box: login_loop.OcrBox | None, label_box: login_loop.OcrBox | None, **kwargs) -> None:
                label = label_box.normalized if label_box is not None else "NONE"
                actions.append(("click-field", label))

            with (
                patch.object(login_loop, "click_field_target", side_effect=fake_click_field),
                patch.object(login_loop, "drag_select_box_text", side_effect=lambda *args, **kwargs: actions.append(("drag-select", None))),
                patch.object(login_loop, "send_ctrl_a", side_effect=lambda: actions.append(("ctrl-a", None))),
                patch.object(login_loop, "send_backspace", side_effect=lambda count=1: actions.append(("backspace", count))),
                patch.object(login_loop, "send_delete", side_effect=lambda count=1: actions.append(("delete", count))),
                patch.object(login_loop, "send_home", side_effect=lambda: actions.append(("home", None))),
                patch.object(login_loop, "send_end", side_effect=lambda: actions.append(("end", None))),
                patch.object(login_loop, "enter_text", side_effect=lambda text: actions.append(("enter-text", text))),
                patch.object(login_loop, "send_text", side_effect=lambda text: actions.append(("send-text", text))),
                patch.object(login_loop, "send_tab", side_effect=lambda: actions.append(("tab", None))),
                patch.object(login_loop, "capture_window", side_effect=fake_capture_window),
                patch.object(login_loop, "inspect_image", side_effect=lambda path: next(inspections)),
                patch.object(login_loop, "has_visible_username", side_effect=lambda inspection, username: next(username_visible)),
                patch.object(login_loop, "has_password_mask", side_effect=lambda inspection: next(password_masked)),
                patch.object(login_loop, "load_ocr_boxes", side_effect=[retry_boxes]),
                patch.object(login_loop, "focus_window", side_effect=lambda hwnd: actions.append(("focus", None))),
                patch.object(login_loop, "click_box_target", side_effect=lambda *args, **kwargs: actions.append(("click-login", None))),
                patch.object(login_loop, "send_enter", side_effect=lambda: actions.append(("enter", None))),
            ):
                login_loop.submit_login(
                    123,
                    "demon",
                    "ecko13",
                    0,
                    ocr_boxes=boxes,
                    capture_dir=capture_dir,
                    attempt=1,
                    username_already_visible=False,
                    password_already_masked=False,
                )

        username_clicks = [entry for entry in actions if entry == ("click-field", "USERNAME EMAIL")]
        password_clicks = [entry for entry in actions if entry == ("click-field", "PASSWORD")]
        self.assertGreaterEqual(len(username_clicks), 2)
        self.assertEqual([], password_clicks)
        self.assertIn(("tab", None), actions)
        self.assertIn(("send-text", "ecko13"), actions)

    def test_submit_login_retry_uses_fresh_visible_username_box(self) -> None:
        actions: list[tuple[str, object]] = []
        initial_boxes = [
            login_loop.OcrBox("USERNAME/EMAIL", "USERNAME EMAIL", 470.0, 200.0, 680.0, 226.0),
            login_loop.OcrBox("PASSWORD", "PASSWORD", 470.0, 314.0, 600.0, 336.0),
            login_loop.OcrBox("LOG IN", "LOG IN", 594.0, 405.0, 701.0, 430.0),
        ]
        retry_boxes = [
            login_loop.OcrBox("USERNAME/EMAIL", "USERNAME EMAIL", 470.0, 200.0, 680.0, 226.0),
            login_loop.OcrBox("ecko13", "ECKO13", 492.0, 246.0, 560.0, 270.0),
            login_loop.OcrBox("PASSWORD", "PASSWORD", 470.0, 314.0, 600.0, 336.0),
            login_loop.OcrBox("*****", "", 492.0, 358.0, 560.0, 382.0),
            login_loop.OcrBox("LOG IN", "LOG IN", 594.0, 405.0, 701.0, 430.0),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            capture_dir = Path(tmpdir)

            def fake_capture_window(hwnd: int, output: Path) -> Path:
                output.write_bytes(b"")
                return output

            def fake_click_field(hwnd: int, value_box: login_loop.OcrBox | None, label_box: login_loop.OcrBox | None, **kwargs) -> None:
                actions.append(("click-field", value_box.text if value_box is not None else (label_box.normalized if label_box is not None else "NONE")))

            inspections = iter(
                [
                    {"state": "login-screen", "detectedTexts": [{"text": "ecko13"}]},
                    {"state": "login-screen", "detectedTexts": [{"text": "demon"}, {"text": "***"}]},
                ]
            )
            username_visible = iter([False, True])
            password_masked = iter([True, True])

            with (
                patch.object(login_loop, "click_field_target", side_effect=fake_click_field),
                patch.object(login_loop, "drag_select_box_text", side_effect=lambda *args, **kwargs: actions.append(("drag-select", value_box.text if (value_box := args[1]) is not None else None))),
                patch.object(login_loop, "send_ctrl_a", side_effect=lambda: actions.append(("ctrl-a", None))),
                patch.object(login_loop, "send_backspace", side_effect=lambda count=1: actions.append(("backspace", count))),
                patch.object(login_loop, "send_delete", side_effect=lambda count=1: actions.append(("delete", count))),
                patch.object(login_loop, "send_home", side_effect=lambda: actions.append(("home", None))),
                patch.object(login_loop, "send_end", side_effect=lambda: actions.append(("end", None))),
                patch.object(login_loop, "enter_text", side_effect=lambda text: actions.append(("enter-text", text))),
                patch.object(login_loop, "send_text", side_effect=lambda text: actions.append(("send-text", text))),
                patch.object(login_loop, "send_tab", side_effect=lambda: actions.append(("tab", None))),
                patch.object(login_loop, "capture_window", side_effect=fake_capture_window),
                patch.object(login_loop, "inspect_image", side_effect=lambda path: next(inspections)),
                patch.object(login_loop, "has_visible_username", side_effect=lambda inspection, username: next(username_visible)),
                patch.object(login_loop, "has_password_mask", side_effect=lambda inspection: next(password_masked)),
                patch.object(login_loop, "load_ocr_boxes", side_effect=[retry_boxes]),
                patch.object(login_loop, "focus_window", side_effect=lambda hwnd: actions.append(("focus", None))),
                patch.object(login_loop, "click_box_target", side_effect=lambda *args, **kwargs: actions.append(("click-login", None))),
                patch.object(login_loop, "send_enter", side_effect=lambda: actions.append(("enter", None))),
            ):
                login_loop.submit_login(
                    123,
                    "demon",
                    "ecko13",
                    0,
                    ocr_boxes=initial_boxes,
                    capture_dir=capture_dir,
                    attempt=1,
                    username_already_visible=False,
                    password_already_masked=True,
                )

        self.assertIn(("click-field", "ecko13"), actions)
        self.assertIn(("drag-select", "ecko13"), actions)
        self.assertIn(("send-text", "demon"), actions)


if __name__ == "__main__":
    unittest.main()
