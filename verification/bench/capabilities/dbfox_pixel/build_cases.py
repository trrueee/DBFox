"""Reproducible scripted requests and independent golden probes, not a rendered final document."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FRAME = "$frames.items.0.id"
LAYER = "$layers.items.0.id"


def call(identity, tool, args, **checks):
    return {"id": identity, "tool": tool, "arguments": args, **checks}


def write(identity, operations, **checks):
    return call(identity, "pixel_apply", {"document_id": "$document_id", "expected_version": "$revision", "operations": operations}, **checks)


def rectangle(x, y, width, height, color=1, *, frame=FRAME, layer=LAYER, filled=True):
    return {"kind": "rect", "frame_id": frame, "layer_id": layer, "rect": {"x": x, "y": y, "width": width, "height": height}, "palette_index": color, "filled": filled}


def area(x, y, width, height, frame="frame_1", layer="layer_1"):
    return {"frame_id": frame, "layer_id": layer, "x": x, "y": y, "width": width, "height": height}


def inspect(identity="inspect", **extra):
    return call(identity, "pixel_inspect", {"document_id": "$document_id", **extra}, unchanged=True)


def base(width=8, height=8, **extra):
    return [call("create", "pixel_create", {"library_id": "$project", "title": "Pixel independent example", "width": width, "height": height, "expected_version": 0, **extra}),
        inspect("frames", kind="frames"), inspect("layers", kind="layers")]


def case(identity, steps, *, assertions=None, prompt=None, **extra):
    return {"case_id": identity, "category": identity, "prompt": prompt or "Create a Pixel document and perform only the explicitly specified incremental operations.",
            "steps": steps, "assertions": assertions or {}, **extra}


def build():
    cases = [case("simple-creation", base(), assertions={"revision": 1, "nonzero": 0, "frame_count": 1, "layer_count": 1})]
    cases.append(case("incremental-modification", base() + [write("block", [rectangle(1, 1, 3, 3)], allowed_changes=[area(1, 1, 3, 3)]),
        write("detail", [rectangle(2, 2, 1, 1, 2)], allowed_changes=[area(2, 2, 1, 1)])],
        assertions={"revision": 3, "nonzero": 9, "points": [["frame_1", "layer_1", 2, 2, 2], ["frame_1", "layer_1", 1, 1, 1], ["frame_1", "layer_1", 0, 0, 0]]}))
    cases.append(case("multi-stage-creation", base() + [write("shape", [rectangle(1, 1, 2, 2)]),
        call("duplicate", "frame_duplicate", {"document_id": "$document_id", "expected_version": "$revision", "operation": {"kind": "frame_duplicate", "source_frame_id": FRAME, "frame_id": "second", "position": 1}}),
        call("layer", "layer_create", {"document_id": "$document_id", "expected_version": "$revision", "operation": {"kind": "layer_create", "layer_id": "highlights", "name": "Highlights", "position": 1}}),
        write("highlight", [rectangle(1, 1, 1, 1, 2, frame="second", layer="highlights"), {"kind": "tag_set", "tag_id": "anim", "name": "Animation", "frame_ids": [FRAME, "second"]}])],
        assertions={"revision": 5, "frame_count": 2, "layer_count": 2, "points": [["second", "layer_1", 2, 2, 1], ["second", "highlights", 1, 1, 2], ["frame_1", "highlights", 1, 1, 0]]}))
    cases.append(case("invalid-instruction-recovery", base() + [write("outside", [rectangle(7, 7, 2, 2)], succeeds=False, unchanged=True),
        inspect("after-invalid", frame_id=FRAME, layer_id=LAYER, rect={"x": 6, "y": 6, "width": 2, "height": 2}), write("correct", [rectangle(6, 6, 2, 2)])], assertions={"revision": 2, "nonzero": 4}))
    cases.append(case("inspect-before-edit", base() + [write("draw", [rectangle(1, 1, 3, 3)]),
        inspect("sample", frame_id=FRAME, layer_id=LAYER, rect={"x": 0, "y": 0, "width": 4, "height": 4}),
        write("sample-correction", [rectangle(1, 1, 1, 1, 2)], allowed_changes=[area(1, 1, 1, 1)])], assertions={"revision": 3, "provider_pixels": "sample"}))
    stale = write("stale", [rectangle(0, 0, 1, 1, 2)], succeeds=False, unchanged=True)
    stale["arguments"]["expected_version"] = "$create.revision"
    cases.append(case("stale-version", base() + [write("fresh", [rectangle(1, 1, 2, 2)]), stale, inspect("latest"),
        write("retry-intent-after-inspect", [rectangle(0, 0, 1, 1, 2)])], assertions={"revision": 3, "nonzero": 5}))
    cases.append(case("no-op", base() + [write("block", [rectangle(1, 1, 2, 2)]),
        write("same", [rectangle(1, 1, 2, 2)], unchanged=True)], assertions={"revision": 2, "noops": ["same"]}))
    cases.append(case("ambiguous-request", base() + [write("two-targets", [rectangle(1, 1, 1, 1), rectangle(6, 1, 1, 1)]),
        {"id": "clarify", "kind": "answer", "text": "请明确要修改左侧还是右侧标记；我尚未替你选择目标。"}],
        prompt="Draw two matching markers; when asked to improve 'that one', ask which marker before changing anything.",
        assertions={"revision": 2, "nonzero": 2, "clarification": True}))
    cases.append(case("large-document", base(128, 128) + [write("layers16", [{"kind": "layer_create", "layer_id": f"large_{i}", "name": f"Layer {i}", "position": i} for i in range(1, 16)]),
        write("upper-corner", [rectangle(127, 127, 1, 1, 2, layer="large_15")]),
        inspect("large-pixels", frame_id=FRAME, layer_id="large_15", rect={"x": 112, "y": 112, "width": 16, "height": 16}),
        write("over-quota", [{"kind": "frame_create", "frame_id": "too-large", "position": 1}], succeeds=False, unchanged=True)],
        assertions={"revision": 3, "frame_count": 1, "layer_count": 16, "nonzero": 1, "provider_pixels": "large-pixels"}))
    cases.append(case("bounded-context", base(32, 32, title="狐🦊" * 80) + [write("many-frames", [{"kind": "frame_create", "frame_id": f"frame_{i}", "position": i - 1} for i in range(2, 65)]),
        write("tags", [{"kind": "tag_set", "tag_id": f"tag{i}", "name": "狐🦊" * 40, "frame_ids": ["frame_1"] + [f"frame_{j}" for j in range(2, 65)]} for i in range(16)]),
        inspect("inspect-tags", kind="tags"), *[inspect(f"page{i}", kind="frames", page=i, page_size=16) for i in range(4)]],
        assertions={"revision": 3, "frame_count": 64, "layer_count": 1, "frame_pages": ["page0", "page1", "page2", "page3"]}))
    human = {"id": "human", "kind": "human", "arguments": {"document_id": "$document_id", "expected_version": "$revision", "mutation_id": "human-one", "operations": [rectangle(6, 6, 1, 1, 2)]}}
    cases.append(case("human-then-agent", base() + [write("agent-first", [rectangle(1, 1, 2, 2)]), human,
        write("old-agent-intent", [rectangle(0, 0, 1, 1)], succeeds=False, unchanged=True), inspect("human-visible"),
        write("agent-after-inspect", [rectangle(0, 0, 1, 1)], allowed_changes=[area(0, 0, 1, 1)])],
        assertions={"revision": 4, "points": [["frame_1", "layer_1", 6, 6, 2], ["frame_1", "layer_1", 0, 0, 1]], "human_steps": 1}))
    cases.append(case("negative-no-mutation", base() + [{"id": "deny", "kind": "answer", "text": "No changes made: loading an external image URL is outside the supported Pixel operations."}],
        prompt="Create a blank document; then refuse importing arbitrary remote images without changing the document.", assertions={"revision": 1, "nonzero": 0}))
    cases.append(case("whole-document-replacement-rejected", base() + [call("replace-all", "pixel_apply", {"document_id": "$document_id", "expected_version": "$revision", "document": {"title": "Replacement"}, "operations": [{"kind": "replace_document", "document": {}}]}, succeeds=False, unchanged=True), inspect("unchanged")], assertions={"revision": 1, "nonzero": 0}))
    scale = base(16, 16)
    for start in range(1, 200, 32):
        scale.append(write(f"scale-frames-{start}", [{"kind": "frame_create", "frame_id": f"scale_{index}", "position": index}
            for index in range(start, min(200, start + 32))]))
    scale += [write("scale-layer-all-frames", [{"kind": "layer_create", "layer_id": "scale-overlay", "name": "200 cels", "position": 1}]),
        call("scale-undo-layer", "pixel_undo", {"document_id": "$document_id", "expected_version": "$revision", "restore_revision": "$scale-frames-193.revision"}),
        *[inspect(f"scale-page-{index}", kind="frames", page=index, page_size=16) for index in range(13)],
        call("scale-export", "pixel_export", {"document_id": "$document_id", "expected_version": "$revision"}, unchanged=True)]
    cases.append(case("hundreds-of-frames", scale, assertions={"revision": 10, "frame_count": 200, "layer_count": 1, "nonzero": 0,
        "frame_pages": [f"scale-page-{index}" for index in range(13)], "truncated_frame_changes": ["scale-layer-all-frames", "scale-undo-layer"]}))
    cases.append(knight())
    return {"schema_version": "1.0", "cases": cases}


def knight():
    palette = [{"name": name, "color": color} for name, color in [
        ("Transparent", "#00000000"), ("Outline", "#25243CFF"), ("Fox", "#D97332FF"), ("Cream", "#FFE7B7FF"),
        ("Steel", "#708DB0FF"), ("Steel light", "#BDD4EAFF"), ("Gold", "#E5B44BFF"), ("Spark", "#FFF4BEFF")]]
    steps = base(32, 32, title="Fox Knight — idle and attack", palette=palette)
    body = [rectangle(8, 5, 16, 10), rectangle(9, 6, 14, 8, 2), rectangle(8, 2, 5, 6), rectangle(19, 2, 5, 6),
        rectangle(9, 3, 3, 4, 2), rectangle(20, 3, 3, 4, 2), rectangle(11, 11, 10, 3, 3), rectangle(15, 10, 2, 2),
        rectangle(11, 8, 2, 2), rectangle(19, 8, 2, 2), rectangle(10, 15, 12, 11), rectangle(11, 16, 10, 9, 2),
        rectangle(10, 26, 5, 4), rectangle(18, 26, 5, 4), rectangle(4, 19, 7, 6), rectangle(5, 20, 5, 4, 2), rectangle(4, 19, 3, 3, 3)]
    steps += [write("silhouette-and-face", body),
        write("layer-structure", [{"kind": "layer_update", "layer_id": LAYER, "name": "Fox silhouette"}, {"kind": "layer_create", "layer_id": "armor", "name": "Armor and sword", "position": 1}, {"kind": "layer_create", "layer_id": "effects", "name": "Attack glints", "position": 2}])]
    armor = [rectangle(10, 16, 12, 8, 4, layer="armor"), rectangle(11, 17, 3, 5, 5, layer="armor"), rectangle(10, 23, 12, 2, 6, layer="armor"),
        rectangle(15, 23, 2, 2, 1, layer="armor"), rectangle(9, 4, 14, 2, 4, layer="armor"), rectangle(15, 3, 2, 4, 6, layer="armor"),
        rectangle(24, 11, 2, 12, 5, layer="armor"), rectangle(22, 21, 6, 2, 6, layer="armor"), rectangle(24, 23, 2, 3, 1, layer="armor")]
    steps.append(write("armor-and-equipment", armor))
    frame_ids = ["frame_1", "idle_2", "idle_3", "idle_4"] + [f"attack_{i}" for i in range(1, 7)]
    steps.append(write("animation-structure", [{"kind": "frame_duplicate", "source_frame_id": FRAME, "frame_id": identity, "position": index} for index, identity in enumerate(frame_ids[1:], 1)]))
    poses = []
    for index, identity in enumerate(frame_ids[1:4], 1):
        poses.append({"kind": "frame_update", "frame_id": identity, "duration_ms": 160 + index * 20})
        poses.append(rectangle(11, 8, 2, 2, 2 if index == 2 else 1, frame=identity))
        poses.append(rectangle(19, 8, 2, 2, 2 if index == 2 else 1, frame=identity))
        poses.append(rectangle(5 + index, 23, 1, 1, 6, frame=identity))
    for index, identity in enumerate(frame_ids[4:], 1):
        poses.append({"kind": "frame_update", "frame_id": identity, "duration_ms": 60 + index * 10})
        poses.append({"kind": "region_transform", "frame_id": identity, "layer_id": "armor", "rect": {"x": 22, "y": 11, "width": 6, "height": 15},
                      "transform": "rotate_cw", "destination": {"x": 16, "y": 9 + index}, "mode": "move"})
        poses.append({"kind": "line", "frame_id": identity, "layer_id": "effects", "x0": 19, "y0": 5 + index, "x1": 30, "y1": 8 + index, "palette_index": 7})
    steps += [write("distinct-idle-and-attack-poses", poses), write("playback-tags", [
        {"kind": "tag_set", "tag_id": "idle", "name": "Idle", "frame_ids": frame_ids[:4], "loop": True},
        {"kind": "tag_set", "tag_id": "attack", "name": "Attack", "frame_ids": frame_ids[4:], "loop": False}]),
        call("initial-export", "pixel_export", {"document_id": "$document_id", "expected_version": "$revision"}, unchanged=True)]
    # Ten change categories after a substantive complete ten-frame animation exists.
    steps += [write("add-glint", [rectangle(28, 8, 2, 2, 7, frame="attack_6", layer="effects")], allowed_changes=[area(28, 8, 2, 2, "attack_6", "effects")]),
        write("delete-glint", [rectangle(28, 8, 1, 1, 0, frame="attack_6", layer="effects")], allowed_changes=[area(28, 8, 1, 1, "attack_6", "effects")]),
        write("local-face-refinement", [rectangle(14, 12, 1, 1, 6)], allowed_changes=[area(14, 12, 1, 1)]),
        write("broad-frame-and-layer-order", [{"kind": "frame_update", "frame_id": "attack_6", "position": 4}, {"kind": "layer_update", "layer_id": "effects", "position": 1}]),
        write("parameter-20-percent", [{"kind": "frame_update", "frame_id": "idle_2", "duration_ms": 144}, {"kind": "palette_set", "index": 4, "name": "Steel", "color": "#607DA0FF"}]),
        {"id": "ambiguous-ask", "kind": "answer", "text": "请明确要调整哪一帧和哪个部位；我没有猜测目标，作品保持当前修订。"},
        inspect("after-clarification"), write("clarified-target", [rectangle(11, 17, 1, 1, 6, frame="attack_2", layer="armor")], allowed_changes=[area(11, 17, 1, 1, "attack_2", "armor")])]
    stale = write("conflicting-old-revision", [rectangle(0, 0, 1, 1)], succeeds=False, unchanged=True)
    stale["arguments"]["expected_version"] = "$initial-export.revision"
    steps += [stale, inspect("after-conflict"), {"id": "human-shield", "kind": "human", "arguments": {"document_id": "$document_id", "expected_version": "$revision", "mutation_id": "human-shield", "operations": [rectangle(6, 17, 2, 3, 6, frame="attack_1", layer="armor")]}},
        inspect("after-human"), write("agent-shield-highlight", [rectangle(6, 17, 1, 1, 5, frame="attack_1", layer="armor")], allowed_changes=[area(6, 17, 1, 1, "attack_1", "armor")]),
        write("temporary-correction", [rectangle(31, 31, 1, 1, 7)]),
        call("undo-correction", "pixel_undo", {"document_id": "$document_id", "expected_version": "$revision", "restore_revision": "$agent-shield-highlight.revision"}),
        write("final-refinement", [rectangle(12, 18, 1, 2, 7, frame="attack_3", layer="armor")], allowed_changes=[area(12, 18, 1, 2, "attack_3", "armor")]),
        call("final-export", "pixel_export", {"document_id": "$document_id", "expected_version": "$revision"}, unchanged=True)]
    return case("fox-knight-stress", steps, stress=True,
        prompt="Create a 32×32 fox knight with four distinct idle poses and six distinct attack poses. Keep stable layers, indexed palette, timing and explicit tags. Apply the specified incremental refinements, ask about ambiguity, reject stale edits, inspect after the human shield edit, undo only the temporary correction, then export.",
        clarification="Adjust only attack_2 armor at (11,17). Keep all other pixels. Continue the listed stale check, human shield edit, inspect, local highlight, undo of the temporary correction and final export.",
        assertions={"frame_count": 10, "layer_count": 3, "human_steps": 1, "clarification": True,
            "points": [["frame_1", "layer_1", 31, 31, 0], ["attack_1", "armor", 7, 19, 6], ["attack_1", "armor", 6, 17, 5]],
            "tags": {"idle": frame_ids[:4], "attack": frame_ids[4:]}, "distinct_frames": 10})


def main():
    (HERE / "cases.json").write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
