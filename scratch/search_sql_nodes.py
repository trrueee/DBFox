with open("engine/agent_kernel/graph_sql_nodes.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "error" in line or "status" in line:
        print(f"Line {i+1}: {line.strip()}")
