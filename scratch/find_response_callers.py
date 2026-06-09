with open("engine/agent_kernel/service.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "_response(" in line:
        print(f"Line {i+1}: {line.strip()}")
