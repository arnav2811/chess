"""
ui_server.py — Chess Fragments Web UI Server
============================================
Serves a classy, chess.com-inspired browser interface.

Features:
- Real-time 5x5 board visualization with WebSockets
- Human vs AI & AI vs AI Watch mode
- Full Move Review / Scrubbing across all moves
- Full Move Undo (take back moves against AI or in analysis)
- Accurate Millisecond-Precision Chess.com Clocks (1m, 3m, 5m, 10m, unlimited)
- Board configurations: Sample 0, 1, 2, 3 (Double Right), 4 (Queenless)
- Material Advantage (+/-) and Dynamic Evaluation Bar
- Dynamic agent switching between all agent_*.py versions
- "Set as Main Tournament agent.py" with auto-backup
- One-click hosting management (start_ui.bat, stop_ui.bat, /api/shutdown)
"""

import sys
import os
import time
import shutil
import threading
import importlib
import importlib.util
import json
from itertools import cycle

from flask import Flask, send_from_directory, jsonify, request
from flask_socketio import SocketIO, emit

# ── Base Directory & Path ────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "ui_static")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from chessmaker.chess.base import Board, Player, Square
from chessmaker.chess.pieces import King, Bishop, Knight, Queen
from extension.piece_right import Right
from extension.piece_pawn import Pawn_Q
from extension.board_utils import list_legal_moves_for, copy_piece_move
from extension.board_rules import get_result, thinking_with_timeout, THINKING_TIME_BUDGET, GAME_TIME_BUDGET
from samples import sample0, sample1, sample2, sample3, sample4

# ── Flask / SocketIO Setup ───────────────────────────────────────────────────
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")
app.config["SECRET_KEY"] = "chess_fragments_classy_secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── Global Game State ────────────────────────────────────────────────────────
_game_lock = threading.Lock()
_game_state = {
    "board": None,
    "players": None,
    "turn_iter": None,
    "ply": 1,
    "active": False,
    "human_side": "white",       # "white" | "black" | None (watch)
    "agent_side": "black",
    "result": None,
    "initial_board_grid": None,
    "move_history": [],
    "selected_piece": None,
    "legal_targets": [],
    "agent_module": None,
    "agent_name": "agent.py",
    "opp_module": None,
    "opp_name": "opponent.py",
    "board_sample_name": "sample0",
    "opponent_type": "baseline",  # 'baseline' | 'strong' | 'master' | or agent filename
    "watch_delay": 0.5,           # seconds between AI moves in watch mode
    "time_control": 300.0,        # seconds per player (5m default)
    "white_time_left": 300.0,
    "black_time_left": 300.0,
    "turn_start_time": None,
    "last_agent_time": 0.0,
    "last_agent_depth": 0,
    "last_agent_nodes": 0,
    "captured_by_white": [],
    "captured_by_black": [],
    "history_snapshots": [],      # List of snapshots for full Move Undo
}

SAMPLES = {
    "sample0": sample0,
    "sample1": sample1,
    "sample2": sample2,
    "sample3": sample3,
    "sample4": sample4,
}

# ── Agent loading & dynamic switching ────────────────────────────────────────

def _load_agent_module(filename):
    """Dynamically import any agent file from the project directory."""
    path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Agent file not found: {path}")
    mod_name = f"dynamic_{os.path.splitext(filename)[0]}_{int(time.time() * 1000)}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _get_agent_fn(mod):
    if mod is None:
        return None
    if hasattr(mod, "agent"):
        return mod.agent
    if hasattr(mod, "opponent"):
        return mod.opponent
    if hasattr(mod, "strong_opponent"):
        return mod.strong_opponent
    if hasattr(mod, "master_opponent"):
        return mod.master_opponent
    return None

def _get_opponent_fn(opponent_type):
    try:
        if opponent_type == "baseline":
            from opponent import opponent
            return opponent
        elif opponent_type == "strong":
            from strong_opponent import strong_opponent
            return strong_opponent
        elif opponent_type == "master":
            from master_opponent import master_opponent
            return master_opponent
        elif opponent_type.endswith(".py"):
            mod = _load_agent_module(opponent_type)
            return _get_agent_fn(mod)
    except Exception as e:
        print(f"[ui_server] Could not load opponent '{opponent_type}': {e}")
    return None

# ── Board serialisation & Material Counting ──────────────────────────────────

PIECE_SYMBOLS = {
    "king":   {"white": "K", "black": "k"},
    "queen":  {"white": "Q", "black": "q"},
    "right":  {"white": "R", "black": "r"},
    "bishop": {"white": "B", "black": "b"},
    "knight": {"white": "N", "black": "n"},
    "pawn":   {"white": "P", "black": "p"},
    "pawn_q": {"white": "P", "black": "p"},
}

MATERIAL_VALUES = {
    "pawn": 1,
    "knight": 3,
    "bishop": 3,
    "right": 6,
    "queen": 9,
    "king": 100,
}

def _piece_name(piece):
    n = type(piece).__name__.lower()
    if n.startswith("pawn"):
        return "pawn"
    return n

def _serialise_board(board):
    grid = []
    white_material = 0
    black_material = 0
    white_pieces = []
    black_pieces = []
    for y in range(5):
        row = []
        for x in range(5):
            sq = board._squares[y][x]
            if sq.piece is None:
                row.append(None)
            else:
                p = sq.piece
                pname = _piece_name(p)
                color = p.player.name
                val = MATERIAL_VALUES.get(pname, 1)
                if color == "white":
                    white_material += val
                    white_pieces.append(pname)
                else:
                    black_material += val
                    black_pieces.append(pname)
                sym = PIECE_SYMBOLS.get(pname, {}).get(color, "?")
                row.append({"piece": pname, "color": color, "symbol": sym, "x": x, "y": y})
        grid.append(row)
    return grid, white_material, black_material, white_pieces, black_pieces

def _calculate_live_clocks():
    """Calculate exact current clocks taking active turn time into account."""
    gs = _game_state
    tc = gs.get("time_control", 300.0)
    w_time = gs.get("white_time_left", tc)
    b_time = gs.get("black_time_left", tc)

    if tc > 0 and gs["active"] and not gs["result"] and gs.get("turn_start_time"):
        elapsed = time.time() - gs["turn_start_time"]
        cp = gs["board"].current_player.name if gs["board"] else None
        if cp == "white":
            w_time = max(0.0, w_time - elapsed)
        elif cp == "black":
            b_time = max(0.0, b_time - elapsed)

    return w_time, b_time

def _serialise_state():
    gs = _game_state
    board_data = None
    legal_targets = []
    w_mat = 0
    b_mat = 0
    if gs["board"] is not None:
        board_data, w_mat, b_mat, _, _ = _serialise_board(gs["board"])
    if gs["legal_targets"]:
        legal_targets = [(x, y) for x, y in gs["legal_targets"]]

    all_legal_moves = {}
    if gs["board"] is not None and gs["active"] and not gs["result"]:
        try:
            legal = list_legal_moves_for(gs["board"], gs["board"].current_player)
            for pc, mv in legal:
                key = f"{pc.position.x},{pc.position.y}"
                if key not in all_legal_moves:
                    all_legal_moves[key] = []
                all_legal_moves[key].append([mv.position.x, mv.position.y])
        except Exception:
            pass

    w_clock, b_clock = _calculate_live_clocks()
    diff = w_mat - b_mat

    return {
        "active": gs["active"],
        "ply": gs["ply"],
        "human_side": gs["human_side"],
        "agent_side": gs["agent_side"],
        "result": gs["result"],
        "initial_board_grid": gs.get("initial_board_grid"),
        "board": board_data,
        "selected": gs["selected_piece"],
        "legal_targets": legal_targets,
        "all_legal_moves": all_legal_moves,
        "move_history": gs["move_history"][-80:],
        "agent_name": gs["agent_name"],
        "board_sample": gs["board_sample_name"],
        "opponent_type": gs["opponent_type"],
        "watch_delay": gs["watch_delay"],
        "time_control": gs.get("time_control", 300.0),
        "white_time_left": round(w_clock, 2),
        "black_time_left": round(b_clock, 2),
        "base_white_time": round(gs["white_time_left"], 2),
        "base_black_time": round(gs["black_time_left"], 2),
        "turn_start_time": gs.get("turn_start_time"),
        "server_now": time.time(),
        "can_undo": len(gs.get("history_snapshots", [])) > 1,
        "current_player": gs["board"].current_player.name if gs["board"] and gs["active"] else None,
        "white_material": w_mat,
        "black_material": b_mat,
        "material_diff": diff,
        "white_advantage": diff if diff > 0 else 0,
        "black_advantage": abs(diff) if diff < 0 else 0,
        "captured_by_white": gs["captured_by_white"],
        "captured_by_black": gs["captured_by_black"],
        "agent_stats": {
            "time": round(gs["last_agent_time"], 3),
            "depth": gs["last_agent_depth"],
            "nodes": gs["last_agent_nodes"],
        }
    }

def _broadcast_state(extra=None):
    data = _serialise_state()
    if extra:
        data.update(extra)
    socketio.emit("state_update", data)

def _broadcast_log(msg, level="info"):
    socketio.emit("log", {"msg": msg, "level": level, "ts": time.strftime("%H:%M:%S")})

# ── Fresh Board Factory ──────────────────────────────────────────────────────

def _make_fresh_board(sample_name):
    white = Player("white")
    black = Player("black")
    sample = SAMPLES.get(sample_name, sample0)
    rows = []
    for row in sample:
        new_row = []
        for sq in row:
            if sq.piece is None:
                new_row.append(Square())
            else:
                p = sq.piece
                pname = _piece_name(p)
                color = p.player.name
                pl = white if color == "white" else black
                if pname == "king":
                    new_row.append(Square(King(pl)))
                elif pname == "queen":
                    new_row.append(Square(Queen(pl)))
                elif pname == "right":
                    new_row.append(Square(Right(pl)))
                elif pname == "bishop":
                    new_row.append(Square(Bishop(pl)))
                elif pname == "knight":
                    new_row.append(Square(Knight(pl)))
                elif pname == "pawn":
                    new_row.append(Square(Pawn_Q(pl)))
                else:
                    new_row.append(Square())
        rows.append(new_row)
    players = [white, black]
    board = Board(squares=rows, players=players, turn_iterator=cycle(players))
    return board, white, black, players

def _save_board_snapshot():
    """Stores deep snapshot of board state for undo."""
    gs = _game_state
    if gs["board"] is None:
        return
    snap = {
        "board": gs["board"].clone(),
        "ply": gs["ply"],
        "move_history": list(gs["move_history"]),
        "captured_by_white": list(gs["captured_by_white"]),
        "captured_by_black": list(gs["captured_by_black"]),
        "white_time_left": gs["white_time_left"],
        "black_time_left": gs["black_time_left"],
    }
    gs["history_snapshots"].append(snap)

def _record_move(ply, player_name, piece_name, fx, fy, tx, ty, captured_piece=None, agent_time=None, board_after=None):
    gs = _game_state
    if captured_piece:
        if player_name == "white":
            gs["captured_by_white"].append(captured_piece)
        else:
            gs["captured_by_black"].append(captured_piece)

    grid = None
    w_mat, b_mat = 0, 0
    if board_after:
        grid, w_mat, b_mat, _, _ = _serialise_board(board_after)

    entry = {
        "ply": ply,
        "player": player_name,
        "piece": piece_name,
        "from": [fx, fy],
        "to": [tx, ty],
        "captured": captured_piece is not None,
        "captured_piece": captured_piece,
        "agent_time": round(agent_time, 2) if agent_time else None,
        "board_grid": grid,
        "white_material": w_mat,
        "black_material": b_mat,
        "captured_by_white": list(gs["captured_by_white"]),
        "captured_by_black": list(gs["captured_by_black"]),
        "white_time": round(gs["white_time_left"], 1),
        "black_time": round(gs["black_time_left"], 1),
    }
    gs["move_history"].append(entry)

# ── AI Move Execution ────────────────────────────────────────────────────────

def _run_agent_move():
    """Executed in background thread for AI turn."""
    gs = _game_state
    if not gs["active"] or gs["result"]:
        return

    board = gs["board"]
    player = board.current_player
    agent_fn = _get_agent_fn(gs["agent_module"])
    opp_fn = _get_opponent_fn(gs["opponent_type"])

    # Determine which function plays
    human = gs["human_side"]
    if human:
        func = agent_fn
    else:
        # Watch mode
        if player.name == "white":
            func = agent_fn
        else:
            func = opp_fn if opp_fn else agent_fn

    if func is None:
        _broadcast_log(f"No agent loaded for {player.name}!", "error")
        return

    _broadcast_log(f"AI ({player.name}) thinking… (ply {gs['ply']})", "info")
    socketio.emit("agent_thinking", {"side": player.name})

    temp_board = board.clone()
    t0 = time.perf_counter()
    try:
        result = thinking_with_timeout(
            func=func,
            thinking_time=THINKING_TIME_BUDGET,
            board=temp_board,
            player=player,
            var=[gs["ply"], THINKING_TIME_BUDGET]
        )
    except Exception as e:
        _broadcast_log(f"Agent error: {e}", "error")
        return
    elapsed = time.perf_counter() - t0

    if result is None or (isinstance(result, tuple) and result[0] == 99):
        _broadcast_log(f"Agent ({player.name}) timeout / no move — selecting fallback", "warn")
        legal = list_legal_moves_for(board, player)
        if not legal:
            _end_game(f"No legal moves — {player.name} loses")
            return
        import random
        ai_piece_tmp, ai_move_tmp = random.choice(legal)
    else:
        ai_piece_tmp, ai_move_tmp = result

    if ai_piece_tmp is None or ai_move_tmp is None:
        legal = list_legal_moves_for(board, player)
        if not legal:
            _end_game(f"No legal moves — {player.name} loses")
            return
        import random
        ai_piece_tmp, ai_move_tmp = random.choice(legal)

    with _game_lock:
        if not gs["active"] or gs["result"]:
            return

        # Deduct thinking time from clock using Unix time
        now = time.time()
        tc = gs.get("time_control", 300.0)
        if tc > 0 and gs.get("turn_start_time"):
            turn_elapsed = now - gs["turn_start_time"]
            if player.name == "white":
                gs["white_time_left"] = max(0.0, gs["white_time_left"] - turn_elapsed)
                if gs["white_time_left"] <= 0:
                    _end_game("Black wins on time!")
                    return
            else:
                gs["black_time_left"] = max(0.0, gs["black_time_left"] - turn_elapsed)
                if gs["black_time_left"] <= 0:
                    _end_game("White wins on time!")
                    return
        gs["turn_start_time"] = now

        try:
            new_board, piece, move_opt = copy_piece_move(gs["board"], ai_piece_tmp, ai_move_tmp)
        except Exception as e:
            _broadcast_log(f"Move copy error: {e}", "error")
            return

        fx, fy = ai_piece_tmp.position.x, ai_piece_tmp.position.y
        tx, ty = ai_move_tmp.position.x, ai_move_tmp.position.y
        
        target_sq = gs["board"]._squares[ty][tx]
        cap_pname = _piece_name(target_sq.piece) if target_sq.piece else None

        depth = getattr(gs["agent_module"], "_last_depth_reached", 0) if gs["agent_module"] else 0
        nodes = getattr(gs["agent_module"], "_last_nodes_searched", 0) if gs["agent_module"] else 0

        gs["board"] = new_board
        gs["last_agent_time"] = elapsed
        gs["last_agent_depth"] = depth
        gs["last_agent_nodes"] = nodes
        _record_move(gs["ply"], player.name, _piece_name(ai_piece_tmp),
                     fx, fy, tx, ty,
                     captured_piece=cap_pname,
                     agent_time=elapsed,
                     board_after=new_board)
        gs["ply"] += 1
        gs["selected_piece"] = None
        gs["legal_targets"] = []

        try:
            piece.move(move_opt)
        except Exception:
            pass

        # Save snapshot for undo
        _save_board_snapshot()

        result_str = get_result(gs["board"])
        if result_str:
            _end_game(result_str)
            return

        legal = list_legal_moves_for(gs["board"], gs["board"].current_player)
        if not legal:
            result_str = f"No legal moves — {gs['board'].current_player.name} loses"
            _end_game(result_str)
            return

    cap_str = f" × {cap_pname}" if cap_pname else ""
    _broadcast_log(f"AI ({player.name}): ({fx},{fy}) → ({tx},{ty}){cap_str}  [{elapsed:.2f}s | d={depth}]", "move")
    _broadcast_state()

    _maybe_schedule_ai()

def _maybe_schedule_ai():
    """Schedules background AI move with configurable pacing delay."""
    gs = _game_state
    if not gs["active"] or gs["result"]:
        return
    next_player = gs["board"].current_player.name
    human = gs["human_side"]

    def runner():
        if human is None:
            delay = gs.get("watch_delay", 0.5)
            if delay > 0:
                time.sleep(delay)
        _run_agent_move()

    if human is None or next_player != human:
        threading.Thread(target=runner, daemon=True).start()

def _end_game(result_str):
    gs = _game_state
    gs["active"] = False
    gs["result"] = result_str
    _broadcast_log(f"Game over: {result_str}", "result")
    _broadcast_state({"result": result_str})

# ── SocketIO Handlers ────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    emit("state_update", _serialise_state())
    _broadcast_log("Connected to Chess Fragments UI server", "info")

@socketio.on("new_game")
def on_new_game(data):
    with _game_lock:
        human_side = data.get("human_side", "white")  # "white" | "black" | "watch"
        board_sample = data.get("board_sample", "sample0")
        opponent_type = data.get("opponent_type", "baseline")
        watch_delay = float(data.get("watch_delay", 0.5))
        time_control = float(data.get("time_control", 300.0))

        if _game_state["agent_module"] is None:
            try:
                _game_state["agent_module"] = _load_agent_module("agent.py")
                _game_state["agent_name"] = "agent.py"
            except Exception as e:
                emit("error", {"msg": str(e)})
                return

        board, white, black, players = _make_fresh_board(board_sample)
        initial_clock = time_control if time_control > 0 else 999999.0
        now = time.time()
        init_grid, _, _, _, _ = _serialise_board(board)

        _game_state.update({
            "board": board,
            "players": players,
            "ply": 1,
            "active": True,
            "human_side": human_side if human_side != "watch" else None,
            "agent_side": ("black" if human_side == "white" else "white") if human_side != "watch" else "both",
            "result": None,
            "initial_board_grid": init_grid,
            "move_history": [],
            "selected_piece": None,
            "legal_targets": [],
            "board_sample_name": board_sample,
            "opponent_type": opponent_type,
            "watch_delay": watch_delay,
            "time_control": time_control,
            "white_time_left": initial_clock,
            "black_time_left": initial_clock,
            "turn_start_time": now,
            "last_agent_time": 0.0,
            "last_agent_depth": 0,
            "last_agent_nodes": 0,
            "captured_by_white": [],
            "captured_by_black": [],
            "history_snapshots": [],
        })

        # Save initial position snapshot
        _save_board_snapshot()

    tc_str = f"{int(time_control // 60)}m" if time_control > 0 else "Unlimited"
    _broadcast_log(f"New match started: Board={board_sample} | Side={human_side} | Clock={tc_str} | Opponent={opponent_type}", "info")
    _broadcast_state()
    time.sleep(0.08)
    _maybe_schedule_ai()

@socketio.on("undo_move")
def on_undo_move():
    """Allows undoing moves during match or analysis."""
    with _game_lock:
        gs = _game_state
        snaps = gs.get("history_snapshots", [])
        if len(snaps) <= 1:
            emit("error", {"msg": "No previous moves to undo"})
            return

        human = gs.get("human_side")
        cp = gs["board"].current_player.name if gs["board"] else None

        # If Human vs AI:
        # If it's Human's turn and AI just responded, undo 2 plies to get back to Human's previous turn!
        # If only 1 move has been played or human is undoing before AI responded, undo 1 ply.
        if human is not None and cp == human and len(snaps) >= 3:
            snaps.pop() # remove AI move
            snaps.pop() # remove Human move
        else:
            snaps.pop()

        target = snaps[-1]
        gs["board"] = target["board"].clone()
        gs["ply"] = target["ply"]
        gs["move_history"] = list(target["move_history"])
        gs["captured_by_white"] = list(target["captured_by_white"])
        gs["captured_by_black"] = list(target["captured_by_black"])
        gs["white_time_left"] = target["white_time_left"]
        gs["black_time_left"] = target["black_time_left"]
        gs["selected_piece"] = None
        gs["legal_targets"] = []
        gs["result"] = None
        gs["active"] = True
        gs["turn_start_time"] = time.time()

    _broadcast_log(f"↶ Move undone. Reverted to ply {gs['ply']}", "warn")
    _broadcast_state()
    _maybe_schedule_ai()

@socketio.on("select_square")
def on_select_square(data):
    gs = _game_state
    if not gs["active"] or gs["result"]:
        return
    x, y = int(data["x"]), int(data["y"])
    board = gs["board"]
    human = gs["human_side"]
    current_player = board.current_player.name

    if human and current_player != human:
        emit("state_update", _serialise_state())
        return

    with _game_lock:
        selected = gs["selected_piece"]
        if selected is not None:
            sx, sy = selected
            legal = list_legal_moves_for(board, board.current_player)
            matched = [(pc, mv) for pc, mv in legal
                       if pc.position.x == sx and pc.position.y == sy
                       and mv.position.x == x and mv.position.y == y]
            if matched:
                pc_tmp, mv_tmp = matched[0]
                try:
                    new_board, piece, move_opt = copy_piece_move(gs["board"], pc_tmp, mv_tmp)
                    target_sq = gs["board"]._squares[y][x]
                    cap_pname = _piece_name(target_sq.piece) if target_sq.piece else None

                    # Deduct human turn time from clock
                    now = time.time()
                    tc = gs.get("time_control", 300.0)
                    if tc > 0 and gs.get("turn_start_time"):
                        turn_elapsed = now - gs["turn_start_time"]
                        if current_player == "white":
                            gs["white_time_left"] = max(0.0, gs["white_time_left"] - turn_elapsed)
                            if gs["white_time_left"] <= 0:
                                _end_game("Black wins on time!")
                                return
                        else:
                            gs["black_time_left"] = max(0.0, gs["black_time_left"] - turn_elapsed)
                            if gs["black_time_left"] <= 0:
                                _end_game("White wins on time!")
                                return
                    gs["turn_start_time"] = now

                    _record_move(gs["ply"], current_player, _piece_name(pc_tmp),
                                 sx, sy, x, y, captured_piece=cap_pname,
                                 board_after=new_board)
                    gs["board"] = new_board
                    gs["ply"] += 1
                    gs["selected_piece"] = None
                    gs["legal_targets"] = []
                    try:
                        piece.move(move_opt)
                    except Exception:
                        pass

                    # Save snapshot for undo
                    _save_board_snapshot()

                    cap_str = f" × {cap_pname}" if cap_pname else ""
                    _broadcast_log(f"Human ({current_player}): ({sx},{sy}) → ({x},{y}){cap_str}", "move")

                    result_str = get_result(gs["board"])
                    if result_str:
                        _end_game(result_str)
                        return
                    legal_next = list_legal_moves_for(gs["board"], gs["board"].current_player)
                    if not legal_next:
                        _end_game(f"No legal moves — {gs['board'].current_player.name} loses")
                        return
                except Exception as e:
                    _broadcast_log(f"Human move error: {e}", "error")
                    gs["selected_piece"] = None
                    gs["legal_targets"] = []
                _broadcast_state()
                _maybe_schedule_ai()
                return
            else:
                gs["selected_piece"] = None
                gs["legal_targets"] = []

        # Select square
        sq_data = board._squares[y][x]
        if sq_data.piece and sq_data.piece.player.name == current_player:
            legal = list_legal_moves_for(board, board.current_player)
            targets = [(mv.position.x, mv.position.y) for pc, mv in legal
                       if pc.position.x == x and pc.position.y == y]
            gs["selected_piece"] = (x, y)
            gs["legal_targets"] = targets
        else:
            gs["selected_piece"] = None
            gs["legal_targets"] = []

    _broadcast_state()

@socketio.on("load_agent")
def on_load_agent(data):
    filename = data.get("filename", "agent.py")
    try:
        mod = _load_agent_module(filename)
        _game_state["agent_module"] = mod
        _game_state["agent_name"] = filename
        emit("agent_loaded", {"name": filename, "ok": True})
        _broadcast_log(f"Active agent switched to: {filename}", "info")
        _broadcast_state()
    except Exception as e:
        emit("agent_loaded", {"name": filename, "ok": False, "error": str(e)})
        _broadcast_log(f"Failed to load {filename}: {e}", "error")

@socketio.on("set_as_main_agent")
def on_set_as_main_agent(data):
    """Copies chosen file over to agent.py with an automatic timestamped backup."""
    source_filename = data.get("filename")
    if not source_filename or not source_filename.endswith(".py"):
        emit("main_agent_updated", {"ok": False, "error": "Invalid filename"})
        return

    source_path = os.path.join(BASE_DIR, source_filename)
    target_path = os.path.join(BASE_DIR, "agent.py")
    if not os.path.exists(source_path):
        emit("main_agent_updated", {"ok": False, "error": "Source file not found"})
        return

    try:
        if os.path.exists(target_path) and source_filename != "agent.py":
            backup_name = f"agent.py.bak_{int(time.time())}"
            shutil.copyfile(target_path, os.path.join(BASE_DIR, backup_name))

        if source_filename != "agent.py":
            shutil.copyfile(source_path, target_path)

        mod = _load_agent_module("agent.py")
        _game_state["agent_module"] = mod
        _game_state["agent_name"] = "agent.py"

        _broadcast_log(f"✓ '{source_filename}' is now active as primary agent.py!", "info")
        emit("main_agent_updated", {"ok": True, "source": source_filename, "agent": "agent.py"})
        _broadcast_state()
    except Exception as e:
        _broadcast_log(f"Error promoting {source_filename} to agent.py: {e}", "error")
        emit("main_agent_updated", {"ok": False, "error": str(e)})

@socketio.on("set_watch_speed")
def on_set_watch_speed(data):
    delay = float(data.get("delay", 0.5))
    _game_state["watch_delay"] = max(0.0, min(delay, 3.0))
    _broadcast_log(f"AI watch speed delay set to {delay:.2f}s", "info")

@socketio.on("list_agents")
def on_list_agents():
    files = sorted([f for f in os.listdir(BASE_DIR) if f.endswith(".py") and "agent" in f.lower() and not f.endswith(".bak")])
    emit("agent_list", {"agents": files})

@socketio.on("resign")
def on_resign():
    human = _game_state["human_side"]
    if human and _game_state["active"]:
        _end_game(f"{human.capitalize()} resigned")

@socketio.on("get_state")
def on_get_state():
    emit("state_update", _serialise_state())

@socketio.on("shutdown_server")
def on_shutdown_server():
    """Allows stopping the server directly from the UI."""
    _broadcast_log("Server stopping by user command...", "warn")
    def _kill():
        time.sleep(0.4)
        os._exit(0)
    threading.Thread(target=_kill, daemon=True).start()

# ── HTTP Routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)

@app.route("/api/agents")
def api_agents():
    files = sorted([f for f in os.listdir(BASE_DIR) if f.endswith(".py") and "agent" in f.lower() and not f.endswith(".bak")])
    return jsonify(files)

@app.route("/api/state")
def api_state():
    return jsonify(_serialise_state())

@app.route("/api/shutdown", methods=["POST", "GET"])
def api_shutdown():
    _broadcast_log("Server shutdown requested via API.", "warn")
    def _kill():
        time.sleep(0.4)
        os._exit(0)
    threading.Thread(target=_kill, daemon=True).start()
    return jsonify({"status": "stopping", "message": "Chess Fragments server is shutting down."})

# ── Server Boot ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Chess Fragments UI Server - http://localhost:5000")
    print("=" * 60)
    try:
        _game_state["agent_module"] = _load_agent_module("agent.py")
        _game_state["agent_name"] = "agent.py"
        print("  [OK] Loaded default: agent.py")
    except Exception as e:
        print(f"  Notice: Could not load agent.py: {e}")
    print("=" * 60)
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
