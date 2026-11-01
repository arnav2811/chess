# EMPEROR v7.4 — diverse self-play analysis

## Dataset integrity

- Completed games: **600**
- Unique starting positions: **600**
- Duplicate starting positions: **0**
- Unique complete trajectories: **600**
- Unique decision positions: **10364**
- Unique tactical review positions: **3332**

## Tactical signals

- capture: 4698
- immediate_major_piece_hang: 1006
- material_guard_trigger: 313
- promotion_allowed_next_ply: 287
- promotion_guard_trigger: 127
- promotion_played: 304

## Guard activity

- material_guard_replacements: 12
- material_guard_triggers: 313
- promotion_guard_replacements: 2
- promotion_guard_triggers: 127

## Outcomes and layout coverage

```json
{
  "BLACK_WIN": 326,
  "WHITE_WIN": 271,
  "DRAW": 3
}
```

```json
{
  "sample0": 47,
  "sample1": 47,
  "sample2": 46,
  "sample3": 46,
  "sample4": 46,
  "sample5": 46,
  "sample6": 46,
  "sample7": 46,
  "sample8": 46,
  "sample9": 46,
  "sample10": 46,
  "sample11": 46,
  "sample12": 46
}
```

## Interpretation

Self-play is not a strength rating. White/Black wins are not independent engine comparisons because both seats run the same v7.4 source.
Immediate major-piece hangs and promotion events are concrete review leads; they are not automatically proven search bugs.
Root candidate values are recorded as score/bound hints and must not be treated as exact evaluations.
The regression-candidate file deliberately does not invent a correct move. Each position requires deeper independent analysis or manual verification.
