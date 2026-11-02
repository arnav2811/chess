"""Run the fixed 18-game schedule against a selected engine module.

This wrapper reuses the repository's live ChessMaker runner without overwriting
the historical V78 result file. It is intentionally sequential so the engine's
own per-game state and 300-second player clocks behave like the supplied runner.
"""

import importlib
import json
import sys

import run_tournament_v78 as runner


MATCHES = [
    (1, 1, "Baseline", "sample0", "white"),
    (2, 1, "Baseline", "sample0", "black"),
    (3, 1, "Baseline", "sample1", "white"),
    (4, 1, "Baseline", "sample1", "black"),
    (5, 1, "Baseline", "sample2", "white"),
    (6, 1, "Baseline", "sample2", "black"),
    (7, 2, "Strong", "sample0", "white"),
    (8, 2, "Strong", "sample0", "black"),
    (9, 2, "Strong", "sample1", "white"),
    (10, 2, "Strong", "sample1", "black"),
    (11, 2, "Strong", "sample2", "white"),
    (12, 2, "Strong", "sample2", "black"),
    (13, 3, "Master", "sample0", "white"),
    (14, 3, "Master", "sample0", "black"),
    (15, 3, "Master", "sample1", "white"),
    (16, 3, "Master", "sample1", "black"),
    (17, 3, "Master", "sample2", "white"),
    (18, 3, "Master", "sample2", "black"),
]


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: python run_engine_tournament.py MODULE OUTPUT.json")
    module_name, output_path = sys.argv[1:]
    engine = importlib.import_module(module_name)
    if hasattr(engine, "_ENABLE_STDERR_LOG"):
        engine._ENABLE_STDERR_LOG = False
    runner.agent_module = engine

    results = []
    for match in MATCHES:
        try:
            results.append(runner.play_one_game(*match))
        except Exception as exc:
            match_id, tier, opponent, board, agent_color = match
            results.append({
                "match_id": match_id,
                "tier": tier,
                "opp": opponent,
                "board": board,
                "agent_color": agent_color,
                "outcome": "ERROR",
                "termination": f"runner error: {exc}",
                "plies": 0,
                "duration_s": 0.0,
                "pieces_left": None,
            })
            print(f"[{match_id:>2d}/18] runner error: {exc}", flush=True)
    summary = {
        "engine_module": module_name,
        "total": len(results),
        "wins": sum(r["outcome"] == "WIN" for r in results),
        "draws": sum(r["outcome"] == "DRAW" for r in results),
        "losses": sum(r["outcome"] == "LOSS" for r in results),
        "errors": sum(r["outcome"] not in {"WIN", "DRAW", "LOSS"} for r in results),
        "games": results,
    }
    summary["win_pct"] = round(100 * summary["wins"] / summary["total"], 1)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    print(json.dumps({key: summary[key] for key in
                      ("engine_module", "total", "wins", "draws", "losses", "errors", "win_pct")}))


if __name__ == "__main__":
    main()
