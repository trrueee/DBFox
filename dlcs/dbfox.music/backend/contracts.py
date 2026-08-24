from __future__ import annotations

import math
import re
from typing import Literal

from dbfox_dlc_api import ToolInputModel, ToolOutputModel
from pydantic import BaseModel, ConfigDict, Field, model_validator


PIANO_LOW = 21
PIANO_HIGH = 108
MAX_MEASURES = 256
MAX_NOTES = 8192
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Meter(Contract):
    beats: int = Field(default=4, ge=1, le=16)
    beat_unit: Literal[1, 2, 4, 8, 16] = 4


class KeySignature(Contract):
    tonic: Literal[
        "C", "C#", "Db", "D", "D#", "Eb", "E", "F",
        "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B",
    ] = "C"
    mode: Literal["major", "minor"] = "major"


class ScoreSection(Contract):
    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=80)
    start_measure: int = Field(ge=1, le=MAX_MEASURES)
    end_measure: int = Field(ge=1, le=MAX_MEASURES)

    @model_validator(mode="after")
    def validate_range(self) -> "ScoreSection":
        if self.end_measure < self.start_measure:
            raise ValueError("section end_measure must not precede start_measure")
        if not _IDENTIFIER.fullmatch(self.id):
            raise ValueError("section id has an invalid format")
        return self


class ScoreNote(Contract):
    id: str = Field(min_length=1, max_length=128)
    measure: int = Field(ge=1, le=MAX_MEASURES)
    beat: float = Field(ge=0)
    duration: float = Field(gt=0, le=64)
    pitch: int = Field(ge=PIANO_LOW, le=PIANO_HIGH)
    velocity: float = Field(default=0.72, ge=0.01, le=1)
    hand: Literal["left", "right"]
    voice: int = Field(default=1, ge=1, le=4)

    @model_validator(mode="after")
    def validate_numbers(self) -> "ScoreNote":
        if not _IDENTIFIER.fullmatch(self.id):
            raise ValueError("note id has an invalid format")
        if not all(math.isfinite(value) for value in (self.beat, self.duration, self.velocity)):
            raise ValueError("note timing and velocity must be finite")
        return self


class PedalEvent(Contract):
    measure: int = Field(ge=1, le=MAX_MEASURES)
    beat: float = Field(ge=0)
    down: bool


class DynamicEvent(Contract):
    measure: int = Field(ge=1, le=MAX_MEASURES)
    beat: float = Field(ge=0)
    value: Literal["pp", "p", "mp", "mf", "f", "ff", "crescendo", "diminuendo"]


class ScoreAnnotation(Contract):
    measure: int = Field(ge=1, le=MAX_MEASURES)
    beat: float = Field(default=0, ge=0)
    text: str = Field(min_length=1, max_length=240)


class ScoreDocument(Contract):
    schema_version: Literal[1] = 1
    title: str = Field(min_length=1, max_length=160)
    tempo: int = Field(default=76, ge=30, le=240)
    meter: Meter = Field(default_factory=Meter)
    key: KeySignature = Field(default_factory=KeySignature)
    measure_count: int = Field(default=16, ge=1, le=MAX_MEASURES)
    sections: tuple[ScoreSection, ...] = ()
    notes: tuple[ScoreNote, ...] = Field(default=(), max_length=MAX_NOTES)
    pedal: tuple[PedalEvent, ...] = ()
    dynamics: tuple[DynamicEvent, ...] = ()
    annotations: tuple[ScoreAnnotation, ...] = ()

    @model_validator(mode="after")
    def validate_score(self) -> "ScoreDocument":
        note_ids = [note.id for note in self.notes]
        section_ids = [section.id for section in self.sections]
        if len(note_ids) != len(set(note_ids)):
            raise ValueError("note ids must be unique")
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("section ids must be unique")
        for section in self.sections:
            if section.end_measure > self.measure_count:
                raise ValueError("section range exceeds measure_count")
        for event in (*self.notes, *self.pedal, *self.dynamics, *self.annotations):
            if event.measure > self.measure_count:
                raise ValueError("score event exceeds measure_count")
            if not math.isfinite(event.beat) or event.beat >= self.meter.beats:
                raise ValueError("score event beat falls outside its measure")
        for note in self.notes:
            if note.beat + note.duration > self.meter.beats + 1e-9:
                raise ValueError("note duration crosses a measure boundary")
        return self


class MusicLibrary(Contract):
    project_id: str
    version: str = "1"


class ScoreSummary(Contract):
    id: str
    project_id: str
    title: str
    head_revision: int = Field(ge=1)
    status: Literal["active", "deleted"]
    content_hash: str
    tempo: int
    key: KeySignature
    meter: Meter
    measure_count: int
    created_at: str
    updated_at: str


class ScoreRevision(Contract):
    score_id: str
    project_id: str
    revision: int = Field(ge=1)
    parent_revision: int | None = Field(default=None, ge=1)
    content_hash: str
    document: ScoreDocument
    summary: str
    created_at: str


class ScoreRevisionArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    score_id: str = Field(alias="scoreId")
    revision: int = Field(ge=1)
    parent_revision: int | None = Field(default=None, alias="parentRevision", ge=1)
    content_hash: str = Field(alias="contentHash", pattern=r"^sha256:[0-9a-f]{64}$")
    title: str
    tempo: int
    key: str
    meter: str
    measure_count: int = Field(alias="measureCount", ge=1)


class ScoreAnalysisArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    score_id: str = Field(alias="scoreId")
    revision: int = Field(ge=1)
    content_hash: str = Field(alias="contentHash", pattern=r"^sha256:[0-9a-f]{64}$")
    key: str
    tempo: int
    form: list[str]
    pitch_range: dict[str, int | None] = Field(alias="pitchRange")
    maximum_polyphony: int = Field(alias="maximumPolyphony", ge=0)
    estimated_difficulty: Literal["beginner", "intermediate", "advanced"] = Field(alias="estimatedDifficulty")
    harmonic_summary: str = Field(alias="harmonicSummary")


class ComposePianoInput(ToolInputModel):
    title: str = Field(min_length=1, max_length=160)
    intent: str = Field(min_length=1, max_length=2000)
    tempo: int = Field(ge=30, le=240)
    meter: Meter
    key: KeySignature
    measure_count: int = Field(ge=1, le=MAX_MEASURES)
    score_draft: ScoreDocument


class ScoreTargetInput(ToolInputModel):
    score_id: str = Field(min_length=1, max_length=128)


class PhraseRevisionInput(ScoreTargetInput):
    measure_start: int = Field(ge=1, le=MAX_MEASURES)
    measure_end: int = Field(ge=1, le=MAX_MEASURES)
    replacement: tuple[ScoreNote, ...] = Field(max_length=MAX_NOTES)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_range(self) -> "PhraseRevisionInput":
        if self.measure_end < self.measure_start:
            raise ValueError("measure_end must not precede measure_start")
        if any(not self.measure_start <= note.measure <= self.measure_end for note in self.replacement):
            raise ValueError("replacement notes must stay inside the selected measure range")
        return self


class ReharmonizeInput(PhraseRevisionInput):
    target_character: str = Field(min_length=1, max_length=400)


class SimplifyInput(ScoreTargetInput):
    measure_start: int | None = Field(default=None, ge=1, le=MAX_MEASURES)
    measure_end: int | None = Field(default=None, ge=1, le=MAX_MEASURES)
    hand: Literal["left", "right", "both"] = "left"


class TransposeInput(ScoreTargetInput):
    semitones: int = Field(ge=-24, le=24)


class AnalyzeScoreInput(ScoreTargetInput):
    pass


class ScoreRevisionOutput(ToolOutputModel):
    score_id: str
    revision: int
    parent_revision: int | None = None
    content_hash: str
    title: str
    measure_count: int
    changed_measure_start: int | None = None
    changed_measure_end: int | None = None


class ScoreAnalysisOutput(ToolOutputModel):
    score_id: str
    revision: int
    key: str
    tempo: int
    form: list[str]
    lowest_pitch: int | None = None
    highest_pitch: int | None = None
    maximum_polyphony: int
    estimated_difficulty: Literal["beginner", "intermediate", "advanced"]
    harmonic_summary: str


class EmptyInput(Contract):
    pass


class ScoreIdInput(Contract):
    score_id: str = Field(min_length=1, max_length=128)


class ScoreGetInput(ScoreIdInput):
    revision: int | None = Field(default=None, ge=1)


class ScoreListOutput(Contract):
    scores: list[ScoreSummary]


class ScoreGetOutput(Contract):
    score: ScoreSummary
    revision: ScoreRevision


class CreateBlankInput(Contract):
    title: str = Field(default="Untitled Score", min_length=1, max_length=160)
    tempo: int = Field(default=76, ge=30, le=240)
    meter: Meter = Field(default_factory=Meter)
    key: KeySignature = Field(default_factory=KeySignature)
    measure_count: int = Field(default=16, ge=1, le=MAX_MEASURES)


class RenameScoreInput(ScoreIdInput):
    title: str = Field(min_length=1, max_length=160)


class DuplicateScoreInput(ScoreIdInput):
    title: str | None = Field(default=None, min_length=1, max_length=160)


class UpdateMetadataInput(ScoreIdInput):
    tempo: int | None = Field(default=None, ge=30, le=240)
    key: KeySignature | None = None


class DeleteScoreOutput(Contract):
    deleted: bool


class AudioSource(Contract):
    id: str
    project_id: str
    name: str
    file_ref: str
    media_type: str
    byte_count: int = Field(ge=1)
    duration_seconds: float = Field(gt=0, le=3600)
    sample_rate: int = Field(ge=8000, le=384000)
    channels: int = Field(ge=1, le=8)
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    analysis_revision: int = Field(default=0, ge=0)
    created_at: str
    updated_at: str


class TranscriptionNote(Contract):
    start_seconds: float = Field(ge=0, le=3600)
    end_seconds: float = Field(gt=0, le=3600)
    pitch: int = Field(ge=PIANO_LOW, le=PIANO_HIGH)
    velocity: float = Field(default=0.72, ge=0.01, le=1)
    confidence: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode="after")
    def validate_time(self) -> "TranscriptionNote":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("transcription note end must follow start")
        return self


class UncertainAudioRange(Contract):
    start_seconds: float = Field(ge=0, le=3600)
    end_seconds: float = Field(gt=0, le=3600)
    confidence: float = Field(ge=0, le=1)
    reason: Literal["low_note_confidence", "dense_polyphony", "tempo_ambiguity", "background_noise"]


class AudioTranscription(Contract):
    audio_source_id: str
    revision: int = Field(ge=1)
    provider_id: str
    provider_version: str
    tempo: int = Field(ge=30, le=240)
    meter: Meter
    key: KeySignature
    confidence: float = Field(ge=0, le=1)
    notes: tuple[TranscriptionNote, ...] = Field(max_length=MAX_NOTES)
    uncertain_ranges: tuple[UncertainAudioRange, ...] = ()
    created_at: str


class AudioAnalysisArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    source_audio_id: str = Field(alias="sourceAudioId")
    analysis_revision: int = Field(alias="analysisRevision", ge=1)
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    duration_seconds: float = Field(alias="durationSeconds", gt=0)
    tempo: int
    key: str
    confidence: float = Field(ge=0, le=1)
    note_count: int = Field(alias="noteCount", ge=0)
    uncertain_ranges: list[UncertainAudioRange] = Field(alias="uncertainRanges")


class TranscriptionArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    source_audio_id: str = Field(alias="sourceAudioId")
    analysis_revision: int = Field(alias="analysisRevision", ge=1)
    score_id: str = Field(alias="scoreId")
    revision: int = Field(ge=1)
    tempo: int
    key: str
    confidence: float = Field(ge=0, le=1)
    uncertain_ranges: list[UncertainAudioRange] = Field(alias="uncertainRanges")


class ImportAudioInput(Contract):
    source_path: str = Field(min_length=1, max_length=4096)
    name: str = Field(min_length=1, max_length=240)
    media_type: str = Field(min_length=1, max_length=120)
    duration_seconds: float = Field(gt=0, le=3600)
    sample_rate: int = Field(ge=8000, le=384000)
    channels: int = Field(ge=1, le=8)


class AudioIdInput(Contract):
    audio_source_id: str = Field(min_length=1, max_length=128)


class AnalyzeAudioInput(ToolInputModel):
    audio_source_id: str = Field(min_length=1, max_length=128)


class AudioAnalysisOutput(ToolOutputModel):
    audio_source_id: str
    analysis_revision: int = Field(ge=1)
    duration_seconds: float = Field(gt=0, le=3600)
    tempo: int = Field(ge=30, le=240)
    key: str
    confidence: float = Field(ge=0, le=1)
    note_count: int = Field(ge=0)
    uncertain_range_count: int = Field(ge=0)


class AudioGetOutput(Contract):
    source: AudioSource
    transcription: AudioTranscription | None = None


class AudioListOutput(Contract):
    sources: list[AudioSource]


class CommitTranscriptionInput(AudioIdInput):
    provider_id: Literal["spotify.basic-pitch"]
    provider_version: str = Field(min_length=1, max_length=40)
    tempo: int = Field(ge=30, le=240)
    meter: Meter = Field(default_factory=Meter)
    key: KeySignature
    confidence: float = Field(ge=0, le=1)
    notes: tuple[TranscriptionNote, ...] = Field(max_length=MAX_NOTES)
    uncertain_ranges: tuple[UncertainAudioRange, ...] = ()


class TranscribePianoInput(ToolInputModel):
    audio_source_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=160)
    quantization: Literal["1/4", "1/8", "1/16"] = "1/16"


class TranscriptionOutput(ToolOutputModel):
    audio_source_id: str
    analysis_revision: int
    score_id: str
    score_revision: int
    confidence: float
    uncertain_range_count: int


class AlignScoreInput(ToolInputModel):
    audio_source_id: str = Field(min_length=1, max_length=128)
    score_id: str = Field(min_length=1, max_length=128)


class AlignmentOutput(ToolOutputModel):
    audio_source_id: str
    score_id: str
    score_revision: int
    aligned_measure_count: int
    confidence: float


class AlignmentArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    source_audio_id: str = Field(alias="sourceAudioId")
    analysis_revision: int = Field(alias="analysisRevision", ge=1)
    score_id: str = Field(alias="scoreId")
    score_revision: int = Field(alias="scoreRevision", ge=1)
    tempo: int
    aligned_measure_count: int = Field(alias="alignedMeasureCount", ge=1)
    confidence: float = Field(ge=0, le=1)
    measure_starts_seconds: list[float] = Field(alias="measureStartsSeconds")
