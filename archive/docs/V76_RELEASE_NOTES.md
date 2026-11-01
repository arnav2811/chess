# v7.6 Release Notes

## Scope

v7.6 is the new public version name for the exact-tablebase R2 candidate. This is a nomenclature and packaging update only.

## Changed

- Engine module renamed to `agent_v76_exact_tablebase.py`.
- `ENGINE_BUILD` set to `v7.6-exact-tablebase`.
- Runtime log banner updated to `[agent v7.6-exact-tablebase]`.
- Test, benchmark, play, comparison, tournament, installer and validator filenames updated to v7.6.
- Benchmark and tournament outputs use `V76_...` names to avoid overwriting v7.5 results.
- README, engineering notes, validation report and manifest updated.

## Not changed

No changes were made to search algorithms, evaluation terms or weights, pruning thresholds, LMR settings, history behaviour, time management, tablebase indexing or WDL semantics. The tablebase payload and baseline v7.4 engine are byte-for-byte copied from the preceding release.

## Validation

The renamed candidate is recompiled and the offline regression tests are rerun as part of this packaging task. A live ChessMaker smoke test remains environment-dependent and must be run in the user's Windows project before tournament promotion.

The package also includes `HISTORICAL_V75_R2_IMPLEMENTATION_DIFF_FROM_V74.patch` as historical provenance; it is not used by the installer.
