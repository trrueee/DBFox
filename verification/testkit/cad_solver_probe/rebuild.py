"""Rebuild pinned PlaneGCS with upstream CMake and no dynamic JS execution.

Inputs are prepared outside product source as documented in README.md.
No downloads, global activation, solver source edits, or product writes occur.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--cmake", type=Path, required=True)
    parser.add_argument("--ninja", type=Path, required=True)
    args = parser.parse_args()
    task = args.task.resolve()
    source = task / "upstream/planegcs"
    sdk = task / "emsdk"
    expected = json.loads(Path(__file__).with_name("source-hashes.json").read_text(encoding="utf-8"))
    for name, digest in expected.items():
        assert sha(source / name) == digest, f"Source mismatch: {name}"
    assert subprocess.check_output(["git", "-C", str(sdk), "rev-parse", "HEAD"], text=True).strip() == "c8dcb45665fec5e743336703f1d22a191810f2a8"
    assert subprocess.check_output(["git", "-C", str(task / "eigen"), "rev-parse", "HEAD"], text=True).strip() == "3147391d946bb4b6c68edd901f2add6ac1f31f8c"
    assert sha(task / "boost_1_74_0.tar.gz") == "afff36d392885120bcac079148c177d1f6f7730ec3d47233aa51b0afa4db94a5"
    adapted = task / "portable-source"
    adapted.mkdir(exist_ok=True)
    for name in expected:
        target = adapted / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    # Only adapt the Linux header paths and the official linker setting.
    cmake = (source / "CMakeLists.txt").read_text(encoding="utf-8")
    cmake = cmake.replace('set(Boost_INCLUDE_DIR "/inc")\nfind_package(Boost REQUIRED)',
                          f'set(Boost_INCLUDE_DIR "{(task / "boost_1_74_0").as_posix()}")')
    cmake = cmake.replace('"/usr/include/eigen3"', f'"{(task / "eigen").as_posix()}"')
    cmake = cmake.replace('-s MODULARIZE=1', '-s MODULARIZE=1 -s DYNAMIC_EXECUTION=0')
    (adapted / "CMakeLists.txt").write_text(cmake, encoding="utf-8")
    env = os.environ.copy()
    # The local SDK config names its own fixed Node, LLVM, Binaryen and Java.
    env["EM_CONFIG"] = str(sdk / ".emscripten")
    env["EM_CACHE"] = str(task / "em-cache")
    env["PATH"] = str(args.cmake.parent) + os.pathsep + str(args.ninja.parent) + os.pathsep + env["PATH"]
    emscripten = sdk / "upstream/emscripten"
    build = task / "build-no-dynamic"
    commands = [
        [sys.executable, str(emscripten / "emcmake.py"), str(args.cmake), "-S", str(adapted), "-B", str(build), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_MAKE_PROGRAM={args.ninja}"],
        [str(args.cmake), "--build", str(build), "--parallel", "2"],
    ]
    for command in commands:
        subprocess.run(command, env=env, check=True)
    package = task / "rebuilt-package"
    shutil.copytree(task / "package", package, dirs_exist_ok=True)
    assets = {}
    for name in ("planegcs.js", "planegcs.wasm"):
        path = build / "bin" / name
        data = path.read_bytes()
        assets[name] = {"raw_bytes": len(data), "gzip_bytes": len(gzip.compress(data, mtime=0)), "sha256": sha(path)}
        shutil.copy2(path, package / "dist/planegcs_dist" / name)
    report = {"scope": "investigative rebuild only", "upstream_commit": "ee9b156da9827a91a56a888a53520f63d5cffaa6", "freecad_commit": (source / "commit.txt").read_text().strip(), "emscripten": "3.1.45", "dynamic_execution": 0, "assets": assets, "inputs": expected}
    (task / "rebuild-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
