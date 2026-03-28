param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PassThruArgs
)

$ErrorActionPreference = "Stop"

$pythonExe = "python"
$scriptPath = Join-Path $PSScriptRoot "watch_rs2client_live.py"

& $pythonExe $scriptPath @PassThruArgs
exit $LASTEXITCODE
