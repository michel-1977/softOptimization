param(
    [string]$ManifestPath = (Join-Path $PSScriptRoot "..\MANIFEST.sha256")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$manifest = Resolve-Path $ManifestPath
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$hasError = $false

Get-Content $manifest | ForEach-Object {
    if ([string]::IsNullOrWhiteSpace($_)) {
        return
    }
    $parts = $_ -split "\s+\*", 2
    if ($parts.Count -ne 2) {
        Write-Host "Malformed line: $_"
        $hasError = $true
        return
    }
    $expected = $parts[0].Trim().ToLower()
    $relPath = $parts[1].Trim()
    $filePath = Join-Path $projectRoot $relPath
    if (-not (Test-Path $filePath)) {
        Write-Host "Missing file: $relPath"
        $hasError = $true
        return
    }
    $actual = (Get-FileHash -Path $filePath -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expected) {
        Write-Host "Mismatch: $relPath"
        $hasError = $true
    } else {
        Write-Host "OK: $relPath"
    }
}

if ($hasError) {
    throw "Manifest verification failed."
}

Write-Host "Manifest verification passed."
