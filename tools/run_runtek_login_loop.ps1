param(
    [string]$Username = "",
    [string]$Password = "",
    [string]$WindowTitle = "RuneTekApp",
    [long]$Handle = 0,
    [Alias('Pid')]
    [int]$TargetPid = 0,
    [int]$MaxAttempts = 5,
    [int]$AttemptWaitSeconds = 15,
    [int]$SettleDelaySeconds = 2,
    [int]$PreClickDelayMs = 500,
    [string]$CaptureDir = "",
    [string]$SummaryOutput = "",
    [switch]$StopOnRepeatedInvalid
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($CaptureDir)) {
    $CaptureDir = Join-Path $root "data\debug\runtek-automation"
}
if ([string]::IsNullOrWhiteSpace($SummaryOutput)) {
    $SummaryOutput = Join-Path $CaptureDir "latest-login-loop.json"
}
New-Item -ItemType Directory -Path $CaptureDir -Force | Out-Null

$bootstrapPath = Join-Path $root "data\debug\world-bootstrap-packets.jsonl"
$transportPath = Join-Path $root "data\debug\prelogin-transport-events.jsonl"
$inspectScript = Join-Path $PSScriptRoot "inspect_runescape_screenshot.py"
$pythonExe = $null
foreach ($candidate in @(
    "C:\Users\skull\AppData\Local\Programs\Python\Python312\python.exe",
    "C:\Users\skull\AppData\Local\Programs\Python\Python311\python.exe"
)) {
    if (Test-Path $candidate) {
        $pythonExe = $candidate
        break
    }
}
if ([string]::IsNullOrWhiteSpace($pythonExe)) {
    throw "Could not resolve a Python interpreter for screenshot inspection."
}

$pythonScript = Join-Path $PSScriptRoot "run_runtek_login_loop.py"
$pythonArgs = @(
    $pythonScript,
    "--username", $Username,
    "--password", $Password,
    "--window-title", $WindowTitle,
    "--max-attempts", [string]$MaxAttempts,
    "--attempt-wait-seconds", [string]$AttemptWaitSeconds,
    "--settle-delay-seconds", [string]$SettleDelaySeconds,
    "--pre-click-delay-ms", [string]$PreClickDelayMs,
    "--capture-dir", $CaptureDir,
    "--summary-output", $SummaryOutput
)
if ($Handle -ne 0) {
    $pythonArgs += @("--handle", ("0x{0:x}" -f $Handle))
}
if ($TargetPid -gt 0) {
    $pythonArgs += @("--pid", [string]$TargetPid)
}
if ($StopOnRepeatedInvalid.IsPresent) {
    $pythonArgs += "--stop-on-repeated-invalid"
}

& $pythonExe @pythonArgs
exit $LASTEXITCODE

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class RuneTekLoginNative {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

  [StructLayout(LayoutKind.Sequential)]
  public struct RECT {
    public int Left;
    public int Top;
    public int Right;
    public int Bottom;
  }

  [DllImport("user32.dll")]
  public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

  [DllImport("user32.dll", CharSet = CharSet.Unicode)]
  public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);

  [DllImport("user32.dll")]
  public static extern bool IsWindowVisible(IntPtr hWnd);

  [DllImport("user32.dll")]
  public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);

  [DllImport("user32.dll")]
  public static extern bool SetForegroundWindow(IntPtr hWnd);

  [DllImport("user32.dll")]
  public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);

  [DllImport("user32.dll")]
  public static extern bool SetCursorPos(int X, int Y);

  [DllImport("user32.dll")]
  public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
}
"@

$MOUSEEVENTF_LEFTDOWN = 0x0002
$MOUSEEVENTF_LEFTUP = 0x0004
$SW_RESTORE = 9

function Find-RuneTekWindow {
    param([string]$Title)

    $script:match = $null
    $callback = [RuneTekLoginNative+EnumWindowsProc]{
        param([IntPtr]$hWnd, [IntPtr]$lParam)
        if (-not [RuneTekLoginNative]::IsWindowVisible($hWnd)) {
            return $true
        }

        $builder = New-Object System.Text.StringBuilder 512
        [void][RuneTekLoginNative]::GetWindowText($hWnd, $builder, $builder.Capacity)
        $text = $builder.ToString()
        if ($text -like "*$Title*") {
            $script:match = $hWnd
            return $false
        }
        return $true
    }

    [void][RuneTekLoginNative]::EnumWindows($callback, [IntPtr]::Zero)
    return $script:match
}

function Get-WindowRect {
    param([IntPtr]$Handle)
    $rect = New-Object RuneTekLoginNative+RECT
    if (-not [RuneTekLoginNative]::GetWindowRect($Handle, [ref]$rect)) {
        throw "Failed to read window bounds for handle $Handle"
    }
    return $rect
}

function Focus-Window {
    param([IntPtr]$Handle)
    [void][RuneTekLoginNative]::ShowWindowAsync($Handle, $SW_RESTORE)
    Start-Sleep -Milliseconds 200
    [void][RuneTekLoginNative]::SetForegroundWindow($Handle)
    Start-Sleep -Milliseconds 300
}

function Invoke-WindowClick {
    param(
        [IntPtr]$Handle,
        [double]$XPercent,
        [double]$YPercent
    )

    $rect = Get-WindowRect -Handle $Handle
    $x = [int]($rect.Left + (($rect.Right - $rect.Left) * $XPercent))
    $y = [int]($rect.Top + (($rect.Bottom - $rect.Top) * $YPercent))

    [void][RuneTekLoginNative]::SetCursorPos($x, $y)
    Start-Sleep -Milliseconds 120
    [RuneTekLoginNative]::mouse_event($MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 60
    [RuneTekLoginNative]::mouse_event($MOUSEEVENTF_LEFTUP, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 250
}

function Set-ClipboardText {
    param([string]$Text)
    [System.Windows.Forms.Clipboard]::SetText($Text)
    Start-Sleep -Milliseconds 120
}

function Send-Paste {
    [System.Windows.Forms.SendKeys]::SendWait("^a")
    Start-Sleep -Milliseconds 80
    [System.Windows.Forms.SendKeys]::SendWait("^v")
    Start-Sleep -Milliseconds 180
}

function Capture-Window {
    param(
        [IntPtr]$Handle,
        [string]$Label
    )

    $rect = Get-WindowRect -Handle $Handle
    $width = $rect.Right - $rect.Left
    $height = $rect.Bottom - $rect.Top
    if ($width -le 0 -or $height -le 0) {
        throw "Window handle $Handle reported invalid bounds ${width}x${height}"
    }

    $path = Join-Path $CaptureDir ("{0}-{1}.png" -f (Get-Date -Format "yyyyMMdd-HHmmss"), $Label)
    $bitmap = New-Object System.Drawing.Bitmap $width, $height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen(
            (New-Object System.Drawing.Point $rect.Left, $rect.Top),
            [System.Drawing.Point]::Empty,
            (New-Object System.Drawing.Size $width, $height)
        )
        $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
    return $path
}

function Inspect-Capture {
    param([string]$ImagePath)
    $json = & $pythonExe $inspectScript $ImagePath
    if ([string]::IsNullOrWhiteSpace($json)) {
        return $null
    }
    return $json | ConvertFrom-Json
}

function Get-NormalizedTexts {
    param([object]$Inspection)
    if ($null -eq $Inspection -or $null -eq $Inspection.detectedTexts) {
        return @()
    }
    return @($Inspection.detectedTexts | ForEach-Object { [string]$_.normalized })
}

function Test-InspectionMarker {
    param(
        [object]$Inspection,
        [string[]]$Markers
    )
    $texts = @(Get-NormalizedTexts -Inspection $Inspection)
    $combined = ($texts -join " | ")
    foreach ($marker in $Markers) {
        if (($texts -contains $marker) -or $combined.Contains($marker)) {
            return $true
        }
    }
    return $false
}

function Get-ArtifactSnapshot {
    $bootstrapItem = if (Test-Path $bootstrapPath) { Get-Item $bootstrapPath } else { $null }
    $transportItem = if (Test-Path $transportPath) { Get-Item $transportPath } else { $null }
    return [pscustomobject]@{
        BootstrapExists = $null -ne $bootstrapItem
        BootstrapLength = if ($bootstrapItem) { [int64]$bootstrapItem.Length } else { 0 }
        BootstrapLastWriteUtc = if ($bootstrapItem) { $bootstrapItem.LastWriteTimeUtc.ToString("o") } else { $null }
        TransportExists = $null -ne $transportItem
        TransportLength = if ($transportItem) { [int64]$transportItem.Length } else { 0 }
        TransportLastWriteUtc = if ($transportItem) { $transportItem.LastWriteTimeUtc.ToString("o") } else { $null }
    }
}

function Test-BootstrapAdvanced {
    param(
        [object]$Before,
        [object]$After
    )
    if ($null -eq $After) {
        return $false
    }
    if (-not $After.BootstrapExists) {
        return $false
    }
    if ($null -eq $Before -or -not $Before.BootstrapExists) {
        return $true
    }
    return [int64]$After.BootstrapLength -gt [int64]$Before.BootstrapLength
}

function Dismiss-GraphicsDriversDialog {
    param([IntPtr]$Handle)
    Invoke-WindowClick -Handle $Handle -XPercent 0.45 -YPercent 0.85
    Invoke-WindowClick -Handle $Handle -XPercent 0.72 -YPercent 0.92
}

function Dismiss-InvalidLoginDialog {
    param([IntPtr]$Handle)
    Invoke-WindowClick -Handle $Handle -XPercent 0.677 -YPercent 0.314
}

function Submit-Login {
    param(
        [IntPtr]$Handle,
        [string]$LoginUser,
        [string]$LoginPassword
    )
    Start-Sleep -Milliseconds $PreClickDelayMs
    Invoke-WindowClick -Handle $Handle -XPercent 0.60 -YPercent 0.36
    Set-ClipboardText -Text $LoginUser
    Send-Paste
    Invoke-WindowClick -Handle $Handle -XPercent 0.60 -YPercent 0.56
    Set-ClipboardText -Text $LoginPassword
    Send-Paste
    Invoke-WindowClick -Handle $Handle -XPercent 0.60 -YPercent 0.69
}

if ([string]::IsNullOrWhiteSpace($Username) -or [string]::IsNullOrWhiteSpace($Password)) {
    throw "Username and Password are required."
}

$handlePtr = if ($Handle -ne 0) { [IntPtr]$Handle } else { Find-RuneTekWindow -Title $WindowTitle }
if ($null -eq $handlePtr -or $handlePtr -eq [IntPtr]::Zero) {
    throw "Could not find visible window containing title '$WindowTitle'"
}

$results = New-Object System.Collections.Generic.List[object]
$invalidCount = 0
$success = $false
$stopReason = "max-attempts-reached"

for ($attempt = 1; $attempt -le [Math]::Max(1, $MaxAttempts); $attempt++) {
    Focus-Window -Handle $handlePtr
    $beforeArtifacts = Get-ArtifactSnapshot
    $beforePath = Capture-Window -Handle $handlePtr -Label ("attempt{0:00}-before" -f $attempt)
    $beforeInspection = Inspect-Capture -ImagePath $beforePath

    if (Test-InspectionMarker -Inspection $beforeInspection -Markers @("GRAPHICSDRIVERS", "GRAPHICS DRIVERS", "UPDATE", "IGNORE")) {
        Dismiss-GraphicsDriversDialog -Handle $handlePtr
        Start-Sleep -Seconds $SettleDelaySeconds
        $beforePath = Capture-Window -Handle $handlePtr -Label ("attempt{0:00}-after-graphics-dismiss" -f $attempt)
        $beforeInspection = Inspect-Capture -ImagePath $beforePath
    }

    if (Test-InspectionMarker -Inspection $beforeInspection -Markers @("INVALID LOGIN OR PASSWORD")) {
        Dismiss-InvalidLoginDialog -Handle $handlePtr
        Start-Sleep -Seconds $SettleDelaySeconds
        $beforePath = Capture-Window -Handle $handlePtr -Label ("attempt{0:00}-after-error-dismiss" -f $attempt)
        $beforeInspection = Inspect-Capture -ImagePath $beforePath
    }

    Submit-Login -Handle $handlePtr -LoginUser $Username -LoginPassword $Password
    Start-Sleep -Seconds $AttemptWaitSeconds

    Focus-Window -Handle $handlePtr
    $afterArtifacts = Get-ArtifactSnapshot
    $afterPath = Capture-Window -Handle $handlePtr -Label ("attempt{0:00}-after" -f $attempt)
    $afterInspection = Inspect-Capture -ImagePath $afterPath

    $bootstrapAdvanced = Test-BootstrapAdvanced -Before $beforeArtifacts -After $afterArtifacts
    $afterState = if ($afterInspection) { [string]$afterInspection.state } else { "unknown" }
    $afterTexts = @(Get-NormalizedTexts -Inspection $afterInspection)

    $attemptResult = [pscustomobject]@{
        Attempt = $attempt
        BeforeImage = $beforePath
        BeforeState = if ($beforeInspection) { [string]$beforeInspection.state } else { "unknown" }
        AfterImage = $afterPath
        AfterState = $afterState
        AfterTexts = $afterTexts
        BootstrapAdvanced = [bool]$bootstrapAdvanced
        BeforeArtifacts = $beforeArtifacts
        AfterArtifacts = $afterArtifacts
    }
    $results.Add($attemptResult)

    if ($bootstrapAdvanced -or $afterState -eq "loading") {
        $success = $true
        $stopReason = if ($bootstrapAdvanced) { "world-bootstrap-observed" } else { "loading-after-submit" }
        break
    }

    if ($afterState -eq "error" -or ($afterTexts -contains "INVALID LOGIN OR PASSWORD")) {
        $invalidCount += 1
        Dismiss-InvalidLoginDialog -Handle $handlePtr
        Start-Sleep -Seconds $SettleDelaySeconds
        if ($StopOnRepeatedInvalid.IsPresent -and $invalidCount -ge 3) {
            $stopReason = "repeated-invalid-login"
            break
        }
        continue
    }
}

$rect = Get-WindowRect -Handle $handlePtr
$summary = [pscustomobject]@{
    WindowHandle = $handlePtr.ToInt64()
    WindowTitle = $WindowTitle
    Success = [bool]$success
    StopReason = $stopReason
    AttemptCount = $results.Count
    Username = $Username
    Bounds = @{
        Left = [int]$rect.Left
        Top = [int]$rect.Top
        Right = [int]$rect.Right
        Bottom = [int]$rect.Bottom
    }
    Attempts = @($results.ToArray())
}

$summaryDirectory = Split-Path -Parent $SummaryOutput
if (-not [string]::IsNullOrWhiteSpace($summaryDirectory)) {
    New-Item -ItemType Directory -Path $summaryDirectory -Force | Out-Null
}
$json = $summary | ConvertTo-Json -Depth 8
Set-Content -Path $SummaryOutput -Value $json -Encoding UTF8
$json
