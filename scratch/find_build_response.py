import glob

for filename in glob.glob("engine/agent_kernel/*.py"):
    with open(filename, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if "build_response" in line:
            print(f"{filename}:{i+1}: {line.strip()}")
