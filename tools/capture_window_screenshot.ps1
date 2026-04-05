param(
    [Parameter(Mandatory = $true)]
    [int]$ProcessId,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [switch]$BringToFront
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing

Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class WindowCaptureNative {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern IntPtr GetWindowDC(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern int ReleaseDC(IntPtr hWnd, IntPtr hDC);

    [DllImport("user32.dll")]
    public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);
}

public static class WindowCaptureGdi {
    [DllImport("gdi32.dll")]
    public static extern IntPtr CreateCompatibleDC(IntPtr hdc);

    [DllImport("gdi32.dll")]
    public static extern IntPtr CreateCompatibleBitmap(IntPtr hdc, int nWidth, int nHeight);

    [DllImport("gdi32.dll")]
    public static extern IntPtr SelectObject(IntPtr hdc, IntPtr hgdiobj);

    [DllImport("gdi32.dll")]
    public static extern bool DeleteObject(IntPtr hObject);

    [DllImport("gdi32.dll")]
    public static extern bool DeleteDC(IntPtr hdc);
}
"@

$process = Get-Process -Id $ProcessId -ErrorAction Stop
if ($process.MainWindowHandle -eq 0) {
    throw "Process $ProcessId does not currently own a main window."
}

$handle = [System.IntPtr]$process.MainWindowHandle
if ($BringToFront) {
    [void][WindowCaptureNative]::ShowWindow($handle, 9)
    [void][WindowCaptureNative]::SetForegroundWindow($handle)
    Start-Sleep -Milliseconds 300
}

$rect = New-Object WindowCaptureNative+RECT
if (-not [WindowCaptureNative]::GetWindowRect($handle, [ref]$rect)) {
    throw "GetWindowRect failed for process $ProcessId."
}

$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
if ($width -le 0 -or $height -le 0) {
    throw "Window rect for process $ProcessId is invalid: ${width}x${height}."
}

$outputItem = Get-Item -LiteralPath ([System.IO.Path]::GetDirectoryName($OutputPath)) -ErrorAction SilentlyContinue
if ($null -eq $outputItem) {
    New-Item -ItemType Directory -Path ([System.IO.Path]::GetDirectoryName($OutputPath)) -Force | Out-Null
}

$bitmap = $null
try {
    $windowDc = [WindowCaptureNative]::GetWindowDC($handle)
    if ($windowDc -eq [System.IntPtr]::Zero) {
        throw "GetWindowDC failed for process $ProcessId."
    }
    try {
        $memoryDc = [WindowCaptureGdi]::CreateCompatibleDC($windowDc)
        if ($memoryDc -eq [System.IntPtr]::Zero) {
            throw "CreateCompatibleDC failed for process $ProcessId."
        }
        try {
            $hBitmap = [WindowCaptureGdi]::CreateCompatibleBitmap($windowDc, $width, $height)
            if ($hBitmap -eq [System.IntPtr]::Zero) {
                throw "CreateCompatibleBitmap failed for process $ProcessId."
            }
            try {
                $oldObject = [WindowCaptureGdi]::SelectObject($memoryDc, $hBitmap)
                try {
                    $printed = [WindowCaptureNative]::PrintWindow($handle, $memoryDc, 2)
                    if (-not $printed) {
                        throw "PrintWindow failed for process $ProcessId."
                    }
                    $bitmap = [System.Drawing.Image]::FromHbitmap($hBitmap)
                    $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
                } finally {
                    if ($oldObject -ne [System.IntPtr]::Zero) {
                        [void][WindowCaptureGdi]::SelectObject($memoryDc, $oldObject)
                    }
                }
            } finally {
                if ($hBitmap -ne [System.IntPtr]::Zero) {
                    [void][WindowCaptureGdi]::DeleteObject($hBitmap)
                }
            }
        } finally {
            if ($memoryDc -ne [System.IntPtr]::Zero) {
                [void][WindowCaptureGdi]::DeleteDC($memoryDc)
            }
        }
    } finally {
        [void][WindowCaptureNative]::ReleaseDC($handle, $windowDc)
    }
} finally {
    if ($null -ne $bitmap) {
        $bitmap.Dispose()
    }
}

Write-Output $OutputPath
