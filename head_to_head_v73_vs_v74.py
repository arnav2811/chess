#!/usr/bin/env python3
"""Paired head-to-head: frozen v7.3 vs candidate v7.4 (PUCT OFF).

Run from the existing Chess Fragments project root, alongside:
  agent_v73_emperor.py
  agent_v74_tactical_guard.py
  extension/ and the installed chessmaker package.

Each PC runs 100 games (50 colour-reversed pairs) using a distinct seed.
The two engines receive isolated Python RNG streams. In each mirrored pair,
the same board and per-engine RNG seeds are used while v7.4 changes colour.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import math
import random
import statistics
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from itertools import cycle
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

V73_FILE = "agent_v73_emperor.py"
V74_FILE = "agent_v74_tactical_guard.py"
ENGINE_FILES = {"v73": V73_FILE, "v74": V74_FILE}
ENGINE_HASHES = {
    V73_FILE: "e2d98f8f6d09cf127d8318cb7944d102cc9fc678dbd9a7d62e11b0d731963c7b",
    V74_FILE: "f071799b7ac06d30a3f912adc541313942e536cf0c1285d5cff294e73abd57dd",
}
BOARDS = ("sample0", "sample1", "sample2", "sample3", "sample4")


def canonical_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_engine_files() -> dict[str, dict[str, str]]:
    details: dict[str, dict[str, str]] = {}
    for filename, expected in ENGINE_HASHES.items():
        path = ROOT / filename
        if not path.is_file():
            raise SystemExit(f"Missing required engine file: {path}")
        actual = canonical_sha256(path)
        details[filename] = {"path": str(path), "sha256": actual}
        if actual != expected:
            raise SystemExit(
                f"SAFETY STOP: {filename} is not the audited engine source.\n"
                f"Expected: {expected}\nActual:   {actual}\n"
                "No games were started. Do not edit either engine to bypass this check."
            )
    return details


def load_engine(engine: str, module_name: str):
    filename = ENGINE_FILES[engine]
    path = ROOT / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load engine module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if not callable(getattr(module, "agent", None)):
        raise RuntimeError(f"{filename} does not expose callable agent()")
    source = path.read_text(encoding="utf-8", errors="replace")
    markers = re.findall(r"\[agent v(\d+(?:\.\d+)?)(?:-[^\]]*)?\]", source)
    expected_version = "7.3" if engine == "v73" else "7.4"
    if not markers or markers[-1] != expected_version:
        raise RuntimeError(f"{filename}: expected version marker {expected_version}; found {markers[-1:]}")
    if engine in ("v73", "v74"):
        for flag in ("_ENABLE_ROOT_PUCT", "_ENABLE_CHECK_EXTENSION",
                     "_ENABLE_ROOT_RANDOM_TIEBREAK"):
            if getattr(module, flag, None) is not False:
                raise RuntimeError(f"{filename}: {flag} must default to OFF")
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
    squares = [[Square(piece) if piece is not None else Square() for piece in row]
               for row in layouts[sample_name]]
    return Board(squares=squares, players=players, turn_iterator=cycle(players)), players


def coord(obj):
    if obj is None:
        return None
    pos = getattr(obj, "position", obj)
    x, y = getattr(pos, "x", None), getattr(pos, "y", None)
    return [int(x), int(y)] if x is not None and y is not None else None


def piece_name(piece: Any) -> str:
    name = type(piece).__name__.lower()
    if name.startswith("pawn_") or name in {"pawnq", "pawn-promotion", "promotingpawn"}:
        return "pawn"
    return name


def board_state(board) -> list[dict[str, Any]]:
    state = []
    for piece in board.get_pieces():
        state.append({
            "piece": piece_name(piece),
            "class": type(piece).__name__,
            "side": str(piece.player.name).lower(),
            "x": int(piece.position.x),
            "y": int(piece.position.y),
        })
    state.sort(key=lambda item: (item["y"], item["x"], item["side"], item["piece"]))
    return state


def capture_coords(move) -> list[list[int]]:
    found = []
    try:
        for item in (getattr(move, "captures", set()) or set()):
            position = coord(item)
            if position is not None:
                found.append(position)
    except TypeError:
        pass
    return sorted(found)


def root_candidates(module, limit: int = 8) -> list[dict[str, Any]]:
    out = []
    for item in (getattr(module, "_last_root_evals", []) or [])[:limit]:
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
    nodes = int(getattr(module, "_last_nodes_searched", 0) or 0)
    depth = int(getattr(module, "_last_depth_reached", 0) or 0)
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
        "tt_hits": int(getattr(module, "_last_tt_hits", 0) or 0),
        "tt_cutoffs": int(getattr(module, "_last_tt_cutoffs", 0) or 0),
        "lmr_one_ply": int(getattr(module, "_last_lmr_one_ply", 0) or 0),
        "lmr_two_ply": int(getattr(module, "_last_lmr_two_ply", 0) or 0),
        "aspiration_fail_low": int(getattr(module, "_last_aspiration_fail_low", 0) or 0),
        "aspiration_fail_high": int(getattr(module, "_last_aspiration_fail_high", 0) or 0),
        "check_extensions": int(getattr(module, "_last_check_extensions", 0) or 0),
        "mobility_extensions": int(getattr(module, "_last_mobility_extensions", 0) or 0),
        "random_tiebreak": bool(getattr(module, "_last_random_tiebreak", False)),
        "material_guard": bool(getattr(module, "_last_material_guard_triggered", False)),
        "material_guard_loss_cp": int(getattr(module, "_last_material_guard_loss", 0) or 0),
        "material_guard_replacement": bool(getattr(module, "_last_material_guard_replacement", False)),
        "promotion_guard": bool(getattr(module, "_last_promotion_guard_triggered", False)),
        "promotion_guard_replacement": bool(getattr(module, "_last_promotion_guard_replacement", False)),
        "root_candidates": root_candidates(module) if nodes > 0 and depth > 0 else [],
    }


def call_with_engine_rng(module, board, player, var, rng: random.Random):
    """Keep v7.3/v7.4 random fallback calls isolated from one another."""
    outer_state = random.getstate()
    random.setstate(rng.getstate())
    try:
        result = module.agent(board, player, var)
        rng.setstate(random.getstate())
        return result
    finally:
        random.setstate(outer_state)


def winner_from_result(result: str | None) -> tuple[str | None, bool]:
    text = (result or "").lower()
    if "draw" in text:
        return None, True
    match = re.search(r"\b(white|black)\s+loses\b", text)
    if match:
        return ("black" if match.group(1) == "white" else "white"), False
    match = re.search(r"\b(white|black)\s+wins?\b", text)
    if match:
        return match.group(1), False
    return None, False


def build_schedule(games: int, seed_base: int, thinking_time: float, game_time: float):
    if games < 10 or games % 10 != 0:
        raise ValueError("--games must be a multiple of 10 and at least 10 for balanced board coverage")
    tasks = []
    pairs = games // 2
    for pair_index in range(pairs):
        board = BOARDS[pair_index % len(BOARDS)]
        pair_seed = seed_base + pair_index * 10
        # The same engine-specific RNG streams are reused for the colour-reversed partner.
        v73_seed = pair_seed + 1
        v74_seed = pair_seed + 2
        for variant, v74_colour in (("A", "white"), ("B", "black")):
            tasks.append({
                "game_id": len(tasks) + 1,
                "pair_id": pair_index + 1,
                "pair_variant": variant,
                "board": board,
                "seed": pair_seed,
                "v74_color": v74_colour,
                "v73_rng_seed": v73_seed,
                "v74_rng_seed": v74_seed,
                "thinking_time": thinking_time,
                "game_time": game_time,
            })
    random.Random(seed_base ^ 0xA5A5_71_69).shuffle(tasks)
    return tasks


def play_one_game(task: dict[str, Any]) -> dict[str, Any]:
    from extension.board_utils import copy_piece_move
    from extension.board_rules import get_result

    game_id = int(task["game_id"])
    suffix = f"h2h_{game_id}_{task['seed']}"
    modules = {}
    names = {"v73": suffix + "_v73", "v74": suffix + "_v74"}
    started = time.perf_counter()
    cpu_started = time.process_time()
    clocks = {"white": float(task["game_time"]), "black": float(task["game_time"])}
    moves_log: list[dict[str, Any]] = []
    outcome = "ERROR"
    termination = "Worker failed before game initialisation"
    winner_engine = None
    winner_color = None
    plies = 0

    try:
        modules["v73"] = load_engine("v73", names["v73"])
        modules["v74"] = load_engine("v74", names["v74"])
        # These should remain true throughout; do not expose a command-line PUCT-on switch.
        for label, module in modules.items():
            if module._ENABLE_ROOT_PUCT is not False:
                raise RuntimeError(f"{label} PUCT did not remain disabled")

        engine_by_side = {
            "white": "v74" if task["v74_color"] == "white" else "v73",
            "black": "v74" if task["v74_color"] == "black" else "v73",
        }
        rngs = {
            "v73": random.Random(task["v73_rng_seed"]),
            "v74": random.Random(task["v74_rng_seed"]),
        }
        board, players = make_fresh_board(task["board"])
        turn_order = cycle(players)

        for ply in range(1, 601):
            player = next(turn_order)
            side = str(player.name).lower()
            engine = engine_by_side[side]
            module = modules[engine]
            if clocks[side] <= 0:
                winner_color = "black" if side == "white" else "white"
                winner_engine = engine_by_side[winner_color]
                outcome = "WIN" if winner_engine == "v74" else "LOSS"
                termination = f"{side} exhausted its {task['game_time']:.1f}s game clock"
                break

            pre_state = board_state(board)
            think_started = time.perf_counter()
            error_text = None
            piece = move_option = None
            try:
                thinking_board = board.clone()
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    returned_piece, returned_move = call_with_engine_rng(
                        module, thinking_board, player,
                        [ply, float(task["thinking_time"])], rngs[engine]
                    )
                board, piece, move_option = copy_piece_move(board, returned_piece, returned_move)
            except Exception as exc:
                error_text = f"{type(exc).__name__}: {exc}"

            elapsed = time.perf_counter() - think_started
            clocks[side] -= elapsed
            search = stats_snapshot(module)
            move_row = {
                "ply": ply,
                "side": side,
                "engine": engine,
                "thinking_time_s": round(elapsed, 4),
                "clock_remaining_s": round(clocks[side], 3),
                "search": search,
                "error": error_text,
            }

            if error_text:
                moves_log.append({**move_row, "pre_state": pre_state})
                winner_color = "black" if side == "white" else "white"
                winner_engine = engine_by_side[winner_color]
                outcome = "WIN" if winner_engine == "v74" else "LOSS"
                termination = f"{engine} ({side}) engine exception: {error_text}"
                break

            if elapsed > task["thinking_time"] + 0.25:
                moves_log.append({**move_row, "pre_state": pre_state, "timeout": True})
                winner_color = "black" if side == "white" else "white"
                winner_engine = engine_by_side[winner_color]
                outcome = "WIN" if winner_engine == "v74" else "LOSS"
                termination = f"{engine} ({side}) exceeded the {task['thinking_time']:.2f}s move budget"
                break

            if not piece or not move_option:
                result = get_result(board)
                winner_color, is_draw = winner_from_result(result)
                moves_log.append({**move_row, "pre_state": pre_state,
                                  "post_state": board_state(board), "result": result})
                if is_draw:
                    outcome, termination = "DRAW", str(result)
                    winner_engine = None
                elif winner_color:
                    winner_engine = engine_by_side[winner_color]
                    outcome = "WIN" if winner_engine == "v74" else "LOSS"
                    termination = str(result)
                else:
                    winner_color = "black" if side == "white" else "white"
                    winner_engine = engine_by_side[winner_color]
                    outcome = "WIN" if winner_engine == "v74" else "LOSS"
                    termination = f"{engine} ({side}) returned no legal move without a terminal result"
                break

            move_data = {
                "piece": piece_name(piece),
                "piece_class": type(piece).__name__,
                "from": coord(piece.position),
                "to": coord(move_option),
                "captures": capture_coords(move_option),
            }
            try:
                piece.move(move_option)
                result = get_result(board)
            except Exception as exc:
                moves_log.append({**move_row, "move": move_data, "pre_state": pre_state,
                                  "error": f"{type(exc).__name__}: {exc}"})
                winner_color = "black" if side == "white" else "white"
                winner_engine = engine_by_side[winner_color]
                outcome = "WIN" if winner_engine == "v74" else "LOSS"
                termination = f"{engine} ({side}) illegal move/application error: {type(exc).__name__}: {exc}"
                break

            plies = ply
            moves_log.append({**move_row, "move": move_data, "pre_state": pre_state,
                              "post_state": board_state(board), "result": result})
            if result:
                winner_color, is_draw = winner_from_result(result)
                if is_draw:
                    outcome, termination = "DRAW", str(result)
                    winner_engine = None
                elif winner_color:
                    winner_engine = engine_by_side[winner_color]
                    outcome = "WIN" if winner_engine == "v74" else "LOSS"
                    termination = str(result)
                else:
                    outcome, termination = "ERROR", f"Unrecognised terminal result: {result}"
                break
        else:
            outcome, termination = "DRAW", "600-ply safety cap"

        return {
            "game_id": game_id,
            "pair_id": task["pair_id"],
            "pair_variant": task["pair_variant"],
            "board": task["board"],
            "seed": task["seed"],
            "v74_color": task["v74_color"],
            "v73_rng_seed": task["v73_rng_seed"],
            "v74_rng_seed": task["v74_rng_seed"],
            "winner_color": winner_color,
            "winner_engine": winner_engine,
            "outcome_for_v74": outcome,
            "termination": termination,
            "plies": plies,
            "wall_time_s": round(time.perf_counter() - started, 3),
            "process_cpu_s": round(time.process_time() - cpu_started, 3),
            "v73_clock_remaining_s": round(clocks["white" if engine_by_side["white"] == "v73" else "black"], 3),
            "v74_clock_remaining_s": round(clocks["white" if engine_by_side["white"] == "v74" else "black"], 3),
            "move_count": len(moves_log),
            "moves": moves_log,
        }
    finally:
        for module_name in names.values():
            sys.modules.pop(module_name, None)


def summarize(results: list[dict[str, Any]], elapsed: float | None = None) -> dict[str, Any]:
    wins = sum(row.get("outcome_for_v74") == "WIN" for row in results)
    draws = sum(row.get("outcome_for_v74") == "DRAW" for row in results)
    losses = sum(row.get("outcome_for_v74") == "LOSS" for row in results)
    errors = sum(row.get("outcome_for_v74") == "ERROR" for row in results)
    n = len(results)
    by_color = {}
    for color in ("white", "black"):
        group = [r for r in results if r.get("v74_color") == color]
        by_color[color] = {
            "games": len(group),
            "W": sum(r.get("outcome_for_v74") == "WIN" for r in group),
            "D": sum(r.get("outcome_for_v74") == "DRAW" for r in group),
            "L": sum(r.get("outcome_for_v74") == "LOSS" for r in group),
            "errors": sum(r.get("outcome_for_v74") == "ERROR" for r in group),
        }
    by_board = {}
    for board in BOARDS:
        group = [r for r in results if r.get("board") == board]
        by_board[board] = {
            "games": len(group),
            "W": sum(r.get("outcome_for_v74") == "WIN" for r in group),
            "D": sum(r.get("outcome_for_v74") == "DRAW" for r in group),
            "L": sum(r.get("outcome_for_v74") == "LOSS" for r in group),
            "errors": sum(r.get("outcome_for_v74") == "ERROR" for r in group),
        }
    pairs = defaultdict(list)
    for row in results:
        pairs[row.get("pair_id")].append(row)
    paired = {"v74_wins_both": 0, "v73_wins_both": 0, "split": 0, "draw_or_error": 0}
    for group in pairs.values():
        if len(group) != 2:
            paired["draw_or_error"] += 1
            continue
        outcomes = [x.get("outcome_for_v74") for x in group]
        if outcomes == ["WIN", "WIN"]:
            paired["v74_wins_both"] += 1
        elif outcomes == ["LOSS", "LOSS"]:
            paired["v73_wins_both"] += 1
        elif set(outcomes) == {"WIN", "LOSS"}:
            paired["split"] += 1
        else:
            paired["draw_or_error"] += 1

    engine_metrics = {}
    for engine in ("v73", "v74"):
        rows = [m for game in results for m in game.get("moves", []) if m.get("engine") == engine]
        total_time = sum(m.get("thinking_time_s", 0.0) for m in rows)
        total_nodes = sum(m.get("search", {}).get("nodes", 0) for m in rows)
        depths = sorted(int(m.get("search", {}).get("depth", 0) or 0) for m in rows)
        p90_index = max(0, min(len(depths) - 1, int(math.ceil(0.90 * len(depths))) - 1)) if depths else 0
        engine_metrics[engine] = {
            "moves": len(rows),
            "weighted_average_depth": round(sum(depths) / len(depths), 3) if depths else 0.0,
            "median_depth": round(statistics.median(depths), 3) if depths else 0.0,
            "p90_depth": depths[p90_index] if depths else 0,
            "moves_depth_ge_6": sum(d >= 6 for d in depths),
            "moves_depth_ge_8": sum(d >= 8 for d in depths),
            "moves_depth_ge_10": sum(d >= 10 for d in depths),
            "max_depth": max(depths, default=0),
            "total_nodes": total_nodes,
            "average_move_time_s": round(total_time / len(rows), 4) if rows else 0.0,
            "aggregate_nps": round(total_nodes / total_time, 1) if total_time else 0.0,
            "puct_calls": sum(bool(m.get("search", {}).get("puct_used")) for m in rows),
            "puct_overrides": sum(bool(m.get("search", {}).get("puct_overrode")) for m in rows),
            "tt_hits": sum(m.get("search", {}).get("tt_hits", 0) for m in rows),
            "tt_cutoffs": sum(m.get("search", {}).get("tt_cutoffs", 0) for m in rows),
            "lmr_one_ply": sum(m.get("search", {}).get("lmr_one_ply", 0) for m in rows),
            "lmr_two_ply": sum(m.get("search", {}).get("lmr_two_ply", 0) for m in rows),
            "aspiration_fail_low": sum(m.get("search", {}).get("aspiration_fail_low", 0) for m in rows),
            "aspiration_fail_high": sum(m.get("search", {}).get("aspiration_fail_high", 0) for m in rows),
            "check_extensions": sum(m.get("search", {}).get("check_extensions", 0) for m in rows),
            "mobility_extensions": sum(m.get("search", {}).get("mobility_extensions", 0) for m in rows),
            "material_guard_triggers": sum(bool(m.get("search", {}).get("material_guard")) for m in rows),
            "material_guard_replacements": sum(bool(m.get("search", {}).get("material_guard_replacement")) for m in rows),
            "promotion_guard_triggers": sum(bool(m.get("search", {}).get("promotion_guard")) for m in rows),
            "promotion_guard_replacements": sum(bool(m.get("search", {}).get("promotion_guard_replacement")) for m in rows),
        }

    summary = {
        "title": "Paired head-to-head: frozen v7.3 vs candidate v7.4 with PUCT disabled",
        "games_completed": n,
        "v74": {"wins": wins, "draws": draws, "losses": losses, "errors": errors,
                "score_pct": round((wins + 0.5 * draws) / n * 100, 2) if n else 0.0},
        "by_v74_colour": by_color,
        "by_board": by_board,
        "paired_colour_reversal": paired,
        "engine_search_metrics": engine_metrics,
        "average_plies": round(sum(r.get("plies", 0) for r in results) / n, 2) if n else 0.0,
        "average_game_wall_s": round(sum(r.get("wall_time_s", 0.0) for r in results) / n, 2) if n else 0.0,
        "puct_disabled_validation": {
            "v74_puct_calls": engine_metrics["v74"]["puct_calls"],
            "v74_puct_overrides": engine_metrics["v74"]["puct_overrides"],
        },
    }
    if elapsed is not None:
        summary["elapsed_wall_s"] = round(elapsed, 2)
        summary["games_per_hour"] = round(n / elapsed * 3600, 2) if elapsed else 0.0
    return summary


def atomic_json(path: Path, data: Any):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(path)


def write_outputs(out_dir: Path, results: list[dict[str, Any]], elapsed: float):
    results.sort(key=lambda row: row["game_id"])
    atomic_json(out_dir / "games.json", results)
    summary = summarize(results, elapsed)
    atomic_json(out_dir / "summary.json", summary)
    game_fields = ["game_id", "pair_id", "pair_variant", "board", "seed", "v74_color",
                   "winner_color", "winner_engine", "outcome_for_v74", "termination", "plies",
                   "wall_time_s", "process_cpu_s", "v73_clock_remaining_s", "v74_clock_remaining_s", "move_count"]
    with (out_dir / "games.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=game_fields)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key, "") for key in game_fields})
    move_fields = ["game_id", "pair_id", "board", "v74_color", "ply", "side", "engine",
                   "thinking_time_s", "clock_remaining_s", "depth", "nodes", "ebf",
                   "puct_used", "puct_simulations", "puct_time_s", "puct_overrode",
                   "aborted_depth", "aborted_nodes", "tt_hits", "tt_cutoffs",
                   "lmr_one_ply", "lmr_two_ply", "aspiration_fail_low", "aspiration_fail_high",
                   "check_extensions", "mobility_extensions", "random_tiebreak",
                   "material_guard", "material_guard_loss_cp", "material_guard_replacement",
                   "promotion_guard", "promotion_guard_replacement",
                   "from", "to", "captures", "error"]
    with (out_dir / "move_metrics.csv").open("w", newline="", encoding="utf-8") as handle, \
         (out_dir / "moves.jsonl").open("w", encoding="utf-8") as move_jsonl:
        writer = csv.DictWriter(handle, fieldnames=move_fields)
        writer.writeheader()
        for game in results:
            for move in game.get("moves", []):
                search = move.get("search", {})
                mdata = move.get("move", {})
                flat = {
                    "game_id": game["game_id"], "pair_id": game["pair_id"],
                    "board": game["board"], "v74_color": game["v74_color"],
                    "ply": move.get("ply"), "side": move.get("side"), "engine": move.get("engine"),
                    "thinking_time_s": move.get("thinking_time_s"),
                    "clock_remaining_s": move.get("clock_remaining_s"),
                    "depth": search.get("depth", 0), "nodes": search.get("nodes", 0),
                    "ebf": search.get("ebf", 0.0),
                    "puct_used": search.get("puct_used", False),
                    "puct_simulations": search.get("puct_simulations", 0),
                    "puct_time_s": search.get("puct_time_s", 0.0),
                    "puct_overrode": search.get("puct_overrode", False),
                    "aborted_depth": search.get("aborted_depth", 0),
                    "aborted_nodes": search.get("aborted_nodes", 0),
                    "tt_hits": search.get("tt_hits", 0),
                    "tt_cutoffs": search.get("tt_cutoffs", 0),
                    "lmr_one_ply": search.get("lmr_one_ply", 0),
                    "lmr_two_ply": search.get("lmr_two_ply", 0),
                    "aspiration_fail_low": search.get("aspiration_fail_low", 0),
                    "aspiration_fail_high": search.get("aspiration_fail_high", 0),
                    "check_extensions": search.get("check_extensions", 0),
                    "mobility_extensions": search.get("mobility_extensions", 0),
                    "random_tiebreak": search.get("random_tiebreak", False),
                    "material_guard": search.get("material_guard", False),
                    "material_guard_loss_cp": search.get("material_guard_loss_cp", 0),
                    "material_guard_replacement": search.get("material_guard_replacement", False),
                    "promotion_guard": search.get("promotion_guard", False),
                    "promotion_guard_replacement": search.get("promotion_guard_replacement", False),
                    "from": json.dumps(mdata.get("from")),
                    "to": json.dumps(mdata.get("to")),
                    "captures": json.dumps(mdata.get("captures", [])),
                    "error": move.get("error"),
                }
                writer.writerow(flat)
                move_jsonl.write(json.dumps({
                    "game_id": game["game_id"], "pair_id": game["pair_id"],
                    "board": game["board"], "v74_color": game["v74_color"], **move,
                }, separators=(",", ":")) + "\n")


def validate_environment():
    import chessmaker  # noqa: F401
    from extension.board_utils import list_legal_moves_for
    for sample in BOARDS:
        board, players = make_fresh_board(sample)
        if not list_legal_moves_for(board, players[0]) or not list_legal_moves_for(board, players[1]):
            raise RuntimeError(f"{sample}: at least one side has no legal opening moves")
    v73 = load_engine("v73", "h2h_validation_v73")
    v74 = load_engine("v74", "h2h_validation_v74")
    try:
        if v73 is v74:
            raise RuntimeError("The engines were not loaded as separate module instances")
        for label, module in (("v7.3", v73), ("v7.4", v74)):
            if module._ENABLE_ROOT_PUCT is not False:
                raise RuntimeError(f"{label} PUCT must be OFF")
            if module._ENABLE_CHECK_EXTENSION is not False:
                raise RuntimeError(f"{label} check extensions must be OFF")
            if module._ENABLE_ROOT_RANDOM_TIEBREAK is not False:
                raise RuntimeError(f"{label} random tie-break must be OFF")
        if getattr(v74, "_MATERIAL_GUARD_MAX_SCORE_LOSS_CP", None) != 150:
            raise RuntimeError("v7.4 material guard score margin must be 150 cp")
    finally:
        sys.modules.pop("h2h_validation_v73", None)
        sys.modules.pop("h2h_validation_v74", None)
    return "Frozen v7.3 and candidate v7.4 imported; all five boards and both opening move lists passed; PUCT/check extensions/random tie-break are OFF; v7.4 guard margin is 150 cp."


def main():
    parser = argparse.ArgumentParser(description="paired frozen v7.3 vs candidate v7.4 head-to-head (PUCT off)")
    parser.add_argument("--games", type=int, default=100, help="Games on this PC; use 100 for the two-PC design")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--thinking-time", type=float, default=14.0)
    parser.add_argument("--game-time", type=float, default=300.0)
    parser.add_argument("--seed", type=int, default=740073)
    parser.add_argument("--out", default="", help="Output directory; not needed with --validate-only")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Resume a stopped run from its games.jsonl checkpoint")
    args = parser.parse_args()

    if args.workers < 1 or args.workers > 20:
        raise SystemExit("--workers must be between 1 and 20")
    if args.thinking_time <= 0 or args.game_time <= 0:
        raise SystemExit("Thinking time and game time must be positive")
    if args.games < 10 or args.games % 10:
        raise SystemExit("--games must be a multiple of 10 and at least 10")

    hashes = verify_engine_files()
    try:
        validation = validate_environment()
    except Exception as exc:
        raise SystemExit(f"Environment validation failed: {type(exc).__name__}: {exc}")
    print(validation, flush=True)
    if args.validate_only:
        print("Validation-only mode: no games were started.")
        return
    if not args.out:
        raise SystemExit("--out is required unless --validate-only is used")

    out_dir = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()

    tasks = build_schedule(args.games, args.seed, args.thinking_time, args.game_time)
    manifest = {
        "title": "Paired head-to-head: frozen v7.3 vs candidate v7.4 (PUCT OFF)",
        "created_local": datetime.now().isoformat(timespec="seconds"),
        "computer_seed": args.seed,
        "games_requested": args.games,
        "workers": args.workers,
        "thinking_time_s_per_move": args.thinking_time,
        "game_clock_s_per_player": args.game_time,
        "boards": list(BOARDS),
        "pairing": "same board and engine-specific RNG seeds; v7.4 plays White and Black once per pair",
        "v74_root_puct": False,
        "v74_check_extensions": False,
        "v74_random_tiebreak": False,
        "v74_material_guard_score_margin_cp": 150,
        "engine_files": hashes,
        "python": sys.version,
        "output_directory": str(out_dir),
    }
    checkpoint = out_dir / "games.jsonl"
    manifest_path = out_dir / "manifest.json"
    completed_results = []
    if out_dir.exists():
        if not args.resume:
            raise SystemExit(f"Output directory already exists; use --resume to continue: {out_dir}")
        if not checkpoint.is_file() or not manifest_path.is_file():
            raise SystemExit("Cannot resume: manifest.json or games.jsonl is missing")
        old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key in ("computer_seed", "games_requested", "thinking_time_s_per_move",
                    "game_clock_s_per_player", "boards", "pairing", "v74_root_puct", "v74_check_extensions", "v74_random_tiebreak", "v74_material_guard_score_margin_cp", "engine_files"):
            if old_manifest.get(key) != manifest.get(key):
                raise SystemExit(f"Cannot resume: manifest setting {key!r} differs from this run")
        with checkpoint.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if line.strip():
                    try:
                        completed_results.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise SystemExit(f"Cannot resume: malformed checkpoint line {line_number}: {exc}")
        ids = [row.get("game_id") for row in completed_results]
        if len(ids) != len(set(ids)):
            raise SystemExit("Cannot resume: duplicate game_id values in checkpoint")
        if any(not isinstance(game_id, int) or not 1 <= game_id <= args.games for game_id in ids):
            raise SystemExit("Cannot resume: checkpoint contains an out-of-range game_id")
        completed_ids = set(ids)
        pending_tasks = [task for task in tasks if task["game_id"] not in completed_ids]
        print(f"Resuming: {len(completed_results)} games already complete; {len(pending_tasks)} remain.")
    else:
        if args.resume:
            raise SystemExit(f"Cannot resume: output directory does not exist: {out_dir}")
        out_dir.mkdir(parents=True)
        atomic_json(manifest_path, manifest)
        pending_tasks = tasks

    print("=" * 78)
    print("HEAD-TO-HEAD: FROZEN v7.3 vs CANDIDATE v7.4 — PUCT OFF")
    print(f"Games: {args.games} ({args.games // 2} colour-reversed pairs; 10 pairs per board at 100 games)")
    print(f"Workers: {args.workers} | Per-move budget: {args.thinking_time:.1f}s | Player clock: {args.game_time:.1f}s")
    print(f"Seed: {args.seed} | Output: {out_dir}")
    print("v7.4 is always the candidate; 50% White / 50% Black. Both engines have isolated RNG streams.")
    for filename, info in hashes.items():
        print(f"{filename}: {info['sha256']}")
    print("=" * 78, flush=True)

    results = list(completed_results)
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        future_map = {pool.submit(play_one_game, task): task for task in pending_tasks}
        for done, future in enumerate(as_completed(future_map), start=len(completed_results) + 1):
            task = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "game_id": task["game_id"], "pair_id": task["pair_id"],
                    "pair_variant": task["pair_variant"], "board": task["board"],
                    "seed": task["seed"], "v74_color": task["v74_color"],
                    "winner_color": None, "winner_engine": None,
                    "outcome_for_v74": "ERROR",
                    "termination": f"Worker exception: {type(exc).__name__}: {exc}",
                    "plies": 0, "wall_time_s": 0.0, "process_cpu_s": 0.0,
                    "v73_clock_remaining_s": None, "v74_clock_remaining_s": None,
                    "move_count": 0, "moves": [],
                }
                print(f"WORKER ERROR game {task['game_id']}: {result['termination']}")
            results.append(result)
            results.sort(key=lambda row: row["game_id"])
            # Durable checkpoint after every completed game.
            with checkpoint.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(result, separators=(",", ":")) + "\n")
            current = summarize(results)
            elapsed = time.perf_counter() - started
            rate = done / elapsed * 3600 if elapsed else 0.0
            print(
                f"Completed {done:>3}/{args.games} | v7.3 {current['v74']['wins']}W-"
                f"{current['v74']['draws']}D-{current['v74']['losses']}L | "
                f"errors {current['v74']['errors']} | {rate:.1f} games/hour",
                flush=True,
            )

    elapsed = time.perf_counter() - started
    write_outputs(out_dir, results, elapsed)
    final = summarize(results, elapsed)
    print("\nFINAL RESULT — v7.4 perspective")
    print(f"v7.4: {final['v74']['wins']}W-{final['v74']['draws']}D-{final['v74']['losses']}L; errors={final['v74']['errors']}")
    print(f"Score: {final['v74']['score_pct']:.2f}%")
    print("By v7.4 colour:", json.dumps(final["by_v74_colour"], sort_keys=True))
    print("By board:", json.dumps(final["by_board"], sort_keys=True))
    print("Paired reversals:", json.dumps(final["paired_colour_reversal"], sort_keys=True))
    print("Search metrics:", json.dumps(final["engine_search_metrics"], sort_keys=True))
    print(f"Elapsed: {elapsed / 60:.1f} min | Results: {out_dir}")
    print("Interpretation rule: a score above 50% favours v7.4; below 50% favours frozen v7.3; draws count as half a point.")


if __name__ == "__main__":
    main()
