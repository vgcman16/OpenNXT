import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_CONFIG = ROOT / "data" / "config" / "server.toml"
TOOLS_CONFIG = ROOT / "tools" / "data" / "config" / "server.toml"


def load_bootstrap_table(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)["lobby"]["bootstrap"]


class BootstrapConfigContractTest(unittest.TestCase):
    def assert_bootstrap_contract(self, bootstrap: dict) -> None:
        self.assertFalse(
            bootstrap["sendWorldInitState"],
            "Expected the canonical 946 bootstrap to stay on the stripped world-init path",
        )
        self.assertEqual(
            1,
            bootstrap["worldInterfaceSelfModelComponent"],
            "Expected IF_SETPLAYERMODEL_SELF to stay bound for the world interface",
        )
        self.assertEqual(-1, bootstrap["worldInterfaceSelfHeadComponent"])
        self.assertTrue(bootstrap["openRootInterface"])
        self.assertFalse(
            bootstrap["openSupplementalChildInterfaces"],
            "Expected the canonical 946 bootstrap to stay on the minimal child-interface path",
        )

    def test_main_server_config_uses_canonical_946_bootstrap_shape(self) -> None:
        self.assert_bootstrap_contract(load_bootstrap_table(MAIN_CONFIG))

    def test_tool_server_config_uses_canonical_946_bootstrap_shape(self) -> None:
        self.assert_bootstrap_contract(load_bootstrap_table(TOOLS_CONFIG))


if __name__ == "__main__":
    unittest.main()
