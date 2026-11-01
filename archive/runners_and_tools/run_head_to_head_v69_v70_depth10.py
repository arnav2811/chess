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
import agent_v70_depth10 as agent_module
agent = agent_module.agent
import agent_v69_stalemate_guard as champion_module
champion_agent = champion_module.agent
from opponent import opponent
from strong_opponent import strong_opponent
from master_opponent import master_opponent

EXPECTED_AGENT_VERSION = "7.0"

def _loaded_agent_info():
    """Detect v7.0 from the actual imported source, including [agent v7.0-depth]."""
    source_path = Path(agent_module.__file__).resolve()
    source = source_path.read_text(encoding="utf-8", errors="replace")
    # Accept the production marker [agent v7.0] and suffixes such as [agent v7.0-depth].
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


def play_one_game(match_id, board_sample_name, candidate_color):
    """Play one game: candidate v7.0-depth10 against frozen v6.9 champion."""
    t0 = time.perf_counter()
    board, players = make_fresh_board(board_sample_name)
    turn_order = cycle(players)
    agent_color = candidate_color  # outcome is always measured for the candidate

    if candidate_color == "white":
        p_white = agent
        p_black = champion_agent
    else:
        p_white = champion_agent
        p_black = agent

    clock = {"white": 300.0, "black": 300.0}
    ply = 1
    termination_reason = "Unknown"
    outcome = "UNKNOWN"

    while True:
        player = next(turn_order)
        temp_board = board.clone()
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
            else:
                termination_reason = f"{player.name} cannot make a legal move or timed out"
                outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        try:
            piece.move(move_opt)
            ply += 1
        except Exception as e:
            termination_reason = f"{player.name} illegal move error: {e}"
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
        "candidate": "v7.0-depth10",
        "opponent": "v6.9",
        "board": board_sample_name,
        "candidate_color": candidate_color,
        "outcome": outcome,
        "termination": termination_reason,
        "plies": ply,
        "duration_s": elapsed,
        "pieces_left": pieces_left,
    }
    print(f"[{match_id:>2d}/10] {board_sample_name} | candidate {candidate_color:>5s} -> {outcome:<4s} | {termination_reason} ({ply} plies, {elapsed}s, {pieces_left} pcs)")
    sys.stdout.flush()
    return result


def main():
    print("=" * 80)
    print("HEAD-TO-HEAD: v7.0 Depth Acceleration Candidate vs frozen v6.9")
    print("10 games: 5 board layouts × both candidate colours; 2 workers")
    print("=" * 80)
    sys.stdout.flush()

    agent_path, agent_version = _loaded_agent_info()
    print(f"Loaded candidate: {agent_path}")
    print(f"Detected agent version: {agent_version} (expected {EXPECTED_AGENT_VERSION})")
    if agent_version != EXPECTED_AGENT_VERSION:
        raise SystemExit(
            f"Wrong candidate version: expected v{EXPECTED_AGENT_VERSION}, found v{agent_version}. "
            "Check agent_v70_depth10.py; v6.9 remains untouched."
        )

    matches = []
    match_id = 1
    for sample in ("sample0", "sample1", "sample2", "sample3", "sample4"):
        for color in ("white", "black"):
            matches.append((match_id, sample, color))
            match_id += 1

    results = []
    with ProcessPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(play_one_game, *match): match[0]
            for match in matches
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                print(f"Match {futures[future]} failed with error: {e}")

    results.sort(key=lambda item: item["match_id"])
    output = "HEAD_TO_HEAD_V69_V70_DEPTH10.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    wins = sum(r["outcome"] == "WIN" for r in results)
    draws = sum(r["outcome"] == "DRAW" for r in results)
    losses = sum(r["outcome"] == "LOSS" for r in results)
    print("\n" + "=" * 80)
    print(f"CANDIDATE SCORE: {wins} W / {draws} D / {losses} L vs v6.9 ({len(results)} games)")
    for color in ("white", "black"):
        group = [r for r in results if r["candidate_color"] == color]
        print(f"Candidate as {color:>5s}: {sum(r['outcome']=='WIN' for r in group)} W / {sum(r['outcome']=='DRAW' for r in group)} D / {sum(r['outcome']=='LOSS' for r in group)} L")
    print(f"Saved: {output}")
    print("Do not promote on this sample alone; repeat with unseen positions/seeds.")
    print("=" * 80)


if __name__ == "__main__":
    main()
