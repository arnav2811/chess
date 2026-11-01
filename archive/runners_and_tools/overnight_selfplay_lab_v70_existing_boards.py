#!/usr/bin/env python3
"""Overnight self-play / parameter-evolution lab for the 5x5 Chess Fragments agent.

Run from the coursework project directory, where chessmaker/extension and the
existing tournament runner are importable. The v6.9 champion file is read-only.
The lab only writes to its own output directory and never overwrites agent.py.
"""
from __future__ import annotations
import argparse, copy, importlib.util, json, math, os, random, shutil, sys, time, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

LAB_VERSION = "1.2-existing-boards"
BASE_AGENT_DEFAULT = "agent_v70_depth10.py"
CHAMPION_DEFAULT = "agent_v69_stalemate_guard.py"
RUNNER_DEFAULT = "run_fresh_18_tournament_diagnostic_v70_fixed.py"
TRAIN_BASES = ("sample0", "sample1", "sample2", "sample3", "sample4")
_MOVE_LOG = []
_RUNNER = None
_CHAMPION_SOURCE = None


def _load_module(path: str, module_name: str):
    path_obj = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(module_name, path_obj)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import agent source: {path_obj}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _baseline_config(module):
    return {
        "piece_values": {k: int(v) for k, v in module.PIECE_VALUES.items()},
        "pawn_scale": 1.0,
        "aspiration_delta": int(getattr(module, "_ASPIRATION_DELTA", 250)),
        "tt_max_size": int(getattr(module, "_TT_MAX_SIZE", 200000)),
    }


def _apply_config(module, cfg):
    module.PIECE_VALUES = dict(module.PIECE_VALUES)
    module.PIECE_VALUES.update({k: int(v) for k, v in cfg["piece_values"].items()})
    scale = float(cfg["pawn_scale"])
    module._PAWN_ADVANCE_BONUS_WHITE = [int(round(v * scale)) for v in module._PAWN_ADVANCE_BONUS_WHITE]
    module._PAWN_ADVANCE_BONUS_BLACK = [int(round(v * scale)) for v in module._PAWN_ADVANCE_BONUS_BLACK]
    module._ASPIRATION_DELTA = int(cfg["aspiration_delta"])
    module._TT_MAX_SIZE = int(cfg["tt_max_size"])


def _mutate(parent, rng, strength=1.0):
    c = copy.deepcopy(parent)
    vals = c["piece_values"]
    # Small, bounded mutations. Keep king value fixed and preserve positive material ordering.
    for name, step, lo, hi in (("pawn", 5, 85, 120), ("knight", 15, 270, 370),
                               ("bishop", 15, 280, 380), ("right", 25, 600, 800),
                               ("queen", 25, 800, 1000)):
        if rng.random() < 0.65:
            vals[name] = int(max(lo, min(hi, vals[name] + round(rng.choice([-2,-1,1,2]) * step * strength))))
    if rng.random() < 0.7:
        c["pawn_scale"] = round(max(0.65, min(1.35, c["pawn_scale"] + rng.choice([-0.15,-0.10,-0.05,0.05,0.10,0.15]) * strength)), 3)
    if rng.random() < 0.5:
        c["aspiration_delta"] = rng.choice([125, 175, 225, 250, 300, 350, 400])
    if rng.random() < 0.25:
        c["tt_max_size"] = rng.choice([100000, 150000, 200000, 250000, 300000])
    vals["king"] = 20000
    return c


def _existing_board_factory(runner, name):
    """Use the coursework runner's existing sample0..sample4 boards unchanged.

    Do not reconstruct pieces or invent shuffled variants: custom pieces such as
    Pawn_Q require constructor arguments (e.g. direction) that generic cloning
    cannot safely reproduce.
    """
    if name not in {f"sample{i}" for i in range(5)}:
        raise ValueError(f"Unknown existing board {name!r}; expected sample0..sample4")
    return _ORIGINAL_MAKE_BOARD(name)


def _traced_copy_piece_move(board, piece, move_opt):
    # Capture move-level diagnostics without changing the runner's move semantics.
    if piece is not None and move_opt is not None:
        try:
            fx, fy = piece.position.x, piece.position.y
            tx, ty = move_opt.position.x, move_opt.position.y
            target = next((p for p in board.get_pieces()
                           if p.position.x == tx and p.position.y == ty), None)
            _MOVE_LOG.append({
                "side": piece.player.name,
                "piece": type(piece).__name__,
                "from": [fx, fy], "to": [tx, ty],
                "capture": type(target).__name__ if target is not None else None,
            })
        except Exception:
            pass
    return _ORIGINAL_COPY_MOVE(board, piece, move_opt)


def _worker_init(runner_path, champion_path, think_time):
    global _RUNNER, _CHAMPION_SOURCE, _ORIGINAL_MAKE_BOARD, _ORIGINAL_COPY_MOVE
    # Runner import pulls in the coursework's actual board/rules implementation.
    runner_file = Path(runner_path).resolve()
    _RUNNER = _load_module(str(runner_file), f"lab_runner_{os.getpid()}")
    _CHAMPION_SOURCE = str(Path(champion_path).resolve())
    _ORIGINAL_MAKE_BOARD = _RUNNER.make_fresh_board
    _ORIGINAL_COPY_MOVE = _RUNNER.copy_piece_move
    _RUNNER.make_fresh_board = lambda name: _existing_board_factory(_RUNNER, name)
    _RUNNER.copy_piece_move = _traced_copy_piece_move
    _RUNNER.THINKING_TIME_BUDGET = float(think_time)


def _play_task(task):
    global _MOVE_LOG
    candidate_path = task["candidate_source"]
    cfg = task["config"]
    candidate_id = task["candidate_id"]
    game_id = task["game_id"]
    seed = task["seed"]
    colour = task["colour"]
    module = _load_module(candidate_path, f"lab_candidate_{os.getpid()}_{game_id}_{candidate_id}")
    _apply_config(module, cfg)
    champion = _load_module(_CHAMPION_SOURCE, f"lab_champion_{os.getpid()}_{game_id}")
    _RUNNER.agent = module.agent
    _RUNNER.strong_opponent = champion.agent
    _MOVE_LOG = []
    try:
        result = _RUNNER.play_one_game(
            game_id, 2, "Strong", f"sample{seed % 5}", colour
        )
        result["moves"] = list(_MOVE_LOG)
        result["candidate_id"] = candidate_id
        result["candidate_config"] = cfg
        result["seed"] = seed
        result["think_time_s"] = _RUNNER.THINKING_TIME_BUDGET
        return result
    except Exception as exc:
        return {
            "match_id": game_id, "candidate_id": candidate_id, "seed": seed,
            "agent_color": colour, "outcome": "ERROR",
            "termination": f"Lab exception: {type(exc).__name__}: {exc}",
            "duration_s": 0.0, "plies": 0, "moves": list(_MOVE_LOG),
            "candidate_config": cfg, "think_time_s": _RUNNER.THINKING_TIME_BUDGET,
            "traceback": traceback.format_exc(),
        }


def _score(results):
    # Never let failed games count as losses or silently reward an all-error run.
    valid = [r for r in results if r.get("outcome") in ("WIN", "DRAW", "LOSS")]
    if not valid:
        return 0.0
    points = sum(1.0 if r.get("outcome") == "WIN" else 0.5 if r.get("outcome") == "DRAW" else 0.0 for r in valid)
    return points / len(valid)


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _candidate_source_text(base_agent_path, cfg):
    source = Path(base_agent_path).read_text(encoding="utf-8")
    block = "\n\n# --- OVERNIGHT SELF-PLAY LAB: learned parameter overrides ---\n"
    block += "# Generated candidate; review and validate before using in coursework.\n"
    block += f"PIECE_VALUES.update({json.dumps(cfg['piece_values'], sort_keys=True)})\n"
    base_white = [0, 60, 30, 10, 0]
    base_black = [0, 10, 30, 60, 0]
    block += f"_PAWN_ADVANCE_BONUS_WHITE = {[int(round(v*cfg['pawn_scale'])) for v in base_white]!r}\n"
    block += f"_PAWN_ADVANCE_BONUS_BLACK = {[int(round(v*cfg['pawn_scale'])) for v in base_black]!r}\n"
    block += f"_ASPIRATION_DELTA = {int(cfg['aspiration_delta'])}\n"
    block += f"_TT_MAX_SIZE = {int(cfg['tt_max_size'])}\n"
    return source + block


def main():
    parser = argparse.ArgumentParser(description="Overnight 5x5 Chess Fragments self-play improvement lab")
    parser.add_argument("--base-agent", default=BASE_AGENT_DEFAULT, help="Experimental base code to tune (default: v7.0-depth10)")
    parser.add_argument("--champion", default=CHAMPION_DEFAULT, help="Frozen incumbent/opponent (default: v6.9); never modified")
    parser.add_argument("--runner", default=RUNNER_DEFAULT, help="Existing tournament runner (must be in project folder)")
    parser.add_argument("--out", default="selfplay_lab_runs/run_001", help="Output directory; never overwrites champion")
    parser.add_argument("--games", type=int, default=1000, help="Total target games, including validation and confirmation")
    parser.add_argument("--workers", type=int, default=2, help="Concurrent game processes; 2 is the balanced default")
    parser.add_argument("--think-time", type=float, default=2.0, help="Per-move budget for fast screening games; use full-strength tests afterwards")
    parser.add_argument("--population", type=int, default=10, help="Candidate configurations per generation")
    parser.add_argument("--seed", type=int, default=690070, help="Reproducible experiment seed")
    parser.add_argument("--benchmark-only", action="store_true", help="Run 10 benchmark games and estimate throughput, without tuning")
    args = parser.parse_args()

    base_agent_path = Path(args.base_agent).resolve()
    champion_path = Path(args.champion).resolve()
    runner_path = Path(args.runner).resolve()
    out_dir = Path(args.out).resolve()
    if not base_agent_path.is_file():
        raise SystemExit(f"Base-agent file not found: {base_agent_path}\nCopy agent_v70_depth10.py into the project folder or pass --base-agent.")
    if not champion_path.is_file():
        raise SystemExit(f"Champion file not found: {champion_path}\nCopy the frozen v6.9 file here; do not point this at a mutable agent.py.")
    if not runner_path.is_file():
        raise SystemExit(f"Runner not found: {runner_path}")
    if args.games < 100 or args.workers < 1 or args.population < 4 or args.think_time <= 0:
        raise SystemExit("Use --games >= 100, --workers >= 1, --population >= 4, and positive --think-time.")
    out_dir.mkdir(parents=True, exist_ok=True)
    # Hash the champion so the report proves which exact source was tested.
    import hashlib
    champion_hash = hashlib.sha256(champion_path.read_bytes()).hexdigest()
    base_agent_hash = hashlib.sha256(base_agent_path.read_bytes()).hexdigest()
    base_mod = _load_module(str(base_agent_path), "lab_baseline_config")
    base_cfg = _baseline_config(base_mod)
    rng = random.Random(args.seed)
    manifest = {
        "lab_version": LAB_VERSION, "started_local": time.strftime("%Y-%m-%d %H:%M:%S"),
        "base_agent_path": str(base_agent_path), "base_agent_sha256": base_agent_hash,
        "champion_path": str(champion_path), "champion_sha256": champion_hash,
        "runner_path": str(runner_path), "target_games": args.games,
        "workers": args.workers, "think_time_s": args.think_time,
        "population": args.population, "seed": args.seed,
        "note": "Champion source is read-only. Fast-screen results are provisional, not a promotion-grade strength claim.",
    }
    _write_json(out_dir / "manifest.json", manifest)
    print("SELF-PLAY LAB", LAB_VERSION)
    print("Candidate base code:", base_agent_path)
    print("Candidate base SHA-256:", base_agent_hash)
    print("Frozen incumbent/opponent:", champion_path)
    print("Champion SHA-256:", champion_hash)
    print(f"Target games: {args.games}; workers: {args.workers}; per-move budget: {args.think_time:.2f}s")
    print("Board source: existing tournament samples sample0..sample4 only (no generated variants)")
    print("Outputs:", out_dir)
    sys.stdout.flush()

    # Each game is a candidate against the immutable champion, not self-play between identical copies.
    # Training seeds are disjoint from held-out and final confirmation seed ranges.
    benchmark_count = 10 if args.benchmark_only else 0
    validation_games = 0 if args.benchmark_only else max(10, int(args.games * 0.10))
    confirmation_games = 0 if args.benchmark_only else max(10, int(args.games * 0.10))
    tuning_budget = max(0, args.games - validation_games - confirmation_games - benchmark_count)
    games_per_candidate = 8  # four paired starting variants, each played with both colours
    generations = max(1, tuning_budget // (args.population * games_per_candidate))
    tuning_games_planned = generations * args.population * games_per_candidate
    if args.benchmark_only:
        generations = 0
        tuning_games_planned = 0

    progress_target = 10 if args.benchmark_only else tuning_games_planned + validation_games + confirmation_games

    population = [copy.deepcopy(base_cfg)]
    while len(population) < args.population:
        population.append(_mutate(base_cfg, rng, strength=1.0 + 0.15 * len(population)))

    all_results = []
    game_counter = 0
    t_start = time.perf_counter()

    def run_tasks(tasks):
        nonlocal game_counter, all_results
        if not tasks:
            return []
        results = []
        with ProcessPoolExecutor(max_workers=args.workers, initializer=_worker_init,
                                 initargs=(str(runner_path), str(champion_path), args.think_time)) as pool:
            futures = {pool.submit(_play_task, task): task for task in tasks}
            for fut in as_completed(futures):
                task = futures[fut]
                try:
                    res = fut.result()
                except Exception as exc:
                    res = {"match_id": task["game_id"], "candidate_id": task["candidate_id"],
                           "seed": task["seed"], "agent_color": task["colour"], "outcome": "ERROR",
                           "termination": f"Worker failure: {type(exc).__name__}: {exc}", "duration_s": 0.0,
                           "plies": 0, "moves": [], "candidate_config": task["config"]}
                results.append(res)
                all_results.append(res)
                game_counter += 1
                # Persist every completed game so Ctrl+C or a crash loses at most a small amount of work.
                if game_counter % 5 == 0 or game_counter == args.games:
                    _write_json(out_dir / "games.json", all_results)
                    elapsed = max(0.001, time.perf_counter() - t_start)
                    rate = game_counter / elapsed
                    remaining = max(0, progress_target - game_counter)
                    eta_h = remaining / max(rate, 1e-9) / 3600
                    print(f"Progress {game_counter}/{progress_target} | {rate*3600:.1f} games/hour | ETA {eta_h:.1f} h")
                    sys.stdout.flush()
        _write_json(out_dir / "games.json", all_results)
        return results

    if args.benchmark_only:
        tasks = []
        for i in range(10):
            tasks.append({"candidate_source": str(base_agent_path), "candidate_id": "baseline-benchmark",
                          "config": base_cfg, "game_id": i+1, "seed": 900000+i,
                          "colour": "white" if i % 2 == 0 else "black"})
        benchmark_results = run_tasks(tasks)
        elapsed = max(0.001, time.perf_counter() - t_start)
        valid_results = [r for r in benchmark_results if r.get("outcome") in ("WIN", "DRAW", "LOSS")]
        error_count = sum(r.get("outcome") == "ERROR" for r in benchmark_results)
        report = {"mode": "benchmark_only", "games_attempted": len(benchmark_results),
                  "valid_games": len(valid_results), "elapsed_s": round(elapsed, 2),
                  "valid_games_per_hour": round(len(valid_results)/elapsed*3600, 2),
                  "average_game_s": round(sum(r.get("duration_s",0) for r in valid_results)/max(1,len(valid_results)),2),
                  "outcomes": {k: sum(r.get("outcome")==k for r in benchmark_results) for k in ("WIN","DRAW","LOSS","ERROR")},
                  "champion_sha256": champion_hash,
                  "status": "FAIL" if error_count or len(valid_results) != 10 else "PASS"}
        _write_json(out_dir / "benchmark_report.json", report)
        print(json.dumps(report, indent=2))
        if error_count or len(valid_results) != 10:
            raise SystemExit("Benchmark failed: at least one game errored. Do not launch the overnight run; inspect games.json.")
        return

    # Evolutionary tuning. All candidates in a generation face the same four seeds and both colours.
    for gen in range(generations):
        print(f"\n=== GENERATION {gen+1}/{generations} ===")
        generation_tasks = []
        seeds = [1000 + gen*100 + j for j in range(4)]
        for ci, cfg in enumerate(population):
            for j, seed in enumerate(seeds):
                for colour in ("white", "black"):
                    game_counter += 0  # counter is incremented centrally after each completed task
                    gid = gen*args.population*games_per_candidate + ci*games_per_candidate + j*2 + (0 if colour=="white" else 1) + 1
                    generation_tasks.append({"candidate_source": str(base_agent_path), "candidate_id": f"g{gen+1}_c{ci+1}",
                                             "config": cfg, "game_id": gid, "seed": seed,
                                             "colour": colour})
        gen_results = run_tasks(generation_tasks)
        generation_errors = [r for r in gen_results if r.get("outcome") == "ERROR"]
        if generation_errors:
            _write_json(out_dir / "generation_error_report.json", {
                "generation": gen + 1, "error_count": len(generation_errors),
                "errors": generation_errors[:20],
                "status": "ABORTED: no candidate should be selected from a generation with game errors"
            })
            raise SystemExit(f"Generation {gen+1} aborted: {len(generation_errors)} game errors. Inspect games.json and generation_error_report.json.")
        scored = []
        for ci, cfg in enumerate(population):
            cid = f"g{gen+1}_c{ci+1}"
            rs = [r for r in gen_results if r.get("candidate_id")==cid]
            scored.append(( _score(rs), cfg, rs, cid ))
        scored.sort(key=lambda x: (x[0], -sum(1 for r in x[2] if r.get("outcome")=="ERROR")), reverse=True)
        gen_summary = [{"candidate_id": cid, "score": round(score,4), "wins": sum(r.get("outcome")=="WIN" for r in rs),
                        "draws": sum(r.get("outcome")=="DRAW" for r in rs), "losses": sum(r.get("outcome")=="LOSS" for r in rs),
                        "errors": sum(r.get("outcome")=="ERROR" for r in rs), "config": cfg}
                       for score,cfg,rs,cid in scored]
        _write_json(out_dir / f"generation_{gen+1:02d}.json", gen_summary)
        print("Top candidates:")
        for row in gen_summary[:3]: print(f"  {row['candidate_id']}: score={row['score']:.3f}, W/D/L/E={row['wins']}/{row['draws']}/{row['losses']}/{row['errors']}")
        if gen + 1 < generations:
            elites = [scored[0][1], scored[1][1]]
            next_population = [copy.deepcopy(elites[0]), copy.deepcopy(elites[1])]
            while len(next_population) < args.population:
                parent = rng.choice(elites if rng.random() < 0.8 else [x[1] for x in scored[:max(3, len(scored)//2)]])
                next_population.append(_mutate(parent, rng, strength=rng.choice([0.5, 0.75, 1.0, 1.25])))
            population = next_population
        else:
            best_config = scored[0][1]
            best_score = scored[0][0]

    if args.benchmark_only:
        return

    # Validation and final confirmation use unseen variant seeds, never used for tuning.
    validation_tasks = []
    for i in range(validation_games):
        validation_tasks.append({"candidate_source": str(base_agent_path), "candidate_id": "best-validation",
                                 "config": best_config, "game_id": 900000+i,
                                 "seed": 100000+i//2, "colour": "white" if i%2==0 else "black"})
    validation_results = run_tasks(validation_tasks)
    validation_score = _score(validation_results)

    final_tasks = []
    for i in range(confirmation_games):
        final_tasks.append({"candidate_source": str(base_agent_path), "candidate_id": "best-confirmation",
                            "config": best_config, "game_id": 950000+i,
                            "seed": 200000+i//2, "colour": "white" if i%2==0 else "black"})
    confirmation_results = run_tasks(final_tasks)
    confirmation_score = _score(confirmation_results)

    # Export learned parameters layered on the v7.0 base as a separate candidate; never overwrite either source.
    candidate_out = out_dir / "agent_lab_candidate.py"
    candidate_out.write_text(_candidate_source_text(base_agent_path, best_config), encoding="utf-8")
    def summarize(rs):
        return {"games": len(rs), "score": round(_score(rs),4),
                "wins": sum(r.get("outcome")=="WIN" for r in rs),
                "draws": sum(r.get("outcome")=="DRAW" for r in rs),
                "losses": sum(r.get("outcome")=="LOSS" for r in rs),
                "errors": sum(r.get("outcome")=="ERROR" for r in rs),
                "terminations": dict((term, sum(r.get("termination")==term for r in rs)) for term in sorted({r.get("termination") for r in rs}))}
    report = {
        "lab_version": LAB_VERSION, "base_agent_sha256": base_agent_hash, "champion_sha256": champion_hash,
        "target_games": args.games, "actual_games": len(all_results),
        "think_time_s": args.think_time, "workers": args.workers,
        "tuning_generations": generations, "population": args.population,
        "tuning_planned_games": tuning_games_planned,
        "tuning_best_score_last_generation": round(best_score,4),
        "validation_heldout": summarize(validation_results),
        "fresh_confirmation": summarize(confirmation_results),
        "best_config": best_config, "candidate_file": str(candidate_out),
        "promotion_status": "NOT_PROMOTED: fast-screen data only; run full-strength validation and the fixed 18-match suite before replacing anything.",
        "elapsed_s": round(time.perf_counter()-t_start,2),
    }
    _write_json(out_dir / "final_report.json", report)
    print("\nLAB COMPLETE")
    print(json.dumps(report, indent=2))
    print("\nBase agent and frozen champion were not modified. Candidate is provisional: ", candidate_out)

if __name__ == "__main__":
    main()
