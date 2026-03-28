param(
    [string[]]$DnsName = @("lobby45a.runescape.com", "content.runescape.com", "localhost", "127.0.0.1", "::1"),
    [string]$PrimaryDnsName = "",
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

if (-not (Get-PSDrive -Name Cert -ErrorAction SilentlyContinue)) {
    try {
        New-PSDrive -Name Cert -PSProvider Certificate -Root "\" | Out-Null
    } catch {
    }
}

$root = Split-Path -Parent $PSScriptRoot
$tlsDir = Join-Path $root "data\tls"
$friendlyName = "OpenNXT Lobby TLS"
$legacyRootCaName = "OpenNXT Local Root"
$pfxPassword = "opennxt-dev"
$rootCaCerName = "opennxt-local-root.cer"
$rootCaPfxName = "opennxt-local-root.pfx"
$rootCaCrlName = "opennxt-local-root.crl"
$rootCaCrlUrl = "http://localhost:8080/opennxt-local-root.crl"
$defaultManagedHosts = @(
    "localhost",
    "127.0.0.1",
    "::1",
    "rs.config.runescape.com",
    "content.runescape.com",
    "lobby45a.runescape.com",
    "lobby46a.runescape.com"
)
$defaultMitmPrimaryHost = "localhost"
$directLeafProfileVersion = 5

function Normalize-DnsNames {
    param([string[]]$Names)

    $normalized = New-Object System.Collections.Generic.List[string]
    foreach ($name in $Names) {
        if ([string]::IsNullOrWhiteSpace($name)) {
            continue
        }
        foreach ($piece in ($name -split ",")) {
            $trimmed = $piece.Trim()
            if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
                $normalized.Add($trimmed)
                $lowerTrimmed = $trimmed.ToLowerInvariant()
                if (
                    [string]::Equals($lowerTrimmed, "*.runescape.com", [System.StringComparison]::OrdinalIgnoreCase) -or
                    [string]::Equals($lowerTrimmed, "*.config.runescape.com", [System.StringComparison]::OrdinalIgnoreCase)
                ) {
                    continue
                }

                if ($lowerTrimmed.EndsWith(".config.runescape.com")) {
                    $label = $lowerTrimmed.Substring(0, $lowerTrimmed.Length - ".config.runescape.com".Length)
                    if (-not [string]::IsNullOrWhiteSpace($label) -and $label -notmatch '\.') {
                        $normalized.Add("*.config.runescape.com")
                    }
                    continue
                }

                if ($lowerTrimmed.EndsWith(".runescape.com")) {
                    $label = $lowerTrimmed.Substring(0, $lowerTrimmed.Length - ".runescape.com".Length)
                    if (-not [string]::IsNullOrWhiteSpace($label) -and $label -notmatch '\.') {
                        $normalized.Add("*.runescape.com")
                    }
                }
            }
        }
    }

    return @($normalized | Select-Object -Unique)
}

function Reorder-DnsNames {
    param(
        [string[]]$Names,
        [string]$PreferredPrimary
    )

    $ordered = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($PreferredPrimary)) {
        $ordered.Add($PreferredPrimary)
    }
    foreach ($name in $Names) {
        if (-not [string]::IsNullOrWhiteSpace($name) -and $ordered -notcontains $name) {
            $ordered.Add($name)
        }
    }

    return @($ordered)
}

function Resolve-CanonicalPrimaryDnsName {
    param(
        [string]$RequestedPrimaryDnsName,
        [string[]]$AllDnsNames
    )

    if (-not [string]::IsNullOrWhiteSpace($RequestedPrimaryDnsName)) {
        if ($RequestedPrimaryDnsName -in @("127.0.0.1", "::1")) {
            return "localhost"
        }
        return $RequestedPrimaryDnsName
    }

    foreach ($candidate in @($AllDnsNames)) {
        if ([string]::IsNullOrWhiteSpace($candidate)) {
            continue
        }
        if ($candidate -in @("127.0.0.1", "::1", "localhost")) {
            continue
        }
        if ($candidate -eq "content.runescape.com") {
            continue
        }
        return $candidate
    }

    foreach ($candidate in @($AllDnsNames)) {
        if ([string]::IsNullOrWhiteSpace($candidate)) {
            continue
        }
        if ($candidate -in @("127.0.0.1", "::1", "localhost")) {
            continue
        }
        return $candidate
    }

    return $defaultMitmPrimaryHost
}

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

function Get-IpAddressSanRepresentations {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return @()
    }

    $ip = $null
    if (-not [System.Net.IPAddress]::TryParse($Value, [ref]$ip)) {
        return @($Value)
    }

    $representations = New-Object System.Collections.Generic.List[string]
    $representations.Add($Value)
    $canonical = $ip.ToString()
    if ($representations -notcontains $canonical) {
        $representations.Add($canonical)
    }

    if ($ip.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetworkV6) {
        $bytes = $ip.GetAddressBytes()
        $segments = for ($index = 0; $index -lt $bytes.Length; $index += 2) {
            "{0:x4}" -f (($bytes[$index] -shl 8) -bor $bytes[$index + 1])
        }
        $expanded = $segments -join ":"
        if ($representations -notcontains $expanded) {
            $representations.Add($expanded)
        }
        $expandedUpper = $expanded.ToUpperInvariant()
        if ($representations -notcontains $expandedUpper) {
            $representations.Add($expandedUpper)
        }
    }

    return @($representations | Select-Object -Unique)
}

function Get-ManagedSubjects {
    param([string[]]$DnsNames)

    $subjects = New-Object System.Collections.Generic.List[string]
    foreach ($name in (@($defaultManagedHosts) + @($DnsNames))) {
        if ([string]::IsNullOrWhiteSpace($name)) {
            continue
        }
        $subject = "CN=$name"
        if ($subjects -notcontains $subject) {
            $subjects.Add($subject)
        }
    }
    $legacyRootSubject = "CN=$legacyRootCaName"
    if ($subjects -notcontains $legacyRootSubject) {
        $subjects.Add($legacyRootSubject)
    }
    return @($subjects)
}

function Get-StoreCertificates {
    param(
        [System.Security.Cryptography.X509Certificates.StoreName]$StoreName,
        [System.Security.Cryptography.X509Certificates.StoreLocation]$StoreLocation
    )

    $store = [System.Security.Cryptography.X509Certificates.X509Store]::new($StoreName, $StoreLocation)
    try {
        $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadOnly)
        return @($store.Certificates)
    } finally {
        $store.Close()
    }
}

function Find-StoreCertificate {
    param(
        [System.Security.Cryptography.X509Certificates.StoreName]$StoreName,
        [System.Security.Cryptography.X509Certificates.StoreLocation]$StoreLocation,
        [string]$Thumbprint
    )

    return Get-StoreCertificates -StoreName $StoreName -StoreLocation $StoreLocation |
        Where-Object { $_.Thumbprint -eq $Thumbprint } |
        Select-Object -First 1
}

function Remove-StoreCertificates {
    param(
        [System.Security.Cryptography.X509Certificates.StoreName]$StoreName,
        [System.Security.Cryptography.X509Certificates.StoreLocation]$StoreLocation,
        [scriptblock]$Filter
    )

    $removedCount = 0
    $store = [System.Security.Cryptography.X509Certificates.X509Store]::new($StoreName, $StoreLocation)
    try {
        $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $matches = @($store.Certificates | Where-Object { & $Filter $_ })
        foreach ($match in $matches) {
            try {
                $store.Remove($match)
                $removedCount += 1
            } catch {
            }
        }
    } finally {
        $store.Close()
    }

    return $removedCount
}

function Invoke-CertUtil {
    param([string[]]$Arguments)

    & certutil @Arguments | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "certutil failed with exit code $LASTEXITCODE for arguments: $($Arguments -join ' ')"
    }
}

function Load-PfxCertificate {
    param(
        [string]$Path,
        [string]$Password
    )

    if (-not (Test-Path $Path)) {
        return $null
    }

    return [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
        $Path,
        $Password,
        [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable -bor
        [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::PersistKeySet
    )
}

function Load-CertificateFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return $null
    }

    return [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($Path)
}

function Get-LeafMetadataPath {
    param([string]$PfxPath)

    return "$PfxPath.metadata.json"
}

function Test-IsExpectedLeafMetadata {
    param(
        [string]$MetadataPath,
        [string]$ExpectedPrimaryDnsName
    )

    if (-not (Test-Path $MetadataPath)) {
        return $false
    }

    try {
        $metadata = Get-Content $MetadataPath -Raw | ConvertFrom-Json
    } catch {
        return $false
    }

    return (
        [int]$metadata.Version -eq $directLeafProfileVersion -and
        [string]$metadata.Generator -eq "python-cryptography-root-signed-leaf" -and
        [string]$metadata.PrimaryDnsName -eq $ExpectedPrimaryDnsName
    )
}

function Write-LeafMetadata {
    param(
        [string]$MetadataPath,
        [string]$PrimaryDnsName
    )

    [pscustomobject]@{
        Generator = "python-cryptography-root-signed-leaf"
        Version = $directLeafProfileVersion
        PrimaryDnsName = $PrimaryDnsName
        GeneratedAt = (Get-Date).ToString("o")
    } | ConvertTo-Json -Depth 3 | Set-Content -Path $MetadataPath -Encoding UTF8
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
    $sanDnsNames = @(
        [regex]::Matches($formatted, 'DNS Name=([^,]+)') |
            ForEach-Object { $_.Groups[1].Value.Trim() } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            Select-Object -Unique
    )
    foreach ($dnsName in $RequiredDnsNames) {
        $matched = $formatted -match [regex]::Escape("DNS Name=$dnsName")
        if (-not $matched) {
            foreach ($sanDnsName in $sanDnsNames) {
                if (-not $sanDnsName.StartsWith("*.")) {
                    continue
                }

                $suffix = $sanDnsName.Substring(1)
                if (-not $dnsName.EndsWith($suffix, [System.StringComparison]::OrdinalIgnoreCase)) {
                    continue
                }

                $prefix = $dnsName.Substring(0, $dnsName.Length - $suffix.Length)
                if (-not [string]::IsNullOrWhiteSpace($prefix) -and $prefix -notmatch '\.') {
                    $matched = $true
                    break
                }
            }
        }
        if (-not $matched) {
            return $false
        }
    }
    foreach ($ipAddress in $RequiredIpAddresses) {
        $ipMatches = @(Get-IpAddressSanRepresentations -Value $ipAddress)
        $matched = $false
        foreach ($candidate in $ipMatches) {
            if (
                $formatted -match [regex]::Escape("IP Address=$candidate") -or
                $formatted -match [regex]::Escape("DNS Name=$candidate")
            ) {
                $matched = $true
                break
            }
        }
        if (-not $matched) {
            return $false
        }
    }

    return $true
}

function Test-CertHasRequiredServerEku {
    param([System.Security.Cryptography.X509Certificates.X509Certificate2]$Cert)

    if (-not $Cert) {
        return $false
    }

    $ekuExtension = $Cert.Extensions |
        Where-Object { $_ -is [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension] } |
        Select-Object -First 1
    if (-not $ekuExtension) {
        return $false
    }

    return @($ekuExtension.EnhancedKeyUsages | ForEach-Object { $_.Value }) -contains "1.3.6.1.5.5.7.3.1"
}

function Test-IsExpectedLeafCertificate {
    param(
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Cert,
        [string]$ExpectedPrimaryDnsName,
        [string[]]$RequiredDnsNames,
        [string[]]$RequiredIpAddresses
    )

    if (-not $Cert) {
        return $false
    }
    if ($Cert.Subject -ne "CN=$ExpectedPrimaryDnsName") {
        return $false
    }
    if ($Cert.Issuer -ne $Cert.Subject) {
        return $false
    }
    if ($Cert.NotAfter -le (Get-Date).AddDays(7)) {
        return $false
    }
    if (-not (Test-CertHasRequiredServerEku -Cert $Cert)) {
        return $false
    }
    if (-not (Test-CertHasRequiredExtension -Cert $Cert -OidValue "2.5.29.15")) {
        return $false
    }

    return Test-CertHasRequiredSans -Cert $Cert -RequiredDnsNames $RequiredDnsNames -RequiredIpAddresses $RequiredIpAddresses
}

function Test-IsExpectedRootSignedLeafCertificate {
    param(
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Cert,
        [string]$ExpectedPrimaryDnsName,
        [string]$ExpectedIssuerCommonName,
        [string[]]$RequiredDnsNames,
        [string[]]$RequiredIpAddresses
    )

    if (-not $Cert) {
        return $false
    }
    if ($Cert.Subject -ne "CN=$ExpectedPrimaryDnsName") {
        return $false
    }
    if ($Cert.Issuer -ne "CN=$ExpectedIssuerCommonName") {
        return $false
    }
    if ($Cert.Subject -eq $Cert.Issuer) {
        return $false
    }
    if ($Cert.NotAfter -le (Get-Date).AddDays(7)) {
        return $false
    }
    if (-not (Test-CertHasRequiredServerEku -Cert $Cert)) {
        return $false
    }

    return Test-CertHasRequiredSans -Cert $Cert -RequiredDnsNames $RequiredDnsNames -RequiredIpAddresses $RequiredIpAddresses
}

function Test-IsExpectedRootCertificate {
    param(
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Cert,
        [string]$ExpectedSubjectCommonName
    )

    if (-not $Cert) {
        return $false
    }
    if ($Cert.Subject -ne "CN=$ExpectedSubjectCommonName") {
        return $false
    }
    if ($Cert.Issuer -ne $Cert.Subject) {
        return $false
    }
    if ($Cert.NotAfter -le (Get-Date).AddDays(30)) {
        return $false
    }
    if (-not (Test-CertHasRequiredExtension -Cert $Cert -OidValue "2.5.29.19")) {
        return $false
    }
    if (-not (Test-CertHasRequiredExtension -Cert $Cert -OidValue "2.5.29.15")) {
        return $false
    }

    return $true
}

function Ensure-ManagedRootCaArtifacts {
    param(
        [string]$RootCerPath,
        [string]$RootPfxPath,
        [string]$RootCrlPath,
        [string]$Password,
        [string]$RootName,
        [switch]$CheckOnly
    )

    $rootCert = Load-PfxCertificate -Path $RootPfxPath -Password $Password
    $rootIsCanonical = (
        (Test-Path $RootCerPath) -and
        (Test-Path $RootPfxPath) -and
        (Test-Path $RootCrlPath) -and
        (Test-IsExpectedRootCertificate -Cert $rootCert -ExpectedSubjectCommonName $RootName)
    )
    $reusedExisting = $rootIsCanonical

    if (-not $CheckOnly -and -not $rootIsCanonical) {
        $generatorScriptPath = Join-Path $env:TEMP "opennxt-generate-root-ca.py"
        $generatorScript = @"
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

root_cer_path = Path(sys.argv[1])
root_pfx_path = Path(sys.argv[2])
root_crl_path = Path(sys.argv[3])
password = sys.argv[4].encode("utf-8")
root_name = sys.argv[5]

root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, root_name)])
now = datetime.now(timezone.utc)
root_cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(root_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(days=1))
    .not_valid_after(now + timedelta(days=3650))
    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    .add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=True,
            crl_sign=True,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    )
    .add_extension(x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()), critical=False)
    .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
    .sign(private_key=root_key, algorithm=hashes.SHA256())
)

crl = (
    x509.CertificateRevocationListBuilder()
    .issuer_name(root_cert.subject)
    .last_update(now - timedelta(days=1))
    .next_update(now + timedelta(days=365))
    .sign(private_key=root_key, algorithm=hashes.SHA256())
)

root_cer_path.write_bytes(root_cert.public_bytes(serialization.Encoding.DER))
root_crl_path.write_bytes(crl.public_bytes(serialization.Encoding.DER))
root_pfx_path.write_bytes(
    pkcs12.serialize_key_and_certificates(
        name=root_name.encode("utf-8"),
        key=root_key,
        cert=root_cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password),
    )
)
"@

        [System.IO.File]::WriteAllText($generatorScriptPath, $generatorScript, [System.Text.Encoding]::ASCII)
        try {
            & python $generatorScriptPath `
                $RootCerPath `
                $RootPfxPath `
                $RootCrlPath `
                $Password `
                $RootName
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to generate OpenNXT local root CA artifacts via Python cryptography."
            }
        } finally {
            Remove-Item $generatorScriptPath -Force -ErrorAction SilentlyContinue
        }

        $rootCert = Load-PfxCertificate -Path $RootPfxPath -Password $Password
        $rootIsCanonical = (
            (Test-Path $RootCerPath) -and
            (Test-Path $RootPfxPath) -and
            (Test-Path $RootCrlPath) -and
            (Test-IsExpectedRootCertificate -Cert $rootCert -ExpectedSubjectCommonName $RootName)
        )
        if (-not $rootIsCanonical) {
            throw "Unable to create canonical OpenNXT local root CA artifacts."
        }
        $reusedExisting = $false
    }

    [pscustomobject]@{
        RootCert = $rootCert
        RootCerPath = $RootCerPath
        RootPfxPath = $RootPfxPath
        RootCrlPath = $RootCrlPath
        CrlUrl = $rootCaCrlUrl
        ReusedExisting = $reusedExisting
    }
}

function Test-IsManagedLobbyTlsCertificate {
    param(
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Cert,
        [string[]]$ManagedSubjects
    )

    if (-not $Cert) {
        return $false
    }
    if ($Cert.FriendlyName -eq $friendlyName) {
        return $true
    }
    return $ManagedSubjects -contains $Cert.Subject
}

function Test-CertHasRequiredExtension {
    param(
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Cert,
        [string]$OidValue
    )

    if (-not $Cert) {
        return $false
    }

    return [bool]($Cert.Extensions | Where-Object { $_.Oid.Value -eq $OidValue } | Select-Object -First 1)
}

function Generate-DirectLeafCertificate {
    param(
        [string]$CerPath,
        [string]$PfxPath,
        [string]$PrimaryName,
        [string[]]$AllDnsNames,
        [string[]]$AllIpAddresses
    )

    $allDnsNames = @($AllDnsNames | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
    $allIpAddresses = @($AllIpAddresses | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
    $certificateNames = @($PrimaryName) + $allDnsNames + $allIpAddresses | Select-Object -Unique

    $generatorScriptPath = Join-Path $env:TEMP "opennxt-generate-direct-lobby-cert.py"
    $generatorScript = @"
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

leaf_cer_path = Path(sys.argv[1])
leaf_pfx_path = Path(sys.argv[2])
password = sys.argv[3].encode("utf-8")
primary_name = sys.argv[4]
dns_names = [value for value in sys.argv[5].split(",") if value]
ip_values = [value for value in sys.argv[6].split(",") if value]

leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, primary_name)])
san_entries = [x509.DNSName(name) for name in dns_names]
for value in ip_values:
    san_entries.append(x509.IPAddress(ip_address(value)))

now = datetime.now(timezone.utc)
builder = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(leaf_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(days=1))
    .not_valid_after(now + timedelta(days=1825))
    .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
    .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=True,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    )
    .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False)
    .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(leaf_key.public_key()), critical=False)
)
leaf_cert = builder.sign(private_key=leaf_key, algorithm=hashes.SHA256())

leaf_cer_path.write_bytes(leaf_cert.public_bytes(serialization.Encoding.DER))
leaf_pfx_path.write_bytes(
    pkcs12.serialize_key_and_certificates(
        name=primary_name.encode("utf-8"),
        key=leaf_key,
        cert=leaf_cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password),
    )
)
"@

    [System.IO.File]::WriteAllText($generatorScriptPath, $generatorScript, [System.Text.Encoding]::ASCII)
    try {
        & python $generatorScriptPath `
            $CerPath `
            $PfxPath `
            $pfxPassword `
            $PrimaryName `
            ($allDnsNames -join ",") `
            ($allIpAddresses -join ",")
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to generate self-signed MITM TLS certificate via Python cryptography."
        }
    } finally {
        Remove-Item $generatorScriptPath -Force -ErrorAction SilentlyContinue
    }
}

function Generate-RootSignedLeafCertificate {
    param(
        [string]$CerPath,
        [string]$PfxPath,
        [string]$RootCerPath,
        [string]$RootPfxPath,
        [string]$PrimaryName,
        [string[]]$AllDnsNames,
        [string[]]$AllIpAddresses,
        [string]$Password,
        [string]$CrlUrl
    )

    $allDnsNames = @($AllDnsNames | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
    $allIpAddresses = @($AllIpAddresses | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
    $generatorScriptPath = Join-Path $env:TEMP "opennxt-generate-root-signed-lobby-cert.py"
    $generatorScript = @"
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

root_pfx_path = Path(sys.argv[1])
root_cer_path = Path(sys.argv[2])
leaf_cer_path = Path(sys.argv[3])
leaf_pfx_path = Path(sys.argv[4])
password = sys.argv[5].encode("utf-8")
primary_name = sys.argv[6]
dns_names = [value for value in sys.argv[7].split(",") if value]
ip_values = [value for value in sys.argv[8].split(",") if value]
crl_url = sys.argv[9]

root_key, root_cert, root_chain = pkcs12.load_key_and_certificates(root_pfx_path.read_bytes(), password)
if root_key is None or root_cert is None:
    raise RuntimeError(f"Unable to load root CA from {root_pfx_path}")

leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, primary_name)])
san_entries = [x509.DNSName(name) for name in dns_names]
for value in ip_values:
    san_entries.append(x509.IPAddress(ip_address(value)))

now = datetime.now(timezone.utc)
builder = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(root_cert.subject)
    .public_key(leaf_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(days=1))
    .not_valid_after(now + timedelta(days=1825))
    .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
    .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=True,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    )
    .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False)
    .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
    .add_extension(
        x509.CRLDistributionPoints([
            x509.DistributionPoint(
                full_name=[x509.UniformResourceIdentifier(crl_url)],
                relative_name=None,
                reasons=None,
                crl_issuer=None,
            )
        ]),
        critical=False,
    )
)
leaf_cert = builder.sign(private_key=root_key, algorithm=hashes.SHA256())

leaf_cer_path.write_bytes(leaf_cert.public_bytes(serialization.Encoding.DER))
leaf_pfx_path.write_bytes(
    pkcs12.serialize_key_and_certificates(
        name=primary_name.encode("utf-8"),
        key=leaf_key,
        cert=leaf_cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password),
    )
)
"@

    [System.IO.File]::WriteAllText($generatorScriptPath, $generatorScript, [System.Text.Encoding]::ASCII)
    try {
        & python $generatorScriptPath `
            $RootPfxPath `
            $RootCerPath `
            $CerPath `
            $PfxPath `
            $Password `
            $PrimaryName `
            ($allDnsNames -join ",") `
            ($allIpAddresses -join ",") `
            $CrlUrl
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to generate root-signed MITM TLS certificate via Python cryptography."
        }
    } finally {
        Remove-Item $generatorScriptPath -Force -ErrorAction SilentlyContinue
    }
}

function Import-LeafToStores {
    param(
        [string]$CerPath,
        [string]$PfxPath,
        [string]$Password
    )

    $leafCert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
        $PfxPath,
        $Password,
        [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable -bor
        [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::PersistKeySet
    )
    $leafCert.FriendlyName = $friendlyName

    $myStore = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        [System.Security.Cryptography.X509Certificates.StoreName]::My,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    $rootStore = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        [System.Security.Cryptography.X509Certificates.StoreName]::Root,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    try {
        $myStore.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $rootStore.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $myStore.Add($leafCert)
        $rootStore.Add([System.Security.Cryptography.X509Certificates.X509Certificate2]::new($CerPath))
    } finally {
        $myStore.Close()
        $rootStore.Close()
    }

    [pscustomobject]@{
        LeafCert = $leafCert
        RootCert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($CerPath)
    }
}

function Import-RootSignedLeafToStores {
    param(
        [string]$LeafPfxPath,
        [string]$LeafCerPath,
        [string]$RootCerPath,
        [string]$Password
    )

    $leafCert = Load-PfxCertificate -Path $LeafPfxPath -Password $Password
    if ($leafCert) {
        $leafCert.FriendlyName = $friendlyName
    }
    $leafPublicCert = Load-CertificateFile -Path $LeafCerPath
    $rootCert = Load-CertificateFile -Path $RootCerPath

    $trustedPeopleStore = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        [System.Security.Cryptography.X509Certificates.StoreName]::TrustedPeople,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    $rootStore = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        [System.Security.Cryptography.X509Certificates.StoreName]::Root,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    $myStore = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        [System.Security.Cryptography.X509Certificates.StoreName]::My,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    try {
        $trustedPeopleStore.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $rootStore.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $myStore.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        if ($leafPublicCert) {
            if (-not (Find-StoreCertificate -StoreName TrustedPeople -StoreLocation CurrentUser -Thumbprint $leafPublicCert.Thumbprint)) {
                $trustedPeopleStore.Add($leafPublicCert)
            }
        }
        if ($rootCert) {
            if (-not (Find-StoreCertificate -StoreName Root -StoreLocation CurrentUser -Thumbprint $rootCert.Thumbprint)) {
                $rootStore.Add($rootCert)
            }
        }
        if ($leafCert) {
            if (-not (Find-StoreCertificate -StoreName My -StoreLocation CurrentUser -Thumbprint $leafCert.Thumbprint)) {
                $myStore.Add($leafCert)
            }
        }
    } finally {
        $trustedPeopleStore.Close()
        $rootStore.Close()
        $myStore.Close()
    }

    [pscustomobject]@{
        LeafCert = $leafCert
        LeafPublicCert = $leafPublicCert
        RootCert = $rootCert
    }
}

function Ensure-LeafPresentInMyStore {
    param(
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$LeafCert
    )

    if (-not $LeafCert) {
        return
    }

    $myStore = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        [System.Security.Cryptography.X509Certificates.StoreName]::My,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    try {
        $myStore.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $existing = @($myStore.Certificates | Where-Object { $_.Thumbprint -eq $LeafCert.Thumbprint })
        if ($existing.Count -eq 0) {
            $myStore.Add($LeafCert)
        }
    } finally {
        $myStore.Close()
    }
}

function Cleanup-LobbyTlsStoreState {
    param(
        [string]$LeafThumbprint,
        [string]$ActiveSubject,
        [string]$TrustedRootThumbprint = "",
        [string[]]$ManagedSubjects = @()
    )

    $removedMy = Remove-StoreCertificates -StoreName My -StoreLocation CurrentUser -Filter {
        param($certificate)
        $certificate.Thumbprint -ne $LeafThumbprint -and
        (Test-IsManagedLobbyTlsCertificate -Cert $certificate -ManagedSubjects $ManagedSubjects)
    }
    $removedTrustedPeople = Remove-StoreCertificates -StoreName TrustedPeople -StoreLocation CurrentUser -Filter {
        param($certificate)
        $certificate.Thumbprint -ne $LeafThumbprint -and
        (Test-IsManagedLobbyTlsCertificate -Cert $certificate -ManagedSubjects $ManagedSubjects)
    }

    $removedRoot = Remove-StoreCertificates -StoreName Root -StoreLocation CurrentUser -Filter {
        param($certificate)
        $certificate.Thumbprint -ne $LeafThumbprint -and
        (
            [string]::IsNullOrWhiteSpace($TrustedRootThumbprint) -or
            $certificate.Thumbprint -ne $TrustedRootThumbprint
        ) -and
        (Test-IsManagedLobbyTlsCertificate -Cert $certificate -ManagedSubjects $ManagedSubjects)
    }

    [pscustomobject]@{
        RemovedMyCount = $removedMy
        RemovedTrustedPeopleCount = $removedTrustedPeople
        RemovedRootCount = $removedRoot
    }
}

function Build-ResultPayload {
    param(
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$LeafCert,
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$TrustedRootCert = $null,
        [string[]]$DnsNames,
        [string]$PrimaryName,
        [string]$LeafCerPath,
        [string]$LeafPfxPath,
        [bool]$ReusedExisting,
        [int]$RemovedMyCount,
        [int]$RemovedTrustedPeopleCount,
        [int]$RemovedRootCount,
        [string]$RootCerPath = "",
        [string]$RootPfxPath = "",
        [string]$RootCrlPath = "",
        [string]$CrlUrl = ""
    )

    $leafThumbprint = if ($LeafCert) { $LeafCert.Thumbprint } else { $null }
    $myTrusted = [bool]$leafThumbprint -and [bool](Find-StoreCertificate -StoreName My -StoreLocation CurrentUser -Thumbprint $leafThumbprint)
    $trustedPeopleTrusted = [bool]$leafThumbprint -and [bool](Find-StoreCertificate -StoreName TrustedPeople -StoreLocation CurrentUser -Thumbprint $leafThumbprint)
    $leafRootTrusted = [bool]$leafThumbprint -and [bool](Find-StoreCertificate -StoreName Root -StoreLocation CurrentUser -Thumbprint $leafThumbprint)
    $directLeafTrusted = $trustedPeopleTrusted -or $leafRootTrusted
    $rootTrusted = if ($TrustedRootCert) {
        [bool](Find-StoreCertificate -StoreName Root -StoreLocation CurrentUser -Thumbprint $TrustedRootCert.Thumbprint)
    } else {
        $leafRootTrusted
    }

    [pscustomobject]@{
        DnsName = $DnsNames
        PrimaryDnsName = $PrimaryName
        FriendlyName = $friendlyName
        ActiveSubject = if ($LeafCert) { $LeafCert.Subject } else { "CN=$PrimaryName" }
        ActiveIssuer = if ($LeafCert) { $LeafCert.Issuer } else { "CN=$PrimaryName" }
        ActiveThumbprint = $leafThumbprint
        Thumbprint = $leafThumbprint
        NotAfter = if ($LeafCert) { $LeafCert.NotAfter } else { $null }
        SanSet = @($DnsNames)
        CertificateStore = if ($trustedPeopleTrusted) {
            "Microsoft.PowerShell.Security\\Certificate::CurrentUser\\TrustedPeople"
        } elseif ($leafRootTrusted) {
            "Microsoft.PowerShell.Security\\Certificate::CurrentUser\\Root"
        } elseif ($myTrusted) {
            "Microsoft.PowerShell.Security\\Certificate::CurrentUser\\My"
        } else {
            $null
        }
        MyTrusted = $myTrusted
        TrustedPeopleTrusted = $trustedPeopleTrusted
        LeafRootTrusted = $leafRootTrusted
        DirectLeafTrusted = $directLeafTrusted
        RootTrusted = $rootTrusted
        TrustHealthy = [bool](
            $leafThumbprint -and
            (Test-Path $LeafPfxPath) -and
            (Test-Path $LeafCerPath) -and
            $directLeafTrusted -and
            $rootTrusted
        )
        ReusedExisting = $ReusedExisting
        RemovedMyCount = $RemovedMyCount
        RemovedTrustedPeopleCount = $RemovedTrustedPeopleCount
        RemovedRootCount = $RemovedRootCount
        CerPath = $LeafCerPath
        PfxPath = $LeafPfxPath
        PfxPassword = $pfxPassword
        RootCaName = if ($TrustedRootCert) { $TrustedRootCert.Subject } else { "CN=$legacyRootCaName" }
        RootCaThumbprint = if ($TrustedRootCert) { $TrustedRootCert.Thumbprint } else { $null }
        RootCaCerPath = $RootCerPath
        RootCaPfxPath = $RootPfxPath
        RootCaCrlPath = $RootCrlPath
        CrlUrl = $CrlUrl
    }
}

New-Item -ItemType Directory -Force -Path $tlsDir | Out-Null

$DnsName = Normalize-DnsNames -Names $DnsName
if ([string]::IsNullOrWhiteSpace($PrimaryDnsName)) {
    $PrimaryDnsName = if ($DnsName.Count -gt 0) { $DnsName[0] } else { "localhost" }
}
$PrimaryDnsName = Resolve-CanonicalPrimaryDnsName -RequestedPrimaryDnsName $PrimaryDnsName -AllDnsNames $DnsName
$DnsName = Reorder-DnsNames -Names $DnsName -PreferredPrimary $PrimaryDnsName
$primaryDnsName = $DnsName[0]
$leafCerPath = Join-Path $tlsDir "$primaryDnsName.cer"
$leafPfxPath = Join-Path $tlsDir "$primaryDnsName.pfx"
$leafMetadataPath = Get-LeafMetadataPath -PfxPath $leafPfxPath
$rootCerPath = Join-Path $tlsDir $rootCaCerName
$rootPfxPath = Join-Path $tlsDir $rootCaPfxName
$rootCrlPath = Join-Path $tlsDir $rootCaCrlName
$sanEntries = Split-SanEntries -Names $DnsName
$managedSubjects = Get-ManagedSubjects -DnsNames $DnsName

$rootState = Ensure-ManagedRootCaArtifacts `
    -RootCerPath $rootCerPath `
    -RootPfxPath $rootPfxPath `
    -RootCrlPath $rootCrlPath `
    -Password $pfxPassword `
    -RootName $legacyRootCaName `
    -CheckOnly:$CheckOnly
$trustedRootCert = $rootState.RootCert
$leafCert = Load-PfxCertificate -Path $leafPfxPath -Password $pfxPassword
$reusedExisting = $false
$removedMyCount = 0
$removedTrustedPeopleCount = 0
$removedRootCount = 0
$leafIsCanonical = Test-IsExpectedRootSignedLeafCertificate `
    -Cert $leafCert `
    -ExpectedPrimaryDnsName $primaryDnsName `
    -ExpectedIssuerCommonName $legacyRootCaName `
    -RequiredDnsNames $sanEntries.DnsNames `
    -RequiredIpAddresses $sanEntries.IpAddresses
$existingThumbprint = if ($leafCert) { $leafCert.Thumbprint } else { $null }
$existingRootTrusted = if ($trustedRootCert) {
    [bool](Find-StoreCertificate -StoreName Root -StoreLocation CurrentUser -Thumbprint $trustedRootCert.Thumbprint)
} else {
    $false
}
$existingLeafInMy = [bool]$existingThumbprint -and [bool](Find-StoreCertificate -StoreName My -StoreLocation CurrentUser -Thumbprint $existingThumbprint)
$existingLeafInTrustedPeople = [bool]$existingThumbprint -and [bool](Find-StoreCertificate -StoreName TrustedPeople -StoreLocation CurrentUser -Thumbprint $existingThumbprint)
$existingLeafInRoot = [bool]$existingThumbprint -and [bool](Find-StoreCertificate -StoreName Root -StoreLocation CurrentUser -Thumbprint $existingThumbprint)

    if (-not $CheckOnly) {
        if (-not $leafIsCanonical) {
            Generate-RootSignedLeafCertificate `
                -CerPath $leafCerPath `
                -PfxPath $leafPfxPath `
            -RootCerPath $rootCerPath `
            -RootPfxPath $rootPfxPath `
            -PrimaryName $primaryDnsName `
            -AllDnsNames $sanEntries.DnsNames `
            -AllIpAddresses $sanEntries.IpAddresses `
            -Password $pfxPassword `
            -CrlUrl $rootState.CrlUrl
        Write-LeafMetadata -MetadataPath $leafMetadataPath -PrimaryDnsName $primaryDnsName
    } elseif ($existingRootTrusted -and ($existingLeafInTrustedPeople -or $existingLeafInRoot)) {
        $reusedExisting = $true
    }

    $leafCert = Load-PfxCertificate -Path $leafPfxPath -Password $pfxPassword
        if (-not $leafCert) {
            throw "Unable to load canonical MITM certificate for $primaryDnsName."
        }

        Ensure-LeafPresentInMyStore -LeafCert $leafCert

        if (-not $reusedExisting) {
            Import-RootSignedLeafToStores `
                -LeafPfxPath $leafPfxPath `
                -LeafCerPath $leafCerPath `
                -RootCerPath $rootCerPath `
                -Password $pfxPassword | Out-Null
            $leafCert = Load-PfxCertificate -Path $leafPfxPath -Password $pfxPassword
            Ensure-LeafPresentInMyStore -LeafCert $leafCert
        }
    } elseif (-not $leafIsCanonical) {
        $leafCert = $null
    }

Build-ResultPayload `
    -LeafCert $leafCert `
    -TrustedRootCert $trustedRootCert `
    -DnsNames $DnsName `
    -PrimaryName $primaryDnsName `
    -LeafCerPath $leafCerPath `
    -LeafPfxPath $leafPfxPath `
    -ReusedExisting $reusedExisting `
    -RemovedMyCount $removedMyCount `
    -RemovedTrustedPeopleCount $removedTrustedPeopleCount `
    -RemovedRootCount $removedRootCount `
    -RootCerPath $rootCerPath `
    -RootPfxPath $rootPfxPath `
    -RootCrlPath $rootCrlPath `
    -CrlUrl $rootState.CrlUrl | ConvertTo-Json -Depth 5
