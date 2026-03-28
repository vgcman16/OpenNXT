 = "C:\WINDOWS\System32\drivers\etc\hosts"
 = @(Get-Content  | Where-Object {
   -notmatch '(^|\s)content\.runescape\.com(\s|$)' -and
   -notmatch '(^|\s)lobby46a\.runescape\.com(\s|$)'
})
 += '127.0.0.1 content.runescape.com'
Set-Content -Path  -Value  -Encoding ASCII
Clear-DnsClientCache
Resolve-DnsName lobby46a.runescape.com -Type A
Resolve-DnsName content.runescape.com -Type A | Out-String | Set-Content "C:\Users\Demon\Documents\New project\OpenNXT\data\debug\last-content-override.txt"
