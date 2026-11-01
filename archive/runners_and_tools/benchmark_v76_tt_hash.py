"""Small synthetic microbenchmark: legacy sorted-tuple TT key vs R2 frozenset key.

This isolates key construction only. It is not a ChessMaker engine NPS claim.
"""
import random
import statistics
import time
from types import SimpleNamespace

import agent_v76_exact_tablebase as agent

rng = random.Random(20261101)
classes = {name: type(name.title(), (), {}) for name in
           ("pawn", "knight", "bishop", "right", "queen", "king")}
white = SimpleNamespace(name="white")
black = SimpleNamespace(name="black")
pieces = []
used = set()
for _ in range(18):
    while True:
        x, y = rng.randrange(5), rng.randrange(5)
        if (x, y) not in used:
            used.add((x, y))
            break
    name = rng.choice(tuple(classes))
    piece = classes[name]()
    piece.player = white if rng.randrange(2) == 0 else black
    piece.position = SimpleNamespace(x=x, y=y)
    pieces.append(piece)
board = SimpleNamespace(get_pieces=lambda: pieces, current_player=white)


def legacy_sorted_tuple_hash():
    rows = []
    for p in board.get_pieces():
        rows.append((agent._piece_name(p), p.player.name, p.position.x, p.position.y))
    rows.sort()
    return hash((tuple(rows), board.current_player.name))


def candidate_frozenset_hash():
    return agent._hash_board(board)

for _ in range(2):
    legacy_sorted_tuple_hash(); candidate_frozenset_hash()

loops = 200_000
results = {"legacy_sorted_tuple": [], "candidate_frozenset": []}
for _ in range(5):
    for label, fn in (("legacy_sorted_tuple", legacy_sorted_tuple_hash),
                      ("candidate_frozenset", candidate_frozenset_hash)):
        start = time.perf_counter()
        for _ in range(loops):
            fn()
        results[label].append(time.perf_counter() - start)

legacy = statistics.median(results["legacy_sorted_tuple"])
candidate = statistics.median(results["candidate_frozenset"])
# Order independence is a correctness property of the new set key.
assert candidate_frozenset_hash() == agent._hash_board(board)
original_pieces = list(pieces)
pieces.reverse()
assert candidate_frozenset_hash() == agent._hash_board(board)
pieces[:] = original_pieces

report = {
    "loops_per_run": loops,
    "runs": 5,
    "median_seconds": {
        "legacy_sorted_tuple": round(legacy, 4),
        "candidate_frozenset": round(candidate, 4),
    },
    "keys_per_second": {
        "legacy_sorted_tuple": round(loops / legacy),
        "candidate_frozenset": round(loops / candidate),
    },
    "relative_key_construction_change_pct": round((legacy / candidate - 1.0) * 100, 2),
    "note": "Synthetic 18-piece board objects; this is a hash-routine microbenchmark, not whole-engine NPS.",
}
import json
from pathlib import Path
Path("V76_TT_HASH_MICROBENCH.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(report)
