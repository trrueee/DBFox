with open("engine/tests/test_agent_kernel.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "@pytest.fixture" in line:
        print(f"Line {i+1}: {line.strip()}")
        # print next few lines
        for j in range(1, 5):
            if i + j < len(lines):
                print(f"  {lines[i+j].strip()}")
