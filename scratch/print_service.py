with open("engine/agent_kernel/service.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i in range(1100, 1180):
    if i < len(lines):
        print(f"{i+1}: {lines[i]}", end="")
