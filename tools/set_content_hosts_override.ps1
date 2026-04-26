$ErrorActionPreference = "Stop"

$LobbyHost = "lobby45a.runescape.com"
$LegacyHostNames = @($LobbyHost, "lobby46a.runescape.com") | Select-Object -Unique
$hosts = "$env:WINDIR\System32\drivers\etc\hosts"
$backupDir = 'C:\Users\Demon\Documents\New project\OpenNXT\data\debug'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$statusLog = Join-Path $backupDir 'content-hosts-override-status.log'
$errorLog = Join-Path $backupDir 'content-hosts-override-error.log'
Remove-Item $statusLog, $errorLog -Force -ErrorAction SilentlyContinue

function Write-HostsFileAtomically {
    param(
        [string]$Path,
        [string[]]$Lines,
        [string]$TempPath
    )

    $content = [string]::Join([Environment]::NewLine, @($Lines))
    if ($content.Length -gt 0) {
        $content += [Environment]::NewLine
    }

    [System.IO.File]::WriteAllText($TempPath, $content, [System.Text.Encoding]::ASCII)
    Move-Item -LiteralPath $TempPath -Destination $Path -Force
}

"started $(Get-Date -Format o)" | Set-Content $statusLog -Encoding ASCII
"whoami: $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)" | Add-Content $statusLog -Encoding ASCII
"hosts-exists: $(Test-Path $hosts)" | Add-Content $statusLog -Encoding ASCII

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $backupDir "hosts.content.backup-$timestamp"
$tempHosts = Join-Path $backupDir "hosts.content.tmp-$timestamp"
try {
    Copy-Item $hosts $backup -Force

    $content = Get-Content $hosts -ErrorAction Stop
    $filtered = $content | Where-Object { $_ -notmatch '(^|\s)content\.runescape\.com(\s|$)' }
    $filtered = $filtered | Where-Object { $_ -notmatch '(^|\s)rs\.config\.runescape\.com(\s|$)' }
    foreach ($legacyHostName in $LegacyHostNames) {
        $escapedLobbyHost = [regex]::Escape($legacyHostName)
        $filtered = $filtered | Where-Object { $_ -notmatch "(^|\s)$escapedLobbyHost(\s|$)" }
    }
    foreach ($legacyHostName in $LegacyHostNames) {
        $filtered += "127.0.0.1 $legacyHostName"
    }
    $filtered += '127.0.0.1 content.runescape.com'
    $filtered += '127.0.0.1 rs.config.runescape.com'

    Write-HostsFileAtomically -Path $hosts -Lines $filtered -TempPath $tempHosts
    Clear-DnsClientCache

    "success" | Set-Content $statusLog -Encoding ASCII
    "Backup: $backup" | Add-Content $statusLog -Encoding ASCII
    "Updated hosts override for lobby/content/config retail hosts" | Add-Content $statusLog -Encoding ASCII
    Resolve-DnsName $LobbyHost -Type A -ErrorAction SilentlyContinue | Out-String | Add-Content $statusLog -Encoding ASCII
    Resolve-DnsName content.runescape.com -Type A -ErrorAction SilentlyContinue | Out-String | Add-Content $statusLog -Encoding ASCII
    Resolve-DnsName rs.config.runescape.com -Type A -ErrorAction SilentlyContinue | Out-String | Add-Content $statusLog -Encoding ASCII
} catch {
    Remove-Item $tempHosts -Force -ErrorAction SilentlyContinue
    $_ | Out-String | Set-Content $errorLog -Encoding ASCII
    throw
}
