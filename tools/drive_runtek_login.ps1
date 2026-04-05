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
    [switch]$CaptureOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($CaptureDir)) {
    $CaptureDir = Join-Path $root "data\debug\runtek-automation"
}
New-Item -ItemType Directory -Path $CaptureDir -Force | Out-Null

if (-not $CaptureOnly) {
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

    & $pythonExe @arguments
    exit $LASTEXITCODE
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

    $match = $null
    $callback = [RuneTekNative+EnumWindowsProc]{
        param([IntPtr]$hWnd, [IntPtr]$lParam)
        if (-not [RuneTekNative]::IsWindowVisible($hWnd)) {
            return $true
        }

        $builder = New-Object System.Text.StringBuilder 512
        [void][RuneTekNative]::GetWindowText($hWnd, $builder, $builder.Capacity)
        $text = $builder.ToString()
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
    [void][RuneTekNative]::SetForegroundWindow($Handle)
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

$handlePtr = if ($Handle -ne 0) { [IntPtr]$Handle } else { Find-RuneTekWindow -Title $WindowTitle }
if ($null -eq $handlePtr -or $handlePtr -eq [IntPtr]::Zero) {
    throw "Could not find visible window containing title '$WindowTitle'"
}

Focus-Window -Handle $handlePtr
$before = Capture-Window -Handle $handlePtr -Label "before"

if (-not $CaptureOnly) {
    Start-Sleep -Milliseconds $PreClickDelayMs

    # Coordinates tuned against the current 946 login layout captured in the local patched client.
    Invoke-WindowClick -Handle $handlePtr -XPercent 0.60 -YPercent 0.36
    Set-ClipboardText -Text $Username
    Send-Paste

    Invoke-WindowClick -Handle $handlePtr -XPercent 0.60 -YPercent 0.56
    Set-ClipboardText -Text $Password
    Send-Paste

    Invoke-WindowClick -Handle $handlePtr -XPercent 0.60 -YPercent 0.69
}

Start-Sleep -Seconds $PostLoginWaitSeconds
Focus-Window -Handle $handlePtr
$after = Capture-Window -Handle $handlePtr -Label "after"
$rect = Get-WindowRect -Handle $handlePtr

[pscustomobject]@{
    WindowHandle = [int64]$handlePtr
    WindowTitle = $WindowTitle
    Before = $before
    After = $after
    Bounds = @{
        Left = $rect.Left
        Top = $rect.Top
        Right = $rect.Right
        Bottom = $rect.Bottom
    }
    CaptureOnly = [bool]$CaptureOnly
    Username = if ($CaptureOnly) { $null } else { $Username }
} | ConvertTo-Json -Depth 4
