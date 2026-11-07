# Chess Fragments Engine — Master Engineering Audit
## v8.4 Source Audit · Strategic Assessment · Research Roadmap

---

## PRIORITY 0 — Source Identity and Champion Preservation

### File Hashes (SHA-256, first 16 hex digits)

| File | Hash | Size | Status |
|------|------|------|--------|
| `agent.py` | `4066c7399bae58a4` | 149,118 B | ✅ CHAMPION |
| `agent_v84_frozen.py` | `4066c7399bae58a4` | 149,118 B | ✅ Identical to champion |
| `agent_final.py` | `e8c70e170f4033b1` | 153,268 B | ⚠️ v8.5 (feature-flag build, NOT champion) |
| `endgame_tablebase_v77.py` | `be24166e37a43b6d` | 3,702 B | ✅ Required companion |
| `endgame_tb_snippet_v77.py` | `242855c997ac3aaa` | 4,709,674 B | ✅ Required companion |

> [!IMPORTANT]
> `agent_final.py` is **NOT** the current champion. It is the v8.5 candidate (with `_FEAT_OPENING_DEVELOPMENT` and `_FEAT_PAWN_TENSION` flags) that caused the 9W/1D regression. The true champion is `agent.py` = `agent_v84_frozen.py`.

### Version Identity Resolution

The directive correctly identified a discrepancy between source labels and feature content. The resolution:

| Claim | Reality |
|-------|---------|
| "v8.4 had 3 static opening entries" | Early v8.4 — later expanded |
| "v8.5 had 5 entries + RFP terminal fix" | Correct — but v8.5 also had dev bonus + pawn tension |
| "Current v8.4 has 5 entries + RFP fix" | ✅ CORRECT — the final build cherry-picked the structural improvements (5 entries, RFP fix) from v8.5 while keeping v8.4's evaluation (no dev bonus, no pawn tension). The ENGINE_BUILD label was not updated to reflect this. |

**True build identity:** The champion is a stabilised hybrid — v8.4 evaluation + v8.5 structural fixes. The correct internal label would be `v8.4.5-tactical-kings` but the submitted label is `v8.4-tactical-kings`.

### Champion Feature Configuration

```
ENGINE_BUILD       = "v8.4-tactical-kings"
DRAW_CONTEMPT      = 60,000
_TT_MAX_SIZE       = 200,000
_EVAL_PHASE_MAX    = 18
_CHECK_EXTENSION_MAX_PLY = 10
_SELECTIVE_OPENING_RAW = 5 entries (sample0×2, sample1×2, sample2×1)
Feature flags      = NONE (all evaluation is unconditional)
```

---

## DELIVERABLE 1 — Architecture Audit

### Search Functions (agent.py line references)

| Component | Location | Notes |
|-----------|----------|-------|
| `_negamax()` | ~L1700 | Main search; colour-flipped negamax convention |
| `_quiescence()` | ~L1600 | Captures + promotions + bounded check evasions |
| `_order_moves()` | ~L1100 | PV > MVV-LVA > Promo > Quiet-check > Killers > History |
| `_score_move()` | ~L1067 | Tiered ordering keys |
| `evaluate_for_white()` | L651 | 400-line handcrafted eval |
| `_build_evaluation_maps()` | ~L540 | Attack/mobility maps; pseudo-legal |
| `agent()` | ~L3000 | Root: opening book → tablebase → ID search |
| `iterative_deepening()` | ~L1920 | Time-controlled ID with aspiration windows |

### Key Configuration Values

| Parameter | Value | Notes |
|-----------|-------|-------|
| Aspiration window | ±250 cp | Directional widening on fail |
| RFP margin | 100 cp/ply | depth ≥ 2, in-check guarded |
| Futility margin | depth 1 only | Non-tactical exempt |
| LMR | 0/1/2-ply dynamic | Tactical/killer/history guarded |
| Check extension cap | ply ≤ 10 | |
| TT size | 200k entries | Bounded LRU |
| Opening book | ply 1–2 only | 5 static entries |

### Established Tournament Record

```
[W] Baseline | sample0 as white | WIN |  14 plies |  66s
[W] Baseline | sample0 as black | WIN |  15 plies |  66s
[W] Baseline | sample1 as white | WIN |  22 plies | 119s
[W] Baseline | sample1 as black | WIN |  17 plies |  87s
[W] Baseline | sample2 as white | WIN |  16 plies |  75s
[W] Baseline | sample2 as black | WIN |  17 plies |  99s
[W] Strong   | sample0 as white | WIN |  18 plies |  85s
[W] Strong   | sample0 as black | WIN |  19 plies | 132s
[W] Strong   | sample1 as white | WIN |  12 plies |  95s
[W] Strong   | sample2 as white | WIN |  24 plies | 144s
TOTAL: 10W / 0D / 0L
```

---

## DELIVERABLE 2 — Strategic Assessment

### Ranked Weaknesses (Confidence × Impact)

#### 🔴 CRITICAL

**W1 — Unknown self-play dynamics (undiagnosed)**

We do not know if v8.4 Black can beat v8.4 White in self-play on sample0. The ablation failures (v8.6 Black losing to v8.4 White) could be:
- A genuine regression caused by the new eval terms (v8.6 is worse than v8.4 as Black)
- An inherent positional asymmetry (Black cannot win sample0 in self-play at this strength)

**This must be diagnosed before any further evaluation changes are made.**

If Black structurally cannot win sample0 in self-play, then v8.6's Black failure is not meaningful — both v8.4 and v8.6 would draw or lose as Black. The improvement programme should then focus on **search quality**, not evaluation.

**Evidence:** Self-play diagnostic running now.

---

#### 🟠 HIGH PRIORITY

**W2 — Move ordering not measured or validated**

The current ordering `PV > MVV-LVA > Promotion > Quiet-check > Killers > History` has never been systematically measured:
- First-move beta cutoff rate (not logged)
- Rank of best move in original ordering (not tracked)
- History table effectiveness (not analysed)
- Killer move effectiveness (not analysed)

**Why it matters:** Move ordering drives the entire alpha-beta efficiency. A 10% improvement in first-move beta-cutoff rate translates to deeper search at the same time budget — which translates directly to fewer tactical mistakes.

**Proposed measurement:** Add instrumentation logging `first_move_cutoff_rate` and `best_move_rank` to the existing per-move diagnostic output.

**Risk:** Low — adding logging doesn't change behaviour.

---

**W3 — Opening book only covers plies 1–2**

After the ply-2 book move, the engine uses full search from ply 3 onward. At ply 3, the search is at depth 3–4 (the first few iterations). Critical opening decisions happen at plies 3–8 without any book guidance.

**Why it matters:** The professor said "stronger opening theory." The book handles the most critical moment (centre recapture at ply 2) but after that, the engine is on its own with limited depth.

**Proposed approach:** Extend the static opening to cover selected ply-3 responses. After White's ply-3 move in sample0 (always the same, since v8.4 plays deterministically), add Black's ply-4 best response to the book.

**Risk:** Low for ply-3 entries — they only fire once and don't affect the middlegame.

---

**W4 — Right piece evaluation may be incomplete**

The Right has rook-like AND knight-jump movement. The current evaluation covers:
- Right PST (rewards central/advanced positions)
- Open-file bonus (+20 cp per pawnless column)
- Battery bonus (line to enemy king)
- Exchange liability (attacker surplus)

What's NOT covered:
- The knight-jump mode's specific threat patterns
- Whether the Right is using its jump mobility vs rook mobility
- Outposts reachable only by jump but not by sliding

**Why it matters:** The Right is the strongest piece in this variant (700 cp). Undervaluing its jump-mode threatens could cause the engine to misplace it.

**Proposed approach:** Add a Right-specific "jump threat" term — count how many enemy pieces are reachable in one L-move by the Right. This is cheap (≤8 squares to check per Right).

**Risk:** Medium — new eval term, needs ablation.

---

#### 🟡 MEDIUM PRIORITY

**W5 — No countermove history**

The current history table learns `(piece_type, from, to) → cutoff_frequency`. Countermove history additionally tracks `(last_move) → (best_response)`, which helps order the specific response to the opponent's last move.

**Why it matters:** In the opening and middlegame, the best response to a specific opponent move is often position-independent. Countermove history captures this.

**Risk:** Low — purely additive to move ordering, doesn't change evaluation.

---

**W6 — Limited quiescence search**

Current QSearch covers: captures, promotions, bounded check evasions. It does NOT cover:
- Quiet moves that create immediate promotion threats
- Moves that set up a fork
- Moves that escape a trapped piece

**Why it matters:** Horizon effects — the search "sees" a capture but not the follow-up threat. On a 5×5 board, one-move threats are extremely common.

**Risk:** High — expanding QSearch is expensive and can cause search explosion. Any expansion needs careful bounding.

---

**W7 — No singular extensions**

When a TT move is significantly better than all alternatives (by a threshold margin), singular extension can search it one ply deeper. This finds forced continuations the engine might miss.

**Risk:** Medium-high — previously warned against in the directive as "problematic." Needs careful implementation.

---

#### 🟢 LOW PRIORITY (but interesting)

**W8 — Aspiration window parameters not tuned**

The ±250 cp initial window was set by convention. On a 5×5 board with DRAW_CONTEMPT=60,000, the typical score range differs from 8×8 chess. Too-narrow windows cause re-searches; too-wide windows reduce pruning.

**Risk:** Low — purely a performance parameter, doesn't affect correctness.

---

**W9 — Evaluation is not parameter-tuned**

Weights like king-forward penalties (45/85/140/200), PST values, battery bonus (18-55 cp) were set by human judgement and game observation. Systematic parameter optimisation could improve them.

**Risk:** Medium — SPSA or coordinate descent needs test infrastructure.

---

### Professor Recommendation Assessment

| Professor's Point | Current Engine | Gap | Proposed Fix |
|-------------------|---------------|-----|-------------|
| Good middlegame | ✅ Confirmed by tournament | — | Preserve |
| Stronger opening theory | ⚠️ 5 book entries, ply 1-2 only | Plies 3-6 unguided | Extend book or improve early eval |
| Better piece ordering | ❓ Not measured | Unknown | Add cutoff-rate logging, CMH |
| Investigate moves per piece | ⚠️ Pseudo-mobility only | No legal move counts | Targeted mobility term (expensive) |
| Space > immediate captures | ⚠️ Pawn advance bonuses exist | No explicit "space" term | Right/Queen space projection |
| Knight move consequences | ⚠️ PST handles basic placement | Jump-mode threats unmeasured | Right/Knight jump-threat term |
| Analyse opening → loss positions | ✅ Done in audit | — | Self-play diagnostic adds more data |

---

## DELIVERABLE 3 — Research Roadmap

### Tier 1: Minimal risk, high confidence

| ID | Change | Risk | Expected gain | Status |
|----|--------|------|--------------|--------|
| R1 | Extend opening book to ply 3-4 for deterministic lines | Very Low | +1-2 cp effective | 🔄 Needs self-play data |
| R2 | Add countermove history to move ordering | Low | +2-5% ordering quality | 📋 Planned |
| R3 | Log first-move cutoff rate (instrumentation only) | Zero | Diagnostic value | 📋 Planned |
| R4 | Harmony-only eval (file-stacking penalty, no dev bonus) | Low | Small positional | 🔄 Ablation running |

### Tier 2: Medium confidence, controlled risk

| ID | Change | Risk | Expected gain | Status |
|----|--------|------|--------------|--------|
| R5 | Right jump-threat term (+N cp per enemy piece reachable by L-move) | Medium | Tactical awareness | 📋 Planned post-R4 |
| R6 | Aspiration window tuning (narrow from ±250 to ±180) | Low | 5-10% fewer re-searches | 📋 Planned |
| R7 | Opening book ply 4-5 entries if self-play shows convergent lines | Medium | Early game stability | Conditional |

### Tier 3: High risk — do not attempt without T1/T2 evidence

| ID | Change | Risk | Condition for consideration |
|----|--------|------|-----------------------------|
| R8 | Null-move pruning | High | Only if thorough QSearch shows horizon effects |
| R9 | SEE capture ordering | Very High | BANNED — 17/18 regression previously |
| R10 | Neural evaluation | Very High | Beyond coursework constraints |
| R11 | Aggressive development bonus | High | All 4 previous attempts regressed |

### Tier 4: Do not implement

- Any broad "space projection" term (regressed in v8.6)
- Any per-piece legal move generation in eval (too expensive)
- Any external databases or persistent learning files
- Any pawn-tension global penalty (regressed in v8.5)

---

## DELIVERABLE 4 — Current Experiment

### Hypothesis: Harmony-Only (v8.6c)

**Weakness addressed:** W2 (move ordering → piece placement diversity)  
**Hypothesis:** A mild penalty for two non-pawn, non-king pieces on the same column discourages redundant piece stacking and encourages board coverage, without overriding tactical decisions.

**Implementation:**
```python
if phase >= 12:
    for side in (1, -1):
        col_counts = [0] * 5  # count pieces per column
        for name, x, y, ps, _ in pieces:
            if ps == side and name not in ('king', 'pawn'):
                col_counts[x] += 1
        for count in col_counts:
            if count >= 2:
                score -= side * 7 * min(2, count - 1)  # max -14cp per column
```

**Key differences from v8.6:**
- **No development bonus** (the regressive term in all previous candidates)
- **Smaller weight**: 7 cp (was 8 cp in v8.6)
- **Same phase gate**: `phase >= 12`
- Starting positions have pieces on distinct columns → zero penalty initially

**Risks:**
- Might still cause Black regression if column-stacking avoidance conflicts with an important defensive move
- Self-play diagnostic will determine if Black can win at all in self-play first

**Success criteria:** 6W/0D/0L vs v8.4 in 6-game ablation (sample0×2, sample1×2, sample2×2).

**Next step if harmony passes:** Add countermove history (R2) on top of v8.6c.

---

## DELIVERABLE 5 — Experimental Discipline Protocol

### State Management

| Label | Current File | Hash | Purpose |
|-------|-------------|------|---------|
| CHAMPION | `agent.py` = `agent_v84_frozen.py` | `4066c7399bae` | Never modified |
| CANDIDATE | `agent_v86c_harmonyonly.py` | TBD | Current experiment |
| DISCARDED | `agent_v86_candidate.py` | — | Dev+harmony, failed |
| DISCARDED | `agent_final.py` | `e8c70e170f` | v8.5 features, failed |

### Research Ledger

| Field | Entry |
|-------|-------|
| **Hypothesis** | File-stacking penalty encourages piece dispersion without overriding tactics |
| **Evidence** | No prior data; derived from positional chess principle |
| **Implementation** | `evaluate_for_white()`: +16 lines after king-exposure block |
| **Expected benefit** | Marginally better piece coordination in opening |
| **Risks** | Could conflict with defensive piece clustering; could cause Black regression |
| **Cost** | O(pieces) = O(10), negligible |
| **Experiment** | 6-game ablation vs v8.4 (90s/side) + self-play diagnostic |
| **Outcome** | 🔄 Running |
| **Decision** | 🔄 Pending |

---

## DELIVERABLE 6 — Failed Experiments Registry

| Version | Feature | Test | Outcome | Root Cause |
|---------|---------|------|---------|-----------|
| v8.1 | SEE capture ordering | 18-game | 1/18 ❌ | Move ordering noise disrupted MVV-LVA; SEE overhead wasted nodes |
| v8.5 | Dev bonus (`phase≥10`) + pawn tension | 10-game | 9W/1D ❌ | Dev bonus fired through middlegame; changed game path → different endgame → tablebase cycling → fivefold repetition draw |
| v8.6-a | Dev bonus (`phase≥14`) + harmony + projection | 6-game ablation | 3W/3L ❌ | Forward projection double-counted attack maps (already in mobility/central control); corrupted Black evaluation |
| v8.6-b | Dev bonus (`phase≥14`) + harmony | 6-game ablation | 1W/1L partial ❌ | Dev bonus incentivized Black to develop instead of best tactical move on sample0 |

**Common failure mode:** New evaluation terms that give a bonus for specific structural features (developed pieces, unstacked columns, forward squares) consistently override the engine's tactical judgement in positions where the tactical move is NOT captured by the bonus. The 15 cp dev bonus is enough to prefer developing a knight over a 10 cp tactical move.

**Distilled principle:** Any new eval term must be small enough that a 100 cp tactical refutation still dominates it. Max magnitude for opening structural terms: **5-8 cp per piece**, not 15 cp.

---

## Open Questions Requiring Self-Play Data

1. **Can v8.4 Black beat v8.4 White on sample0?**  
   → If yes: v8.6's Black failure is a genuine regression  
   → If no: v8.6's Black failure is a positional artefact; we should focus on search, not eval  

2. **What are the first 5 moves of v8.4 White on sample0?**  
   → Will determine if ply-3 book extension is feasible

3. **What is the first-move beta-cutoff rate?**  
   → Will determine if move ordering improvements are the highest-value target

4. **Does the Right ever use its jump mode?**  
   → Will determine if Right-jump-threat evaluation is worth implementing

> [!NOTE]
> Self-play diagnostic (`self_play_diagnostic.py`) is currently running. Results will determine which of Tiers 1-2 to implement next.
