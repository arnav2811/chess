# v7.4 Tactical Guard — revised candidate

Base: exact frozen v7.3 Emperor source (`agent_v73_emperor.py`), SHA-256:
`e2d98f8f6d09cf127d8318cb7944d102cc9fc678dbd9a7d62e11b0d731963c7b`.

## Changes

- Added bounded material exchange verification after the selected root move. It accounts for immediate recaptures/countercaptures and whether the reply piece can be immediately recaptured.
- A checking move alone no longer suppresses a major-piece-loss warning.
- Added an immediate-promotion check that simulates the promotion and checks whether the promoted piece is immediately capturable.
- Tightened replacement policy: selected move must have an exact root score; candidate alternative must also be exact and be within 150 cp; maximum four alternatives.
- Added material and promotion guard diagnostics to move statistics.
- Added a dedicated v7.3-v7.4 paired, source-hash-locked runner.

## Unchanged

- `evaluate_for_white` verified AST-identical to frozen v7.3.
- Piece values, move ordering, PVS, Negamax, iterative deepening, TT, aspiration windows, quiescence and LMR unchanged.
- PUCT OFF, check extensions OFF, root random tie-break OFF.

## Validation status

- Python syntax compilation: passed.
- v7.4 offline guard tests: 12/12 passed.
- v7.3-v7.4 runner syntax/help/hash verification: passed.
- Live ChessMaker import/board validation and gameplay: **not run in the authoring environment**; `chessmaker` is not installed here. Run `--validate-only` locally before any games.

Candidate only. Not promoted.
