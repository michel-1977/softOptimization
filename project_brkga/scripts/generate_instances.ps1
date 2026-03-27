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

function New-ProjectObject([int]$instanceId, [int]$projectId, [int]$projectCount) {
    $cost = 8 + (($projectId * 3 + $instanceId) % 17)
    $value = [math]::Round(16 + 1.7 * $projectId + 0.9 * $instanceId + 2.3 * [math]::Sin(($projectId + $instanceId) / 4.0), 4)
    $risk = [math]::Round(2.0 + (($projectId + 2 * $instanceId) % 11) / 3.0, 4)

    $deps = @()
    if ($projectId -gt 4 -and (($projectId + $instanceId) % 3 -eq 0)) {
        $deps += ("P{0:d2}" -f ($projectId - 2))
    }
    if ($projectId -gt 6 -and (($projectId + $instanceId) % 5 -eq 0)) {
        $deps += ("P{0:d2}" -f ($projectId - 5))
    }
    $deps = @($deps | Select-Object -Unique)

    return @{
        id = ("P{0:d2}" -f $projectId)
        cost = [int]$cost
        value = [double]$value
        risk = [double]$risk
        prerequisites = @($deps)
    }
}

for ($k = 1; $k -le 10; $k++) {
    $projectCount = 18 + ($k * 2)
    $projects = @()
    $costAccumulator = 0

    for ($projId = 1; $projId -le $projectCount; $projId++) {
        $project = New-ProjectObject -instanceId $k -projectId $projId -projectCount $projectCount
        $projects += $project
        $costAccumulator += $project.cost
    }

    $budget = [int][Math]::Floor($costAccumulator * (0.42 + 0.01 * ($k % 4)))
    $riskAversion = [math]::Round(0.20 + 0.03 * ($k % 5), 4)
    $instance = @{
        name = ("pps_{0:d2}" -f $k)
        budget = $budget
        risk_aversion = $riskAversion
        projects = $projects
    }

    $path = Join-Path $instancesPath ("pps_{0:d2}.json" -f $k)
    $json = $instance | ConvertTo-Json -Depth 100
    [System.IO.File]::WriteAllText($path, $json + "`n", [System.Text.Encoding]::UTF8)
}

Write-Host "Generated 10 BRKGA benchmark instances in $instancesPath"
