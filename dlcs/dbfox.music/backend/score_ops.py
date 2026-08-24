from __future__ import annotations

from collections import Counter, defaultdict

from .contracts import (
    AudioTranscription,
    KeySignature,
    ScoreAnalysisOutput,
    ScoreDocument,
    ScoreNote,
)


_PITCH_CLASS = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}
_SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def replace_phrase(
    document: ScoreDocument,
    start: int,
    end: int,
    replacement: tuple[ScoreNote, ...],
) -> ScoreDocument:
    if end > document.measure_count:
        raise ValueError("selected measure range exceeds the score")
    target_indexes = [
        index for index, note in enumerate(document.notes)
        if start <= note.measure <= end
    ]
    insertion_index = target_indexes[0] if target_indexes else next(
        (index for index, note in enumerate(document.notes) if note.measure > end),
        len(document.notes),
    )
    notes: list[ScoreNote] = []
    inserted = False
    for index, note in enumerate(document.notes):
        if index == insertion_index:
            notes.extend(sorted(replacement, key=_note_order))
            inserted = True
        if not start <= note.measure <= end:
            notes.append(note)
    if not inserted:
        notes.extend(sorted(replacement, key=_note_order))
    return ScoreDocument.model_validate({
        **document.model_dump(mode="json"),
        "notes": [note.model_dump(mode="json") for note in notes],
    })


def transpose(document: ScoreDocument, semitones: int) -> ScoreDocument:
    notes = [
        note.model_copy(update={"pitch": note.pitch + semitones})
        for note in document.notes
    ]
    if any(note.pitch < 21 or note.pitch > 108 for note in notes):
        raise ValueError("transposition would move notes outside the 88-key piano range")
    tonic = _SHARP_NAMES[(_PITCH_CLASS[document.key.tonic] + semitones) % 12]
    return ScoreDocument.model_validate({
        **document.model_dump(mode="json"),
        "key": KeySignature(tonic=tonic, mode=document.key.mode).model_dump(mode="json"),
        "notes": [note.model_dump(mode="json") for note in notes],
    })


def simplify(
    document: ScoreDocument,
    *,
    start: int,
    end: int,
    hand: str,
) -> ScoreDocument:
    if end > document.measure_count:
        raise ValueError("selected measure range exceeds the score")
    target_hands = {"left", "right"} if hand == "both" else {hand}
    groups: dict[tuple[int, float, float, str, int], list[ScoreNote]] = defaultdict(list)
    untouched: list[ScoreNote] = []
    for note in document.notes:
        if start <= note.measure <= end and note.hand in target_hands:
            groups[(note.measure, note.beat, note.duration, note.hand, note.voice)].append(note)
        else:
            untouched.append(note)

    simplified: list[ScoreNote] = []
    for notes in groups.values():
        ordered = sorted(notes, key=lambda item: (item.pitch, item.id))
        # Keep the registral anchor and at most one close support tone. This
        # deterministically removes octave doubling and dense chords without
        # rewriting rhythm or notes outside the requested range.
        anchor = ordered[0] if ordered[0].hand == "left" else ordered[-1]
        simplified.append(anchor)
        candidates = [
            note for note in ordered
            if note.id != anchor.id and 3 <= abs(note.pitch - anchor.pitch) <= 7
        ]
        if candidates:
            simplified.append(min(candidates, key=lambda item: (abs(item.pitch - anchor.pitch), item.id)))
    return ScoreDocument.model_validate({
        **document.model_dump(mode="json"),
        "notes": [
            note.model_dump(mode="json")
            for note in sorted((*untouched, *simplified), key=_note_order)
        ],
    })


def analyze(score_id: str, revision: int, document: ScoreDocument) -> ScoreAnalysisOutput:
    pitches = [note.pitch for note in document.notes]
    simultaneous = Counter(
        (note.measure, round(note.beat, 6)) for note in document.notes
    )
    maximum_polyphony = max(simultaneous.values(), default=0)
    event_density = len(document.notes) / max(document.measure_count, 1)
    leaps: list[int] = []
    for hand in ("left", "right"):
        ordered = sorted((note for note in document.notes if note.hand == hand), key=_note_order)
        leaps.extend(abs(current.pitch - previous.pitch) for previous, current in zip(ordered, ordered[1:]))
    large_leaps = sum(value >= 12 for value in leaps)
    shortest = min((note.duration for note in document.notes), default=document.meter.beats)
    difficulty_score = event_density + maximum_polyphony * 1.5 + large_leaps * 0.15
    if shortest < 0.5:
        difficulty_score += 4
    difficulty = "beginner" if difficulty_score < 8 else "intermediate" if difficulty_score < 18 else "advanced"
    form = [section.label for section in document.sections] or ["through-composed"]
    key_name = f"{document.key.tonic} {document.key.mode}"
    harmonic_summary = (
        f"Declared in {key_name}; {maximum_polyphony}-note peak polyphony across "
        f"{document.measure_count} measures."
    )
    return ScoreAnalysisOutput(
        score_id=score_id,
        revision=revision,
        key=key_name,
        tempo=document.tempo,
        form=form,
        lowest_pitch=min(pitches) if pitches else None,
        highest_pitch=max(pitches) if pitches else None,
        maximum_polyphony=maximum_polyphony,
        estimated_difficulty=difficulty,
        harmonic_summary=harmonic_summary,
    )


def score_from_transcription(
    transcription: AudioTranscription,
    *,
    title: str,
    quantization: str,
) -> ScoreDocument:
    quantum = {"1/4": 1.0, "1/8": 0.5, "1/16": 0.25}[quantization]
    beats_per_second = transcription.tempo / 60.0
    prepared: list[tuple[float, float, int, float, float]] = []
    for note in transcription.notes:
        start = round((note.start_seconds * beats_per_second) / quantum) * quantum
        end = round((note.end_seconds * beats_per_second) / quantum) * quantum
        duration = max(quantum, end - start)
        prepared.append((start, duration, note.pitch, note.velocity, note.confidence))
    if not prepared:
        raise ValueError("transcription contains no notes")

    meter_beats = transcription.meter.beats
    maximum_end = max(start + duration for start, duration, *_ in prepared)
    measure_count = max(1, min(256, int((maximum_end + meter_beats - 1e-9) // meter_beats)))
    notes: list[ScoreNote] = []
    for index, (absolute_start, duration, pitch, velocity, _confidence) in enumerate(prepared, start=1):
        remaining = duration
        cursor = absolute_start
        segment = 1
        while remaining > 1e-9:
            measure = int(cursor // meter_beats) + 1
            if measure > measure_count:
                break
            beat = cursor - (measure - 1) * meter_beats
            segment_duration = min(remaining, meter_beats - beat)
            if segment_duration <= 1e-9:
                cursor = measure * meter_beats
                continue
            notes.append(ScoreNote(
                id=f"tx_{index:05d}_{segment}",
                measure=measure,
                beat=round(beat, 6),
                duration=round(segment_duration, 6),
                pitch=pitch,
                velocity=velocity,
                hand="left" if pitch < 60 else "right",
                voice=1,
            ))
            cursor += segment_duration
            remaining -= segment_duration
            segment += 1
    return ScoreDocument(
        title=title,
        tempo=transcription.tempo,
        meter=transcription.meter,
        key=transcription.key,
        measure_count=measure_count,
        notes=tuple(sorted(notes, key=_note_order)),
    )


def _note_order(note: ScoreNote) -> tuple[int, float, str, int, int, str]:
    return (note.measure, note.beat, note.hand, note.voice, note.pitch, note.id)
