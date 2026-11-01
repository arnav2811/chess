#!/usr/bin/env python3
"""Validate and combine the PC1 + PC2 v6.9-v7.1 head-to-head results."""
from __future__ import annotations
import argparse, csv, json
from collections import defaultdict
from pathlib import Path

EXPECTED_GAMES_PER_PC = 100
EXPECTED_TOTAL = 200
EXPECTED_BOARDS = ("sample0", "sample1", "sample2", "sample3", "sample4")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_run(folder: Path):
    manifest_path, games_path = folder / "manifest.json", folder / "games.json"
    if not manifest_path.is_file() or not games_path.is_file():
        raise SystemExit(f"Missing manifest.json or games.json in {folder}")
    manifest = read_json(manifest_path)
    games = read_json(games_path)
    if manifest.get("games_requested") != EXPECTED_GAMES_PER_PC:
        raise SystemExit(f"{folder}: expected {EXPECTED_GAMES_PER_PC} requested games")
    if manifest.get("v71_root_puct") is not False:
        raise SystemExit(f"{folder}: manifest does not confirm v7.1 PUCT OFF")
    if len(games) != EXPECTED_GAMES_PER_PC:
        raise SystemExit(f"{folder}: games.json contains {len(games)}, expected {EXPECTED_GAMES_PER_PC}")
    if len({g.get("game_id") for g in games}) != len(games):
        raise SystemExit(f"{folder}: duplicate game_id values")
    if any(g.get("outcome_for_v71") not in {"WIN", "DRAW", "LOSS", "ERROR"} for g in games):
        raise SystemExit(f"{folder}: unexpected outcome value")

    pairs = defaultdict(list)
    for game in games:
        pairs[game.get("pair_id")].append(game)
    if len(pairs) != EXPECTED_GAMES_PER_PC // 2:
        raise SystemExit(f"{folder}: expected 50 mirrored pairs, found {len(pairs)}")
    for pair_id, rows in pairs.items():
        if len(rows) != 2 or {r.get("v71_color") for r in rows} != {"white", "black"}:
            raise SystemExit(f"{folder}: pair {pair_id} is not a complete colour reversal")
        for field in ("board", "seed", "v69_rng_seed", "v71_rng_seed"):
            if len({r.get(field) for r in rows}) != 1:
                raise SystemExit(f"{folder}: pair {pair_id} differs on matched field {field}")

    counts = {b: sum(g.get("board") == b for g in games) for b in EXPECTED_BOARDS}
    if counts != {b: 20 for b in EXPECTED_BOARDS}:
        raise SystemExit(f"{folder}: board balance incorrect: {counts}")
    if sum(g.get("v71_color") == "white" for g in games) != 50:
        raise SystemExit(f"{folder}: v7.1 White count is not 50")
    if sum(g.get("v71_color") == "black" for g in games) != 50:
        raise SystemExit(f"{folder}: v7.1 Black count is not 50")
    return manifest, games


def build_summary(games, manifests):
    w = sum(g["outcome_for_v71"] == "WIN" for g in games)
    d = sum(g["outcome_for_v71"] == "DRAW" for g in games)
    l = sum(g["outcome_for_v71"] == "LOSS" for g in games)
    e = sum(g["outcome_for_v71"] == "ERROR" for g in games)
    by_color = {}
    for color in ("white", "black"):
        group = [g for g in games if g["v71_color"] == color]
        by_color[color] = {
            "games": len(group),
            "W": sum(g["outcome_for_v71"] == "WIN" for g in group),
            "D": sum(g["outcome_for_v71"] == "DRAW" for g in group),
            "L": sum(g["outcome_for_v71"] == "LOSS" for g in group),
            "errors": sum(g["outcome_for_v71"] == "ERROR" for g in group),
        }
    by_board = {}
    for board in EXPECTED_BOARDS:
        group = [g for g in games if g["board"] == board]
        by_board[board] = {
            "games": len(group),
            "W": sum(g["outcome_for_v71"] == "WIN" for g in group),
            "D": sum(g["outcome_for_v71"] == "DRAW" for g in group),
            "L": sum(g["outcome_for_v71"] == "LOSS" for g in group),
            "errors": sum(g["outcome_for_v71"] == "ERROR" for g in group),
        }
    pairs = defaultdict(list)
    for g in games:
        pairs[(g["source_run"], g["pair_id"])].append(g)
    paired = {"v71_wins_both": 0, "v69_wins_both": 0, "split": 0, "draw_or_error": 0}
    for rows in pairs.values():
        outcomes = [r["outcome_for_v71"] for r in rows]
        if len(rows) != 2:
            paired["draw_or_error"] += 1
        elif outcomes == ["WIN", "WIN"]:
            paired["v71_wins_both"] += 1
        elif outcomes == ["LOSS", "LOSS"]:
            paired["v69_wins_both"] += 1
        elif set(outcomes) == {"WIN", "LOSS"}:
            paired["split"] += 1
        else:
            paired["draw_or_error"] += 1

    engine_metrics = {}
    for engine in ("v69", "v71"):
        rows = [m for game in games for m in game.get("moves", []) if m.get("engine") == engine]
        total_time = sum(m.get("thinking_time_s", 0.0) for m in rows)
        total_nodes = sum(m.get("search", {}).get("nodes", 0) for m in rows)
        engine_metrics[engine] = {
            "moves": len(rows),
            "average_depth_per_move": round(sum(m.get("search", {}).get("depth", 0) for m in rows) / len(rows), 3) if rows else 0.0,
            "max_depth": max((m.get("search", {}).get("depth", 0) for m in rows), default=0),
            "total_nodes": total_nodes,
            "average_move_time_s": round(total_time / len(rows), 4) if rows else 0.0,
            "aggregate_nps": round(total_nodes / total_time, 1) if total_time else 0.0,
            "puct_calls": sum(bool(m.get("search", {}).get("puct_used")) for m in rows),
            "puct_overrides": sum(bool(m.get("search", {}).get("puct_overrode")) for m in rows),
        }
    n = len(games)
    return {
        "title": "Combined 200-game paired head-to-head: frozen v6.9 vs v7.1 (PUCT OFF)",
        "games_completed": n,
        "expected_games": EXPECTED_TOTAL,
        "v71": {"wins": w, "draws": d, "losses": l, "errors": e,
                "score_pct": round((w + 0.5 * d) / n * 100, 2) if n else 0.0},
        "by_v71_colour": by_color,
        "by_board": by_board,
        "paired_colour_reversal": paired,
        "engine_search_metrics": engine_metrics,
        "average_plies": round(sum(g.get("plies", 0) for g in games) / n, 2) if n else 0.0,
        "average_game_wall_s": round(sum(g.get("wall_time_s", 0.0) for g in games) / n, 2) if n else 0.0,
        "puct_disabled_validation": {
            "v71_puct_calls": engine_metrics["v71"]["puct_calls"],
            "v71_puct_overrides": engine_metrics["v71"]["puct_overrides"],
        },
        "source_runs": [
            {"name": m["output_directory"], "computer_seed": m["computer_seed"], "games": m["games_requested"]}
            for m in manifests
        ],
    }


def main():
    ap = argparse.ArgumentParser(description="Combine two 100-game PC head-to-head result folders")
    ap.add_argument("pc1_folder", type=Path)
    ap.add_argument("pc2_folder", type=Path)
    ap.add_argument("--out", type=Path, default=Path("head_to_head_runs/combined_200"))
    args = ap.parse_args()

    manifest1, games1 = validate_run(args.pc1_folder)
    manifest2, games2 = validate_run(args.pc2_folder)
    def fingerprint_map(manifest):
        return {name: details.get("sha256") for name, details in manifest.get("engine_files", {}).items()}
    if fingerprint_map(manifest1) != fingerprint_map(manifest2):
        raise SystemExit("The two PCs did not use identical engine fingerprints")
    if manifest1.get("computer_seed") == manifest2.get("computer_seed"):
        raise SystemExit("The PC seed values are identical; expected independent PC1/PC2 seeds")
    if manifest1.get("thinking_time_s_per_move") != manifest2.get("thinking_time_s_per_move") or manifest1.get("game_clock_s_per_player") != manifest2.get("game_clock_s_per_player"):
        raise SystemExit("The two PCs used different time controls")
    if len(games1) + len(games2) != EXPECTED_TOTAL:
        raise SystemExit("Combined total is not 200 games")

    all_games = []
    for source_name, games in ((args.pc1_folder.name, games1), (args.pc2_folder.name, games2)):
        for game in games:
            row = dict(game)
            row["source_run"] = source_name
            row["global_game_id"] = len(all_games) + 1
            all_games.append(row)

    out = args.out.resolve()
    if out.exists():
        raise SystemExit(f"Output already exists: {out}")
    out.mkdir(parents=True)
    summary = build_summary(all_games, [manifest1, manifest2])
    (out / "combined_games.json").write_text(json.dumps(all_games, indent=2), encoding="utf-8")
    (out / "combined_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    fields = ["global_game_id", "source_run", "game_id", "pair_id", "pair_variant", "board", "seed",
              "v71_color", "winner_color", "winner_engine", "outcome_for_v71", "termination", "plies", "wall_time_s"]
    with (out / "combined_games.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in all_games:
            writer.writerow({key: row.get(key, "") for key in fields})

    move_fields = ["global_game_id", "source_run", "pair_id", "board", "v71_color", "ply", "side", "engine",
                   "thinking_time_s", "depth", "nodes", "ebf", "puct_used", "puct_overrode", "error"]
    with (out / "combined_move_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=move_fields)
        writer.writeheader()
        for game in all_games:
            for move in game.get("moves", []):
                search = move.get("search", {})
                writer.writerow({
                    "global_game_id": game["global_game_id"], "source_run": game["source_run"],
                    "pair_id": game["pair_id"], "board": game["board"], "v71_color": game["v71_color"],
                    "ply": move.get("ply"), "side": move.get("side"), "engine": move.get("engine"),
                    "thinking_time_s": move.get("thinking_time_s"), "depth": search.get("depth", 0),
                    "nodes": search.get("nodes", 0), "ebf": search.get("ebf", 0.0),
                    "puct_used": search.get("puct_used", False),
                    "puct_overrode": search.get("puct_overrode", False), "error": move.get("error"),
                })

    report = [
        "# v6.9 vs v7.1 — combined 200-game head-to-head",
        "",
        f"**v7.1 score: {summary['v71']['score_pct']:.2f}%** (W-D-L: {summary['v71']['wins']}-{summary['v71']['draws']}-{summary['v71']['losses']}; errors: {summary['v71']['errors']})",
        "",
        "## Colour split",
        "",
        "| v7.1 colour | Games | Wins | Draws | Losses |",
        "|---|---:|---:|---:|---:|",
    ]
    for color, stat in summary["by_v71_colour"].items():
        report.append(f"| {color.title()} | {stat['games']} | {stat['W']} | {stat['D']} | {stat['L']} |")
    report += ["", "## Board split", "", "| Board | Games | Wins | Draws | Losses |", "|---|---:|---:|---:|---:|"]
    for board, stat in summary["by_board"].items():
        report.append(f"| {board} | {stat['games']} | {stat['W']} | {stat['D']} | {stat['L']} |")
    report += ["", "## Matched colour-reversal pairs", "", json.dumps(summary["paired_colour_reversal"], indent=2),
               "", "## Notes", "", "- Both engine source fingerprints must match across PCs.",
               "- v7.1 root PUCT was disabled in both runs.",
               "- Draws count as half a point in the v7.1 score.",
               "- Do not promote based on score alone; inspect colour, board, paired results, errors, and search diagnostics."]
    (out / "combined_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(f"Merged {len(all_games)} games. v7.1: {summary['v71']['wins']}W-{summary['v71']['draws']}D-{summary['v71']['losses']}L; errors={summary['v71']['errors']}; score={summary['v71']['score_pct']:.2f}%")
    print(f"Saved: {out}")

if __name__ == "__main__":
    main()
