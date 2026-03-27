param(
    [string]$InstancesDir = (Join-Path $PSScriptRoot "..\instances")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$resolved = Resolve-Path (Join-Path $InstancesDir ".") -ErrorAction SilentlyContinue
if (-not $resolved) {
    New-Item -ItemType Directory -Path $InstancesDir | Out-Null
    $resolved = Resolve-Path (Join-Path $InstancesDir ".")
}
$instancesPath = $resolved

function Get-ExpectedReturn([int]$instanceId, [int]$assetId) {
    $base = 0.028 + 0.0021 * $assetId + 0.0007 * $instanceId
    $wave = 0.0025 * [math]::Sin(($assetId + $instanceId) / 2.7)
    return [math]::Round($base + $wave, 6)
}

function Get-Volatility([int]$instanceId, [int]$assetId) {
    $base = 0.085 + 0.003 * (($assetId + $instanceId) % 7)
    return [math]::Round($base, 6)
}

for ($k = 1; $k -le 12; $k++) {
    $assetCount = 8 + $k
    $maxAssets = [Math]::Max(3, [Math]::Floor($assetCount * 0.45))
    $minAssets = 2 + [Math]::Floor($assetCount * 0.20)
    if ($minAssets -gt $maxAssets) {
        $minAssets = $maxAssets
    }

    $assets = @()
    $vol = @()
    for ($i = 1; $i -le $assetCount; $i++) {
        $ri = Get-ExpectedReturn -instanceId $k -assetId $i
        $vi = Get-Volatility -instanceId $k -assetId $i
        $assets += @{
            id = ("A{0:d2}" -f $i)
            expected_return = $ri
            volatility = $vi
        }
        $vol += $vi
    }

    $covariance = @()
    for ($i = 0; $i -lt $assetCount; $i++) {
        $row = @()
        for ($j = 0; $j -lt $assetCount; $j++) {
            if ($i -eq $j) {
                $value = $vol[$i] * $vol[$i]
            } else {
                $corr = 0.14 + 0.02 * (($i + $j + $k) % 5)
                $value = $vol[$i] * $vol[$j] * $corr
            }
            $row += [math]::Round($value, 8)
        }
        $covariance += ,$row
    }

    $instance = @{
        name = ("fin_{0:d2}" -f $k)
        min_assets = $minAssets
        max_assets = $maxAssets
        assets = $assets
        covariance = $covariance
    }

    $instancePath = Join-Path $instancesPath ("instance_{0:d2}.json" -f $k)
    $json = $instance | ConvertTo-Json -Depth 100
    [System.IO.File]::WriteAllText($instancePath, $json + "`n", [System.Text.Encoding]::UTF8)
}

Write-Host "Generated 12 financial benchmark instances in $instancesPath"
