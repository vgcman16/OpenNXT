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

New-Item -ItemType Directory -Force -Path $tlsDir | Out-Null

$requiredNames = @($DnsName | Sort-Object -Unique)

$cert = Get-ChildItem Cert:\CurrentUser\My |
    Where-Object {
        $_.FriendlyName -eq $friendlyName -and
        $_.NotAfter -gt (Get-Date).AddDays(7) -and
        (@($requiredNames | Where-Object { $_ -notin @($_.DnsNameList | ForEach-Object { $_.Unicode }) }).Count -eq 0)
    } |
    Sort-Object NotAfter -Descending |
    Select-Object -First 1

if (-not $cert) {
    $cert = New-SelfSignedCertificate `
        -DnsName $DnsName `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -FriendlyName $friendlyName `
        -KeyAlgorithm RSA `
        -KeyLength 2048 `
        -HashAlgorithm SHA256 `
        -KeyExportPolicy Exportable `
        -NotAfter (Get-Date).AddYears(5)
}

Export-Certificate -Cert $cert -FilePath $cerPath -Force | Out-Null

if (-not (Get-ChildItem Cert:\CurrentUser\Root | Where-Object Thumbprint -eq $cert.Thumbprint)) {
    Import-Certificate -FilePath $cerPath -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
}

Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password (ConvertTo-SecureString $pfxPassword -AsPlainText -Force) -Force | Out-Null

[pscustomobject]@{
    DnsName = $DnsName
    FriendlyName = $friendlyName
    Thumbprint = $cert.Thumbprint
    NotAfter = $cert.NotAfter
    CertificateStore = $cert.PSParentPath
    RootTrusted = $true
    CerPath = $cerPath
    PfxPath = $pfxPath
    PfxPassword = $pfxPassword
} | ConvertTo-Json -Depth 3
