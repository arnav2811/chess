# Two-PC Chess Fragments self-play controls — 200 games

## Experiment design

Run 100 games per engine version, for 200 games total:

- PC1: 50 games of frozen v6.9 vs an independent frozen v6.9 instance, then 50 games of v7.1 vs an independent v7.1 instance (PUCT forced OFF).
- PC2: same two 50-game jobs, using a separate seed range.
- Each machine runs **both** engine versions. This crossover design reduces hardware confounding when comparing White/Black win proportions.
- Each 50-game job contains 25 paired RNG-stream swaps, with equal board coverage: 10 games on each of sample0–sample4.
- Across both PCs, each engine has 100 games, 20 per board.

Both sides in a game are separate imports of the same source file. Their transposition tables, opening caches, history heuristics, repetition memory, own-player clocks and RNG streams are independent. The frozen v6.9 and v7.1 source files are checked against SHA-256 hashes before any game starts. v7.1 PUCT is forcibly disabled by the runner.

This is a **self-play side-bias / first-player control**, not a direct v6.9-v7.1 head-to-head rating test.

## Required environment

Run inside the working coursework project directory, where:

- Python 3.13 is available (or the same working Python version used for the last tournament).
- `chessmaker` is importable in that Python environment.
- `extension/` is present. This bundle includes the exact `board_rules.py`, `board_utils.py`, `piece_pawn.py` and `piece_right.py` files uploaded for this experiment.

Do not use a different `chessmaker` package or change the movement/rules helpers between PCs. The bundle does not include the third-party `chessmaker` library itself.

## Install the bundle on BOTH PCs

Copy `chess_selfplay_2pc_bundle.zip` to each PC. On each computer, open PowerShell in the existing project root (the folder containing `extension` and where `python -c "import chessmaker"` works), then extract the ZIP into that folder:

```powershell
Expand-Archive "$HOME\Downloads\chess_selfplay_2pc_bundle.zip" -DestinationPath . -Force
```

This installs the two audited engine filenames, the runner, merger, tests and helper files under `extension/`. It does **not** replace `agent.py`.

Preflight:

```powershell
python --version
python -c "import chessmaker, extension.board_rules, extension.board_utils; print('Chess Fragments environment OK')"
python -m py_compile selfplay_control_runner.py merge_selfplay_results.py test_selfplay_control_runner.py agent_v69_frozen_overnight.py agent_v71_adaptive_tactical_hybrid.py
python -m unittest -v test_selfplay_control_runner.py
```

Then validate both engines and all five board layouts without starting games:

```powershell
python selfplay_control_runner.py --engine v69 --validate-only
python selfplay_control_runner.py --engine v71 --validate-only
```

Do not launch the long run unless both validation commands pass on both PCs.

## Run PC1

From the project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_selfplay_pc1.ps1 -Workers 8
```

PC1 runs:

- `selfplay_runs\pc1_v69_50`
- `selfplay_runs\pc1_v71_50`

PC1 seed base: `730069`.

## Run PC2

From the same project root on PC2:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_selfplay_pc2.ps1 -Workers 8
```

PC2 runs:

- `selfplay_runs\pc2_v69_50`
- `selfplay_runs\pc2_v71_50`

PC2 seed base: `730169`.

If PC2 has substantially fewer CPU cores, use the same lower worker count for both versions on PC2, e.g. `-Workers 6`. Do not run multiple tournament scripts simultaneously on one PC. Keep both versions on each PC at the same worker count.

## Expected outputs from each 50-game job

Each run folder contains:

- `manifest.json` — hashes, environment, settings and seed.
- `games.jsonl` — append-only checkpoint, one completed game per line.
- `games.json` and `games.csv` — final game-level results.
- `moves.jsonl` — move-by-move log, including pre/post board state, selected piece/from/to/captures, search diagnostics and top root candidates when available.
- `move_metrics.csv` — flattened move-level diagnostics.
- `summary.json` — winner colour, board-level results, pair consistency, game lengths, nodes/depth and throughput.

If a run is interrupted, re-run the same command with `--resume` and the same `--out` folder. Do not delete `games.jsonl`.

## Transfer and merge the results

Once both PCs finish, copy PC2's two run folders to PC1, under `selfplay_runs\pc2_v69_50` and `selfplay_runs\pc2_v71_50`.

Optional transfer archive on PC2:

```powershell
Compress-Archive -Path .\selfplay_runs\pc2_v69_50, .\selfplay_runs\pc2_v71_50 -DestinationPath .\pc2_selfplay_results.zip -Force
```

On PC1, extract it into `selfplay_runs` (check the extracted folder names; move them to the exact names above if the archive created an extra parent folder):

```powershell
Expand-Archive .\pc2_selfplay_results.zip -DestinationPath .\selfplay_runs -Force
```

Merge the four result folders:

```powershell
python merge_selfplay_results.py .\selfplay_runs\pc1_v69_50 .\selfplay_runs\pc2_v69_50 .\selfplay_runs\pc1_v71_50 .\selfplay_runs\pc2_v71_50 --out .\selfplay_runs\combined_200
```

The merger refuses to combine runs with different engine hashes or a v7.1 run where PUCT was not explicitly disabled. It creates `combined_summary.json`, `combined_games.csv` and `combined_report.md`.

## Runtime estimate

The latest 20-game, 8-worker mixed head-to-head completed at about 74 games/hour. At that observed rate, 50 games is roughly 41 minutes and the two sequential jobs on each PC roughly 81 minutes. Same-engine games can be longer or shorter; allow the full three-hour window and watch the runner's live throughput. This is an estimate, not a guarantee.

## Interpretation

For each version, inspect:

- White win share across 100 self-play games.
- Whether the White advantage is consistent across all five boards.
- Whether paired RNG-stream swaps produce stable results.
- Draws, timeouts, illegal moves and engine errors.
- Whether any board (especially sample3/sample4) behaves differently.
- Per-move depth/nodes and exact pre/post board states around losses.

A strong White win share in both self-play conditions would support a first-player advantage in these setups. It would not, by itself, prove v6.9 is stronger than v7.1. A cross-engine tournament is a separate experiment.
