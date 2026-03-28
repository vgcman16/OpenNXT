from __future__ import annotations

import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent


class LocalhostLeafTrustContractTest(unittest.TestCase):
    def test_setup_script_exposes_canonical_mitm_trust_fields(self) -> None:
        text = (TOOLS_DIR / "setup_lobby_tls_cert.ps1").read_text(encoding="utf-8")
        self.assertIn("[string]$PrimaryDnsName", text)
        self.assertIn("[switch]$CheckOnly", text)
        self.assertIn("Resolve-CanonicalPrimaryDnsName", text)
        self.assertIn('$defaultMitmPrimaryHost = "localhost"', text)
        self.assertIn("ActiveSubject", text)
        self.assertIn("ActiveIssuer", text)
        self.assertIn("ActiveThumbprint", text)
        self.assertIn("SanSet", text)
        self.assertIn("TrustedPeopleTrusted", text)
        self.assertIn("LeafRootTrusted", text)
        self.assertIn("DirectLeafTrusted", text)
        self.assertIn("TrustHealthy", text)
        self.assertIn("RemovedTrustedPeopleCount", text)
        self.assertIn("RemovedMyCount", text)
        self.assertIn("RemovedRootCount", text)
        self.assertIn("TrustedRootThumbprint", text)
        self.assertIn("Generate-RootSignedLeafCertificate", text)
        self.assertIn("Ensure-ManagedRootCaArtifacts", text)
        self.assertIn("python-cryptography-root-signed-leaf", text)
        self.assertIn("OpenNXT Local Root", text)
        self.assertIn("opennxt-local-root.crl", text)
        self.assertIn('http://localhost:8080/opennxt-local-root.crl', text)
        self.assertIn("CRLDistributionPoints", text)
        self.assertIn("pkcs12.serialize_key_and_certificates", text)
        self.assertIn("cas=None", text)
        self.assertIn("x509.IPAddress", text)
        self.assertIn('OidValue "2.5.29.15"', text)
        self.assertIn("*.runescape.com", text)
        self.assertIn("*.config.runescape.com", text)
        self.assertIn("if (-not (Find-StoreCertificate -StoreName TrustedPeople -StoreLocation CurrentUser -Thumbprint $leafPublicCert.Thumbprint))", text)

    def test_lobby_proxy_launcher_uses_canonical_primary_leaf(self) -> None:
        text = (TOOLS_DIR / "launch_lobby_tls_terminator.ps1").read_text(encoding="utf-8")
        self.assertIn('[string]$LobbyHost = "localhost"', text)
        self.assertIn("Get-CertInfo -CheckOnly", text)
        self.assertIn('Join-Path $PSScriptRoot "tls_terminate_proxy.py"', text)
        self.assertIn("-DnsName $certificateDnsNames", text)
        self.assertIn("[switch]$InlineProxy", text)
        self.assertIn("if ($InlineProxy)", text)
        self.assertIn("Quote-CmdArgument", text)
        self.assertIn("Start-Process", text)
        self.assertIn("-RedirectStandardOutput $stdout", text)
        self.assertIn("-RedirectStandardError $stderr", text)
        self.assertIn('LaunchMode = "start-process-python"', text)
        self.assertIn("-PrimaryDnsName", text)
        self.assertIn("Resolve-CanonicalMitmPrimaryDnsName", text)
        self.assertIn('$defaultMitmPrimaryHost = "localhost"', text)
        self.assertIn("$LobbyHost", text)
        self.assertIn("Canonical MITM certificate", text)
        self.assertIn('$activePrimaryDnsName', text)
        self.assertIn('$activePfxPath', text)
        self.assertIn('$certInfo.PfxPath', text)
        self.assertIn("DirectLeafTrusted", text)
        self.assertIn('"rs.config.runescape.com"', text)
        self.assertIn("--tls-extra-mitm-host", text)
        self.assertIn("return $defaultMitmPrimaryHost", text)

    def test_watchdog_restarts_lobby_proxy_with_localhost_identity(self) -> None:
        text = (TOOLS_DIR / "keep_local_live_stack.ps1").read_text(encoding="utf-8")
        self.assertIn('$defaultMitmPrimaryHost = "localhost"', text)
        self.assertIn('"-LobbyHost"', text)
        self.assertIn('$defaultMitmPrimaryHost', text)
        self.assertIn("& $lobbyProxyScript @lobbyProxyArgs | Out-Null", text)

    def test_client_launchers_repair_or_block_on_bad_trust(self) -> None:
        for script_name in ("launch-client-only.ps1", "launch-win64c-live.ps1"):
            text = (TOOLS_DIR / script_name).read_text(encoding="utf-8")
            self.assertIn("Ensure-CanonicalMitmTrust", text)
            self.assertIn("-CheckOnly", text)
            self.assertIn('$defaultMitmPrimaryHost = "localhost"', text)
            self.assertIn("return $defaultMitmPrimaryHost", text)
            self.assertIn("TrustHealthy", text)
            self.assertIn("DirectLeafTrusted", text)
            self.assertIn("Canonical MITM TLS trust is unhealthy", text)
            self.assertIn("downloadMetadataSource", text)

        client_only_text = (TOOLS_DIR / "launch-client-only.ps1").read_text(encoding="utf-8")
        self.assertIn('[string]$DownloadMetadataSource = "patched"', client_only_text)
        self.assertIn('Set-QueryParameter -Url $ConfigUrl -Name "downloadMetadataSource"', client_only_text)
        live_text = (TOOLS_DIR / "launch-win64c-live.ps1").read_text(encoding="utf-8")
        self.assertIn("CanonicalMitmTrustState", live_text)
        self.assertIn("tls_terminate_proxy.py", live_text)
        self.assertIn("started lobby proxy launcher pid=", live_text)
        self.assertIn("Start-CanonicalMitmTrustRepair", live_text)
        self.assertIn("started canonical mitm trust repair pid=", live_text)
        self.assertIn("terminated canonical mitm trust repair pid=", live_text)

    def test_watcher_exposes_new_prelogin_tls_states(self) -> None:
        text = (TOOLS_DIR / "watch_rs2client_live.py").read_text(encoding="utf-8")
        self.assertIn("prelogin-raw-game-only", text)
        self.assertIn("prelogin-tls-failed", text)
        self.assertIn("prelogin-mitm-handshake-failed", text)


if __name__ == "__main__":
    unittest.main()
