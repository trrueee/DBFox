from __future__ import annotations

import json
from typing import Callable

from dbfox_dlc_api import (
    ArtifactDraft,
    BackendExtensionHost,
    CapabilityGuidanceSpec,
    BaseTool,
    ContextContributionInput,
    ContextFragment,
    DlcOperationContext,
    DlcOperationError,
    DlcOperationSpec,
    ExtensionToolRunContext,
    ResourceScopeRef,
    SemanticArtifactCompletionSupport,
    ToolExecutionSpec,
    ToolResourceRequirement,
    ToolInputError,
    ToolObservationProjection,
    ToolOutcome,
    ToolReconciliation,
    ToolPolicy,
    ToolPresentation,
    ToolSemanticSpec,
    ToolKey,
)

from .contracts import (
    AnalyzeScoreInput,
    AnalyzeAudioInput,
    AlignmentArtifactPayload,
    AlignmentOutput,
    AlignScoreInput,
    AudioAnalysisOutput,
    AudioAnalysisArtifactPayload,
    AudioGetOutput,
    AudioIdInput,
    AudioListOutput,
    AudioSource,
    AudioTranscription,
    CommitTranscriptionInput,
    ComposePianoInput,
    CreateBlankInput,
    DeleteScoreOutput,
    DuplicateScoreInput,
    EmptyInput,
    ImportAudioInput,
    MusicLibrary,
    PhraseRevisionInput,
    ReharmonizeInput,
    RenameScoreInput,
    ScoreAnalysisArtifactPayload,
    ScoreAnalysisOutput,
    ScoreDocument,
    ScoreGetInput,
    ScoreGetOutput,
    ScoreIdInput,
    ScoreListOutput,
    ScoreRevision,
    ScoreRevisionArtifactPayload,
    ScoreRevisionOutput,
    SimplifyInput,
    TransposeInput,
    TranscribePianoInput,
    TranscriptionArtifactPayload,
    TranscriptionOutput,
    UpdateMetadataInput,
)
from .score_ops import (
    analyze,
    expand_piano_composition,
    replace_phrase,
    score_from_transcription,
    simplify,
    transpose,
)
from .store import AUDIO_KIND, LIBRARY_KIND, SCORE_KIND, MusicStore


SCORE_REVISION_ARTIFACT = "dbfox.music.score_revision"
SCORE_ANALYSIS_ARTIFACT = "dbfox.music.analysis"
AUDIO_ANALYSIS_ARTIFACT = "dbfox.music.audio_analysis"
TRANSCRIPTION_ARTIFACT = "dbfox.music.transcription"
ALIGNMENT_ARTIFACT = "dbfox.music.alignment"
MAX_CONTEXT_CHARS = 14_000


def _library(context: ExtensionToolRunContext) -> MusicLibrary:
    resource = context.require_one(LIBRARY_KIND)
    if not isinstance(resource, MusicLibrary):
        raise RuntimeError("music library did not resolve to MusicLibrary")
    return resource


def _score(input_score_id: str, context: ExtensionToolRunContext) -> ScoreRevision:
    resource = context.require_one(SCORE_KIND)
    if not isinstance(resource, ScoreRevision):
        raise RuntimeError("music score did not resolve to ScoreRevision")
    if resource.score_id != input_score_id:
        raise ToolInputError("The requested score is not the authorized score.")
    return resource


def _scope(context: ExtensionToolRunContext, kind: str) -> ResourceScopeRef:
    scopes = context.scopes(kind)
    if len(scopes) != 1:
        raise RuntimeError(f"Music tool requires exactly one {kind} scope")
    return scopes[0]


def _audio(input_audio_id: str, context: ExtensionToolRunContext) -> tuple[AudioSource, AudioTranscription | None]:
    resource = context.require_one(AUDIO_KIND)
    if (
        not isinstance(resource, tuple)
        or len(resource) != 2
        or not isinstance(resource[0], AudioSource)
        or (resource[1] is not None and not isinstance(resource[1], AudioTranscription))
    ):
        raise RuntimeError("music audio did not resolve to an audio source snapshot")
    if resource[0].id != input_audio_id:
        raise ToolInputError("The requested audio source is not authorized.")
    return resource


def _revision_output(
    revision: ScoreRevision,
    *,
    changed: tuple[int, int] | None = None,
) -> ScoreRevisionOutput:
    return ScoreRevisionOutput(
        score_id=revision.score_id,
        revision=revision.revision,
        parent_revision=revision.parent_revision,
        content_hash=revision.content_hash,
        title=revision.document.title,
        measure_count=revision.document.measure_count,
        changed_measure_start=changed[0] if changed else None,
        changed_measure_end=changed[1] if changed else None,
    )


def _revision_artifact(revision: ScoreRevision, scope: ResourceScopeRef) -> ArtifactDraft:
    document = revision.document
    return ArtifactDraft(
        key="score_revision",
        type=SCORE_REVISION_ARTIFACT,
        schema_version=1,
        title=document.title,
        payload={
            "scoreId": revision.score_id,
            "projectId": revision.project_id,
            "revision": revision.revision,
            "parentRevision": revision.parent_revision,
            "contentHash": revision.content_hash,
            "title": document.title,
            "tempo": document.tempo,
            "key": f"{document.key.tonic} {document.key.mode}",
            "meter": f"{document.meter.beats}/{document.meter.beat_unit}",
            "measureCount": document.measure_count,
        },
        summary=(
            f"{document.measure_count} measures · {document.key.tonic} "
            f"{document.key.mode} · quarter note = {document.tempo} · revision {revision.revision}"
        ),
        semantic_key=f"music_score:{revision.score_id}",
        resource_refs=(scope,),
        select_if_none=True,
    )


class ComposePianoTool(BaseTool[ComposePianoInput, ScoreRevisionOutput]):
    name = "music_compose_piano"
    group = "music"
    description = "Expand a compact per-measure piano composition plan and commit it as a new immutable score revision."
    input_model = ComposePianoInput
    output_model = ScoreRevisionOutput
    version = "2"
    policy = ToolPolicy(risk_level="warning", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="reconcile",
        retryable=False,
        concurrency="sequential",
        required_resources=(ToolResourceRequirement(kind=LIBRARY_KIND),),
    )
    semantics = ToolSemanticSpec(produces=(SCORE_REVISION_ARTIFACT,))
    presentation = ToolPresentation(title="创作钢琴谱", category="manage")

    def __init__(self, store: MusicStore) -> None:
        self._store = store

    def run(self, input: ComposePianoInput, context: ExtensionToolRunContext) -> ToolOutcome[ScoreRevisionOutput]:
        draft = expand_piano_composition(input)
        if not draft.notes:
            raise ToolInputError("A composed score must contain at least one note.")
        library = _library(context)
        revision = self._store.create_score(
            library.project_id,
            draft,
            f"Composed: {input.intent[:240]}",
            creation_invocation_id=context.invocation_id,
        )
        scope = _scope(context, LIBRARY_KIND)
        return ToolOutcome(output=_revision_output(revision), artifacts=(_revision_artifact(revision, scope),))

    def reconcile(
        self,
        input: ComposePianoInput,
        context: ExtensionToolRunContext,
    ) -> ToolReconciliation:
        library = _library(context)
        revision = self._store.get_score_by_creation_invocation(
            library.project_id,
            context.invocation_id,
        )
        if revision is None:
            return ToolReconciliation(status="not_applied")
        scope = _scope(context, LIBRARY_KIND)
        return ToolReconciliation(
            status="succeeded",
            output=_revision_output(revision).model_dump(mode="json"),
            artifacts=(_revision_artifact(revision, scope),),
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="钢琴谱创作未完成。")
        return ToolObservationProjection(
            summary=f"已创建 {output.get('measure_count', 0)} 小节钢琴谱，Revision {output.get('revision', 0)}。",
            facts={"score_id": output.get("score_id"), "revision": output.get("revision"), "measure_count": output.get("measure_count")},
            provider_payload=output,
        )


class _ScoreWriteTool:
    policy = ToolPolicy(risk_level="warning", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="never_retry",
        retryable=False,
        concurrency="sequential",
        required_resources=(ToolResourceRequirement(kind=SCORE_KIND, selector_field="score_id"),),
    )
    semantics = ToolSemanticSpec(produces=(SCORE_REVISION_ARTIFACT,))

    def __init__(self, store: MusicStore) -> None:
        self._store = store

    def _commit(
        self,
        source: ScoreRevision,
        document: ScoreDocument,
        summary: str,
        context: ExtensionToolRunContext,
        changed: tuple[int, int] | None = None,
    ) -> ToolOutcome[ScoreRevisionOutput]:
        try:
            revision = self._store.commit_revision(
                source.project_id,
                source.score_id,
                source.revision,
                document,
                summary,
            )
        except (KeyError, ValueError) as exc:
            raise ToolInputError("The score could not be revised from the frozen authorized revision.") from exc
        scope = _scope(context, SCORE_KIND)
        return ToolOutcome(
            output=_revision_output(revision, changed=changed),
            artifacts=(_revision_artifact(revision, scope),),
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="乐谱修订未完成。")
        return ToolObservationProjection(
            summary=f"已创建乐谱 Revision {output.get('revision', 0)}。",
            facts={
                "score_id": output.get("score_id"),
                "revision": output.get("revision"),
                "changed_measure_start": output.get("changed_measure_start"),
                "changed_measure_end": output.get("changed_measure_end"),
            },
            provider_payload=output,
        )


class RevisePhraseTool(_ScoreWriteTool, BaseTool[PhraseRevisionInput, ScoreRevisionOutput]):
    name = "music_revise_phrase"
    group = "music"
    description = "Replace notes only inside one measure range of the authorized frozen score revision."
    input_model = PhraseRevisionInput
    output_model = ScoreRevisionOutput
    version = "1"
    presentation = ToolPresentation(title="修订乐句", category="manage")

    def run(self, input: PhraseRevisionInput, context: ExtensionToolRunContext) -> ToolOutcome[ScoreRevisionOutput]:
        source = _score(input.score_id, context)
        try:
            document = replace_phrase(source.document, input.measure_start, input.measure_end, input.replacement)
        except ValueError as exc:
            raise ToolInputError("The phrase replacement is not a valid score document.") from exc
        return self._commit(source, document, input.reason, context, (input.measure_start, input.measure_end))


class ReharmonizeTool(_ScoreWriteTool, BaseTool[ReharmonizeInput, ScoreRevisionOutput]):
    name = "music_reharmonize"
    group = "music"
    description = "Commit a model-proposed reharmonization inside one bounded measure range only."
    input_model = ReharmonizeInput
    output_model = ScoreRevisionOutput
    version = "1"
    presentation = ToolPresentation(title="重新配和声", category="manage")

    def run(self, input: ReharmonizeInput, context: ExtensionToolRunContext) -> ToolOutcome[ScoreRevisionOutput]:
        source = _score(input.score_id, context)
        try:
            document = replace_phrase(source.document, input.measure_start, input.measure_end, input.replacement)
        except ValueError as exc:
            raise ToolInputError("The reharmonization is not a valid local score replacement.") from exc
        summary = f"Reharmonized measures {input.measure_start}-{input.measure_end}: {input.target_character}. {input.reason}"
        return self._commit(source, document, summary, context, (input.measure_start, input.measure_end))


class SimplifyTool(_ScoreWriteTool, BaseTool[SimplifyInput, ScoreRevisionOutput]):
    name = "music_simplify"
    group = "music"
    description = "Deterministically reduce chord density in a selected hand and measure range."
    input_model = SimplifyInput
    output_model = ScoreRevisionOutput
    version = "1"
    presentation = ToolPresentation(title="简化演奏难度", category="manage")

    def run(self, input: SimplifyInput, context: ExtensionToolRunContext) -> ToolOutcome[ScoreRevisionOutput]:
        source = _score(input.score_id, context)
        start = input.measure_start or 1
        end = input.measure_end or source.document.measure_count
        if end < start:
            raise ToolInputError("The simplify measure range is invalid.")
        try:
            document = simplify(source.document, start=start, end=end, hand=input.hand)
        except ValueError as exc:
            raise ToolInputError("The score cannot be simplified within the requested range.") from exc
        return self._commit(source, document, f"Simplified {input.hand} hand in measures {start}-{end}", context, (start, end))


class TransposeTool(_ScoreWriteTool, BaseTool[TransposeInput, ScoreRevisionOutput]):
    name = "music_transpose"
    group = "music"
    description = "Deterministically transpose every note and the declared key by a semitone interval."
    input_model = TransposeInput
    output_model = ScoreRevisionOutput
    version = "1"
    presentation = ToolPresentation(title="移调", category="manage")

    def run(self, input: TransposeInput, context: ExtensionToolRunContext) -> ToolOutcome[ScoreRevisionOutput]:
        source = _score(input.score_id, context)
        if input.semitones == 0:
            raise ToolInputError("Transpose semitones must change the score.")
        try:
            document = transpose(source.document, input.semitones)
        except ValueError as exc:
            raise ToolInputError("The requested transposition exceeds the piano range.") from exc
        return self._commit(
            source,
            document,
            f"Transposed by {input.semitones:+d} semitones",
            context,
            (1, source.document.measure_count),
        )


class AnalyzeScoreTool(BaseTool[AnalyzeScoreInput, ScoreAnalysisOutput]):
    name = "music_analyze_score"
    group = "music"
    description = "Deterministically summarize form, range, polyphony, and estimated piano difficulty."
    input_model = AnalyzeScoreInput
    output_model = ScoreAnalysisOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        required_resources=(ToolResourceRequirement(kind=SCORE_KIND, selector_field="score_id"),),
    )
    semantics = ToolSemanticSpec(produces=(SCORE_ANALYSIS_ARTIFACT,))
    presentation = ToolPresentation(title="分析乐谱", category="explore")

    def run(self, input: AnalyzeScoreInput, context: ExtensionToolRunContext) -> ToolOutcome[ScoreAnalysisOutput]:
        source = _score(input.score_id, context)
        output = analyze(source.score_id, source.revision, source.document)
        artifact = ArtifactDraft(
            key="analysis",
            type=SCORE_ANALYSIS_ARTIFACT,
            schema_version=1,
            title=f"{source.document.title} · Analysis",
            payload={
                "scoreId": source.score_id,
                "revision": source.revision,
                "contentHash": source.content_hash,
                "key": output.key,
                "tempo": output.tempo,
                "form": output.form,
                "pitchRange": {"lowest": output.lowest_pitch, "highest": output.highest_pitch},
                "maximumPolyphony": output.maximum_polyphony,
                "estimatedDifficulty": output.estimated_difficulty,
                "harmonicSummary": output.harmonic_summary,
            },
            summary=output.harmonic_summary,
            semantic_key=f"music_analysis:{source.score_id}:{source.revision}",
            resource_refs=(_scope(context, SCORE_KIND),),
        )
        return ToolOutcome(output=output, artifacts=(artifact,))

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="乐谱分析未完成。")
        return ToolObservationProjection(
            summary=f"已分析乐谱：{output.get('key', '')}，难度 {output.get('estimated_difficulty', '')}。",
            facts={key: output.get(key) for key in ("score_id", "revision", "key", "tempo", "maximum_polyphony", "estimated_difficulty")},
            provider_payload=output,
        )


class AnalyzeAudioTool(BaseTool[AnalyzeAudioInput, AudioAnalysisOutput]):
    name = "music_analyze_audio"
    group = "music"
    description = "Inspect immutable tempo, key, note-confidence, and uncertainty facts produced by the audio transcription model."
    input_model = AnalyzeAudioInput
    output_model = AudioAnalysisOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        required_resources=(ToolResourceRequirement(kind=AUDIO_KIND, selector_field="audio_source_id"),),
    )
    semantics = ToolSemanticSpec(produces=(AUDIO_ANALYSIS_ARTIFACT,))
    presentation = ToolPresentation(title="分析钢琴录音", category="explore")

    def run(self, input: AnalyzeAudioInput, context: ExtensionToolRunContext) -> ToolOutcome[AudioAnalysisOutput]:
        source, transcription = _audio(input.audio_source_id, context)
        if transcription is None:
            raise ToolInputError("This audio source has not completed model transcription yet.")
        output = AudioAnalysisOutput(
            audio_source_id=source.id,
            analysis_revision=transcription.revision,
            duration_seconds=source.duration_seconds,
            key=f"{transcription.key.tonic} {transcription.key.mode}",
            tempo=transcription.tempo,
            confidence=transcription.confidence,
            note_count=len(transcription.notes),
            uncertain_range_count=len(transcription.uncertain_ranges),
        )
        summary = (
            f"Basic Pitch detected {output.note_count} piano note candidates; "
            f"overall confidence {output.confidence:.0%}."
        )
        artifact = ArtifactDraft(
            key="audio_analysis",
            type=AUDIO_ANALYSIS_ARTIFACT,
            schema_version=1,
            title=f"{source.name} · Audio Analysis",
            payload={
                "sourceAudioId": source.id,
                "analysisRevision": transcription.revision,
                "fingerprint": source.fingerprint,
                "durationSeconds": source.duration_seconds,
                "tempo": transcription.tempo,
                "key": f"{transcription.key.tonic} {transcription.key.mode}",
                "confidence": transcription.confidence,
                "noteCount": len(transcription.notes),
                "uncertainRanges": [item.model_dump(mode="json") for item in transcription.uncertain_ranges],
            },
            summary=summary,
            semantic_key=f"music_audio_analysis:{source.id}:{transcription.revision}",
            resource_refs=(_scope(context, AUDIO_KIND),),
        )
        return ToolOutcome(output=output, artifacts=(artifact,))

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="录音分析未完成。")
        return ToolObservationProjection(
            summary=(
                f"已分析 {output.get('note_count', 0)} 个音符候选，"
                f"置信度 {float(output.get('confidence', 0)):.0%}。"
            ),
            facts={key: output.get(key) for key in (
                "audio_source_id", "analysis_revision", "tempo", "key",
                "confidence", "note_count", "uncertain_range_count",
            )},
            provider_payload=output,
        )


class TranscribePianoTool(BaseTool[TranscribePianoInput, TranscriptionOutput]):
    name = "music_transcribe_piano"
    group = "music"
    description = "Normalize an immutable Basic Pitch note transcription into a validated, playable piano Score revision."
    input_model = TranscribePianoInput
    output_model = TranscriptionOutput
    version = "1"
    policy = ToolPolicy(risk_level="warning", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="never_retry",
        retryable=False,
        concurrency="sequential",
        required_resources=(ToolResourceRequirement(kind=AUDIO_KIND, selector_field="audio_source_id"),),
    )
    semantics = ToolSemanticSpec(produces=(SCORE_REVISION_ARTIFACT, TRANSCRIPTION_ARTIFACT))
    presentation = ToolPresentation(title="把钢琴录音转成乐谱", category="manage")

    def __init__(self, store: MusicStore) -> None:
        self._store = store

    def run(self, input: TranscribePianoInput, context: ExtensionToolRunContext) -> ToolOutcome[TranscriptionOutput]:
        source, transcription = _audio(input.audio_source_id, context)
        if transcription is None:
            raise ToolInputError("Run transcription in Piano Studio before creating a score.")
        try:
            document = score_from_transcription(transcription, title=input.title, quantization=input.quantization)
            revision = self._store.create_score(
                source.project_id,
                document,
                f"Transcribed from {source.id} analysis revision {transcription.revision}",
            )
        except ValueError as exc:
            raise ToolInputError("The model transcription could not form a valid piano score.") from exc
        scope = _scope(context, AUDIO_KIND)
        score_artifact = _revision_artifact(revision, scope)
        transcription_artifact = ArtifactDraft(
            key="transcription",
            type=TRANSCRIPTION_ARTIFACT,
            schema_version=1,
            title=f"{source.name} · Transcription",
            payload={
                "sourceAudioId": source.id,
                "analysisRevision": transcription.revision,
                "scoreId": revision.score_id,
                "revision": revision.revision,
                "tempo": transcription.tempo,
                "key": f"{transcription.key.tonic} {transcription.key.mode}",
                "confidence": transcription.confidence,
                "uncertainRanges": [item.model_dump(mode="json") for item in transcription.uncertain_ranges],
            },
            summary=f"Transcribed {len(transcription.notes)} note candidates with {transcription.confidence:.0%} confidence.",
            semantic_key=f"music_transcription:{source.id}:{transcription.revision}",
            resource_refs=(scope,),
        )
        return ToolOutcome(
            output=TranscriptionOutput(
                audio_source_id=source.id,
                analysis_revision=transcription.revision,
                score_id=revision.score_id,
                score_revision=revision.revision,
                confidence=transcription.confidence,
                uncertain_range_count=len(transcription.uncertain_ranges),
            ),
            artifacts=(score_artifact, transcription_artifact),
        )


class AlignScoreToAudioTool(BaseTool[AlignScoreInput, AlignmentOutput]):
    name = "music_align_score_to_audio"
    group = "music"
    description = "Create a deterministic measure timeline between an authorized score revision and audio transcription."
    input_model = AlignScoreInput
    output_model = AlignmentOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe", requires_approval=False)
    execution = ToolExecutionSpec(
        recovery="retry_safe",
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        required_resources=(
            ToolResourceRequirement(kind=AUDIO_KIND, selector_field="audio_source_id"),
            ToolResourceRequirement(kind=SCORE_KIND, selector_field="score_id"),
        ),
    )
    semantics = ToolSemanticSpec(produces=(ALIGNMENT_ARTIFACT,))
    presentation = ToolPresentation(title="对齐录音与乐谱", category="visualize")

    def run(self, input: AlignScoreInput, context: ExtensionToolRunContext) -> ToolOutcome[AlignmentOutput]:
        source, transcription = _audio(input.audio_source_id, context)
        score = _score(input.score_id, context)
        if transcription is None:
            raise ToolInputError("This audio source has no transcription timeline.")
        seconds_per_measure = score.document.meter.beats * 60 / transcription.tempo
        starts = [round(index * seconds_per_measure, 4) for index in range(score.document.measure_count)]
        confidence = min(transcription.confidence, 1.0 if score.document.tempo == transcription.tempo else 0.8)
        output = AlignmentOutput(
            audio_source_id=source.id,
            score_id=score.score_id,
            score_revision=score.revision,
            aligned_measure_count=score.document.measure_count,
            confidence=confidence,
        )
        artifact = ArtifactDraft(
            key="alignment",
            type=ALIGNMENT_ARTIFACT,
            schema_version=1,
            title=f"{score.document.title} · Audio Alignment",
            payload={
                "sourceAudioId": source.id,
                "analysisRevision": transcription.revision,
                "scoreId": score.score_id,
                "scoreRevision": score.revision,
                "tempo": transcription.tempo,
                "alignedMeasureCount": score.document.measure_count,
                "confidence": confidence,
                "measureStartsSeconds": starts,
            },
            summary=f"Aligned {score.document.measure_count} measures at {confidence:.0%} confidence.",
            resource_refs=(_scope(context, AUDIO_KIND), _scope(context, SCORE_KIND)),
        )
        return ToolOutcome(output=output, artifacts=(artifact,))


class MusicContextContributor:
    id = "dbfox.music"

    def __init__(self, store: MusicStore) -> None:
        self._store = store

    def build(self, input: ContextContributionInput) -> tuple[ContextFragment, ...]:
        fragments: list[ContextFragment] = []
        for ref in input.resource_refs:
            if ref.kind == LIBRARY_KIND:
                fragments.append(ContextFragment(
                    source_id=self.id,
                    source_version=str(ref.version or "1"),
                    lane="resource",
                    content="Authorized music library: the Agent may create one new piano Score in this Project.",
                    provenance={"resource_kind": LIBRARY_KIND, "project_id": str(ref.id)},
                ))
            elif ref.kind == SCORE_KIND:
                try:
                    revision = self._store.resolve_score(ref)
                except (KeyError, ValueError):
                    continue
                encoded = json.dumps(revision.document.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
                truncated = len(encoded) > MAX_CONTEXT_CHARS
                fragments.append(ContextFragment(
                    source_id=self.id,
                    source_version=f"{revision.score_id}:{revision.revision}",
                    lane="resource",
                    content=(
                        f"Authorized immutable piano score revision {revision.revision} "
                        f"(content hash {revision.content_hash}).\nScoreDocument JSON:\n{encoded[:MAX_CONTEXT_CHARS]}"
                    ),
                    provenance={
                        "score_id": revision.score_id,
                        "revision": revision.revision,
                        "content_hash": revision.content_hash,
                        "truncated": truncated,
                    },
                ))
            elif ref.kind == AUDIO_KIND:
                try:
                    source, transcription = self._store.resolve_audio(ref)
                except (KeyError, ValueError):
                    continue
                detail = "model transcription pending"
                if transcription is not None:
                    detail = (
                        f"Basic Pitch analysis revision {transcription.revision}: "
                        f"tempo {transcription.tempo}, key {transcription.key.tonic} "
                        f"{transcription.key.mode}, {len(transcription.notes)} note candidates, "
                        f"confidence {transcription.confidence:.3f}."
                    )
                fragments.append(ContextFragment(
                    source_id=self.id,
                    source_version=f"{source.id}:{source.analysis_revision}",
                    lane="resource",
                    content=f"Authorized piano audio source {source.name}. {detail}",
                    provenance={
                        "audio_source_id": source.id,
                        "fingerprint": source.fingerprint,
                        "analysis_revision": source.analysis_revision,
                    },
                ))
        return tuple(fragments[:8])


def _project_id(context: DlcOperationContext) -> str:
    if not context.project_id:
        raise ValueError("Music operation requires a project_id")
    return context.project_id


def _operation_error(exc: Exception, *, status: int = 400) -> DlcOperationError:
    code = "MUSIC_NOT_FOUND" if isinstance(exc, KeyError) else "MUSIC_INVALID"
    return DlcOperationError(code=code, message="The requested music resource could not be processed.", status_code=404 if isinstance(exc, KeyError) else status)


def _register_operations(host: BackendExtensionHost, store: MusicStore) -> None:
    def list_scores(_input: EmptyInput, context: DlcOperationContext) -> ScoreListOutput:
        return ScoreListOutput(scores=store.list_scores(_project_id(context)))

    def get_score(input: ScoreGetInput, context: DlcOperationContext) -> ScoreGetOutput:
        project_id = _project_id(context)
        try:
            return ScoreGetOutput(score=store.get_score(project_id, input.score_id), revision=store.get_revision(project_id, input.score_id, input.revision))
        except (KeyError, ValueError) as exc:
            raise _operation_error(exc) from exc

    def create_blank(input: CreateBlankInput, context: DlcOperationContext) -> ScoreGetOutput:
        document = ScoreDocument(title=input.title, tempo=input.tempo, meter=input.meter, key=input.key, measure_count=input.measure_count)
        revision = store.create_score(_project_id(context), document, "Created blank score")
        return ScoreGetOutput(score=store.get_score(revision.project_id, revision.score_id), revision=revision)

    def rename(input: RenameScoreInput, context: DlcOperationContext) -> ScoreGetOutput:
        project_id = _project_id(context)
        try:
            current = store.get_revision(project_id, input.score_id)
            document = ScoreDocument.model_validate({**current.document.model_dump(mode="json"), "title": input.title})
            revision = store.commit_revision(project_id, input.score_id, current.revision, document, "Renamed score")
            return ScoreGetOutput(score=store.get_score(project_id, input.score_id), revision=revision)
        except (KeyError, ValueError) as exc:
            raise _operation_error(exc, status=409) from exc

    def duplicate(input: DuplicateScoreInput, context: DlcOperationContext) -> ScoreGetOutput:
        project_id = _project_id(context)
        try:
            source = store.get_revision(project_id, input.score_id)
            title = input.title or f"{source.document.title} Copy"
            document = ScoreDocument.model_validate({**source.document.model_dump(mode="json"), "title": title})
            revision = store.create_score(project_id, document, f"Duplicated from {source.score_id} revision {source.revision}")
            return ScoreGetOutput(score=store.get_score(project_id, revision.score_id), revision=revision)
        except (KeyError, ValueError) as exc:
            raise _operation_error(exc) from exc

    def delete(input: ScoreIdInput, context: DlcOperationContext) -> DeleteScoreOutput:
        return DeleteScoreOutput(deleted=store.delete_score(_project_id(context), input.score_id))

    def update_metadata(input: UpdateMetadataInput, context: DlcOperationContext) -> ScoreGetOutput:
        project_id = _project_id(context)
        try:
            current = store.get_revision(project_id, input.score_id)
            values = current.document.model_dump(mode="json")
            if input.tempo is not None:
                values["tempo"] = input.tempo
            if input.key is not None:
                values["key"] = input.key.model_dump(mode="json")
            document = ScoreDocument.model_validate(values)
            revision = store.commit_revision(project_id, input.score_id, current.revision, document, "Updated score metadata")
            return ScoreGetOutput(score=store.get_score(project_id, input.score_id), revision=revision)
        except (KeyError, ValueError) as exc:
            raise _operation_error(exc, status=409) from exc

    def list_audio(_input: EmptyInput, context: DlcOperationContext) -> AudioListOutput:
        return AudioListOutput(sources=store.list_audio_sources(_project_id(context)))

    def get_audio(input: AudioIdInput, context: DlcOperationContext) -> AudioGetOutput:
        project_id = _project_id(context)
        try:
            source = store.get_audio_source(project_id, input.audio_source_id)
            return AudioGetOutput(source=source, transcription=store.get_transcription(project_id, source.id))
        except (KeyError, ValueError) as exc:
            raise _operation_error(exc) from exc

    def import_audio(input: ImportAudioInput, context: DlcOperationContext) -> AudioGetOutput:
        try:
            source = store.import_audio(_project_id(context), **input.model_dump())
            return AudioGetOutput(source=source)
        except (OSError, ValueError) as exc:
            raise _operation_error(exc) from exc

    def commit_transcription(input: CommitTranscriptionInput, context: DlcOperationContext) -> AudioGetOutput:
        project_id = _project_id(context)
        try:
            transcription = store.commit_transcription(project_id, input)
            return AudioGetOutput(
                source=store.get_audio_source(project_id, input.audio_source_id),
                transcription=transcription,
            )
        except (KeyError, ValueError) as exc:
            raise _operation_error(exc, status=409) from exc

    specs: tuple[tuple[str, type, type, Callable, tuple[str, ...]], ...] = (
        ("scores.list", EmptyInput, ScoreListOutput, list_scores, ()),
        ("scores.get", ScoreGetInput, ScoreGetOutput, get_score, ()),
        ("scores.create_blank", CreateBlankInput, ScoreGetOutput, create_blank, ()),
        ("scores.rename", RenameScoreInput, ScoreGetOutput, rename, ()),
        ("scores.duplicate", DuplicateScoreInput, ScoreGetOutput, duplicate, ()),
        ("scores.delete", ScoreIdInput, DeleteScoreOutput, delete, ()),
        ("scores.update_metadata", UpdateMetadataInput, ScoreGetOutput, update_metadata, ()),
        ("audio.list", EmptyInput, AudioListOutput, list_audio, ()),
        ("audio.get", AudioIdInput, AudioGetOutput, get_audio, ()),
        ("audio.import", ImportAudioInput, AudioGetOutput, import_audio, ("filesystem_read",)),
        ("audio.commit_transcription", CommitTranscriptionInput, AudioGetOutput, commit_transcription, ()),
    )
    for name, input_model, output_model, handler, capabilities in specs:
        host.operations.register(DlcOperationSpec(
            name=name,
            input_model=input_model,
            output_model=output_model,
            handler=handler,
            scope="project",
            capabilities=capabilities,
        ))


def register(host: BackendExtensionHost) -> None:
    store = MusicStore(host.runtime_info.data_path)
    for tool in (
        ComposePianoTool(store),
        RevisePhraseTool(store),
        ReharmonizeTool(store),
        SimplifyTool(store),
        TransposeTool(store),
        AnalyzeScoreTool(),
        AnalyzeAudioTool(),
        TranscribePianoTool(store),
        AlignScoreToAudioTool(),
    ):
        host.tools.register(tool)
    host.agent_guidance.register(CapabilityGuidanceSpec(
        id="piano_composition",
        version="1",
        instructions=(
            "When the active request asks to create a score and an authorized Music Library is available, "
            "produce a durable piano score instead of only describing what it could sound like.\n"
            "Preserve explicit musical constraints, including measure count, key, meter, tempo, formal "
            "sections, hand roles, register, playability, chord labels, and stylistic direction.\n"
            "Translate form boundaries exactly. Keep the piano writing playable for the requested difficulty, "
            "and use the requested roles for right and left hand rather than mechanically duplicating material.\n"
            "For an existing authorized score, prefer a focused revision over replacing unrelated measures.\n"
            "Do not claim that a score was created or revised until a successful score-revision observation returns."
        ),
        applies_to_resource_kinds=(LIBRARY_KIND, SCORE_KIND, AUDIO_KIND),
        applies_to_artifact_types=(SCORE_REVISION_ARTIFACT, TRANSCRIPTION_ARTIFACT),
        tool_refs=tuple(
            ToolKey(owner_id="dbfox.music", local_name=name)
            for name in (
                "music_compose_piano",
                "music_revise_phrase",
                "music_reharmonize",
                "music_simplify",
                "music_transpose",
            )
        ),
    ))
    host.resources.register_provider(store.list_resources)
    host.resources.register_resolver(LIBRARY_KIND, store.resolve_library)
    host.resources.register_resolver(SCORE_KIND, store.resolve_score)
    host.resources.register_resolver(AUDIO_KIND, store.resolve_audio)
    host.context.register(MusicContextContributor(store))
    host.artifacts.register(SCORE_REVISION_ARTIFACT, 1, ScoreRevisionArtifactPayload)
    host.artifacts.register(SCORE_ANALYSIS_ARTIFACT, 1, ScoreAnalysisArtifactPayload)
    host.artifacts.register(AUDIO_ANALYSIS_ARTIFACT, 1, AudioAnalysisArtifactPayload)
    host.artifacts.register(TRANSCRIPTION_ARTIFACT, 1, TranscriptionArtifactPayload)
    host.artifacts.register(ALIGNMENT_ARTIFACT, 1, AlignmentArtifactPayload)
    host.completion.register_support(SemanticArtifactCompletionSupport(
        id="dbfox.music.score_revision",
        semantic_capability=SCORE_REVISION_ARTIFACT,
    ))
    _register_operations(host, store)
