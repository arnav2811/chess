# v7.5 Endgame Depth candidate

**Status: experimental candidate; not yet validated in the live ChessMaker runtime or a tournament.** Keep v7.4, v7.3 and v6.9 unchanged.

## Changes relative to v7.4

1. **Retrograde tablebase integration.** Calls the 65-configuration tablebase from both Negamax and quiescence before approximate evaluation. The current generated database provides exact WDL for supported positions with two kings and one or two non-king pieces (three or four pieces total). It does not cover every possible ≤4-piece position; unsupported configurations safely fall back to the normal search.
2. **Tablebase diagnostics.** Per-move counters expose availability, probes, hits, wins, losses and draws.
3. **Deadline protection.** Polls the deadline every 8 search nodes, after expensive move generation, before/after each root child, and before aspiration retries. An interrupted iteration retains the last fully completed iteration's move.
4. **Persistent aged history.** History scores now survive between this engine's turns within a game, decay once per turn, and are capped; they reset at a new-game boundary. Killer moves remain turn-local.
5. **Conservative LMR adjustment.** The second-ply reduction is permitted one move earlier at high depth, while tactical moves, checks, killers and sufficiently strong history remain protected.
6. **Preserved safeguards.** v7.4's anti-repetition policy, anti-loss checks, material guard, promotion guard, anti-stalemate evaluation, PVS, aspiration windows, TT and quiescence remain in place. PUCT stays disabled.

## Included files

- `agent_v75_endgame_depth.py`
- `endgame_tablebase.py` and `endgame_tb_snippet.py`
- `run_v75_18_tournament.py`
- `run_v74_v75_head_to_head.py` (10 games, paired by board and colour against v7.4)
- `agent_v74_tactical_guard.py` (reference opponent for that comparison)
- `smoke_test_v75.py`
- `test_v75_tablebase.py`
- `test_v75_search_controls.py`
- `validate_v75.ps1`
- `extension/` helpers used by the project

Keep the project's existing `chessmaker/` dependency, `opponent.py`, `strong_opponent.py`, `master_opponent.py`, `samples.py`, and other coursework files in the same project directory. Do not delete or overwrite the frozen agents.

## One-command validation (PowerShell)

From the project directory after extracting this package:

```powershell
.\validate_v75.ps1 -RunTournament
```

The script compiles the files, runs framework-independent tablebase and search-control tests, runs the live ChessMaker smoke test, then runs a 10-game paired-colour v7.5-v7.4 comparison and the 18-game three-tier benchmark. It stops at the first failure. Outputs are `V74_V75_H2H_10.json` and `TOURNAMENT_18_RESULTS.json`.

To run only the short checks and live smoke test, omit `-RunTournament`.

## What has and has not been verified here

Verified in the available environment:
- Python compilation of the v7.5 agent and test/runner scripts.
- All 65 tablebase configurations load.
- A real decisive K+Q table entry is correctly returned as a win by the same agent helper used in search.
- History ageing, the adjusted LMR thresholds and expired-root fallback pass focused regression tests.

Not verified here:
- Live Board/Piece integration with the actual ChessMaker runtime (not installed in this environment).
- Search NPS or average completed-depth improvement on real games.
- Zero clock forfeits in the full match runner.
- Win-rate improvement over v7.4/v6.9.

A tablebase hit proves the exact WDL result for that supported position; it does **not** prove the whole engine is stronger. Promote v7.5 only after the live smoke test, paired-colour head-to-head tests and timing/depth comparisons pass.
