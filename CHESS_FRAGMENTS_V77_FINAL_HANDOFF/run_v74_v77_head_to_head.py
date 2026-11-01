"""Paired-colour v7.7 vs v7.4 head-to-head on all five official boards.

Runs 10 games: each engine gets White and Black once on each board.
Writes V77_V74_H2H_10.json with outcomes and per-move search metrics.
Requires the project's ChessMaker dependency and existing opponent/board helpers.
"""
import json
import random
import sys
import time
import statistics
from concurrent.futures import ProcessPoolExecutor, as_completed

import agent_v74_tactical_guard_v77baseline as v74
import agent_v77_final as v77
from extension.board_rules import (
    THINKING_TIME_BUDGET, GAME_TIME_BUDGET,
    get_result, thinking_with_timeout,
)
from extension.board_utils import copy_piece_move
from run_v77_18_tournament import make_fresh_board, _piece_records, _coord_records


def play_one(game_id, pair_id, board_name, candidate_color, seed):
    random.seed(seed)
    board, players = make_fresh_board(board_name)
    turn_order = iter(())
    from itertools import cycle
    turn_order = cycle(players)
    clock = {"white": float(GAME_TIME_BUDGET), "black": float(GAME_TIME_BUDGET)}
    ply = 1
    termination = "Unknown"
    outcome = "UNKNOWN"
    move_metrics = []
    move_history = []
    initial_position = _piece_records(board)
    candidate_engine = v77

    while True:
        player = next(turn_order)
        if clock[player.name] <= 0:
            termination = f"{player.name} game clock exhausted"
            outcome = "LOSS" if player.name == candidate_color else "WIN"
            break
        is_candidate_turn = player.name == candidate_color
        engine = candidate_engine if is_candidate_turn else v74
        temp_board = board.clone()
        started = time.perf_counter()
        try:
            p_piece, p_move = thinking_with_timeout(
                func=engine.agent,
                thinking_time=min(THINKING_TIME_BUDGET, clock[player.name]),
                board=temp_board,
                player=player,
                var=[ply, THINKING_TIME_BUDGET],
            )
        except Exception as exc:
            termination = f"{player.name} agent error: {type(exc).__name__}: {exc}"
            outcome = "LOSS" if is_candidate_turn else "WIN"
            break
        spent = time.perf_counter() - started
        clock[player.name] -= spent

        stats_log = getattr(engine, "_move_stats_log", [])
        if stats_log:
            latest = stats_log[-1]
            move_metrics.append({
                "ply": ply,
                "engine": "v7.7" if is_candidate_turn else "v7.4",
                "side": player.name,
                "depth": latest.get("depth", 0),
                "nodes": latest.get("nodes", 0),
                "time_s": latest.get("time_s", round(spent, 3)),
                "nps": (round(latest.get("nodes", 0) / max(latest.get("time_s", spent), 0.001), 1)),
                "tablebase_probes": latest.get("tablebase_probes", 0),
                "tablebase_hits": latest.get("tablebase_hits", 0),
                "tablebase_root_solved": latest.get("tablebase_root_solved", False),
                "aborted_depth": latest.get("aborted_depth", 0),
                "aborted_nodes": latest.get("aborted_nodes", 0),
                "tablebase_repeat_avoided": latest.get("tablebase_repeat_avoided", False),
                "stalemate_guard_calls": latest.get("stalemate_guard_calls", 0),
                "stalemate_guard_threats": latest.get("stalemate_guard_threats", 0),
                "stalemate_guard_inconclusive": latest.get("stalemate_guard_inconclusive", 0),
                "stalemate_guard_replacements": latest.get("stalemate_guard_replacements", 0),
            })

        if (not p_piece) or (not p_move):
            res = get_result(board)
            if res:
                termination = res
                low = res.lower()
                outcome = "DRAW" if "draw" in low else (
                    "LOSS" if f"{candidate_color} loses" in low else "WIN")
            else:
                termination = f"{player.name} returned no move / timed out"
                outcome = "LOSS" if is_candidate_turn else "WIN"
            break

        if p_piece is not None and p_move is not None:
            try:
                move_history.append({
                    "ply": ply, "side": player.name,
                    "engine": "v7.7" if is_candidate_turn else "v7.4",
                    "piece": type(p_piece).__name__,
                    "from": [int(p_piece.position.x), int(p_piece.position.y)],
                    "to": [int(p_move.position.x), int(p_move.position.y)],
                    "captures": _coord_records(getattr(p_move, "captures", set())),
                    "board_before": _piece_records(board),
                })
            except Exception:
                move_history.append({"ply": ply, "side": player.name,
                                     "engine": "v7.7" if is_candidate_turn else "v7.4",
                                     "serialization_error": True})
        try:
            board, piece, move = copy_piece_move(board, p_piece, p_move)
            if piece is None or move is None:
                raise RuntimeError("could not map selected move to live board")
            piece.move(move)
        except Exception as exc:
            termination = f"{player.name} move application error: {type(exc).__name__}: {exc}"
            outcome = "LOSS" if is_candidate_turn else "WIN"
            break

        ply += 1
        res = get_result(board)
        if res:
            termination = res
            low = res.lower()
            outcome = "DRAW" if "draw" in low else (
                "LOSS" if f"{candidate_color} loses" in low else "WIN")
            break

    return {
        "game_id": game_id,
        "pair_id": pair_id,
        "board": board_name,
        "candidate_color": candidate_color,
        "seed": seed,
        "outcome_for_v77": outcome,
        "termination": termination,
        "plies": ply,
        "candidate_clock_remaining_s": round(clock[candidate_color], 3),
        "initial_position": initial_position,
        "move_history": move_history,
        "move_metrics": move_metrics,
    }


def main():
    boards = ["sample0", "sample1", "sample2", "sample3", "sample4"]
    games = []
    gid = 1
    for pair_id, board_name in enumerate(boards, start=1):
        # Matched colour pair: same board and seed, candidate changes colour.
        seed = 750000 + pair_id
        for color in ("white", "black"):
            games.append((gid, pair_id, board_name, color, seed))
            gid += 1

    print("=" * 78)
    print("v7.7 EXACT TABLEBASE vs v7.4 TACTICAL GUARD — 10 paired-colour games")
    print("=" * 78)
    results = []
    with ProcessPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(play_one, *g): g[0] for g in games}
        for future in as_completed(futures):
            game_id = futures[future]
            try:
                result = future.result()
                results.append(result)
                print(f"[{result['game_id']:02d}/10] {result['board']} | v7.7 {result['candidate_color']:>5s} | "
                      f"{result['outcome_for_v77']:<4s} | {result['plies']} plies | {result['termination']}")
            except Exception as exc:
                results.append({"game_id": game_id, "outcome_for_v77": "ERROR", "error": repr(exc)})
                print(f"[{game_id:02d}/10] ERROR: {exc}")
            sys.stdout.flush()

    results.sort(key=lambda x: x["game_id"])
    complete = [r for r in results if r.get("outcome_for_v77") in ("WIN", "DRAW", "LOSS")]
    wins = sum(r["outcome_for_v77"] == "WIN" for r in complete)
    draws = sum(r["outcome_for_v77"] == "DRAW" for r in complete)
    losses = sum(r["outcome_for_v77"] == "LOSS" for r in complete)
    all_metrics = [m for r in complete for m in r.get("move_metrics", [])]
    summary = {}
    for engine in ("v7.4", "v7.7"):
        metrics = [m for m in all_metrics if m["engine"] == engine]
        depths = [m["depth"] for m in metrics]
        times = [m["time_s"] for m in metrics]
        nodes = [m["nodes"] for m in metrics]
        summary[engine] = {
            "decisions": len(metrics),
            "average_completed_depth": round(sum(depths) / len(depths), 3) if depths else None,
            "median_completed_depth": statistics.median(depths) if depths else None,
            "average_nodes": round(sum(nodes) / len(nodes), 1) if nodes else None,
            "average_thinking_time_s": round(sum(times) / len(times), 3) if times else None,
            "average_nps": round(sum(nodes) / max(sum(times), 0.001), 2) if times else None,
            "average_depth_excluding_zero_node_turns": round(
                sum(m["depth"] for m in metrics if m.get("nodes", 0) > 0)
                / max(1, sum(1 for m in metrics if m.get("nodes", 0) > 0)), 3
            ),
            "zero_node_decisions": sum(1 for m in metrics if m.get("nodes", 0) == 0),
            "decisions_depth_ge_6": sum(1 for m in metrics if m.get("depth", 0) >= 6),
            "decisions_depth_ge_8": sum(1 for m in metrics if m.get("depth", 0) >= 8),
            "aborted_depth_decisions": sum(1 for m in metrics if m.get("aborted_depth", 0) > 0),
            "tablebase_probes": sum(m.get("tablebase_probes", 0) for m in metrics),
            "tablebase_hits": sum(m.get("tablebase_hits", 0) for m in metrics),
            "tablebase_wins": sum(m.get("tablebase_wins", 0) for m in metrics),
            "tablebase_losses": sum(m.get("tablebase_losses", 0) for m in metrics),
            "tablebase_draws": sum(m.get("tablebase_draws", 0) for m in metrics),
            "tablebase_root_solved_decisions": sum(
                1 for m in metrics if m.get("tablebase_root_solved", False)
            ),
            "tablebase_repeat_avoided_decisions": sum(
                1 for m in metrics if m.get("tablebase_repeat_avoided", False)
            ),
            "stalemate_guard_calls": sum(m.get("stalemate_guard_calls", 0) for m in metrics),
            "stalemate_guard_threats": sum(m.get("stalemate_guard_threats", 0) for m in metrics),
            "stalemate_guard_inconclusive": sum(m.get("stalemate_guard_inconclusive", 0) for m in metrics),
            "stalemate_guard_replacements": sum(m.get("stalemate_guard_replacements", 0) for m in metrics),
        }
    report = {
        "title": "v7.7 final candidate vs v7.4 paired-colour head-to-head",
        "candidate_build": "v7.7-final-stalemate-repetition-guards",
        "games_requested": len(games),
        "games_completed": len(complete),
        "v77_record": {"wins": wins, "draws": draws, "losses": losses,
                       "score_pct": round((wins + 0.5 * draws) / len(complete) * 100, 2) if complete else None},
        "engine_metrics": summary,
        "games": results,
    }
    with open("V77_V74_H2H_10.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("\n" + "=" * 78)
    print(f"v7.7 W-D-L: {wins}-{draws}-{losses} / {len(complete)} games")
    for engine, metrics in summary.items():
        print(f"{engine}: avg depth={metrics['average_completed_depth']}, "
              f"avg nodes={metrics['average_nodes']}, avg time={metrics['average_thinking_time_s']}s, "
              f"TB={metrics['tablebase_hits']}/{metrics['tablebase_probes']} "
                      f"root-solves={metrics['tablebase_root_solved_decisions']}")
    print("Saved V77_V74_H2H_10.json")


if __name__ == "__main__":
    main()
