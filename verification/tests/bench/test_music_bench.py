from __future__ import annotations

from pathlib import Path

import pytest

from verification.bench.capabilities.dbfox_music.direct.runtime import run_music_direct_bench
from verification.bench.capabilities.dbfox_music.transcription.scoring import NoteEvent, score_notes
from verification.bench.composition.core_music.runtime import run_core_music_bench


def test_music_direct_bench_runs_production_capability(tmp_path: Path) -> None:
    report = run_music_direct_bench(output_dir=tmp_path / "music-direct", repetitions=1)
    assert report["passed_trials"] == 4
    assert report["scored_trials"] == 4


def test_transcription_note_scorer_matches_pitch_and_bounded_onset() -> None:
    expected = (NoteEvent(60, 0, .5), NoteEvent(64, .5, .5), NoteEvent(67, 1, 1))
    actual = (NoteEvent(60, .01, .48), NoteEvent(64, .52, .45), NoteEvent(69, 1, 1))
    score = score_notes(expected, actual)
    assert score.precision == pytest.approx(2 / 3)
    assert score.recall == pytest.approx(2 / 3)
    assert score.mean_onset_error == pytest.approx(.015)


def test_core_music_composition_uses_real_runloop(tmp_path: Path) -> None:
    report = run_core_music_bench(output_dir=tmp_path / "core-music", repetitions=1)
    assert report["passed_trials"] == 1
    assert report["scored_trials"] == 1
