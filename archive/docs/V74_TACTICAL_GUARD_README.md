# EMPEROR v7.4 — Tactical Guard candidate

**Status: revised experimental candidate; not yet live-validated or promoted.**

This version is based on the exact frozen v7.3 Emperor source. It leaves the v7.3 file untouched and does not change the evaluator or main search architecture.

## What the supplied game exposed

In the 35-ply ledger, Black's 10th move moved the Right from `(4,0)` to `(3,2)`, where White's bishop immediately captured it. Later, Black's 16th move allowed White's pawn on `(4,1)` to promote on its next move. The ledger is enough to identify those tactical failures, but not enough to prove the exact search reason v7.3 chose the moves.

## Changes in revised v7.4

1. **Material-loss guard.** After search, it checks legal opponent captures of our major pieces and examines our immediate replies. It credits actual recaptures/countercaptures and charges the replying piece back if the opponent can immediately take it. A checking move by itself no longer makes the material loss disappear.
2. **Promotion guard.** It checks whether the opponent can promote on its next move, then simulates the promotion and checks whether we can immediately capture the promoted piece. Only an unanswerable immediate promotion is treated as an emergency.
3. **Conservative replacement.** It only considers alternatives with fully resolved root scores, requires the selected move itself to have an exact score, examines at most four alternatives, and permits a maximum score drop of **150 cp** (1.5 pawns). PVS bounds are not used. It will leave the original move in place if no qualifying safe alternative exists.
4. **Diagnostics.** Search records now include `material_guard`, `material_guard_loss_cp`, `material_guard_replacement`, `promotion_guard`, and `promotion_guard_replacement`.

The evaluator, material values, PVS/Negamax, iterative deepening, TT, aspiration windows, quiescence, LMR, PUCT default (OFF), check extensions (OFF), and random root tie-break (OFF) are otherwise unchanged.

This is a narrow guard, not a complete SEE, tactical solver, or guarantee against all promotion races. The immediate exchange check is deliberately bounded and can return inconclusive when its time reserve expires.

## Install

Copy these files to the root of the existing Chess Fragments project:

- `agent_v74_tactical_guard.py`
- `test_agent_v74.py`
- `head_to_head_v73_vs_v74.py`

Keep `agent_v73_emperor.py` unchanged beside them. Do not overwrite `agent.py` or any frozen engine.

## Offline checks

```powershell
python -m py_compile .\agent_v74_tactical_guard.py .\test_agent_v74.py .\head_to_head_v73_vs_v74.py
python -m unittest -v test_agent_v74.py
```

The tests stub ChessMaker. They check the guard logic and evaluator identity; they do not prove real-board move generation or game legality.

## Live validation, then first paired smoke test

Run from the project root, with the existing `extension/` folder and installed ChessMaker package:

```powershell
python .\head_to_head_v73_vs_v74.py --validate-only
```

Only after that passes, run the first 10-game colour-reversed pilot:

```powershell
python .\head_to_head_v73_vs_v74.py --games 10 --workers 2 --thinking-time 12 --game-time 300 --seed 740074 --out .\h2h_runs\v73_vs_v74_smoke10
```

This is five colour-reversed pairs across the five supplied board layouts. Do not start with a 100-game run before checking the pilot for zero illegal moves, exceptions, and timeouts.

The runner writes `games.json`, `summary.json`, `games.csv`, `move_metrics.csv`, and `moves.jsonl`. The CSV/JSONL search metrics include guard triggers and successful replacements. `manifest.json` records exact source hashes and experiment settings.

## Promotion criteria

Do not promote v7.4 based on one human game or the 10-game smoke. Inspect the move ledger around each guard trigger, then run a larger paired v7.3 comparison with balanced colours and board layouts. Check overall score, White/Black score separately, paired reversals, guard false positives, errors, timeouts, and whether the candidate still handles sound sacrifices. A higher win rate is not sufficient if it creates more illegal moves or clock failures.
