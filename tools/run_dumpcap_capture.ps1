$out = 'C:\Users\Demon\Documents\New project\OpenNXT\data\debug\login-click-capture'
New-Item -ItemType Directory -Force -Path $out | Out-Null

$pcap = Join-Path $out 'login-click-443.pcapng'
if (Test-Path $pcap) {
    Remove-Item $pcap -Force
}

$arguments = "-i 7 -i 10 -f ""port 443 or port 43595"" -a duration:45 -w ""$pcap"""
$process = Start-Process -FilePath 'C:\Program Files\Wireshark\dumpcap.exe' -ArgumentList $arguments -PassThru

Start-Sleep -Seconds 2

[pscustomobject]@{
    ProcessId = $process.Id
    Pcap = $pcap
} | Format-List
