param(
    [string]$ListenAddress = "127.0.0.1",
    [int]$ListenPort = 443
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$debugDir = Join-Path $root "data\debug"
New-Item -ItemType Directory -Force -Path $debugDir | Out-Null

$statusLog = Join-Path $debugDir "content-portproxy-clear-status.log"
$errorLog = Join-Path $debugDir "content-portproxy-clear-error.log"
Remove-Item $statusLog, $errorLog -Force -ErrorAction SilentlyContinue

try {
    "started $(Get-Date -Format o)" | Set-Content $statusLog -Encoding ASCII
    "whoami: $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)" | Add-Content $statusLog -Encoding ASCII
    ("listen={0}:{1}" -f $ListenAddress, $ListenPort) | Add-Content $statusLog -Encoding ASCII

    & netsh interface portproxy delete v4tov4 listenaddress=$ListenAddress listenport=$ListenPort | Out-Null

    $rules = & netsh interface portproxy show v4tov4 | Out-String
    if ($rules -match [Regex]::Escape($ListenAddress) -and $rules -match [Regex]::Escape([string]$ListenPort)) {
        throw "Portproxy rule still appears in 'netsh interface portproxy show v4tov4'. Run this script from an elevated Administrator PowerShell."
    }

    "success" | Add-Content $statusLog -Encoding ASCII
    $rules | Add-Content $statusLog -Encoding ASCII
} catch {
    $_ | Out-String | Set-Content $errorLog -Encoding ASCII
    throw
}
