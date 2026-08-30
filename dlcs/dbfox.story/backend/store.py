"""Durable SQLite state for the dbfox.story DLC.

The DLC owns its facts: story worlds, entities, relationship edges, and
immutable revisions live here — queryable SQL, not prose in a context window.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from dbfox_dlc_api import ResourceScopeRef
from pydantic import BaseModel, ConfigDict

from .contracts import (
    EntityOutput,
    RelationEdgeOutput,
    RevisionOutput,
    WorldOutput,
)
from .resource_kind import STORY_WORLD_KIND


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex


class WorldDescriptor(BaseModel):
    """Resource discovery descriptor for the project's story world."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    id: str
    version: str
    name: str
    is_default: bool = True


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
        root = Path(data_path) / "dbfox.story"
        root.mkdir(parents=True, exist_ok=True)
        self.database_path = root / "state.sqlite3"
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

    def list_resources(self, project_id: str) -> tuple[WorldDescriptor, ...]:
        world = self.get_world(project_id)
        if world is None:
            return ()
        return (
            WorldDescriptor(
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
        if str(row["generation"]) != str(ref.version or ""):
            raise ValueError(
                f"Story world '{ref.id}' changed: authorized version"
                f" {ref.version!r}, current {row['generation']}"
            )
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
