# PowerShell script to upload firmware
# Usage: .\scripts\upload_firmware.ps1 -Version "1.0.4" -FilePath "C:\Users\ADMIN\Downloads\uvc_wifi_stream.bin"

param(
    [Parameter(Mandatory=$true)]
    [string]$Version,
    
    [Parameter(Mandatory=$true)]
    [string]$FilePath,
    
    [string]$AdminUser = $env:ADMIN_USER,
    [string]$AdminPass = $env:ADMIN_PASS,
    [string]$BaseUrl = $env:BASE_URL,
    [string]$ReleaseNotes,
    [int]$RolloutPercent = 100
)

# Set defaults if not provided
if (-not $AdminUser) { $AdminUser = "admin" }
if (-not $BaseUrl) { $BaseUrl = "http://localhost:8000" }
if (-not $AdminPass) {
    Write-Host "[ERROR] Admin password required. Set ADMIN_PASS environment variable or use -AdminPass parameter" -ForegroundColor Red
    exit 1
}

# Build command
$cmd = "python scripts/upload_firmware.py --version `"$Version`" --file `"$FilePath`" --admin-user `"$AdminUser`" --admin-pass `"$AdminPass`" --base-url `"$BaseUrl`""

if ($ReleaseNotes) {
    $cmd += " --release-notes `"$ReleaseNotes`""
}

if ($RolloutPercent -ne 100) {
    $cmd += " --rollout-percent $RolloutPercent"
}

Write-Host "Running: $cmd" -ForegroundColor Gray
Invoke-Expression $cmd

