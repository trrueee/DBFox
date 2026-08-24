from __future__ import annotations

from collections import Counter, defaultdict
import re

from .contracts import (
    AudioTranscription,
    KeySignature,
    ComposePianoInput,
    HarmonyEvent,
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
_HARMONY_ROOT = re.compile(r"^(?P<root>[A-G](?:#|b)?)(?P<body>.*)$")
_HARMONY_SLASH_BASS = re.compile(r"^(?P<body>.*)/(?P<bass>[A-G](?:#|b)?)$")


def _transpose_pitch_name(name: str, semitones: int) -> str:
    return _SHARP_NAMES[(_PITCH_CLASS[name] + semitones) % 12]


def _transpose_harmony_symbol(symbol: str, semitones: int) -> str:
    match = _HARMONY_ROOT.fullmatch(symbol)
    if match is None:
        return symbol
    root = _transpose_pitch_name(match.group("root"), semitones)
    body = match.group("body")
    slash = _HARMONY_SLASH_BASS.fullmatch(body)
    bass = slash.group("bass") if slash else None
    body = slash.group("body") if slash else body
    suffix = f"/{_transpose_pitch_name(bass, semitones)}" if bass else ""
    return f"{root}{body}{suffix}"


def expand_piano_composition(input: ComposePianoInput) -> ScoreDocument:
    """Deterministically expand a compact creative plan into canonical notes."""

    notes: list[ScoreNote] = []
    harmony: list[HarmonyEvent] = []
    note_sequence = 0

    def append_note(*, measure: int, beat: float, duration: float, pitch: int, velocity: float, hand: str) -> None:
        nonlocal note_sequence
        note_sequence += 1
        notes.append(ScoreNote(
            id=f"compose_{note_sequence:05d}",
            measure=measure,
            beat=round(beat, 6),
            duration=round(duration, 6),
            pitch=pitch,
            velocity=velocity,
            hand=hand,
        ))

    for plan in input.composition.measures:
        harmony.append(HarmonyEvent(measure=plan.measure, beat=0, symbol=plan.chord))
        for melody_note in plan.melody:
            append_note(
                measure=plan.measure,
                beat=melody_note.beat,
                duration=melody_note.duration,
                pitch=melody_note.pitch,
                velocity=melody_note.velocity,
                hand="right",
            )
        pitches = plan.chord_pitches
        if plan.accompaniment == "arpeggio_eighths":
            duration = 0.5
            beats = [index * duration for index in range(int(input.meter.beats / duration))]
            sequence = [pitches[index % len(pitches)] for index in range(len(beats))]
        elif plan.accompaniment == "broken_quarters":
            duration = 1.0
            beats = [float(index) for index in range(input.meter.beats)]
            sequence = [pitches[index % len(pitches)] for index in range(len(beats))]
        elif plan.accompaniment == "root_fifth_half_notes":
            duration = 2.0
            beats = [float(index) for index in range(0, input.meter.beats, 2)]
            support = pitches[-1] if len(pitches) == 2 else pitches[1]
            sequence = [pitches[0] if index % 2 == 0 else support for index in range(len(beats))]
        else:
            duration = 2.0
            beats = [float(index) for index in range(0, input.meter.beats, 2)]
            sequence = []
        if plan.accompaniment == "block_half_notes":
            for beat in beats:
                for pitch in pitches:
                    append_note(
                        measure=plan.measure,
                        beat=beat,
                        duration=min(duration, input.meter.beats - beat),
                        pitch=pitch,
                        velocity=plan.accompaniment_velocity,
                        hand="left",
                    )
        else:
            for beat, pitch in zip(beats, sequence):
                append_note(
                    measure=plan.measure,
                    beat=beat,
                    duration=min(duration, input.meter.beats - beat),
                    pitch=pitch,
                    velocity=plan.accompaniment_velocity,
                    hand="left",
                )
    return ScoreDocument(
        title=input.title,
        tempo=input.tempo,
        meter=input.meter,
        key=input.key,
        measure_count=input.measure_count,
        sections=input.composition.sections,
        notes=tuple(sorted(notes, key=_note_order)),
        pedal=input.composition.pedal,
        dynamics=input.composition.dynamics,
        harmony=tuple(harmony),
        annotations=input.composition.annotations,
    )


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
    tonic = _transpose_pitch_name(document.key.tonic, semitones)
    return ScoreDocument.model_validate({
        **document.model_dump(mode="json"),
        "key": KeySignature(tonic=tonic, mode=document.key.mode).model_dump(mode="json"),
        "notes": [note.model_dump(mode="json") for note in notes],
        "harmony": [
            event.model_copy(
                update={"symbol": _transpose_harmony_symbol(event.symbol, semitones)}
            ).model_dump(mode="json")
            for event in document.harmony
        ],
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
