"""Reuse the product example plus an actually recorded winning input route."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def prepare(source: Path, output: Path):
    evidence = json.loads(source.read_text(encoding="utf-8-sig"))
    assert evidence["won"]["outcome"] == "won" and evidence["won"]["ticks"] == 3600
    root = Path(__file__).resolve().parents[3]
    script = "import {survivalOperations} from './dlcs/dbfox.game/frontend/presets.js'; console.log(JSON.stringify(survivalOperations('SCENE')));"
    ops = json.loads(subprocess.check_output(["node", "--input-type=module", "-e", script], cwd=root, text=True, encoding="utf-8"))
    ops = json.loads(json.dumps(ops).replace('"SCENE"', '"$summary.metadata.initial_scene_id"'))
    ops[1]["entities"][0]["components"][0]["x"] = 480
    inputs = [{**event, "entity_id": "$entities.items.0.id"} for event in evidence["inputs"]]
    step = lambda identity, tool, arguments, requires=None: {"id": identity, "tool": tool, "arguments": arguments, **({"requires": requires} if requires else {})}
    plan = {"steps": [
        step("create", "game_create", {"title": "Native Agent Fox Survival", "expected_library_version": 1}),
        step("summary", "game_inspect", {"game_id": "$game_id", "section": "summary"}),
        step("design", "game_modify", {"game_id": "$game_id", "expected_version": "$version", "operations": ops}),
        step("entities", "game_inspect", {"game_id": "$game_id", "section": "entities", "limit": 10}),
        step("lost", "playtest", {"game_id": "$game_id", "expected_version": "$version", "seed": 42, "ticks": 3600, "inputs": []}),
        step("adjust", "game_modify", {"game_id": "$game_id", "expected_version": "$version", "operations": [{"kind": "component_modify", "component_id": {"id": "$entities.items.0.components.3.id"}, "component": {"kind": "health", "initial": 4, "maximum": 4}}]}, [{"path": "$lost.report.outcome", "equals": "lost"}]),
        step("won", "playtest", {"game_id": "$game_id", "expected_version": "$version", "seed": 42, "ticks": 3600, "inputs": inputs}),
        step("export", "game_export", {"game_id": "$game_id", "expected_version": "$version"}, [{"path": "$won.report.outcome", "equals": "won"}, {"path": "$won.report.ticks_completed", "equals": 3600}]),
    ], "answer": "Created the fox/slime game, observed the real losing playtest, adjusted its health component, replayed a bounded movement route and observed a real sixty-second win. Exported the exact revised Game."}
    output.write_text(json.dumps({"game-author-native": plan}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    prepare(Path(sys.argv[1]), Path(sys.argv[2]))
