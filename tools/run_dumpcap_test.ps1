$out = 'C:\Users\Demon\Documents\New project\OpenNXT\data\debug\login-click-capture'
New-Item -ItemType Directory -Force -Path $out | Out-Null

$pcap = Join-Path $out 'bgtest.pcapng'
$stdout = Join-Path $out 'bgtest.stdout.log'
$stderr = Join-Path $out 'bgtest.stderr.log'

Remove-Item $pcap, $stdout, $stderr -Force -ErrorAction SilentlyContinue

$arguments = "-i 7 -i 10 -f ""port 443 or port 43595"" -a duration:5 -w ""$pcap"""
$process = Start-Process -FilePath 'C:\Program Files\Wireshark\dumpcap.exe' -ArgumentList $arguments -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr

Start-Sleep -Seconds 7

[pscustomobject]@{
    ProcessRunning = (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) -ne $null
    PcapExists = Test-Path $pcap
    StdoutExists = Test-Path $stdout
    StderrExists = Test-Path $stderr
    Pcap = $pcap
    Stdout = $stdout
    Stderr = $stderr
} | Format-List

if (Test-Path $stdout) {
    '--- stdout ---'
    Get-Content $stdout
}

if (Test-Path $stderr) {
    '--- stderr ---'
    Get-Content $stderr
}
