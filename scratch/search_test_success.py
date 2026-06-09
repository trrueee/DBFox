with open("engine/tests/test_agent_kernel.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if ".success" in line or '"success"' in line or "'success'" in line:
        print(f"Line {i+1}: {line.strip()}")
