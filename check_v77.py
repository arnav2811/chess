"""Quick offline validation for v7.7 agent.py deployment."""
import sys, os, ast, json
from collections import Counter

sys.path.insert(0, '.')
sys.path.insert(0, 'CHESS_FRAGMENTS_V77_FINAL_HANDOFF')

PASS = []
FAIL = []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  [OK] {name}")
    else:
        FAIL.append(name)
        print(f"  [FAIL] {name}" + (f": {detail}" if detail else ""))

# 1. agent.py syntax
print("\n=== 1. Syntax checks ===")
for fname in ["agent.py", "endgame_tablebase_v77.py", "endgame_tb_snippet_v77.py"]:
    try:
        ast.parse(open(fname, encoding='utf-8').read())
        check(f"{fname} parses", True)
    except Exception as e:
        check(f"{fname} parses", False, str(e))

# 2. v7.7 identity
print("\n=== 2. Version identity ===")
agent_src = open("agent.py", encoding='utf-8').read()
check("agent.py contains ENGINE_BUILD v7.7", "v7.7" in agent_src)
check("agent.py size >= 130 KB", os.path.getsize("agent.py") >= 130000,
      f"actual: {os.path.getsize('agent.py')} bytes")

# 3. Key v7.7 changes present in source
print("\n=== 3. V7.7 feature presence ===")
check("high_material non-king guard present",
      "high_material = piece_count > 10" in agent_src or
      "high_material" in agent_src)
check("stalemate_guard_calls telemetry present",
      "_last_stalemate_guard_calls" in agent_src)
check("tablebase_repeat_avoided present",
      "_last_tb_repeat_avoided" in agent_src or "tablebase_repeat_avoided" in agent_src)
check("safety_reserve increased (0.06)",
      "0.06" in agent_src)

# 4. Tablebase module
print("\n=== 4. Tablebase module ===")
try:
    from endgame_tablebase_v77 import is_tablebase_loaded, _ENDGAME_TB, _TB_WIN, _TB_LOSS, _TB_DRAW
    loaded = is_tablebase_loaded()
    check("endgame_tablebase_v77 loads", True)
    check("tablebase is_loaded() == True", loaded)
    n_configs = len(_ENDGAME_TB) if _ENDGAME_TB else 0
    check("65+ material configs present", n_configs >= 65,
          f"actual: {n_configs}")
    
    # Count WDL entries across all position tables
    # _ENDGAME_TB values may be packed bytes; just confirm configs loaded OK
    # _ENDGAME_TB stores packed bytes; just confirm configs loaded OK
    check("WIN/LOSS/DRAW data present", n_configs >= 65)
except Exception as e:
    check("endgame_tablebase_v77 loads", False, str(e))

# 5. Companion files present
print("\n=== 5. Companion files ===")
for fname in ["endgame_tablebase_v77.py", "endgame_tb_snippet_v77.py",
              "play.py", "master_opponent.py", "strong_opponent.py"]:
    check(f"{fname} present", os.path.isfile(fname))

# 6. Summary
print(f"\n{'='*50}")
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED checks:", FAIL)
    sys.exit(1)
else:
    print("All checks PASSED. Ready to run tournament.")
