param(
    [string]$DumpDir = "",
    [int]$StartupTimeoutSeconds = 30,
    [int]$ProxyStartupTimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$powershellExe = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$launchScript = Join-Path $PSScriptRoot "launch-win64c-live.ps1"
$launchStateFile = Join-Path $root "tmp-launch-win64c-live.state.json"
$launchWrapperOut = Join-Path $root "tmp-launch-win64c-procdump-wrapper.out.log"
$launchWrapperErr = Join-Path $root "tmp-launch-win64c-procdump-wrapper.err.log"
$procdumpOut = Join-Path $root "tmp-rs2client-procdump.out.log"
$procdumpErr = Join-Path $root "tmp-rs2client-procdump.err.log"

function Get-ProcDumpPath {
    $direct = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\Microsoft.Sysinternals.Suite_Microsoft.Winget.Source_8wekyb3d8bbwe\procdump.exe"
    if (Test-Path $direct) {
        return $direct
    }

    $candidate = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages") -Recurse -Filter procdump.exe -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
    if ($candidate) {
        return $candidate
    }

    throw "Could not find procdump.exe"
}

if ([string]::IsNullOrWhiteSpace($DumpDir)) {
    $DumpDir = Join-Path $root ("data\debug\procdump\{0}" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
}

New-Item -ItemType Directory -Path $DumpDir -Force | Out-Null
Remove-Item $launchStateFile, $procdumpOut, $procdumpErr, $launchWrapperOut, $launchWrapperErr -ErrorAction SilentlyContinue

$launchWrapper = Start-Process -FilePath $powershellExe `
    -ArgumentList @(
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        ('"{0}"' -f $launchScript),
        "-StartupTimeoutSeconds",
        $StartupTimeoutSeconds.ToString(),
        "-ProxyStartupTimeoutSeconds",
        $ProxyStartupTimeoutSeconds.ToString()
    ) `
    -WorkingDirectory $root `
    -RedirectStandardOutput $launchWrapperOut `
    -RedirectStandardError $launchWrapperErr `
    -PassThru

$deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds + $ProxyStartupTimeoutSeconds + 20)
while ((Get-Date) -lt $deadline) {
    if (Test-Path $launchStateFile) {
        break
    }
    Start-Sleep -Milliseconds 500
}

if (-not (Test-Path $launchStateFile)) {
    $wrapperError = if (Test-Path $launchWrapperErr) { Get-Content -Path $launchWrapperErr -Raw } else { "" }
    throw "launch-win64c-live.ps1 did not produce $launchStateFile`n$wrapperError"
}

$launchState = Get-Content -Path $launchStateFile -Raw | ConvertFrom-Json
$clientPid = [int]$launchState.ClientPid
if (-not (Get-Process -Id $clientPid -ErrorAction SilentlyContinue)) {
    throw "Client pid $clientPid exited before ProcDump could attach"
}

$procdumpPath = Get-ProcDumpPath
$quotedDumpComment = '"OpenNXT local repro"'
$quotedDumpDir = ('"{0}"' -f $DumpDir)
$procdumpArgs = @(
    "-accepteula",
    "-ma",
    "-e",
    "-t",
    "-o",
    "-dc",
    $quotedDumpComment,
    $clientPid.ToString(),
    $quotedDumpDir
)
$procdump = Start-Process -FilePath $procdumpPath `
    -ArgumentList $procdumpArgs `
    -WorkingDirectory $root `
    -RedirectStandardOutput $procdumpOut `
    -RedirectStandardError $procdumpErr `
    -PassThru

[pscustomobject]@{
    DumpDir = $DumpDir
    ProcDumpPath = $procdumpPath
    ProcDumpArgs = $procdumpArgs
    ProcDumpPid = $procdump.Id
    ProcDumpOut = $procdumpOut
    ProcDumpErr = $procdumpErr
    LaunchWrapperPid = $launchWrapper.Id
    LaunchWrapperOut = $launchWrapperOut
    LaunchWrapperErr = $launchWrapperErr
    LaunchStateFile = $launchStateFile
    ClientPid = $clientPid
    ClientExe = $launchState.ClientExe
    ServerPid = $launchState.ServerPid
    LobbyProxyPid = $launchState.LobbyProxyPid
    GameProxyPid = $launchState.GameProxyPid
    WatchdogPid = $launchState.WatchdogPid
} | ConvertTo-Json -Depth 3
