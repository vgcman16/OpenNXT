from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from run_runtek_login_loop import (
    artifact_snapshot,
    bootstrap_advanced,
    capture_window,
    dismiss_graphics_dialog,
    dismiss_invalid_login,
    focus_window,
    has_invalid_login_response,
    has_marker,
    has_password_mask,
    has_visible_username,
    inspect_image,
    is_login_screen_ready,
    load_ocr_boxes,
    normalized_texts,
    resolve_hwnd,
    submit_login,
    wait_for_login_screen,
)


DEFAULT_PHASE_SWITCH_REDIRECTS = [
    "world*.runescape.com=localhost",
    "lobby*.runescape.com=localhost",
    "content.runescape.com=localhost",
]


def default_phase_switch_redirects() -> list[str]:
    return list(DEFAULT_PHASE_SWITCH_REDIRECTS)


def dedupe_rules(rules: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for rule in rules:
        normalized = str(rule or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Wait for the 947 login UI on the safe retail-shaped startup path, then attach localhost world redirects just before login submit."
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--window-title", default="RuneTekApp")
    parser.add_argument("--handle", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--login-screen-timeout-seconds", type=int, default=120)
    parser.add_argument("--attempt-wait-seconds", type=int, default=25)
    parser.add_argument("--settle-delay-seconds", type=int, default=2)
    parser.add_argument("--pre-click-delay-ms", type=int, default=500)
    parser.add_argument("--trace-duration-seconds", type=int, default=240)
    parser.add_argument(
        "--capture-dir",
        type=Path,
        default=root / "data" / "debug" / "runtek-automation",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=root / "data" / "debug" / "runtek-automation" / "latest-phase-switch-login.json",
    )
    parser.add_argument(
        "--direct-summary-path",
        type=Path,
        default=root / "data" / "debug" / "direct-rs2client-patch" / "latest-client-only.json",
        help="Summary JSON produced by the direct patch launcher, used to resolve the live rs2client pid when --pid is not supplied.",
    )
    parser.add_argument(
        "--trace-output",
        type=Path,
        default=root / "data" / "debug" / "direct-rs2client-patch" / "latest-phase-switch-hook.jsonl",
    )
    parser.add_argument(
        "--resolve-redirect",
        action="append",
        default=default_phase_switch_redirects(),
        help="Host redirect rule in source=target form. May be supplied multiple times.",
    )
    parser.add_argument(
        "--connect-redirect",
        action="append",
        default=default_phase_switch_redirects(),
        help="Connect redirect rule in source=target form. May be supplied multiple times.",
    )
    return parser.parse_args()


def load_summary_pid(summary_path: Path) -> int:
    if not summary_path.exists():
        return 0
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    try:
        return int(payload.get("pid") or 0)
    except (TypeError, ValueError):
        return 0


def build_phase_switch_trace_args(
    python_exe: str,
    root: Path,
    pid: int,
    output_path: Path,
    duration_seconds: int,
    resolve_redirects: list[str],
    connect_redirects: list[str],
) -> list[str]:
    trace_script = root / "tools" / "trace_rs2client_live.py"
    args = [
        python_exe,
        str(trace_script),
        "--pid",
        str(pid),
        "--output",
        str(output_path),
        "--duration-seconds",
        str(max(0, duration_seconds)),
    ]
    for rule in dedupe_rules(resolve_redirects):
        args.extend(["--resolve-redirect", rule])
    for rule in dedupe_rules(connect_redirects):
        args.extend(["--connect-redirect", rule])
    return args


def start_phase_switch_trace(
    python_exe: str,
    root: Path,
    pid: int,
    output_path: Path,
    duration_seconds: int,
    resolve_redirects: list[str],
    connect_redirects: list[str],
) -> subprocess.Popen[str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = build_phase_switch_trace_args(
        python_exe=python_exe,
        root=root,
        pid=pid,
        output_path=output_path,
        duration_seconds=duration_seconds,
        resolve_redirects=resolve_redirects,
        connect_redirects=connect_redirects,
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        args,
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        creationflags=creation_flags,
    )


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    hwnd = resolve_hwnd(args.handle, args.window_title)
    pid = args.pid if args.pid > 0 else load_summary_pid(args.direct_summary_path)
    if hwnd == 0:
        raise RuntimeError(f"Could not find a visible window containing title {args.window_title!r}")
    if pid <= 0:
        raise RuntimeError(
            f"Could not resolve a live rs2client pid from --pid or {args.direct_summary_path}"
        )

    focus_window(hwnd)
    before_artifacts = artifact_snapshot(root)
    before_path = args.capture_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-phase-switch-before.png"
    before_path.parent.mkdir(parents=True, exist_ok=True)
    capture_window(hwnd, before_path)
    before_inspection = inspect_image(before_path)

    if has_marker(before_inspection, "GRAPHICSDRIVERS", "GRAPHICS DRIVERS", "UPDATE", "IGNORE"):
        dismiss_graphics_dialog(hwnd)
        time.sleep(max(0, args.settle_delay_seconds))
        before_path = args.capture_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-phase-switch-after-graphics-dismiss.png"
        capture_window(hwnd, before_path)
        before_inspection = inspect_image(before_path)

    if has_invalid_login_response(before_inspection):
        dismiss_invalid_login(hwnd)
        time.sleep(max(0, args.settle_delay_seconds))
        before_path = args.capture_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-phase-switch-after-error-dismiss.png"
        capture_window(hwnd, before_path)
        before_inspection = inspect_image(before_path)

    before_path, before_inspection = wait_for_login_screen(
        hwnd,
        args.capture_dir,
        1,
        args.settle_delay_seconds,
        args.login_screen_timeout_seconds,
        before_path,
        before_inspection,
    )

    tracer_process: subprocess.Popen[str] | None = None
    stop_reason = "login-screen-not-ready"
    success = False

    if is_login_screen_ready(before_inspection):
        tracer_process = start_phase_switch_trace(
            python_exe=sys.executable,
            root=root,
            pid=pid,
            output_path=args.trace_output,
            duration_seconds=args.trace_duration_seconds,
            resolve_redirects=args.resolve_redirect,
            connect_redirects=args.connect_redirect,
        )
        time.sleep(1.5)
        username_visible = has_visible_username(before_inspection, args.username)
        password_masked = has_password_mask(before_inspection)
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
            attempt=1,
            username_already_visible=username_visible,
            password_already_masked=password_masked,
        )
        time.sleep(max(0, args.attempt_wait_seconds))
        focus_window(hwnd)
        after_artifacts = artifact_snapshot(root)
        after_path = args.capture_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-phase-switch-after.png"
        capture_window(hwnd, after_path)
        after_inspection = inspect_image(after_path)
        after_state = str(after_inspection.get("state") or "unknown")
        observed_bootstrap = bootstrap_advanced(before_artifacts, after_artifacts)
        if observed_bootstrap or after_state == "loading":
            success = True
            stop_reason = "world-bootstrap-observed" if observed_bootstrap else "loading-after-submit"
        elif has_invalid_login_response(after_inspection):
            stop_reason = "invalid-login"
        elif after_state == "error":
            stop_reason = "client-error"
        else:
            stop_reason = "no-world-progress"
    else:
        username_visible = False
        password_masked = False
        pre_submit_path = None
        pre_submit_inspection = None
        pre_submit_username_visible = False
        pre_submit_password_masked = False
        after_artifacts = before_artifacts
        after_path = before_path
        after_inspection = before_inspection
        after_state = str(after_inspection.get("state") or "unknown")
        observed_bootstrap = False

    summary = {
        "windowHandle": hwnd,
        "windowTitle": args.window_title,
        "pid": pid,
        "directSummaryPath": str(args.direct_summary_path),
        "success": success,
        "stopReason": stop_reason,
        "traceOutput": str(args.trace_output),
        "tracePid": tracer_process.pid if tracer_process is not None else None,
        "resolveRedirects": args.resolve_redirect,
        "connectRedirects": args.connect_redirect,
        "beforeImage": str(before_path),
        "beforeState": before_inspection.get("state") if before_inspection else "unknown",
        "beforeTexts": normalized_texts(before_inspection),
        "beforeUsernameVisible": username_visible,
        "beforePasswordMasked": password_masked,
        "preSubmitImage": str(pre_submit_path) if pre_submit_path is not None else None,
        "preSubmitState": pre_submit_inspection.get("state") if pre_submit_inspection else None,
        "preSubmitUsernameVisible": pre_submit_username_visible,
        "preSubmitPasswordMasked": pre_submit_password_masked,
        "afterImage": str(after_path),
        "afterState": after_state,
        "afterTexts": normalized_texts(after_inspection),
        "bootstrapAdvanced": observed_bootstrap,
        "beforeArtifacts": before_artifacts,
        "afterArtifacts": after_artifacts,
    }
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
