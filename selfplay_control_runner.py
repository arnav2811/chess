#!/usr/bin/env python3
"""Two-sided self-play control runner for Chess Fragments.

Run from the existing coursework project root (the directory containing
`extension/` and the installed `chessmaker` package).

Examples:
  python selfplay_control_runner.py --engine v69 --games 100 --workers 8 --out selfplay_runs/v69_100
  python selfplay_control_runner.py --engine v71 --games 100 --workers 8 --out selfplay_runs/v71_100

Both sides use independent imports of the SAME selected engine file. PUCT is
forced OFF for v7.1. A per-colour RNG stream is maintained independently.
Results are checkpointed in games.jsonl as each game completes and can resume.
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
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENGINE_FILES = {
    "v69": "agent_v69_frozen_overnight.py",
    "v71": "agent_v71_adaptive_tactical_hybrid.py",
}
ENGINE_HASHES = {
    "agent_v69_frozen_overnight.py": "df5cfb7305e8374ed45b6a862e6934cf0f3168e7c7eca9b1c18e9cfd517e08bd",
    "agent_v71_adaptive_tactical_hybrid.py": "488b051b3dce2e49f3b883a16dc12eddaba31510a0596bde7b83247c933865de",
}
BOARDS = ("sample0", "sample1", "sample2", "sample3", "sample4")


def canonical_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_engine_files() -> dict[str, dict[str, str]]:
    result = {}
    for filename, expected in ENGINE_HASHES.items():
        path = ROOT / filename
        if not path.is_file():
            raise SystemExit(f"Missing required engine file: {path}")
        actual = canonical_sha256(path)
        result[filename] = {"path": str(path), "sha256": actual}
        if actual != expected:
            raise SystemExit(
                f"SAFETY STOP: {filename} differs from the audited source.\n"
                f"Expected {expected}\nActual   {actual}\n"
                "No games were started. Restore the bundle's exact source file."
            )
    return result


def load_engine(filename: str, module_name: str, engine: str):
    path = ROOT / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load engine module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if not callable(getattr(module, "agent", None)):
        raise RuntimeError(f"{filename} does not export agent(board, player, var)")
    if engine == "v71":
        if not hasattr(module, "_ENABLE_ROOT_PUCT"):
            raise RuntimeError("The audited v7.1 source has no _ENABLE_ROOT_PUCT switch")
        module._ENABLE_ROOT_PUCT = False
        if hasattr(module, "_ENABLE_STDERR_LOG"):
            module._ENABLE_STDERR_LOG = False
    return module


def make_fresh_board(sample_name: str):
    from chessmaker.chess.base import Player, Board, Square
    from chessmaker.chess.pieces import King, Bishop, Knight, Queen
    from extension.piece_right import Right
    from extension.piece_pawn import Pawn_Q

    white, black = Player("white"), Player("black")
    players = [white, black]
    layouts = {
        "sample0": [
            [Knight(black), Queen(black), King(black), Bishop(black), Right(black)],
            [Pawn_Q(black) for _ in range(5)], [None] * 5,
            [Pawn_Q(white) for _ in range(5)],
            [Right(white), Bishop(white), King(white), Queen(white), Knight(white)],
        ],
        "sample1": [
            [Right(black), Queen(black), King(black), Knight(black), Bishop(black)],
            [Pawn_Q(black) for _ in range(5)], [None] * 5,
            [Pawn_Q(white) for _ in range(5)],
            [Bishop(white), Knight(white), King(white), Queen(white), Right(white)],
        ],
        "sample2": [
            [Right(black), Bishop(black), King(black), Queen(black), Knight(black)],
            [Pawn_Q(black) for _ in range(5)], [None] * 5,
            [Pawn_Q(white) for _ in range(5)],
            [Knight(white), Queen(white), King(white), Bishop(white), Right(white)],
        ],
        "sample3": [
            [Right(black), Queen(black), King(black), Right(black), Knight(black)],
            [Pawn_Q(black) for _ in range(5)], [None] * 5,
            [Pawn_Q(white) for _ in range(5)],
            [Knight(white), Right(white), King(white), Queen(white), Right(white)],
        ],
        "sample4": [
            [Right(black), Bishop(black), King(black), Knight(black), Right(black)],
            [Pawn_Q(black) for _ in range(5)], [None] * 5,
            [Pawn_Q(white) for _ in range(5)],
            [Right(white), Knight(white), King(white), Bishop(white), Right(white)],
        ],
    }
    if sample_name not in layouts:
        raise ValueError(f"Unknown board sample: {sample_name}")
    squares = [[Square(p) if p is not None else Square() for p in row]
               for row in layouts[sample_name]]
    return Board(squares=squares, players=players, turn_iterator=cycle(players)), players


def piece_name(piece: Any) -> str:
    name = type(piece).__name__.lower()
    if name.startswith("pawn_") or name in {"pawnq", "pawn-promotion", "promotingpawn"}:
        return "pawn"
    return name


def board_state(board) -> list[dict[str, Any]]:
    pieces = []
    for p in board.get_pieces():
        pieces.append({
            "piece": piece_name(p),
            "class": type(p).__name__,
            "side": str(p.player.name).lower(),
            "x": int(p.position.x),
            "y": int(p.position.y),
        })
    pieces.sort(key=lambda q: (q["y"], q["x"], q["side"], q["piece"]))
    return pieces


def coord(obj):
    if obj is None:
        return None
    pos = getattr(obj, "position", obj)
    x, y = getattr(pos, "x", None), getattr(pos, "y", None)
    if x is None or y is None:
        return None
    return [int(x), int(y)]


def capture_coords(move) -> list[list[int]]:
    raw = getattr(move, "captures", set()) or set()
    found = []
    try:
        for item in raw:
            c = coord(item)
            if c is not None:
                found.append(c)
    except TypeError:
        pass
    return sorted(found)


def root_candidates(module, limit: int = 8) -> list[dict[str, Any]]:
    rows = getattr(module, "_last_root_evals", []) or []
    out = []
    for item in rows[:limit]:
        try:
            score, piece, move = item
            out.append({
                "score_cp": float(score),
                "piece": piece_name(piece),
                "side": str(piece.player.name).lower(),
                "from": coord(piece.position),
                "to": coord(move),
            })
        except Exception:
            continue
    return out


def stats_snapshot(module) -> dict[str, Any]:
    puct = getattr(module, "_last_puct_stats", {}) or {}
    depth = int(getattr(module, "_last_depth_reached", 0) or 0)
    nodes = int(getattr(module, "_last_nodes_searched", 0) or 0)
    return {
        "depth": depth,
        "nodes": nodes,
        "ebf": float(getattr(module, "_last_branching_factor", 0.0) or 0.0),
        "puct_used": bool(puct.get("used", False)),
        "puct_simulations": int(puct.get("simulations", 0) or 0),
        "puct_time_s": float(puct.get("elapsed_s", 0.0) or 0.0),
        "puct_overrode": bool(puct.get("overrode", False)),
        "puct_mode": str(puct.get("policy_mode", "none")),
        "iterations": list(getattr(module, "_last_iteration_trace", []) or []),
        "aborted_depth": int(getattr(module, "_last_aborted_depth", 0) or 0),
        "aborted_nodes": int(getattr(module, "_last_aborted_nodes", 0) or 0),
        # v6.9 may leave the previous search's root list intact on an opening-book
        # hit; only persist it when this move actually searched nodes.
        "root_candidates": root_candidates(module) if nodes > 0 and depth > 0 else [],
    }


def fresh_rng(seed: int) -> random.Random:
    return random.Random(seed & 0xFFFFFFFFFFFFFFFF)


def call_with_independent_rng(module, board, player, var, rng: random.Random):
    """Temporarily install this colour's RNG state for legacy random fallbacks."""
    outer_state = random.getstate()
    random.setstate(rng.getstate())
    try:
        result = module.agent(board, player, var)
        rng.setstate(random.getstate())
        return result
    finally:
        random.setstate(outer_state)


def terminal_winner(result: str | None) -> tuple[str | None, bool]:
    text = (result or "").lower()
    if "draw" in text:
        return None, True
    m = re.search(r"\b(white|black)\s+loses\b", text)
    if m:
        return ("black" if m.group(1) == "white" else "white"), False
    m = re.search(r"\b(white|black)\s+wins?\b", text)
    if m:
        return m.group(1), False
    return None, False


def play_one_game(task: dict[str, Any]) -> dict[str, Any]:
    from extension.board_utils import copy_piece_move, list_legal_moves_for
    from extension.board_rules import get_result

    engine = task["engine"]
    filename = ENGINE_FILES[engine]
    game_id = int(task["game_id"])
    suffix = f"{engine}_selfplay_game_{game_id}_{task['seed']}"
    white_name, black_name = suffix + "_white", suffix + "_black"
    white_module = black_module = None
    started = time.perf_counter()
    cpu_started = time.process_time()
    moves_log: list[dict[str, Any]] = []
    clocks = {"white": float(task["game_time"]), "black": float(task["game_time"])}
    outcome = "UNKNOWN"
    termination = "Unknown"
    plies = 0
    try:
        # Independent module objects mean each side has its own TT, history,
        # opening cache, repetition memory and internal player clock.
        white_module = load_engine(filename, white_name, engine)
        black_module = load_engine(filename, black_name, engine)
        modules = {"white": white_module, "black": black_module}
        rngs = {
            "white": fresh_rng(task["white_rng_seed"]),
            "black": fresh_rng(task["black_rng_seed"]),
        }
        board, players = make_fresh_board(task["board"])
        player_by_side = {p.name.lower(): p for p in players}
        turn_order = cycle(players)
        game_started = datetime.now().isoformat(timespec="seconds")

        for ply in range(1, 601):
            player = next(turn_order)
            side = str(player.name).lower()
            module = modules[side]
            if clocks[side] <= 0:
                winner = "black" if side == "white" else "white"
                outcome = "WHITE_WIN_BY_CLOCK" if side == "black" else "BLACK_WIN_BY_CLOCK"
                termination = f"{side} exceeded its {task['game_time']:.1f}s player clock"
                break

            pre_state = board_state(board)
            think_started = time.perf_counter()
            error_text = None
            returned_piece = returned_move = None
            try:
                thinking_board = board.clone()
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    returned_piece, returned_move = call_with_independent_rng(
                        module, thinking_board, player, [ply, float(task["thinking_time"])], rngs[side]
                    )
                board, piece, move_option = copy_piece_move(board, returned_piece, returned_move)
            except Exception as exc:
                piece, move_option = None, None
                error_text = f"{type(exc).__name__}: {exc}"
            think_elapsed = time.perf_counter() - think_started
            clocks[side] -= think_elapsed
            snapshot = stats_snapshot(module)

            if error_text:
                moves_log.append({
                    "ply": ply, "side": side, "error": error_text,
                    "think_time_s": round(think_elapsed, 4), "pre_state": pre_state,
                    "search": snapshot,
                })
                winner = "black" if side == "white" else "white"
                outcome = f"{winner.upper()}_WIN_BY_ENGINE_ERROR"
                termination = f"{side} engine exception: {error_text}"
                break

            if not piece or not move_option:
                # A None move is acceptable only when the rules adjudicate the
                # current side as having no legal move.
                try:
                    result = get_result(board)
                except Exception as exc:
                    result = None
                    error_text = f"terminal-check error: {type(exc).__name__}: {exc}"
                winner, is_draw = terminal_winner(result)
                moves_log.append({
                    "ply": ply, "side": side, "move": None,
                    "think_time_s": round(think_elapsed, 4), "pre_state": pre_state,
                    "post_state": board_state(board), "result": result,
                    "search": snapshot, "error": error_text,
                })
                if is_draw:
                    outcome, termination = "DRAW", str(result)
                elif winner:
                    outcome = f"{winner.upper()}_WIN"
                    termination = str(result)
                else:
                    winner = "black" if side == "white" else "white"
                    outcome = (f"{winner.upper()}_WIN_BY_TIMEOUT"
                               if think_elapsed > task["thinking_time"] + 0.25
                               else f"{winner.upper()}_WIN_BY_NO_MOVE")
                    termination = error_text or f"{side} returned no move without a terminal result"
                break

            source = coord(piece.position)
            destination = coord(move_option)
            move_data = {
                "piece": piece_name(piece),
                "piece_class": type(piece).__name__,
                "from": source,
                "to": destination,
                "captures": capture_coords(move_option),
            }
            if think_elapsed > task["thinking_time"] + 0.25:
                moves_log.append({
                    "ply": ply, "side": side, "move": move_data,
                    "think_time_s": round(think_elapsed, 4), "pre_state": pre_state,
                    "search": snapshot, "timeout": True,
                })
                winner = "black" if side == "white" else "white"
                outcome = f"{winner.upper()}_WIN_BY_TIMEOUT"
                termination = f"{side} exceeded {task['thinking_time']:.2f}s move budget"
                break

            try:
                piece.move(move_option)
                result = get_result(board)
            except Exception as exc:
                moves_log.append({
                    "ply": ply, "side": side, "move": move_data,
                    "think_time_s": round(think_elapsed, 4), "pre_state": pre_state,
                    "search": snapshot, "error": f"{type(exc).__name__}: {exc}",
                })
                winner = "black" if side == "white" else "white"
                outcome = f"{winner.upper()}_WIN_BY_ILLEGAL_MOVE"
                termination = f"{side} move application failed: {type(exc).__name__}: {exc}"
                break

            plies = ply
            moves_log.append({
                "ply": ply, "side": side, "move": move_data,
                "think_time_s": round(think_elapsed, 4),
                "clock_remaining_s": round(clocks[side], 3),
                "pre_state": pre_state, "post_state": board_state(board),
                "result": result, "search": snapshot,
            })
            if result:
                winner, is_draw = terminal_winner(result)
                if is_draw:
                    outcome, termination = "DRAW", str(result)
                elif winner:
                    outcome, termination = f"{winner.upper()}_WIN", str(result)
                else:
                    outcome, termination = "UNKNOWN_RESULT", str(result)
                break
        else:
            outcome, termination, winner = "DRAW", "600-ply safety cap", None

        return {
            "game_id": game_id,
            "pair_id": task["pair_id"],
            "pair_variant": task["pair_variant"],
            "engine": engine,
            "board": task["board"],
            "seed": task["seed"],
            "white_rng_seed": task["white_rng_seed"],
            "black_rng_seed": task["black_rng_seed"],
            "winner_color": winner if "winner" in locals() else None,
            "outcome": outcome,
            "termination": termination,
            "plies": plies,
            "wall_time_s": round(time.perf_counter() - started, 3),
            "process_cpu_s": round(time.process_time() - cpu_started, 3),
            "white_clock_remaining_s": round(clocks["white"], 3),
            "black_clock_remaining_s": round(clocks["black"], 3),
            "move_count": len(moves_log),
            "moves": moves_log,
        }
    finally:
        # Do not let imported TT/history state accumulate across hundreds of
        # games inside a reused worker process.
        sys.modules.pop(white_name, None)
        sys.modules.pop(black_name, None)


def build_schedule(engine: str, games: int, seed_base: int,
                   thinking_time: float, game_time: float) -> list[dict[str, Any]]:
    if games < 10 or games % 10 != 0:
        raise ValueError("--games must be a multiple of 10 (e.g. 100) for equal board coverage.")
    pairs = games // 2
    tasks = []
    for pair_index in range(pairs):
        board = BOARDS[pair_index % len(BOARDS)]
        base = seed_base + pair_index * 2
        stream_a, stream_b = base, base + 1
        # Paired random streams: same starting layout and seed pair, but the
        # two colour-specific RNG streams are swapped in the mirror game.
        variants = [
            ("A", stream_a, stream_b),
            ("B", stream_b, stream_a),
        ]
        for variant, white_seed, black_seed in variants:
            tasks.append({
                "game_id": len(tasks) + 1,
                "pair_id": pair_index + 1,
                "pair_variant": variant,
                "engine": engine,
                "board": board,
                "seed": seed_base + pair_index,
                "white_rng_seed": white_seed,
                "black_rng_seed": black_seed,
                "thinking_time": thinking_time,
                "game_time": game_time,
            })
    random.Random(seed_base ^ (0x6A09E667 if engine == "v69" else 0xBB67AE85)).shuffle(tasks)
    return tasks


def summarize(results: list[dict[str, Any]], engine: str, elapsed: float | None = None) -> dict[str, Any]:
    n = len(results)
    outcome_names = (
        "DRAW", "WHITE_WIN", "BLACK_WIN",
        "WHITE_WIN_BY_CLOCK", "BLACK_WIN_BY_CLOCK",
        "WHITE_WIN_BY_TIMEOUT", "BLACK_WIN_BY_TIMEOUT",
        "WHITE_WIN_BY_NO_MOVE", "BLACK_WIN_BY_NO_MOVE",
        "WHITE_WIN_BY_ILLEGAL_MOVE", "BLACK_WIN_BY_ILLEGAL_MOVE",
        "WHITE_WIN_BY_ENGINE_ERROR", "BLACK_WIN_BY_ENGINE_ERROR",
        "UNKNOWN_RESULT", "WORKER_ERROR",
    )
    counts = {k: sum(r.get("outcome") == k for r in results) for k in outcome_names}
    # In self-play the winner is a colour, not an engine; both sides use the same engine.
    white_wins = sum(r.get("winner_color") == "white" for r in results)
    black_wins = sum(r.get("winner_color") == "black" for r in results)
    draws = counts["DRAW"]
    by_board = {}
    for b in BOARDS:
        group = [r for r in results if r["board"] == b]
        by_board[b] = {
            "games": len(group),
            "white_wins": sum(r.get("winner_color") == "white" for r in group),
            "black_wins": sum(r.get("winner_color") == "black" for r in group),
            "draws": sum(r.get("outcome") == "DRAW" for r in group),
        }
    pair_map: dict[int, list[dict[str, Any]]] = {}
    for row in results:
        pair_map.setdefault(int(row["pair_id"]), []).append(row)
    pair_summary = {"white_wins_both": 0, "black_wins_both": 0, "split": 0, "draw_or_mixed": 0}
    for group in pair_map.values():
        winners = [r.get("winner_color") for r in group]
        if len(winners) == 2 and winners == ["white", "white"]:
            pair_summary["white_wins_both"] += 1
        elif len(winners) == 2 and winners == ["black", "black"]:
            pair_summary["black_wins_both"] += 1
        elif len(winners) == 2 and set(winners) == {"white", "black"}:
            pair_summary["split"] += 1
        else:
            pair_summary["draw_or_mixed"] += 1
    summary = {
        "engine": engine,
        "games_completed": n,
        "outcomes": counts,
        "winner_color": {
            "white_wins": white_wins,
            "black_wins": black_wins,
            "draws": draws,
            "white_win_pct_of_decisive": round(100 * white_wins / (white_wins + black_wins), 2)
                if white_wins + black_wins else None,
        },
        "by_board": by_board,
        "paired_rng_stream_results": pair_summary,
        "average_plies": round(sum(r.get("plies", 0) for r in results) / n, 2) if n else 0.0,
        "average_game_wall_s": round(sum(r.get("wall_time_s", 0.0) for r in results) / n, 2) if n else 0.0,
        "total_engine_nodes": sum(
            m.get("search", {}).get("nodes", 0)
            for r in results for m in r.get("moves", [])
        ),
        "max_completed_depth": max((m.get("search", {}).get("depth", 0)
                                     for r in results for m in r.get("moves", [])), default=0),
        "puct_calls": sum(bool(m.get("search", {}).get("puct_used"))
                          for r in results for m in r.get("moves", [])),
        "puct_overrides": sum(bool(m.get("search", {}).get("puct_overrode"))
                              for r in results for m in r.get("moves", [])),
    }
    if elapsed is not None:
        summary["elapsed_wall_s"] = round(elapsed, 2)
        summary["games_per_hour"] = round(n / elapsed * 3600, 2) if elapsed > 0 else 0.0
    return summary


def atomic_json(path: Path, data: Any):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(path)


def write_final_outputs(out_dir: Path, results: list[dict[str, Any]], engine: str, elapsed: float):
    results.sort(key=lambda r: r["game_id"])
    summary = summarize(results, engine, elapsed)
    atomic_json(out_dir / "games.json", results)
    atomic_json(out_dir / "summary.json", summary)

    game_fields = ["game_id", "pair_id", "pair_variant", "engine", "board", "seed",
                   "white_rng_seed", "black_rng_seed", "winner_color", "outcome",
                   "termination", "plies", "wall_time_s", "process_cpu_s",
                   "white_clock_remaining_s", "black_clock_remaining_s", "move_count"]
    with (out_dir / "games.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=game_fields)
        writer.writeheader()
        for row in results:
            writer.writerow({k: row.get(k, "") for k in game_fields})

    move_fields = ["game_id", "pair_id", "board", "engine", "ply", "side", "think_time_s",
                   "piece", "piece_class", "from", "to", "captures", "depth", "nodes", "ebf",
                   "root_candidates", "iterations", "aborted_depth", "aborted_nodes",
                   "puct_used", "puct_simulations", "puct_time_s", "puct_overrode",
                   "pre_state", "post_state", "result", "error", "timeout"]
    with (out_dir / "move_metrics.csv").open("w", newline="", encoding="utf-8") as fcsv, \
         (out_dir / "moves.jsonl").open("w", encoding="utf-8") as fjl:
        writer = csv.DictWriter(fcsv, fieldnames=move_fields)
        writer.writeheader()
        for row in results:
            for move in row.get("moves", []):
                md = move.get("move") or {}
                search = move.get("search") or {}
                flat = {
                    "game_id": row["game_id"], "pair_id": row["pair_id"],
                    "board": row["board"], "engine": engine,
                    "ply": move.get("ply"), "side": move.get("side"),
                    "think_time_s": move.get("think_time_s"),
                    "piece": md.get("piece"), "piece_class": md.get("piece_class"),
                    "from": json.dumps(md.get("from")), "to": json.dumps(md.get("to")),
                    "captures": json.dumps(md.get("captures", [])),
                    "depth": search.get("depth", 0), "nodes": search.get("nodes", 0),
                    "ebf": search.get("ebf", 0.0),
                    "root_candidates": json.dumps(search.get("root_candidates", []), separators=(",", ":")),
                    "iterations": json.dumps(search.get("iterations", []), separators=(",", ":")),
                    "aborted_depth": search.get("aborted_depth", 0),
                    "aborted_nodes": search.get("aborted_nodes", 0),
                    "puct_used": search.get("puct_used", False),
                    "puct_simulations": search.get("puct_simulations", 0),
                    "puct_time_s": search.get("puct_time_s", 0.0),
                    "puct_overrode": search.get("puct_overrode", False),
                    "pre_state": json.dumps(move.get("pre_state", []), separators=(",", ":")),
                    "post_state": json.dumps(move.get("post_state", []), separators=(",", ":")),
                    "result": move.get("result"), "error": move.get("error"),
                    "timeout": move.get("timeout", False),
                }
                writer.writerow(flat)
                fjl.write(json.dumps({
                    "game_id": row["game_id"], "pair_id": row["pair_id"],
                    "board": row["board"], "engine": engine, **move,
                }, separators=(",", ":")) + "\n")


def validate_environment(engine: str):
    import chessmaker  # noqa: F401
    from extension.board_utils import list_legal_moves_for
    for sample in BOARDS:
        board, players = make_fresh_board(sample)
        white_moves = list_legal_moves_for(board, players[0])
        black_moves = list_legal_moves_for(board, players[1])
        if not white_moves or not black_moves:
            raise RuntimeError(f"{sample}: expected legal moves for both sides")
    filename = ENGINE_FILES[engine]
    a = load_engine(filename, f"validate_{engine}_white", engine)
    b = load_engine(filename, f"validate_{engine}_black", engine)
    try:
        if a is b:
            raise RuntimeError("White and Black must have separate module instances")
        if engine == "v71" and (a._ENABLE_ROOT_PUCT or b._ENABLE_ROOT_PUCT):
            raise RuntimeError("v7.1 PUCT did not disable correctly")
    finally:
        sys.modules.pop(f"validate_{engine}_white", None)
        sys.modules.pop(f"validate_{engine}_black", None)
    return "Environment, all five boards, legal move generation, and independent engine imports passed."


def main():
    parser = argparse.ArgumentParser(description="Independent-instance same-engine Chess Fragments self-play controls")
    parser.add_argument("--engine", choices=("v69", "v71"), required=True,
                        help="Engine to use for BOTH White and Black")
    parser.add_argument("--games", type=int, default=100,
                        help="Games to run (must be a multiple of 10; default 100)")
    parser.add_argument("--workers", type=int, default=8,
                        help="Parallel independent games (default 8)")
    parser.add_argument("--thinking-time", type=float, default=14.0)
    parser.add_argument("--game-time", type=float, default=300.0)
    parser.add_argument("--seed", type=int, default=730069)
    parser.add_argument("--out", required=True,
                        help="Output directory, e.g. selfplay_runs/v69_100")
    parser.add_argument("--validate-only", action="store_true",
                        help="Verify hashes, imports, boards, legal moves and separate side modules; run no games")
    parser.add_argument("--resume", action="store_true",
                        help="Resume an existing output directory using games.jsonl checkpoints")
    args = parser.parse_args()

    if not (1 <= args.workers <= 20):
        raise SystemExit("--workers must be between 1 and 20")
    if args.thinking_time <= 0 or args.game_time <= 0:
        raise SystemExit("Time budgets must be positive")

    hashes = verify_engine_files()
    try:
        validation = validate_environment(args.engine)
    except Exception as exc:
        raise SystemExit(f"Coursework environment validation failed: {type(exc).__name__}: {exc}")
    print(validation)
    if args.validate_only:
        print("Validation-only mode: no games were started.")
        return

    tasks = build_schedule(args.engine, args.games, args.seed, args.thinking_time, args.game_time)
    out_dir = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()
    checkpoint = out_dir / "games.jsonl"
    manifest_path = out_dir / "manifest.json"
    manifest_core = {
        "title": "Same-engine two-sided self-play control",
        "engine": args.engine,
        "engine_file": ENGINE_FILES[args.engine],
        "games_requested": args.games,
        "workers_at_start": args.workers,
        "thinking_time_s_per_move": args.thinking_time,
        "game_clock_s_per_player": args.game_time,
        "seed_base": args.seed,
        "boards": list(BOARDS),
        "schedule": "equal board coverage; paired games swap independent White/Black RNG streams",
        "puct_enabled": False if args.engine == "v71" else None,
        "engine_files": hashes,
        "python": sys.version,
    }

    if out_dir.exists():
        if not args.resume:
            raise SystemExit(f"Output directory exists: {out_dir}. Use a new --out or pass --resume.")
        if not manifest_path.is_file() or not checkpoint.is_file():
            raise SystemExit("Cannot resume: manifest.json or games.jsonl is missing.")
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key in ("engine", "engine_file", "games_requested", "thinking_time_s_per_move",
                    "game_clock_s_per_player", "seed_base", "boards", "puct_enabled", "engine_files"):
            if old.get(key) != manifest_core.get(key):
                raise SystemExit(f"Resume safety stop: manifest field {key!r} differs from this run.")
    else:
        out_dir.mkdir(parents=True)
        atomic_json(manifest_path, {
            **manifest_core,
            "created_local": datetime.now().isoformat(timespec="seconds"),
            "output_directory": str(out_dir),
            "notes": "Each side is a separate module import; v7.1 PUCT is forced off.",
        })

    completed: dict[int, dict[str, Any]] = {}
    if checkpoint.exists():
        with checkpoint.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    completed[int(row["game_id"])] = row
                except Exception:
                    # Ignore a truncated final line from an interrupted write.
                    continue
    invalid_ids = set(completed) - {t["game_id"] for t in tasks}
    if invalid_ids:
        raise SystemExit(f"Checkpoint contains unknown game IDs: {sorted(invalid_ids)[:10]}")
    todo = [t for t in tasks if t["game_id"] not in completed]

    print("=" * 78)
    print(f"SELF-PLAY CONTROL: {args.engine.upper()} vs {args.engine.upper()}")
    print(f"Games: {args.games} | Workers: {args.workers} | Boards: 20% each")
    print(f"Thinking limit: {args.thinking_time:.1f}s | Per-side game clock: {args.game_time:.1f}s")
    print(f"PUCT: {'OFF' if args.engine == 'v71' else 'not applicable'}")
    print(f"Completed checkpoint games: {len(completed)} | Remaining: {len(todo)}")
    print(f"Output: {out_dir}")
    print("White and Black use separate module imports and independent random streams.")
    print("=" * 78, flush=True)

    started = time.perf_counter()
    if todo:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(play_one_game, task): task for task in todo}
            for future in as_completed(futures):
                task = futures[future]
                try:
                    row = future.result()
                except Exception as exc:
                    row = {
                        "game_id": task["game_id"], "pair_id": task["pair_id"],
                        "pair_variant": task["pair_variant"], "engine": args.engine,
                        "board": task["board"], "seed": task["seed"],
                        "white_rng_seed": task["white_rng_seed"],
                        "black_rng_seed": task["black_rng_seed"],
                        "winner_color": None, "outcome": "WORKER_ERROR",
                        "termination": f"{type(exc).__name__}: {exc}",
                        "plies": 0, "wall_time_s": 0.0, "process_cpu_s": 0.0,
                        "white_clock_remaining_s": args.game_time,
                        "black_clock_remaining_s": args.game_time,
                        "move_count": 0, "moves": [],
                        "traceback": traceback.format_exc(),
                    }
                completed[row["game_id"]] = row
                with checkpoint.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, separators=(",", ":")) + "\n")
                    f.flush()
                done = len(completed)
                elapsed = time.perf_counter() - started
                rate = (len(todo) and (done - (args.games - len(todo))) / elapsed * 3600) if elapsed else 0.0
                current = summarize(list(completed.values()), args.engine)
                print(
                    f"Completed {done:>3}/{args.games} | "
                    f"White {current['winner_color']['white_wins']} - "
                    f"Black {current['winner_color']['black_wins']} - "
                    f"Draw {current['winner_color']['draws']} | "
                    f"new-run throughput {rate:.1f} games/hour",
                    flush=True,
                )

    elapsed = time.perf_counter() - started
    results = sorted(completed.values(), key=lambda r: r["game_id"])
    write_final_outputs(out_dir, results, args.engine, elapsed)
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    print("\n" + "=" * 78)
    print(f"FINAL SELF-PLAY RESULT: {args.engine.upper()} vs {args.engine.upper()}")
    print(f"Games: {summary['games_completed']} | White wins: {summary['winner_color']['white_wins']} | "
          f"Black wins: {summary['winner_color']['black_wins']} | Draws: {summary['winner_color']['draws']}")
    print(f"White share of decisive games: {summary['winner_color']['white_win_pct_of_decisive']}%")
    print(f"Elapsed: {summary['elapsed_wall_s']:.1f}s | Throughput: {summary['games_per_hour']:.1f} games/hour")
    print("By board:", json.dumps(summary["by_board"], sort_keys=True))
    print("Paired RNG stream results:", json.dumps(summary["paired_rng_stream_results"], sort_keys=True))
    print(f"Saved: {out_dir}")
    print("=" * 78)


if __name__ == "__main__":
    main()
