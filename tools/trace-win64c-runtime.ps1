param(
    [int]$TraceTimeoutSeconds = 20,
    [int]$TraceIntervalMilliseconds = 250,
    [int]$StartupTimeoutSeconds = 30,
    [int]$ProxyStartupTimeoutSeconds = 20,
    [string]$OutputPath = "",
    [Nullable[int]]$CefRemoteDebuggingPort = $null,
    [switch]$EnableCefLogging,
    [switch]$CaptureConsole,
    [string[]]$ExtraClientArgs = @(),
    [string]$ExtraClientArgsCsv = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$powershellExe = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$pythonExe = "python"
$launchScript = Join-Path $PSScriptRoot "launch-win64c-live.ps1"
$launchStateFile = Join-Path $root "tmp-launch-win64c-live.state.json"
$launchWrapperOut = Join-Path $root "tmp-trace-win64c-runtime-wrapper.out.log"
$launchWrapperErr = Join-Path $root "tmp-trace-win64c-runtime-wrapper.err.log"

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $root ("data\debug\runtime-trace\rs2client-{0}.jsonl" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
}

Remove-Item $launchStateFile, $launchWrapperOut, $launchWrapperErr -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path (Split-Path -Parent $OutputPath) -Force | Out-Null

$normalizedExtraClientArgs = @()
foreach ($arg in @($ExtraClientArgs) + @($ExtraClientArgsCsv -split ";")) {
    if ([string]::IsNullOrWhiteSpace($arg)) {
        continue
    }

    foreach ($piece in ($arg -split ",")) {
        if (-not [string]::IsNullOrWhiteSpace($piece)) {
            $normalizedExtraClientArgs += $piece.Trim()
        }
    }
}

$launchArgs = @(
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    ('"{0}"' -f $launchScript),
    "-StartupTimeoutSeconds",
    $StartupTimeoutSeconds.ToString(),
    "-ProxyStartupTimeoutSeconds",
    $ProxyStartupTimeoutSeconds.ToString()
)

if ($CefRemoteDebuggingPort) {
    $launchArgs += "-CefRemoteDebuggingPort"
    $launchArgs += $CefRemoteDebuggingPort.ToString()
}

if ($EnableCefLogging) {
    $launchArgs += "-EnableCefLogging"
}

if ($CaptureConsole) {
    $launchArgs += "-CaptureConsole"
}

if ($normalizedExtraClientArgs.Count -gt 0) {
    $launchArgs += "-ExtraClientArgsCsv"
    $launchArgs += ('"{0}"' -f ($normalizedExtraClientArgs -join ";"))
}

$launchWrapper = Start-Process -FilePath $powershellExe `
    -ArgumentList $launchArgs `
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
    throw "Client pid $clientPid exited before runtime tracing could attach"
}

try {
    & $pythonExe (Join-Path $PSScriptRoot "trace_process_runtime.py") `
        --pid $clientPid `
        --interval-ms $TraceIntervalMilliseconds `
        --timeout-seconds $TraceTimeoutSeconds `
        --output $OutputPath
} finally {
    foreach ($pidValue in @(
        $launchState.ClientPid,
        $launchState.WatchdogPid,
        $launchState.LobbyProxyPid,
        $launchState.GameProxyPid,
        $launchState.ServerPid,
        $launchState.WrapperPid,
        $launchWrapper.Id
    )) {
        if ($null -eq $pidValue) {
            continue
        }

        try {
            taskkill /PID $pidValue /F | Out-Null
        } catch {
        }
    }
}

[pscustomobject]@{
    OutputPath = $OutputPath
    LaunchArgs = $launchArgs
    LaunchStateFile = $launchStateFile
    LaunchWrapperOut = $launchWrapperOut
    LaunchWrapperErr = $launchWrapperErr
    ClientPid = $clientPid
    ServerPid = $launchState.ServerPid
    LobbyProxyPid = $launchState.LobbyProxyPid
    GameProxyPid = $launchState.GameProxyPid
    WatchdogPid = $launchState.WatchdogPid
} | ConvertTo-Json -Depth 3
