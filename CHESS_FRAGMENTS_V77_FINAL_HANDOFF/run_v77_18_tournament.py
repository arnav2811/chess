import sys
import os
import time
import json
import statistics
from itertools import cycle
from concurrent.futures import ProcessPoolExecutor, as_completed

# Framework imports
from chessmaker.chess.base import Player, Board, Square
from chessmaker.chess.pieces import King, Bishop, Knight, Queen
from extension.piece_right import Right
from extension.piece_pawn import Pawn_Q
from extension.board_utils import copy_piece_move
from extension.board_rules import get_result, thinking_with_timeout, THINKING_TIME_BUDGET, GAME_TIME_BUDGET

# Opponents & Agent
import agent_v77_final as v77_engine
agent = v77_engine.agent
from opponent import opponent
from strong_opponent import strong_opponent
from master_opponent import master_opponent


def _piece_records(board):
    """Portable serialisation of a 5x5 board for post-game replay/debugging."""
    records = []
    for piece in board.get_pieces():
        records.append({"piece": type(piece).__name__, "side": piece.player.name,
                        "x": int(piece.position.x), "y": int(piece.position.y)})
    records.sort(key=lambda r: (r["side"], r["piece"], r["y"], r["x"]))
    return records


def _coord_records(items):
    out = []
    for item in (items or []):
        try:
            out.append([int(item.x), int(item.y)])
        except Exception:
            try:
                out.append([int(item.position.x), int(item.position.y)])
            except Exception:
                continue
    return out


def make_fresh_board(sample_name):
    white = Player("white")
    black = Player("black")
    players = [white, black]

    if sample_name == "sample0":
        squares = [
            [Square(Knight(black)), Square(Queen(black)), Square(King(black)), Square(Bishop(black)), Square(Right(black))],
            [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black))],
            [Square(), Square(), Square(), Square(), Square()],
            [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white))],
            [Square(Right(white)), Square(Bishop(white)), Square(King(white)), Square(Queen(white)), Square(Knight(white))],
        ]
    elif sample_name == "sample1":
        squares = [
            [Square(Right(black)), Square(Queen(black)), Square(King(black)), Square(Knight(black)), Square(Bishop(black))],
            [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black))],
            [Square(), Square(), Square(), Square(), Square()],
            [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white))],
            [Square(Bishop(white)), Square(Knight(white)), Square(King(white)), Square(Queen(white)), Square(Right(white))],
        ]
    elif sample_name == "sample2":
        squares = [
            [Square(Right(black)), Square(Bishop(black)), Square(King(black)), Square(Queen(black)), Square(Knight(black))],
            [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black))],
            [Square(), Square(), Square(), Square(), Square()],
            [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white))],
            [Square(Knight(white)), Square(Queen(white)), Square(King(white)), Square(Bishop(white)), Square(Right(white))],
        ]
    elif sample_name == "sample3":
        squares = [
            [Square(Right(black)), Square(Queen(black)), Square(King(black)), Square(Right(black)), Square(Knight(black))],
            [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black))],
            [Square(), Square(), Square(), Square(), Square()],
            [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white))],
            [Square(Knight(white)), Square(Right(white)), Square(King(white)), Square(Queen(white)), Square(Right(white))],
        ]
    elif sample_name == "sample4":
        squares = [
            [Square(Right(black)), Square(Bishop(black)), Square(King(black)), Square(Knight(black)), Square(Right(black))],
            [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black))],
            [Square(), Square(), Square(), Square(), Square()],
            [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white))],
            [Square(Right(white)), Square(Knight(white)), Square(King(white)), Square(Bishop(white)), Square(Right(white))],
        ]
    else:
        raise ValueError(f"Unknown board sample: {sample_name}")

    board = Board(squares=squares, players=players, turn_iterator=cycle(players))
    return board, players


def play_one_game(match_id, tier, opp_name, board_sample_name, agent_color):
    """Executes a single game and returns a detailed result dictionary."""
    t0 = time.perf_counter()
    board, players = make_fresh_board(board_sample_name)
    turn_order = cycle(players)

    opp_map = {
        "Baseline": opponent,
        "Strong": strong_opponent,
        "Master": master_opponent,
    }
    opp_fn = opp_map[opp_name]

    if agent_color == "white":
        p_white = agent
        p_black = opp_fn
    else:
        p_white = opp_fn
        p_black = agent

    # Individual clocks: 300.0s for White, 300.0s for Black
    clock = {"white": 300.0, "black": 300.0}
    ply = 1
    termination_reason = "Unknown"
    outcome = "UNKNOWN"
    move_metrics = []
    move_history = []
    initial_position = _piece_records(board)

    while True:
        player = next(turn_order)
        temp_board = board.clone()

        # Check if current player's individual clock has expired
        if clock[player.name] <= 0.0:
            termination_reason = f"{player.name} game time limit exceeded"
            outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        current_fn = p_white if player.name == "white" else p_black
        is_engine_turn = player.name == agent_color
        stats_before = len(getattr(v77_engine, "_move_stats_log", [])) if is_engine_turn else 0
        t_move_start = time.perf_counter()
        try:
            p_piece, p_move_opt = thinking_with_timeout(
                func=current_fn,
                thinking_time=min(THINKING_TIME_BUDGET, clock[player.name]),
                board=temp_board,
                player=player,
                var=[ply, THINKING_TIME_BUDGET]
            )
            if p_piece is not None and p_move_opt is not None:
                try:
                    move_history.append({
                        "ply": ply, "side": player.name,
                        "engine": "v7.7" if is_engine_turn else opp_name,
                        "piece": type(p_piece).__name__,
                        "from": [int(p_piece.position.x), int(p_piece.position.y)],
                        "to": [int(p_move_opt.position.x), int(p_move_opt.position.y)],
                        "captures": _coord_records(getattr(p_move_opt, "captures", set())),
                        "board_before": _piece_records(board),
                    })
                except Exception:
                    move_history.append({"ply": ply, "side": player.name,
                                         "engine": "v7.7" if is_engine_turn else opp_name,
                                         "serialization_error": True})
            board, piece, move_opt = copy_piece_move(board, p_piece, p_move_opt)
        except Exception as e:
            termination_reason = f"{player.name} error: {e}"
            outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        move_duration = time.perf_counter() - t_move_start
        clock[player.name] -= move_duration
        if is_engine_turn:
            engine_log = getattr(v77_engine, "_move_stats_log", [])
            if len(engine_log) > stats_before:
                latest = engine_log[-1]
                move_metrics.append({
                    "ply": ply,
                    "side": player.name,
                    "depth": latest.get("depth", 0),
                    "nodes": latest.get("nodes", 0),
                    "time_s": latest.get("time_s", round(move_duration, 3)),
                    "aborted_depth": latest.get("aborted_depth", 0),
                    "aborted_nodes": latest.get("aborted_nodes", 0),
                    "tt_hits": latest.get("tt_hits", 0),
                    "tt_cutoffs": latest.get("tt_cutoffs", 0),
                    "lmr_one_ply": latest.get("lmr_one_ply", 0),
                    "lmr_two_ply": latest.get("lmr_two_ply", 0),
                    "tablebase_ready": latest.get("tablebase_ready", False),
                    "tablebase_probes": latest.get("tablebase_probes", 0),
                    "tablebase_hits": latest.get("tablebase_hits", 0),
                    "tablebase_wins": latest.get("tablebase_wins", 0),
                    "tablebase_losses": latest.get("tablebase_losses", 0),
                    "tablebase_draws": latest.get("tablebase_draws", 0),
                    "tablebase_root_solved": latest.get("tablebase_root_solved", False),
                    "material_guard": latest.get("material_guard", False),
                    "material_guard_replacement": latest.get("material_guard_replacement", False),
                    "promotion_guard": latest.get("promotion_guard", False),
                    "promotion_guard_replacement": latest.get("promotion_guard_replacement", False),
                    "tablebase_repeat_avoided": latest.get("tablebase_repeat_avoided", False),
                    "stalemate_guard_calls": latest.get("stalemate_guard_calls", 0),
                    "stalemate_guard_threats": latest.get("stalemate_guard_threats", 0),
                    "stalemate_guard_inconclusive": latest.get("stalemate_guard_inconclusive", 0),
                    "stalemate_guard_replacements": latest.get("stalemate_guard_replacements", 0),
                })

        if (not piece) or (not move_opt):
            res = get_result(board)
            if res:
                termination_reason = res
                res_low = res.lower()
                if "draw" in res_low:
                    outcome = "DRAW"
                elif f"{agent_color} loses" in res_low:
                    outcome = "LOSS"
                else:
                    outcome = "WIN"
            elif p_piece == 99:
                termination_reason = f"{player.name} thinking time out"
                outcome = "LOSS" if player.name == agent_color else "WIN"
            else:
                termination_reason = f"{player.name} cannot make a legal move"
                outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        try:
            piece.move(move_opt)
            ply += 1
        except Exception as e:
            termination_reason = f"{player.name} illegal move error"
            outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        res = get_result(board)
        if res:
            termination_reason = res
            res_low = res.lower()
            if "draw" in res_low:
                outcome = "DRAW"
            elif f"{agent_color} loses" in res_low:
                outcome = "LOSS"
            else:
                outcome = "WIN"
            break

    elapsed = round(time.perf_counter() - t0, 1)
    pieces_left = len(list(board.get_pieces()))

    result = {
        "match_id": match_id,
        "tier": tier,
        "opp_name": opp_name,
        "board": board_sample_name,
        "agent_color": agent_color,
        "outcome": outcome,
        "termination": termination_reason,
        "plies": ply,
        "duration_s": elapsed,
        "pieces_left": pieces_left,
        "initial_position": initial_position,
        "move_history": move_history,
        "move_metrics": move_metrics,
    }
    print(f"[{match_id:>2d}/18] Tier {tier} ({opp_name}) | {board_sample_name} | Agent {agent_color:>5s} -> {outcome:<4s} | {termination_reason} ({ply} plies, {elapsed}s, {pieces_left} pcs)")
    sys.stdout.flush()
    return result


def main():
    matches = [
        # Tier 1: Baseline (D3)
        (1, 1, "Baseline", "sample0", "white"),
        (2, 1, "Baseline", "sample0", "black"),
        (3, 1, "Baseline", "sample1", "white"),
        (4, 1, "Baseline", "sample1", "black"),
        (5, 1, "Baseline", "sample2", "white"),
        (6, 1, "Baseline", "sample2", "black"),

        # Tier 2: Strong (D5)
        (7, 2, "Strong", "sample0", "white"),
        (8, 2, "Strong", "sample0", "black"),
        (9, 2, "Strong", "sample1", "white"),
        (10, 2, "Strong", "sample1", "black"),
        (11, 2, "Strong", "sample2", "white"),
        (12, 2, "Strong", "sample2", "black"),

        # Tier 3: Master (D7)
        (13, 3, "Master", "sample0", "white"),
        (14, 3, "Master", "sample0", "black"),
        (15, 3, "Master", "sample1", "white"),
        (16, 3, "Master", "sample1", "black"),
        (17, 3, "Master", "sample2", "white"),
        (18, 3, "Master", "sample2", "black"),
    ]

    print("=" * 80)
    print("RUNNING FRESH 18-MATCH v7.7 EXACT-TABLEBASE THREE-TIER BENCHMARK")
    print("=" * 80)
    sys.stdout.flush()

    results = []
    # Use a bounded worker pool; concurrent games are independent
    with ProcessPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(play_one_game, m[0], m[1], m[2], m[3], m[4]): m[0]
            for m in matches
        }
        for future in as_completed(futures):
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                m_id = futures[future]
                print(f"Match {m_id} failed with error: {e}")

    results.sort(key=lambda r: r["match_id"])

    # Save to JSON
    with open("V77_TOURNAMENT_18_RESULTS.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Aggregate the engine's per-move instrumentation. The primary tournament
    # JSON remains a list for compatibility with the earlier result files.
    all_metrics = [m for game in results for m in game.get("move_metrics", [])]
    total_nodes = sum(m.get("nodes", 0) for m in all_metrics)
    total_time = sum(m.get("time_s", 0.0) for m in all_metrics)
    metric_summary = {
        "candidate_build": "v7.7-exact-tablebase",
        "engine_decisions": len(all_metrics),
        "average_completed_depth": round(sum(m.get("depth", 0) for m in all_metrics) / len(all_metrics), 3) if all_metrics else None,
        "median_completed_depth": statistics.median(m.get("depth", 0) for m in all_metrics) if all_metrics else None,
        "average_depth_excluding_zero_node_turns": round(
            sum(m.get("depth", 0) for m in all_metrics if m.get("nodes", 0) > 0)
            / max(1, sum(1 for m in all_metrics if m.get("nodes", 0) > 0)), 3
        ),
        "total_nodes": total_nodes,
        "total_engine_time_s": round(total_time, 3),
        "aggregate_nps": round(total_nodes / max(total_time, 0.001), 2),
        "decisions_depth_ge_6": sum(1 for m in all_metrics if m.get("depth", 0) >= 6),
        "decisions_depth_ge_8": sum(1 for m in all_metrics if m.get("depth", 0) >= 8),
        "aborted_depth_decisions": sum(1 for m in all_metrics if m.get("aborted_depth", 0) > 0),
        "tablebase_probes": sum(m.get("tablebase_probes", 0) for m in all_metrics),
        "tablebase_hits": sum(m.get("tablebase_hits", 0) for m in all_metrics),
        "tablebase_wins": sum(m.get("tablebase_wins", 0) for m in all_metrics),
        "tablebase_losses": sum(m.get("tablebase_losses", 0) for m in all_metrics),
        "tablebase_draws": sum(m.get("tablebase_draws", 0) for m in all_metrics),
        "tablebase_root_solved_decisions": sum(1 for m in all_metrics if m.get("tablebase_root_solved", False)),
        "material_guard_triggers": sum(1 for m in all_metrics if m.get("material_guard", False)),
        "material_guard_replacements": sum(1 for m in all_metrics if m.get("material_guard_replacement", False)),
        "promotion_guard_triggers": sum(1 for m in all_metrics if m.get("promotion_guard", False)),
        "promotion_guard_replacements": sum(1 for m in all_metrics if m.get("promotion_guard_replacement", False)),
        "tablebase_repeat_avoided_decisions": sum(1 for m in all_metrics if m.get("tablebase_repeat_avoided", False)),
        "stalemate_guard_calls": sum(m.get("stalemate_guard_calls", 0) for m in all_metrics),
        "stalemate_guard_threats": sum(m.get("stalemate_guard_threats", 0) for m in all_metrics),
        "stalemate_guard_inconclusive": sum(m.get("stalemate_guard_inconclusive", 0) for m in all_metrics),
        "stalemate_guard_replacements": sum(m.get("stalemate_guard_replacements", 0) for m in all_metrics),
        "per_move_metrics_included": True,
        "full_move_history_included": True,
    }
    with open("V77_TOURNAMENT_18_METRICS_SUMMARY.json", "w", encoding="utf-8") as f:
        json.dump(metric_summary, f, indent=2)

    # Print Summary Table
    wins = sum(1 for r in results if r["outcome"] == "WIN")
    losses = sum(1 for r in results if r["outcome"] == "LOSS")
    draws = sum(1 for r in results if r["outcome"] == "DRAW")

    t1_wins = sum(1 for r in results if r["tier"] == 1 and r["outcome"] == "WIN")
    t2_wins = sum(1 for r in results if r["tier"] == 2 and r["outcome"] == "WIN")
    t3_wins = sum(1 for r in results if r["tier"] == 3 and r["outcome"] == "WIN")

    print("\n" + "=" * 80)
    print(f"TOURNAMENT FINAL SCORECARD: {wins} WINS / {draws} DRAWS / {losses} LOSSES ({wins/len(results)*100:.1f}% Win Rate)")
    print(f"   Tier 1 (Baseline D3): {t1_wins}/6 ({t1_wins/6*100:.1f}%)")
    print(f"   Tier 2 (Strong D5):   {t2_wins}/6 ({t2_wins/6*100:.1f}%)")
    print(f"   Tier 3 (Master D7):   {t3_wins}/6 ({t3_wins/6*100:.1f}%)")
    print(f"   Engine avg depth: {metric_summary['average_completed_depth']} | "
          f"aggregate NPS: {metric_summary['aggregate_nps']} | "
          f"TB hits/probes: {metric_summary['tablebase_hits']}/{metric_summary['tablebase_probes']} | "
          f"root TB solves: {metric_summary['tablebase_root_solved_decisions']}")
    print("Metrics saved to V77_TOURNAMENT_18_METRICS_SUMMARY.json")
    print("=" * 80)


if __name__ == "__main__":
    main()
