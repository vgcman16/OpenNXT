param(
    [string]$ListenAddress = "127.0.0.1",
    [int]$ListenPort = 443,
    [string]$ConnectAddress = "91.235.140.195",
    [int]$ConnectPort = 443
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$debugDir = Join-Path $root "data\debug"
New-Item -ItemType Directory -Force -Path $debugDir | Out-Null

$statusLog = Join-Path $debugDir "content-portproxy-status.log"
$errorLog = Join-Path $debugDir "content-portproxy-error.log"
Remove-Item $statusLog, $errorLog -Force -ErrorAction SilentlyContinue

try {
    "started $(Get-Date -Format o)" | Set-Content $statusLog -Encoding ASCII
    "whoami: $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)" | Add-Content $statusLog -Encoding ASCII
    ("listen={0}:{1} connect={2}:{3}" -f $ListenAddress, $ListenPort, $ConnectAddress, $ConnectPort) | Add-Content $statusLog -Encoding ASCII

    & netsh interface portproxy delete v4tov4 listenaddress=$ListenAddress listenport=$ListenPort | Out-Null
    & netsh interface portproxy add v4tov4 listenaddress=$ListenAddress listenport=$ListenPort connectaddress=$ConnectAddress connectport=$ConnectPort protocol=tcp | Out-Null

    $rules = & netsh interface portproxy show v4tov4 | Out-String
    if ($rules -notmatch [Regex]::Escape($ListenAddress) -or $rules -notmatch ("{0}\s+{1}\s+{2}" -f [Regex]::Escape($ListenPort), [Regex]::Escape($ConnectAddress), [Regex]::Escape($ConnectPort))) {
        throw "Portproxy rule did not appear in 'netsh interface portproxy show v4tov4'. Run this script from an elevated Administrator PowerShell."
    }

    "success" | Add-Content $statusLog -Encoding ASCII
    $rules | Add-Content $statusLog -Encoding ASCII
} catch {
    $_ | Out-String | Set-Content $errorLog -Encoding ASCII
    throw
}
