# COMP2321 Chess Fragments — Submission Guide

## v7.9 Engine Stats (from 18-game tournament logs, 215 plies)

### Search Depth

| Metric | Value |
|--------|-------|
| **Average depth (all plies)** | **2.1** |
| **Average depth (substantive, depth ≥ 2)** | **3.2** |
| **Median depth** | 3 |
| **Max depth reached** | 7 (endgame, few pieces) |
| **Most common depth** | 3 (32% of plies) |

**Depth distribution:**
```
depth 0  (instant/terminal): 59 plies  █████████████████████████████████████
depth 1  (quiescence only):  21 plies  █████████████
depth 2                    : 30 plies  ██████████████████
depth 3  ← most common     : 69 plies  ████████████████████████████████████████
depth 4                    : 26 plies  ████████████████
depth 5                    :  6 plies  ████
depth 6                    :  2 plies  █
depth 7  (late endgame)     :  2 plies  █
```

> [!NOTE]
> Depth 0/1 plies are not wasted — they are either terminal positions (checkmate/stalemate detected instantly), tablebase root-solved positions (47 root solves this tournament, 1192 TB probes), or quiescence-only tails. The engine is spending its time budget correctly.

### Speed

| Metric | Value |
|--------|-------|
| Average NPS | 73 nodes/sec |
| Median NPS | 82 nodes/sec |
| Average nodes/ply | 602 |
| Median nodes/ply | 750 |
| Avg thinking time/ply | 6.4s |
| Tablebase probes | 1,192 across 18 games |
| TB root solves | 47 across 18 games |

> [!TIP]
> Python's ~75–100 NPS is a known bottleneck on this hardware. The engine compensates through high pruning efficiency (alpha-beta + TT + LMR + aspiration windows), endgame tablebase perfect play, and time management that uses the full 300s budget.

---

## Estimated ELO

> [!IMPORTANT]
> ELO can't be measured precisely without a large Swiss-system tournament. This is a reasoned estimate based on performance data and architecture.

### Method: Performance-based estimation

The agent scored **18/18 (100%)** against Baseline, Strong, and Master tier opponents.

Based on ELO maths, if the Master opponent is estimated at ~1800 ELO (strong rule-based 5×5 player), then:
- Winning 100% against Master (6/6) → agent is at least **250–300 ELO above Master**
- That places v7.9 at roughly **~2050–2100 ELO** on the 5×5 Chess Fragments scale

### Architecture ELO contributors

| Feature | Typical ELO gain | Present in v7.9? |
|---------|-----------------|-----------------|
| Alpha-beta over minimax | +200–300 | ✅ |
| Transposition table | +50–100 | ✅ |
| Move ordering (killers + history) | +50–100 | ✅ |
| Aspiration windows | +20–40 | ✅ |
| LMR | +30–60 | ✅ |
| Endgame tablebase | +100–200 (endgames) | ✅ |
| Quiescence search | +50–100 | ✅ |
| Check extensions | +20–50 | ❌ Disabled by default (`_ENABLE_CHECK_EXTENSION = False`) |
| Mobility extension | +10–30 | ✅ |
| Stalemate guard | prevents catastrophic losses | ✅ |
| Draw contempt | +20–40 (win-only scoring) | ✅ |

> [!NOTE]
> These gains are not additive — they interact. A reasonable combined estimate for a Python agent with this feature set on a 5×5 board: **~2000–2100 ELO** (equivalent to a strong club player on standard chess, scaled for the simplified variant).

---

## Submission File Checklist

### ✅ Files to Submit (REQUIRED)

| File | Size | Why Required |
|------|------|-------------|
| **`agent.py`** | 139 KB | **THE submission — main engine, v7.9** |
| **`endgame_tablebase_v77.py`** | 3.6 KB | API layer: `probe_endgame_tb()`, `_solve_root_from_tablebase()` — imported by `agent.py` |
| **`endgame_tb_snippet_v77.py`** | 4,599 KB | 4.7 MB binary tablebase data — must travel with the above |

> [!CAUTION]
> If you can only submit **one file**, you must merge all three into a single `agent.py` (see merge instructions below). Without the tablebase files, the agent falls back gracefully but loses perfect endgame play.

### ✅ Files to Keep (Coursework Infrastructure — may be needed)

| File | Size | Purpose |
|------|------|---------|
| `opponent.py` | 5.7 KB | Baseline opponent (used by tournament runner) |
| `strong_opponent.py` | 6.3 KB | Strong tier opponent |
| `master_opponent.py` | 15.1 KB | Master tier opponent |
| `samples.py` | 3.3 KB | Board positions for tournament |
| `play.py` / `play_v76.py` | 7.3 KB | Game runner (coursework infrastructure) |
| `opening_book.py` | 3.5 KB | Opening book (imported by some agents) |
| `extension/` | — | Coursework chessmaker module — **DO NOT REMOVE** |
| `tests/` | — | Coursework test suite |

### ❌ Safe to Delete / Ignore (Not Needed for Submission)

| File / Folder | Size | Reason |
|--------------|------|--------|
| `agent_v69_stalemate_guard.py` | 86 KB | Old reference agent — not submitted |
| `agent_v70.py` … `agent_v76_*.py` | 98–134 KB each | Intermediate versions — superseded |
| `endgame_tablebase.py` | 3.6 KB | Duplicate of `endgame_tablebase_v77.py` |
| `endgame_tb_snippet.py` | 4,599 KB | Duplicate of `endgame_tb_snippet_v77.py` |
| `run_tournament_v78.py` | 9.2 KB | Dev tool only |
| `check_v77.py` | 2.8 KB | Dev pre-flight only |
| `ui_server.py` | 31.7 KB | Debug UI only |
| `start_ui.bat` / `stop_ui.bat` | 1.4 KB | Debug UI only |
| `V78_TOURNAMENT_RESULTS.json` | 5.2 KB | Evidence / keep for report |
| `tournament_stderr.log` | 2.7 KB | Dev log only |
| `CHESS_FRAGMENTS_V77_FINAL_HANDOFF/` | — | Handoff folder — dev record only |
| `archive/` | **~500 MB** | All run data, old agents, benchmarks — local only |

> [!WARNING]
> The `archive/` folder contains ~500 MB of run data including `games.json` files (75 GB equivalent uncompressed). **Never submit or upload this folder.** Keep it locally as evidence.

---

## Single-File Merge Instructions (if one-file submission required)

If the coursework system only accepts **one `agent.py`**, merge the three files in this order:

```
1. Copy endgame_tb_snippet_v77.py content → paste at TOP of merged file
   (it defines _ENDGAME_TB_DATA as a bytes literal)

2. Copy endgame_tablebase_v77.py content → paste BELOW step 1
   (it uses _ENDGAME_TB_DATA)

3. Copy agent.py content → paste BELOW step 2
   (remove the two import lines:
      from endgame_tablebase_v77 import ...
      from endgame_tb_snippet_v77 import ...
   since those are now inline)
```

Result: one ~4.8 MB `agent.py` that is fully self-contained.

---

## Final Submission Summary

```
Tournament score:  18W / 0D / 0L  (18/18, 100%)
  Baseline:        6W  0D  0L
  Strong:          6W  0D  0L
  Master:          6W  0D  0L

Engine:            v7.9-stalemate-guard-always-on
Average depth:     3.2 plies (substantive searches)
Max depth:         7 plies (endgame)
NPS:               ~75 nodes/sec (Python, no C extensions)
Endgame:           Perfect via 65-config tablebase (4.7 MB)
Estimated ELO:     ~2000–2100 (5×5 Chess Fragments scale)
Draw policy:       Draw contempt active — only wins count
```
