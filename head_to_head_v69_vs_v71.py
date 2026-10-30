#!/usr/bin/env python3
"""
Controlled head-to-head tournament: frozen v6.9 vs v7.1 adaptive tactical hybrid.

Run from the chess project root:
    python head_to_head_v69_vs_v71.py

Defaults: 10 games, 8 worker processes, coursework time controls.
The script refuses to run if either engine file differs from the audited hashes.
It does not modify either engine.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import random
import re
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from itertools import cycle
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

V69_FILE = "agent_v69_frozen_overnight.py"
V71_FILE = "agent_v71_adaptive_tactical_hybrid.py"

# SHA-256 fingerprints taken from the supplied repository archive.
EXPECTED_HASHES = {
    V69_FILE: "df5cfb7305e8374ed45b6a862e6934cf0f3168e7c7eca9b1c18e9cfd517e08bd",
    V71_FILE: "488b051b3dce2e49f3b883a16dc12eddaba31510a0596bde7b83247c933865de",
}

SAMPLE_NAMES = ("sample0", "sample1", "sample2", "sample3", "sample4")


def sha256(path: Path) -> str:
    # Canonicalise Windows CRLF and Unix LF so Git's core.autocrlf setting
    # cannot trigger a false safety stop. This still detects every actual
    # source-code change; only newline representation is normalised.
    raw = path.read_bytes()
    canonical = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(canonical).hexdigest()


def verify_engines():
    details = {}
    for filename, expected in EXPECTED_HASHES.items():
        path = PROJECT_ROOT / filename
        if not path.is_file():
            raise SystemExit(f"Missing engine file: {path}")
        actual = sha256(path)
        details[filename] = {"path": str(path), "sha256": actual}
        if actual != expected:
            raise SystemExit(
                f"\nSAFETY STOP: {filename} does not match the audited copy.\n"
                f"Expected: {expected}\nActual:   {actual}\n"
                "No games were started. Restore the intended file or audit the "
                "change before running a comparison."
            )
    return details


def load_agent(filename: str, module_name: str, expected_version: str):
    path = PROJECT_ROOT / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load agent module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    source = path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"\[agent v(\d+(?:\.\d+)?)(?:-[^\]]*)?\]", source)
    version = matches[-1] if matches else "unknown"
    if version != expected_version:
        raise RuntimeError(
            f"{filename}: expected version marker {expected_version}, found {version}"
        )
    if not callable(getattr(module, "agent", None)):
        raise RuntimeError(f"{filename} does not expose callable agent()")
    return module


def make_fresh_board(sample_name: str):
    # Deliberately mirrors the project's existing tournament board definitions.
    from chessmaker.chess.base import Player, Board, Square
    from chessmaker.chess.pieces import King, Bishop, Knight, Queen
    from extension.piece_right import Right
    from extension.piece_pawn import Pawn_Q

    white = Player("white")
    black = Player("black")
    players = [white, black]

    layouts = {
        "sample0": [
            [Knight(black), Queen(black), King(black), Bishop(black), Right(black)],
            [Pawn_Q(black), Pawn_Q(black), Pawn_Q(black), Pawn_Q(black), Pawn_Q(black)],
            [None, None, None, None, None],
            [Pawn_Q(white), Pawn_Q(white), Pawn_Q(white), Pawn_Q(white), Pawn_Q(white)],
            [Right(white), Bishop(white), King(white), Queen(white), Knight(white)],
        ],
        "sample1": [
            [Right(black), Queen(black), King(black), Knight(black), Bishop(black)],
            [Pawn_Q(black), Pawn_Q(black), Pawn_Q(black), Pawn_Q(black), Pawn_Q(black)],
            [None, None, None, None, None],
            [Pawn_Q(white), Pawn_Q(white), Pawn_Q(white), Pawn_Q(white), Pawn_Q(white)],
            [Bishop(white), Knight(white), King(white), Queen(white), Right(white)],
        ],
        "sample2": [
            [Right(black), Bishop(black), King(black), Queen(black), Knight(black)],
            [Pawn_Q(black), Pawn_Q(black), Pawn_Q(black), Pawn_Q(black), Pawn_Q(black)],
            [None, None, None, None, None],
            [Pawn_Q(white), Pawn_Q(white), Pawn_Q(white), Pawn_Q(white), Pawn_Q(white)],
            [Knight(white), Queen(white), King(white), Bishop(white), Right(white)],
        ],
        "sample3": [
            [Right(black), Queen(black), King(black), Right(black), Knight(black)],
            [Pawn_Q(black), Pawn_Q(black), Pawn_Q(black), Pawn_Q(black), Pawn_Q(black)],
            [None, None, None, None, None],
            [Pawn_Q(white), Pawn_Q(white), Pawn_Q(white), Pawn_Q(white), Pawn_Q(white)],
            [Knight(white), Right(white), King(white), Queen(white), Right(white)],
        ],
        "sample4": [
            [Right(black), Bishop(black), King(black), Knight(black), Right(black)],
            [Pawn_Q(black), Pawn_Q(black), Pawn_Q(black), Pawn_Q(black), Pawn_Q(black)],
            [None, None, None, None, None],
            [Pawn_Q(white), Pawn_Q(white), Pawn_Q(white), Pawn_Q(white), Pawn_Q(white)],
            [Right(white), Knight(white), King(white), Bishop(white), Right(white)],
        ],
    }
    if sample_name not in layouts:
        raise ValueError(f"Unknown board sample: {sample_name}")

    squares = [
        [Square(piece) if piece is not None else Square() for piece in row]
        for row in layouts[sample_name]
    ]
    board = Board(squares=squares, players=players, turn_iterator=cycle(players))
    return board, players


def classify_terminal(result_text: str, candidate_color: str):
    text = (result_text or "").lower()
    if "draw" in text:
        return "DRAW"
    match = re.search(r"\b(white|black)\s+loses\b", text)
    if match:
        loser = match.group(1)
        return "LOSS" if loser == candidate_color else "WIN"
    match = re.search(r"\b(white|black)\s+wins?\b", text)
    if match:
        winner = match.group(1)
        return "WIN" if winner == candidate_color else "LOSS"
    return "ERROR"


def stats_snapshot(module):
    puct = getattr(module, "_last_puct_stats", {}) or {}
    iterations = getattr(module, "_last_iteration_trace", []) or []
    return {
        "depth": int(getattr(module, "_last_depth_reached", 0) or 0),
        "nodes": int(getattr(module, "_last_nodes_searched", 0) or 0),
        "ebf": float(getattr(module, "_last_branching_factor", 0.0) or 0.0),
        "puct_used": bool(puct.get("used", False)),
        "puct_simulations": int(puct.get("simulations", 0) or 0),
        "puct_time_s": float(puct.get("elapsed_s", 0.0) or 0.0),
        "puct_overrode": bool(puct.get("overrode", False)),
        "puct_mode": str(puct.get("policy_mode", "none")),
        "iterations": iterations,
        "aborted_depth": int(getattr(module, "_last_aborted_depth", 0) or 0),
        "aborted_nodes": int(getattr(module, "_last_aborted_nodes", 0) or 0),
    }


def play_one_game(task):
    """One isolated game. Engine modules are freshly imported for every game."""
    from extension.board_utils import copy_piece_move
    from extension.board_rules import get_result, thinking_with_timeout
    from extension.board_rules import THINKING_TIME_BUDGET, GAME_TIME_BUDGET

    game = task
    game_id = game["game_id"]
    candidate_color = game["candidate_color"]
    sample_name = game["board"]
    seed = game["seed"]
    think_time = game["thinking_time"]
    game_time = game["game_time"]
    puct_enabled = bool(game.get("puct_enabled", True))

    random.seed(seed)
    # Unique module names plus fresh imports prevent TT/history/clock state leaking
    # from one game into another when a worker process is reused.
    suffix = f"g{game_id}_{seed}"
    v69 = load_agent(V69_FILE, f"tournament_v69_{suffix}", "6.9")
    v71 = load_agent(V71_FILE, f"tournament_v71_{suffix}", "7.1")
    # Toggle the experiment from the runner; the audited agent file/hash stays fixed.
    v71._ENABLE_ROOT_PUCT = puct_enabled

    candidate_module = v71
    champion_module = v69
    candidate_agent = candidate_module.agent
    champion_agent = champion_module.agent

    board, players = make_fresh_board(sample_name)
    turn_order = cycle(players)
    p_white, p_black = (
        (candidate_agent, champion_agent)
        if candidate_color == "white"
        else (champion_agent, candidate_agent)
    )

    clocks = {"white": float(game_time), "black": float(game_time)}
    metrics = {"v6.9": [], "v7.1": []}
    started = time.perf_counter()
    cpu_started = time.process_time()
    ply = 1
    plies_completed = 0
    outcome = "UNKNOWN"
    termination = "Unknown"

    while ply <= 600:
        player = next(turn_order)
        side = player.name
        engine_name = "v7.1" if side == candidate_color else "v6.9"
        module = candidate_module if engine_name == "v7.1" else champion_module
        function = p_white if side == "white" else p_black

        if clocks[side] <= 0:
            outcome = "LOSS" if side == candidate_color else "WIN"
            termination = f"{side} exhausted its {game_time:.1f}s game clock"
            break

        thinking_board = board.clone()
        move_started = time.perf_counter()
        error_text = None
        try:
            # Suppress per-move engine diagnostics from interleaving across workers;
            # structured depth/node metrics are captured below instead.
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                p_piece, p_move = thinking_with_timeout(
                    func=function,
                    thinking_time=min(float(think_time), clocks[side]),
                    board=thinking_board,
                    player=player,
                    var=[ply, float(think_time)],
                )
            board, piece, move_option = copy_piece_move(board, p_piece, p_move)
        except Exception as exc:
            piece, move_option = None, None
            error_text = f"{type(exc).__name__}: {exc}"

        move_elapsed = time.perf_counter() - move_started
        clocks[side] -= move_elapsed
        snapshot = stats_snapshot(module)
        metrics[engine_name].append({
            "ply": ply,
            "side": side,
            "move_time_s": round(move_elapsed, 4),
            **snapshot,
            "error": error_text,
        })

        if error_text:
            outcome = "LOSS" if side == candidate_color else "WIN"
            termination = f"{side} engine exception: {error_text}"
            break

        if not piece or not move_option:
            result = get_result(board)
            if result:
                outcome = classify_terminal(result, candidate_color)
                termination = result
            else:
                outcome = "LOSS" if side == candidate_color else "WIN"
                termination = f"{side} failed to return a legal move (or timed out)"
            break

        try:
            piece.move(move_option)
            plies_completed += 1
            ply += 1
        except Exception as exc:
            outcome = "LOSS" if side == candidate_color else "WIN"
            termination = f"{side} illegal-move/application error: {type(exc).__name__}: {exc}"
            break

        result = get_result(board)
        if result:
            outcome = classify_terminal(result, candidate_color)
            termination = result
            break
    else:
        outcome = "DRAW"
        termination = "Safety cap reached: 600 plies"

    elapsed = time.perf_counter() - started
    cpu_elapsed = time.process_time() - cpu_started

    def aggregate(rows):
        if not rows:
            return {"moves": 0, "avg_depth": 0.0, "max_depth": 0,
                    "avg_nodes": 0.0, "total_nodes": 0, "avg_move_time_s": 0.0,
                    "aggregate_nps": 0.0}
        total_nodes = sum(r["nodes"] for r in rows)
        total_time = sum(r["move_time_s"] for r in rows)
        return {
            "moves": len(rows),
            "avg_depth": round(sum(r["depth"] for r in rows) / len(rows), 3),
            "max_depth": max(r["depth"] for r in rows),
            "avg_nodes": round(total_nodes / len(rows), 1),
            "total_nodes": total_nodes,
            "avg_move_time_s": round(total_time / len(rows), 4),
            "aggregate_nps": round(total_nodes / total_time, 1) if total_time else 0.0,
            "puct_calls": sum(bool(r.get("puct_used")) for r in rows),
            "puct_simulations": sum(r.get("puct_simulations", 0) for r in rows),
            "puct_overrides": sum(bool(r.get("puct_overrode")) for r in rows),
            "puct_time_s": round(sum(r.get("puct_time_s", 0.0) for r in rows), 4),
        }

    result_row = {
        "game_id": game_id,
        "pair_id": game["pair_id"],
        "seed": seed,
        "board": sample_name,
        "candidate_color": candidate_color,
        "outcome_for_candidate": outcome,
        "termination": termination,
        "plies": plies_completed,
        "wall_time_s": round(elapsed, 3),
        "process_cpu_s": round(cpu_elapsed, 3),
        "v69_clock_remaining_s": round(clocks["white" if candidate_color == "black" else "black"], 3),
        "v71_clock_remaining_s": round(clocks[candidate_color], 3),
        "v69_search": aggregate(metrics["v6.9"]),
        "v71_search": aggregate(metrics["v7.1"]),
        "move_metrics": metrics,
    }
    return result_row


def build_schedule(games: int, think_time: float, game_time: float, seed_base: int,
                   puct_enabled: bool = True):
    if games < 10 or games % 2:
        raise ValueError("--games must be an even number and at least 10.")
    pairs = games // 2
    tasks = []
    for pair_index in range(pairs):
        sample = SAMPLE_NAMES[pair_index % len(SAMPLE_NAMES)]
        repeat = pair_index // len(SAMPLE_NAMES)
        pair_id = pair_index + 1
        seed = seed_base + pair_index
        for color in ("white", "black"):
            tasks.append({
                "game_id": len(tasks) + 1,
                "pair_id": pair_id,
                "board": sample,
                "candidate_color": color,
                "seed": seed,
                "repeat": repeat + 1,
                "thinking_time": think_time,
                "game_time": game_time,
                "puct_enabled": bool(puct_enabled),
            })
    # Randomise execution order without changing the paired schedule.
    random.Random(seed_base ^ 0x5A17).shuffle(tasks)
    return tasks


def summarize(results):
    wins = sum(r["outcome_for_candidate"] == "WIN" for r in results)
    draws = sum(r["outcome_for_candidate"] == "DRAW" for r in results)
    losses = sum(r["outcome_for_candidate"] == "LOSS" for r in results)
    errors = sum(r["outcome_for_candidate"] == "ERROR" for r in results)
    n = len(results)
    summary = {
        "games_completed": n,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "errors": errors,
        "candidate_score_pct": round((wins + 0.5 * draws) / n * 100, 2) if n else 0.0,
        "by_color": {},
        "by_board": {},
    }
    for color in ("white", "black"):
        group = [r for r in results if r["candidate_color"] == color]
        summary["by_color"][color] = {
            "games": len(group),
            "W": sum(r["outcome_for_candidate"] == "WIN" for r in group),
            "D": sum(r["outcome_for_candidate"] == "DRAW" for r in group),
            "L": sum(r["outcome_for_candidate"] == "LOSS" for r in group),
        }
    for board in SAMPLE_NAMES:
        group = [r for r in results if r["board"] == board]
        summary["by_board"][board] = {
            "games": len(group),
            "W": sum(r["outcome_for_candidate"] == "WIN" for r in group),
            "D": sum(r["outcome_for_candidate"] == "DRAW" for r in group),
            "L": sum(r["outcome_for_candidate"] == "LOSS" for r in group),
        }
    return summary


def atomic_json(path: Path, data):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(
        description="Paired head-to-head tournament: frozen v6.9 vs v7.1 adaptive tactical hybrid."
    )
    parser.add_argument("--games", type=int, default=10,
                        help="Total games; even number >=10 (default: 10).")
    parser.add_argument("--workers", type=int, default=8,
                        help="Parallel independent games (default: 8).")
    parser.add_argument("--thinking-time", type=float, default=14.0,
                        help="Per-move thinking budget in seconds (default: 14).")
    parser.add_argument("--game-time", type=float, default=300.0,
                        help="Per-player total game clock in seconds (default: 300).")
    parser.add_argument("--seed", type=int, default=730069,
                        help="Deterministic tournament seed.")
    parser.add_argument("--puct", choices=("on", "off"), default="on",
                        help="Enable or disable the v7.1 root PUCT probe (default: on).")
    parser.add_argument("--out", type=str, default="",
                        help="Optional output directory. Must not already exist.")
    args = parser.parse_args()

    if args.workers < 1 or args.workers > 20:
        raise SystemExit("--workers must be between 1 and 20.")
    if args.thinking_time <= 0 or args.game_time <= 0:
        raise SystemExit("Time budgets must be positive.")

    hashes = verify_engines()
    try:
        import chessmaker  # noqa: F401
        import extension.board_rules  # noqa: F401
    except Exception as exc:
        raise SystemExit(
            "Could not import the coursework environment. Run this file from "
            "the chess project root with chessmaker installed.\n"
            f"Import error: {type(exc).__name__}: {exc}"
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else PROJECT_ROOT / "head_to_head_runs" / f"v69_vs_v71_{stamp}"
    out_dir = out_dir.resolve()
    if out_dir.exists():
        raise SystemExit(f"Output directory already exists; refusing to overwrite: {out_dir}")
    out_dir.mkdir(parents=True)

    puct_enabled = args.puct == "on"
    tasks = build_schedule(args.games, args.thinking_time, args.game_time,
                           args.seed, puct_enabled=puct_enabled)
    manifest = {
        "title": "Frozen v6.9 vs v7.1 adaptive tactical hybrid head-to-head",
        "created_local": datetime.now().isoformat(timespec="seconds"),
        "games_requested": args.games,
        "workers": args.workers,
        "puct_enabled": puct_enabled,
        "thinking_time_s_per_move": args.thinking_time,
        "game_clock_s_per_player": args.game_time,
        "seed": args.seed,
        "pairing": "same board and seed; candidate plays each colour once per pair",
        "boards": list(SAMPLE_NAMES),
        "engine_files": hashes,
        "python": sys.version,
        "output_directory": str(out_dir),
    }
    atomic_json(out_dir / "manifest.json", manifest)

    print("=" * 76)
    print("HEAD-TO-HEAD: FROZEN v6.9 vs v7.1 ADAPTIVE TACTICAL HYBRID")
    print("=" * 76)
    print(f"Games: {args.games} ({args.games // 2} colour-reversed pairs)")
    print(f"Workers: {args.workers}")
    print(f"Root PUCT: {'ENABLED' if puct_enabled else 'DISABLED'}")
    print(f"Per-move budget: {args.thinking_time:.1f}s | Per-player game clock: {args.game_time:.1f}s")
    print("Boards: sample0, sample1, sample2, sample3, sample4")
    for name, info in hashes.items():
        print(f"{name}: {info['sha256']}")
    print(f"Output: {out_dir}")
    print("v6.9 is loaded from its frozen file; neither engine file will be modified.")
    print("-" * 76, flush=True)

    results = []
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        future_map = {pool.submit(play_one_game, task): task for task in tasks}
        for completed, future in enumerate(as_completed(future_map), start=1):
            task = future_map[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {
                    "game_id": task["game_id"],
                    "pair_id": task["pair_id"],
                    "seed": task["seed"],
                    "board": task["board"],
                    "candidate_color": task["candidate_color"],
                    "outcome_for_candidate": "ERROR",
                    "termination": f"Worker exception: {type(exc).__name__}: {exc}",
                    "plies": 0,
                    "wall_time_s": 0.0,
                    "process_cpu_s": 0.0,
                    "v69_search": {},
                    "v71_search": {},
                    "move_metrics": {},
                }
                print(f"ERROR game {task['game_id']}: {row['termination']}")
            results.append(row)
            results.sort(key=lambda r: r["game_id"])
            atomic_json(out_dir / "games.json", results)
            summary = summarize(results)
            elapsed = time.perf_counter() - started
            rate = completed / elapsed * 3600 if elapsed else 0.0
            print(
                f"Completed {completed:>3}/{args.games} | "
                f"v7.1 {summary['wins']}W-{summary['draws']}D-{summary['losses']}L"
                f" | errors {summary['errors']} | {rate:.1f} games/hour"
            )

    total_elapsed = time.perf_counter() - started
    summary = summarize(results)
    summary["elapsed_wall_s"] = round(total_elapsed, 2)
    summary["games_per_hour"] = round(len(results) / total_elapsed * 3600, 2) if total_elapsed else 0
    summary["average_game_wall_s"] = round(
        sum(r.get("wall_time_s", 0) for r in results) / len(results), 2
    ) if results else 0
    summary["candidate_search"] = {}
    for engine_key, label in (("v71_search", "v7.1"), ("v69_search", "v6.9")):
        rows = [r.get(engine_key, {}) for r in results if r.get(engine_key)]
        total_moves = sum(x.get("moves", 0) for x in rows)
        total_nodes = sum(x.get("total_nodes", 0) for x in rows)
        summary["candidate_search"][label] = {
            "moves": total_moves,
            "weighted_avg_depth": round(
                sum(x.get("avg_depth", 0) * x.get("moves", 0) for x in rows) / total_moves, 3
            ) if total_moves else 0,
            "max_depth": max((x.get("max_depth", 0) for x in rows), default=0),
            "total_nodes": total_nodes,
            "puct_calls": sum(x.get("puct_calls", 0) for x in rows),
            "puct_simulations": sum(x.get("puct_simulations", 0) for x in rows),
            "puct_overrides": sum(x.get("puct_overrides", 0) for x in rows),
            "puct_time_s": round(sum(x.get("puct_time_s", 0.0) for x in rows), 4),
        }

    atomic_json(out_dir / "summary.json", summary)

    with (out_dir / "games.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "game_id", "pair_id", "seed", "board", "candidate_color",
            "outcome_for_candidate", "termination", "plies", "wall_time_s", "process_cpu_s",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in results:
            writer.writerow({k: row.get(k, "") for k in fields})

    with (out_dir / "move_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["game_id", "pair_id", "board", "candidate_color", "engine",
                  "ply", "side", "move_time_s", "depth", "nodes", "ebf", "error",
                  "puct_used", "puct_simulations", "puct_time_s", "puct_overrode",
                  "puct_mode", "aborted_depth", "aborted_nodes", "iterations"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in results:
            for engine_name, moves in row.get("move_metrics", {}).items():
                for move in moves:
                    csv_move = dict(move)
                    csv_move["iterations"] = json.dumps(csv_move.get("iterations", []),
                                                       separators=(",", ":"))
                    writer.writerow({
                        "game_id": row["game_id"], "pair_id": row["pair_id"],
                        "board": row["board"], "candidate_color": row["candidate_color"],
                        "engine": engine_name, **csv_move,
                    })

    print("\n" + "=" * 76)
    print("FINAL RESULT — v7.1 scored from its own perspective")
    print(f"{summary['wins']} wins / {summary['draws']} draws / {summary['losses']} losses / {summary['errors']} errors")
    print(f"Score: {summary['candidate_score_pct']:.2f}%")
    print(f"Elapsed: {summary['elapsed_wall_s']:.1f}s | Throughput: {summary['games_per_hour']:.1f} games/hour")
    print("By colour:", json.dumps(summary["by_color"], sort_keys=True))
    print("By board:", json.dumps(summary["by_board"], sort_keys=True))
    print("Search diagnostics:", json.dumps(summary["candidate_search"], sort_keys=True))
    print(f"Saved results to: {out_dir}")
    print("Do not promote v7.1 from this tournament alone; inspect the paired results and validation sample.")
    print("=" * 76)


if __name__ == "__main__":
    main()
