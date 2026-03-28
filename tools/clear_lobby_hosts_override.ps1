$HostName = "lobby45a.runescape.com"
$LegacyHostNames = @($HostName, "lobby46a.runescape.com") | Select-Object -Unique
$hosts = "$env:WINDIR\System32\drivers\etc\hosts"
$backupDir = 'C:\Users\Demon\Documents\New project\OpenNXT\data\debug'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$statusLog = Join-Path $backupDir 'hosts-clear-status.log'
$errorLog = Join-Path $backupDir 'hosts-clear-error.log'
Remove-Item $statusLog, $errorLog -Force -ErrorAction SilentlyContinue

"started $(Get-Date -Format o)" | Set-Content $statusLog -Encoding ASCII
"whoami: $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)" | Add-Content $statusLog -Encoding ASCII
"hosts-exists: $(Test-Path $hosts)" | Add-Content $statusLog -Encoding ASCII

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $backupDir "hosts.clear.backup-$timestamp"
try {
    Copy-Item $hosts $backup -Force

    $content = Get-Content $hosts -ErrorAction Stop
    $filtered = $content
    foreach ($legacyHostName in $LegacyHostNames) {
        $escapedHostName = [regex]::Escape($legacyHostName)
        $filtered = $filtered | Where-Object {
            $_ -notmatch "(^|\s)$escapedHostName(\s|$)"
        }
    }

    Set-Content -Path $hosts -Value $filtered -Encoding ASCII
    Clear-DnsClientCache

    "success" | Set-Content $statusLog -Encoding ASCII
    "Backup: $backup" | Add-Content $statusLog -Encoding ASCII
    "Removed hosts override for $HostName" | Add-Content $statusLog -Encoding ASCII
    Resolve-DnsName $HostName -Type A | Out-String | Add-Content $statusLog -Encoding ASCII
} catch {
    $_ | Out-String | Set-Content $errorLog -Encoding ASCII
    throw
}
