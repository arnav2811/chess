param([int]$Workers = 8)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== PC1: validate frozen engines and project setup ===" -ForegroundColor Cyan
python .\head_to_head_v69_vs_v71_200.py --games 100 --workers $Workers --thinking-time 14 --game-time 300 --seed 730069 --out head_to_head_runs\pc1_v69_vs_v71_100 --validate-only
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== PC1: 100 paired v6.9 vs v7.1 games (PUCT OFF) ===" -ForegroundColor Cyan
python .\head_to_head_v69_vs_v71_200.py --games 100 --workers $Workers --thinking-time 14 --game-time 300 --seed 730069 --out head_to_head_runs\pc1_v69_vs_v71_100
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "PC1 complete: 100 head-to-head games." -ForegroundColor Green
