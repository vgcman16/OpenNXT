param(
    [switch]$DisableChecksumOverride
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$bat = Join-Path $root "build\install\OpenNXT\bin\OpenNXT.bat"
$stdout = Join-Path $root "tmp-runserver.out.log"
$stderr = Join-Path $root "tmp-runserver.err.log"
$javaHome = "C:\Program Files\Eclipse Adoptium\jdk-25.0.2.10-hotspot"

function Get-NewestWriteTimeUtc {
    param([string[]]$Paths)

    $newest = [datetime]::MinValue
    foreach ($path in $Paths) {
        if (-not (Test-Path $path)) {
            continue
        }

        $item = Get-Item $path
        if ($item.PSIsContainer) {
            $candidate = Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTimeUtc -Descending |
                Select-Object -First 1
            if ($null -ne $candidate -and $candidate.LastWriteTimeUtc -gt $newest) {
                $newest = $candidate.LastWriteTimeUtc
            }
        } elseif ($item.LastWriteTimeUtc -gt $newest) {
            $newest = $item.LastWriteTimeUtc
        }
    }

    return $newest
}

function Ensure-InstalledServerCurrent {
    $installLibDir = Join-Path $root "build\install\OpenNXT\lib"
    $installedJar = Get-ChildItem $installLibDir -Filter "OpenNXT-*.jar" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch "sources|javadoc" } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    $sourceRoots = @(
        (Join-Path $root "build.gradle"),
        (Join-Path $root "gradle.properties"),
        (Join-Path $root "src\main"),
        (Join-Path $root "src\generated"),
        (Join-Path $root "src\main\resources")
    )
    $newestSourceTime = Get-NewestWriteTimeUtc -Paths $sourceRoots
    $installedTime = if ($null -ne $installedJar) { $installedJar.LastWriteTimeUtc } else { [datetime]::MinValue }
    $needsInstallDist = -not (Test-Path $bat) -or $null -eq $installedJar -or $newestSourceTime -gt $installedTime

    if (-not $needsInstallDist) {
        return
    }

    & (Join-Path $root "gradlew.bat") --no-daemon --console=plain installDist
    if ($LASTEXITCODE -ne 0) {
        throw "installDist failed while preparing the installed server."
    }
}

function Get-InstalledServerJar {
    $installLibDir = Join-Path $root "build\install\OpenNXT\lib"
    return Get-ChildItem $installLibDir -Filter "OpenNXT-*.jar" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch "sources|javadoc" } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
}

function Test-InstalledServerEntrypoint {
    $installedJar = Get-InstalledServerJar
    if ($null -eq $installedJar) {
        return $false
    }

    try {
        $entries = & jar tf $installedJar.FullName 2>$null
        return ($entries | Select-String -SimpleMatch "com/opennxt/MainKt.class") -ne $null
    } catch {
        return $false
    }
}

Ensure-InstalledServerCurrent

$useInstalledServer = Test-InstalledServerEntrypoint

Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 8080, 8081, 43596 } |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
        try {
            taskkill /PID $_ /F | Out-Null
        } catch {
        }
    }

Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -match 'OpenNXT\\build\\install\\OpenNXT\\bin\\OpenNXT\.bat' -or
        $_.CommandLine -match 'com\.opennxt\.MainKt' -or
        $_.CommandLine -match 'gradlew(?:\.bat)?".*run --args=""run-server""' -or
        $_.CommandLine -match 'gradlew(?:\.bat)? .* run --args=""run-server""'
    } |
    ForEach-Object {
        try {
            taskkill /PID $_.ProcessId /F | Out-Null
        } catch {
        }
    }

Remove-Item $stdout, $stderr -ErrorAction SilentlyContinue

$envCommands = @('set "JAVA_HOME={0}"' -f $javaHome)
if ($DisableChecksumOverride) {
    $envCommands += 'set "OPENNXT_DISABLE_CHECKSUM_OVERRIDE=1"'
}
$envPrefix = ($envCommands -join " && ")

$command =
    if ($useInstalledServer) {
        '{0} && call "{1}" run-server' -f $envPrefix, $bat
    } else {
        '{0} && call "{1}" --no-daemon --console=plain run --args=""run-server""' -f $envPrefix, (Join-Path $root "gradlew.bat")
    }

$process = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @("/c", $command) `
    -WorkingDirectory $root `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

Start-Sleep -Seconds 6

[pscustomobject]@{
    ProcessId = $process.Id
    Stdout = $stdout
    Stderr = $stderr
    LaunchMode = if ($useInstalledServer) { "installDist" } else { "gradleRunFallback" }
} | ConvertTo-Json -Depth 3
