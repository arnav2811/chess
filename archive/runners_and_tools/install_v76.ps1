$ErrorActionPreference = 'Stop'
$SourceDir = $PSScriptRoot
$TargetDir = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path (Join-Path $TargetDir 'agent.py'))) {
    Write-Host "Target does not look like the existing coursework project: $TargetDir" -ForegroundColor Red
    Write-Host "Extract this package into a child folder of the project root before running the installer."
    exit 1
}

$FilesToInstall = @(
    'agent_v76_exact_tablebase.py',
    'endgame_tablebase.py',
    'endgame_tb_snippet.py',
    'run_v74_v76_head_to_head.py',
    'run_v76_18_tournament.py',
    'smoke_test_v76.py',
    'play_v76.py',
    'validate_v76.ps1',
    'test_v76_tablebase.py',
    'test_v76_historical_tablebase_corpus.py',
    'test_v76_engineering_controls.py',
    'benchmark_v76_tt_hash.py',
    'historical_tablebase_regression_600run.jsonl',
    'historical_tablebase_regression_600run_summary.json',
    'V76_README.md',
    'V76_ENGINEERING_NOTES.md',
    'V76_VALIDATION_REPORT.md',
    'V76_TT_HASH_MICROBENCH.json',
    'V76_MANIFEST.json',
)

foreach ($Name in $FilesToInstall) {
    $From = Join-Path $SourceDir $Name
    if (-not (Test-Path $From)) { throw "Package file missing: $From" }
    Copy-Item -LiteralPath $From -Destination (Join-Path $TargetDir $Name) -Force
}

# Keep the supplied v7.4 reference available for H2H, but never overwrite an
# existing local copy (which may contain later user-specific fixes).
$Baseline = 'agent_v74_tactical_guard.py'
if (-not (Test-Path (Join-Path $TargetDir $Baseline))) {
    Copy-Item (Join-Path $SourceDir $Baseline) (Join-Path $TargetDir $Baseline)
} else {
    Write-Host "Preserved existing $Baseline" -ForegroundColor Yellow
}

# Preserve the user's extension folder. Add only missing package helpers.
$TargetExtension = Join-Path $TargetDir 'extension'
if (-not (Test-Path $TargetExtension)) { New-Item -ItemType Directory -Path $TargetExtension | Out-Null }
foreach ($Name in @('board_rules.py','board_utils.py','piece_pawn.py','piece_right.py')) {
    $Target = Join-Path $TargetExtension $Name
    if (-not (Test-Path $Target)) {
        Copy-Item (Join-Path (Join-Path $SourceDir 'extension') $Name) $Target
    }
}

Write-Host "`nv7.6 files installed into: $TargetDir" -ForegroundColor Green
Write-Host 'Existing agent.py, v6.9, v7.4, samples, opponents and extension helpers were preserved.' -ForegroundColor Green
Write-Host 'Next: run .\validate_v76.ps1 from the target project root.' -ForegroundColor Cyan
