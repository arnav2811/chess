# v7.1 Adaptive Tactical Hybrid — Experimental Report

**Project:** COMP2321 Chess Fragments, 5×5 custom chess variant  
**Date:** 30 October 2026  
**Status:** Experimental candidate; v6.9 remains champion  

## Executive decision

v7.1 is a controlled experiment, not a claimed strength breakthrough. It retains v6.9's classical Negamax/PVS engine and adds a small, optional PUCT root probe plus bounded tactical search changes. The candidate has passed source compilation and six structural tests. It has **not** been run against real ChessMaker boards in this authoring environment because the `chessmaker` dependency is not installed here.

## Why the design is conservative

The actual 5×5 rules make terminal mobility central: checkmate and stalemate/no-legal-move both lose; only two Kings and fivefold repetition are draws; each player has a 300-second total clock and a per-move thinking limit. The custom Right combines rook-like sliding movement and a jumping knight move. A generic 8×8-chess MCTS or neural network cannot safely assume standard chess semantics.

The provided `board_rules.py` also mutates repetition history inside `get_result()`. The inherited engine deliberately avoids calling that function inside search. v7.1 continues to use the inherited lightweight terminal check and legal-move detection rather than calling the mutating result function from its tree.

## Architecture

```text
              Root position + legal moves
                         |
                         v
      Iterative-deepening Negamax / PVS / alpha-beta
        TT + aspiration + LMR + bounded quiescence
                         |
                         v
        Completed root candidates and centipawn scores
                         |
              Is the root ambiguous?
                  /            \
                no              yes
                |                |
         Keep classical      Up to 4 root moves
             move            within 180 cp
                                  |
                                  v
                     Bounded PUCT tree (<=28 sims)
                       depth <=4, <=0.18 seconds
                                  |
                                  v
                    Adaptive handcrafted priors
                 behind: controlled complications
                 ahead: sound exchange / conversion
                                  |
                                  v
                 Classical choice / PUCT tie-break
                                  |
                                  v
                 One-reply terminal-loss verifier
                                  |
                                  v
                         Return legal move
```

### PUCT details

The implementation uses the conventional PUCT selection shape:

\[
U(s,a) = -Q(s,a) + c_{puct}P(s,a)\frac{\sqrt{N(s)}}{1+N(s,a)}
\]

The child value is negated because it is stored from the child's side-to-move perspective. The leaf value comes from the existing hand-coded evaluator, mapped to a bounded range with `tanh`. Terminal wins/losses map to ±1; draws map to 0; a node with no legal moves is a loss for the side to move.

The probe is deliberately gated:

- It only runs after a completed classical iterative-deepening search.
- It is skipped for decisive mate-range scores.
- Normalised root-score entropy must be at least 0.38.
- It only considers up to four legal moves no more than 180 cp below the classical best.
- It is limited to 28 simulations, depth 4 and 0.18 seconds maximum.
- It leaves a portion of the pre-existing safety reserve for the final anti-loss check.
- It only overrides the classical move when the challenger receives at least two more visits and its backed-up value is not more than 0.06 worse.

This is **not neural MCTS**. Priors are simple deterministic features: score proximity, captures, promotion, plausible direct checks and centrality. The policy adapts its appetite for complications from the classical root score. These priors influence exploration; they do not prove that a move is sound.

## Search changes beyond PUCT

### Quiet checks alongside captures

The inherited q-search considered quiet checks only if no capture/promotion candidate existed. v7.1 can now consider one quiet checking move alongside captures, or two when there are no captures. It keeps the previous q-depth, check budget and near-root constraints, filters geometrically, then verifies that the cloned child actually checks the enemy king.

This is a deliberate, bounded increase in tactical breadth. Its main risk is consuming time in check-heavy positions; the per-move diagnostics and tournament clocks must determine whether the added branch budget is acceptable.

### Root driver

v7.1 retains v7.0's root-PV carry-forward, hard TT/PV ordering tier and fail-high root cutoff. These changes are included because they are search-driver improvements independent of MCTS.

### Determinism and telemetry

Fallback selection is deterministic rather than random. Each move can record completed iterative-deepening depths, nodes, elapsed time, aborted depth/nodes, and PUCT use/simulations/time/mode/override. The paired runner captures these fields into JSON and CSV.

## Exact source provenance

| File | Role | Canonical SHA-256 |
|---|---|---|
| `agent_v69_frozen_overnight.py` | Frozen incumbent; exact uploaded v6.9 champion bytes | `df5cfb7305e8374ed45b6a862e6934cf0f3168e7c7eca9b1c18e9cfd517e08bd` |
| `agent_v71_adaptive_tactical_hybrid.py` | Experimental candidate | `488b051b3dce2e49f3b883a16dc12eddaba31510a0596bde7b83247c933865de` |

The uploaded v6.9 source starts with a stale “v6.6” header comment, but its canonical SHA-256 matches the audited frozen v6.9 file. The v7.1 candidate is a new copy and does not edit that source.

## Validation performed here

- `py_compile` passed for the agent, tests and head-to-head runner.
- Six mock/structural unit tests passed:
  1. PUCT softmax priors normalise and remain stable.
  2. Root entropy increases for close candidate scores.
  3. PUCT returns one of the legal root moves and leaves the root board unchanged.
  4. Decisive mate-range root scores skip PUCT.
  5. Adaptive priors behave differently in winning vs losing modes.
  6. A no-legal-move leaf is treated as a loss.
- The paired runner verified the frozen v6.9 and v7.1 hashes and generated a 10-game/5-pair schedule.

These are structural tests, not ChessMaker integration tests or strength results. The ChessMaker package is missing from this environment, so no genuine board move, game, timing budget or match result has been measured here.

## How to run on the coursework machine

Place these files in the project root beside the existing `extension` directory and the installed `chessmaker` package:

- `agent_v69_frozen_overnight.py`
- `agent_v71_adaptive_tactical_hybrid.py`
- `head_to_head_v69_vs_v71.py`
- `test_agent_v71.py`

Then run in PowerShell:

```powershell
python -m py_compile agent_v71_adaptive_tactical_hybrid.py head_to_head_v69_vs_v71.py test_agent_v71.py
python -m unittest -v test_agent_v71.py
python head_to_head_v69_vs_v71.py --games 10 --workers 8 --puct on
```

Run the matched ablation with the identical candidate source and frozen incumbent, but with the PUCT switch disabled:

```powershell
python head_to_head_v69_vs_v71.py --games 10 --workers 8 --puct off
```

The runner writes `puct_enabled` into the manifest. It changes the candidate module's runtime flag after hash verification; it does not edit the agent file. Compare the two runs before attributing any improvement to MCTS.

The runner refuses to start if either engine hash differs, creates a fresh output directory, runs five colour-reversed board/seed pairs, and writes `manifest.json`, `games.json`, `summary.json`, `games.csv` and `move_metrics.csv`. It defaults to 10 games so the first run is a pilot, not a long overnight commitment.

Only after the 10-game pilot has zero errors and its clocks/diagnostics look sane should you run:

```powershell
python head_to_head_v69_vs_v71.py --games 40 --workers 8 --puct on
```

A larger tournament should follow only if the pilot result warrants it. The `--puct on` and `--puct off` modes provide the required ablation without editing the candidate source.

## Risks and known limitations

1. No full ChessMaker runtime validation has been performed here.
2. A small number of PUCT simulations may not provide enough evidence to improve root choice; the probe is intentionally not allowed to overrule clearly superior alpha-beta scores.
3. The root entropy is score ambiguity, not a direct measure of tactical chaos or opponent difficulty.
4. The handcrafted policy is not trained and may be biased; its effect must be ablated.
5. Extra quiet checks can increase q-search cost. Check completed depths, per-move elapsed times and game-clock use.
6. The existing evaluation uses pseudo-attack maps and is not a complete legal SEE or pin-aware attack model.
7. This candidate must not be described as stronger until a paired, reproducible tournament supports that statement.

## Promotion criteria

Keep v6.9 as champion unless v7.1 demonstrates a repeatable improvement across boards and colours, with no new terminal-safety failures, illegal moves, timeouts or serious per-move clock regressions. Require a PUCT-on vs PUCT-off ablation before attributing any improvement to MCTS. Do not claim conventional chess Elo from this custom-variant local benchmark.
