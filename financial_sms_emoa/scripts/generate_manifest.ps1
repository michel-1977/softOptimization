param(
    [string]$InstancesDir = (Join-Path $PSScriptRoot "..\instances"),
    [string]$OutputManifest = (Join-Path $PSScriptRoot "..\MANIFEST.sha256")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$instancesPath = Resolve-Path $InstancesDir
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$manifestPath = Join-Path $projectRoot "MANIFEST.sha256"

$lines = @()
Get-ChildItem -Path $instancesPath -Filter "*.json" | Sort-Object Name | ForEach-Object {
    $hash = (Get-FileHash -Path $_.FullName -Algorithm SHA256).Hash.ToLower()
    $relative = "instances/$($_.Name)"
    $lines += "$hash *$relative"
}

[System.IO.File]::WriteAllLines($manifestPath, $lines, [System.Text.Encoding]::UTF8)
Write-Host "Wrote manifest: $manifestPath"
