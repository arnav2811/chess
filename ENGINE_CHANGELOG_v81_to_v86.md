# Chess Fragments Engine — Development Changelog
## v8.1 → v8.6 | COMP2321 Coursework

> [!IMPORTANT]
> **Current submission:** `agent.py` = **v8.4-tactical-kings** — the only version that achieved 10W/0D/0L.
> All changes are relative to the v8.0 proven base (`agent_v80_clean_backup.py`).

---

## Baseline: v8.0 — `v8.0-final-submission`

The foundation everything builds on. Established the core architecture that all later versions preserve.

**What it had:**
- Iterative deepening Negamax + Alpha-Beta + PVS (Principal Variation Search)
- Aspiration windows (±250 cp, auto-widening on fail)
- Transposition Table (200k entries, Zobrist keys)
- MVV-LVA capture ordering
- Late Move Reductions (LMR) — dynamic 0/1/2-ply
- Quiescence search (captures + promotions + bounded check evasions)
- Check extensions + low-mobility extensions
- King safety: `zone_pressure × 10`, checker `+135`, cage `+78`
- Self-learning opening book (plies 1–2), 2 static entries
- DRAW_CONTEMPT = 60,000 (draws treated as losses)
- Retrograde endgame tablebase (65 ≤4-piece configs)
- Repetition avoidance

**Result:** Beat Baseline consistently; had known weaknesses against Strong opponents.

---

## v8.1 — SEE Capture Ordering

**Hypothesis:** Static Exchange Evaluation (SEE) would rank captures more accurately than MVV-LVA by accounting for recaptures, reducing the number of losing exchanges the engine considers first.

**What was tried:** Replaced MVV-LVA with a full SEE ordering pass on all captures.

**Result:** ❌ **REGRESSION — 17/18 test failures**

**Root cause analysis:**
SEE is computed at the **root move-ordering level** before the search tree has resolved tactical consequences. On a 5×5 board, positions are compact enough that the existing search + MVV-LVA already finds the right captures quickly. SEE introduced ordering noise that disrupted move ordering for non-capture moves, broke the history/killer heuristic calibration, and caused the search to explore different branches than the carefully tuned v8.0 baseline.

**Lesson learned:**
> *On a 5×5 board with short tactical sequences, the search itself proves capture quality faster than a static exchange estimator can approximate it. MVV-LVA at a fraction of the cost is the right tool here. SEE is permanently banned.*

**Permanent rule:** Never reintroduce SEE. `agent.py` uses MVV-LVA only.

---

## v8.2 — `v8.2-tb-draw-deep-stalemate-guard`

**What was added:** Deep stalemate guard — a one-reply terminal-safety veto that runs at both giving and receiving stalemate risk. The engine explicitly checks whether a candidate move leaves the opponent in a stalemated position (which is a loss for the stalemating side in this variant) before committing.

**Key insight that motivated this:** In the Chess Fragments variant, stalemate is a *loss* for the side that creates it, not a draw. Standard chess engines treat stalemate as draw and may happily walk into it. The guard prevents the engine from accidentally stalemating itself or walking the opponent into a "free" stalemate draw.

**Also included:** Improved draw detection robustness in the tablebase section. Draws via fivefold repetition were being handled inconsistently; this version ensured DRAW_CONTEMPT was applied uniformly.

**Result:** ✅ Passed regression tests. Improved reliability in endgame positions with few moves.

**Lesson learned:**
> *Domain-specific terminal conditions (stalemate = loss, not draw) need explicit guards. Standard chess engine assumptions are dangerous in Chess Fragments. Always audit game rules against the actual library implementation.*

---

## v8.3 — Tactical midgame and search improvements

**What was added over v8.2:**
- Refined aspiration window retry logic (directional widening before full-window fallback)
- Improved LMR guard conditions (tactical moves, checks, promotions exempt from reduction)
- Bounded LRU transposition table (no wholesale flush — aged eviction instead)
- Side- and piece-aware killer/history keys (coordinate-only keys aliased across colours, causing misdirected move ordering)
- Completed-iteration fallback when time expires mid-depth

**Result:** ✅ Beat Baseline. Reached the start of this engineering session.

**What was still missing:**
- Opening book only had 2 entries — left Black exposed to common White gambits
- King safety weights were too conservative: a check threat was `+135 cp` but the engine could still be lured into allowing checks
- No penalty for the king walking forward in the middlegame (PST alone gave −10 cp, insufficient)

**Lesson learned:**
> *Good search mechanics are necessary but not sufficient. A tactically correct engine still needs evaluation terms that give it the right strategic instincts — especially in the opening where the search tree hasn't deepened enough to see consequences.*

---

## v8.4 — `v8.4-tactical-kings` ⭐ THE CHAMPION

**Tournament result: 10W / 0D / 0L — Baseline 6/6 · Strong 4/4**

This is the version that actually won all 10 games. Every change was driven by a specific observed failure mode.

### Change 1: Opening book expanded to 5 entries

**Before:** 2 static entries, only covering sample0 (h-pawn) and sample1 (a-pawn) Black responses.

**After:** Added 3 more entries covering the most tactically decisive early moment in all 3 sample boards — the moment White advances the centre pawn and Black can recapture immediately.

```
sample0: Black (3,1)→(2,2) recaptures White centre pawn
sample1: Black (3,1)→(2,2) recaptures White centre pawn
sample2: Black (3,1)→(2,2) recaptures White centre pawn
```

**Why it mattered:** The centre pawn recapture is played in `depth=0, time=0.01s` — instantaneously, burning zero clock. Without the book entry the engine spent 10+ seconds searching for the same move the book gives immediately, and occasionally misidentified the best recapture under time pressure.

**Lesson:**
> *A 5-entry opening book isn't "cheating" or hardcoding — it's recognising that some positions have objectively best moves that the engine can find instantly. The book saves clock budget and eliminates variance on critical opening moments.*

### Change 2: King forward exposure penalty

**Before:** King walking forward in middlegame was penalised ~−10 cp by the PST. Completely inadequate.

**After:** Explicit, phase-gated penalty:
```
1 rank forward  → −45 cp
2 ranks forward → −85 cp
3 ranks forward → −140 cp
4 ranks forward → −200 cp
(only fires when phase > 5, i.e. not in a pure endgame)
```

**Why it mattered:** On a 5×5 board a king that walks to rank 2 or 3 is geometrically in range of every enemy piece. The search needs to see 4–5 moves ahead to discover the resulting checkmate, and at 10s/move with ~1500 nodes it was regularly getting fooled. The evaluation penalty makes the king walk immediately undesirable, so the search never chooses it even at shallow depth.

**Lesson:**
> *Evaluation must compensate for search horizon limits. If the bad outcome is 5 moves away and the search only reaches depth 3, a static penalty is the correct safety mechanism.*

### Change 3: Open-file battery bonus

**After:** When a Right or Queen is on the same file or rank as the enemy king with a clear path between them, award `+18 to +55 cp` scaled inversely by distance.

**Why it mattered:** Diagnosed a specific loss where the opponent's Right invaded the back rank unimpeded. The engine had not given sufficient weight to controlling open lines toward the enemy king. This term makes "line up on the king's file" a genuinely attractive strategic plan rather than something the engine stumbles into by accident.

### Change 4: Right open-file bonus (+20 cp)

**After:** Any Right on a file with no pawns (own or enemy) on that column scores +20 cp.

**Why it mattered:** The Right is the most powerful piece in this variant (rook + jumping knight). An open file gives it immediate invasion potential even when not directly aimed at the king. The engine needed a nudge to centralise Rights on open files rather than leaving them behind pawn chains.

### Change 5: King safety weight escalation

| Parameter | v8.3 | v8.4 |
|-----------|------|------|
| `zone_pressure` multiplier | ×10 | ×13 |
| Checker penalty | 135 | 155 |
| Cage penalty (zero safe escapes) | 78 | 88 |

**Why it mattered:** The existing weights were calibrated for an engine that had no king-forward penalty. Once the king could no longer escape forward to avoid pressure, the zone/checker/cage weights needed to be heavier to make the engine treat check threats with the urgency they deserve on a 5×5 board.

### Change 6: RFP stalemate fix (correctness)

**Before:** Reverse Futility Pruning (RFP) fired before legal move generation. If a position had no legal moves (stalemate) but a high static eval, RFP would return a good score for what is actually a losing position (stalemate = loss in this variant).

**After:** Legal move generation runs first; if no moves, return `−MATE_SCORE`. RFP only fires after confirming moves exist.

**Why it mattered:** This was a silent bug that could cause catastrophic misjudgements near stalemate positions. It didn't cause any observed failures at this point, but it was a correctness requirement.

**Overall v8.4 lesson:**
> *The five evaluation changes (king exposure, battery bonus, open-file bonus, king danger weights, opening book) all addressed the same strategic theme: on a 5×5 board, king safety and piece activity in open lines are worth dramatically more than standard chess heuristics suggest. The board is too small to absorb threats across multiple moves. Static evaluation must reflect this geometry.*

---

## v8.5 — ROLLED BACK (9W / 1D / 0L)

**What was tried:** Two new evaluation terms on top of v8.4:

### Term 1: Opening development bonus
```python
if phase >= 10:  # fires until 8 non-pawn pieces captured
    weight = max(0, phase - 9) * 2
    # reward each piece off its home rank
```
**Intent:** Address the professor's feedback — "develop pieces intelligently."

### Term 2: Pawn tension penalty
```python
if phase >= 8:
    for col in range(5):
        if col not in our_pawn_files:
            if enemy_right_or_queen on same col:
                score -= 12  # discourage premature exchanges
```
**Intent:** "Capturing isn't always best" — maintain pawn tension.

**Result:** ❌ **REGRESSION — 1 draw (fivefold repetition, 62 plies)**

The draw occurred in sample2/White vs Strong. From ply 31 onwards the engine was entirely tablebase-guided. `tb_repeat` fired repeatedly (plies 43, 53, 59…), indicating the tablebase was cycling through the same positions. In v8.4, this same game was won in 24 plies.

**Root cause diagnosed:**
The opening development bonus (`phase >= 10`) fired well into the **middlegame** (up to 8 non-pawn pieces captured). This changed the evaluation of positions that v8.4 had won cleanly, causing a different middlegame path, reaching a different endgame position that the tablebase couldn't convert — cycling into fivefold repetition.

**What was NOT the cause:**
- The tablebase itself (it works correctly)
- The RFP fix (already in v8.4)
- The opening book (unchanged)

**Lessons learned:**
> *1. `phase >= 10` is not "opening" — it fires through the entire early-to-mid transition. The correct gate for a true "opening only" term is `phase >= 14` (at most 4 non-pawn pieces captured, essentially the first 2–3 moves).*
>
> *2. The pawn tension term (-12 cp per open file with enemy major) is too broad. It fires on every open file regardless of whether the enemy piece actually threatens the king, discouraging moves that may be essential for other reasons.*
>
> *3. Any new evaluation term that changes the middlegame path risks reaching a different endgame position. Even if the new term is "correct" strategically, it can interact with the tablebase and cause a draw via repetition avoidance failure. Test the full game, not just the opening.*
>
> *4. When an engine wins 10/10 at full strength, every new feature is a liability until proven otherwise by tournament data.*

---

## v8.6 — `v8.6-opening-harmony` (In Progress / Candidate)

**Base:** v8.4 (10W/0D/0L)

**Goal:** Apply the professor's brainstorm feedback (develop intelligently, create space, piece harmony) while keeping v8.4's 10W/0D/0L intact.

**Changes over v8.4:**

### Term 1: Opening development bonus (narrowed from v8.5)
```python
if phase >= 14:  # only first 2-3 moves (≤4 non-pawn pieces captured)
    dev_weight = max(0, phase - 13) * 3   # max 15 cp at full board
    # reward each piece off its home rank
```
Key improvement over v8.5: threshold raised from 10 → 14 (fires 4× less broadly), weight per piece capped at 15 cp (vs 18 cp in v8.5 at max).

### Term 2: Piece harmony (new)
```python
if phase >= 12:
    # count non-pawn, non-king pieces per column per side
    # penalise -8 cp per extra piece stacked on same file
```
Discourages two pieces on the same column in the opening — spreads piece coverage, addresses professor's "create space" feedback.

### ~~Term 3: Forward projection~~ (REMOVED after ablation)

An earlier draft included a bonus for attacking the opponent's first 2 ranks. **Ablation result:** v8.6 won as White but **lost as Black** (sample0, 20 plies — identical game length to v8.4). The term was dropped immediately.

**What the forward projection term got wrong:**
The attack maps it used (`attacks[side][ey][ex]`) are already incorporated into mobility scoring, central control, exchange liability, and king tropism. Adding another bonus on top of the same data double-counted attacks on the opponent's back ranks, making Black overly aggressive toward White's starting position and misvaluing positions where consolidation was better than forward pressure.

**Lesson:**
> *Don't add evaluation components on top of data that is already priced into the evaluation elsewhere. The attack maps feeding the existing terms are correct — adding a separate bonus for the same attack squares creates double-counting that distorts the score asymmetrically depending on which side is to move.*

**Current ablation status:** Running v8.6 (dev bonus + harmony only) vs v8.4. Must achieve 6W/0D/0L in the head-to-head before proceeding to the full 10-game tournament.

---

## Summary Table

| Version | Build String | Key Feature | Tournament | Verdict |
|---------|-------------|-------------|------------|---------|
| v8.0 | `v8.0-final-submission` | Foundation: ID-Negamax, PVS, TT, QSearch | Baseline: W | ✅ Base |
| v8.1 | — | SEE capture ordering | 1/18 ❌ | ❌ ROLLED BACK |
| v8.2 | `v8.2-tb-draw-deep-stalemate-guard` | Deep stalemate guard, draw robustness | Baseline: W | ✅ Improvement |
| v8.3 | — | LMR refinement, TT eviction, killer keys | Baseline: W | ✅ Improvement |
| v8.4 | `v8.4-tactical-kings` | King exposure + battery + open file + king danger | **10W/0D/0L** | ✅ **CHAMPION** |
| v8.5 | — | Dev bonus (`phase>=10`) + pawn tension | 9W/1D ❌ | ❌ ROLLED BACK |
| v8.6 | `v8.6-opening-harmony` | Dev bonus (`phase>=14`) + harmony | 🔄 Testing | 🔄 Pending |

---

## Cross-Version Engineering Principles (Distilled)

**1. The board geometry is everything.**
5×5 compresses all tactical threats into 2–3 moves. Terms that matter on 8×8 (pawn chains, knight outposts, long-term planning) matter here too but at a 2–3× weight because consequences arrive faster.

**2. Test before claiming improvement.**
v8.1 and v8.5 both looked reasonable on paper. Both failed empirically. The 10-game tournament is the only valid ground truth.

**3. Evaluation terms gate on game phase.**
"Opening" = `phase >= 14`. "Middlegame" = `phase 6–13`. "Endgame" = `phase <= 5`. Never let an opening heuristic fire in the middlegame (the v8.5 error).

**4. The tablebase is both a strength and a constraint.**
Once the engine enters tablebase range, it follows probe results faithfully. Any middlegame path that reaches a different position than v8.4 found may land in a tablebase position the probe struggles to convert. Preserve v8.4's middlegame choices wherever possible.

**5. The search proves tactics; evaluation guides strategy.**
Don't add evaluation terms to handle tactics the search can already resolve. Add them only for strategic biases the search tree cannot see within its time budget (e.g., king exposure 5 moves out, long-term open-file domination).

**6. Never let a draw stand.**
DRAW_CONTEMPT = 60,000 must never be changed. Under winner-takes-all scoring, a draw is a loss. The engine must always fight.
