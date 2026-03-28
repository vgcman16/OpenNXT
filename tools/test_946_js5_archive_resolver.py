from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_js5_archive_resolver import build_artifact, render_markdown


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2) + "\n")


class Js5ArchiveResolverTest(unittest.TestCase):
    @patch("run_946_js5_archive_resolver.input_fingerprint", return_value="fingerprint")
    def test_reference_tables_only_session_is_classified(self, _: patch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary_json = root / "summary.json"
            session_jsonl = root / "session.jsonl"
            index_kt = root / "Index.kt"
            prefetch_kt = root / "PrefetchTable.kt"
            write_text(index_kt, "const val INTERFACES = 3\nconst val MAPS = 5\n")
            write_text(prefetch_kt, "IndexPrefetch(Index.INTERFACES)\n")
            write_text(
                session_jsonl,
                "\n".join(
                    [
                        json.dumps(
                            {
                                "eventType": "request_frame",
                                "index": 255,
                                "archive": 18,
                                "label": "reference-table[18]",
                                "relativeMillis": 10,
                            }
                        ),
                        json.dumps(
                            {
                                "eventType": "response_header",
                                "index": 255,
                                "archive": 18,
                                "relativeMillis": 20,
                            }
                        ),
                    ]
                )
                + "\n",
            )
            write_json(
                summary_json,
                {
                    "sessions": [
                        {
                            "sessionId": 1,
                            "sessionJsonl": str(session_jsonl),
                        }
                    ]
                },
            )

            with patch("run_946_js5_archive_resolver.INDEX_KT", index_kt), patch(
                "run_946_js5_archive_resolver.PREFETCH_TABLE_KT", prefetch_kt
            ):
                artifact = build_artifact(
                    SimpleNamespace(
                        js5_session_dir=root,
                        summary_json=summary_json,
                        output_dir=root,
                    )
                )

        self.assertEqual(artifact["status"], "ok")
        self.assertEqual(artifact["summary"]["resolvedArchiveCount"], 1)
        self.assertEqual(artifact["resolutions"][0]["category"], "reference-table")
        self.assertIn("reference-table", render_markdown(artifact))

    @patch("run_946_js5_archive_resolver.input_fingerprint", return_value="fingerprint")
    def test_archive_session_resolves_map_labels(self, _: patch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary_json = root / "summary.json"
            session_jsonl = root / "session.jsonl"
            index_kt = root / "Index.kt"
            prefetch_kt = root / "PrefetchTable.kt"
            write_text(index_kt, "const val MAPS = 5\nconst val INTERFACES = 3\n")
            write_text(prefetch_kt, "ArchivePrefetch(Index.MAPS, 1234)\n")
            write_text(
                session_jsonl,
                "\n".join(
                    [
                        json.dumps(
                            {
                                "eventType": "request_frame",
                                "index": 5,
                                "archive": 1234,
                                "label": "archive[5,1234]",
                                "relativeMillis": 25,
                            }
                        ),
                        json.dumps(
                            {
                                "eventType": "response_header",
                                "index": 5,
                                "archive": 1234,
                                "relativeMillis": 40,
                            }
                        ),
                    ]
                )
                + "\n",
            )
            write_json(summary_json, {"sessions": [{"sessionId": 9, "sessionJsonl": str(session_jsonl)}]})

            with patch("run_946_js5_archive_resolver.INDEX_KT", index_kt), patch(
                "run_946_js5_archive_resolver.PREFETCH_TABLE_KT", prefetch_kt
            ):
                artifact = build_artifact(
                    SimpleNamespace(
                        js5_session_dir=root,
                        summary_json=summary_json,
                        output_dir=root,
                    )
                )

        self.assertEqual(artifact["resolutions"][0]["category"], "map/region-related")
        self.assertTrue(artifact["resolutions"][0]["prefetchedByDefault"])

    @patch("run_946_js5_archive_resolver.input_fingerprint", return_value="fingerprint")
    def test_unresolved_archives_remain_explicit(self, _: patch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary_json = root / "summary.json"
            session_jsonl = root / "session.jsonl"
            index_kt = root / "Index.kt"
            prefetch_kt = root / "PrefetchTable.kt"
            write_text(index_kt, "const val MAPS = 5\n")
            write_text(prefetch_kt, "")
            write_text(
                session_jsonl,
                json.dumps(
                    {
                        "eventType": "request_frame",
                        "index": 77,
                        "archive": 9,
                        "relativeMillis": 5,
                    }
                )
                + "\n",
            )
            write_json(summary_json, {"sessions": [{"sessionId": 2, "sessionJsonl": str(session_jsonl)}]})

            with patch("run_946_js5_archive_resolver.INDEX_KT", index_kt), patch(
                "run_946_js5_archive_resolver.PREFETCH_TABLE_KT", prefetch_kt
            ):
                artifact = build_artifact(
                    SimpleNamespace(
                        js5_session_dir=root,
                        summary_json=summary_json,
                        output_dir=root,
                    )
                )

        self.assertEqual(artifact["resolutions"][0]["category"], "unresolved")
        self.assertIn("archive[77,9]", artifact["resolutions"][0]["label"])


if __name__ == "__main__":
    unittest.main()
