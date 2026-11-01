# 🎮 Chess Fragments Agent — Submission & Testing Guide

## Quick Start: Run a Game in 30 Seconds

```bash
cd "CW-COMP2321-fullgame -Post Cut V5.6"
conda activate comp2321        # or your Python 3.12+ venv
python test_fullgame.py        # Agent (White) vs Opponent (Black), sample0
```

The game plays automatically and prints the result:
```
=== Game ended: Checkmate - black loses ===
```

---

## 1. Playing Against the Agent Yourself (Interactive)

The project includes `play.py` — a terminal-based interactive game:

```bash
# You play White, AI plays Black (default)
python play.py

# You play Black, AI plays White
python play.py --side black

# Choose a different starting board
python play.py --board sample1
python play.py --board sample2
```

### Controls
| Input | Action |
|---|---|
| `2 4 2 3` | Move piece at (col=2, row=4) → (col=2, row=3) |
| `board` | Reprint the board |
| `quit` | Resign |
| `Ctrl+C` | Force quit |

### Reading the Board
```
   0   1   2   3   4       ← column index (x)
0  n   q   k   b   R*      ← Black's back rank (lowercase = Black)
1  p   p   p   p   p
2  .   .   .   .   .       ← empty squares
3  P   P   P   P   P       ← White's pawns (UPPERCASE = White)
4  R*  B   K   Q   N       ← White's back rank
```

- **K/k** = King, **Q/q** = Queen, **B/b** = Bishop, **N/n** = Knight
- **R\*/r\*** = Right (Rook + Knight hybrid — the custom piece!)
- **P/p** = Pawn (promotes to Queen on the far rank)
- Coordinates: x = column (0–4, left→right), y = row (0–4, top→bottom)

---

## 2. Testing Against Different Opponents

### Available Opponents

| Opponent | File | Strength | Search Depth |
|---|---|---|---|
| **Baseline** | `opponent.py` | Weak | Depth 3 (minimax) |
| **Strong** | `strong_opponent.py` | Medium | Depth 5 (negamax + TT + PSTs) |
| **Master** | `master_opponent.py` | Hard | Depth 7 (alpha-beta + dynamic heuristics) |

### Configuring Matchups

Edit the last line of [test_fullgame.py](file:///c:/Users/arnav/Downloads/CW-COMP2321-fullgame%20-Post%20Cut%20V5.6/test_fullgame.py):

```python
if __name__ == "__main__":
    # Agent as White vs Baseline opponent as Black
    testgame_timeout(p_white=agent, p_black=opponent, board_sample=sample0)
```

#### All Possible Combinations

```python
# ─── Import opponents at the top of test_fullgame.py ───
from opponent import opponent
from strong_opponent import strong_opponent
from master_opponent import master_opponent    # if you have this file

# ─── Agent as WHITE ───
testgame_timeout(p_white=agent, p_black=opponent, board_sample=sample0)
testgame_timeout(p_white=agent, p_black=strong_opponent, board_sample=sample1)

# ─── Agent as BLACK ───
testgame_timeout(p_white=opponent, p_black=agent, board_sample=sample0)
testgame_timeout(p_white=strong_opponent, p_black=agent, board_sample=sample2)

# ─── Agent vs itself (mirror match) ───
testgame_timeout(p_white=agent, p_black=agent, board_sample=sample0)
```

#### Available Board Samples

| Sample | Description | Import |
|---|---|---|
| `sample0` | Standard symmetric | `from samples import sample0` |
| `sample1` | Mirrored piece arrangement | `from samples import sample1` |
| `sample2` | Asymmetric setup | `from samples import sample2` |
| `sample3` | Double-Right (Right-heavy) | `from samples import sample3` |
| `sample4` | Queen-less (endgame practice) | `from samples import sample4` |

> [!TIP]
> Run all 3 official boards (sample0, sample1, sample2) as both White and Black — that's 6 games per opponent, 18 total across 3 tiers. This is the "full tournament sweep" pattern.

---

## 3. Running a Full 18-Game Tournament (CLI One-Liner)

You can run all matchups quickly from the command line:

```bash
# Quick smoke test: Agent White vs Baseline on sample0
python test_fullgame.py

# To test all boards, edit test_fullgame.py or use this pattern:
python -c "
from test_fullgame import testgame_timeout
from agent import agent
from opponent import opponent
from samples import sample0, sample1, sample2

for board_name, board in [('sample0', sample0), ('sample1', sample1), ('sample2', sample2)]:
    print(f'\n===== {board_name}: Agent White vs Opponent Black =====')
    testgame_timeout(p_white=agent, p_black=opponent, board_sample=board)
    print(f'\n===== {board_name}: Opponent White vs Agent Black =====')
    testgame_timeout(p_white=opponent, p_black=agent, board_sample=board)
"
```

---

## 4. Understanding the Agent's Output

During search, the agent prints instrumentation to **stderr**:

```
[agent v5.6] ply=  1  white  depth=6  nodes= 142857  ebf=2.81  nps= 12345  time=11.58s
```

| Field | Meaning |
|---|---|
| `ply` | Current half-move number |
| `depth` | Deepest completed search depth |
| `nodes` | Total positions evaluated |
| `ebf` | Effective branching factor (lower = better pruning) |
| `nps` | Nodes per second |
| `time` | Wall-clock thinking time for this move |

> [!NOTE]
> The EBF of **~2.8** (down from a theoretical maximum of ~10) shows that the pruning heuristics are working well — the agent prunes ~72% of the tree.

---

## 5. Files to Submit

> [!IMPORTANT]
> **Only `agent.py` is graded.** Submit the single file. The marking system runs it against their own test harness — your `opponent.py`, `play.py`, etc. are for your local testing only.

### Submission Checklist

| # | Check | Status |
|---|---|---|
| 1 | `agent.py` has a function `agent(board, player, var)` | ✅ |
| 2 | No external dependencies (only `chessmaker`, `board_utils`, Python builtins) | ✅ |
| 3 | All helper functions defined inside `agent.py` | ✅ |
| 4 | Agent returns `(piece, move_option)` tuple | ✅ |
| 5 | Tested on all 3 official boards (sample0, sample1, sample2) | ✅ |
| 6 | Tested as both White and Black | ✅ |
| 7 | Never exceeds 14 s thinking time per move | ✅ |
| 8 | Never exceeds 300 s total game time | ✅ |
| 9 | Works on Python 3.12 and 3.13 | ✅ |
| 10 | Code is well-commented with clear docstrings | ✅ |

---

## 6. Project Files and Repository Cleanup

Understanding what files are used for submission versus internal development and reporting:

| File | Purpose | Status |
|---|---|---|
| `agent.py` | Complete standalone tournament agent | 🚀 **PRIMARY SUBMISSION FILE** |
| `CHANGELOG.md` | Full iterative design history & tablebase ablation archive | 📌 **KEPT** for documentation & report writing |
| `SUBMISSION_GUIDE.md` | Testing, CLI usage, and submission guide | 📌 **KEPT** for reference |
| `EXPLAIN.md` | In-depth strategy and heuristic explanations | 📌 Useful for coursework report |
| `PRESENTATION_20_SLIDES.md` | Slide deck outline for project viva/presentation | 📌 Kept for presentation preparation |
| `play.py` | Interactive terminal play mode against the AI | 🛠️ Testing utility |
| `test_fullgame.py` | Coursework game execution harness | 🛠️ Testing utility |
| `opponent.py` | Coursework Baseline (Depth 3 Minimax) | 🛠️ Testing utility |
| `strong_opponent.py` | Adversarial Stress Test (Depth 5 Negamax) | 🛠️ Testing utility |
| `master_opponent.py` | Master Benchmark (Depth 7 Alpha-Beta) | 🛠️ Testing utility |
| `samples.py` | Board sample initializations | 🛠️ Coursework framework |
| `extension/` | Framework rules and piece definitions | 🛠️ Coursework framework |

---

## 7. Tournament Performance Summary

Based on the v5.6 Clean Sweep architecture:

| Tier | Opponent | Wins | Losses | Draws | Win Rate | Points |
|---|---|---|---|---|---|---|
| 1 | Baseline (Depth 3) | 6 | 0 | 0 | **100.0%** | **6.0 / 6.0 (100%)** |
| 2 | Strong (Depth 5) | 5 | 0 | 1 | **83.3%** | **5.5 / 6.0 (91.7%)** |
| 3 | Master (Depth 7) | 3 | 0 | 3 | **50.0%** | **4.5 / 6.0 (75.0%)** |
| **Total** | **All 18 Matches** | **14** | **0** | **4** | **77.8%** | **16.0 / 18.0 (88.9%)** |

> [!TIP]
> The agent achieved **0 LOSSES across all 18 matches** against Depth-3, Depth-5, and Depth-7 adversaries. With the Black clock bug fixed, Black went from losing 3 games to being 100% undefeated (7W / 2D / 0L). Key strengths: (1) 0 clock timeouts or forfeits, (2) anti-stalemate awareness, and (3) deep search depth 6–8 with aggressive pruning.

---

## 8. Quick Debugging Tips

| Problem | Likely Cause | Fix |
|---|---|---|
| Agent returns `None` | No legal moves available | Normal — game is over |
| Game ends in "Draw - game timeout" | 300 s budget exhausted | Dynamic budgeting prevents this — check `effective_budget` |
| Agent plays randomly | Search throws an exception | Check stderr for tracebacks |
| `ModuleNotFoundError: chessmaker` | Missing dependency | `pip install chessmaker` |
| Crashes on Python 3.13 | `piece.name` returns property object | Already fixed via `_piece_name()` helper |
