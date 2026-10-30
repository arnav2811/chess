# Chess Fragments Agent — Development Changelog
## Version history: v5.5 to v7.1 (experimental)

**Project:** COMP2321 Chess Fragments — 5×5 adversarial-search agent  
**Record updated:** 30 October 2026  
**Purpose:** Preserve the engineering history, explain why changes were made, record regressions and rejected ideas, and distinguish measured results from claims that still need reproduction.

---

## Evidence and interpretation

This is a reconstructed engineering changelog based on the available development record, version-specific reports, conversation exports, and the 30 October 2026 v6.9-v7.0 head-to-head output. It is **not a source-code audit**: the exact local source snapshots for every historical version were not available together for line-by-line comparison.

Labels used below:

- **Reported implementation** — described as implemented in a version-specific development record or source header.
- **Reported benchmark** — a result recorded in the development history; not necessarily independently reproducible now.
- **Verified current test** — directly present in the 30 October 2026 head-to-head files.
- **Proposal / investigation** — considered, but not established as part of the engine.
- **Unknown** — the available record does not establish the exact implementation or version boundary.

Do not treat every feature in this document as present in every later version. In particular, some experiments were reverted, selectively retained, or rebuilt from an earlier baseline.

## Executive version table

| Version | Main development theme | Important result / status |
|---|---|---|
| v5.5 | Tactical reliability: TT move-coordinate fix, bounded quiescence, frontier futility, context-aware pawn scoring | Reported 4.5/6 vs depth-5; first reported White wins in that series |
| v5.6 | Clock management, anti-stalemate king mobility, two-ply opening responses, aspiration calibration; tablebase experiment removed | Reported 6/6 baseline and 15/18 in one later three-tier snapshot; other snapshots differ |
| v6.0 | Aggressive forward pruning experiment: reverse futility, razoring, improving heuristic, stronger LMR | Reported severe regression and clock exhaustion; rolled back |
| v6.1 | Search-driver continuation / cleanup | Exact change list is incomplete in the available record |
| v6.2 | Bounded low-mobility extension | Controlled experiment; prior reported baseline 15/18, three losses as Black |
| v6.3 | Bounded quiet-check quiescence and tactical classification | First prototype failed; controlled rebuild from v6.2 narrowed the check search |
| v6.4 | Rebuild from a known candidate; book, root safety, symmetry TT and evaluator changes | Reported 13/18; regression against the v6.2 baseline |
| v6.5 | Regression-safe tactical candidate rebuilt from v6.2 | Focused tests reported; full playing-strength result not established |
| v6.6 | Stronger tactical/anti-loss baseline | Reported 16/18; 9/9 White, 7/9 Black |
| v6.7 | Threat-Shadow root sweep and 16-entry static opening book | Reported 15/18; two known bait-pawn traps addressed but new losses appeared |
| v6.8 | Selective opening patch: retain only two defensive book entries; remove Threat-Shadow sweep | Reported 17/18 in later log; one high-material king-stalemate loss remained |
| v6.9 | Targeted high-material king-stalemate guard | Original report kept v6.8 as rollback pending full test; later v6.9 was used as incumbent in v7.0 head-to-head |
| v7.0 | Depth-10-labelled search candidate / selective search tuning | Passed a separate 18-game diagnostic as reported; lost 4–6 to v6.9 in the 10-game paired head-to-head |

---

# Detailed chronology

## v5.5 — Tactical reliability breakthrough

**Theme:** Repair search correctness and address tactical horizon problems without reintroducing the earlier expensive search behaviour.

Changes recorded:

1. **Transposition-table move-coordinate correction.** Earlier TT entries stored a move-list index. Since move ordering changes between searches, an index could point to a different move later. The reported fix stored exact from/to coordinates and matched them against the current legal-move list.
2. **Bounded capture quiescence search.** Added a capture-focused leaf extension with a stand-pat score, a two-ply bound and delta pruning. The intent was to avoid evaluating immediately after an unresolved capture sequence.
3. **Frontier futility pruning.** At depth one, quiet moves estimated to be clearly below alpha could be skipped. This was intended to reserve computation for promising lines.
4. **Context-aware pawn restraint.** White's early pawn-advance bonus was reduced to limit overextension; Black retained stronger counter-attacking pawn incentives.
5. **Retained the classical search foundation.** Negamax, iterative deepening, alpha-beta/PVS, TT and existing move-ordering techniques remained the core.

**Reported result:** 4 wins, 1 draw and 1 loss (4.5/6) against the depth-5 opponent, compared with 2.5/6 for v5.4 in the earlier six-game comparison. The record describes this as the first version to secure White wins against that opponent. These figures are historical reports, not a fresh reproduction.

**Lesson:** Search correctness and tactical stability mattered more than nominal depth. A TT move must be represented independently of a transient move-list ordering.

## v5.6 — Clock-aware clean-up and compact engine

**Theme:** Improve conversion and game-clock survival without replacing the v5.5 search core.

Changes recorded:

1. **Dynamic per-player game-clock budgeting.** The engine adjusted its per-move budget based on elapsed game time and an estimate of remaining moves, rather than spending a fixed maximum on every move.
2. **Anti-stalemate king-mobility gradient.** Added a cheap positional term based on the number of escape squares available to each king. The custom game treats having no legal moves as a loss, so king confinement is strategically important.
3. **Two-ply opening responses.** The recorded opening cache/book covered the first two plies rather than only the initial move.
4. **Aspiration-window calibration.** The reported aspiration window was widened to ±250 centipawns to reduce repeated root re-searches after large tactical score swings.
5. **Tablebase experiment was removed from the lean build.** A retrograde tablebase covering up to four pieces was generated and embedded in an experimental build, but the later ablation record reports zero activations in the 18-game suite. The payload was therefore removed from the compact search/evaluation build.

**Reported results:** The historical changelog reports a clean 6/6 baseline result and a 15/18 result in a later three-tier snapshot. Other contemporaneous records contain different 18-game scoreboards (including 14W/4D/0L and 15W/0D/3L). These must remain separate snapshots; do not combine them or present one as independently verified without the corresponding raw logs and exact source hash.

**Tablebase caveat:** The tablebase's existence as an experiment is recorded. Its claimed competitive benefit is not established. Later records also flag an incomplete adapter/data-file dependency and inconsistent activation claims.

**Lesson:** A theoretical endgame feature has no practical value if relevant positions are not reached. Measure activation rate, probe cost and match impact before retaining large generated data.

## v6.0 — Aggressive forward-pruning regression

**Theme:** Import stronger-engine selective-pruning ideas in an attempt to increase nominal depth.

Changes recorded:

- Reverse Futility Pruning (RFP).
- Razoring.
- An improving-position heuristic affecting pruning margins.
- More aggressive / multi-ply Late Move Reductions.

**Reported outcome:** A sharp regression against the depth-5 opponent. The historical comparison records a fall to 1.5/6 points in one stress-test snapshot, with clock exhaustion in games that earlier versions had converted.

**Diagnosis recorded:** On the compact 5×5 board, tactical threats and terminal nets can arise very quickly. Forward pruning incorrectly discarded lines that contained forcing mates or terminal mobility changes. This created a misleading increase in nominal depth while reducing tactical reliability. The engine then spent more time searching without finding the decisive line and risked exhausting the overall game clock.

**Action:** The aggressive RFP/razoring/improving stack was rolled back. v5.5/v5.6-style conservative search was restored.

**Lesson:** A deeper reported search is not necessarily a stronger search. Selective pruning must be validated against tactical and terminal positions, not accepted because it increases depth.

## v6.1 — Search-driver continuation

The available v6.2 report refers to v6.1 as already having a search driver with no decisive-score/runaway-lead early exit; its only completed-iteration early exit was the forced-mate stop. The precise v6.1 change list is not preserved in the material reviewed here.

**Status:** Keep this entry deliberately incomplete. Do not invent a feature list or attribute later v6.2+ changes to v6.1.

## v6.2 — Bounded low-mobility extension

**Starting point:** v6.1 search.

Change recorded:

- Retained the existing one-legal-move extension, with a ply cap.
- Added a one-ply extension when a node had exactly two legal moves, remaining depth was at least three, and the node was within the first eight plies.
- No material values, evaluator weights, opening entries, terminal scoring or time-budget logic were intentionally changed.

**Motivation:** Low-mobility positions on a 5×5 board can be tactically sensitive, particularly because stalemate is a loss. The extension aimed to see one move further in constrained positions without extending every node.

**Reported baseline:** The v6.2 comparison record gives 15/18, with all three losses as Black and losses concentrated against stronger opponents.

**Evidence:** The v6.2 change note records compilation and stub-based evaluator tests. It explicitly says a full 18-match tournament was still required to establish playing strength.

## v6.3 — Controlled quiet-check rebuild

**Problem:** Capture-only quiescence can miss quiet checks and mating threats just beyond the nominal search horizon.

The first broad prototype reportedly expanded too much and failed badly. The controlled rebuild was based directly on v6.2 and narrowed the new search:

- Kept the v6.2 two-legal-move extension.
- Added a bounded quiet-check extension in quiescence, only when no capture/promotion candidates remained.
- Used a geometric prefilter to identify plausible checks before cloning and confirming child positions.
- Capped the number of candidate quiet checks per quiescence node.
- Classified direct quiet checks as tactical for LMR/futility decisions.
- Disabled depth-one frontier futility pruning at eight pieces or fewer.

**Validation recorded:** Compilation, evaluator invariants and geometric check-prefilter tests passed in the authoring environment.

**Strength status:** No verified full tournament result for the controlled rebuild was recorded in its changelog. The earlier failed prototype and the controlled rebuild must not be conflated.

## v6.4 — Multi-change rebuild and regression

**Starting point:** The exact user-uploaded best candidate described as a v6.0-source build, not simply the latest version number.

Changes recorded in the v6.4 changelog:

- Backtracked three losses from an uploaded 18-game diagnostic.
- Embedded the existing 16-entry opening book with `Pawn_Q` name normalisation.
- Added a time-bounded root verifier for immediate opponent wins, including stalemate losses.
- Canonicalised TT keys under horizontal reflection and normalised best-move coordinates.
- Made frontier futility pruning check-safe and disabled LMR in checked nodes.
- Added nonlinear low-mobility pressure and optional tablebase adapter calls.
- Replaced random fallback selection with deterministic tactical move ordering.

**Reported outcome:** The v6.5 regression report says the v6.4 run scored 13 wins and 5 losses, compared with the v6.2 report's 15 wins and 3 losses. The report attributes the regression risk to bundling multiple changes, including evaluator-weight changes and a symmetry TT rewrite, rather than isolating one variable.

**Important caveat:** The v6.4 report itself says the tablebase data snippet was missing, so exact tablebase probing was inactive in that environment.

**Lesson:** Do not bundle evaluator retuning, TT representation changes, opening changes and safety logic into one experiment if you want to know what helped.

## v6.5 — Regression-safe tactical candidate

**Starting point:** Rebuilt directly from v6.2 to preserve a known baseline.

Changes recorded:

1. Preserved v6.2 evaluator weights and core search; avoided the v6.4 symmetry-TT rewrite and broad post-search policy changes.
2. Used coordinate-based piece-position signatures for the 16-entry opening book, with legal-move validation before returning a book move.
3. Corrected quiescence terminal handling: check for no-legal-move terminal states before stand-pat or delta-pruning returns.
4. Disabled depth-one futility pruning close to the root to reduce the chance of pruning quiet terminal tactics.

**Validation recorded:** Compilation, focused opening-book and quiescence tests, and inherited evaluator invariants passed.

**Strength status:** The report explicitly retains v6.2 as the baseline and requires the same 18-game suite before promotion. No full v6.5 playing-strength result is established in the reviewed record.

## v6.6 — Stronger measured baseline

The v6.7 report identifies v6.6 as the measured baseline:

- 16/18 overall.
- 9/9 as White.
- 7/9 as Black.
- The two reported losses were both as Black against the depth-5 Strong opponent: sample0 and sample2.
- Both games reportedly began with Black accepting an offered bait pawn and then losing on ply 8.

The available reports describe v6.6 as containing entropy-guided anti-loss / terminal-safety work and bounded quiet-check search inherited from the preceding development line. The exact complete v6.6 source diff is not present in the reviewed material, so this description is not a substitute for a code audit.

**Lesson:** The losses were concentrated and diagnosable. The next experiment should target the two opening traps rather than globally retune the evaluator.

## v6.7 — Threat-Shadow root sweep and static opening book

Changes recorded:

1. Embedded all 16 supplied static opening entries using normalised piece names and coordinates, including the custom `Pawn_Q` type.
2. Validated each opening move against the legal-move list before returning it.
3. Added a **Threat-Shadow Root Sweep**: after the main search, profile forcing opponent replies (captures, promotions and geometrically plausible checks) after up to three leading root candidates.
4. When root scores were close or the position volatile, re-searched candidates one ply deeper at a common depth.
5. Replaced the main choice only for a mate-loss distinction or a large score improvement; bounded the extra work by the move deadline.

**Reported outcome:** v6.7 scored 15/18, down from v6.6's 16/18. The two known bait-pawn openings were addressed, but the report associates the broader book/root-sweep experiment with new Strong and Master losses.

**Lesson:** A safety sweep can be useful, but broad opening coverage and extra root work can introduce regressions. Preserve only changes with isolated evidence.

## v6.8 — Selective opening patch

**Starting point:** v6.6 core, not the full v6.7 experiment.

Changes recorded:

- Retained exactly two defensive opening responses from v6.7:
  - sample0 after White's e-pawn push: `(3,1) -> (3,2)`.
  - sample2 after White's a-pawn push: `(1,1) -> (1,2)`.
- Excluded two other v6.7 opening entries associated with new losses.
- Removed the Threat-Shadow root sweep.
- Kept v6.6 evaluation, TT, PVS, LMR, entropy verification and time management unchanged.

**Reported outcome:** A later v6.8 tournament log records 17 wins, 0 draws and 1 loss (17/18). Its only reported loss was Strong/sample2 as Black, involving a high-material king move that allowed a one-reply stalemate trap.

**Lesson:** The selective patch was a better-controlled experiment than v6.7. The remaining loss was a specific terminal-safety defect, not a reason to rewrite the whole evaluator.

## v6.9 — Targeted high-material king-stalemate guard

**Motivation:** Address the single v6.8 loss. The recorded trace says Black's king moved from `(3,0)` to `(2,0)`, after which White's king moved from `(2,4)` to `(1,4)` and Black lost by stalemate.

Change recorded:

- Kept the existing low-material two-ply terminal verifier.
- Extended the bounded verifier to a selected king move in a high-material position.
- If the selected king move was proven to permit an immediate terminal loss, checked a small number of alternatives (up to three in the high-material case).
- Reserved a small part of the move budget for the post-search safety check.
- Did not change evaluation weights, core search, move ordering, TT logic or opening-book entries.

**Original report's acceptance caveat:** It explicitly said to keep v6.8 as champion until the same 18-game tournament was completed.

**Later head-to-head evidence:** v6.9 was subsequently used as the frozen incumbent against v7.0 in the 30 October 2026 paired test. This proves it was available as a benchmark opponent; it does not retroactively prove that every historical v6.9 report was independently reproduced.

## v7.0 — Depth-10-labelled candidate

**Theme:** Increase search ambition and experiment with selective search while preserving the established tactical engine.

The available project history describes the v7.0 candidate as retaining the classical foundation:

- Negamax / alpha-beta.
- Iterative deepening.
- PVS and aspiration windows.
- Transposition table and move ordering.
- Quiescence search.
- Selective extensions and reductions, including LMR.
- Frontier futility pruning and other bounded selective-search logic.
- Hand-coded positional/tactical evaluation and terminal-safety behaviour.

The precise complete diff from v6.9 is not available in the reviewed record. The label “depth10” is a target/configuration label, not evidence that depth 10 was reached in live games.

**Separate diagnostic:** The development history reports an 18/18 result for a v7.0 diagnostic suite. That is a limited fixed-suite result, not proof that v7.0 is stronger than v6.9.

**30 October 2026 paired head-to-head — verified from uploaded output:**

- 10 games, five colour-reversed pairs, same board and seed within each pair.
- 8 worker processes.
- 14-second per-move budget and 300-second per-player game clock.
- v7.0: 4 wins, 0 draws, 6 losses (40% score).
- v7.0 as White: 3 wins, 2 losses.
- v7.0 as Black: 1 win, 4 losses.
- Board results: sample0 1–1; sample1 0–2; sample2 1–1; sample3 1–1; sample4 1–1.
- No runner errors.
- v6.9: 181,899 nodes over 137 recorded moves; weighted average depth 3.241; maximum depth 7.
- v7.0: 188,622 nodes over 136 recorded moves; weighted average depth 3.177; maximum depth 7.

**Interpretation:** v7.0 searched about 3.7% more nodes but did not improve the result in this sample. It failed both games on sample1 and had a poor Black-side result. Ten games are not enough to estimate a stable strength difference, but the result is sufficient to withhold promotion and investigate the losses.

**Current decision:** v6.9 remains the champion; v7.0 remains an experimental candidate.

---

# Cross-version lessons

1. **Correctness before depth.** TT move identity, legal-move validation, terminal scoring and game-state isolation must be correct before search optimisations can help.
2. **The 5×5 variant changes the trade-offs.** Small-board tactical density, the custom Right piece, and stalemate-as-loss make standard-chess pruning assumptions dangerous.
3. **Quiescence must be bounded.** Capture-only search addresses some horizon effects; quiet-check handling can help, but broad checking expansions can consume the entire deadline.
4. **Pruning must be variant-aware.** v6.0 demonstrated that more nominal depth can coexist with worse play.
5. **Opening responses should be selective and evidence-based.** v6.7's broad book/root sweep regressed; v6.8 retained only two targeted responses.
6. **Terminal safety deserves explicit treatment.** In this game, no legal moves is a loss even when the king is not in check. Stalemate traps are tactical wins, not draws.
7. **Clock and lifecycle correctness are strategic features.** Per-player clock accounting and clean state reset for both colours are essential.
8. **Keep an immutable champion.** Every candidate should be tested against a frozen source hash and a fixed suite.
9. **Separate benchmark speed from playing strength.** More workers increase tournament throughput; they do not make an individual search stronger and may reduce per-process CPU availability.
10. **Do not claim Elo from these custom-opponent samples.** The opponents do not have independently calibrated ratings, and this is a custom 5×5 variant.

---

# v7.1 — Adaptive Tactical Hybrid (experimental; not promoted)

**Starting point:** the uploaded v6.9 champion, verified by canonical source hash `df5cfb7305e8374ed45b6a862e6934cf0f3168e7c7eca9b1c18e9cfd517e08bd`. The uploaded file's opening comment still says v6.6, but the file bytes match the audited v6.9 champion. The original champion file is preserved separately as `agent_v69_frozen_overnight.py`.

**Motivation:** The 30 October paired head-to-head gave v7.0 a 4W/0D/6L result against v6.9. Its extra root-driver changes did not translate into a win. The next experiment should add tactical decision support without replacing the proven alpha-beta search or introducing a heavyweight neural dependency.

### Changes implemented in the v7.1 candidate

1. **Retained the classical core.** Negamax, alpha-beta/PVS, iterative deepening, aspiration windows, TT, LMR, the hand-coded evaluation, terminal-loss guard, two selective static opening replies and own-clock management remain the foundation.
2. **Root-PV ordering.** If the root has no TT entry, carry forward the best move from the previous completed iteration. The TT/PV preference is a separate sort tier, so a large accumulated history score cannot outrank it.
3. **Root aspiration fail-high cutoff.** Stop scanning additional root moves after a beta cutoff; widen the aspiration window and re-search as required.
4. **Bounded quiet-check quiescence beside captures.** The prior v6.9 q-search considered quiet checks only when there were no captures. v7.1 also checks at most one quiet-check candidate when captures exist (at most two when the capture frontier is quiet), only within the existing q-depth/check-budget and near-root limits. A geometric prefilter proposes checks; a cloned child is verified with the agent's check detector before it is searched.
5. **Optional root PUCT/MCTS probe.** A small policy-guided PUCT tree is run only after a completed classical root iteration, only when root scores are ambiguous (normalised entropy threshold 0.38), and only among up to four legal moves within 180 centipawns of the classical best. It is capped at 28 simulations, depth 4 and 0.18 seconds maximum, with a stricter time slice derived from the existing safety reserve. It may only overturn the classical move when the challenger has at least two extra visits and its backed-up value is not materially worse. The terminal-loss verifier still runs afterwards.
6. **Adaptive risk priors.** The PUCT policy uses handcrafted priors, not a neural network. When the top root score says the side is behind (≤−180 cp), the prior is more willing to investigate forcing checks, promotions and captures (“controlled complication”). When ahead (≥+180 cp), it prefers sound exchanges over speculative captures (“conversion”). Near equality it stays balanced. These are priors, not overrides of adversarial backups or tactical proof.
7. **Deterministic fallback.** Replace random legal-move fallback with stable tactical move ordering. This improves reproducibility and makes failure analysis easier.
8. **Iteration and PUCT instrumentation.** Record completed depth/node/time/score per iteration, aborted depth/node counts, whether PUCT ran, simulation count, time, policy mode and whether it changed the move.

### Why no neural network in v7.1?

The user proposed a Komodo Dragon / neural-policy-inspired direction. v7.1 implements the search-side idea first: PUCT with explicit handcrafted policy priors and a value from the existing evaluator. It does **not** train or run a neural network. No self-play dataset, held-out positions, calibration evidence or acceptable inference-latency measurement is yet available. A small policy/value model is therefore a v7.2 research option, not something to bolt onto this candidate without evidence.

### Validation completed in this authoring environment

- Python compilation passed for the v7.1 agent, its test file and the v6.9-v7.1 tournament runner.
- Six structural unit tests passed. They exercise stable softmax priors, root-entropy ordering, PUCT returning a legal root move without mutating the root, skipping decisive root positions, adaptive risk-prior behaviour and the no-legal-move-is-a-loss leaf rule.
- The paired runner's source-hash verifier was checked against the frozen v6.9 copy and v7.1 candidate; both hashes matched after canonicalising CRLF/LF.
- The runner's 10-game paired schedule builds correctly.

**Not validated here:** the coursework `chessmaker` package is absent from this environment. The v7.1 candidate has not been executed on a real ChessMaker board, has not played an actual match in this environment, and has no measured win-rate or strength claim. Passing mock-tree tests does not prove chess strength or all rule/API interactions.

### Candidate source fingerprint

`agent_v71_adaptive_tactical_hybrid.py` SHA-256: `488b051b3dce2e49f3b883a16dc12eddaba31510a0596bde7b83247c933865de`.

### Acceptance rule

- Keep v6.9 frozen and unchanged.
- Run the 10-game colour-reversed pilot with the supplied `head_to_head_v69_vs_v71.py` runner (8 workers by default).
- Inspect PUCT activation, per-move times, aborted iterations, terminal outcomes and every paired result. If PUCT rarely activates, do not increase its budget blindly; first inspect root entropy and candidate score spread.
- Only after the pilot has zero errors and no obvious clock pathology, run 40 or more games, then a larger suite if the evidence remains promising.
- Promotion requires a repeatable paired improvement across colours and boards, no increase in terminal-safety failures/timeouts, and an ablation comparing v7.1 with PUCT disabled. v7.1 is an experiment, not the new champion.

### Next research branch: v7.2 (proposal only)

A compact policy/value model may be trained offline from position records containing board state, legal moves, principal variation, search score and terminal outcome. Its first use should be move ordering / PUCT priors, not replacing the value function or terminal checks. It must be evaluated on held-out positions and under a strict inference-time budget. If it costs enough time to reduce completed alpha-beta depth or creates clock failures, reject it.

## Source trail used for this reconstruction

The following project records were available and informed this changelog:

- Historical `Pasted markdown (2)(2).md` — detailed v0–v5.6 chronology, including v5.5, v5.6, v6.0, tablebase experiment and rejected techniques.
- `AGENT_V62_CHANGELOG.md` — bounded low-mobility extension.
- `AGENT_V63_CHANGELOG.md` — controlled quiet-check rebuild.
- `AGENT_V64_CHANGELOG.md` — v6.4 multi-change rebuild.
- `AGENT_V65_REGRESSION_REPORT.md` — v6.4 regression and v6.5 controlled rebuild.
- `AGENT_V67_THREAT_SHADOW_REPORT.md` — v6.7 opening book and Threat-Shadow root sweep.
- `AGENT_V68_SELECTIVE_BOOK_REPORT.md` — v6.8 selective opening patch.
- `AGENT_V69_STALEMATE_GUARD_REPORT.md` — v6.9 targeted high-material king-stalemate guard.
- 30 October 2026 `games.json`, `summary.json`, `games.csv`, `move_metrics.csv` and `manifest.json` — v6.9-v7.0 paired head-to-head; plus the v7.1 candidate source, six structural tests and new v6.9-v7.1 runner.

**Final evidence note:** Where the source records disagree, this changelog preserves the disagreement instead of manufacturing a single clean performance narrative. Update entries only when the exact source file, version marker, hash and raw test output are available.
