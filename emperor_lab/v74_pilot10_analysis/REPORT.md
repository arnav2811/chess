# EMPEROR v7.4 — diverse self-play analysis

## Dataset integrity

- Completed games: **10**
- Unique starting positions: **10**
- Duplicate starting positions: **0**
- Unique complete trajectories: **10**
- Unique decision positions: **158**
- Unique tactical review positions: **62**

## Tactical signals

- capture: 71
- immediate_major_piece_hang: 16
- material_guard_trigger: 22
- promotion_allowed_next_ply: 4
- promotion_guard_trigger: 4
- promotion_played: 4

## Guard activity

- material_guard_replacements: 0
- material_guard_triggers: 22
- promotion_guard_replacements: 0
- promotion_guard_triggers: 4

## Outcomes and layout coverage

```json
{
  "BLACK_WIN": 5,
  "WHITE_WIN": 5
}
```

```json
{
  "sample0": 1,
  "sample1": 1,
  "sample2": 1,
  "sample3": 1,
  "sample4": 1,
  "sample5": 1,
  "sample6": 1,
  "sample7": 1,
  "sample8": 1,
  "sample9": 1
}
```

## Interpretation

Self-play is not a strength rating. White/Black wins are not independent engine comparisons because both seats run the same v7.4 source.
Immediate major-piece hangs and promotion events are concrete review leads; they are not automatically proven search bugs.
Root candidate values are recorded as score/bound hints and must not be treated as exact evaluations.
The regression-candidate file deliberately does not invent a correct move. Each position requires deeper independent analysis or manual verification.
