with open("engine/agent_kernel/service.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for line_idx in [306, 490]:
    print(f"--- Line {line_idx} context ---")
    for idx in range(line_idx - 10, line_idx + 15):
        if idx < len(lines):
            print(f"{idx+1}: {lines[idx]}", end="")
