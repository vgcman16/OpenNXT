param(
    [switch]$DisableChecksumOverride,
    [switch]$EnableRetailRawChecksumPassthrough,
    [switch]$EnableRetailLoggedOutJs5Passthrough,
    [switch]$DisableRetailLoggedOutJs5Passthrough,
    [switch]$DisableRetailLoggedOutJs5Proxy,
    [switch]$EnableLoggedOutJs5PrefetchTable,
    [switch]$SkipHttpFileVerification
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$bat = Join-Path $root "build\install\OpenNXT\bin\OpenNXT.bat"
$stdout = Join-Path $root "tmp-runserver.out.log"
$stderr = Join-Path $root "tmp-runserver.err.log"
$installDistLog = Join-Path $root "tmp-runserver-installDist.log"
$javaHome = "C:\Program Files\Eclipse Adoptium\jdk-25.0.2.10-hotspot"
$powershellExe = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"

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

    Remove-Item $installDistLog -ErrorAction SilentlyContinue
    $gradleCommand = 'call "{0}" --no-daemon --console=plain installDist > "{1}" 2>&1' -f (Join-Path $root "gradlew.bat"), $installDistLog
    & $env:ComSpec /c $gradleCommand
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

function Get-PortFromEndpoint {
    param([string]$Endpoint)

    if ($Endpoint -match ':(\d+)$') {
        return [int]$Matches[1]
    }

    return $null
}

function Get-NetstatTcpRecords {
    $records = @()

    foreach ($line in (netstat -ano -p tcp)) {
        if ($line -notmatch '^\s*TCP\s+') {
            continue
        }

        $parts = ($line -replace '^\s+', '') -split '\s+'
        if ($parts.Length -lt 5) {
            continue
        }

        $localPort = Get-PortFromEndpoint $parts[1]
        if ($null -eq $localPort) {
            continue
        }

        $owningProcessId = 0
        if (-not [int]::TryParse($parts[4], [ref]$owningProcessId)) {
            continue
        }

        $records += [pscustomobject]@{
            LocalAddress  = $parts[1]
            LocalPort     = $localPort
            RemoteAddress = $parts[2]
            RemotePort    = Get-PortFromEndpoint $parts[2]
            State         = $parts[3]
            OwningProcess = $owningProcessId
            Source        = "netstat"
        }
    }

    return $records
}

function Get-TcpListenerRecords {
    param([int[]]$Ports)

    $normalizedPorts = @(
        $Ports |
            Where-Object { $_ -is [int] -and $_ -gt 0 } |
            Select-Object -Unique
    )
    if ($normalizedPorts.Count -eq 0) {
        return @()
    }

    try {
        return @(
            Get-NetTCPConnection -State Listen -ErrorAction Stop |
                Where-Object { $_.LocalPort -in $normalizedPorts } |
                ForEach-Object {
                    [pscustomobject]@{
                        LocalAddress  = [string]$_.LocalAddress
                        LocalPort     = [int]$_.LocalPort
                        RemoteAddress = [string]$_.RemoteAddress
                        RemotePort    = if ($null -ne $_.RemotePort) { [int]$_.RemotePort } else { $null }
                        State         = [string]$_.State
                        OwningProcess = [int]$_.OwningProcess
                        Source        = "Get-NetTCPConnection"
                    }
                }
        )
    } catch {
        return @(
            Get-NetstatTcpRecords |
                Where-Object { $_.State -eq "LISTENING" -and $_.LocalPort -in $normalizedPorts }
        )
    }
}

function Wait-ListeningPorts {
    param(
        [int[]]$Ports,
        [int]$TimeoutSeconds = 60,
        [int]$DelayMilliseconds = 500
    )

    $requiredPorts = @(
        $Ports |
            Where-Object { $_ -is [int] -and $_ -gt 0 } |
            Select-Object -Unique
    )
    if ($requiredPorts.Count -eq 0) {
        return $true
    }

    $retries = [Math]::Max(1, [int][Math]::Ceiling(($TimeoutSeconds * 1000) / $DelayMilliseconds))
    for ($attempt = 0; $attempt -lt $retries; $attempt++) {
        if ($attempt -gt 0) {
            Start-Sleep -Milliseconds $DelayMilliseconds
        }

        $listening = @(
            Get-TcpListenerRecords -Ports $requiredPorts |
                Select-Object -ExpandProperty LocalPort -Unique
        )

        $allPresent = $true
        foreach ($requiredPort in $requiredPorts) {
            if (-not ($listening -contains [int]$requiredPort)) {
                $allPresent = $false
                break
            }
        }

        if ($allPresent) {
            return $true
        }
    }

    return $false
}

function Get-ListeningProcessIds {
    param([int[]]$Ports)

    return @(
        Get-TcpListenerRecords -Ports $Ports |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
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

$startupLines = @(
    '[Console]::Error.WriteLine(''START_SERVER_LOGGED wrapper-enter'')'
    '[Console]::Error.Flush()'
    ('$env:JAVA_HOME = ''{0}''' -f $javaHome)
    '$env:OPENNXT_STARTUP_PROBE = ''1'''
    ('[Console]::Error.WriteLine(''START_SERVER_LOGGED flags raw={0} enableLoggedOut={1} disableLoggedOut={2} disableProxy={3} prefetch={4} skipHttp={5}'')' -f @(
        [bool]$EnableRetailRawChecksumPassthrough,
        [bool]$EnableRetailLoggedOutJs5Passthrough,
        [bool]$DisableRetailLoggedOutJs5Passthrough,
        [bool]$DisableRetailLoggedOutJs5Proxy,
        [bool]$EnableLoggedOutJs5PrefetchTable,
        [bool]$SkipHttpFileVerification
    ))
    '[Console]::Error.Flush()'
)
if ($useInstalledServer) {
    $startupLines += '$env:JAVA_TOOL_OPTIONS = ''-XX:TieredStopAtLevel=1'''
}
if ($EnableRetailRawChecksumPassthrough) {
    $startupLines += '$env:OPENNXT_ENABLE_RETAIL_RAW_CHECKSUM_PASSTHROUGH = ''1'''
}
if ($EnableRetailLoggedOutJs5Passthrough) {
    $startupLines += '$env:OPENNXT_ENABLE_RETAIL_LOGGED_OUT_JS5_PASSTHROUGH = ''1'''
}
if ($DisableRetailLoggedOutJs5Passthrough) {
    $startupLines += '$env:OPENNXT_ENABLE_RETAIL_LOGGED_OUT_JS5_PASSTHROUGH = ''0'''
}
if ($DisableRetailLoggedOutJs5Proxy) {
    $startupLines += '$env:OPENNXT_DISABLE_RETAIL_LOGGED_OUT_JS5_PROXY = ''1'''
}
if ($EnableLoggedOutJs5PrefetchTable) {
    $startupLines += '$env:OPENNXT_ENABLE_LOGGED_OUT_JS5_PREFETCH_TABLE = ''1'''
}
if ($DisableChecksumOverride) {
    $startupLines += '$env:OPENNXT_DISABLE_CHECKSUM_OVERRIDE = ''1'''
}
$runServerArgs = @("run-server")
if ($SkipHttpFileVerification) {
    $runServerArgs += "--skip-http-file-verification"
}
if ($useInstalledServer) {
    $startupLines += '[Console]::Error.WriteLine(''START_SERVER_LOGGED before-bat'')'
    $startupLines += '[Console]::Error.Flush()'
    $startupLines += ('& ''{0}'' {1}' -f $bat, ($runServerArgs -join " "))
    $startupLines += '[Console]::Error.WriteLine(''START_SERVER_LOGGED after-bat'')'
    $startupLines += '[Console]::Error.Flush()'
} else {
    $startupLines += '[Console]::Error.WriteLine(''START_SERVER_LOGGED before-gradle'')'
    $startupLines += '[Console]::Error.Flush()'
    $gradleRunArgs = if ($SkipHttpFileVerification) { 'run-server --skip-http-file-verification' } else { 'run-server' }
    $startupLines += ('& ''{0}'' --no-daemon --console=plain run --args=''{1}''' -f (Join-Path $root "gradlew.bat"), $gradleRunArgs)
    $startupLines += '[Console]::Error.WriteLine(''START_SERVER_LOGGED after-gradle'')'
    $startupLines += '[Console]::Error.Flush()'
}
$encodedCommand = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes(($startupLines -join [Environment]::NewLine)))

$process = Start-Process -FilePath $powershellExe `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encodedCommand) `
    -WorkingDirectory $root `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

$portsReady = Wait-ListeningPorts -Ports @(8080, 43596) -TimeoutSeconds 60
$serverPid = Get-ListeningProcessIds -Ports @(8080, 43596) | Select-Object -First 1

[pscustomobject]@{
    ProcessId = $process.Id
    Ready = [bool]$portsReady
    ServerPid = if ($serverPid) { [int]$serverPid } else { $null }
    Stdout = $stdout
    Stderr = $stderr
    InstallDistLog = $installDistLog
    ListenerSnapshot = @(
        Get-TcpListenerRecords -Ports @(8080, 43596) |
            Sort-Object LocalPort, OwningProcess |
            ForEach-Object { "{0}@{1}/pid={2}/src={3}" -f $_.LocalPort, $_.LocalAddress, $_.OwningProcess, $_.Source }
    )
    LaunchMode = if ($useInstalledServer) { "installDist" } else { "gradleRunFallback" }
} | ConvertTo-Json -Depth 3
