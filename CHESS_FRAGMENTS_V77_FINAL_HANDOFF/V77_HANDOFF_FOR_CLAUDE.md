# Chess Fragments AI — handoff for Claude

**Current candidate:** v7.7 (`agent_v77_final.py`)  
**Previous measured candidate:** v7.6 (`agent_v76_exact_tablebase.py`)  
**Frozen comparison reference:** v7.4 Tactical Guard  
**Known-good historical reference:** v6.9 Frozen Overnight  
**Assessment timing:** User said the assessment is in four days from the 2026-11-01 conversation. Prioritise reliability and evidence over broad redesign.

---

## Read this first

The user is handing the project to you after repeated iterations where improvements were claimed too early. Do not make speculative claims, do not silently alter the champion, and do not say a new version is stronger unless actual paired-colour results support it. The user has substantial prior research and does not want to repeat it.

Start by reading:

1. `V77_README.md`
2. `V77_CHANGELOG.md`
3. `V77_VALIDATION_REPORT.md`
4. `agent_v77_final.py`
5. `V76_TOURNAMENT_18_METRICS_SUMMARY.json` and `V76_TOURNAMENT_18_RESULTS.json` under `evidence/v76_results/`
6. `V76_V74_H2H_10.json` under `evidence/v76_results/`
7. `evidence/history/CHESS_FRAGMENTS_ENGINE_DEVELOPMENT_LOG.md`

The v7.7 engine is a candidate/handoff build, **not a live-validated champion**. Its offline tests pass in the build environment. That environment lacks `chessmaker`, so the live smoke test and v7.7 tournaments must be run in the user's actual Windows project.

## Project constraints and environment

- Game: custom 5×5 Chess Fragments variant, not standard 8×8 chess.
- A side with no legal moves loses, whether or not it is in check. Stalemate is therefore a loss, not a draw.
- User's project root previously used: `C:\Users\arnav\Downloads\CW-COMP2321-fullgame -Post Cut V5.6`.
- Windows 11, PowerShell, VS Code.
- User has an existing `chessmaker` dependency, `extension/` helpers, `samples.py`, `opponent.py`, `strong_opponent.py`, and `master_opponent.py`.
- Preserve existing `agent.py`, `agent_v69_frozen_overnight.py`, `agent_v74_tactical_guard.py`, and all old tournament JSON. Do not overwrite them.
- v7.7 files use unique names (`agent_v77_final.py`, `endgame_tablebase_v77.py`, `endgame_tb_snippet_v77.py`) to avoid the stale-adapter collision experienced while extracting v7.6.

## What was built for v7.7

v7.7 is a narrow stabilisation of v7.6, not a new search architecture.

### A. High-material one-reply terminal-loss verification

In v7.6, `_entropy_guided_anti_loss` contained this policy:

- Fully check one-opponent-reply terminal threats at low material.
- At high material, only do the check when the chosen piece is the king.
- Return early for high-material non-king moves.

The v7.6 18-game diagnostic recorded two losses as Black against Strong, Matches 8 and 12. Both games ended at ply 16 with 15 pieces left, by `Stalemate (no more possible moves) - black loses`. The v7.6 result JSON has no coordinates or move sequence. Therefore we cannot prove from that JSON whether the last Black move was a king move or non-king move, nor reconstruct the precise blunder. The high-material non-king bypass is nevertheless a real guard-coverage blind spot given those high-material terminal losses.

v7.7 removes that bypass and applies `_opponent_has_immediate_terminal_win` to every selected move when the normal search path is used. The verifier enumerates opponent replies and checks whether any reply leaves our side with no legal move. If so, it tries up to four alternative candidates in crowded positions, within a bounded safety reserve. The crowded-position reserve is now capped at 0.70 seconds / 6% of the computed budget. This can trade a small amount of search time for terminal safety; measure it in the actual environment.

New telemetry:

- `stalemate_guard_calls`
- `stalemate_guard_threats`
- `stalemate_guard_inconclusive`
- `stalemate_guard_replacements`

Important limitation: it is a bounded one-opponent-reply terminal verifier, not a proof against every deeper forced stalemate net. If the deadline is reached it reports inconclusive and preserves a fallback; do not call it a general stalemate solver.

### B. Repetition-aware tablebase tie-break

The 65-configuration endgame tablebase returns exact side-to-move WDL scores:

- WIN: `+95000 - ply`
- LOSS: `-95000 + ply`
- DRAW: exactly `0`

The tablebase is already used by v7.6: 587/587 recorded probes were hits in the 18-game run. However, Match 9 (Strong, White, sample1) lasted 101 plies, ended in fivefold repetition with three pieces remaining, and accounted for 535 tablebase hits and 28 root-solved decisions.

v7.7 changes `_solve_root_from_tablebase`: exact score remains the primary sort key; only among exactly equal scores is the lower `_position_history` count preferred. This cannot convert a theoretically drawn tablebase position into a win and cannot override superior WDL. It only tries to avoid choosing an already repeated child when another equally scored child is available.

New telemetry:

- `tablebase_repeat_avoided`

### C. Replay data in future benchmarks

The previous V76 JSON results provided move-level search metrics but **did not store the actual move coordinates or position sequence**. That made it impossible to reconstruct Matches 8, 9 and 12 from the uploaded evidence.

Both new v7.7 runners now record:

- initial board material/coordinates;
- every ply, side, engine/opponent label;
- moved piece type;
- from/to coordinates;
- captured squares;
- full board state immediately before each move;
- per-move search/tablebase/stalemate guard telemetry.

Do not remove this instrumentation. It is essential for replaying future failures.

## Evidence from the V76 tournament just completed by the user

### 18-game three-tier benchmark

Overall: **15 wins, 1 draw, 2 losses** (86.1% score).

By tier:

| Tier | W-D-L | Score |
|---|---:|---:|
| Baseline | 6-0-0 | 100% |
| Strong | 3-1-2 | 58.3% |
| Master | 6-0-0 | 100% |

The two losses were both as Black against Strong:

- Match 8: `sample0`, Black, 16 plies, 15 pieces left, stalemate loss.
- Match 12: `sample2`, Black, 16 plies, 15 pieces left, stalemate loss.

Match 9: `sample1`, White, 101 plies, three pieces left, fivefold repetition draw. Its move metrics record 535 tablebase hits and 28 root-solved decisions.

Aggregate search metrics across 215 engine decisions:

- Average completed depth: 2.34; median: 2.
- Average excluding zero-node decisions: 2.794.
- Total nodes: 128,521.
- Engine thinking time: 1,654.2 seconds; aggregate NPS: 77.69.
- 149 decisions aborted a deeper iteration (about 69.3%).
- 7 decisions reached depth 6 or more; none reached depth 8.
- 587 tablebase probes, 587 hits: 103 WDL wins, 326 losses, 158 draws.
- 28 root-solved tablebase decisions.
- Material guard triggered 16 times but produced zero replacements.
- Promotion guard triggered zero times.

The endgame database is now demonstrably used in actual tournament positions. Its coverage is still limited to the 65 material configurations encoded in the embedded data; do not claim universal coverage of all positions with four or fewer pieces.

### V76 versus V74 paired-colour 10-game benchmark

Record for v7.6: **5 wins, 0 draws, 5 losses** (50%).

| Metric | v7.4 | v7.6 |
|---|---:|---:|
| Average depth | 2.011 | 2.044 |
| Median depth | 2 | 2 |
| Average NPS | 65.80 | 66.75 |
| Average thinking time | 8.230s | 8.134s |
| Zero-node decisions | 13 | 13 |
| Aborted-depth decisions | 65 | 64 |
| Tablebase hits | 0 | 0 |

This is a marginal throughput/depth difference, not a material strength gain. All five paired boards had the same winning colour in both halves of the pair: four pairs were won by White twice, and one pair was won by Black twice. Therefore this 10-game sample has strong starting-position/colour effects and does not establish v7.6 superiority over v7.4.

## Existing research/architecture to preserve

The historical version development and 100/200/500/600-game self-play programme is documented in `evidence/history/CHESS_FRAGMENTS_ENGINE_DEVELOPMENT_LOG.md`. Keep the old engine files and evidence. Important lines of work already explored:

- v6.9 Frozen Overnight as an historical known-good reference.
- v7.0 Depth10 diagnostic branch.
- v7.1 Adaptive Tactical Hybrid and 200-game paired head-to-head against v6.9 (the prior dev log records 55% for v7.1).
- v7.3 Emperor and two 250-game paired comparisons (against v6.9 and v7.1); historical weaknesses and the Black-side issues are in the development log.
- v7.4 Tactical Guard and the extensive 600-game self-play/diagnostic corpus.
- PUCT/MCTS experiments were not justified; PUCT stays disabled.
- Existing calibrated evaluation covers material, piece-square placement, tapered king activity, pawn structure/promotion races, mobility/safe mobility, attack/defence exposure, king safety, anti-stalemate mobility, mating drive and conversion.

Do not rewrite the evaluation weights merely because v7.6 average depth is low. First profile `list_legal_moves_for`, board cloning, `_build_evaluation_maps`, `evaluate_for_white`, move ordering, and node accounting under the actual Windows runtime.

## Offline validation already run for v7.7

In the current build environment these all passed:

- Python compilation of engine, adapter/data, baseline, tests, runners and player.
- All 65 tablebase material configurations load.
- K+Q decisive probe returns +95000.
- All 555 distinct historical 3-/4-piece tablebase states match expected WDL: 240 WIN, 227 LOSS, 88 DRAW.
- Exact DRAW remains zero even when an old caller supplies extreme material contempt.
- Existing history ageing, conservative LMR, low-mobility futility gate, order-independent TT hash, root tablebase selection/fallback, and expired-deadline fallback tests.
- New high-material non-king terminal guard branch test and safe-alternative replacement test.
- New equal-WDL repeated-child preference test and exact-WDL-priority test.
- TT-key synthetic microbenchmark (final rerun): sorted tuple median 1.1230s vs frozenset 1.0648s, 5 × 200,000 calls. This is a 5.46% improvement for the isolated key-construction operation only, not an overall NPS result. Earlier preliminary numbers were superseded by this final rerun.

**Live ChessMaker smoke test is not passed here.** This environment lacks the `chessmaker` module. Run `validate_v77.ps1` in the user's actual project. Do not run tournaments if the live smoke check fails.

## Commands in the user's Windows project root

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\validate_v77.ps1
```

If and only if every check passes, run:

```powershell
.\validate_v77.ps1 -RunTournament
```

Or separately:

```powershell
python .\run_v74_v77_head_to_head.py
python .\run_v77_18_tournament.py
```

Expected result files:

- `V77_V74_H2H_10.json`
- `V77_TOURNAMENT_18_RESULTS.json`
- `V77_TOURNAMENT_18_METRICS_SUMMARY.json`

Each tournament result now contains replayable `initial_position` and `move_history` data. Ask the user to share all three JSON files if further analysis is required.

## Recommended Claude next steps

1. Confirm live ChessMaker validation and tablebase readiness in the user's environment.
2. Inspect v7.7's code diff against v7.6; preserve the narrowly scoped changes unless testing reveals a defect.
3. Run the two tournaments only after live validation passes. Analyse W-D-L by colour and tier, and inspect actual move histories for each loss/draw.
4. Specifically inspect whether the one-reply guard is called, whether it detects any opponent move that leaves the engine with no legal move, how often it is inconclusive, whether it replaces unsafe moves, and what time it costs.
5. Analyse whether equal-WDL tablebase tie-breaking lowers repeated-position counts in Match-9-like endgames.
6. Profile the search under the real Windows runtime before attempting to raise average depth. Preserve completed-iteration safety and the 300-second per-player clock. Report whole-engine NPS separately from synthetic TT-key microbenchmarks.
7. If tuning, do controlled ablations with matched boards, matched seeds, both colours, identical opponent versions and preserved raw move histories. Never change evaluation, LMR, pruning and time budgeting together in one experiment.
8. Keep v6.9 and v7.4 intact until a statistically meaningful paired-colour result and no critical safety regressions support promotion.

## Suggested first message to the user

Acknowledge the handoff, confirm you will inspect the included v7.7 source and results, and state the first live validation command. Do not ask the user to re-explain the version history; it is included here. Do not promise victories or an unverified depth target.
