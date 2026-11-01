# Chess Fragments v7.6 — Exact Tablebase Engine

**Build ID:** `v7.6-exact-tablebase`  
**Release type:** nomenclature-only release of the validated v7.5 R2 code.  
**Important:** the engine search and evaluation logic is unchanged from the preceding R2 build. No new strength or speed claim is made by renaming it v7.6.

## What is included

- `agent_v76_exact_tablebase.py` — engine candidate.
- `endgame_tablebase.py` and `endgame_tb_snippet.py` — exact retrograde tablebase adapter and embedded 65-configuration data.
- `agent_v74_tactical_guard.py` — v7.4 comparison baseline (installer preserves an existing local copy).
- Paired-colour v7.4 head-to-head and 18-game tiered tournament runners.
- Human-play launcher, ChessMaker smoke test, offline regressions, historical 600-game tablebase corpus, and TT-key microbenchmark.
- PowerShell installer and hard-gated validator.

## Install

1. Keep your existing project and champion files unchanged. Back up or commit the project first.
2. Extract `V76_EXACT_TABLEBASE_PACKAGE.zip` into a child folder of your existing ChessMaker project, for example `_v76_release`.
3. Open PowerShell in the existing project root and run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\_v76_release\install_v76.ps1
```

The installer preserves `agent.py`, v6.9, v7.4, historical results, existing opponent/sample files, and existing extension helpers. It copies only the v7.6 candidate and release support files; it adds extension helpers only if missing.

Keep these three files together in the project root: `agent_v76_exact_tablebase.py`, `endgame_tablebase.py`, and `endgame_tb_snippet.py`.

## Validate before tournaments

From the project root, run:

```powershell
.\validate_v76.ps1
```

This compiles the candidate and runners, tests the basic K+Q tablebase probe, validates all 555 distinct historical endgame states, runs the search-control regressions and TT-key microbenchmark, then attempts a live ChessMaker smoke test. The script stops immediately if any check fails.

Only after the smoke test and every earlier check pass, run:

```powershell
.\validate_v76.ps1 -RunTournament
```

This adds the 10-game paired-colour v7.4 comparison and the 18-game three-tier diagnostic tournament. Results use new filenames and do not overwrite previous evidence:

- `V76_V74_H2H_10.json`
- `V76_TOURNAMENT_18_RESULTS.json`
- `V76_TOURNAMENT_18_METRICS_SUMMARY.json`
- `V76_TT_HASH_MICROBENCH.json`

## Play against v7.6

```powershell
python .\play_v76.py --side white --board sample0
python .\play_v76.py --side black --board sample0
```

## Evidence and limitations

The previous R2 offline regression suite passed: all 65 tablebase configurations loaded; the basic decisive K+Q probe passed; all 555 unique historical 3-/4-piece states extracted from the 600-game v7.4 corpus matched their stored WDL labels (240 WIN, 227 LOSS, 88 DRAW); exact DRAW scoring, root WDL choice/fallback, LMR/history safeguards, low-mobility futility gating, and expired-deadline fallback passed. Fresh packaging-time rerun (5 runs × 200,000 calls) measured medians of 1.1493s for the legacy sorted-tuple key and 0.9050s for the v7.6 frozenset key: 21.26% lower median key-construction time and 26.99% higher key throughput in this synthetic microbenchmark. This is not a whole-engine speedup claim.

ChessMaker was unavailable in the build environment, so no live v7.6 move or v7.6 tournament has been verified here. The earlier v7.5 candidate's 10-game H2H and 18-game results are historical evidence about that earlier code, not results for this release. v7.6 must earn promotion through fresh Windows validation.

## Versioning note

This release changes the version label from v7.5 R2 to v7.6 and updates imports, scripts, log labels, build IDs, output filenames, installer, validator, and documentation. It deliberately does not change search, pruning, move ordering, evaluation weights, tablebase semantics, time management, or any other engine behaviour.
