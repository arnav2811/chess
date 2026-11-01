param(
    [switch]$RunTournament
)
$ErrorActionPreference = 'Stop'

Write-Host '=== v7.5 compile check ===' -ForegroundColor Cyan
python -m py_compile agent_v75_endgame_depth.py agent_v74_tactical_guard.py run_v75_18_tournament.py run_v74_v75_head_to_head.py smoke_test_v75.py test_v75_tablebase.py test_v75_search_controls.py
if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed.' }

Write-Host '=== Tablebase regression ===' -ForegroundColor Cyan
python test_v75_tablebase.py
if ($LASTEXITCODE -ne 0) { throw 'Tablebase regression failed.' }

Write-Host '=== Search-control regressions ===' -ForegroundColor Cyan
python test_v75_search_controls.py
if ($LASTEXITCODE -ne 0) { throw 'Search-control regression failed.' }

Write-Host '=== Live ChessMaker smoke test ===' -ForegroundColor Cyan
python smoke_test_v75.py
if ($LASTEXITCODE -ne 0) { throw 'Live ChessMaker smoke test failed; do not run the tournament yet.' }

if ($RunTournament) {
    Write-Host '=== 10-game paired-colour v7.5 vs v7.4 head-to-head ===' -ForegroundColor Cyan
    python run_v74_v75_head_to_head.py
    if ($LASTEXITCODE -ne 0) { throw 'v7.5 vs v7.4 head-to-head failed.' }

    Write-Host '=== 18-game three-tier benchmark ===' -ForegroundColor Cyan
    python run_v75_18_tournament.py
    if ($LASTEXITCODE -ne 0) { throw 'Three-tier tournament failed.' }
}
Write-Host 'v7.5 validation steps completed.' -ForegroundColor Green
