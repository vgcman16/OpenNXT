from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

try:
    from tools.serve_https_jav_config import build_target_url
except ModuleNotFoundError:
    from serve_https_jav_config import build_target_url


class ServeHttpsJavConfigTest(unittest.TestCase):
    def test_build_target_url_preserves_jav_config_query(self) -> None:
        url = build_target_url(
            "http://127.0.0.1:8080/jav_config.ws",
            "/jav_config.ws?binaryType=6&baseConfigSource=original",
        )

        self.assertEqual(
            "http://127.0.0.1:8080/jav_config.ws?binaryType=6&baseConfigSource=original",
            url,
        )

    def test_build_target_url_preserves_nested_path(self) -> None:
        url = build_target_url(
            "http://127.0.0.1:8080/custom/path",
            "/jav_config.ws?contentRouteRewrite=0",
        )

        self.assertEqual(
            "http://127.0.0.1:8080/jav_config.ws?contentRouteRewrite=0",
            url,
        )


if __name__ == "__main__":
    unittest.main()
