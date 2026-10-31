# v7.3 Emperor — experimental search-efficiency candidate

## Status

This is a **candidate**, not a promoted champion. It does not overwrite v6.9, v7.1, or v7.2.
The frozen v6.9 reference remains unchanged. Source SHA-256 is recorded in the delivery message.

## Design decisions

The engine starts from the v7.2 codebase, retaining the v7.1 classical search-control fixes and v7.2 side-/piece-aware move-ordering improvements. The evaluator's executable body is unchanged from v7.1 (and v6.9); only its explanatory docstring differs.

Changes in v7.3:

1. **Dynamic conservative LMR.** Keeps the familiar one-ply reduction for late quiet moves. Allows a two-ply reduction only at depth 8+, for very late quiet moves, and protects captures/promotions/checks, checked nodes, killer moves, and strong-history moves.
2. **Bounded LRU transposition table.** Retains deeper entries, refreshes recently used entries, and evicts the least-recently-used entry at capacity instead of flushing the whole table at 90% capacity. TT size remains 200,000.
3. **Directional aspiration widening.** A fail-low widens the lower bound; a fail-high widens the upper bound. The already-established side is not widened unnecessarily.
4. **Check extensions disabled by default.** The v7.2 check-extension experiment is retained behind a configuration flag but disabled in the baseline because the v7.2 pilots did not establish that its extra node cost paid off. Existing low-mobility extensions remain.
5. **Random root tie-breaking is optional and disabled by default.** When explicitly enabled, it selects reproducibly among root moves within 8 cp of the best score, but only where PVS produced fully resolved root scores; zero-window bounds are excluded. It does not add noise to evaluation or internal search. Because PVS often resolves only one candidate exactly, this deliberately conservative experiment may activate infrequently.
6. **More instrumentation.** Logs report TT hits/cutoffs, one-/two-ply LMR counts, aspiration fail-lows/highs, extension counts, and whether random tie-breaking was used.

## Files

- `agent_v73_emperor.py` — engine candidate.
- `test_agent_v73.py` — offline regression tests for helper policies and structural invariants.
- `head_to_head_v69_vs_v73.py` — hash-locked paired benchmark against the frozen champion.
- `head_to_head_v71_vs_v73.py` — hash-locked paired benchmark against the v7.1 reference.

## Installation

Copy both files into the same directory as the existing v7.1 source and the project's `extension/` directory. Do not rename or overwrite any existing engine.

## Validate in PowerShell

```powershell
python -m py_compile .\agent_v73_emperor.py .\test_agent_v73.py
python -m unittest -v test_agent_v73.py
python -c "import chessmaker, extension.board_rules, extension.board_utils; print('ChessMaker environment OK')"
```

The offline unit tests use a stub for the board utility import and do **not** prove that live ChessMaker games work. The third command verifies the local runtime dependency. A live one-game smoke test and a small paired pilot are still required.

## Suggested ablations

The first benchmark is **E0**, the exact file as delivered: check extensions OFF, random tie-break OFF, dynamic LMR ON. The runners verify the engine SHA-256, so do not toggle constants in this file and then bypass the hash check.

Only after E0 has a clean pilot should separate, separately named and hash-locked variants be created:

- **E1:** check extensions ON, with every other setting unchanged.
- **R1:** root tie-break ON, with every other setting unchanged.
- **L1:** two-ply LMR disabled, with every other setting unchanged.

Run each variant separately. Do not combine E1, R1, and L1 in one experiment. Record the exact source hash and configuration for every run.

## Benchmark protocol

1. Use identical starting positions for every engine and swap colours in each pair.
2. Use one PC, fixed worker count, identical per-move and per-game time limits, and separate output directories.
3. The runner requires at least 10 games; start with 10 (five colour-reversed pairs across the five boards), then use 20 paired games per matchup if the pilot is clean.
4. Inspect illegal moves, timeouts, errors, and per-move elapsed time before interpreting win rate.
5. Compare average, median, 90th percentile and maximum **completed** depth; also compare nodes, NPS, TT hit/cutoff rates, LMR counts, aspiration failures, and timeouts.
6. Only after the pilot looks healthy, expand to a diverse position suite and larger paired tournament.

## Important limitations

- ChessMaker is not bundled with this candidate and was not available in the build environment. The runner scripts were syntax-checked and their source-hash/module-loading paths were checked with a stubbed board-utility import, but the real board-construction/validation path and live gameplay have not been run here. No live game or tournament claim is made.
- Maximum depth alone is not an engine-strength metric. Promotion requires paired match results and tactical regression testing.
- Randomisation is an experimental variety feature, not a search-speed technique. Keep it off unless its ablation improves results without increasing tactical errors.
