param(
    [string[]]$DnsName = @("lobby46a.runescape.com", "content.runescape.com", "localhost", "127.0.0.1")
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$tlsDir = Join-Path $root "data\tls"
$friendlyName = "OpenNXT Lobby TLS"
$primaryDnsName = $DnsName[0]
$cerPath = Join-Path $tlsDir "$primaryDnsName.cer"
$pfxPath = Join-Path $tlsDir "$primaryDnsName.pfx"
$pfxPassword = "opennxt-dev"

function Split-SanEntries {
    param([string[]]$Names)

    $dnsNames = New-Object System.Collections.Generic.List[string]
    $ipAddresses = New-Object System.Collections.Generic.List[string]

    foreach ($name in $Names) {
        $ip = $null
        if ([System.Net.IPAddress]::TryParse($name, [ref]$ip)) {
            $ipAddresses.Add($name)
        } else {
            $dnsNames.Add($name)
        }
    }

    [pscustomobject]@{
        DnsNames = @($dnsNames)
        IpAddresses = @($ipAddresses)
    }
}

function Test-CertHasRequiredSans {
    param(
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Cert,
        [string[]]$RequiredDnsNames,
        [string[]]$RequiredIpAddresses
    )

    if (-not $Cert) {
        return $false
    }

    $sanExtension = $Cert.Extensions | Where-Object { $_.Oid.Value -eq "2.5.29.17" } | Select-Object -First 1
    if (-not $sanExtension) {
        return $false
    }

    $formatted = $sanExtension.Format($false)
    foreach ($dnsName in $RequiredDnsNames) {
        if ($formatted -notmatch [regex]::Escape("DNS Name=$dnsName")) {
            return $false
        }
    }

    foreach ($ipAddress in $RequiredIpAddresses) {
        if ($formatted -notmatch [regex]::Escape("IP Address=$ipAddress")) {
            return $false
        }
    }

    return $true
}

New-Item -ItemType Directory -Force -Path $tlsDir | Out-Null

$requiredNames = @($DnsName | Sort-Object -Unique)
$sanEntries = Split-SanEntries -Names $requiredNames
$pythonScript = Join-Path $env:TEMP "opennxt-generate-lobby-cert.py"
$pythonScriptContent = @"
import ipaddress
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


cer_path = Path(sys.argv[1])
pfx_path = Path(sys.argv[2])
password = sys.argv[3].encode("utf-8")
primary_dns_name = sys.argv[4]
dns_names = json.loads(os.environ["OPENNXT_TLS_DNS_JSON"])
ip_addresses = json.loads(os.environ["OPENNXT_TLS_IP_JSON"])

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, primary_dns_name)])
san_entries = [x509.DNSName(name) for name in dns_names]
san_entries.extend(x509.IPAddress(ipaddress.ip_address(ip)) for ip in ip_addresses)

now = datetime.now(timezone.utc)
cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(minutes=5))
    .not_valid_after(now + timedelta(days=365 * 5))
    .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
    .add_extension(
        x509.ExtendedKeyUsage(
            [ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]
        ),
        critical=False,
    )
    .sign(private_key=key, algorithm=hashes.SHA256())
)

cer_path.write_bytes(cert.public_bytes(serialization.Encoding.DER))
pfx_path.write_bytes(
    pkcs12.serialize_key_and_certificates(
        primary_dns_name.encode("utf-8"),
        key,
        cert,
        None,
        serialization.BestAvailableEncryption(password),
    )
)
"@

Set-Content -Path $pythonScript -Value $pythonScriptContent -Encoding ASCII

$dnsNamesJson = ConvertTo-Json -InputObject @($sanEntries.DnsNames) -Compress
$ipAddressesJson = ConvertTo-Json -InputObject @($sanEntries.IpAddresses) -Compress

$env:OPENNXT_TLS_DNS_JSON = $dnsNamesJson
$env:OPENNXT_TLS_IP_JSON = $ipAddressesJson

python $pythonScript $cerPath $pfxPath $pfxPassword $primaryDnsName
if ($LASTEXITCODE -ne 0) {
    throw "Failed to generate TLS certificate via Python."
}

Remove-Item $pythonScript -Force -ErrorAction SilentlyContinue
Remove-Item Env:OPENNXT_TLS_DNS_JSON -ErrorAction SilentlyContinue
Remove-Item Env:OPENNXT_TLS_IP_JSON -ErrorAction SilentlyContinue

$importedRoot = Import-Certificate -FilePath $cerPath -CertStoreLocation "Cert:\CurrentUser\Root"
$cert = $importedRoot.Certificate

[pscustomobject]@{
    DnsName = $DnsName
    FriendlyName = $friendlyName
    Thumbprint = if ($cert) { $cert.Thumbprint } else { $null }
    NotAfter = if ($cert) { $cert.NotAfter } else { $null }
    CertificateStore = "Cert:\CurrentUser\Root"
    RootTrusted = $true
    CerPath = $cerPath
    PfxPath = $pfxPath
    PfxPassword = $pfxPassword
} | ConvertTo-Json -Depth 3
