# Chess Fragments 5×5 Engine — Development, Experiments & Handoff Log

**Document purpose:** Complete technical handoff for a new AI coding agent or researcher taking over the Chess Fragments engine. This document records the development path, important design decisions, benchmark protocols, measured outcomes, lessons, current file state, and a recommended version-retention policy.

**Snapshot date:** 1 November 2026  
**Current research candidate:** v7.5 Endgame Depth  
**Frozen historical reference:** v6.9 Frozen Overnight  
**Most data-rich fully measured research build:** v7.4 Tactical Guard

> **Handoff rule:** Treat this document as the project history and experiment index, not as permission to overwrite the current champion or to assume the newest version is strongest. Preserve all frozen baselines and raw evidence. Promote only after paired, colour-reversed, reproducible tests.

---

## 1. Executive summary

This project is a custom search engine for **Chess Fragments**, a compact 5×5 chess variant implemented with ChessMaker. The engine has evolved from a simple legal-move picker into a measured search system using iterative deepening Negamax, alpha-beta pruning, PVS, aspiration windows, transposition tables, killer/history move ordering, LMR, quiescence, tactical safeguards, clock management, anti-repetition logic, and special handling for the variant's stalemate rule.

The most important discoveries are not merely algorithmic:

1. **The game rules differ materially from standard chess.** A player with no legal moves loses; stalemate is not a draw. A king's escape-space and immobilisation risks are therefore first-class tactical concerns.
2. **ChessMaker move generation is expensive.** The evaluation function must not call legal-move generation. Search code must avoid redundant `list_legal_moves_for()` calls, and timing is as important as nominal depth.
3. **Some standard chess-engine techniques regress on this 5×5 game.** Null-move pruning and aggressive forward pruning caused measurable problems. RFP/razoring made the engine look deeper while missing tactical continuations and exhausting the game clock.
4. **The colour and board-layout effects are severe.** Several builds looked excellent in aggregate while losing overwhelmingly as Black or on one particular board. A single score without colour/board splits is misleading.
5. **Search depth is not strength.** In the 200-game v6.9-v7.1 head-to-head, v7.1 won 55% despite recording a lower average depth and lower aggregate NPS. The 250-game v7.3-v7.1 test then showed that v7.3 was weaker overall despite improvements in its search architecture.
6. **The old endgame tablebase was deliberately removed after an ablation showed zero hits in the measured 18-game tournament.** v7.5 reintroduces a tablebase probe as an experiment, but it must prove real-game hit rate and benefit before being considered worth its complexity.
7. **v6.9, v7.1, v7.4 and v7.5 have different roles.** v6.9 is an essential frozen reference, v7.1 is a crucial H2H challenger whose source must be preserved, v7.4 has the largest diverse self-play dataset, and v7.5 is a new unvalidated candidate. None should be deleted.

### Current recommendation

- Keep **v6.9** as a read-only benchmark anchor.
- Recover and keep **v7.1** as an important challenger/reference (its source file is not in the current handoff folder, but its SHA-256 is recorded below).
- Keep **v7.4** and all of its 600-game data as the main tactical-regression research branch.
- Keep **v7.5** as an experimental branch until its live ChessMaker tests and paired tournaments are complete.
- Preserve **v7.3** as the architectural predecessor of v7.4, but do not promote it based on its 60.8% result against v6.9 alone; it loses badly to v7.1 and has severe Black-side weaknesses.
- Move older versions to a cold archive rather than permanently deleting them. Remove duplicate copies only after hashes and backups are verified.

---

## 2. Rules and environment that every future agent must understand

### 2.1 Variant-specific rules and pieces

- Board dimensions: **5×5**.
- The game uses ChessMaker and the provided `extension/` helpers.
- Custom `Right` piece: hybrid of rook movement and knight jumps. It is unusually powerful on a 5×5 board and changes material/tactical balance compared with standard chess.
- Custom `Pawn_Q`/promotion pawn class may appear in runtime objects. It must be normalised to the ordinary `pawn` material/evaluation category.
- **Stalemate is a loss for the player with no legal move.** Do not import conventional chess assumptions that stalemate is a draw.
- King absence/terminal capture and no-legal-move outcomes need to be scored according to the actual `board_rules.py` implementation.
- Repetition/timeout outcomes may be draws under the supplied game rules, but the engine should avoid avoidable repetition draws when ahead and preserve draws when clearly losing only when that is the safer result.

### 2.2 Performance facts

Historical profiling in the project measured approximately:

| Operation | Approximate cost | Engineering implication |
|---|---:|---|
| `list_legal_moves_for()` | ~5 ms/call in the early profile | Dominant search-node cost; avoid extra calls |
| `board.clone()` | ~0.3 ms | Non-trivial when repeated in pruning schemes |
| Clone + apply move | ~0.9 ms | Keep child-board construction controlled |
| Custom terminal check | ~0.01 ms | Prefer over state-mutating result helpers in search |
| Pure static evaluation | ~0.01 ms | Iterate pieces; do not generate legal moves |
| Board hash | ~0.02 ms in the older profile | TT hashing is not the main bottleneck |

Later tournament runs report lower aggregate NPS values (roughly 42–156 in the large experiments). These measurements were gathered under different boards, clocks, engine versions, search workloads and instrumentation, so do not compare NPS figures across unrelated runs as if they were one controlled benchmark.

### 2.3 Critical API pitfalls already discovered

- `get_result()` from `board_rules.py` can update repetition state (`_rep_hist`). Calling it inside a search tree corrupted the board's repetition accounting in early versions. Use a non-mutating custom terminal check inside search.
- `list_legal_moves_for()` is expensive. Static evaluation must never call it for both sides or every leaf.
- ChessMaker's piece-name property behaviour changed across Python releases; the code uses `type(piece).__name__` and explicit normalisation rather than relying on a potentially broken `piece.name` descriptor.
- The test harness must construct a **fresh board for each game**. Board sample lists may be mutable/shared; reusing them caused one game to mutate the starting layout used by the next game.
- Transposition-table best moves must be stored by stable coordinates, not by a move-list index. Move ordering changes between searches, so an index can point to a different or illegal move when probed later.
- A search must preserve the last fully completed iterative-deepening result when the next iteration is interrupted by the clock.

---

## 3. Development chronology and version log

The detailed current lineage begins in v6.x, but the earlier v0-v5 work explains several non-negotiable architecture decisions.

### 3.1 Early foundation: v0 through v5.6

| Version | Change | Result / lesson | Retention |
|---|---|---|---|
| v0 | Random legal move from the supplied skeleton | Established the `agent(board, player, var)` interface and move tuple format | Archive only |
| v1 | Full minimax, iterative deepening, quiescence, legal-move mobility evaluation | Timed out immediately. Mobility evaluation generated legal moves for both sides at leaves | Do not revive |
| v2 | Negamax and faster piece-only evaluation, but quiescence still generated legal moves at leaves | Still timed out; `get_result()` also mutated repetition history | Archive as historical lesson |
| v3 | Removed quiescence, replaced mutating terminal helper with custom terminal check | First working engine; won early sample tests | Historical baseline |
| v4 | Killer moves, history heuristic, LMR | 6/6 standard suite; free move-ordering improvements helped | Keep concept, not necessarily active file |
| v5.0/v5.1 | Null-move pruning, PVS, aspiration windows, opening cache | Regression; NMP performed poorly on 5×5 because zugzwang is common and cloning costs time | Keep PVS/aspiration ideas; keep NMP disabled |
| v5.2 | Disabled NMP while retaining PVS and aspiration | Improved stress result (3.0/6 versus 2.0/6 for v5.0) | Historical stable branch |
| v5.3 | Repetition avoidance, per-move depth/node/EBF/NPS/time instrumentation, tighter time checks | Established the need for observability and clock-aware search | Concepts retained |
| v5.4 | King tropism, pawn drives, connected-pawn bonus, tempo, 2s safety margin | 6/6 standard; stress suite remained mixed due to overextended pawns | Archive |
| v5.5 | Fixed TT move-index corruption, bounded quiescence, frontier futility, context-aware pawn restraint | Major recovery: 4.5/6 stress and first White wins against depth-5 | Keep as historical source if desired |
| v6.0 | Added RFP, razoring, improving heuristic and stronger multi-ply LMR | Nominal depth rose, but tactical quality and clock results collapsed; forced mates were pruned | **Rejected. Never reintroduce unchanged** |
| v5.6 Clean Sweep | Dynamic 300s player-clock allocation, anti-stalemate king-mobility gradient, 2-ply opening book, aspiration calibration | Strong operational single-file baseline; tablebase payload ablated after measured zero activations | Keep in cold archive |

#### Important v5.6 tablebase history

A 65-material-configuration retrograde tablebase was generated for positions with two to four pieces. The build pipeline used a custom fast board representation, retrograde propagation, compression and an embedded payload. It was tested in a separate `v5.6-TB` branch and then removed from the lean v5.6 Clean Sweep build.

The archived `CHANGELOG.md` records **zero tablebase activations in the 18-game benchmark** and reports that no game in that run ended at four or fewer pieces (average pieces remaining at termination was reported as 8.9). It therefore concluded that the tablebase added substantial complexity/file size without a demonstrated tournament benefit.

There is an inconsistency inside that older document: its cross-version summary refers to a 15/18 stress result, while the fresh post-clock-fix scorecard records 14 wins, 4 draws and 0 losses. Do not silently combine those numbers. Preserve the old changelog as a historical record and use the version-tagged raw JSON files for later v6.7-v7.0 tournament scores.

### 3.2 v6.4 — Anti-loss rebuild

The available `agent_v64_anti_loss.py` is the first current-branch version with the mature search framework clearly visible:

- Iterative Deepening Negamax + alpha-beta.
- PVS and ±250 cp aspiration windows with widening.
- 200,000-entry horizontally symmetric transposition table.
- Six-tier move ordering: PV, MVV-LVA, promotions, killers, history, centre.
- LMR for non-tactical late moves.
- Quiescence for captures/promotions and bounded check evasions.
- Depth-1 frontier futility pruning with check safety.
- Anti-stalemate king mobility gradient.
- Promotion-race evaluation, safety-weighted mobility, exchange liability and endgame mating drive.
- Own-clock budgeting for the 300-second per-player clock.
- Opening cache/book for early plies, repetition avoidance and stderr instrumentation.
- Optional tablebase import and probe hooks are present in this file.

Material values in the mature 5×5 line include Pawn 100, Knight 320, Bishop 330, Right 700, Queen 900 and King 20,000. These are calibrated for the compact variant, not copied uncritically from 8×8 chess.

### 3.3 v6.5 — Regression-safe tactical fix

`agent_v65_regression_safe.py` retains the main search architecture and the 200k coordinate-keyed TT, but the optional tablebase hook is no longer present. It continues to use the custom `Pawn_Q` normalisation and own-clock budgeting. It is an intermediate stabilisation file, not a current promotion candidate.

### 3.4 v6.6 — Entropy-guided threat search

`agent_v66_entropy_threat.py` adds an information-theoretic / anti-loss idea on top of the normal alpha-beta engine:

- Computes normalised root entropy from the distribution of root move scores.
- In low-material positions (roughly 10 pieces or fewer), performs a bounded root safety audit for immediate terminal-loss replies.
- Uses entropy/uncertainty to decide how many alternatives to examine, rather than unconditionally deepening every move.
- Aims to preserve counterplay when losing while avoiding needless volatility when ahead.
- Retains standard tactical ordering, killers/history, LMR, quiescence, anti-stalemate and clock management.

The later v6.7/v6.8 source comments explicitly state that v6.6's self-learning cache did not actually consult the supplied `opening_book.py` data. This was an implementation gap, not a failure of the general idea of opening books.

### 3.5 v6.7 — Threat-shadow experiment + verified opening entries

`agent_v67_threat_shadow.py` explores a bounded threat-shadow/root-sweep idea:

- Profiles candidate opponent replies for forcing volatility: checks, captures, promotions and severe tactical threats.
- Adds a bounded extra root audit when the candidate move is tactically volatile.
- Adds 16 verified static opening entries after losses exposed Black-side bait-pawn traps that the self-learning cache failed to cover.

This is experimental. The broad threat-shadow sweep was later narrowed/removed in v6.8 to avoid spending too much time on speculative root branching.

**Tagged 18-game score:** 15 wins / 3 losses (15/18). This is a three-tier diagnostic, not an Elo estimate.

### 3.6 v6.8 — Selective book

`agent_v68_selective_book.py` narrows the opening repair to two specific defensive replies corresponding to measured v6.6 loss patterns. The intention was to avoid overriding unrelated openings or paying for a broad threat-shadow search on every turn.

**Tagged 18-game score:** 17 wins / 1 loss. Tier split: Baseline 6/6, Strong 5/6, Master 6/6.

### 3.7 v6.9 — Frozen Overnight / Stalemate Guard

`agent_v69_frozen_overnight.py` is a key stable reference. It descends from the selective-book line and fixes a specific crowded-position failure: a king move can allow the opponent's next king reply to immobilise the moving side, which is an immediate loss under the variant rules.

Key characteristics:

- Retains the mature PVS/Negamax search and core ordering.
- Keeps the two selective Black-side opening responses.
- Adds a narrow terminal-safety scan around risky king moves in crowded positions (the code comments refer to the earlier v6.8 Strong/sample2 loss pattern).
- Caps the number of candidate king moves inspected to limit overhead.
- Reserves clock budget rather than assuming high-material positions are cheap.
- Retains anti-stalemate, repetition, promotion and clock safeguards.

**Tagged 18-game score:** 18 wins / 0 losses, with 6/6 against each of Baseline, Strong and Master tiers. The run is balanced across White/Black and the three standard sample boards.

SHA-256 of the frozen source recorded in the 100-game manifests:

`df5cfb7305e8374ed45b6a862e6934cf0f3168e7c7eca9b1c18e9cfd517e08bd`

This version must remain untouched as a reproducible baseline even if a later candidate becomes stronger.

### 3.8 v7.0 — Depth acceleration candidate

Available files include `agent_v70.py`, `agent_v70_depth10.py`, and `agent_v70_depth10_overnight.py`.

The depth-oriented branch adds:

- Cached piece-class name lookup to reduce repeated class-name handling.
- Explicit PV/TT move priority rather than allowing large accumulated history bonuses to obscure the PV move.
- Reuse of the previous iteration's root best move when a TT PV is unavailable.
- Root alpha-beta cutoffs and iteration-level completed/aborted diagnostics.
- More explicit tracing of completed versus interrupted iterative-deepening iterations.

The word **Depth10** in a filename is a target/branch label, not evidence that average completed search depth was 10. The actual depth must be read from per-move logs and benchmark summaries.

**Tagged 18-game scores:**
- Standard v7.0: 16 wins / 2 losses.
- v7.0 Depth10 diagnostic: 18 wins / 0 losses in the separately recorded three-tier 18-game runs.

A separate fast benchmark folder is important context:
- `v70_benchmark_fixed`: 10 valid games, 2 wins / 2 draws / 6 losses, 0 errors.
- `v70_benchmark_001`: 10 attempted games, all 10 errors due to the harness/import setup; elapsed time was 0.19s, so those were not completed games.
- An overnight manifest/plan refers to 1,000 target games, but the available valid report is only 10 games. **Do not claim a 1,000-game benchmark was completed.**

The short per-move budget also exposed partial-iteration issues: a search can start a deeper iteration but fail to finish it, so the last completed depth and the attempted depth must be reported separately.

### 3.9 v7.1 — Adaptive Tactical Hybrid

The full source `agent_v71_adaptive_tactical_hybrid.py` is not present in the current mounted handoff files, but its exact SHA-256 is recorded by both PC1 and PC2 manifests:

`488b051b3dce2e49f3b883a16dc12eddaba31510a0596bde7b83247c933865de`

Its role is important: it is a measured challenger to v6.9 and is used as one of the two parent research lines for v7.3. Do not reconstruct its source from guesses. Recover the original file from the user's project archive/working directory and verify its hash before reproducing the tests.

Measured evidence:
- 100-game same-engine controls (50 PC1 + 50 PC2).
- 200-game direct paired head-to-head versus v6.9: v7.1 scored 55.0% (110 wins, 0 draws, 90 losses).

PUCT was explicitly disabled in the v7.1/v6.9 controlled comparison. Thus the 55% result is not evidence for PUCT.

### 3.10 v7.2 — Mobility-aware branch

The full source `agent_v72_mobility_aware.py` is also not present in the current mounted handoff files. Manifests record this SHA-256:

`7360db1d0482cd3dd3965a279c2c733507307efad42690ec305408468d331883`

Recover it from the original project folder before attempting code-level comparisons. It was evaluated in two 20-game pilot H2Hs, with PUCT disabled:

- v7.2 vs v6.9: 10 wins / 10 losses (50%). As White: 8-2; as Black: 2-8.
- v7.2 vs v7.1: 8 wins / 12 losses (40%). As White: 8-2; as Black: 0-10.

The pilots show a severe Black-side problem. They are useful screening evidence, but 20 games are not enough to establish a precise strength rating.

### 3.11 v7.3 — Emperor

`agent_v73_emperor.py` combines the v7.1 search-control line with v7.2 ordering ideas. Major architecture items in source:

- Side- and piece-aware killer/history keys to avoid aliasing move-ordering statistics across players or piece classes.
- Dynamic 0/1/2-ply LMR for non-tactical late moves, guarded by tactical/killer/history conditions.
- Bounded LRU transposition table instead of wholesale flushes at high occupancy.
- Directional aspiration-window widening.
- Bounded quiet-check quiescence in addition to captures/promotions.
- Deterministic fail-safe move selection and optional root tie-breaking (disabled by default).
- Check extensions disabled by default; selected low-mobility extensions retained.
- PUCT/MCTS code remains in the source for experimentation but **`_ENABLE_ROOT_PUCT = False`** in the tested configuration.

#### 250 games: v7.3 vs v6.9

- v7.3: 152 wins, 0 draws, 98 losses = **60.8% score**.
- As White: 118 wins, 7 losses (125 games).
- As Black: 34 wins, 91 losses (125 games).
- Paired colour reversals: v7.3 won both games in 28 pairs; v6.9 won both in 1 pair; 96 pairs split.
- v7.3 weighted average depth 2.492 vs v6.9 2.460; median depth 2 for both; p90 5 for both.
- v7.3 had 36 moves at depth ≥8, versus 78 for v6.9; aggregate NPS 62.7 vs 65.0.
- PUCT calls/overrides: zero.

This initially looks like a v7.3 victory in the aggregate, but the White/Black split is unacceptable. The 60.8% headline masks a strong White-side result and a catastrophic Black-side result.

#### 250 games: v7.3 vs v7.1

- v7.3: 112 wins, 1 draw, 137 losses = **45.0% score**.
- As White: 99 wins, 1 draw, 25 losses.
- As Black: 13 wins, 0 draws, 112 losses.
- Paired reversals: v7.3 won both in 5 pairs; v7.1 won both in 17; 102 split; 1 draw/error pair.
- v7.3 weighted average depth 2.695 vs v7.1 2.728; p90 5 vs 6; aggregate NPS 69.3 vs 68.7.
- v7.3 had 56 moves at depth ≥8 versus 100 for v7.1.
- PUCT calls/overrides: zero.

**Conclusion:** v7.3 was not a promotion over v7.1. The two 250-game studies must be kept separate: they have different opponents/baselines. They should not be merged into one 500-game win percentage.

### 3.12 v7.4 — Emperor Tactical Guard

`agent_v74_tactical_guard.py` freezes the v7.3 search architecture and adds bounded tactical guards:

- Material-exchange guard that checks whether the chosen move permits a major piece to be lost in the immediate tactical resolution.
- Immediate-promotion guard for an opponent promotion threat that is not adequately addressed by the selected move.
- A replacement move is considered only when the alternate is near-equal (within the configured 150cp loss window) and passes the safety checks; the guard does not blindly choose a different root move.
- Existing anti-stalemate, repetition, tactical ordering, LMR and clock logic are retained.
- PUCT remains disabled; check extensions and root random tie-breaks are off in the measured configuration.

SHA-256 in the 600-game manifest:

`f071799b7ac06d30a3f912adc541313942e536cf0c1285d5cff294e73abd57dd`

#### 10-game pilot

- 10 games, 10 unique initial positions and trajectories.
- Five games started with White to move, five with Black to move.
- Outcomes: five White wins, five Black wins.
- 158 search moves; average depth 3.449; median 4; p90 6; max 7.
- Average move time 7.8058s; aggregate NPS 155.8.
- 22 material-guard triggers, 0 replacements.
- 4 promotion-guard triggers, 0 replacements.
- No game errors/timeouts in the pilot summary.

The pilot suggests the guards were conservative; 10 games are not a strength evaluation.

#### 600-game diverse self-play

The 600-game experiment is one of the most important project assets. It was configured as follows:

- Requested/completed: 600 games.
- Four workers.
- Per-move thinking allowance: 12 seconds.
- Per-player game clock: 300 seconds.
- Seed: 740600.
- Random legal opening playouts of 4–14 plies, with a mild quiet-move preference while retaining capture opportunities.
- Unique canonical opening-position hashes; no repeated starting positions.
- 300 games started with White to move, 300 with Black to move.
- Thirteen board layouts balanced: sample0 and sample1 had 47 games each; sample2–sample12 had 46 each.
- Exactly 600 unique completed trajectories; no repeated full trajectory.

Results and instrumentation:

| Metric | Result |
|---|---:|
| Games | 600 |
| White wins | 271 |
| Black wins | 326 |
| Draws | 3 |
| Unique decision positions | 10,364 |
| Unique tactical-review positions | 3,332 |
| Average total plies | 26.73 |
| Average plies after supplied opening | 17.82 |
| Average search depth per move | 2.313 |
| Median / p90 depth | 2 / 4 |
| Maximum recorded depth | 49 |
| Moves at depth ≥6 / ≥8 / ≥10 | 310 / 98 / 42 |
| Total search nodes | 3,845,059 |
| Average move time | 8.5587s |
| Aggregate NPS | 42.0 |
| Material guard triggers / replacements | 313 / 12 |
| Promotion guard triggers / replacements | 127 / 2 |
| Captures | 4,698 |
| Immediate major-piece-hang signals | 1,006 |
| Promotions played | 304 |
| Promotion opportunities allowed next ply | 287 |
| Engine/game errors | 0 |
| Instrumented search timeout counter | 6 |
| Wall time | 23,023.41s (~6h23m) |

Interpretation notes:

- This is **same-engine self-play**, not a rating test. It does not show that v7.4 beats v6.9 or v7.1.
- The Black-win count (326 vs 271 White wins) shows the outcome distribution under this setup, but it is not a direct engine-versus-engine strength comparison.
- The maximum depth of 49 is an outlier, not typical performance. Median depth 2 and p90 4 are more representative of ordinary moves.
- Six instrumentation timeouts must not be described as six game forfeits. The summary records zero game errors; the `timeouts` counter is a search-level diagnostic and needs to be interpreted according to the logger's semantics.
- Guard triggers are not the same as actual replacements. The material guard replaced 12 root moves out of 313 trigger events; the promotion guard replaced 2 out of 127.
- The 1,006 immediate-major-piece-hang signals are a review queue, not 1,006 proven engine blunders. The analysis report explicitly cautions that candidate scores/bounds are not exact evaluations and that each candidate needs independent tactical analysis.

The 600-game corpus is extremely valuable for tactical regression mining, colour/board analysis and future evaluation testing. Preserve all raw JSONL/CSV and analysis outputs.

### 3.13 v7.5 — Endgame Depth (current candidate, not yet champion)

Current candidate file: `agent_v75_endgame_depth.py`. It is based on v7.4 and adds four main changes:

1. **Retrograde tablebase integration:** Imports `probe_endgame_tb` and `is_tablebase_loaded`, then probes in Negamax and quiescence. Tablebase results use decisive WDL-style scores around ±95,000 adjusted by ply; draw handling includes contempt and the tablebase module's anti-stalemate gradient.
2. **Tighter deadline polling:** Checks every eight nodes and at root-loop / expensive search boundaries to reduce deadline overshoot.
3. **Cross-turn history persistence:** History ordering survives between the engine's turns within one game, decays by 22% (factor 0.78) between turns, and is reset at a new-game boundary. It is bounded to avoid unbounded growth.
4. **Conservative LMR threshold adjustment:** The second-ply reduction trigger can activate slightly earlier at high depth, while tactical moves retain safeguards.

The helper's draw contempt uses **material balance**, not the full positional evaluation, to avoid distorting the exact tablebase WDL order.

#### v7.5 verification already completed in the build environment

- Python compilation of the agent and harness files: passed.
- The tablebase loader reports 65 configurations.
- A decisive K+Q probe through the agent helper returns the expected winning score of 95,000.
- History persistence/ageing regression: passed.
- LMR threshold and tactical-exemption regression: passed.
- Expired-root-deadline fallback regression: passed.
- Package ZIP integrity check: passed.

#### What remains unverified

- Live ChessMaker `Board`/`Piece` integration and full agent call in the user's actual project environment.
- Whether v7.5 has better average completed depth, NPS, clock safety or win rate than v7.4/v6.9.
- Whether its tablebase is reached often enough to justify the extra code/data.
- Actual paired tournament results.

The build environment used for this handoff did not have the `chessmaker` Python package installed, so the live smoke test could not be completed here. The user's Windows project environment has the relevant package. Do not state that v7.5 has passed a live tournament or that average depth has improved until the local validation/benchmarks are run.

The tablebase still contains only **65 supported material configurations** for 2–4 piece positions; it does not cover every conceivable ≤4-piece position. The historical v5.6 experiment found zero activations in one 18-game run and no ≤4-piece terminal positions. Treat tablebase integration as a measured hypothesis, not an automatic strength improvement.

---

## 4. Benchmark and self-play programme

This section separates different experiment types. A future agent must not call all of them “self-play” or merge incompatible scores.

### 4.1 Eighteen-game three-tier diagnostic tournament

**Purpose:** Fast, interpretable opponent-suite check across three opponent levels and both colours.

**Structure:**
- 3 opponent tiers: Baseline, Strong, Master.
- 3 starting boards: sample0, sample1, sample2.
- Both colours for each board/tier pair.
- 6 games per tier, 18 games in total.
- The historical harness used the project's scripted opponents (typically described as baseline depth 3, strong depth 5, master depth 7). These are internal opponents, not calibrated Elo opponents.

**Version-tagged raw JSON outcomes:**

| Engine/result file | Wins | Draws | Losses | Tier notes |
|---|---:|---:|---:|---|
| v6.7 `TOURNAMENT_18_DIAGNOSTIC_RESULTS_V67.json` | 15 | 0 | 3 | Baseline 6/6, Strong 5/6, Master 4/6 |
| v6.8 `...V68_Selective_Book.json` | 17 | 0 | 1 | Baseline 6/6, Strong 5/6, Master 6/6 |
| v6.9 `...V69.json` | 18 | 0 | 0 | 6/6 in all three tiers |
| v7.0 `...V70.json` | 16 | 0 | 2 | Baseline 6/6, Strong 5/6, Master 5/6 |
| v7.0 Depth10 `...V70_DEPTH10.json` | 18 | 0 | 0 | Separate run; 6/6 in all three tiers |

There is also `TOURNAMENT_18_DIAGNOSTIC_RESULTS_V70_DEPTH10(1).json`, which also records 18/18. The two files should be retained as separate run outputs unless their manifests establish they are exact duplicates.

**Unattributed/exploratory 18-game result files:** The current folder also contains runs with 18 losses, 15/3, 13/5, 13/5, 16/2, 15/3, and a 14-win/4-loss result (`TOURNAMENT_18_RESULTS.json`). Do not attach these to a particular source version without a matching manifest or source fingerprint. They remain part of the development evidence but should not contaminate version-labelled comparisons.

**What it taught us:** the versioned suite captured major improvements from v6.7 to v6.9 and shows that a later search candidate can regress. But 18 games are a screening gate, not enough to establish general superiority. Different seeds, opening positions, clock budgets or opponent changes can also make separate 18-game scores non-comparable.

### 4.2 Two 100-game same-engine self-play control sets (v6.9 and v7.1)

These are two separate 100-game self-play experiments, one for v6.9 and one for v7.1. Each 100 is composed of 50 games on PC1 and 50 on PC2. They are **controls for colour/board/worker effects**, not direct strength tests between versions.

Configuration recorded in the manifests:
- 50 games per PC per engine.
- 14 seconds per move; 300 seconds per player.
- Five boards: sample0 through sample4, equal coverage.
- Paired RNG streams swap the White/Black streams.
- 8 workers at start.
- PC1 seed base 730069; PC2 seed base 730169.
- v6.9 and v7.1 source hashes recorded in every manifest.
- PUCT forced off for v7.1.

#### v6.9 self-play results (100 total)

| Run | White wins | Black wins | Draws | Avg plies | Avg game wall | Max completed depth |
|---|---:|---:|---:|---:|---:|---:|
| PC1, 50 games | 33 | 17 | 0 | 31.94 | 279.70s | 10 |
| PC2, 50 games | 36 | 12 | 2 | 28.68 | 230.17s | 34 |
| **Combined, 100** | **69** | **29** | **2** | — | — | — |

#### v7.1 self-play results (100 total)

| Run | White wins | Black wins | Draws | Avg plies | Avg game wall | Max completed depth |
|---|---:|---:|---:|---:|---:|---:|
| PC1, 50 games | 25 | 24 | 1 | 35.62 | 297.64s | 33 |
| PC2, 50 games | 35 | 15 | 0 | 35.14 | 305.10s | 9 |
| **Combined, 100** | **60** | **39** | **1** | — | — | — |

**What we learned:**
- Both engines show a substantial colour effect in same-source play; the PC1/PC2 and layout differences are also noticeable.
- The v6.9 aggregate of 69 White wins vs 29 Black wins and v7.1 aggregate of 60 vs 39 confirm that same-engine self-play is useful for detecting colour/layout pathologies.
- A maximum depth of 34 on one run and 9 on another demonstrates why a single maximum-depth number is almost meaningless without move-level distributions, hardware, position and budget context.
- These controls cannot tell us which engine is better, because the same source is playing both sides.

### 4.3 The 200-game paired head-to-head: v6.9 vs v7.1

**Purpose:** Direct comparison after the self-play controls, with both versions playing both colours and across multiple boards.

- 200 games total: 100 on PC1 and 100 on PC2.
- Five boards, 40 games per board in combined summary.
- Paired colour reversal is recorded.
- PUCT disabled for v7.1.
- Both source hashes are checked in the manifests.
- Zero engine errors.

**Result:** v7.1 scored 55.0%: 110 wins, 0 draws, 90 losses.

| Split | v7.1 wins | Draws | Losses |
|---|---:|---:|---:|
| As White (100) | 63 | 0 | 37 |
| As Black (100) | 47 | 0 | 53 |
| sample0 (40) | 20 | 0 | 20 |
| sample1 (40) | 12 | 0 | 28 |
| sample2 (40) | 20 | 0 | 20 |
| sample3 (40) | 19 | 0 | 21 |
| sample4 (40) | 39 | 0 | 1 |

Paired colour-reversal counts:
- v7.1 won both games in 19 pairs.
- v6.9 won both games in 9 pairs.
- 72 pairs split (each version won one game).
- 0 draw/error pairs.

Search diagnostics:

| Metric | v6.9 | v7.1 |
|---|---:|---:|
| Search moves | 3,126 | 3,136 |
| Average depth per move | 3.181 | 2.991 |
| Maximum depth | 9 | 8 |
| Total nodes | 4,416,391 | 4,054,053 |
| Average move time | 9.0566s | 8.5952s |
| Aggregate NPS | 156.0 | 150.4 |
| PUCT calls / overrides | 0 / 0 | 0 / 0 |

**Key learning:** v7.1 won the head-to-head with a lower recorded average depth and lower aggregate NPS. Depth and throughput are useful diagnostics, but they are not proxies for move quality or match strength. The sample4 result (39-1) also shows that overall score can be dominated by a board-specific interaction.

### 4.4 v7.2 screening pilots (20 + 20 games)

These are two separate 20-game tests, not a 40-game match against one common opponent.

| Matchup | v7.2 W-D-L | Score | v7.2 White | v7.2 Black | Avg depth opponent / v7.2 | NPS opponent / v7.2 |
|---|---:|---:|---:|---:|---:|---:|
| v7.2 vs v6.9 | 10-0-10 | 50.0% | 8-0-2 | 2-0-8 | 3.199 / 2.866 | 102.1 / 89.2 |
| v7.2 vs v7.1 | 8-0-12 | 40.0% | 8-0-2 | 0-0-10 | 2.934 / 2.812 | 119.8 / 128.3 |

PUCT calls and overrides were zero in both pilots. The v7.2 vs v7.1 pilot is particularly concerning: v7.2 went 0-10 as Black. More NPS in the latter comparison did not translate into wins.

**Lesson:** keep v7.2 as a research/archive reference, but do not promote it without fixing and revalidating its Black-side behaviour.

### 4.5 The “500-game” programme: two distinct 250-game H2Hs

The 500-game number is the sum of two experiments, each with a different opponent baseline. They are not one homogeneous 500-game match and must not be reported as a single aggregate win percentage.

#### A. 250 games: v7.3 vs v6.9

- v7.3: 152 wins, 0 draws, 98 losses = **60.8%**.
- v7.3 White: 118 wins / 7 losses.
- v7.3 Black: 34 wins / 91 losses.
- Paired reversals: v7.3 won both in 28 pairs; v6.9 won both in 1; 96 split.
- No engine errors; PUCT disabled and had zero calls/overrides.

Search diagnostics:

| Metric | v6.9 | v7.3 |
|---|---:|---:|
| Weighted average depth | 2.460 | 2.492 |
| Median depth | 2 | 2 |
| p90 depth | 5 | 5 |
| Moves depth ≥8 | 78 | 36 |
| Max depth | 10 | 9 |
| Aggregate NPS | 65.0 | 62.7 |

Despite the headline 60.8%, the colour split makes v7.3 an unacceptable promotion as-is. It wins overwhelmingly as White and loses overwhelmingly as Black.

#### B. 250 games: v7.3 vs v7.1

- v7.3: 112 wins, 1 draw, 137 losses = **45.0%**.
- v7.3 White: 99 wins, 1 draw, 25 losses.
- v7.3 Black: 13 wins, 0 draws, 112 losses.
- Paired reversals: v7.3 won both in 5 pairs; v7.1 won both in 17; 102 split; 1 draw/error pair.
- No engine errors; PUCT disabled and had zero calls/overrides.

Search diagnostics:

| Metric | v7.1 | v7.3 |
|---|---:|---:|
| Weighted average depth | 2.728 | 2.695 |
| Median depth | 2 | 2 |
| p90 depth | 6 | 5 |
| Moves depth ≥8 | 100 | 56 |
| Max depth | 10 | 10 |
| Aggregate NPS | 68.7 | 69.3 |

**What the 500 games taught us:**
- v7.3 can beat v6.9 in aggregate while losing to v7.1. A new architecture is not automatically stronger.
- v7.3's Black-side losses are not a small statistical fluctuation: 91/125 losses to v6.9 and 112/125 losses to v7.1.
- Its slightly higher depth/NPS in some comparisons does not rescue its practical results.
- The correct research action was to diagnose and guard tactical losses, which led to v7.4, not to promote v7.3 based on one headline percentage.

### 4.6 v7.4 pilot and 600-game unique-opening self-play

The detailed protocol and findings are in section 3.12. Reiterating the purpose:

- The 10-game pilot checked harness stability and whether the new guards activated.
- The 600-game run broadened the position distribution to 13 board samples and 600 unique legal opening positions/trajectories.
- The main research value is the **3,332-position tactical review bank**, plus 10,364 unique decision positions and event logs.
- It is not a v7.4-vs-v7.3 or v7.4-vs-v6.9 match. Both colours used v7.4.

### 4.7 v7.5 tests to date

The v7.5 tablebase and search-control regression scripts pass in the build environment, but no live ChessMaker tournament has yet run here. The intended local validation command is:

```powershell
powershell -ExecutionPolicy Bypass -File .\validate_v75.ps1 -RunTournament
```

The script is designed to compile the files, run the tablebase regression, run history/LMR/deadline-control regressions, smoke-test the live ChessMaker agent, and then run v7.4-v7.5 H2H plus the 18-game diagnostic. **Do not treat the command's existence as evidence that the tournament already ran.**

---

## 5. What the experiments have taught us — consolidated findings

### 5.1 Search speed and depth

- Improving move ordering and reducing unnecessary work can improve depth without changing the evaluation.
- A high *attempted* depth is not the same as a high *completed* depth. Always log and compare completed iterative-deepening iterations.
- Average, median, p90, maximum and threshold counts (≥6, ≥8, ≥10) are all needed. A single maximum such as 49 may be one unusual endgame branch.
- The 200-game v6.9-v7.1 result proves that lower average depth can still win more games.
- Avoid promising a depth-10 engine until the move-level distribution supports that claim under the actual game clock.
- The primary performance target should be **more useful completed search per second under the same clock**, not a raw depth headline.

### 5.2 Variant-specific tactics

- Stalemate-loss prevention is not optional. King mobility/escape squares must be evaluated in this variant.
- An opponent king with very few escapes can be an offensive target; our own king with few escapes is an immediate strategic danger.
- Promotion races and immediate promotion threats need explicit handling.
- Right/Queen tactics become forcing quickly on a 5×5 board; tactical density is high. A quiet-looking move may allow a mate or immobilisation net in one or two plies.
- Material-only evaluation cannot fully describe tactical safety. However, a tactical safeguard must have a narrow trigger and a proven replacement move; broad overrides can harm the engine.

### 5.3 Pruning and search extensions

- **Null Move Pruning:** rejected after measured regressions. Small-board zugzwang and clone cost make it dangerous.
- **RFP/Razoring:** rejected after v6.0. It created hollow nominal depth and pruned tactical/mating continuations.
- **LMR:** useful only with tight exemptions for captures, promotions, checks, killer moves, PV moves and strong history moves. Increasing reductions too aggressively is risky.
- **Quiescence:** useful when bounded and tactical; do not allow it to become unbounded legal-move expansion.
- **PVS and aspiration windows:** retained as useful search-efficiency tools, but aspiration windows must widen correctly after fail-low/fail-high.
- **PUCT/MCTS:** retained only as an experimental code path; disabled in the important controlled benchmarks. Those results cannot be used to claim PUCT helped. The expensive ChessMaker move-generation API makes shallow extra simulations costly.

### 5.4 Tablebase

- A 65-configuration retrograde tablebase exists and is now connected in v7.5.
- Historically, the tablebase was ablated from v5.6 after zero activations in the 18-game suite and a terminal piece-count distribution that never reached four or fewer pieces.
- Tablebase code and correctness tests are worth preserving as a research component, but its **practical value must be measured**: record probes, hits, hit rate, WDL outcomes, nodes saved, time saved and whether hits occur in actual competitive games.
- If real matches still show zero or negligible hits, the default submission/runtime build should likely keep the tablebase optional or exclude the large data blob. Do not delete the research implementation.

### 5.5 Colour and board-layout control

- Always report each version's results as White and Black separately.
- Always break down by board layout. Sample4 produced a dramatic 39-1 v7.1 result in one 200-game set; that may indicate a matchup/layout interaction, not universal strength.
- Use paired colour reversal: the same opening/seed should be played with colours swapped. Report both-win / split / both-loss pair counts.
- Use equal board counts and equal colour counts. Avoid unbalanced test sets.
- Run on at least two machines only when source hashes, clock settings and harness settings are verified. Report machine-specific splits rather than hiding differences in a combined mean.

### 5.6 Self-play versus head-to-head

- Same-engine self-play is excellent for finding side bias, board bias, repetition, clock starvation and recurring tactical failures.
- Same-engine self-play is **not a strength rating**.
- A paired direct head-to-head is necessary to compare versions.
- Tactical event banks are leads for review, not proof of a bug. Verify a position with independent search, tablebase, or manual line analysis before changing evaluation weights.

---

## 6. Version retention and archive policy

The goal should be a small active research set with an immutable cold archive. Do not keep every experimental version in the working root, but do not permanently delete evidence or useful predecessors.

### 6.1 Keep in the active/research set

| Version/file | Role | Recommendation |
|---|---|---|
| `agent_v69_frozen_overnight.py` | Frozen stable reference and 18/18 three-tier diagnostic build | **Keep read-only.** Never overwrite. Use as a baseline in every serious comparison. |
| `agent_v71_adaptive_tactical_hybrid.py` | Strong H2H challenger; beat v6.9 55% in 200 games | **Recover and keep.** Its source is missing from this handoff mount; verify SHA before use. |
| `agent_v73_emperor.py` | Parent architecture for v7.4; useful search experiments | Keep in research archive/read-only. Do not promote in current state because of severe Black-side results. |
| `agent_v74_tactical_guard.py` | Latest large self-play corpus and tactical guard implementation | **Keep active as a research baseline.** Preserve exact source hash and 600-game evidence. |
| `agent_v75_endgame_depth.py` | Current tablebase/deadline/history/LMR candidate | Keep as experimental branch; do not replace v6.9/v7.4 until live H2H tests pass. |
| `endgame_tablebase.py`, `endgame_tb_snippet.py` | Tablebase adapter and data | Keep together; adapter without snippet may report unavailable. Measure actual hit rates. |
| `extension/` and the ChessMaker harness | Required board helpers and local execution | Keep unchanged unless the game rules genuinely need a bug fix. |

### 6.2 Keep in a cold archive (source plus its test output)

- v5.6 Clean Sweep and v5.6-TB material: important stable history and tablebase ablation evidence.
- v6.4 and v6.5: transitional anti-loss / regression-safe sources; v6.4 has optional tablebase hooks.
- v6.6: entropy-guided root safety/anti-loss approach.
- v6.7: threat-shadow prototype and 16-opening experiment.
- v6.8: narrow selective opening-book patch.
- v7.0 and v7.0 Depth10: retain one exact source per distinct SHA plus diagnostics; avoid duplicate filename clutter.
- v7.2: retain source if recovered, along with its 20+20 pilots and hash; useful negative-result reference.
- Earlier v0-v5.5 versions: source may be retained in one historical folder, but they should not remain in the active working root.

### 6.3 Do not delete

Do **not** delete the following even if the corresponding agent is archived:

- `combined_games.json`, `combined_games.csv`, `combined_move_metrics.csv`, `combined_summary.json`, `combined_report.md`.
- Original 100-game manifests, `games.json`, `games.jsonl`, `moves.jsonl`, `move_metrics.csv`, summary files and board/seed metadata.
- Both 250-game H2H archives and their summaries/manifests.
- v7.4 600-game archive, opening corpus, moves, tactical events, tactical position bank, regression candidates and report.
- Version-tagged 18-game tournament JSON files.
- Source SHA-256 values and test scripts.

These files are the experiment record. Removing them would destroy the basis for future comparisons and could cause a later agent to repeat work or misinterpret a result.

### 6.4 Suggested clean project layout

```text
chess-fragments/
├── active/
│   ├── agent_v69_frozen_overnight.py
│   ├── agent_v74_tactical_guard.py
│   ├── agent_v75_endgame_depth.py
│   └── agent_v71_adaptive_tactical_hybrid.py   # recover original + verify SHA
├── engine_archive/
│   ├── v5x/
│   ├── v6x/
│   ├── v7.0/
│   ├── v7.2/
│   └── v7.3/
├── tablebase/
│   ├── endgame_tablebase.py
│   └── endgame_tb_snippet.py
├── extension/
├── benchmarks/
│   ├── 18_game_diagnostics/
│   ├── selfplay_100_controls/
│   ├── h2h_200_v69_v71/
│   ├── pilots_v72/
│   ├── h2h_250_v69_v73/
│   ├── h2h_250_v71_v73/
│   └── v74_selfplay_600/
├── tests/
└── CHESS_FRAGMENTS_ENGINE_DEVELOPMENT_LOG.md
```

This is a suggested organisation only. Copy the original result files into it; do not move or delete the user's only copies before validating the archive.

---

## 7. Evidence and file index

The current handoff environment contained the following files/directories. On the user's Windows project, some already live in the original project folder rather than under these `/mnt/data` paths.

### 7.1 Engine source snapshots

- `agent_v69_frozen_overnight.py` — v6.9 frozen source.
- `agent_v69_stalemate_guard(4).py` — extra copy; check hash before deduplicating.
- `audit_extract/chess-main/agent_v64_anti_loss.py`.
- `audit_extract/chess-main/agent_v65_regression_safe.py`.
- `audit_extract/chess-main/agent_v66_entropy_threat.py`.
- `audit_extract/chess-main/agent_v67_threat_shadow.py`.
- `audit_extract/chess-main/agent_v68_selective_book.py`.
- `audit_extract/chess-main/agent_v70.py`.
- `audit_extract/chess-main/agent_v70_depth10.py`.
- `audit_extract/chess-main/agent_v70_depth10_overnight.py`.
- `agent_v73_emperor.py`.
- `agent_v74_tactical_guard.py`.
- `agent_v75_endgame_depth.py`.
- `audit_extract/chess-main/agent_5.6.py`, plus `agent_5.8.py`, `agent_5.9.py`, `agent_6.0.py`, `agent_6.1.py`, `agent_6.3.py`.

### 7.2 Self-play and H2H archives

- `selfplay_runs_pc1andpc2_combined.zip` — original two-PC 100-game control material.
- `audit_extract/selfplay_runs/pc1_v69_50/`.
- `audit_extract/selfplay_runs/pc2_v69_50/`.
- `audit_extract/selfplay_runs/pc1_v71_50/`.
- `audit_extract/selfplay_runs/pc2_v71_50/`.
- `combined_games.json` / `.csv`, `combined_move_metrics.csv`, `combined_summary.json`, `combined_report.md` — 200-game v6.9-v7.1 direct comparison.
- `v69_vs_v72_pilot.zip`, `v71_vs_v72_pilot.zip` and extracted equivalents under `audit_extract/`.
- `v69_vs_v73_250.zip`, `v71_vs_v73_250.zip` and extracted equivalents under `audit_extract/`.
- `emperor_lab.zip` — v7.4 pilot/600-game experiment archive.
- `audit_extract/emperor_lab/v74_pilot10_overnight/` and `v74_pilot10_analysis/`.
- `audit_extract/emperor_lab/v74_unique600_overnight/` and `v74_unique600_analysis/`.

### 7.3 18-game diagnostics

- `TOURNAMENT_18_DIAGNOSTIC_RESULTS_V67.json`.
- `TOURNAMENT_18_DIAGNOSTIC_RESULTS_V68_Selective_Book.json`.
- `TOURNAMENT_18_DIAGNOSTIC_RESULTS_V69.json`.
- `TOURNAMENT_18_DIAGNOSTIC_RESULTS_V70.json`.
- `TOURNAMENT_18_DIAGNOSTIC_RESULTS_V70_DEPTH10.json` and `(1).json`.
- `TOURNAMENT_18_DIAGNOSTIC_RESULTS(1).json` through `(5).json`, plus the unnumbered file: exploratory runs without enough metadata to assign to a particular source version.
- `TOURNAMENT_18_RESULTS.json`: 14 wins / 4 losses; do not assign to a source version without its original manifest.

### 7.4 v7.5 candidate files

- `agent_v75_endgame_depth.py`.
- `endgame_tablebase.py`.
- `endgame_tb_snippet.py`.
- `test_v75_tablebase.py`.
- `test_v75_search_controls.py`.
- `smoke_test_v75.py`.
- `run_v75_18_tournament.py`.
- `run_v74_v75_head_to_head.py`.
- `validate_v75.ps1`.
- `V75_README.md` and `V75_MANIFEST.json`.
- `V75_ENDGAME_DEPTH_PACKAGE.zip`.

### 7.5 Known missing source snapshots

The current handoff mount does not include the source files for:
- `agent_v71_adaptive_tactical_hybrid.py` (SHA-256 `488b051b3dce2e49f3b883a16dc12eddaba31510a0596bde7b83247c933865de`).
- `agent_v72_mobility_aware.py` (SHA-256 `7360db1d0482cd3dd3965a279c2c733507307efad42690ec305408468d331883`).

The manifests and the results are present. These are recoverable from the original Windows project if it still exists. A future agent should locate the exact original files and compare SHA-256; it must not fabricate substitute versions and label them v7.1/v7.2.

---

## 8. Guidance for the next AI agent

The next agent should read this document before editing any source. Then follow this order.

### Step 1 — Establish reproducibility

1. Confirm the current working directory and identify the active ChessMaker package/version.
2. Verify source hashes for v6.9, v7.1 (after recovery), v7.4 and v7.5.
3. Confirm the `extension/` files and `samples.py` are the same in all benchmark conditions.
4. Ensure every game creates a fresh board instance; do not reuse mutated sample objects.
5. Confirm the actual game clock and per-move budget. The large historical experiments used 300s per player; other runs used 12s or 14s per move. Do not mix them without reporting the difference.

### Step 2 — Validate v7.5 locally before a tournament

Run:

```powershell
python -m py_compile .\agent_v75_endgame_depth.py .\run_v75_18_tournament.py .\run_v74_v75_head_to_head.py .\smoke_test_v75.py .\test_v75_tablebase.py .\test_v75_search_controls.py
python .\test_v75_tablebase.py
python .\test_v75_search_controls.py
python .\smoke_test_v75.py
```

Then run the supplied validation script:

```powershell
powershell -ExecutionPolicy Bypass -File .\validate_v75.ps1 -RunTournament
```

Inspect the output for actual ChessMaker import, legal move, board mutation, deadline, and clock behaviour. A passing `py_compile` or mock-board tablebase test does not replace the live smoke test.

### Step 3 — Make controlled H2H tests

At minimum compare v7.5 against v7.4 and v6.9. Ideally include v7.1 after source recovery.

- Use identical initial position sets and independent RNG seeds for each engine.
- Play every position twice with colours reversed.
- Keep board layout, opening generator, clock, per-move cap, workers and hardware identical.
- Use at least 200 games per important comparison; 250 is preferable when investigating a colour-sensitive candidate.
- Run v7.4 and v7.5 in both directions, not just `candidate as White`.
- Preserve every PGN/game trace equivalent, JSONL move log, summary and manifest.
- Report W/D/L, points%, colour split, board split, paired-reversal counts, error/timeouts, average/median/p90/max completed depth, threshold counts, nodes, NPS, move time, TT hits/cutoffs, LMR counts, tablebase probes/hits and root replacements.

### Step 4 — Decide whether the optimisation worked

Do not accept "average depth increased" as sufficient. Check:

- Did average **completed** depth rise under the same clock?
- Did NPS rise or did the engine simply visit fewer/shallower nodes?
- Did score improve against frozen baselines?
- Did either colour regress?
- Did any board layout regress sharply?
- Did clock forfeits or aborted iterations increase?
- Did tactical guard interventions improve concrete positions or merely change moves?
- Did tablebase hits occur in real games and save meaningful search time?

### Step 5 — Tactical regression workflow

Use the v7.4 3,332-position tactical-review bank and the 10,364 unique decision-position set as a source of candidate tests. For every candidate:

1. Reconstruct the exact board, side to move and legal move list.
2. Independently analyse the forcing line, including captures, checks, promotions and no-legal-move/stalemate-loss outcomes.
3. Establish a correct/acceptable move or WDL result before labelling the engine choice a blunder.
4. Add a minimal regression test that can run quickly.
5. Re-run the full benchmark after changing evaluation/search logic.

Never infer a correct move solely from a root score/bound recorded in a PVS search. The v7.4 analysis report explicitly warns that root candidate scores may be bounds, not exact evaluations.

### Step 6 — Preserve frozen baselines

Never edit frozen sources in place. Every new candidate should have:
- A new versioned filename.
- A source SHA-256 in its manifest.
- A changelog of exact modifications.
- A test report including failures, not only successful runs.
- A clear promotion decision with reasons.

---

## 9. Promotion gates and project status

Use the following policy so the project does not regress through enthusiasm for a new design:

| Gate | Requirement | Decision if failed |
|---|---|---|
| Static integrity | Compile/import, no syntax errors, source hash recorded | Do not benchmark |
| Unit/regression tests | Tablebase, TT, terminal, repetition, promotion, anti-stalemate, LMR and clock tests pass | Fix or revert |
| Live runtime | Full ChessMaker smoke test; legal moves and board state verified | Do not run large tournament |
| Short screening | 18-game three-tier suite with errors/timeouts logged | Diagnose; no promotion |
| Paired H2H | ≥200 games, equal colour reversal and board coverage, same hardware/configuration | Continue testing; no promotion |
| Colour robustness | No severe Black/White asymmetry hidden by aggregate score | Reject or repair candidate |
| Tactical regression | No known high-impact regressions; 600-game tactical candidates reviewed | Reject or repair candidate |
| Efficiency | Higher useful completed depth or stronger score at the same clock, without timeout increase | Do not claim speedup |
| Final promotion | Candidate reliably beats/equals frozen references across repeated controlled trials | Promote only after full report |

### Current promotion status

| Engine | Status | Reason |
|---|---|---|
| v6.9 | Frozen reference | 18/18 diagnostic; important comparison anchor; not assumed unbeatable |
| v7.1 | Strong challenger | 55% in 200-game H2H vs v6.9; source recovery required |
| v7.2 | Archived experimental | Weak 20-game pilot results, severe Black-side failures |
| v7.3 | Archived research predecessor | 60.8% vs v6.9 but only 45.0% vs v7.1; extreme Black-side losses |
| v7.4 | Active research baseline | 600 unique self-play games and tactical corpus; no direct H2H proof of superiority |
| v7.5 | Experimental candidate | Regression tests pass; live ChessMaker and tournament performance unverified |

---

## 10. Final handoff summary

The engine project has a meaningful experimental history, including early algorithmic failures, controlled pruning ablations, versioned 18-game opponent tournaments, two-PC 100-game same-engine controls for v6.9 and v7.1, a 200-game paired v6.9-v7.1 H2H, two 20-game v7.2 pilots, two distinct 250-game v7.3 H2Hs, and a 600-game v7.4 unique-opening self-play corpus.

The core engineering lesson is to optimise for **correct, useful completed search under the real game clock**, not nominal depth. The major strategic lesson is to measure both colours and all board layouts. The major process lesson is to preserve source hashes, manifests, move logs and frozen baselines.

The next agent should not redesign everything from scratch. It should:

1. Keep v6.9, recover v7.1, and retain v7.4 as the key references.
2. Validate v7.5 live in the user's ChessMaker environment.
3. Run paired colour-reversed H2Hs with fixed seeds and identical clocks.
4. Review v7.4 tactical candidates before changing evaluation weights.
5. Keep the tablebase optional unless real-game hit-rate and strength/efficiency data justify it.
6. Promote only with measured results and keep all prior sources/results read-only.

**Do not delete the old engine versions or raw experiments simply to clean the directory. Archive them, keep only a small active set, and preserve enough provenance to reproduce every reported result.**

