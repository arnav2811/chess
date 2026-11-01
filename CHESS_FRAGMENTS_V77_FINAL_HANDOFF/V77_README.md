# Chess Fragments v7.7 — final handoff candidate

**Build:** `v7.7-final-stalemate-repetition-guards`  
**Purpose:** Stabilisation candidate based on the observed v7.6 results, packaged with replay-capable benchmark runners and a Claude handoff.  
**Do not call this a tournament-proven champion yet.**

## What's different from v7.6

1. **High-material stalemate-loss verification is no longer skipped for non-king moves.** v7.6 only ran the full one-opponent-reply terminal-loss verifier in low-material positions or for a king move in a crowded position. v7.6 Matches 8 and 12 were Black stalemate losses with 15 pieces still on the board. The result JSON did not record actual moves, so the exact moving piece cannot be confirmed from those old logs; the code-level coverage gap is real nonetheless. v7.7 applies the check to every selected move when the ordinary search path is used.
2. **A slightly larger safety reserve is available in crowded positions.** It is capped at 0.70 seconds / 6% of the computed move budget. Alternative verification in crowded positions remains capped at four candidates to bound the cost.
3. **Equal-score exact tablebase children are repetition-aware.** Exact WDL score always has priority. Only when child scores are exactly equal does v7.7 prefer the child position reached fewer times in the current game. A draw is never promoted over a win, and a win is never traded for repetition avoidance.
4. **Stalemate and tablebase repetition telemetry is added.** Per-move output records guard calls, detected threats, inconclusive checks, replacements, and tablebase repetition avoidance.
5. **Both benchmark runners now save complete move histories.** Each move has its ply, side, engine/opponent label, piece type, from/to coordinates, captures, and board state immediately before the move. This is specifically to prevent a repeat of the v7.6 situation where match metrics existed but the critical move sequence was unavailable.

The existing search architecture, calibrated evaluation terms, PUCT-off setting, exact 65-configuration tablebase, TT hash design, v7.4-conservative LMR, and other established safeguards are retained. There is no wholesale evaluator rewrite or new search algorithm in this release.

## Extracting into the existing project

Extract this ZIP directly into the existing ChessMaker project root. The v7.7 module names are unique, including `endgame_tablebase_v77.py` and `endgame_tb_snippet_v77.py`, so they do not collide with the older v7.5/v7.6 modules. The package intentionally does not overwrite `agent.py`, v6.9, v7.4, or your project's `extension/`, `samples.py`, or opponent modules.

Keep these files together in the project root:

- `agent_v77_final.py`
- `endgame_tablebase_v77.py`
- `endgame_tb_snippet_v77.py`

The existing project must already provide `chessmaker`, `extension.board_utils`, `extension.board_rules`, `samples.py`, `opponent.py`, `strong_opponent.py`, and `master_opponent.py` for live play and tournament runs.

## Validate first

Run PowerShell from the project root:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\validate_v77.ps1
```

The validation script compiles the engine and runners, runs the basic retrograde check, validates all 555 historical tablebase states, runs search-control and v7.7-specific guard regressions, runs the TT-key microbenchmark, and finally attempts one live ChessMaker move. It stops immediately on failure.

Only if the full validation script passes, run:

```powershell
.\validate_v77.ps1 -RunTournament
```

Or run the tournaments separately:

```powershell
python .\run_v74_v77_head_to_head.py
python .\run_v77_18_tournament.py
```

The new result files are:

- `V77_V74_H2H_10.json`
- `V77_TOURNAMENT_18_RESULTS.json`
- `V77_TOURNAMENT_18_METRICS_SUMMARY.json`
- `V77_TT_HASH_MICROBENCH.json`

Both tournament JSON files now include `initial_position` and full `move_history` arrays, as well as search and safeguard telemetry.

## Play against v7.7

```powershell
python .\play_v77.py --side white --board sample0
python .\play_v77.py --side black --board sample0
```

## Current validation status

Passed in the build environment:

- Python compilation of the engine, tests, benchmark and runners.
- All 65 tablebase configurations load.
- Decisive K+Q probe returns the expected `+95000`.
- All 555 unique 3-/4-piece positions extracted from the historic 600-game corpus match expected WDL (240 WIN, 227 LOSS, 88 DRAW).
- Legacy material contempt cannot alter exact DRAW=0.
- Existing history, LMR, futility, TT-key and root-tablebase regressions.
- New v7.7 regression: a high-material non-king move is sent through the terminal-loss verifier; a proven unsafe choice is replaced by a verified safe alternative.
- New v7.7 regression: equal-WDL tablebase choices prefer less-repeated positions, without overriding superior WDL.
- TT-key microbenchmark repeated five times with 200,000 calls per run.

**Not passed / not run in this build environment:** the live ChessMaker smoke test and any v7.7 tournament. The environment does not contain the `chessmaker` package (`ModuleNotFoundError`). This is an environment limitation, not evidence that the user's installed project will fail. Run the hard-gated validation in the actual Windows project before the tournaments.

## Important operating rule

Keep `agent.py`, v6.9 Frozen Overnight and v7.4 Tactical Guard unchanged. Treat v7.7 as a final handoff candidate until it passes live validation and fresh paired-colour testing. The version label is not a strength claim.
