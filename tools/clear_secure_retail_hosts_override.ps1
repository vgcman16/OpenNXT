param()

$ErrorActionPreference = "Stop"

$hosts = "$env:WINDIR\System32\drivers\etc\hosts"
$markerBegin = "# OpenNXT secure retail hosts override begin"
$markerEnd = "# OpenNXT secure retail hosts override end"

function Write-HostsFileAtomically {
    param(
        [string]$Path,
        [string[]]$Lines
    )

    $tempPath = "{0}.{1}.tmp" -f $Path, ([System.Guid]::NewGuid().ToString("N"))
    try {
        $content = [string]::Join([Environment]::NewLine, @($Lines))
        if ($content.Length -gt 0) {
            $content += [Environment]::NewLine
        }
        [System.IO.File]::WriteAllText($tempPath, $content, [System.Text.Encoding]::ASCII)
        Move-Item -LiteralPath $tempPath -Destination $Path -Force
    } finally {
        Remove-Item $tempPath -Force -ErrorAction SilentlyContinue
    }
}

$existingLines = @()
if (Test-Path $hosts) {
    $existingLines = @(Get-Content -Path $hosts -ErrorAction Stop)
}

$filteredLines = New-Object System.Collections.Generic.List[string]
$insideManagedBlock = $false
foreach ($line in $existingLines) {
    if ($line -eq $markerBegin) {
        $insideManagedBlock = $true
        continue
    }
    if ($line -eq $markerEnd) {
        $insideManagedBlock = $false
        continue
    }
    if (-not $insideManagedBlock) {
        $filteredLines.Add($line)
    }
}

Write-HostsFileAtomically -Path $hosts -Lines $filteredLines
Clear-DnsClientCache | Out-Null

Write-Output (@{
    enabled = $false
    hosts = @()
    hostsPath = $hosts
} | ConvertTo-Json -Depth 4)
