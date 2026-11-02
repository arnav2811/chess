# Chess Fragments Agent — Changelog v7.7 → v7.9

> **Final tournament result (v7.9): 18W / 0D / 0L — 100% win rate**  
> Baseline 6/6 · Strong 6/6 · Master 6/6

---

## v7.9 — "Stalemate Guard Always On"
**Date:** 2026-11-01  
**Result:** ✅ 18/18 — Perfect Score  
**ENGINE_BUILD:** `"v7.9-stalemate-guard-always-on"`

### What Changed

#### Fix 1 — Stalemate Guard Always Runs (Root Cause of v7.8 Loss)

**The bug:** In v7.8, the stalemate guard (`_entropy_guided_anti_loss`) was gated behind a flag:

```python
# v7.8 — BROKEN
if not _last_tb_root_solved:
    piece, move_opt = _entropy_guided_anti_loss(board, player, var, deadline)
```

When the endgame tablebase successfully solved the root position (`_last_tb_root_solved = True`), the stalemate guard was **completely skipped**. The engine walked into a stalemate trap in game 12 (Strong/Black/sample2, ply ~53) while the tablebase was confidently guiding moves — it knew the position was theoretically winning, but didn't see the stalemate one move away.

**The fix:** The stalemate guard now always runs, regardless of tablebase status:

```python
# v7.9 — FIXED: always check for stalemate traps
piece, move_opt = _entropy_guided_anti_loss(board, player, var, deadline)
if piece is None:
    piece, move_opt = _tb_or_search_result   # fall back if no threat detected
```

**Why this is safe:** `_entropy_guided_anti_loss` only overrides the engine's chosen move when it detects the opponent is in a stalemate-adjacent position AND the engine's chosen move would complete that stalemate. It is a veto, not a replacement — if no stalemate threat is detected it returns `None` and the tablebase/search result stands.

#### Fix 2 — Tablebase DRAW returns 0, not −DRAW_CONTEMPT

**The bug (v7.8):** Draw contempt was applied to tablebase DRAW probes:

```python
# v7.8 — caused fighting from theoretically drawn positions
if tb_result == "DRAW":
    return -DRAW_CONTEMPT   # ← BAD: engine panics, makes desperate moves
```

This caused the engine to treat proven draws as near-losses and make increasingly erratic moves trying to "escape" — setting up the stalemate trap that killed game 12.

**The fix:** Proven tablebase draws return 0:

```python
# v7.9
if tb_result == "DRAW":
    return 0   # accepted — neither side can force a win from here
```

Draw contempt is still correctly applied to:
- **K-vs-K terminal** → `−DRAW_CONTEMPT` (agent avoids trading down to bare kings)
- **Repetition avoidance** → positions seen ≥1 time get a penalty (break loops early)
- **Tablebase DRAW** → `0` (accept — don't fight the inevitable) ✅

### Game 12 Replay (why v7.9 wins it)

| Phase | v7.8 | v7.9 |
|-------|------|------|
| Ply ~34 — tablebase takes over | Guard skipped (`tb_root_solved=True`) | Guard always active |
| Ply ~53 — opponent near-stalemate | Engine plays stalemate-completing move | Guard vetoes, engine plays safe move |
| Outcome | **LOSS (stalemate)** | **WIN (White clock runs out, 53 plies)** |

---

## v7.8 — "Win-Only / No Draws"
**Date:** 2026-11-01  
**Result:** ⚠️ 17/18 — 1 loss (Game 12: Strong/Black/sample2, stalemate)  
**ENGINE_BUILD:** `"v7.8-win-only-no-draws"`

### Motivation

The user's rule is explicit: **only a win counts, draws = losses**. v7.7 occasionally drew game 12. v7.8 aimed to eliminate all draws by making the engine hate them.

### What Changed

#### 1. Draw Contempt Constant

```python
DRAW_CONTEMPT = 60_000   # > max material, < checkmate
```

One constant controls all draw-avoidance. Larger than any material score so the engine always prefers any winnable position over a draw.

#### 2. K-vs-K Terminal Detection

```python
if _is_king_vs_king(board):
    return -DRAW_CONTEMPT
```

K-vs-K is a guaranteed draw. Scoring it at −60,000 makes the engine refuse to trade down to bare kings even when materially ahead. Previously returned 0.

#### 3. Repetition Threshold Lowered

```python
# v7.7: penalise when position seen >= 2 times
# v7.8: penalise when position seen >= 1 time (first repeat = bad)
if _position_history.count(pos_key) >= 1:
    score -= REPETITION_PENALTY
```

Breaks out of cyclic play one cycle earlier.

#### 4. Draw Contempt on Tablebase DRAW ← **The Mistake**

```python
if tb_result == "DRAW":
    return -DRAW_CONTEMPT   # Introduced in v7.8, reverted in v7.9
```

Intended to make the engine fight drawn endgames. Instead caused panicked, erratic moves in theoretically equal positions → stalemate in game 12. **This was the regression. Reverted in v7.9.**

---

## v7.7 — "Final Handoff"
**Date:** 2026-11-01  
**Result:** ~17/18 (sometimes drew game 12)  
**ENGINE_BUILD:** `"v7.7-final"`

### Architecture Overview

v7.7 is the consolidated production build — all prior experimental branches merged into one coherent engine.

### Core Search: Iterative Deepening Alpha-Beta

```
Root
 └─ Iterative deepening (depth 1 → 2 → 3 → … until time expires)
     └─ Alpha-Beta Negamax
         ├─ Transposition Table (Zobrist hashing)
         ├─ Move ordering: TT move → killers → captures (MVV-LVA) → quiet (history)
         ├─ Late Move Reduction (LMR)
         ├─ Aspiration Windows
         ├─ Check extensions (+1 ply)
         └─ Mobility extensions (+1 ply when opponent mobility critically low)
```

**Why iterative deepening?** On the 5×5 board with a 300s clock we can't predict depth. Iterative deepening always has a complete result from the previous depth to return if time runs out. Average depth: **2–4 plies** (median ~3), endgame positions reach **5–6 plies**.

### Evaluation Function

| Component | Weight | Purpose |
|-----------|--------|---------|
| Material | ~1000/piece | Raw piece advantage |
| Mobility | +15/legal move | Activity and control |
| King safety | −200 if exposed | Penalise exposed king |
| Promotion threat | +300 near last rank | Encourage pawn pushes |
| Centre control | +20/centre square | Positional control |
| Piece-square tables | ±10–50/piece | Good piece placement |
| Repetition penalty | −DRAW_CONTEMPT | Avoid cyclic play |

### Endgame Tablebase

Pre-computed binary tablebase covering **65 material configurations** with 3–4 pieces:

- **Probe at any node:** `probe_endgame_tb(board)` → `WIN / LOSE / DRAW / UNKNOWN`
- **Root solve (≤4 pieces):** `_solve_root_from_tablebase()` picks the optimal move directly, bypassing search
- **Leaf probe:** During alpha-beta, tablebase results replace static eval for 3-4 piece positions

**Data:** `endgame_tb_snippet_v77.py` (~4.7 MB packed binary), loaded by `endgame_tablebase_v77.py`.

### Stalemate Guard: `_entropy_guided_anti_loss`

A dedicated safety net that runs after the search/tablebase selects a move:

1. Enumerate all opponent responses to the engine's chosen move
2. Check if any response leaves the opponent with 0 legal moves (not in check) = stalemate
3. If stalemate detected → scan all engine moves for one that doesn't enable it
4. Among safe alternatives, prefer the move that maximises opponent legal moves ("entropy" = harder to get stuck)

### Move Ordering Pipeline

Good move ordering determines how many nodes alpha-beta prunes. The ordering:

```
1. Hash move (TT best from previous iteration)
2. Winning captures (MVV-LVA: best victim / cheapest attacker)
3. Killer moves (2 moves that caused beta-cutoffs at this depth)
4. Quiet moves (sorted by history heuristic — moves that historically raised α)
5. Losing captures (attacker more valuable than victim)
```

### Time Management

```python
effective_budget = remaining_time / estimated_moves_left
safety_reserve   = min(0.70, max(0.10, effective_budget * 0.06))
thinking_time    = effective_budget - safety_reserve
```

- `estimated_moves_left` recalculates each ply from piece count + game phase
- Emergency brake: if `time.time() > deadline`, return best move found so far
- Safety reserve scales with budget — prevents time forfeits

### Repetition Avoidance

```python
_position_history: list[str]   # Zobrist hash per ply
```

Before accepting any move, the resulting board hash is checked against history. Positions already seen are penalised — prevents the opponent from forcing a draw by repetition.

---

## Strategy Summary

| Strategy | Applied In | Effect |
|----------|-----------|--------|
| Iterative deepening | All games | Full time use; safe fallback |
| Alpha-beta pruning | All games | ~10× more nodes than minimax |
| Transposition table | Mid/late game | No re-searching of identical positions |
| LMR | Quiet positions | ~1 free extra ply of depth |
| Aspiration windows | Iterations ≥2 | Faster cutoffs around expected score |
| Check extensions | Tactical positions | Sees mates 1-2 plies deeper |
| Mobility extensions | Low-mobility positions | Detects zugzwang/stalemate earlier |
| Endgame tablebase | ≤4 pieces | Perfect play in all covered endgames |
| Stalemate guard | **Always** (v7.9+) | Never walks into stalemate |
| Draw contempt (K-vs-K) | Terminal detection | Never trades down to bare kings |
| Draw contempt (repetition) | History check | Never cycles into a draw |
| Move ordering | Every node | Maximises pruning efficiency |

---

## File Map

| File | Role |
|------|------|
| [`agent.py`](file:///c:/Users/arnav/Downloads/CW-COMP2321-fullgame%20-Post%20Cut%20V5.6/agent.py) | Main engine — v7.9 submission |
| [`endgame_tablebase_v77.py`](file:///c:/Users/arnav/Downloads/CW-COMP2321-fullgame%20-Post%20Cut%20V5.6/endgame_tablebase_v77.py) | Tablebase probe/solve API |
| [`endgame_tb_snippet_v77.py`](file:///c:/Users/arnav/Downloads/CW-COMP2321-fullgame%20-Post%20Cut%20V5.6/endgame_tb_snippet_v77.py) | 4.7 MB pre-computed tablebase binary |
| [`run_tournament_v78.py`](file:///c:/Users/arnav/Downloads/CW-COMP2321-fullgame%20-Post%20Cut%20V5.6/run_tournament_v78.py) | 18-game tournament runner |
| [`check_v77.py`](file:///c:/Users/arnav/Downloads/CW-COMP2321-fullgame%20-Post%20Cut%20V5.6/check_v77.py) | Pre-flight sanity checks |
| `V78_TOURNAMENT_RESULTS.json` | v7.9 results (18W/0D/0L) |

---

## Version Score Table

| Version | W | D | L | Score | Notes |
|---------|---|---|---|-------|-------|
| v7.7 | 17 | 1 | 0 | 17/18 | Drew game 12 (stalemate guard existed but TB DRAW was 0) |
| v7.8 | 17 | 0 | 1 | 17/18 | Lost game 12 (TB DRAW contempt + guard skipped in TB mode) |
| **v7.9** | **18** | **0** | **0** | **18/18 ✅** | Both bugs fixed — perfect score |
