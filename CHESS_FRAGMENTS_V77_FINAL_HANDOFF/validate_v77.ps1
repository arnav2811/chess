param(
    [switch]$RunTournament
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUNBUFFERED = '1'

function Invoke-PyCheck([string[]]$ArgsToPython, [string]$Label) {
    Write-Host "`n=== $Label ===" -ForegroundColor Cyan
    & python @ArgsToPython
    if ($LASTEXITCODE -ne 0) {
        throw "Python check failed ($Label), exit code $LASTEXITCODE. Stop here; do not run tournaments."
    }
}

Invoke-PyCheck @('-m', 'py_compile', 'agent_v77_final.py', 'endgame_tablebase_v77.py', 'endgame_tb_snippet_v77.py', 'agent_v74_tactical_guard_v77baseline.py', 'run_v77_18_tournament.py', 'run_v74_v77_head_to_head.py', 'test_v77_tablebase.py', 'test_v77_historical_tablebase_corpus.py', 'test_v77_engineering_controls.py', 'test_v77_final_guards.py', 'benchmark_v77_tt_hash.py', 'smoke_test_v77.py', 'play_v77.py') 'Compile v7.7 engine, tests and runners'
Invoke-PyCheck @('test_v77_tablebase.py') 'Basic exact retrograde tablebase regression'
Invoke-PyCheck @('test_v77_historical_tablebase_corpus.py') '555-position historical tablebase regression'
Invoke-PyCheck @('test_v77_engineering_controls.py') 'History, LMR, futility, TT and root-TB regressions'
Invoke-PyCheck @('test_v77_final_guards.py') 'High-material stalemate and repetition regressions'
Invoke-PyCheck @('benchmark_v77_tt_hash.py') 'TT-key microbenchmark (not whole-engine NPS)'
Invoke-PyCheck @('smoke_test_v77.py') 'Live ChessMaker one-move smoke test'

Write-Host "`nAll pre-tournament checks passed." -ForegroundColor Green

if ($RunTournament) {
    Invoke-PyCheck @('run_v74_v77_head_to_head.py') '10-game paired-colour v7.4 vs v7.7 head-to-head'
    Invoke-PyCheck @('run_v77_18_tournament.py') '18-game three-tier v7.7 diagnostic tournament'
    Write-Host "`nTournament outputs (now include complete move histories):" -ForegroundColor Green
    Write-Host '  V77_V74_H2H_10.json'
    Write-Host '  V77_TOURNAMENT_18_RESULTS.json'
    Write-Host '  V77_TOURNAMENT_18_METRICS_SUMMARY.json'
}
