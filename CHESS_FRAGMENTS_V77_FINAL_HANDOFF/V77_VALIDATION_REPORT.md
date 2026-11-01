# v7.7 validation report

Date: 2026-11-01

## Offline checks run in this build environment

| Check | Result |
|---|---|
| Python compilation for engine, adapter/data, baseline, tests, runners and player | PASS |
| Basic exact tablebase regression | PASS — 65 configurations; decisive K+Q returns `+95000` |
| Historical endgame corpus | PASS — all 555 unique states; 240 WIN, 227 LOSS, 88 DRAW |
| Exact DRAW semantics | PASS — legacy material contempt cannot alter `DRAW = 0` |
| Search-control regressions | PASS — history ageing, conservative LMR, low-mobility futility, TT key, root tablebase and fallback |
| v7.7 high-material terminal-loss guard | PASS — non-king path is checked and a verified safe alternative is selected in controlled tests |
| v7.7 equal-WDL repetition preference | PASS — lower-repetition child is preferred when exact WDL is tied |
| Exact-WDL priority | PASS — repetition preference never overrides a superior WDL score |
| TT-key microbenchmark | PASS — five runs of 200,000 calls |

### TT-key microbenchmark (final rerun)

- Legacy sorted-tuple median: **1.1230 seconds**
- Candidate `frozenset` median: **1.0648 seconds**
- Relative improvement for this isolated key-construction operation: **5.46%**
- Median samples: five runs, each with 200,000 synthetic 18-piece board keys.

This is not a whole-engine NPS or playing-strength result. Microbenchmark results vary between runs; the final rerun above supersedes earlier preliminary figures.

## Live integration status

The live smoke test was attempted and stopped at:

```text
ModuleNotFoundError: No module named 'chessmaker'
```

ChessMaker is absent from this build environment. Therefore no live v7.7 move, live clock check, or v7.7 tournament has been verified here. Run `validate_v77.ps1` in the actual Windows project. Do not run the tournaments unless the entire validation script, including the live smoke test, passes.

## Scope of v7.7 regression proof

The v7.7-specific tests use controlled board/move stubs to exercise guard-policy branching and root-tablebase tie-breaking without ChessMaker. They verify that the high-material/non-king bypass is gone, that an unsafe selected move is replaced when a safe alternative is verified, and that repetition only breaks exact WDL ties. They do not reconstruct the exact historical v7.6 Matches 8/12/9: the uploaded v7.6 game records omitted move histories and snapshots.
