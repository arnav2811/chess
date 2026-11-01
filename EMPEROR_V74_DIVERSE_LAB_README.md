# EMPEROR v7.4 — Tactical Guard + Diverse Self-Play Lab

**Status:** v7.4 is an experimental candidate. It is not promoted and has not been validated against a live ChessMaker installation in the authoring environment.

## What changed in v7.4

The supplied 35-ply human game exposed two concrete tactical failure patterns:

- Black's Right moved to `(3,2)` and White's Bishop captured it on the very next move.
- Black later allowed White's pawn to reach its promotion square on the next move.

The v7.4 source adds a bounded immediate material-loss guard and a next-move promotion guard. The material check examines the opponent's capture, our immediate reply, what that reply actually wins, and whether the replying piece can itself be taken immediately. A checking move alone does not cancel a major-piece-loss warning. The promotion check only flags an immediate promotion when the promoted piece cannot be captured at once.

The selected move is only replaced when the selected root score and alternative root score are exact search results, and the alternative is within 150 centipawns. It examines at most four alternatives. The evaluator is AST-identical to frozen v7.3; PVS/Negamax, iterative deepening, TT, aspiration windows, quiescence, LMR, piece values and normal move ordering are unchanged. PUCT, check extensions and root random tie-breaking remain OFF.

This is a targeted safety layer, not a complete static-exchange evaluator or a guarantee against every tactic. The guard can also decline to intervene when the time reserve is exhausted or an exact root score is unavailable.

## Diverse self-play: 600 unique starting positions

`emperor_v74_diverse_selfplay.py` creates a stored corpus of **600 distinct legal positions** before it starts the games. Each position is produced by a seeded random legal prelude of 4–14 plies, with a mild preference for quiet development while retaining tactical captures. A canonical hash includes every piece's type, side, square, and side to move; duplicate positions are rejected.

The start side is balanced 300 White-to-move / 300 Black-to-move. The generator cycles evenly through 13 5×5 layouts:

- Original `sample0`–`sample4` from the project.
- Eight additional controlled back-rank permutations, `sample5`–`sample12`. These use one King, Bishop, Knight, Queen and Right per side, with the King in the centre. They are extra experimental layouts, not changes to the coursework's default board.

Each self-play game loads two independent Python module instances from the exact same v7.4 source, one for White and one for Black. PUCT, check extensions and root random tie-breaking stay off. The complete opening prelude, every pre/post-move board, search metrics, tactical-guard activations, captures, game result and timing are logged. The opening corpus is saved before gameplay, so `--resume` reuses precisely the same positions.

**Important:** self-play is a diagnostic dataset, not a strength rating. Since both sides use v7.4, its win/loss split cannot prove that v7.4 is stronger than v7.3 or v6.9. The value is in finding hangs, promotion races, repeated decision positions, guard triggers, search failures and candidate tactical positions.

## Files

- `agent_v74_tactical_guard.py` — candidate engine; source hash locked in the runners.
- `agent_v73_emperor.py` — frozen evaluator/reference source for the v7.4 regression test.
- `test_agent_v74.py` — offline tactical-guard regression tests.
- `head_to_head_v73_vs_v74.py` — balanced v7.3-v7.4 head-to-head runner on the five original layouts.
- `emperor_v74_diverse_selfplay.py` — unique-position 600-game v7.4 self-play runner.
- `analyze_emperor_v74_selfplay.py` — tactical/data-diversity analysis.
- `test_emperor_v74_diverse_lab.py` — offline test suite for layouts and analysis.

## Install

Copy these files to the root of the existing Chess Fragments project, beside the existing `extension/` directory. Do not replace `agent.py`, `agent_v73_emperor.py`, or any frozen champion file.

## 1. Offline checks (PowerShell)

```powershell
python -m py_compile .\agent_v74_tactical_guard.py .\test_agent_v74.py .\head_to_head_v73_vs_v74.py .\emperor_v74_diverse_selfplay.py .\analyze_emperor_v74_selfplay.py .\test_emperor_v74_diverse_lab.py
python -m unittest -v test_agent_v74.py test_emperor_v74_diverse_lab.py
```

Expected authoring-environment result: **19 tests passed**. The tests use ChessMaker stubs for tactical guard logic; they do not prove live board legality.

## 2. Live validation on the project machine

```powershell
python .\emperor_v74_diverse_selfplay.py --validate-only
```

This imports ChessMaker and the project extensions, validates all 13 layouts for opening legal moves and king counts, checks that the two v7.4 seats are isolated modules with the required switches OFF, and generates a 20-position unique-opening smoke corpus (10 starts for each side to move).

Do not run the 600 games if this fails.

## 3. First 10-game live pilot

```powershell
python .\emperor_v74_diverse_selfplay.py --games 10 --workers 2 --thinking-time 6 --game-time 240 --seed 740600 --min-opening-plies 4 --max-opening-plies 14 --out .\emperor_lab\v74_pilot10
```

Inspect `games.csv` and the output for zero worker exceptions, zero illegal move/application errors, zero opening replay mismatches, and no unexpected time forfeits. Then analyse it:

```powershell
python .\analyze_emperor_v74_selfplay.py .\emperor_lab\v74_pilot10 --out .\emperor_lab\v74_pilot10_analysis
```

## 4. Full 600-game diverse self-play

After the pilot is clean:

```powershell
python .\emperor_v74_diverse_selfplay.py --games 600 --workers 4 --thinking-time 8 --game-time 300 --seed 740600 --min-opening-plies 4 --max-opening-plies 14 --out .\emperor_lab\v74_unique600
```

This produces 600 distinct starting positions, not 600 repeated runs from the same five starting boards. The generator balances the side to move and distributes positions across the 13 layouts. Use 2 workers instead of 4 if the laptop becomes too hot or unresponsive. Run only one tournament at a time and keep the machine plugged in/awake.

To resume an interrupted run, repeat the exact command with `--resume` appended:

```powershell
python .\emperor_v74_diverse_selfplay.py --games 600 --workers 4 --thinking-time 8 --game-time 300 --seed 740600 --min-opening-plies 4 --max-opening-plies 14 --out .\emperor_lab\v74_unique600 --resume
```

## 5. Analyse what the 600 games teach us

```powershell
python .\analyze_emperor_v74_selfplay.py .\emperor_lab\v74_unique600 --out .\emperor_lab\v74_unique600_analysis
```

The analysis directory contains:

- `REPORT.md` and `analysis.json` — unique-position coverage, unique trajectories, repeat rates, board/colour coverage, tactical event and guard counts.
- `tactical_events.jsonl` — observed captures, immediate Right/Queen hangs, promotions, and guard triggers.
- `tactical_position_bank.jsonl` — deduplicated high-signal positions with the observed move and surrounding board state.
- `tactical_regression_candidates.jsonl` — positions ready for independent review; it intentionally does **not** invent a correct move or label the engine's chosen move as ground truth.

A major-piece hang is detected when the opponent captures a Right or Queen on the very next ply. Promotion events are labelled separately. These are concrete review leads, not automatically proven search bugs. Root score rows are labelled as score/bound hints; PVS bounds are not ground truth.

## 6. Strength test against frozen v7.3

The 600-game self-play set diagnoses v7.4's own tactical behaviour. For a strength comparison, use the separate hash-locked H2H runner:

```powershell
python .\head_to_head_v73_vs_v74.py --validate-only
python .\head_to_head_v73_vs_v74.py --games 10 --workers 2 --thinking-time 12 --game-time 300 --seed 740074 --out .\h2h_runs\v73_vs_v74_smoke10
```

That H2H smoke uses the five original layouts and balanced colour reversal. It is separate from the 600 unique-position self-play corpus. Do not promote v7.4 from a 10-game pilot or self-play alone; use a larger paired H2H and manually inspect every guard replacement, hanging-piece event, promotion race, error and timeout first.

## Candidate source fingerprint

`agent_v74_tactical_guard.py` SHA-256 (canonical LF line endings):

```text
f071799b7ac06d30a3f912adc541313942e536cf0c1285d5cff294e73abd57dd
```

The self-play and H2H runners stop if their expected engine fingerprints do not match.
