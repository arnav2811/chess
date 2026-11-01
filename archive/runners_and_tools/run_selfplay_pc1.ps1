param([int]$Workers = 8)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== PC1: validate both engines and project environment ===" -ForegroundColor Cyan
python .\selfplay_control_runner.py --engine v69 --validate-only --out selfplay_runs\validation_v69
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python .\selfplay_control_runner.py --engine v71 --validate-only --out selfplay_runs\validation_v71
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== PC1: v6.9 self-play, 50 games ===" -ForegroundColor Cyan
python .\selfplay_control_runner.py --engine v69 --games 50 --workers $Workers --thinking-time 14 --game-time 300 --seed 730069 --out selfplay_runs\pc1_v69_50
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== PC1: v7.1 PUCT-OFF self-play, 50 games ===" -ForegroundColor Cyan
python .\selfplay_control_runner.py --engine v71 --games 50 --workers $Workers --thinking-time 14 --game-time 300 --seed 730069 --out selfplay_runs\pc1_v71_50
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "PC1 complete: 100 games total." -ForegroundColor Green