"""Deterministic note-event metrics for transcription fixtures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NoteEvent:
    pitch: int
    onset: float
    duration: float


@dataclass(frozen=True)
class TranscriptionScore:
    precision: float
    recall: float
    f1: float
    mean_onset_error: float
    mean_duration_error: float


def score_notes(expected: tuple[NoteEvent, ...], actual: tuple[NoteEvent, ...], *, onset_tolerance: float = .05) -> TranscriptionScore:
    remaining = set(range(len(actual)))
    matches: list[tuple[NoteEvent, NoteEvent]] = []
    for target in expected:
        candidates = [index for index in remaining if actual[index].pitch == target.pitch and abs(actual[index].onset - target.onset) <= onset_tolerance]
        if not candidates:
            continue
        selected = min(candidates, key=lambda index: abs(actual[index].onset - target.onset))
        remaining.remove(selected)
        matches.append((target, actual[selected]))
    precision = len(matches) / len(actual) if actual else (1.0 if not expected else 0.0)
    recall = len(matches) / len(expected) if expected else (1.0 if not actual else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    onset_error = sum(abs(left.onset - right.onset) for left, right in matches) / len(matches) if matches else 0.0
    duration_error = sum(abs(left.duration - right.duration) for left, right in matches) / len(matches) if matches else 0.0
    return TranscriptionScore(precision, recall, f1, onset_error, duration_error)
