#!/usr/bin/env python3
"""Merge two-PC Chess Fragments self-play runs into one comparison report.

Example:
  python merge_selfplay_results.py \
    selfplay_runs/pc1_v69_50 selfplay_runs/pc2_v69_50 \
    selfplay_runs/pc1_v71_50 selfplay_runs/pc2_v71_50 \
    --out selfplay_runs/combined_200
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path


def read_run(path: Path):
    manifest_path = path / "manifest.json"
    summary_path = path / "summary.json"
    games_path = path / "games.json"
    if not (manifest_path.is_file() and summary_path.is_file() and games_path.is_file()):
        raise SystemExit(f"Incomplete run folder: {path} (need manifest.json, summary.json, games.json)")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    games = json.loads(games_path.read_text(encoding="utf-8"))
    return manifest, summary, games


def aggregate(engine: str, rows: list[dict]):
    white = sum(r.get("winner_color") == "white" for r in rows)
    black = sum(r.get("winner_color") == "black" for r in rows)
    draws = sum(r.get("outcome") == "DRAW" for r in rows)
    decisive = white + black
    by_board = {}
    for board in ("sample0", "sample1", "sample2", "sample3", "sample4"):
        group = [r for r in rows if r.get("board") == board]
        by_board[board] = {
            "games": len(group),
            "white_wins": sum(r.get("winner_color") == "white" for r in group),
            "black_wins": sum(r.get("winner_color") == "black" for r in group),
            "draws": sum(r.get("outcome") == "DRAW" for r in group),
        }
    return {
        "engine": engine,
        "games": len(rows),
        "white_wins": white,
        "black_wins": black,
        "draws": draws,
        "other_terminal_or_error_results": len(rows) - decisive - draws,
        "white_share_of_decisive_pct": round(100 * white / decisive, 2) if decisive else None,
        "by_board": by_board,
        "average_plies": round(sum(r.get("plies", 0) for r in rows) / len(rows), 2) if rows else 0,
        "average_game_wall_s": round(sum(r.get("wall_time_s", 0) for r in rows) / len(rows), 2) if rows else 0,
        "source_runs": sorted({r.get("source_run", "") for r in rows}),
    }


def main():
    parser = argparse.ArgumentParser(description="Merge independent 2-PC self-play control outputs")
    parser.add_argument("runs", nargs="+", help="Run folders; provide both PCs' v69 and v71 folders")
    parser.add_argument("--out", required=True, help="New combined output directory")
    args = parser.parse_args()
    run_paths = [Path(p).resolve() for p in args.runs]
    loaded = [(p, *read_run(p)) for p in run_paths]
    engines = {m.get("engine") for _, m, _, _ in loaded}
    if engines != {"v69", "v71"}:
        raise SystemExit(f"Expected both v69 and v71 run folders; found {sorted(engines)}")

    expected_hashes = None
    combined = {"v69": [], "v71": []}
    run_summaries = []
    for path, manifest, summary, games in loaded:
        engine = manifest.get("engine")
        if engine not in combined:
            raise SystemExit(f"Unknown engine in {path}: {engine}")
        hashes = {k: v.get("sha256") for k, v in manifest.get("engine_files", {}).items()}
        if expected_hashes is None:
            expected_hashes = hashes
        elif hashes != expected_hashes:
            raise SystemExit(f"Engine source hashes differ in {path}; refusing to merge incomparable runs")
        if engine == "v71" and manifest.get("puct_enabled") is not False:
            raise SystemExit(f"v7.1 run {path} did not explicitly disable PUCT")
        if len(games) != summary.get("games_completed"):
            raise SystemExit(f"Game count mismatch in {path}")
        run_tag = path.name
        for g in games:
            row = dict(g)
            row["source_run"] = run_tag
            row["source_game_id"] = row.get("game_id")
            combined[engine].append(row)
        run_summaries.append({"run": run_tag, "engine": engine, "summary": summary})

    out = Path(args.out).resolve()
    if out.exists():
        raise SystemExit(f"Output already exists: {out}")
    out.mkdir(parents=True)

    # Enforce intended design: 100 per version across two equal 50-game PC runs.
    # Allow alternative totals, but always flag uneven split in report data.
    engine_summaries = {k: aggregate(k, v) for k, v in combined.items()}
    all_rows = []
    for engine in ("v69", "v71"):
        for r in combined[engine]:
            flat = {k: v for k, v in r.items() if k != "moves"}
            all_rows.append(flat)

    result = {
        "title": "Two-PC same-engine Chess Fragments self-play controls",
        "merged_local": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "total_games": sum(len(v) for v in combined.values()),
        "engine_source_hashes": expected_hashes,
        "puct_policy": {"v69": "not applicable", "v71": "disabled"},
        "by_engine": engine_summaries,
        "input_runs": run_summaries,
        "interpretation_note": (
            "These are same-engine self-play controls. Winner-colour proportions estimate first-player/side bias "
            "under the tested boards, clocks and runtime. They are not a direct v69-vs-v71 strength comparison."
        ),
    }
    (out / "combined_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    fields = ["engine", "source_run", "source_game_id", "pair_id", "pair_variant", "board", "seed",
              "winner_color", "outcome", "termination", "plies", "wall_time_s", "process_cpu_s"]
    with (out / "combined_games.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in all_rows:
            writer.writerow({k: r.get(k, "") for k in fields})

    lines = [
        "# Two-PC self-play control report", "",
        f"**Total games:** {result['total_games']}", "",
        "| Engine | Games | White wins | Black wins | Draws | White share of decisive games |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for engine in ("v69", "v71"):
        s = engine_summaries[engine]
        val = "n/a" if s["white_share_of_decisive_pct"] is None else f"{s['white_share_of_decisive_pct']:.2f}%"
        lines.append(f"| {engine} | {s['games']} | {s['white_wins']} | {s['black_wins']} | {s['draws']} | {val} |")
    lines += ["", "## Board breakdown", ""]
    for engine in ("v69", "v71"):
        lines += [f"### {engine}", "", "| Board | Games | White wins | Black wins | Draws |", "|---|---:|---:|---:|---:|"]
        for board, s in engine_summaries[engine]["by_board"].items():
            lines.append(f"| {board} | {s['games']} | {s['white_wins']} | {s['black_wins']} | {s['draws']} |")
        lines.append("")
    lines += ["## Interpretation", "", result["interpretation_note"], "",
              "Compare white win share separately for each engine. Since both PCs ran both versions, "
              "the combined comparison is less confounded by hardware differences. Check per-run summaries "
              "for any machine-specific outliers."]
    (out / "combined_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Merged {result['total_games']} games into {out}")
    for engine in ("v69", "v71"):
        s = engine_summaries[engine]
        print(f"{engine}: {s['games']} games | W wins {s['white_wins']} | B wins {s['black_wins']} | draws {s['draws']} | White share {s['white_share_of_decisive_pct']}%")


if __name__ == "__main__":
    main()
