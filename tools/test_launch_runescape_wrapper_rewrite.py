import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.launch_runescape_wrapper_rewrite import (
    build_connect_redirects,
    build_effective_rewrite_map,
    build_wrapper_spawn_script,
    build_route_resolve_redirects,
    should_auto_redirect_route_hosts,
    cleanup_spawned_processes,
    cleanup_wrapper_after_child_ready,
    build_param_rewrite_map,
    build_route_rewrite_map,
    extract_param_map,
    find_embedded_rsa_key,
    load_rsa_moduli,
    normalize_jump_bypass_specs,
    normalize_patch_offsets,
    parse_resolve_redirect_specs,
    query_process_command_line,
    query_process_path,
    resolve_fetch_config_uri,
    rebuild_windows_command_line,
    rewrite_param_tokens,
    tokenize_windows_command_line,
)


class LaunchRuneScapeWrapperRewriteTest(unittest.TestCase):
    def test_parse_args_supports_repeatable_wrapper_extra_args(self) -> None:
        from unittest.mock import patch
        from tools.launch_runescape_wrapper_rewrite import parse_args

        argv = [
            "launch_runescape_wrapper_rewrite.py",
            "--wrapper-exe",
            r"C:\RuneScape.exe",
            "--config-uri",
            "http://localhost:8080/jav_config.ws",
            "--trace-output",
            r"C:\trace.jsonl",
            "--wrapper-extra-arg=--useAngle",
            "--wrapper-extra-arg=--another-flag",
        ]
        with patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(["--useAngle", "--another-flag"], args.wrapper_extra_arg)

    def test_parse_args_supports_optional_child_hook_capture(self) -> None:
        from unittest.mock import patch
        from tools.launch_runescape_wrapper_rewrite import parse_args

        argv = [
            "launch_runescape_wrapper_rewrite.py",
            "--wrapper-exe",
            r"C:\RuneScape.exe",
            "--config-uri",
            "http://localhost:8080/jav_config.ws",
            "--trace-output",
            r"C:\trace.jsonl",
            "--child-hook-output",
            r"C:\child-trace.jsonl",
            "--child-hook-verbose",
            "--child-hook-duration-seconds",
            "30",
        ]
        with patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(r"C:\child-trace.jsonl", args.child_hook_output)
        self.assertTrue(args.child_hook_verbose)
        self.assertEqual(30, args.child_hook_duration_seconds)

    def test_parse_args_supports_optional_rsa_config(self) -> None:
        from unittest.mock import patch
        from tools.launch_runescape_wrapper_rewrite import parse_args

        argv = [
            "launch_runescape_wrapper_rewrite.py",
            "--wrapper-exe",
            r"C:\RuneScape.exe",
            "--config-uri",
            "http://localhost:8080/jav_config.ws",
            "--trace-output",
            r"C:\trace.jsonl",
            "--rsa-config",
            r"C:\rsa.toml",
        ]
        with patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(r"C:\rsa.toml", args.rsa_config)

    def test_parse_args_supports_repeatable_resolve_redirects(self) -> None:
        from unittest.mock import patch
        from tools.launch_runescape_wrapper_rewrite import parse_args

        argv = [
            "launch_runescape_wrapper_rewrite.py",
            "--wrapper-exe",
            r"C:\RuneScape.exe",
            "--config-uri",
            "http://localhost:8080/jav_config.ws",
            "--trace-output",
            r"C:\trace.jsonl",
            "--resolve-redirect",
            "rs.config.runescape.com=localhost",
            "--resolve-redirect",
            "content.runescape.com=localhost",
        ]
        with patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(
            ["rs.config.runescape.com=localhost", "content.runescape.com=localhost"],
            args.resolve_redirect,
        )

    def test_parse_args_supports_rewrite_scope(self) -> None:
        from unittest.mock import patch
        from tools.launch_runescape_wrapper_rewrite import parse_args

        argv = [
            "launch_runescape_wrapper_rewrite.py",
            "--wrapper-exe",
            r"C:\RuneScape.exe",
            "--config-uri",
            "http://localhost:8080/jav_config.ws",
            "--trace-output",
            r"C:\trace.jsonl",
            "--rewrite-scope",
            "routes",
        ]
        with patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual("routes", args.rewrite_scope)

    def test_parse_resolve_redirect_specs_normalizes_hosts(self) -> None:
        self.assertEqual(
            {
                "rs.config.runescape.com": "localhost",
                "content.runescape.com": "127.0.0.1",
            },
            parse_resolve_redirect_specs(
                [" RS.CONFIG.RUNESCAPE.COM = localhost ", "content.runescape.com=127.0.0.1"]
            ),
        )

    def test_normalize_patch_offsets_accepts_hex_and_decimal(self) -> None:
        self.assertEqual([0x590C72, 0x590F92], normalize_patch_offsets(["0x590c72", "5836690"]))

    def test_normalize_jump_bypass_specs_accepts_hex_and_decimal(self) -> None:
        self.assertEqual(
            [(0x590C72, 0x590DCB), (5836690, 5837035)],
            normalize_jump_bypass_specs(["0x590c72:0x590dcb", "5836690:5837035"]),
        )

    def test_extract_param_map_reads_param_lines(self) -> None:
        config = "\n".join(
            [
                "codebase=http://localhost:8080/",
                "param=3=localhost",
                "param=35=http://localhost:8080",
                "param=49=localhost",
            ]
        )

        result = extract_param_map(config)

        self.assertEqual(
            {
                "3": "localhost",
                "35": "http://localhost:8080",
                "49": "localhost",
            },
            result,
        )

    def test_resolve_fetch_config_uri_rewrites_public_config_host_to_local_endpoint(self) -> None:
        original = (
            "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?"
            "binaryType=6&hostRewrite=0&contentRouteRewrite=0&worldUrlRewrite=0"
            "&codebaseRewrite=1&baseConfigSource=live&liveCache=1"
        )

        rewritten = resolve_fetch_config_uri(original)

        self.assertEqual(
            "http://localhost:8080/jav_config.ws?binaryType=6&hostRewrite=0&contentRouteRewrite=0&worldUrlRewrite=0&codebaseRewrite=1&baseConfigSource=live&liveCache=1",
            rewritten,
        )

    def test_resolve_fetch_config_uri_keeps_existing_local_config_uri(self) -> None:
        original = "http://localhost:8080/jav_config.ws?binaryType=6"
        self.assertEqual(original, resolve_fetch_config_uri(original))

    def test_should_auto_redirect_route_hosts_false_for_retail_shaped_947_startup(self) -> None:
        config_uri = (
            "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?"
            "binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=0"
            "&worldUrlRewrite=0&codebaseRewrite=0&gameHostRewrite=0"
        )
        self.assertFalse(should_auto_redirect_route_hosts(config_uri))

    def test_should_auto_redirect_route_hosts_true_when_local_route_rewrite_requested(self) -> None:
        config_uri = (
            "http://localhost:8080/jav_config.ws?"
            "binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=1"
            "&worldUrlRewrite=1&codebaseRewrite=1"
        )
        self.assertTrue(should_auto_redirect_route_hosts(config_uri))

    def test_load_rsa_moduli_reads_login_and_js5_moduli(self) -> None:
        with TemporaryDirectory() as temp_dir:
            rsa_path = Path(temp_dir) / "rsa.toml"
            rsa_path.write_text(
                "\n".join(
                    [
                        "[login]",
                        'modulus = "abcd"',
                        "[js5]",
                        'modulus = "ef01"',
                    ]
                ),
                encoding="utf-8",
            )

            result = load_rsa_moduli(rsa_path)

        self.assertEqual({"login": "abcd", "js5": "ef01"}, result)

    def test_find_embedded_rsa_key_matches_null_delimited_ascii_hex(self) -> None:
        embedded = "a" * 256
        payload = b"\x00" + embedded.encode("ascii") + b"\x00\x00\x00" + b"suffix"

        offset, value = find_embedded_rsa_key(payload, 1024)

        self.assertEqual(1, offset)
        self.assertEqual(embedded, value)

    def test_build_route_rewrite_map_keeps_only_route_fields(self) -> None:
        route_map = build_route_rewrite_map(
            {
                "2": "1144",
                "3": "localhost",
                "29": "session-token",
                "35": "http://localhost:8080",
                "37": "localhost",
                "40": "http://localhost:8080",
                "49": "localhost",
            }
        )

        self.assertEqual(
            {
                "3": "localhost",
                "35": "http://localhost:8080",
                "37": "localhost",
                "40": "http://localhost:8080",
                "49": "localhost",
            },
            route_map,
        )

    def test_build_param_rewrite_map_keeps_all_param_fields(self) -> None:
        rewrite_map = build_param_rewrite_map(
            {
                "2": "1144",
                "3": "localhost",
                "27": "5",
                "29": "session-token",
                "35": "http://localhost:8080",
                "37": "localhost",
                "40": "http://localhost:8080",
                "49": "localhost",
            }
        )

        self.assertEqual(
            {
                "2": "1144",
                "3": "localhost",
                "27": "5",
                "29": "session-token",
                "35": "http://localhost:8080",
                "37": "localhost",
                "40": "http://localhost:8080",
                "49": "localhost",
            },
            rewrite_map,
        )

    def test_build_wrapper_spawn_script_hooks_brokered_process_creation_apis(self) -> None:
        script = build_wrapper_spawn_script(r"C:\game\rs2client.exe")

        self.assertIn('installCreateProcessHook("kernelbase.dll", "CreateProcessInternalW", 1, 2, 8, "wide");', script)
        self.assertIn('installCreateProcessHook("advapi32.dll", "CreateProcessAsUserW", 1, 2, 8, "wide");', script)
        self.assertIn('installCreateProcessHook("advapi32.dll", "CreateProcessAsUserA", 1, 2, 8, "ansi");', script)
        self.assertIn('installCreateProcessHook("advapi32.dll", "CreateProcessWithTokenW", 2, 3, 6, "wide");', script)
        self.assertIn('installCreateProcessHook("advapi32.dll", "CreateProcessWithTokenA", 2, 3, 6, "ansi");', script)
        self.assertIn('installCreateProcessHook("advapi32.dll", "CreateProcessWithLogonW", 4, 5, 8, "wide");', script)
        self.assertIn('installShellExecuteHook("shell32.dll", "ShellExecuteA", 2, 3, 4, "ansi");', script)
        self.assertIn('installShellExecuteHook("shell32.dll", "ShellExecuteW", 2, 3, 4, "wide");', script)
        self.assertIn('installShellExecuteExHook("shell32.dll", "ShellExecuteExA", "ansi");', script)
        self.assertIn('installShellExecuteExHook("shell32.dll", "ShellExecuteExW", "wide");', script)

    def test_build_wrapper_spawn_script_can_one_shot_override_first_eligible_child_spawn(self) -> None:
        script = build_wrapper_spawn_script(r"C:\game\rs2client.exe")

        self.assertIn("const overrideState = { consumed: false };", script)
        self.assertIn('return "direct-match";', script)
        self.assertIn('return "one-shot";', script)
        self.assertIn('if (haystack.indexOf("runescape.exe") !== -1 || haystack.indexOf("jagexlauncher") !== -1) {', script)
        self.assertIn("overrideState.consumed = true;", script)
        self.assertIn("matchKind: matchKind,", script)

    def test_build_effective_rewrite_map_uses_full_param_map(self) -> None:
        rewrite_map = build_effective_rewrite_map(
            "\n".join(
                [
                    "param=2=1140",
                    "param=3=localhost",
                    "param=18=1362217156",
                    "param=29=session-token",
                    "param=35=http://localhost:8080/k=5",
                    "param=37=localhost",
                    "param=40=http://localhost:8080/k=5",
                    "param=49=localhost",
                ]
            )
        )

        self.assertEqual(
            {
                "2": "1140",
                "3": "localhost",
                "18": "1362217156",
                "29": "session-token",
                "35": "http://localhost:8080/k=5",
                "37": "localhost",
                "40": "http://localhost:8080/k=5",
                "49": "localhost",
            },
            rewrite_map,
        )

    def test_build_effective_rewrite_map_can_limit_to_route_params(self) -> None:
        rewrite_map = build_effective_rewrite_map(
            "\n".join(
                [
                    "param=2=1140",
                    "param=3=localhost",
                    "param=18=1362217156",
                    "param=29=session-token",
                    "param=35=http://localhost:8080/k=5",
                    "param=37=localhost",
                    "param=40=http://localhost:8080/k=5",
                    "param=49=localhost",
                ]
            ),
            rewrite_scope="routes",
        )

        self.assertEqual(
            {
                "3": "localhost",
                "35": "http://localhost:8080/k=5",
                "37": "localhost",
                "40": "http://localhost:8080/k=5",
                "49": "localhost",
            },
            rewrite_map,
        )

    def test_build_route_resolve_redirects_derives_world_lobby_and_content_hosts(self) -> None:
        redirects = build_route_resolve_redirects(
            {
                "3": "lobby48a.runescape.com",
                "35": "https://world31.runescape.com/k=5",
                "37": "content.runescape.com",
                "40": "https://world31.runescape.com/k=5",
                "49": "content.runescape.com",
            }
        )

        self.assertEqual(
            {
                "lobby48a.runescape.com": "localhost",
                "world31.runescape.com": "localhost",
                "content.runescape.com": "localhost",
            },
            redirects,
        )

    def test_build_route_resolve_redirects_skips_loopback_hosts(self) -> None:
        redirects = build_route_resolve_redirects(
            {
                "3": "localhost",
                "35": "https://localhost/k=5",
                "37": "127.0.0.1",
                "40": "https://[::1]/k=5",
                "49": "::1",
            }
        )

        self.assertEqual({}, redirects)

    def test_build_connect_redirects_resolves_ips_for_redirected_hosts(self) -> None:
        def fake_resolver(host: str, *_args):
            if host == "world34.runescape.com":
                return [
                    (None, None, None, None, ("8.26.16.159", 0)),
                    (None, None, None, None, ("8.26.16.159", 0)),
                ]
            if host == "content.runescape.com":
                return [
                    (None, None, None, None, ("91.235.140.195", 0)),
                    (None, None, None, None, ("91.235.140.196", 0)),
                ]
            raise OSError("unresolved")

        redirects = build_connect_redirects(
            {
                "world34.runescape.com": "localhost",
                "content.runescape.com": "127.0.0.1",
                "missing.runescape.com": "localhost",
            },
            resolver=fake_resolver,
        )

        self.assertEqual(
            {
                "8.26.16.159": "localhost",
                "91.235.140.195": "127.0.0.1",
                "91.235.140.196": "127.0.0.1",
            },
            redirects,
        )

    def test_rewrite_param_tokens_replaces_only_mapped_values(self) -> None:
        arguments = [
            r"C:\ProgramData\Jagex\launcher\rs2client.exe",
            "35",
            "https://world42.runescape.com/k=5",
            "37",
            "content.runescape.com",
            "launcher",
            "6374",
        ]
        rewritten, changes = rewrite_param_tokens(arguments, {"35": "http://localhost:8080", "37": "localhost"})

        self.assertEqual("http://localhost:8080", rewritten[2])
        self.assertEqual("localhost", rewritten[4])
        self.assertEqual("launcher", rewritten[5])
        self.assertEqual("6374", rewritten[6])
        self.assertEqual(
            [
                {"param": "35", "old": "https://world42.runescape.com/k=5", "new": "http://localhost:8080"},
                {"param": "37", "old": "content.runescape.com", "new": "localhost"},
            ],
            changes,
        )

    def test_tokenize_and_rebuild_round_trip_simple_wrapper_command(self) -> None:
        command_line = (
            '"C:\\ProgramData\\Jagex\\launcher\\rs2client.exe" '
            '"35" "https://world42.runescape.com/k=5" '
            '"37" "content.runescape.com" '
            '"launcher" "6374"'
        )

        tokens = tokenize_windows_command_line(command_line)
        rebuilt = rebuild_windows_command_line(tokens)

        self.assertEqual(
            [
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
                "35",
                "https://world42.runescape.com/k=5",
                "37",
                "content.runescape.com",
                "launcher",
                "6374",
            ],
            tokens,
        )
        self.assertEqual(
            'C:\\ProgramData\\Jagex\\launcher\\rs2client.exe 35 https://world42.runescape.com/k=5 37 content.runescape.com launcher 6374',
            rebuilt,
        )
        self.assertEqual(tokens, tokenize_windows_command_line(rebuilt))

    def test_rewrite_param_tokens_does_not_treat_numeric_values_as_keys(self) -> None:
        arguments = [
            r"C:\ProgramData\Jagex\launcher\rs2client.exe",
            "15",
            "",
            "27",
            "79",
            "26",
            "false",
            "21",
            "loading",
            "launcher",
            "6674",
        ]

        rewritten, changes = rewrite_param_tokens(arguments, {"27": "5", "21": "loading2"})

        self.assertEqual(
            [
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
                "15",
                "",
                "27",
                "5",
                "26",
                "false",
                "21",
                "loading2",
                "launcher",
                "6674",
            ],
            rewritten,
        )
        self.assertEqual(
            [
                {"param": "27", "old": "79", "new": "5"},
                {"param": "21", "old": "loading", "new": "loading2"},
            ],
            changes,
        )

    def test_tokenize_preserves_empty_quoted_arguments(self) -> None:
        command_line = (
            '"C:\\ProgramData\\Jagex\\launcher\\rs2client.exe" '
            '"15" "" "27" "140" "launcher" "635C"'
        )

        tokens = tokenize_windows_command_line(command_line)

        self.assertEqual(
            [
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
                "15",
                "",
                "27",
                "140",
                "launcher",
                "635C",
            ],
            tokens,
        )

    def test_rebuild_windows_command_line_uses_minimal_quoting(self) -> None:
        rebuilt = rebuild_windows_command_line(
            [
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
                "15",
                "",
                "27",
                "140",
                "https://world48.runescape.com/k=5",
                "launcher",
                "635C",
            ]
        )

        self.assertEqual(
            'C:\\ProgramData\\Jagex\\launcher\\rs2client.exe 15 "" 27 140 https://world48.runescape.com/k=5 launcher 635C',
            rebuilt,
        )

    def test_cleanup_spawned_processes_targets_child_before_wrapper_and_dedupes(self) -> None:
        from unittest.mock import patch

        recorded_calls: list[list[str]] = []

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(args, **kwargs):
            recorded_calls.append(list(args))
            return Completed()

        with patch("tools.launch_runescape_wrapper_rewrite.subprocess.run", side_effect=fake_run), patch(
            "tools.launch_runescape_wrapper_rewrite.query_process_path", return_value=None
        ), patch("tools.launch_runescape_wrapper_rewrite.query_process_command_line", return_value=None):
            cleanup_results = cleanup_spawned_processes(200, 100, "missing-child")

        self.assertEqual(
            [
                ["taskkill", "/PID", "100", "/T", "/F"],
                ["taskkill", "/PID", "200", "/T", "/F"],
            ],
            recorded_calls,
        )
        self.assertEqual([100, 200], [entry["pid"] for entry in cleanup_results])

    def test_cleanup_spawned_processes_uses_stop_process_fallback_when_taskkill_leaves_process_alive(self) -> None:
        from unittest.mock import patch

        recorded_calls: list[list[str]] = []

        class Completed:
            def __init__(self, returncode: int = 0) -> None:
                self.returncode = returncode
                self.stdout = ""
                self.stderr = ""

        def fake_run(args, **kwargs):
            recorded_calls.append(list(args))
            return Completed()

        query_results = iter(
            [
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
                None,
                None,
                None,
            ]
        )

        def fake_query_process_path(_pid: int):
            return next(query_results)

        with patch("tools.launch_runescape_wrapper_rewrite.subprocess.run", side_effect=fake_run), patch(
            "tools.launch_runescape_wrapper_rewrite.query_process_path", side_effect=fake_query_process_path
        ), patch("tools.launch_runescape_wrapper_rewrite.query_process_command_line", return_value=None), patch(
            "tools.launch_runescape_wrapper_rewrite.time.sleep"
        ):
            cleanup_results = cleanup_spawned_processes(200, 100, "missing-child")

        self.assertEqual(
            [
                ["taskkill", "/PID", "100", "/T", "/F"],
                ["powershell", "-NoProfile", "-Command", "Stop-Process -Id 100 -Force -ErrorAction SilentlyContinue"],
                ["taskkill", "/PID", "200", "/T", "/F"],
            ],
            recorded_calls,
        )
        self.assertTrue(cleanup_results[0]["aliveAfterTaskkill"])
        self.assertFalse(cleanup_results[0]["aliveAfterFallback"])

    def test_cleanup_wrapper_after_child_ready_skips_termination_to_preserve_child(self) -> None:
        from unittest.mock import patch

        recorded_events: list[dict[str, object]] = []

        with patch(
            "tools.launch_runescape_wrapper_rewrite.query_process_path",
            side_effect=[
                r"C:\RuneScape.exe",
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
            ],
        ), patch(
            "tools.launch_runescape_wrapper_rewrite.query_process_command_line",
            return_value=None,
        ), patch(
            "tools.launch_runescape_wrapper_rewrite.terminate_process_only",
        ) as terminate_process_only:
            result = cleanup_wrapper_after_child_ready(200, 100, recorded_events.append)

        terminate_process_only.assert_not_called()
        self.assertEqual(
            {
                "pid": 200,
                "skipped": True,
                "reason": "preserve-wrapper-child-lifetime",
                "childAliveAfterSkip": True,
            },
            result,
        )
        self.assertEqual("wrapper-cleanup-skipped", recorded_events[0]["action"])

    def test_query_process_helpers_tolerate_timeout(self) -> None:
        from unittest.mock import patch

        timeout = subprocess.TimeoutExpired(cmd=["powershell"], timeout=10)
        with patch("tools.launch_runescape_wrapper_rewrite.subprocess.run", side_effect=timeout):
            self.assertIsNone(query_process_command_line(1234))
            self.assertIsNone(query_process_path(1234))


if __name__ == "__main__":
    unittest.main()
