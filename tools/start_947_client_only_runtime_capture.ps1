param(
    [int]$LaunchTimeoutSeconds = 90,
    [int]$ProbeDurationSeconds = 90,
    [switch]$FirstChanceDumps,
    [switch]$RepairR15AtStateCapture,
    [string]$FunctionStartRva = "0x590bc0",
    [string]$FaultRva = "0x590de8",
    [string]$StateCaptureRva = "0x590dcb"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$launchScript = Join-Path $PSScriptRoot "launch-client-only.ps1"
$probeScript = Join-Path $PSScriptRoot "start_947_client_crash_probe.ps1"
$dumpScript = Join-Path $PSScriptRoot "start_947_client_userdump.ps1"

function Get-Rs2ClientRecords {
    @(Get-CimInstance Win32_Process -Filter "Name='rs2client.exe'" -ErrorAction SilentlyContinue)
}

$preexistingProcessIds = [System.Collections.Generic.HashSet[int]]::new()
foreach ($record in Get-Rs2ClientRecords) {
    $preexistingProcessIds.Add([int]$record.ProcessId) | Out-Null
}

$dumpArguments = @("-ExecutionPolicy", "Bypass", "-File", $dumpScript, "-WaitForProcess")
if ($FirstChanceDumps.IsPresent) {
    $dumpArguments += "-FirstChance"
}
$dumpMonitor = powershell @dumpArguments | ConvertFrom-Json

$launcherProcess = Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", $launchScript) `
    -WorkingDirectory $root `
    -PassThru `
    -WindowStyle Hidden

$attachedProcessIds = [System.Collections.Generic.HashSet[int]]::new()
$probeRuns = New-Object System.Collections.Generic.List[object]
$deadline = (Get-Date).AddSeconds($LaunchTimeoutSeconds)

while ((Get-Date) -lt $deadline) {
    foreach ($record in (Get-Rs2ClientRecords | Sort-Object ProcessId)) {
        $processId = [int]$record.ProcessId
        if ($preexistingProcessIds.Contains($processId) -or $attachedProcessIds.Contains($processId)) {
            continue
        }

        $probeArguments = @(
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            $probeScript,
            "-TargetPid",
            $processId,
            "-DurationSeconds",
            $ProbeDurationSeconds,
            "-FunctionStartRva",
            $FunctionStartRva,
            "-FaultRva",
            $FaultRva,
            "-StateCaptureRva",
            $StateCaptureRva
        )
        if ($RepairR15AtStateCapture.IsPresent) {
            $probeArguments += "-RepairR15AtStateCapture"
        }

        $probeRun = powershell @probeArguments | ConvertFrom-Json

        $attachedProcessIds.Add($processId) | Out-Null
        $probeRuns.Add(
            [pscustomobject]@{
                ProcessId = $processId
                ExecutablePath = $record.ExecutablePath
                CommandLine = $record.CommandLine
                Probe = $probeRun
            }
        ) | Out-Null
    }

    if ($attachedProcessIds.Count -gt 0) {
        $aliveAttachedCount = @(
            Get-Rs2ClientRecords | Where-Object {
                $attachedProcessIds.Contains([int]$_.ProcessId)
            }
        ).Count

        if ($aliveAttachedCount -eq 0 -and $launcherProcess.HasExited) {
            break
        }
    }

    Start-Sleep -Milliseconds 500
}

Start-Sleep -Seconds 3

[pscustomobject]@{
    LauncherPid = $launcherProcess.Id
    LauncherHasExited = $launcherProcess.HasExited
    DumpMonitor = $dumpMonitor
    ProbeRuns = @($probeRuns)
    LatestProbePath = Join-Path $root "data\debug\frida-crash-probe\latest-client-only.jsonl"
    LatestHookPath = Join-Path $root "data\debug\direct-rs2client-patch\latest-client-only-hook.jsonl"
    TransportPath = Join-Path $root "data\debug\prelogin-transport-events.jsonl"
    FunctionStartRva = $FunctionStartRva
    FaultRva = $FaultRva
    StateCaptureRva = $StateCaptureRva
} | ConvertTo-Json -Depth 8
