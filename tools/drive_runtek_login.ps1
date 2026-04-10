param(
    [string]$Username = "demon",
    [string]$Password = "demon",
    [string]$WindowTitle = "RuneTekApp",
    [long]$Handle = 0,
    [Alias('Pid')]
    [int]$TargetPid = 0,
    [string]$CaptureDir = "",
    [int]$PreClickDelayMs = 600,
    [int]$PostLoginWaitSeconds = 12,
    [int]$LoginScreenTimeoutSeconds = 45,
    [switch]$LegacyOnly,
    [switch]$CaptureOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
$inspectScript = Join-Path $PSScriptRoot "inspect_runescape_screenshot.py"
if ([string]::IsNullOrWhiteSpace($CaptureDir)) {
    $CaptureDir = Join-Path $root "data\debug\runtek-automation"
}
New-Item -ItemType Directory -Path $CaptureDir -Force | Out-Null

function Get-PythonExe {
    foreach ($candidate in @(
        "C:\Users\skull\AppData\Local\Programs\Python\Python312\python.exe",
        "C:\Users\skull\AppData\Local\Programs\Python\Python311\python.exe"
    )) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    return $null
}

function Test-ShouldUseLegacyLoginFallback {
    param([string]$OutputText)

    if ([string]::IsNullOrWhiteSpace($OutputText)) {
        return $false
    }

    $markers = @(
        "numpy._core._multiarray_umath",
        "PyCapsule_Import could not import module ""datetime""",
        "ImportError",
        "DLL load failed",
        "No module named",
        "rapidocr_onnxruntime",
        "cv2",
        "Application Control"
    )
    foreach ($marker in $markers) {
        if ($OutputText -like "*$marker*") {
            return $true
        }
    }
    return $false
}

function Get-LatestDirectPatchPid {
    $summaryPath = Join-Path $root "data\debug\direct-rs2client-patch\latest-client-only.json"
    if (-not (Test-Path $summaryPath)) {
        return 0
    }

    try {
        $summary = Get-Content -Raw -Path $summaryPath | ConvertFrom-Json
        if ($summary.pid -is [int] -and $summary.pid -gt 0) {
            return [int]$summary.pid
        }
    } catch {
        return 0
    }

    return 0
}

$pythonExe = Get-PythonExe

if (-not $CaptureOnly -and -not $LegacyOnly) {
    if ([string]::IsNullOrWhiteSpace($pythonExe)) {
        throw "Could not resolve a Python interpreter for the guarded login driver."
    }

    $pythonScript = Join-Path $PSScriptRoot "run_runtek_login_loop.py"
    $summaryOutput = Join-Path $CaptureDir "latest-drive-runtek-login.json"
    $arguments = @(
        $pythonScript,
        "--username", $Username,
        "--password", $Password,
        "--window-title", $WindowTitle,
        "--max-attempts", "1",
        "--attempt-wait-seconds", [string]$PostLoginWaitSeconds,
        "--settle-delay-seconds", "2",
        "--pre-click-delay-ms", [string]$PreClickDelayMs,
        "--capture-dir", $CaptureDir,
        "--summary-output", $summaryOutput
    )
    if ($Handle -ne 0) {
        $arguments += @("--handle", ("0x{0:x}" -f $Handle))
    }
    if ($TargetPid -gt 0) {
        $arguments += @("--pid", [string]$TargetPid)
    }

    $pythonOutput = & $pythonExe @arguments 2>&1
    $pythonExitCode = $LASTEXITCODE
    if ($pythonExitCode -eq 0) {
        $pythonOutput
        exit 0
    }

    $pythonOutputText = ($pythonOutput | Out-String)
    if (-not (Test-ShouldUseLegacyLoginFallback -OutputText $pythonOutputText)) {
        if (-not [string]::IsNullOrWhiteSpace($pythonOutputText)) {
            Write-Error $pythonOutputText.Trim()
        }
        exit $pythonExitCode
    }

    Write-Warning "Python login driver hit blocked native modules; falling back to legacy no-OCR submitter."
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class RuneTekNative {
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
  public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

  [DllImport("user32.dll")]
  public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);

  [DllImport("user32.dll")]
  public static extern bool SetForegroundWindow(IntPtr hWnd);

  [DllImport("user32.dll")]
  public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);

  [DllImport("user32.dll")]
  public static extern bool BringWindowToTop(IntPtr hWnd);

  [DllImport("user32.dll")]
  public static extern IntPtr GetForegroundWindow();

  [DllImport("user32.dll", SetLastError = true)]
  public static extern bool SetWindowPos(
      IntPtr hWnd,
      IntPtr hWndInsertAfter,
      int X,
      int Y,
      int cx,
      int cy,
      uint uFlags
  );

  [DllImport("user32.dll")]
  public static extern bool SetCursorPos(int X, int Y);

  [DllImport("user32.dll")]
  public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
}
"@

$MOUSEEVENTF_LEFTDOWN = 0x0002
$MOUSEEVENTF_LEFTUP = 0x0004
$SW_RESTORE = 9
$HWND_TOPMOST = [IntPtr](-1)
$HWND_NOTOPMOST = [IntPtr](-2)
$SWP_NOSIZE = 0x0001
$SWP_NOMOVE = 0x0002
$SWP_SHOWWINDOW = 0x0040

function Find-RuneTekWindow {
    param(
        [string]$Title,
        [int]$TargetProcessId = 0
    )

    $match = $null
    $callback = [RuneTekNative+EnumWindowsProc]{
        param([IntPtr]$hWnd, [IntPtr]$lParam)
        if (-not [RuneTekNative]::IsWindowVisible($hWnd)) {
            return $true
        }

        $builder = New-Object System.Text.StringBuilder 512
        [void][RuneTekNative]::GetWindowText($hWnd, $builder, $builder.Capacity)
        $text = $builder.ToString()
        $windowPid = 0
        [void][RuneTekNative]::GetWindowThreadProcessId($hWnd, [ref]$windowPid)
        if ($TargetProcessId -gt 0 -and $windowPid -ne $TargetProcessId) {
            return $true
        }
        if ($text -like "*$Title*") {
            $script:match = $hWnd
            return $false
        }
        return $true
    }

    [void][RuneTekNative]::EnumWindows($callback, [IntPtr]::Zero)
    return $match
}

function Get-WindowRect {
    param([IntPtr]$Handle)
    $rect = New-Object RuneTekNative+RECT
    if (-not [RuneTekNative]::GetWindowRect($Handle, [ref]$rect)) {
        throw "Failed to read window bounds for handle $Handle"
    }
    return $rect
}

function Focus-Window {
    param([IntPtr]$Handle)
    [void][RuneTekNative]::ShowWindowAsync($Handle, $SW_RESTORE)
    Start-Sleep -Milliseconds 200
    [void][RuneTekNative]::SetWindowPos(
        $Handle,
        $HWND_TOPMOST,
        0,
        0,
        0,
        0,
        ($SWP_NOMOVE -bor $SWP_NOSIZE -bor $SWP_SHOWWINDOW)
    )
    Start-Sleep -Milliseconds 80
    [void][RuneTekNative]::SetWindowPos(
        $Handle,
        $HWND_NOTOPMOST,
        0,
        0,
        0,
        0,
        ($SWP_NOMOVE -bor $SWP_NOSIZE -bor $SWP_SHOWWINDOW)
    )
    Start-Sleep -Milliseconds 80
    [void][RuneTekNative]::BringWindowToTop($Handle)
    Start-Sleep -Milliseconds 80
    [void][RuneTekNative]::SetForegroundWindow($Handle)
    Start-Sleep -Milliseconds 400
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

    [void][RuneTekNative]::SetCursorPos($x, $y)
    Start-Sleep -Milliseconds 120
    [RuneTekNative]::mouse_event($MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 60
    [RuneTekNative]::mouse_event($MOUSEEVENTF_LEFTUP, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 200
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
    Start-Sleep -Milliseconds 150
}

function Send-Tab {
    [System.Windows.Forms.SendKeys]::SendWait("{TAB}")
    Start-Sleep -Milliseconds 180
}

function Send-Enter {
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
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

    if ([string]::IsNullOrWhiteSpace($pythonExe) -or -not (Test-Path $inspectScript)) {
        return $null
    }

    try {
        $rawOutput = & $pythonExe $inspectScript $ImagePath 2>$null
        if ($null -eq $rawOutput) {
            return $null
        }
        $jsonLine = @($rawOutput | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1)
        if ($jsonLine.Count -eq 0) {
            return $null
        }
        return ($jsonLine[0] | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Wait-ForLoginScreen {
    param(
        [IntPtr]$Handle,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds([Math]::Max(1, $TimeoutSeconds))
    $attempt = 0
    $lastPath = $null
    $lastInspection = $null

    while ((Get-Date) -lt $deadline) {
        $attempt += 1
        Focus-Window -Handle $Handle
        $lastPath = Capture-Window -Handle $Handle -Label ("login-wait-{0:00}" -f $attempt)
        $lastInspection = Inspect-Capture -ImagePath $lastPath
        $state = if ($null -eq $lastInspection) { "unknown" } else { [string]$lastInspection.state }
        if ($state -eq "login-screen" -or $state -eq "error") {
            break
        }
        Start-Sleep -Seconds 3
    }

    return [pscustomobject]@{
        Path = $lastPath
        Inspection = $lastInspection
        State = if ($null -eq $lastInspection) { "unknown" } else { [string]$lastInspection.state }
    }
}

$resolvedPid = if ($TargetPid -gt 0) { $TargetPid } else { Get-LatestDirectPatchPid }
$handlePtr = if ($Handle -ne 0) { [IntPtr]$Handle } else { Find-RuneTekWindow -Title $WindowTitle -TargetProcessId $resolvedPid }
if ($null -eq $handlePtr -or $handlePtr -eq [IntPtr]::Zero) {
    throw "Could not find visible window containing title '$WindowTitle'"
}

Focus-Window -Handle $handlePtr
$before = Capture-Window -Handle $handlePtr -Label "before"
$beforeInspection = Inspect-Capture -ImagePath $before
$beforeState = if ($null -eq $beforeInspection) { "unknown" } else { [string]$beforeInspection.state }
$submitted = $false

if (-not $CaptureOnly) {
    $loginReady = Wait-ForLoginScreen -Handle $handlePtr -TimeoutSeconds $LoginScreenTimeoutSeconds
    if (-not [string]::IsNullOrWhiteSpace($loginReady.Path)) {
        $before = $loginReady.Path
    }
    if ($null -ne $loginReady.Inspection) {
        $beforeInspection = $loginReady.Inspection
        $beforeState = [string]$loginReady.State
    }

    if ($beforeState -ne "login-screen") {
        Write-Warning ("Legacy login submitter did not observe a login screen before timeout; last state was '{0}'." -f $beforeState)
    } else {
    Start-Sleep -Milliseconds $PreClickDelayMs

    # Tuned for the contained 947 RuneTek login card; use keyboard navigation
    # between fields so we don't depend on brittle OCR on this machine.
    Invoke-WindowClick -Handle $handlePtr -XPercent 0.60 -YPercent 0.36
    Set-ClipboardText -Text $Username
    Send-Paste

    Send-Tab
    Set-ClipboardText -Text $Password
    Send-Paste

    Invoke-WindowClick -Handle $handlePtr -XPercent 0.60 -YPercent 0.69
    Send-Enter
    Send-Enter
    Send-Enter
        $submitted = $true
    }
}

Start-Sleep -Seconds $PostLoginWaitSeconds
Focus-Window -Handle $handlePtr
$after = Capture-Window -Handle $handlePtr -Label "after"
$afterInspection = Inspect-Capture -ImagePath $after
$afterState = if ($null -eq $afterInspection) { "unknown" } else { [string]$afterInspection.state }
$rect = Get-WindowRect -Handle $handlePtr

[pscustomobject]@{
    WindowHandle = [int64]$handlePtr
    WindowTitle = $WindowTitle
    Before = $before
    BeforeState = $beforeState
    After = $after
    AfterState = $afterState
    Bounds = @{
        Left = $rect.Left
        Top = $rect.Top
        Right = $rect.Right
        Bottom = $rect.Bottom
    }
    CaptureOnly = [bool]$CaptureOnly
    LegacyOnly = [bool]$LegacyOnly
    Submitted = $submitted
    Username = if ($CaptureOnly) { $null } else { $Username }
    ResolvedPid = $resolvedPid
} | ConvertTo-Json -Depth 4
