param()

$ErrorActionPreference = "Stop"

$hosts = "$env:WINDIR\System32\drivers\etc\hosts"
$LobbyHost = "lobby45a.runescape.com"
$LegacyHostNames = @($LobbyHost, "lobby46a.runescape.com") | Select-Object -Unique
$targets = @(
    "127.0.0.1 $LobbyHost",
    "127.0.0.1 content.runescape.com"
)

$lines = @()
if (Test-Path $hosts) {
    $lines = @(Get-Content $hosts | Where-Object { $_ -notmatch "(^|\s)content\.runescape\.com(\s|$)" })
    foreach ($legacyHostName in $LegacyHostNames) {
        $lines = @($lines | Where-Object {
            $_ -notmatch ("(^|\s){0}(\s|$)" -f [regex]::Escape($legacyHostName))
        })
    }
}

$lines += $targets
Set-Content -Path $hosts -Value $lines -Encoding ASCII
Clear-DnsClientCache

Resolve-DnsName $LobbyHost -Type A
Resolve-DnsName content.runescape.com -Type A
