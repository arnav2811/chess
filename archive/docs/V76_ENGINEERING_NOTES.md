# v7.6 Engineering Notes and Evidence

## Decision summary

The v7.6 code (formerly the v7.5 R2 candidate) keeps v7.4's proven strategic/evaluation design and corrects the actual defects exposed by the previous v7.5 candidate's H2H. It does not attempt a risky evaluator rewrite or add MCTS/null-move pruning.

## Baseline evidence that informed R2

### Previous v7.5 vs v7.4, 10 paired-colour games

- v7.5 record: 5 wins, 0 draws, 5 losses.
- Average completed depth: 2.317 vs v7.4's 2.380.
- Average nodes: 684.8 vs 713.2.
- Average think time: 8.801s vs 9.077s.
- Tablebase hits: zero for both engines in that H2H.

Interpretation: no demonstrated playing-strength gain; slightly lower average depth; modest time saving; the test did not reach a covered endgame position, so it did not demonstrate tablebase value.

### Previous v7.5 18-game diagnostic tournament

- 17 wins, 0 losses, 1 draw against the three diagnostic opponent tiers.
- The only draw was a fivefold repetition as Black against Master, after 74 plies with six pieces remaining.

Interpretation: the previous public v7.5 build performed strongly against those opponents, but this is not a direct v7.4 comparison and does not validate the revised exact-tablebase candidate.

### v7.4 600-game analysis

- 600 completed games, 600 unique starting positions, 10,364 unique decision positions.
- Tactical signals: 1,006 immediate-major-piece-capture events; 287 next-ply promotion signals; 313 material-guard triggers (12 replacements); 127 promotion-guard triggers (2 replacements).
- The analysis report explicitly labels these as review leads, not verified blunders or ground-truth moves.

Interpretation: preserve the existing evaluation and guard stack. Do not alter weights based solely on raw signal counts.

## v7.6 code changes (implemented in the preceding R2 engineering pass)

### Exact tablebase

The previous adapter modified DRAW entries with material contempt and king-cornering gradient, although the embedded retrograde probe returned zero. v7.6 makes DRAW=0 and preserves WDL minimax semantics. The agent passes the already-collected piece list to the adapter, so the board is not traversed a second time for each probe.

### Actual root selection

Previously, the tablebase was only probed inside Negamax/quiescence. v7.6 additionally tries the root itself: it checks root coverage, then evaluates every legal child via terminal detection or tablebase WDL. It verifies the child's best WDL is consistent with the root WDL. If any child cannot be proved, the normal search takes over. Root-solved moves are separately instrumented and are not misreported as depth-search iterations.

### Search safeguards

- LMR's two-ply reduction threshold is restored to the v7.4 setting (`depth >= 8`, `move_index >= 11`, history `<64`).
- Frontier futility is restricted to nodes with at least six legal moves, leaving low-mobility stalemate tactics to the full search.
- Iterative deepening, PVS, aspiration windows, TT, history, killer moves, quiescence, promotion/check ordering, tactical guards, repetition avoidance and clock fallback remain.

### TT key

v7.6 hashes a frozenset of complete piece descriptors plus side-to-move. The key is independent of `get_pieces()` order and avoids sorting. Fresh packaging-time rerun (5 runs × 200,000 calls) measured medians of 1.1493s for the legacy sorted-tuple key and 0.9050s for the v7.6 frozenset key: 21.26% lower median key-construction time and 26.99% higher key throughput in this synthetic microbenchmark. This is not a whole-engine speedup claim.

## Tests completed here

- Python compilation for all v7.6 Python modules and helper modules.
- Basic K+Q tablebase probe passes.
- All 65 stored material configurations load.
- The 555 distinct historical 3-/4-piece states all match the embedded table's exact WDL through the production adapter and the agent's tablebase helper.
- WDL split verified: 240 WIN, 227 LOSS, 88 DRAW.
- Extreme legacy `mat_diff` values do not change DRAW=0.
- Direct root tablebase selector chooses the best mocked WDL child; it refuses partial child data and falls back.
- History ageing, conservative LMR exemptions, low-mobility futility gate, TT order-independence/side sensitivity and expired-root fallback pass.
- Hash microbenchmark completed.

## Not completed here

ChessMaker is not installed in this execution environment. Therefore the actual `smoke_test_v76.py`, live move generation, full H2H and 18-game R2 tournament have not been run here. No R2 win-rate or full-engine NPS claim is made.

## Operational decision

Treat v7.6 as the active exact-tablebase candidate, but retain the previous v7.5 package for reproducibility. Keep v6.9 and v7.4 immutable. Run `validate_v76.ps1`, review smoke-test output, then run the v7.6 H2H/tournament. Promotion is a data-backed choice, not an assumption.
