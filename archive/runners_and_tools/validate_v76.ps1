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

Invoke-PyCheck @('-m', 'py_compile', 'agent_v76_exact_tablebase.py', 'endgame_tablebase.py', 'endgame_tb_snippet.py', 'run_v74_v76_head_to_head.py', 'run_v76_18_tournament.py', 'test_v76_historical_tablebase_corpus.py', 'test_v76_engineering_controls.py') 'Compile candidate and benchmark scripts'
Invoke-PyCheck @('test_v76_tablebase.py') 'Basic retrograde tablebase regression'
Invoke-PyCheck @('test_v76_historical_tablebase_corpus.py') '600-game historical tablebase regression corpus'
Invoke-PyCheck @('test_v76_engineering_controls.py') 'Search controls, hash, LMR and root-TB tests'
Invoke-PyCheck @('benchmark_v76_tt_hash.py') 'Transposition-key microbenchmark'
Invoke-PyCheck @('smoke_test_v76.py') 'Live ChessMaker engine smoke test'

Write-Host "`nAll pre-tournament checks passed." -ForegroundColor Green

if ($RunTournament) {
    Invoke-PyCheck @('run_v74_v76_head_to_head.py') '10-game paired-colour v7.4 vs v7.6 head-to-head'
    Invoke-PyCheck @('run_v76_18_tournament.py') '18-game three-tier v7.6 diagnostic tournament'
    Write-Host "`nTournament outputs:" -ForegroundColor Green
    Write-Host '  V76_V74_H2H_10.json'
    Write-Host '  V76_TOURNAMENT_18_RESULTS.json'
    Write-Host '  V76_TOURNAMENT_18_METRICS_SUMMARY.json'
}
