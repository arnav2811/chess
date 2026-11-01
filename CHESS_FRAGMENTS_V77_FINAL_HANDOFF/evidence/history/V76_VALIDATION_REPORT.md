# v7.6 Validation Report

Build: `v7.6-exact-tablebase`

## Completed in this build environment

| Check | Result | Evidence |
|---|---|---|
| Python compilation | PASS | Candidate, baseline, runners, tests, play harness and extension helpers |
| Embedded tablebase load | PASS | 65 material-configuration keys |
| Basic decisive K+Q regression | PASS | Returns `+95000` for side to move |
| Historical endgame corpus | PASS | 555 distinct states from the v7.4 600-game run |
| Historical WDL coverage | PASS | 240 WIN, 227 LOSS, 88 DRAW |
| Exact score semantics | PASS | WIN `+95000-ply`, LOSS `-95000+ply`, DRAW exactly `0` |
| Legacy contempt immunity | PASS | Extreme `mat_diff` values cannot change an exact DRAW |
| Agent integration | PASS | Agent Negamax/quiescence probe helper returns all 555 expected values |
| Root tablebase selector | PASS | Mocked best-WDL selection and incomplete-child fallback |
| Search safeguards | PASS | History ageing, conservative LMR, low-mobility futility gate, expired-root fallback |
| TT key microbenchmark | PASS | 21.26% lower median key-construction time (26.99% higher key throughput) in a synthetic 18-piece test |

## Tablebase historical coverage

- 618 eligible occurrences in the historical v7.4 600-game move log.
- 555 unique board-placement + side-to-move states after deduplication.
- Occurrence WDL: 258 WIN, 242 LOSS, 118 DRAW.
- Unique-state WDL: 240 WIN, 227 LOSS, 88 DRAW.

## Not completed here

`python smoke_test_v76.py` was attempted and stopped at import with `ModuleNotFoundError: No module named 'chessmaker'`. Therefore this environment has **not** executed a live ChessMaker move, the paired-colour v7.4 H2H, or the 18-game v7.6 tournament. These remain mandatory in the user's Windows project. The PowerShell validator stops before tournaments if the smoke test fails.

## Interpretation

The offline tests establish correct tablebase loading, indexing and WDL semantics across historical states, plus the framework-independent search-control behaviours. They do **not** establish a full-engine win-rate or a whole-engine NPS increase. The 21.26% median-time reduction (26.99% throughput gain) is limited to transposition-key construction on synthetic 18-piece board objects. v7.6 must earn promotion through fresh Windows tests.


## v7.6 nomenclature release

The v7.6 release changes only names, import targets, build/log labels, output filenames, installer/validator references and documentation. The engine algorithm and evaluation code is unchanged from the preceding R2 candidate. Offline tests were rerun after the rename; live ChessMaker validation remains required.
