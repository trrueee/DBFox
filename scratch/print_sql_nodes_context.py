with open("engine/agent_kernel/graph_sql_nodes.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for idx in range(100, 160):
    if idx < len(lines):
        print(f"{idx+1}: {lines[idx]}", end="")
