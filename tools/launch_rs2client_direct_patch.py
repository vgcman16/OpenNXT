from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any
import threading

import frida

try:
    from tools.launch_runescape_wrapper_rewrite import (
        build_connect_redirects,
        normalize_jump_bypass_specs,
        normalize_patch_offsets,
        patch_remote_embedded_rsa_moduli,
        patch_remote_inline_offsets,
        patch_remote_jump_bypass_blocks,
        patch_remote_null_read_offsets,
        query_process_command_line,
        query_process_path,
    )
    from tools.trace_rs2client_live import build_hook_script as build_startup_hook_script
    from tools.trace_rs2client_live import normalize_payload as normalize_startup_hook_payload
except ImportError:
    from launch_runescape_wrapper_rewrite import (  # type: ignore
        build_connect_redirects,
        normalize_jump_bypass_specs,
        normalize_patch_offsets,
        patch_remote_embedded_rsa_moduli,
        patch_remote_inline_offsets,
        patch_remote_jump_bypass_blocks,
        patch_remote_null_read_offsets,
        query_process_command_line,
        query_process_path,
    )
    from trace_rs2client_live import build_hook_script as build_startup_hook_script  # type: ignore
    from trace_rs2client_live import normalize_payload as normalize_startup_hook_payload  # type: ignore


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Launch a local rs2client.exe directly, apply the same in-memory guard patches used on the "
            "947 wrapper child path, and report whether the process survives startup."
        )
    )
    parser.add_argument("--client-exe", required=True, help="Path to the local rs2client.exe")
    parser.add_argument("--working-dir", required=True, help="Working directory for the client process")
    parser.add_argument(
        "--client-arg",
        action="append",
        default=[],
        help="Repeatable client argument to append after the executable path",
    )
    parser.add_argument("--summary-output", required=True, help="Path to write the JSON summary")
    parser.add_argument("--trace-output", help="Optional JSONL trace output")
    parser.add_argument(
        "--startup-hook-output",
        help="Optional JSONL file for a pre-resume Frida startup hook on the direct client",
    )
    parser.add_argument(
        "--startup-hook-verbose",
        action="store_true",
        help="Emit higher-volume startup hook events when --startup-hook-output is enabled",
    )
    parser.add_argument("--rsa-config", help="Optional rsa.toml to patch embedded moduli in memory")
    parser.add_argument(
        "--patch-inline-offset",
        action="append",
        default=[],
        help="Repeatable inline patch offset (hex or decimal)",
    )
    parser.add_argument(
        "--patch-null-read-offset",
        action="append",
        default=[],
        help="Repeatable null-read patch offset (hex or decimal)",
    )
    parser.add_argument(
        "--patch-jump-bypass",
        action="append",
        default=[],
        help="Repeatable source:target jump-bypass patch (hex or decimal)",
    )
    parser.add_argument(
        "--resolve-redirect",
        action="append",
        default=[],
        help="Repeatable host=target redirect applied inside GetAddrInfo* before resume",
    )
    parser.add_argument(
        "--patch-delay-seconds",
        type=float,
        default=0.0,
        help="Optional delay after spawn before applying patches",
    )
    parser.add_argument(
        "--monitor-seconds",
        type=float,
        default=15.0,
        help="How long to wait before deciding whether the process survived startup",
    )
    return parser.parse_args(argv)


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


def _write_trace(handle, action: str, **payload: Any) -> None:
    if handle is None:
        return
    event = {"timestamp": round(time.time(), 6), "action": action, **payload}
    handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")
    handle.flush()


def build_summary(
    *,
    client_exe: Path,
    working_dir: Path,
    argv_list: list[str],
    launch_mode: str,
    monitor_seconds: float,
    patch_delay_seconds: float,
    inline_patch_offsets: list[int],
    inline_patch_results: list[dict[str, Any]],
    null_patch_offsets: list[int],
    null_patch_results: list[dict[str, Any]],
    jump_bypass_specs: list[tuple[int, int]],
    jump_patch_results: list[dict[str, Any]],
    rsa_config_path: Path | None,
    rsa_patch_results: Any,
    resolve_redirects: dict[str, str],
    connect_redirects: dict[str, dict[str, Any]],
    startup_hook_output: Path | None,
    startup_hook_verbose: bool,
    trace_output: Path | None,
    process_pid: int,
    exit_code: int | None,
    summary_stage: str,
) -> dict[str, Any]:
    live_process_path = query_process_path(process_pid)
    live_command_line = query_process_command_line(process_pid)
    alive = exit_code is None and (live_process_path is not None or live_command_line is not None)
    return {
        "pid": process_pid,
        "clientExe": str(client_exe),
        "workingDir": str(working_dir),
        "argv": argv_list,
        "launchMode": launch_mode,
        "monitorSeconds": monitor_seconds,
        "patchDelaySeconds": patch_delay_seconds,
        "inlinePatchOffsets": [f"0x{offset:x}" for offset in inline_patch_offsets],
        "inlinePatchResults": inline_patch_results,
        "nullReadPatchOffsets": [f"0x{offset:x}" for offset in null_patch_offsets],
        "nullReadPatchResults": null_patch_results,
        "jumpBypassSpecs": [
            {"sourceOffset": f"0x{source:x}", "targetOffset": f"0x{target:x}"}
            for source, target in jump_bypass_specs
        ],
        "jumpBypassResults": jump_patch_results,
        "rsaConfigPath": str(rsa_config_path) if rsa_config_path is not None else None,
        "rsaPatchResults": rsa_patch_results,
        "resolveRedirects": resolve_redirects,
        "connectRedirects": connect_redirects,
        "startupHookOutput": str(startup_hook_output) if startup_hook_output is not None else None,
        "startupHookVerbose": startup_hook_verbose,
        "summaryStage": summary_stage,
        "processAlive": alive,
        "exitCode": exit_code,
        "liveProcessPath": live_process_path,
        "liveCommandLine": live_command_line,
        "traceOutput": str(trace_output) if trace_output is not None else None,
    }


def write_summary_output(summary_output: Path, summary: dict[str, Any]) -> None:
    temp_output = summary_output.with_name(summary_output.name + ".tmp")
    temp_output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    temp_output.replace(summary_output)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    client_exe = Path(args.client_exe)
    working_dir = Path(args.working_dir)
    summary_output = Path(args.summary_output)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    trace_output = Path(args.trace_output) if args.trace_output else None
    startup_hook_output = Path(args.startup_hook_output) if args.startup_hook_output else None
    if trace_output is not None:
        trace_output.parent.mkdir(parents=True, exist_ok=True)
    if startup_hook_output is not None:
        startup_hook_output.parent.mkdir(parents=True, exist_ok=True)

    inline_patch_offsets = normalize_patch_offsets(args.patch_inline_offset)
    null_patch_offsets = normalize_patch_offsets(args.patch_null_read_offset)
    jump_bypass_specs = normalize_jump_bypass_specs(args.patch_jump_bypass)
    rsa_config_path = Path(args.rsa_config) if args.rsa_config else None
    resolve_redirects = parse_resolve_redirect_specs(args.resolve_redirect)
    connect_redirects = build_connect_redirects(resolve_redirects)

    if not client_exe.exists():
        raise FileNotFoundError(f"Client executable not found: {client_exe}")
    if not working_dir.exists():
        raise FileNotFoundError(f"Working directory not found: {working_dir}")

    trace_handle = trace_output.open("w", encoding="utf-8") if trace_output is not None else None
    startup_hook_handle = startup_hook_output.open("w", encoding="utf-8") if startup_hook_output is not None else None
    try:
        argv_list = [str(client_exe), *args.client_arg]
        process = None
        process_pid: int
        launch_mode = "subprocess"
        startup_session = None
        startup_script = None
        startup_stop = threading.Event()

        def write_startup_event(event: dict[str, Any]) -> None:
            if startup_hook_handle is None:
                return
            startup_hook_handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")
            startup_hook_handle.flush()

        use_spawn_session = startup_hook_output is not None or bool(resolve_redirects)
        if use_spawn_session:
            device = frida.get_local_device()
            process_pid = int(device.spawn(argv_list, cwd=str(working_dir)))
            launch_mode = "frida-spawn"
            _write_trace(trace_handle, "spawned", pid=process_pid, argv=argv_list, workingDir=str(working_dir), launchMode=launch_mode)
            startup_session = device.attach(process_pid)

            def on_startup_message(message: dict[str, Any], _data: Any) -> None:
                if message.get("type") == "send":
                    payload = message.get("payload", {})
                    if isinstance(payload, dict):
                        normalized = normalize_startup_hook_payload(payload)
                        normalized.setdefault("pid", process_pid)
                        write_startup_event(normalized)
                    else:
                        write_startup_event(
                            {
                                "timestamp": round(time.time(), 6),
                                "category": "client.unknown",
                                "action": "message",
                                "pid": process_pid,
                                "payload": payload,
                            }
                        )
                    return

                write_startup_event(
                    {
                        "timestamp": round(time.time(), 6),
                        "category": "client.unknown",
                        "action": "frida-message",
                        "pid": process_pid,
                        "message": message,
                    }
                )

            def on_startup_detached(reason: str, crash: Any) -> None:
                event = {
                    "timestamp": round(time.time(), 6),
                    "category": "client.lifecycle",
                    "action": "detached",
                    "pid": process_pid,
                    "reason": reason,
                }
                if crash is not None:
                    event["crash"] = crash
                write_startup_event(event)
                startup_stop.set()

            startup_script = startup_session.create_script(
                build_startup_hook_script(
                    args.startup_hook_verbose,
                    resolve_redirects=resolve_redirects,
                    connect_redirects=connect_redirects,
                )
            )
            startup_script.on("message", on_startup_message)
            startup_session.on("detached", on_startup_detached)
            startup_script.load()
            pre_resume_event = {
                "timestamp": round(time.time(), 6),
                "category": "client.lifecycle",
                "action": "pre-resume-attached",
                "pid": process_pid,
                "verbose": bool(args.startup_hook_verbose),
                "resolveRedirects": resolve_redirects,
                "connectRedirects": connect_redirects,
            }
            write_startup_event(pre_resume_event)
            _write_trace(
                trace_handle,
                "pre-resume-attached",
                pid=process_pid,
                resolveRedirects=resolve_redirects,
                connectRedirects=connect_redirects,
            )
        else:
            process = subprocess.Popen(argv_list, cwd=str(working_dir))
            process_pid = int(process.pid)
            _write_trace(trace_handle, "spawned", pid=process_pid, argv=argv_list, workingDir=str(working_dir), launchMode=launch_mode)

        if args.patch_delay_seconds > 0:
            time.sleep(args.patch_delay_seconds)

        inline_patch_results = patch_remote_inline_offsets(process_pid, inline_patch_offsets)
        _write_trace(trace_handle, "inline-patched", pid=process_pid, results=inline_patch_results)

        null_patch_results = patch_remote_null_read_offsets(process_pid, null_patch_offsets)
        _write_trace(trace_handle, "null-read-patched", pid=process_pid, results=null_patch_results)

        jump_patch_results = patch_remote_jump_bypass_blocks(process_pid, jump_bypass_specs)
        _write_trace(trace_handle, "jump-bypass-patched", pid=process_pid, results=jump_patch_results)

        rsa_patch_results = None
        live_path = query_process_path(process_pid)
        if rsa_config_path is not None and live_path:
            rsa_patch_results = patch_remote_embedded_rsa_moduli(process_pid, Path(live_path), rsa_config_path)
            _write_trace(trace_handle, "rsa-patched", pid=process_pid, results=rsa_patch_results)

        if startup_hook_output is not None:
            device.resume(process_pid)
            _write_trace(trace_handle, "resumed", pid=process_pid, launchMode=launch_mode)

        ready_summary = build_summary(
            client_exe=client_exe,
            working_dir=working_dir,
            argv_list=argv_list,
            launch_mode=launch_mode,
            monitor_seconds=args.monitor_seconds,
            patch_delay_seconds=args.patch_delay_seconds,
            inline_patch_offsets=inline_patch_offsets,
            inline_patch_results=inline_patch_results,
            null_patch_offsets=null_patch_offsets,
            null_patch_results=null_patch_results,
            jump_bypass_specs=jump_bypass_specs,
            jump_patch_results=jump_patch_results,
            rsa_config_path=rsa_config_path,
            rsa_patch_results=rsa_patch_results,
            resolve_redirects=resolve_redirects,
            connect_redirects=connect_redirects,
            startup_hook_output=startup_hook_output,
            startup_hook_verbose=bool(args.startup_hook_verbose),
            trace_output=trace_output,
            process_pid=process_pid,
            exit_code=None,
            summary_stage="ready",
        )
        _write_trace(trace_handle, "summary-ready", summary=ready_summary)
        write_summary_output(summary_output, ready_summary)

        deadline = time.time() + max(0.0, args.monitor_seconds)
        exit_code = None
        while time.time() < deadline:
            if process is not None:
                exit_code = process.poll()
                if exit_code is not None:
                    break
            else:
                if query_process_path(process_pid) is None:
                    break
            time.sleep(0.25)

        if process is not None and exit_code is None:
            exit_code = process.poll()

        summary = build_summary(
            client_exe=client_exe,
            working_dir=working_dir,
            argv_list=argv_list,
            launch_mode=launch_mode,
            monitor_seconds=args.monitor_seconds,
            patch_delay_seconds=args.patch_delay_seconds,
            inline_patch_offsets=inline_patch_offsets,
            inline_patch_results=inline_patch_results,
            null_patch_offsets=null_patch_offsets,
            null_patch_results=null_patch_results,
            jump_bypass_specs=jump_bypass_specs,
            jump_patch_results=jump_patch_results,
            rsa_config_path=rsa_config_path,
            rsa_patch_results=rsa_patch_results,
            resolve_redirects=resolve_redirects,
            connect_redirects=connect_redirects,
            startup_hook_output=startup_hook_output,
            startup_hook_verbose=bool(args.startup_hook_verbose),
            trace_output=trace_output,
            process_pid=process_pid,
            exit_code=exit_code,
            summary_stage="final",
        )
        _write_trace(trace_handle, "summary", summary=summary)
        write_summary_output(summary_output, summary)

        if startup_script is not None:
            try:
                startup_script.unload()
            except frida.InvalidOperationError:
                pass
        if startup_session is not None:
            try:
                startup_session.detach()
            except frida.InvalidOperationError:
                pass
        startup_stop.set()
    finally:
        if trace_handle is not None:
            trace_handle.close()
        if startup_hook_handle is not None:
            startup_hook_handle.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
