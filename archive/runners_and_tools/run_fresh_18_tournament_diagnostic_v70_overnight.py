import sys
import os
import time
import json
import re
from pathlib import Path
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
import agent_v70 as agent_module
agent = agent_module.agent
from opponent import opponent
from strong_opponent import strong_opponent
from master_opponent import master_opponent

EXPECTED_AGENT_VERSION = "7.0"

def _loaded_agent_info():
    """Detect v7.0 from the actual imported source, including [agent v7.0-exp]."""
    source_path = Path(agent_module.__file__).resolve()
    source = source_path.read_text(encoding="utf-8", errors="replace")
    # Accept the production marker [agent v7.0] and suffixes such as [agent v7.0-exp].
    matches = re.findall(r"\[agent v(\d+(?:\.\d+)?)(?:-[^\]]*)?\]", source)
    if matches:
        version = matches[-1]
    else:
        # Fallback to the descriptive version header if a logging marker is absent.
        header = re.search(r"Chess Fragments AI Agent \(v(\d+\.\d+)", source)
        version = header.group(1) if header else "unknown"
    return source_path, version


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

    while True:
        player = next(turn_order)
        temp_board = board.clone()

        # Check if current player's individual clock has expired
        if clock[player.name] <= 0.0:
            termination_reason = f"{player.name} game time limit exceeded"
            outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        current_fn = p_white if player.name == "white" else p_black
        t_move_start = time.perf_counter()
        try:
            p_piece, p_move_opt = thinking_with_timeout(
                func=current_fn,
                thinking_time=min(THINKING_TIME_BUDGET, clock[player.name]),
                board=temp_board,
                player=player,
                var=[ply, THINKING_TIME_BUDGET]
            )
            board, piece, move_opt = copy_piece_move(board, p_piece, p_move_opt)
        except Exception as e:
            termination_reason = f"{player.name} error: {e}"
            outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        move_duration = time.perf_counter() - t_move_start
        clock[player.name] -= move_duration

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

    agent_path, agent_version = _loaded_agent_info()
    print(f"Loaded agent: {agent_path}")
    print(f"Detected agent version: {agent_version} (expected {EXPECTED_AGENT_VERSION})")
    if agent_version != EXPECTED_AGENT_VERSION:
        raise SystemExit(
            f"Wrong agent version loaded: expected v{EXPECTED_AGENT_VERSION}, found v{agent_version}. "
            "Check agent_v70.py and its version marker; do not replace agent.py unless you intend to."
        )

    print("=" * 80)
    print("RUNNING FRESH 18-MATCH TOURNAMENT (v7.0 Experimental Tactical Resilience)")
    print("=" * 80)
    sys.stdout.flush()

    results = []
    # Use 8 concurrent workers on 16-core CPU for rapid execution & parallel clock stress
    with ProcessPoolExecutor(max_workers=2) as executor:
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
    with open("TOURNAMENT_18_DIAGNOSTIC_RESULTS_V70.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

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
    print("=" * 80)


if __name__ == "__main__":
    main()
