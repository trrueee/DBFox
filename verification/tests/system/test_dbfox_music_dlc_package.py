"""Conformance coverage for the dbfox.music capability boundary."""

from __future__ import annotations

from pathlib import Path
import wave

import pytest

from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.dlc.api import DlcOperationContext, ResourceScopeRef
from engine.tools.runtime import ToolRunContext
from scripts.build_dbfox_music_dlc_fixture import SOURCE_ROOT, build_dbfox_music_dlc_fixture


def _snapshot(tmp_path: Path):
    built = build_dbfox_music_dlc_fixture(tmp_path / "archives")
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")
    service.trust_publisher_from_file(
        built.archive,
        expected_package_digest=built.package_digest,
        expected_publisher_key_id=built.publisher_fingerprint,
    )
    service.install_from_file(built.archive)
    service.set_desired_enabled("dbfox.music", True)
    snapshot = ContributionCompiler(service.storage_root).compile(built_ins=BuiltinContributionSet())
    assert snapshot.activation_failures == ()
    return service, snapshot


def _invoke(snapshot, name: str, project_id: str, payload: dict):
    contribution = snapshot.get_operation("dbfox.music", name)
    assert contribution is not None
    result = contribution.spec.handler(
        contribution.spec.input_model.model_validate(payload),
        DlcOperationContext(dlc_id="dbfox.music", operation_name=name, project_id=project_id),
    )
    return contribution.spec.output_model.model_validate(result)


def test_music_source_uses_only_public_extension_api() -> None:
    for source in sorted((SOURCE_ROOT / "backend").rglob("*.py")):
        value = source.read_text(encoding="utf-8")
        assert "from engine" not in value
        assert "import engine" not in value


def test_music_package_owns_complete_capability_contributions(tmp_path: Path) -> None:
    _service, snapshot = _snapshot(tmp_path)
    assert {item.tool.name for item in snapshot.tools} == {
        "music_compose_piano",
        "music_revise_phrase",
        "music_reharmonize",
        "music_simplify",
        "music_transpose",
        "music_analyze_score",
        "music_analyze_audio",
        "music_transcribe_piano",
        "music_align_score_to_audio",
    }
    assert [item.kind for item in snapshot.resource_resolvers] == [
        "dbfox.music.library",
        "dbfox.music.score",
        "dbfox.music.audio",
    ]
    assert {item.artifact_type for item in snapshot.artifact_contracts} == {
        "dbfox.music.score_revision",
        "dbfox.music.analysis",
        "dbfox.music.audio_analysis",
        "dbfox.music.transcription",
        "dbfox.music.alignment",
    }
    assert [(item.owner_id, item.support.id) for item in snapshot.completion_supports] == [
        ("dbfox.music", "dbfox.music.score_revision")
    ]
    active = next(item for item in snapshot.active_dlcs if item.dlc_id == "dbfox.music")
    assert active.frontend_entrypoint == "frontend/index.js"


def test_score_revisions_are_immutable_and_resource_authority_is_head_bound(tmp_path: Path) -> None:
    _service, snapshot = _snapshot(tmp_path)
    created = _invoke(snapshot, "scores.create_blank", "project-music", {
        "title": "Moonlit Window",
        "tempo": 76,
        "meter": {"beats": 4, "beat_unit": 4},
        "key": {"tonic": "C", "mode": "major"},
        "measure_count": 16,
    })
    score_id = created.score.id
    original_hash = created.revision.content_hash
    renamed = _invoke(snapshot, "scores.rename", "project-music", {
        "score_id": score_id,
        "title": "Moonlit Window II",
    })
    assert renamed.revision.revision == 2
    assert renamed.revision.parent_revision == 1
    assert renamed.revision.content_hash != original_hash
    first = _invoke(snapshot, "scores.get", "project-music", {"score_id": score_id, "revision": 1})
    assert first.revision.document.title == "Moonlit Window"
    resolver = next(item.resolver for item in snapshot.resource_resolvers if item.kind == "dbfox.music.score")
    with pytest.raises(ValueError, match="stale"):
        resolver(ResourceScopeRef(kind="dbfox.music.score", id=score_id, version=1))
    resolved = resolver(ResourceScopeRef(kind="dbfox.music.score", id=score_id, version=2))
    assert resolved.content_hash == renamed.revision.content_hash


def test_transpose_tool_is_deterministic_and_preserves_old_revision(tmp_path: Path) -> None:
    _service, snapshot = _snapshot(tmp_path)
    library_resolver = next(item.resolver for item in snapshot.resource_resolvers if item.kind == "dbfox.music.library")
    library_ref = ResourceScopeRef(kind="dbfox.music.library", id="project-compose", version="1")
    library = library_resolver(library_ref)
    compose = next(item.tool for item in snapshot.tools if item.tool.name == "music_compose_piano")
    draft = {
        "title": "First Light",
        "tempo": 80,
        "meter": {"beats": 4, "beat_unit": 4},
        "key": {"tonic": "C", "mode": "major"},
        "measure_count": 1,
        "notes": [
            {"id": "n1", "measure": 1, "beat": 0, "duration": 1, "pitch": 60, "velocity": .7, "hand": "right"},
            {"id": "n2", "measure": 1, "beat": 0, "duration": 1, "pitch": 48, "velocity": .6, "hand": "left"},
        ],
    }
    composed = compose.run(compose.input_model.model_validate({
        "title": "First Light", "intent": "quiet", "tempo": 80,
        "meter": draft["meter"], "key": draft["key"], "measure_count": 1, "score_draft": draft,
    }), ToolRunContext.for_invocation(
        request=None, idempotency_key="compose-1", scope_refs=(library_ref,),
        resources={library_ref.canonical(): library},
    ))
    score_id = composed.output.score_id
    score_resolver = next(item.resolver for item in snapshot.resource_resolvers if item.kind == "dbfox.music.score")
    score_ref = ResourceScopeRef(kind="dbfox.music.score", id=score_id, version=1)
    frozen = score_resolver(score_ref)
    transpose = next(item.tool for item in snapshot.tools if item.tool.name == "music_transpose")
    outcome = transpose.run(transpose.input_model.model_validate({"score_id": score_id, "semitones": 2}), ToolRunContext.for_invocation(
        request=None, idempotency_key="transpose-1", scope_refs=(score_ref,),
        resources={score_ref.canonical(): frozen},
    ))
    assert outcome.output.revision == 2
    first = _invoke(snapshot, "scores.get", "project-compose", {"score_id": score_id, "revision": 1})
    second = _invoke(snapshot, "scores.get", "project-compose", {"score_id": score_id, "revision": 2})
    assert [note.pitch for note in first.revision.document.notes] == [60, 48]
    assert [note.pitch for note in second.revision.document.notes] == [62, 50]


def test_audio_transcription_is_durable_versioned_and_normalizes_to_score(tmp_path: Path) -> None:
    _service, snapshot = _snapshot(tmp_path)
    source_path = tmp_path / "piano.wav"
    with wave.open(str(source_path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(22_050)
        stream.writeframes(b"\0\0" * 22_050)
    import_spec = snapshot.get_operation("dbfox.music", "audio.import")
    assert import_spec is not None
    assert import_spec.spec.capabilities == ("filesystem_read",)
    imported = _invoke(snapshot, "audio.import", "project-audio", {
        "source_path": str(source_path), "name": "piano.wav", "media_type": "audio/wav",
        "duration_seconds": 1.0, "sample_rate": 22_050, "channels": 1,
    })
    audio_id = imported.source.id
    before_ref = ResourceScopeRef(
        kind="dbfox.music.audio", id=audio_id,
        version=f"{imported.source.fingerprint}:0",
    )
    committed = _invoke(snapshot, "audio.commit_transcription", "project-audio", {
        "audio_source_id": audio_id,
        "provider_id": "spotify.basic-pitch", "provider_version": "1.0.1",
        "tempo": 60, "meter": {"beats": 4, "beat_unit": 4},
        "key": {"tonic": "C", "mode": "major"}, "confidence": .83,
        "notes": [
            {"start_seconds": 0, "end_seconds": .5, "pitch": 60, "velocity": .8, "confidence": .9},
            {"start_seconds": .5, "end_seconds": 1, "pitch": 48, "velocity": .65, "confidence": .76},
        ],
        "uncertain_ranges": [{"start_seconds": .5, "end_seconds": 1, "confidence": .48, "reason": "low_note_confidence"}],
    })
    assert committed.source.analysis_revision == 1
    assert committed.transcription is not None
    assert committed.transcription.notes[0].pitch == 60
    resolver = next(item.resolver for item in snapshot.resource_resolvers if item.kind == "dbfox.music.audio")
    with pytest.raises(ValueError, match="stale"):
        resolver(before_ref)
    current_ref = ResourceScopeRef(
        kind="dbfox.music.audio", id=audio_id,
        version=f"{committed.source.fingerprint}:1",
    )
    resource = resolver(current_ref)
    analysis_tool = next(item.tool for item in snapshot.tools if item.tool.name == "music_analyze_audio")
    analysis = analysis_tool.run(analysis_tool.input_model.model_validate({
        "audio_source_id": audio_id,
    }), ToolRunContext.for_invocation(
        request=None, idempotency_key="analyze-audio-1", scope_refs=(current_ref,),
        resources={current_ref.canonical(): resource},
    ))
    assert analysis.output.audio_source_id == audio_id
    assert analysis.output.note_count == 2
    assert analysis.output.uncertain_range_count == 1
    assert analysis.artifacts[0].type == "dbfox.music.audio_analysis"
    tool = next(item.tool for item in snapshot.tools if item.tool.name == "music_transcribe_piano")
    outcome = tool.run(tool.input_model.model_validate({
        "audio_source_id": audio_id, "title": "Piano Take", "quantization": "1/16",
    }), ToolRunContext.for_invocation(
        request=None, idempotency_key="transcribe-1", scope_refs=(current_ref,),
        resources={current_ref.canonical(): resource},
    ))
    assert outcome.output.score_revision == 1
    assert {artifact.type for artifact in outcome.artifacts} == {
        "dbfox.music.score_revision", "dbfox.music.transcription",
    }
    score = _invoke(snapshot, "scores.get", "project-audio", {"score_id": outcome.output.score_id})
    assert [note.pitch for note in score.revision.document.notes] == [60, 48]
