# v8.2 Endgame Safety Candidate

## Baseline

`agent_final.py` is the frozen v8.0 submission candidate with the measured
18W/0D/0L three-tier result. `agent.py` is the experimental v8.1 line and is
not used as the v8.2 base because its SEE/RFP changes scored 17/18.

## Change

`agent_v82_candidate.py` adds a bounded two-opponent-reply self-stalemate proof.
It is enabled only when all of the following hold:

- the root was fully solved by the exact tablebase;
- the root WDL is DRAW (`0`); and
- the position has at most four pieces.

The proof uses correct minimax quantifiers: an opponent first reply is a real
threat only when every legal response available to us still permits the
opponent to leave us with no legal move. Unknown/deadline cases are preserved
as inconclusive and never treated as proven safe.

The candidate also fixes a runtime compatibility bug in the inherited guard:
some ChessMaker versions expose `get_pieces()` as a generator, so calling
`len(board.get_pieces())` raised and disabled the guard. `_piece_count()` now
handles both list-like and generator-like APIs.

## Promotion gate

Run the focused regression and live smoke test first:

```powershell
python .\tests\test_v82_endgame_guard.py
python -m py_compile .\agent_v82_candidate.py
```

Then run the same paired-colour and 18-game suites used for v8.0. Promote only
if the candidate preserves legal-move safety, clock behaviour, and the v8.0
result while reducing the known four-piece Black stalemate losses.
