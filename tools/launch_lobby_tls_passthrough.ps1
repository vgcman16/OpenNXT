$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$stdout = Join-Path $root "tmp-lobby-tls.out.log"
$stderr = Join-Path $root "tmp-lobby-tls.err.log"

Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -eq 443 } |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
        try {
            taskkill /PID $_ /F | Out-Null
        } catch {
        }
    }

Remove-Item $stdout, $stderr -ErrorAction SilentlyContinue

$process = Start-Process -FilePath (Join-Path $root "build\\install\\OpenNXT\\bin\\OpenNXT.bat") `
    -ArgumentList @(
        "run-tool",
        "lobby-tls-passthrough",
        "--remote-host", "127.0.0.1",
        "--remote-port", "43595",
        "--idle-timeout-seconds", "1800",
        "--session-idle-timeout-seconds", "120",
        "--max-sessions", "64"
    ) `
    -WorkingDirectory $root `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

Start-Sleep -Seconds 2

[pscustomobject]@{
    ProcessId = $process.Id
    Stdout = $stdout
    Stderr = $stderr
} | ConvertTo-Json -Depth 3
