param(
    [string]$Message = "Update dashboards"
)

$ErrorActionPreference = "Stop"

function Invoke-GitIfDirty {
    param(
        [string]$Path,
        [string]$CommitMessage
    )

    Push-Location $Path
    try {
        $dirty = git status --porcelain
        if ($dirty) {
            git add -A
            git commit -m $CommitMessage
        }
        git push origin main
    }
    finally {
        Pop-Location
    }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$taxiPath = Join-Path $root "dashboard2.1"

Write-Host "1/2 Push dashboard Taxi..." -ForegroundColor Cyan
Invoke-GitIfDirty -Path $taxiPath -CommitMessage "$Message - taxi"

Write-Host "2/2 Push dashboard principal..." -ForegroundColor Cyan
Invoke-GitIfDirty -Path $root -CommitMessage "$Message - main"

Write-Host "Termine." -ForegroundColor Green
