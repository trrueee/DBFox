"""Durable SQLite state for the dbfox.story DLC.

The DLC owns its facts: story worlds, entities, relationship edges, and
immutable revisions live here — queryable SQL, not prose in a context window.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from dbfox_dlc_api import ProjectResourceDescriptor, ResourceScopeRef

from .contracts import (
    ChapterCatalogItem,
    ChapterOutput,
    ChapterVersionCatalogItem,
    ChapterVersionOutput,
    EntityOutput,
    RelationEdgeOutput,
    RevisionOutput,
    WorldOutput,
)
from .resource_kind import STORY_WORLD_KIND


MAX_CHAPTER_CONTENT_CHARS = 100_000
MAX_CHAPTER_CONTENT_BYTES = MAX_CHAPTER_CONTENT_CHARS * 4


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex


class ChapterConflictError(ValueError):
    """The chapter changed after the caller read its current snapshot."""


class WorldHandle:
    """Authorized world handle resolved from a ResourceScopeRef."""

    def __init__(
        self,
        *,
        world_id: str,
        project_id: str,
        title: str,
        generation: int,
    ) -> None:
        self.id = world_id
        self.project_id = project_id
        self.title = title
        self.generation = generation


class StoryStateStore:
    def __init__(self, data_path: Path) -> None:
        self.root = (Path(data_path) / "dbfox.story").resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)
        self.chapter_root = self.root / "chapters"
        self.chapter_root.mkdir(parents=True, exist_ok=True)
        for tombstone in self.chapter_root.rglob(".*.deleted"):
            try:
                tombstone.unlink()
            except OSError:
                pass
        self.database_path = self.root / "state.sqlite3"
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
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS worlds (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    generation INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK (kind IN ('character','scene','plotline')),
                    name TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (project_id, kind, name)
                );
                CREATE TABLE IF NOT EXISTS relation_edges (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    from_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                    to_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK (status IN ('pending','confirmed','rejected')),
                    revision_id TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );
                CREATE TABLE IF NOT EXISTS chapters (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    content_path TEXT,
                    content_sha256 TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chapter_versions (
                    id TEXT PRIMARY KEY,
                    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
                    seq INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_sha256 TEXT,
                    author TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_edges_project_status
                    ON relation_edges (project_id, status);
                """
            )
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(chapters)")
            }
            if "content_path" not in columns:
                connection.execute("ALTER TABLE chapters ADD COLUMN content_path TEXT")
            if "content_sha256" not in columns:
                connection.execute("ALTER TABLE chapters ADD COLUMN content_sha256 TEXT")
            version_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(chapter_versions)")
            }
            if "content_sha256" not in version_columns:
                connection.execute(
                    "ALTER TABLE chapter_versions ADD COLUMN content_sha256 TEXT"
                )
            for version in connection.execute(
                "SELECT id, content FROM chapter_versions WHERE content_sha256 IS NULL"
            ).fetchall():
                connection.execute(
                    "UPDATE chapter_versions SET content_sha256 = ? WHERE id = ?",
                    (
                        hashlib.sha256(str(version["content"]).encode("utf-8")).hexdigest(),
                        version["id"],
                    ),
                )
            self._normalize_chapter_version_sequences(connection)
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_chapter_versions_seq"
                " ON chapter_versions (chapter_id, seq)"
            )
            self._migrate_chapter_files(connection)

    @staticmethod
    def _normalize_chapter_version_sequences(
        connection: sqlite3.Connection,
    ) -> None:
        """Repair legacy duplicate sequences before adding uniqueness."""

        duplicates = connection.execute(
            "SELECT 1 FROM chapter_versions GROUP BY chapter_id, seq"
            " HAVING COUNT(*) > 1 LIMIT 1"
        ).fetchone()
        if duplicates is None:
            return
        chapter_ids = connection.execute(
            "SELECT DISTINCT chapter_id FROM chapter_versions"
        ).fetchall()
        for chapter in chapter_ids:
            chapter_id = str(chapter["chapter_id"])
            rows = connection.execute(
                "SELECT id FROM chapter_versions WHERE chapter_id = ?"
                " ORDER BY seq, created_at, rowid",
                (chapter_id,),
            ).fetchall()
            for offset, row in enumerate(rows, start=1):
                connection.execute(
                    "UPDATE chapter_versions SET seq = ? WHERE id = ?",
                    (-offset, row["id"]),
                )
            connection.execute(
                "UPDATE chapter_versions SET seq = -seq WHERE chapter_id = ?",
                (chapter_id,),
            )

    def _migrate_chapter_files(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT id, project_id, content, content_path FROM chapters"
        ).fetchall()
        for row in rows:
            relative_path = str(row["content_path"] or self._chapter_relative_path(
                str(row["project_id"]), str(row["id"])
            ))
            path = self._resolve_chapter_path(relative_path)
            content = str(row["content"] or "")
            if not path.is_file():
                if not content:
                    version = connection.execute(
                        "SELECT content FROM chapter_versions WHERE chapter_id = ? ORDER BY seq DESC LIMIT 1",
                        (row["id"],),
                    ).fetchone()
                    content = str(version["content"] or "") if version else ""
                self._write_chapter_file(path, content)
            digest = hashlib.sha256(self._read_chapter_bytes(path)).hexdigest()
            connection.execute(
                "UPDATE chapters SET content = '', content_path = ?, content_sha256 = ? WHERE id = ?",
                (relative_path, digest, row["id"]),
            )

    @staticmethod
    def _chapter_relative_path(project_id: str, chapter_id: str) -> str:
        return f"chapters/{project_id}/{chapter_id}.md"

    def _resolve_chapter_path(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve(strict=False)
        if path == self.root or not path.is_relative_to(self.root):
            raise ValueError("章节正文文件越出故事目录。")
        return path

    @staticmethod
    def _read_chapter_bytes(path: Path) -> bytes:
        try:
            with path.open("rb") as stream:
                data = stream.read(MAX_CHAPTER_CONTENT_BYTES + 1)
        except OSError as exc:
            raise ValueError("章节正文文件不可读取。") from exc
        if len(data) > MAX_CHAPTER_CONTENT_BYTES:
            raise ValueError("章节正文文件超过 400000 字节上限。")
        return data

    @staticmethod
    def _write_chapter_file(path: Path, content: str) -> str:
        if len(content) > MAX_CHAPTER_CONTENT_CHARS:
            raise ValueError("章节正文超过 100000 字上限。")
        data = content.encode("utf-8")
        if len(data) > MAX_CHAPTER_CONTENT_BYTES:
            raise ValueError("章节正文超过 UTF-8 存储上限。")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
            ) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
                temporary = Path(stream.name)
            os.replace(temporary, path)
        except OSError:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise
        return hashlib.sha256(data).hexdigest()

    # ── Worlds ──

    def ensure_world(self, project_id: str, title: str | None = None) -> WorldOutput:
        with self._connect() as connection, connection:
            row = connection.execute(
                "SELECT * FROM worlds WHERE project_id = ?", (project_id,)
            ).fetchone()
            if row is None:
                now = _now()
                connection.execute(
                    "INSERT INTO worlds (id, project_id, title, generation, created_at, updated_at)"
                    " VALUES (?, ?, ?, 1, ?, ?)",
                    (_new_id(), project_id, title or "未命名故事", now, now),
                )
                row = connection.execute(
                    "SELECT * FROM worlds WHERE project_id = ?", (project_id,)
                ).fetchone()
            elif title and row["title"] != title:
                connection.execute(
                    "UPDATE worlds SET title = ?, updated_at = ? WHERE id = ?",
                    (title, _now(), row["id"]),
                )
                row = connection.execute(
                    "SELECT * FROM worlds WHERE project_id = ?", (project_id,)
                ).fetchone()
        return self._world_output(row)

    def get_world(self, project_id: str) -> WorldOutput | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM worlds WHERE project_id = ?", (project_id,)
            ).fetchone()
        return self._world_output(row) if row else None

    def _bump_world(self, connection: sqlite3.Connection, project_id: str) -> None:
        connection.execute(
            "UPDATE worlds SET generation = generation + 1, updated_at = ? WHERE project_id = ?",
            (_now(), project_id),
        )

    def _world_output(self, row: sqlite3.Row) -> WorldOutput:
        return WorldOutput(
            id=row["id"],
            title=row["title"],
            generation=int(row["generation"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── Resource provider surface ──

    def list_resources(self, project_id: str) -> tuple[ProjectResourceDescriptor, ...]:
        world = self.get_world(project_id)
        if world is None:
            return ()
        return (
            ProjectResourceDescriptor(
                kind=STORY_WORLD_KIND,
                id=world.id,
                version=str(world.generation),
                name=world.title,
                is_default=True,
            ),
        )

    def resolve(self, ref: ResourceScopeRef) -> WorldHandle:
        if ref.kind != STORY_WORLD_KIND:
            raise KeyError(f"Unexpected resource kind: {ref.kind}")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM worlds WHERE id = ?", (ref.id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"Story world '{ref.id}' does not exist")
        # Unlike a database resource, a story world has no dangerous reads to
        # stale-fence: the id already pins the project. Mid-Run entity edits
        # bump the generation, so enforcing the frozen version here would
        # invalidate the Run's own write tools.
        return WorldHandle(
            world_id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            generation=int(row["generation"]),
        )

    # ── Entities ──

    def create_entity(
        self,
        project_id: str,
        *,
        kind: str,
        name: str,
        summary: str,
    ) -> EntityOutput:
        now = _now()
        with self._connect() as connection, connection:
            exists = connection.execute(
                "SELECT 1 FROM entities WHERE project_id = ? AND kind = ? AND name = ?",
                (project_id, kind, name),
            ).fetchone()
            if exists:
                raise ValueError(f"{kind} “{name}”已存在。")
            connection.execute(
                "INSERT INTO entities (id, project_id, kind, name, summary, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (_new_id(), project_id, kind, name, summary, now, now),
            )
            self._bump_world(connection, project_id)
            row = connection.execute(
                "SELECT * FROM entities WHERE project_id = ? AND kind = ? AND name = ?",
                (project_id, kind, name),
            ).fetchone()
        return self._entity_output(row)

    def update_entity(
        self,
        project_id: str,
        entity_id: str,
        *,
        name: str | None,
        summary: str | None,
    ) -> EntityOutput:
        with self._connect() as connection, connection:
            row = self._entity_row(connection, project_id, entity_id)
            updates: dict[str, object] = {}
            if name is not None and name != row["name"]:
                clash = connection.execute(
                    "SELECT 1 FROM entities WHERE project_id = ? AND kind = ? AND name = ?",
                    (project_id, row["kind"], name),
                ).fetchone()
                if clash:
                    raise ValueError(f"{row['kind']} “{name}”已存在。")
                updates["name"] = name
            if summary is not None:
                updates["summary"] = summary
            if updates:
                updates["updated_at"] = _now()
                assignments = ", ".join(f"{column} = ?" for column in updates)
                connection.execute(
                    f"UPDATE entities SET {assignments} WHERE id = ?",
                    (*updates.values(), entity_id),
                )
                self._bump_world(connection, project_id)
            row = self._entity_row(connection, project_id, entity_id)
        return self._entity_output(row)

    def delete_entity(self, project_id: str, entity_id: str) -> bool:
        with self._connect() as connection, connection:
            self._entity_row(connection, project_id, entity_id)
            cursor = connection.execute(
                "DELETE FROM entities WHERE id = ?", (entity_id,)
            )
            self._bump_world(connection, project_id)
            return cursor.rowcount > 0

    def list_entities(
        self,
        project_id: str,
        *,
        kind: str | None = None,
        name_contains: str | None = None,
    ) -> tuple[EntityOutput, ...]:
        query = "SELECT * FROM entities WHERE project_id = ?"
        parameters: list[object] = [project_id]
        if kind:
            query += " AND kind = ?"
            parameters.append(kind)
        if name_contains:
            query += " AND name LIKE ?"
            parameters.append(f"%{name_contains}%")
        query += " ORDER BY kind, created_at"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(self._entity_output(row) for row in rows)

    def _entity_row(
        self, connection: sqlite3.Connection, project_id: str, entity_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM entities WHERE id = ? AND project_id = ?",
            (entity_id, project_id),
        ).fetchone()
        if row is None:
            raise ValueError("实体不存在或不属于当前项目。")
        return row

    @staticmethod
    def _entity_output(row: sqlite3.Row) -> EntityOutput:
        return EntityOutput(
            id=row["id"],
            kind=row["kind"],
            name=row["name"],
            summary=row["summary"],
            updated_at=row["updated_at"],
        )

    # ── Relation edges ──

    def propose_relations(
        self,
        project_id: str,
        items: list[dict[str, str]],
    ) -> tuple[tuple[RelationEdgeOutput, ...], tuple[str, ...]]:
        """Create pending edges from {from_name, to_name, kind, reason} items.

        Returns (created edges, unknown-name errors). Duplicate pending or
        confirmed edges for the same triple are skipped and reported.
        """
        created: list[RelationEdgeOutput] = []
        unknown: list[str] = []
        now = _now()
        with self._connect() as connection, connection:
            for item in items:
                from_row = connection.execute(
                    "SELECT id, name FROM entities WHERE project_id = ? AND name = ?",
                    (project_id, item["from_name"]),
                ).fetchone()
                to_row = connection.execute(
                    "SELECT id, name FROM entities WHERE project_id = ? AND name = ?",
                    (project_id, item["to_name"]),
                ).fetchone()
                if from_row is None:
                    unknown.append(item["from_name"])
                    continue
                if to_row is None:
                    unknown.append(item["to_name"])
                    continue
                duplicate = connection.execute(
                    "SELECT 1 FROM relation_edges WHERE project_id = ? AND from_entity_id = ?"
                    " AND to_entity_id = ? AND kind = ? AND status IN ('pending','confirmed')",
                    (project_id, from_row["id"], to_row["id"], item["kind"]),
                ).fetchone()
                if duplicate:
                    continue
                connection.execute(
                    "INSERT INTO relation_edges (id, project_id, from_entity_id, to_entity_id,"
                    " kind, reason, status, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                    (
                        _new_id(),
                        project_id,
                        from_row["id"],
                        to_row["id"],
                        item["kind"],
                        item.get("reason", ""),
                        now,
                    ),
                )
                created.append(
                    self._edge_output(
                        connection,
                        connection.execute(
                            "SELECT * FROM relation_edges WHERE from_entity_id = ?"
                            " AND to_entity_id = ? AND kind = ? AND status = 'pending'"
                            " AND created_at = ?",
                            (from_row["id"], to_row["id"], item["kind"], now),
                        ).fetchone(),
                    )
                )
        return tuple(created), tuple(unknown)

    def decide_edge(
        self,
        project_id: str,
        edge_id: str,
        decision: str,
    ) -> RelationEdgeOutput:
        with self._connect() as connection, connection:
            row = self._edge_row(connection, project_id, edge_id)
            if row["status"] == "confirmed" and decision != "confirmed":
                raise ValueError("已进入修订的关系不可回退；请先创建新修订或提出新提案。")
            connection.execute(
                "UPDATE relation_edges SET status = ?, decided_at = ? WHERE id = ?",
                (decision, _now(), edge_id),
            )
            self._bump_world(connection, project_id)
            row = self._edge_row(connection, project_id, edge_id)
            return self._edge_output(connection, row)

    def decide_batch(
        self,
        project_id: str,
        decisions: list[dict[str, str]],
    ) -> tuple[RelationEdgeOutput, ...]:
        return tuple(
            self.decide_edge(project_id, item["edge_id"], item["decision"])
            for item in decisions
        )

    def list_edges(
        self,
        project_id: str,
        *,
        status: str | None = None,
    ) -> tuple[RelationEdgeOutput, ...]:
        query = "SELECT * FROM relation_edges WHERE project_id = ?"
        parameters: list[object] = [project_id]
        if status:
            query += " AND status = ?"
            parameters.append(status)
        query += " ORDER BY created_at"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
            return tuple(self._edge_output(connection, row) for row in rows)

    def _edge_row(
        self, connection: sqlite3.Connection, project_id: str, edge_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM relation_edges WHERE id = ? AND project_id = ?",
            (edge_id, project_id),
        ).fetchone()
        if row is None:
            raise ValueError("关系不存在或不属于当前项目。")
        return row

    @staticmethod
    def _edge_output(
        connection: sqlite3.Connection, row: sqlite3.Row
    ) -> RelationEdgeOutput:
        names = {
            entity_row["id"]: entity_row["name"]
            for entity_row in connection.execute(
                "SELECT id, name FROM entities WHERE project_id = ?",
                (row["project_id"],),
            ).fetchall()
        }
        return RelationEdgeOutput(
            id=row["id"],
            from_entity_id=row["from_entity_id"],
            from_name=names.get(row["from_entity_id"], row["from_entity_id"]),
            to_entity_id=row["to_entity_id"],
            to_name=names.get(row["to_entity_id"], row["to_entity_id"]),
            kind=row["kind"],
            reason=row["reason"],
            status=row["status"],
            revision_id=row["revision_id"],
            created_at=row["created_at"],
            decided_at=row["decided_at"],
        )

    # ── Revisions ──

    def commit_revision(
        self,
        project_id: str,
        note: str,
    ) -> tuple[RevisionOutput, int]:
        """Promote every confirmed-but-unrevised edge into an immutable revision."""
        now = _now()
        with self._connect() as connection, connection:
            world_row = connection.execute(
                "SELECT id FROM worlds WHERE project_id = ?", (project_id,)
            ).fetchone()
            if world_row is None:
                raise ValueError("故事世界不存在。")
            pending_confirm = connection.execute(
                "SELECT id FROM relation_edges WHERE project_id = ?"
                " AND status = 'confirmed' AND revision_id IS NULL",
                (project_id,),
            ).fetchall()
            seq_row = connection.execute(
                "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM revisions WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            revision_id = _new_id()
            seq = int(seq_row["max_seq"]) + 1
            connection.execute(
                "INSERT INTO revisions (id, project_id, seq, note, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (revision_id, project_id, seq, note, now),
            )
            for row in pending_confirm:
                connection.execute(
                    "UPDATE relation_edges SET revision_id = ? WHERE id = ?",
                    (revision_id, row["id"]),
                )
            return (
                RevisionOutput(
                    id=revision_id,
                    seq=seq,
                    note=note,
                    confirmed_count=len(pending_confirm),
                    created_at=now,
                ),
                len(pending_confirm),
            )

    def list_revisions(self, project_id: str) -> tuple[RevisionOutput, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT r.*, (SELECT COUNT(*) FROM relation_edges e"
                " WHERE e.revision_id = r.id) AS confirmed_count"
                " FROM revisions r WHERE r.project_id = ? ORDER BY r.seq",
                (project_id,),
            ).fetchall()
        return tuple(
            RevisionOutput(
                id=row["id"],
                seq=int(row["seq"]),
                note=row["note"],
                confirmed_count=int(row["confirmed_count"]),
                created_at=row["created_at"],
            )
            for row in rows
        )

    # ── Chapters ──

    def create_chapter(
        self,
        project_id: str,
        *,
        title: str,
        content: str,
        author: str,
    ) -> ChapterOutput:
        now = _now()
        chapter_id = _new_id()
        relative_path = self._chapter_relative_path(project_id, chapter_id)
        path = self._resolve_chapter_path(relative_path)
        digest = ""
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                seq_row = connection.execute(
                    "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM chapters WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
                seq = int(seq_row["max_seq"]) + 1
                digest = self._write_chapter_file(path, content)
                connection.execute(
                    "INSERT INTO chapters (id, project_id, seq, title, content, content_path,"
                    " content_sha256, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, '', ?, ?, ?, ?)",
                    (chapter_id, project_id, seq, title, relative_path, digest, now, now),
                )
                connection.execute(
                    "INSERT INTO chapter_versions"
                    " (id, chapter_id, seq, title, content, content_sha256, author, created_at)"
                    " VALUES (?, ?, 1, ?, ?, ?, ?, ?)",
                    (_new_id(), chapter_id, title, content, digest, author, now),
                )
                row = connection.execute(
                    "SELECT * FROM chapters WHERE id = ?", (chapter_id,)
                ).fetchone()
                connection.commit()
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return self._chapter_output(row, content=content, digest=digest)

    def update_chapter(
        self,
        project_id: str,
        chapter_id: str,
        *,
        title: str | None,
        content: str | None,
        author: str,
        expected_sha256: str,
    ) -> ChapterOutput:
        now = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_row = self._chapter_row(connection, project_id, chapter_id)
            current_row, current_content, path, current_digest = self._reconcile_chapter(
                connection,
                current_row,
            )
            if current_digest != expected_sha256:
                connection.commit()
                raise ChapterConflictError(
                    "章节已在读取后发生变化，请重新读取后再保存。"
                )
            new_title = title if title is not None else current_row["title"]
            new_content = content if content is not None else current_content
            previous_bytes = current_content.encode("utf-8")
            digest = self._write_chapter_file(path, new_content)
            try:
                version_seq = self._next_chapter_version_seq(connection, chapter_id)
                connection.execute(
                    "INSERT INTO chapter_versions"
                    " (id, chapter_id, seq, title, content, content_sha256, author, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        _new_id(),
                        chapter_id,
                        version_seq,
                        new_title,
                        new_content,
                        digest,
                        author,
                        now,
                    ),
                )
                connection.execute(
                    "UPDATE chapters SET title = ?, content = '', content_sha256 = ?,"
                    " updated_at = ? WHERE id = ?",
                    (new_title, digest, now, chapter_id),
                )
                row = self._chapter_row(connection, project_id, chapter_id)
                connection.commit()
            except Exception:
                connection.rollback()
                self._write_chapter_file(path, previous_bytes.decode("utf-8"))
                raise
        return self._chapter_output(row, content=new_content, digest=digest)

    def append_chapter(
        self,
        project_id: str,
        chapter_id: str,
        *,
        content: str,
        author: str,
        expected_sha256: str,
    ) -> ChapterOutput:
        chapter = self.get_chapter(project_id, chapter_id)
        if chapter.content_sha256 != expected_sha256:
            raise ChapterConflictError(
                "章节已在读取后发生变化，请重新读取后再续写。"
            )
        combined = chapter.content.rstrip() + "\n\n" + content.lstrip()
        if len(combined) > 100_000:
            raise ValueError("章节续写后超过 100000 字上限。")
        return self.update_chapter(
            project_id,
            chapter_id,
            title=None,
            content=combined,
            author=author,
            expected_sha256=expected_sha256,
        )

    def delete_chapter(self, project_id: str, chapter_id: str) -> bool:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._chapter_row(connection, project_id, chapter_id)
            _row, _content, path, _digest = self._reconcile_chapter(connection, row)
            tombstone = path.with_name(f".{path.name}.{_new_id()}.deleted")
            os.replace(path, tombstone)
            try:
                cursor = connection.execute(
                    "DELETE FROM chapters WHERE id = ?", (chapter_id,)
                )
                connection.commit()
            except Exception:
                connection.rollback()
                os.replace(tombstone, path)
                raise
        try:
            tombstone.unlink(missing_ok=True)
        except OSError:
            pass
        return cursor.rowcount > 0

    def move_chapter(self, project_id: str, chapter_id: str, direction: str) -> None:
        if direction not in ("up", "down"):
            raise ValueError("direction 只能是 up 或 down。")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._chapter_row(connection, project_id, chapter_id)
            neighbor_seq = row["seq"] - 1 if direction == "up" else row["seq"] + 1
            neighbor = connection.execute(
                "SELECT id FROM chapters WHERE project_id = ? AND seq = ?",
                (project_id, neighbor_seq),
            ).fetchone()
            if neighbor is None:
                connection.commit()
                return
            connection.execute("UPDATE chapters SET seq = ? WHERE id = ?", (neighbor_seq, row["id"]))
            connection.execute("UPDATE chapters SET seq = ? WHERE id = ?", (row["seq"], neighbor["id"]))
            connection.commit()

    def list_chapter_catalog(
        self,
        project_id: str,
    ) -> tuple[ChapterCatalogItem, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, seq, title, updated_at FROM chapters"
                " WHERE project_id = ? ORDER BY seq",
                (project_id,),
            ).fetchall()
        return tuple(
            ChapterCatalogItem(
                id=str(row["id"]),
                seq=int(row["seq"]),
                title=str(row["title"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        )

    def list_chapters(self, project_id: str) -> tuple[ChapterOutput, ...]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT * FROM chapters WHERE project_id = ? ORDER BY seq",
                (project_id,),
            ).fetchall()
            chapters = tuple(
                self._chapter_output(
                    reconciled,
                    content=content,
                    digest=digest,
                )
                for reconciled, content, _path, digest in (
                    self._reconcile_chapter(connection, row) for row in rows
                )
            )
            connection.commit()
        return chapters

    def get_chapter(self, project_id: str, chapter_id: str) -> ChapterOutput:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._chapter_row(connection, project_id, chapter_id)
            row, content, _path, digest = self._reconcile_chapter(connection, row)
            connection.commit()
        return self._chapter_output(row, content=content, digest=digest)

    def list_chapter_versions(
        self,
        project_id: str,
        chapter_id: str,
    ) -> tuple[ChapterVersionCatalogItem, ...]:
        self.get_chapter(project_id, chapter_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, chapter_id, seq, title, content_sha256, author, created_at"
                " FROM chapter_versions WHERE chapter_id = ? ORDER BY seq DESC",
                (chapter_id,),
            ).fetchall()
        return tuple(self._chapter_version_catalog(row) for row in rows)

    def get_chapter_version(
        self,
        project_id: str,
        chapter_id: str,
        version_id: str,
    ) -> ChapterVersionOutput:
        self.get_chapter(project_id, chapter_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chapter_versions WHERE id = ? AND chapter_id = ?",
                (version_id, chapter_id),
            ).fetchone()
        if row is None:
            raise ValueError("章节版本不存在。")
        return self._chapter_version_output(row)

    def restore_chapter_version(
        self,
        project_id: str,
        chapter_id: str,
        version_id: str,
        *,
        expected_sha256: str,
        author: str,
    ) -> ChapterOutput:
        version = self.get_chapter_version(project_id, chapter_id, version_id)
        return self.update_chapter(
            project_id,
            chapter_id,
            title=version.title,
            content=version.content,
            author=author,
            expected_sha256=expected_sha256,
        )

    def _chapter_row(
        self, connection: sqlite3.Connection, project_id: str, chapter_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM chapters WHERE id = ? AND project_id = ?",
            (chapter_id, project_id),
        ).fetchone()
        if row is None:
            raise ValueError("章节不存在或不属于当前项目。")
        return row

    @staticmethod
    def _next_chapter_version_seq(
        connection: sqlite3.Connection,
        chapter_id: str,
    ) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM chapter_versions"
            " WHERE chapter_id = ?",
            (chapter_id,),
        ).fetchone()
        return int(row["max_seq"]) + 1

    def _reconcile_chapter(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> tuple[sqlite3.Row, str, Path, str]:
        """Reconcile the Markdown current value with durable version history.

        SQLite serializes this method under ``BEGIN IMMEDIATE``. A process crash
        after the atomic file replacement but before the metadata commit is
        recovered as an explicit ``recovery`` version on the next access.
        """

        relative_path = str(row["content_path"] or "")
        path = self._resolve_chapter_path(relative_path)
        if not path.is_file():
            latest = connection.execute(
                "SELECT title, content, content_sha256 FROM chapter_versions"
                " WHERE chapter_id = ? ORDER BY seq DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            if latest is None:
                raise ValueError("章节正文文件不存在且没有可恢复版本。")
            content = str(latest["content"])
            digest = self._write_chapter_file(path, content)
            connection.execute(
                "UPDATE chapters SET title = ?, content_sha256 = ?, updated_at = ?"
                " WHERE id = ?",
                (str(latest["title"]), digest, _now(), row["id"]),
            )
            row = self._chapter_row(connection, str(row["project_id"]), str(row["id"]))
            return row, content, path, digest

        data = self._read_chapter_bytes(path)
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("章节正文文件不是 UTF-8 文本。") from exc
        if len(content) > MAX_CHAPTER_CONTENT_CHARS:
            raise ValueError("章节正文超过 100000 字上限。")
        digest = hashlib.sha256(data).hexdigest()
        stored_digest = str(row["content_sha256"] or "")
        if digest != stored_digest:
            now = _now()
            connection.execute(
                "INSERT INTO chapter_versions"
                " (id, chapter_id, seq, title, content, content_sha256, author, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, 'recovery', ?)",
                (
                    _new_id(),
                    row["id"],
                    self._next_chapter_version_seq(connection, str(row["id"])),
                    row["title"],
                    content,
                    digest,
                    now,
                ),
            )
            connection.execute(
                "UPDATE chapters SET content_sha256 = ?, updated_at = ? WHERE id = ?",
                (digest, now, row["id"]),
            )
            row = self._chapter_row(connection, str(row["project_id"]), str(row["id"]))
        return row, content, path, digest

    def _chapter_content(self, row: sqlite3.Row) -> tuple[str, Path, str]:
        relative_path = str(row["content_path"] or "")
        path = (self.root / relative_path).resolve(strict=True)
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError("章节正文文件不存在或越出故事目录。")
        data = path.read_bytes()
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("章节正文文件不是 UTF-8 文本。") from exc
        return content, path, hashlib.sha256(data).hexdigest()

    def _chapter_output(
        self,
        row: sqlite3.Row,
        *,
        content: str | None = None,
        digest: str | None = None,
    ) -> ChapterOutput:
        if content is None or digest is None:
            content, _path, digest = self._chapter_content(row)
        return ChapterOutput(
            id=row["id"],
            seq=int(row["seq"]),
            title=row["title"],
            content=content,
            content_path=str(row["content_path"]),
            content_sha256=digest,
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _chapter_version_catalog(row: sqlite3.Row) -> ChapterVersionCatalogItem:
        return ChapterVersionCatalogItem(
            id=row["id"],
            chapter_id=row["chapter_id"],
            seq=int(row["seq"]),
            title=row["title"],
            content_sha256=row["content_sha256"],
            author=row["author"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _chapter_version_output(row: sqlite3.Row) -> ChapterVersionOutput:
        return ChapterVersionOutput(
            id=row["id"],
            chapter_id=row["chapter_id"],
            seq=int(row["seq"]),
            title=row["title"],
            content=row["content"],
            content_sha256=row["content_sha256"],
            author=row["author"],
            created_at=row["created_at"],
        )

    # ── Agent-facing facts ──

    def graph_facts(
        self,
        project_id: str,
        *,
        entity_kind: str | None = None,
        name_contains: str | None = None,
    ) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
        """Return all entities and CONFIRMED relations only. Pending proposals
        and rejected vetoes are author workspace state, never world truth."""
        entities = self.list_entities(
            project_id, kind=entity_kind, name_contains=name_contains
        )
        confirmed = self.list_edges(project_id, status="confirmed")
        entity_payload = tuple(
            {"name": entity.name, "kind": entity.kind, "summary": entity.summary}
            for entity in entities
        )
        relation_payload = tuple(
            {
                "from": edge.from_name,
                "to": edge.to_name,
                "kind": edge.kind,
                "reason": edge.reason,
            }
            for edge in confirmed
        )
        return entity_payload, relation_payload
