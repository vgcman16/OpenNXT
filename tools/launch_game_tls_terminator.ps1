$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$stdout = Join-Path $root "tmp-game-proxy.out.log"
$stderr = Join-Path $root "tmp-game-proxy.err.log"
$proxyScript = Join-Path $PSScriptRoot "tcp_proxy.py"

Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -eq 43595 } |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
        try {
            taskkill /PID $_ /F | Out-Null
        } catch {
        }
    }

Remove-Item $stdout, $stderr -ErrorAction SilentlyContinue

$process = Start-Process -FilePath "python" `
    -ArgumentList @(
        ('"{0}"' -f $proxyScript),
        "--listen-host", "127.0.0.1",
        "--listen-port", "43595",
        "--remote-host", "127.0.0.1",
        "--remote-port", "43596"
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
