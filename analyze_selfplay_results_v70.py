#!/usr/bin/env python3
"""Summarize selfplay_lab_runs/<run>/games.json without modifying any files."""
import argparse, json
from collections import Counter, defaultdict
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("results", nargs="?", default="selfplay_lab_runs/run_001/games.json")
    args = p.parse_args()
    path = Path(args.results)
    if not path.exists():
        raise SystemExit(f"Results file not found: {path}")
    games = json.loads(path.read_text(encoding="utf-8"))
    by_candidate = defaultdict(list)
    terminations = Counter()
    captured = Counter()
    loss_examples = []
    for g in games:
        by_candidate[str(g.get("candidate_id", "unknown"))].append(g)
        terminations[(g.get("outcome"), g.get("termination", "Unknown"))] += 1
        if g.get("outcome") == "LOSS":
            loss_examples.append({"game": g.get("match_id"), "candidate": g.get("candidate_id"),
                                  "colour": g.get("agent_color"), "seed": g.get("seed"),
                                  "termination": g.get("termination"), "plies": g.get("plies"),
                                  "duration_s": g.get("duration_s")})
        agent_colour = g.get("agent_color")
        for m in g.get("moves", []):
            if m.get("capture") and m.get("side") != agent_colour:
                captured[m["capture"]] += 1
    print(f"Games loaded: {len(games)} from {path}")
    print("\nCandidate scores (W=1, D=0.5, L/E=0):")
    for cid, rs in sorted(by_candidate.items()):
        w = sum(r.get("outcome") == "WIN" for r in rs)
        d = sum(r.get("outcome") == "DRAW" for r in rs)
        l = sum(r.get("outcome") == "LOSS" for r in rs)
        e = sum(r.get("outcome") == "ERROR" for r in rs)
        score = (w + .5*d) / max(1, len(rs))
        print(f"  {cid:24s} {score:6.1%}  W/D/L/E={w}/{d}/{l}/{e}  n={len(rs)}")
    print("\nOutcome / termination counts:")
    for (outcome, term), count in terminations.most_common():
        print(f"  {outcome:7s} {count:4d}  {term}")
    print("\nCandidate pieces captured by the opponent (rough diagnostic):")
    for piece, count in captured.most_common():
        print(f"  {piece:16s} {count}")
    print("\nLoss examples:")
    for item in loss_examples[:30]:
        print(" ", json.dumps(item, ensure_ascii=False))
    if len(loss_examples) > 30:
        print(f"  ... plus {len(loss_examples)-30} more")

if __name__ == "__main__":
    main()
