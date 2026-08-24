from __future__ import annotations

import hashlib
import json
import sqlite3
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dbfox_dlc_api import ProjectResourceDescriptor, ResourceScopeRef

from .contracts import (
    AudioSource,
    AudioTranscription,
    CommitTranscriptionInput,
    MusicLibrary,
    ScoreDocument,
    ScoreRevision,
    ScoreSummary,
)


LIBRARY_KIND = "dbfox.music.library"
SCORE_KIND = "dbfox.music.score"
AUDIO_KIND = "dbfox.music.audio"
_AUDIO_EXTENSIONS = {"wav", "mp3", "m4a", "flac", "ogg"}
_MAX_AUDIO_BYTES = 128 * 1024 * 1024


def _canonical_document(document: ScoreDocument) -> str:
    return json.dumps(
        document.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _content_hash(encoded: str) -> str:
    return f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


class MusicStore:
    def __init__(self, data_path: Path) -> None:
        data_path.mkdir(parents=True, exist_ok=True)
        self.database_path = data_path / "state.sqlite3"
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS scores (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    head_revision INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('active', 'deleted')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_music_scores_project
                    ON scores(project_id, status, updated_at);
                CREATE TABLE IF NOT EXISTS score_revisions (
                    score_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    parent_revision INTEGER,
                    content_hash TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(score_id, revision),
                    FOREIGN KEY(score_id) REFERENCES scores(id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ux_music_score_revision_hash
                    ON score_revisions(score_id, content_hash);
                CREATE TABLE IF NOT EXISTS audio_sources (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    file_ref TEXT NOT NULL UNIQUE,
                    media_type TEXT NOT NULL,
                    byte_count INTEGER NOT NULL,
                    duration_seconds REAL NOT NULL,
                    sample_rate INTEGER NOT NULL,
                    channels INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL,
                    analysis_revision INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_music_audio_project
                    ON audio_sources(project_id, updated_at);
                CREATE TABLE IF NOT EXISTS audio_transcriptions (
                    audio_source_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    provider_id TEXT NOT NULL,
                    provider_version TEXT NOT NULL,
                    tempo INTEGER NOT NULL,
                    meter_json TEXT NOT NULL,
                    key_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    notes_json TEXT NOT NULL,
                    uncertain_ranges_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(audio_source_id, revision),
                    FOREIGN KEY(audio_source_id) REFERENCES audio_sources(id)
                );
                PRAGMA user_version = 2;
            """)

    @staticmethod
    def _revision(row: sqlite3.Row) -> ScoreRevision:
        return ScoreRevision(
            score_id=str(row["score_id"]),
            project_id=str(row["project_id"]),
            revision=int(row["revision"]),
            parent_revision=(int(row["parent_revision"]) if row["parent_revision"] is not None else None),
            content_hash=str(row["content_hash"]),
            document=ScoreDocument.model_validate_json(str(row["document_json"])),
            summary=str(row["summary"]),
            created_at=str(row["created_at"]),
        )

    def _revision_query(self, *, include_status: bool = False) -> str:
        status = ", s.status" if include_status else ""
        return (
            "SELECT r.*, s.project_id" + status + " FROM score_revisions r "
            "JOIN scores s ON s.id = r.score_id "
        )

    def create_score(self, project_id: str, document: ScoreDocument, summary: str) -> ScoreRevision:
        score_id = f"score_{uuid4().hex}"
        now = datetime.now(UTC).isoformat()
        encoded = _canonical_document(document)
        digest = _content_hash(encoded)
        with self._connect() as connection, connection:
            connection.execute(
                "INSERT INTO scores (id, project_id, title, head_revision, status, created_at, updated_at) VALUES (?, ?, ?, 1, 'active', ?, ?)",
                (score_id, project_id, document.title, now, now),
            )
            connection.execute(
                "INSERT INTO score_revisions (score_id, revision, parent_revision, content_hash, document_json, summary, created_at) VALUES (?, 1, NULL, ?, ?, ?, ?)",
                (score_id, digest, encoded, summary, now),
            )
        return self.get_revision(project_id, score_id, 1)

    def commit_revision(
        self,
        project_id: str,
        score_id: str,
        expected_revision: int,
        document: ScoreDocument,
        summary: str,
    ) -> ScoreRevision:
        encoded = _canonical_document(document)
        digest = _content_hash(encoded)
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT head_revision, status FROM scores WHERE id = ? AND project_id = ?",
                (score_id, project_id),
            ).fetchone()
            if row is None or str(row["status"]) != "active":
                connection.rollback()
                raise KeyError("score not found")
            if int(row["head_revision"]) != expected_revision:
                connection.rollback()
                raise ValueError("score revision is stale")
            duplicate = connection.execute(
                "SELECT revision FROM score_revisions WHERE score_id = ? AND content_hash = ?",
                (score_id, digest),
            ).fetchone()
            if duplicate is not None:
                connection.rollback()
                raise ValueError("score revision does not change the document")
            revision = expected_revision + 1
            connection.execute(
                "INSERT INTO score_revisions (score_id, revision, parent_revision, content_hash, document_json, summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (score_id, revision, expected_revision, digest, encoded, summary, now),
            )
            updated = connection.execute(
                "UPDATE scores SET title = ?, head_revision = ?, updated_at = ? WHERE id = ? AND project_id = ? AND head_revision = ?",
                (document.title, revision, now, score_id, project_id, expected_revision),
            )
            if updated.rowcount != 1:
                connection.rollback()
                raise ValueError("score revision changed concurrently")
            connection.commit()
        return self.get_revision(project_id, score_id, revision)

    def get_revision(self, project_id: str, score_id: str, revision: int | None = None) -> ScoreRevision:
        with self._connect() as connection:
            if revision is None:
                row = connection.execute(
                    self._revision_query() + "WHERE s.id = ? AND s.project_id = ? AND r.revision = s.head_revision",
                    (score_id, project_id),
                ).fetchone()
            else:
                row = connection.execute(
                    self._revision_query() + "WHERE s.id = ? AND s.project_id = ? AND r.revision = ?",
                    (score_id, project_id, revision),
                ).fetchone()
        if row is None:
            raise KeyError("score revision not found")
        return self._revision(row)

    def _summary(self, row: sqlite3.Row) -> ScoreSummary:
        document = ScoreDocument.model_validate_json(str(row["document_json"]))
        return ScoreSummary(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            title=str(row["title"]),
            head_revision=int(row["head_revision"]),
            status=str(row["status"]),
            content_hash=str(row["content_hash"]),
            tempo=document.tempo,
            key=document.key,
            meter=document.meter,
            measure_count=document.measure_count,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def list_scores(self, project_id: str, *, include_deleted: bool = False) -> list[ScoreSummary]:
        clause = "" if include_deleted else "AND s.status = 'active'"
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT s.*, r.content_hash, r.document_json FROM scores s JOIN score_revisions r ON r.score_id = s.id AND r.revision = s.head_revision WHERE s.project_id = ? "
                + clause + " ORDER BY s.updated_at DESC, s.id",
                (project_id,),
            ).fetchall()
        return [self._summary(row) for row in rows]

    def get_score(self, project_id: str, score_id: str) -> ScoreSummary:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT s.*, r.content_hash, r.document_json FROM scores s JOIN score_revisions r ON r.score_id = s.id AND r.revision = s.head_revision WHERE s.project_id = ? AND s.id = ?",
                (project_id, score_id),
            ).fetchone()
        if row is None:
            raise KeyError("score not found")
        return self._summary(row)

    def delete_score(self, project_id: str, score_id: str) -> bool:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection, connection:
            result = connection.execute(
                "UPDATE scores SET status = 'deleted', updated_at = ? WHERE project_id = ? AND id = ? AND status = 'active'",
                (now, project_id, score_id),
            )
        return result.rowcount == 1

    def list_resources(self, project_id: str) -> tuple[ProjectResourceDescriptor, ...]:
        resources = [
            ProjectResourceDescriptor(
                kind=LIBRARY_KIND,
                id=project_id,
                version="1",
                name="Music",
            )
        ]
        resources.extend(
            ProjectResourceDescriptor(
                kind=SCORE_KIND,
                id=score.id,
                version=score.head_revision,
                name=score.title,
            )
            for score in self.list_scores(project_id)
        )
        resources.extend(
            ProjectResourceDescriptor(
                kind=AUDIO_KIND,
                id=source.id,
                version=f"{source.fingerprint}:{source.analysis_revision}",
                name=source.name,
            )
            for source in self.list_audio_sources(project_id)
        )
        return tuple(resources)

    def resolve_library(self, ref: ResourceScopeRef) -> MusicLibrary:
        if ref.kind != LIBRARY_KIND or str(ref.version or "") != "1":
            raise ValueError("music library resource is stale or invalid")
        return MusicLibrary(project_id=str(ref.id))

    def resolve_score(self, ref: ResourceScopeRef) -> ScoreRevision:
        if ref.kind != SCORE_KIND:
            raise KeyError(ref.kind)
        if ref.version is None:
            raise ValueError("music score resource requires a frozen revision")
        with self._connect() as connection:
            row = connection.execute(
                self._revision_query(include_status=True) + "WHERE s.id = ? AND r.revision = ?",
                (str(ref.id), int(ref.version)),
            ).fetchone()
        if row is None or str(row["status"]) != "active":
            raise ValueError("music score revision does not exist or is inactive")
        # Canonical authority always points at the current head. An older
        # conversation intent is rejected and must be canonicalized again.
        summary = self.get_score(str(row["project_id"]), str(ref.id))
        if summary.head_revision != int(ref.version):
            raise ValueError("music score resource revision is stale")
        return self._revision(row)

    @staticmethod
    def _audio_source(row: sqlite3.Row) -> AudioSource:
        return AudioSource.model_validate(dict(row))

    def _audio_path(self, file_ref: str) -> Path:
        candidate = (self.database_path.parent / file_ref).resolve()
        audio_root = (self.database_path.parent / "audio").resolve()
        if candidate.parent != audio_root:
            raise ValueError("audio file reference escaped its private store")
        return candidate

    def import_audio(
        self,
        project_id: str,
        *,
        source_path: str,
        name: str,
        media_type: str,
        duration_seconds: float,
        sample_rate: int,
        channels: int,
    ) -> AudioSource:
        source = Path(source_path).resolve(strict=True)
        suffix = source.suffix.lower().lstrip(".")
        if suffix not in _AUDIO_EXTENSIONS or not source.is_file():
            raise ValueError("unsupported audio file")
        size = source.stat().st_size
        if size < 1 or size > _MAX_AUDIO_BYTES:
            raise ValueError("audio file size is outside the supported range")
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
        fingerprint = f"sha256:{digest.hexdigest()}"
        audio_id = f"audio_{uuid4().hex}"
        file_ref = f"audio/{audio_id}.{suffix}"
        destination = self._audio_path(file_ref)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(destination)
        now = datetime.now(UTC).isoformat()
        try:
            with self._connect() as connection, connection:
                connection.execute(
                    "INSERT INTO audio_sources (id, project_id, name, file_ref, media_type, byte_count, duration_seconds, sample_rate, channels, fingerprint, analysis_revision, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                    (audio_id, project_id, name, file_ref, media_type, size, duration_seconds, sample_rate, channels, fingerprint, now, now),
                )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return self.get_audio_source(project_id, audio_id)

    def get_audio_source(self, project_id: str, audio_source_id: str) -> AudioSource:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM audio_sources WHERE project_id = ? AND id = ?",
                (project_id, audio_source_id),
            ).fetchone()
        if row is None:
            raise KeyError("audio source not found")
        return self._audio_source(row)

    def list_audio_sources(self, project_id: str) -> list[AudioSource]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audio_sources WHERE project_id = ? ORDER BY updated_at DESC, id",
                (project_id,),
            ).fetchall()
        return [self._audio_source(row) for row in rows]

    def commit_transcription(
        self,
        project_id: str,
        input: CommitTranscriptionInput,
    ) -> AudioTranscription:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT analysis_revision, duration_seconds FROM audio_sources WHERE project_id = ? AND id = ?",
                (project_id, input.audio_source_id),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError("audio source not found")
            if any(note.end_seconds > float(row["duration_seconds"]) + 0.05 for note in input.notes):
                connection.rollback()
                raise ValueError("transcription notes exceed audio duration")
            revision = int(row["analysis_revision"]) + 1
            connection.execute(
                "INSERT INTO audio_transcriptions (audio_source_id, revision, provider_id, provider_version, tempo, meter_json, key_json, confidence, notes_json, uncertain_ranges_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    input.audio_source_id,
                    revision,
                    input.provider_id,
                    input.provider_version,
                    input.tempo,
                    json.dumps(input.meter.model_dump(mode="json"), sort_keys=True),
                    json.dumps(input.key.model_dump(mode="json"), sort_keys=True),
                    input.confidence,
                    json.dumps([item.model_dump(mode="json") for item in input.notes], separators=(",", ":")),
                    json.dumps([item.model_dump(mode="json") for item in input.uncertain_ranges], separators=(",", ":")),
                    now,
                ),
            )
            connection.execute(
                "UPDATE audio_sources SET analysis_revision = ?, updated_at = ? WHERE id = ?",
                (revision, now, input.audio_source_id),
            )
            connection.commit()
        committed = self.get_transcription(project_id, input.audio_source_id, revision)
        if committed is None:
            raise RuntimeError("committed audio transcription is unavailable")
        return committed

    def get_transcription(
        self,
        project_id: str,
        audio_source_id: str,
        revision: int | None = None,
    ) -> AudioTranscription | None:
        source = self.get_audio_source(project_id, audio_source_id)
        selected = revision if revision is not None else source.analysis_revision
        if selected == 0:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT t.* FROM audio_transcriptions t JOIN audio_sources a ON a.id = t.audio_source_id WHERE a.project_id = ? AND t.audio_source_id = ? AND t.revision = ?",
                (project_id, audio_source_id, selected),
            ).fetchone()
        if row is None:
            raise KeyError("audio transcription not found")
        return AudioTranscription(
            audio_source_id=audio_source_id,
            revision=int(row["revision"]),
            provider_id=str(row["provider_id"]),
            provider_version=str(row["provider_version"]),
            tempo=int(row["tempo"]),
            meter=json.loads(str(row["meter_json"])),
            key=json.loads(str(row["key_json"])),
            confidence=float(row["confidence"]),
            notes=json.loads(str(row["notes_json"])),
            uncertain_ranges=json.loads(str(row["uncertain_ranges_json"])),
            created_at=str(row["created_at"]),
        )

    def resolve_audio(self, ref: ResourceScopeRef) -> tuple[AudioSource, AudioTranscription | None]:
        if ref.kind != AUDIO_KIND:
            raise KeyError(ref.kind)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM audio_sources WHERE id = ?",
                (str(ref.id),),
            ).fetchone()
        if row is None:
            raise ValueError("audio source does not exist")
        source = self._audio_source(row)
        expected = f"{source.fingerprint}:{source.analysis_revision}"
        if str(ref.version or "") != expected:
            raise ValueError("audio source analysis revision is stale")
        return source, self.get_transcription(source.project_id, source.id)
