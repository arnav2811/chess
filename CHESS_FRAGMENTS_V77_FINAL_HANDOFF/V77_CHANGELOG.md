# v7.7 changelog

## Parent

Based on the v7.6 exact-tablebase source and its three uploaded result files:

- `V76_TOURNAMENT_18_RESULTS.json`
- `V76_TOURNAMENT_18_METRICS_SUMMARY.json`
- `V76_V74_H2H_10.json`

## Changes

### 1. Stalemate-loss guard coverage

v7.6 `_entropy_guided_anti_loss` returned early for crowded positions unless the selected piece was the king. That left high-material non-king moves without the one-opponent-reply terminal-loss verifier. Matches 8 and 12 both ended in Black stalemate loss with 15 pieces still present. v7.7 removes the non-king bypass, uses a bounded crowded-position safety reserve, and caps alternative checks at four candidates.

The old v7.6 JSON did not record move coordinates, so this is a code-path coverage fix motivated by the losses, not a claim that the precise final v7.6 moves have been replayed and proven to be non-king moves.

### 2. Tablebase repetition tie-break

When all compared children have the same exact tablebase score, v7.7 prefers a child signature with a lower count in `_position_history`. Exact WDL score remains the primary ordering key. `tablebase_repeat_avoided` records whether this secondary criterion changed the first-in-order best-WDL choice.

### 3. Diagnostics and benchmark evidence

New per-move diagnostics:

- `stalemate_guard_calls`
- `stalemate_guard_threats`
- `stalemate_guard_inconclusive`
- `stalemate_guard_replacements`
- `tablebase_repeat_avoided`

### 4. Replayable benchmark results

Both v7.7 tournament runners now preserve the initial board and every move's pre-move board, moving piece, source square, destination square, captures, side, ply and engine label. This is necessary to analyse future stalemate and repetition failures without reconstructing games from summary data.

## Not changed

- Material / positional evaluation weights.
- Core Negamax, alpha-beta, PVS, iterative deepening and aspiration architecture.
- Existing transposition-table implementation.
- Exact 65-configuration retrograde dataset and WDL scoring semantics.
- PUCT remains disabled.
- No new null-move pruning or speculative evaluation penalties.
