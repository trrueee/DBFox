"""Single durable Voxel authority: immutable chunk deltas and metadata revisions."""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from dbfox_dlc_api import BaseModel, ProjectResourceDescriptor, ResourceScopeRef

from .contracts import (
    CHUNK_BYTES, LIBRARY_KIND, MAX_HISTORY_BYTES, MAX_LIVE_CHUNKS, MAX_METADATA_BYTES,
    WORLD_KIND, ApplyInput, ChunkData, ChunkDifference, ChunkPageInput, ChunkPageOutput,
    ConfigureInput, CreateInput, DiffInput, DiffOutput, InspectInput, InspectOutput,
    LayerOrder, LayerPut, LayerRemove, ListInput, MetadataSet, MutationOutput,
    PalettePut, PaletteRemove, ReadInput, RegionPut, RegionRemove, Rename,
    RevisionsInput, RevisionsOutput, RevisionSummary, UndoInput, WorldDocument,
    WorldListOutput, WorldOutput, WorldSummary, WriteInput,
)
from .geometry import (
    EMPTY_CHUNK, Canvas, ChunkKey, VoxelError, apply_geometry, check_cancel,
    layer_exists, positions, validate_bounds,
)


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def payload_hash(kind: str, value: BaseModel) -> str:
    return digest(canonical({"schema": 1, "operation": kind, "input": value.model_dump(mode="json")}).encode("utf-8"))


def now() -> str:
    return datetime.now(UTC).isoformat()


def never_cancelled() -> bool:
    return False


@dataclass(frozen=True)
class Library:
    project_id: str


@dataclass(frozen=True)
class ChunkRecord:
    version: int
    raw_hash: str
    nonzero_count: int


@dataclass(frozen=True)
class WorldSnapshot:
    world_id: str
    project_id: str
    version: int
    parent_version: int | None
    content_hash: str
    document: WorldDocument
    chunks: dict[ChunkKey, ChunkRecord]


def fingerprint(document: WorldDocument, chunks: dict[ChunkKey, ChunkRecord]) -> str:
    hasher = hashlib.sha256()
    hasher.update(canonical(document.model_dump(mode="json")).encode("utf-8"))
    for key, record in sorted(chunks.items()):
        hasher.update(b"\n")
        hasher.update(canonical([*key, record.raw_hash]).encode("utf-8"))
    return "sha256:" + hasher.hexdigest()


class VoxelStore:
    def __init__(self, data_path: Path) -> None:
        data_path.mkdir(parents=True, exist_ok=True)
        self.database_path = data_path / "state.sqlite3"
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        try:
            yield connection
        except sqlite3.Error as exc:
            connection.rollback()
            if isinstance(exc, sqlite3.OperationalError) and ("locked" in str(exc).lower() or "busy" in str(exc).lower()):
                raise VoxelError("STORE_BUSY", "The voxel store is busy; refresh before another edit.", 409) from exc
            raise VoxelError("CORRUPT_STATE", "The voxel store could not be read or committed safely.", 409) from exc
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in (0, 1):
                raise VoxelError("UNSUPPORTED_SCHEMA", "This voxel store uses an unsupported schema version.", 409)
            if version == 0:
                existing = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
                if existing:
                    raise VoxelError("UNSUPPORTED_SCHEMA", "The voxel store has unversioned tables; automatic adoption is unavailable.", 409)
                connection.execute("PRAGMA journal_mode=WAL")
                connection.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE worlds (
                        id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                        head_version INTEGER NOT NULL CHECK(head_version >= 1), created_at TEXT NOT NULL
                    );
                    CREATE INDEX ix_worlds_project ON worlds(project_id,id);
                    CREATE TABLE world_revisions (
                        world_id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version >= 1),
                        parent_version INTEGER, operation_kind TEXT NOT NULL,
                        restored_from_version INTEGER, document_json TEXT NOT NULL,
                        content_hash TEXT NOT NULL, created_at TEXT NOT NULL,
                        PRIMARY KEY(world_id,version), FOREIGN KEY(world_id) REFERENCES worlds(id)
                    );
                    CREATE TABLE chunk_versions (
                        world_id TEXT NOT NULL, layer_id TEXT NOT NULL,
                        cx INTEGER NOT NULL CHECK(cx BETWEEN 0 AND 15),
                        cy INTEGER NOT NULL CHECK(cy BETWEEN 0 AND 15),
                        cz INTEGER NOT NULL CHECK(cz BETWEEN 0 AND 15),
                        version INTEGER NOT NULL, raw_hash TEXT NOT NULL,
                        nonzero_count INTEGER NOT NULL CHECK(nonzero_count BETWEEN 0 AND 4096),
                        blob BLOB,
                        CHECK((nonzero_count=0 AND blob IS NULL) OR (nonzero_count>0 AND blob IS NOT NULL)),
                        PRIMARY KEY(world_id,layer_id,cx,cy,cz,version),
                        FOREIGN KEY(world_id,version) REFERENCES world_revisions(world_id,version)
                    );
                    CREATE INDEX ix_chunks_revision ON chunk_versions(world_id,version,layer_id,cx,cy,cz);
                    CREATE TABLE operation_receipts (
                        project_id TEXT NOT NULL, origin TEXT NOT NULL CHECK(origin IN ('tool','human')),
                        request_id TEXT NOT NULL, operation_kind TEXT NOT NULL, payload_hash TEXT NOT NULL,
                        world_id TEXT NOT NULL, base_version INTEGER, result_version INTEGER NOT NULL,
                        outcome_json TEXT NOT NULL, created_at TEXT NOT NULL,
                        PRIMARY KEY(project_id,origin,request_id),
                        FOREIGN KEY(world_id,result_version) REFERENCES world_revisions(world_id,version)
                    );
                    PRAGMA user_version=1;
                    COMMIT;
                """)
            if str(connection.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
                raise VoxelError("CORRUPT_STATE", "The voxel store failed its integrity check.", 409)
            required = {"worlds", "world_revisions", "chunk_versions", "operation_receipts"}
            actual = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required <= actual or connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise VoxelError("CORRUPT_STATE", "The voxel store has missing or inconsistent durable records.", 409)

    @staticmethod
    def _metadata(document: WorldDocument) -> str:
        encoded = canonical(document.model_dump(mode="json"))
        if len(encoded.encode("utf-8")) > MAX_METADATA_BYTES:
            raise VoxelError("METADATA_TOO_LARGE", "Voxel metadata may occupy at most 64 KiB.")
        return encoded

    def _index(self, connection: sqlite3.Connection, world_id: str, version: int, document: WorldDocument) -> dict[ChunkKey, ChunkRecord]:
        rows = connection.execute("""
            SELECT c.layer_id,c.cx,c.cy,c.cz,c.version,c.raw_hash,c.nonzero_count
            FROM chunk_versions c JOIN (
                SELECT layer_id,cx,cy,cz,MAX(version) AS version FROM chunk_versions
                WHERE world_id=? AND version<=? GROUP BY layer_id,cx,cy,cz
            ) latest ON c.layer_id=latest.layer_id AND c.cx=latest.cx AND c.cy=latest.cy
                AND c.cz=latest.cz AND c.version=latest.version
            WHERE c.world_id=?
        """, (world_id, version, world_id)).fetchall()
        layers = {layer.id for layer in document.layers}
        result: dict[ChunkKey, ChunkRecord] = {}
        for row in rows:
            key = (str(row["layer_id"]), int(row["cx"]), int(row["cy"]), int(row["cz"]))
            if key[0] not in layers:
                continue
            count = int(row["nonzero_count"])
            if count:
                if any(c < 0 or c * 16 >= size for c, size in zip(key[1:], document.size)) or not 1 <= count <= CHUNK_BYTES:
                    raise VoxelError("CORRUPT_STATE", "A voxel chunk index is invalid.", 409)
                result[key] = ChunkRecord(int(row["version"]), str(row["raw_hash"]), count)
        if len(result) > MAX_LIVE_CHUNKS:
            raise VoxelError("CORRUPT_STATE", "The voxel world exceeds its stored chunk budget.", 409)
        return result

    def _snapshot(self, connection: sqlite3.Connection, project_id: str, world_id: str, version: int | None = None) -> WorldSnapshot:
        if version is None:
            head = connection.execute("""SELECT w.head_version,
                (SELECT MAX(r.version) FROM world_revisions r WHERE r.world_id=w.id) AS latest
                FROM worlds w WHERE w.project_id=? AND w.id=?""", (project_id, world_id)).fetchone()
            if head is None:
                raise VoxelError("WORLD_NOT_FOUND", "The requested voxel world is unavailable in this Project.", 404)
            if type(head["head_version"]) is not int or head["head_version"] < 1 or head["head_version"] != head["latest"]:
                raise VoxelError("CORRUPT_STATE", "The voxel world head does not match its durable history.", 409)
            version = head["head_version"]
        row = connection.execute("""
            SELECT r.*,w.project_id FROM worlds w JOIN world_revisions r ON r.world_id=w.id
            WHERE w.project_id=? AND w.id=? AND r.version=?
        """, (project_id, world_id, version)).fetchone()
        if row is None:
            raise VoxelError("WORLD_NOT_FOUND", "The requested voxel world revision is unavailable in this Project.", 404)
        try:
            document = WorldDocument.model_validate_json(str(row["document_json"]))
            self._metadata(document)
        except ValueError as exc:
            raise VoxelError("CORRUPT_STATE", "The voxel world metadata is invalid.", 409) from exc
        resolved_version = row["version"]
        if type(resolved_version) is not int or resolved_version < 1:
            raise VoxelError("CORRUPT_STATE", "The voxel revision version is invalid.", 409)
        parent_version = row["parent_version"]
        if ((resolved_version == 1 and parent_version is not None)
                or (resolved_version > 1 and (type(parent_version) is not int
                    or parent_version != resolved_version - 1
                    or connection.execute("SELECT 1 FROM world_revisions WHERE world_id=? AND version=?",
                        (world_id, parent_version)).fetchone() is None))):
            raise VoxelError("CORRUPT_STATE", "The voxel revision has an invalid or missing parent.", 409)
        chunks = self._index(connection, world_id, resolved_version, document)
        stored_hash = str(row["content_hash"])
        if fingerprint(document, chunks) != stored_hash:
            raise VoxelError("CORRUPT_STATE", "The voxel revision fingerprint does not match its stored content.", 409)
        snapshot = WorldSnapshot(world_id, str(row["project_id"]), resolved_version, parent_version, stored_hash, document, chunks)
        # The revision fingerprint binds raw hashes, not derived index counts.
        # Validate those counts against the same bounded decoder used for chunk
        # reads before publishing a snapshot to summaries, context, or mutations.
        for key in chunks:
            self._raw(connection, snapshot, key)
        return snapshot

    def snapshot(self, project_id: str, world_id: str, version: int | None = None) -> WorldSnapshot:
        with self._connect() as connection:
            return self._snapshot(connection, project_id, world_id, version)

    @staticmethod
    def summary(snapshot: WorldSnapshot) -> WorldSummary:
        doc = snapshot.document
        return WorldSummary(world_id=snapshot.world_id, project_id=snapshot.project_id,
            version=snapshot.version, parent_version=snapshot.parent_version, title=doc.title,
            status=doc.status, size=doc.size, content_hash=snapshot.content_hash,
            chunk_count=len(snapshot.chunks), nonzero_count=sum(c.nonzero_count for c in snapshot.chunks.values()),
            layer_count=len(doc.layers), palette_count=len(doc.palette), region_count=len(doc.regions))

    def get(self, project_id: str, input: ReadInput) -> WorldOutput:
        snapshot = self.snapshot(project_id, input.world_id, input.version)
        return WorldOutput(**self.summary(snapshot).model_dump(), document=snapshot.document)

    def list_worlds(self, project_id: str, input: ListInput) -> WorldListOutput:
        with self._connect() as connection:
            rows = connection.execute("""SELECT w.id,r.document_json FROM worlds w JOIN world_revisions r
                ON r.world_id=w.id AND r.version=w.head_version WHERE w.project_id=? AND w.id>?
                ORDER BY w.id""", (project_id, input.after or "")).fetchall()
            worlds: list[WorldSummary] = []
            has_next = False
            for row in rows:
                try:
                    document = WorldDocument.model_validate_json(str(row["document_json"]))
                except ValueError as exc:
                    raise VoxelError("CORRUPT_STATE", "A voxel world has invalid metadata.", 409) from exc
                if not input.include_deleted and document.status == "deleted":
                    continue
                if len(worlds) == input.limit:
                    has_next = True
                    break
                worlds.append(self.summary(self._snapshot(connection, project_id, str(row["id"]))))
        return WorldListOutput(worlds=worlds, next_after=worlds[-1].world_id if has_next else None)

    def list_resources(self, project_id: str) -> tuple[ProjectResourceDescriptor, ...]:
        worlds = self.list_worlds(project_id, ListInput(limit=128))
        return (ProjectResourceDescriptor(kind=LIBRARY_KIND, id=project_id, version=1, name="Voxel worlds"),
            *(ProjectResourceDescriptor(kind=WORLD_KIND, id=w.world_id, version=w.version, name=w.title) for w in worlds.worlds))

    @staticmethod
    def resolve_library(ref: ResourceScopeRef) -> Library:
        if ref.kind != LIBRARY_KIND or str(ref.version) != "1":
            raise VoxelError("INVALID_RESOURCE", "The voxel library reference is invalid.", 409)
        return Library(str(ref.id))

    def resolve_world(self, ref: ResourceScopeRef) -> WorldSnapshot:
        if ref.kind != WORLD_KIND or ref.version is None or isinstance(ref.version, bool):
            raise VoxelError("INVALID_RESOURCE", "An immutable voxel world version is required.", 409)
        try:
            version = int(ref.version)
        except (ValueError, TypeError) as exc:
            raise VoxelError("INVALID_RESOURCE", "The voxel resource version is invalid.", 409) from exc
        if str(version) != str(ref.version) or version < 1:
            raise VoxelError("INVALID_RESOURCE", "The voxel resource version is invalid.", 409)
        with self._connect() as connection:
            row = connection.execute("SELECT project_id FROM worlds WHERE id=?", (str(ref.id),)).fetchone()
            if row is None:
                raise VoxelError("WORLD_NOT_FOUND", "The voxel resource is unavailable.", 404)
            # Reconciliation resolves historical scopes before querying an exact receipt.
            return self._snapshot(connection, str(row[0]), str(ref.id), version)

    def _receipt(self, connection: sqlite3.Connection, project_id: str, origin: str, request_id: str, kind: str, hashed: str, input: CreateInput | WriteInput) -> MutationOutput | None:
        row = connection.execute("SELECT operation_kind,payload_hash,world_id,base_version,result_version,outcome_json FROM operation_receipts WHERE project_id=? AND origin=? AND request_id=?", (project_id, origin, request_id)).fetchone()
        if row is None:
            return None
        if str(row["operation_kind"]) != kind or str(row["payload_hash"]) != hashed:
            raise VoxelError("INVOCATION_CONFLICT", "The request identity was already used with different voxel input.", 409)
        try:
            output = MutationOutput.model_validate_json(str(row["outcome_json"]), strict=True)
            base_version, result_version = row["base_version"], row["result_version"]
            if (type(result_version) is not int or result_version < 1
                    or output.project_id != project_id or output.world_id != row["world_id"]
                    or output.version != result_version or output.operation_kind != kind):
                raise ValueError("Receipt identity mismatch")
            if isinstance(input, CreateInput):
                if kind != "create" or base_version is not None or result_version != 1 or not output.changed:
                    raise ValueError("Invalid create receipt")
            elif (type(base_version) is not int or base_version != input.expected_version
                    or output.world_id != input.world_id
                    or result_version != base_version + int(output.changed)):
                raise ValueError("Receipt version mismatch")
            snapshot = self._snapshot(connection, project_id, output.world_id, result_version)
            summary = self.summary(snapshot).model_dump(mode="json")
            if any(output.model_dump(mode="json")[key] != value for key, value in summary.items()):
                raise ValueError("Receipt differs from its immutable revision")
            if output.changed and not isinstance(input, CreateInput) and snapshot.parent_version != base_version:
                raise ValueError("Receipt parent mismatch")
            if output.changed_chunk_count < 0 or output.changed_voxel_count < 0:
                raise ValueError("Negative receipt change counts")
            if (not output.changed or isinstance(input, CreateInput)) and (output.changed_chunk_count or output.changed_voxel_count):
                raise ValueError("Unexpected receipt change counts")
            if output.changed:
                # Each new revision has exactly one producing receipt. No-op
                # receipts at that revision have base_version == result_version.
                # A receipt must not adopt a later request's valid revision.
                producers = connection.execute("""SELECT project_id,origin,request_id FROM operation_receipts
                    WHERE world_id=? AND result_version=?
                    AND (base_version IS NULL OR base_version=result_version-1)""",
                    (output.world_id, result_version)).fetchall()
                if len(producers) != 1 or tuple(producers[0]) != (project_id, origin, request_id):
                    raise ValueError("Receipt does not uniquely produce its revision")
                revision = connection.execute("SELECT operation_kind FROM world_revisions WHERE world_id=? AND version=?",
                    (output.world_id, result_version)).fetchone()
                changed_chunks = connection.execute("SELECT layer_id,cx,cy,cz FROM chunk_versions WHERE world_id=? AND version=?",
                    (output.world_id, result_version)).fetchall()
                if revision is None or revision[0] != kind or len(changed_chunks) != output.changed_chunk_count:
                    raise ValueError("Receipt differs from its durable changes")
                if not isinstance(input, CreateInput):
                    before = self._snapshot(connection, project_id, output.world_id, base_version)
                    changed_voxels = 0
                    for chunk in changed_chunks:
                        key = (str(chunk[0]), int(chunk[1]), int(chunk[2]), int(chunk[3]))
                        changed_voxels += sum(a != b for a, b in zip(self._raw(connection, before, key), self._raw(connection, snapshot, key)))
                    if changed_voxels != output.changed_voxel_count:
                        raise ValueError("Receipt voxel count differs from its durable changes")
            return output
        except ValueError as exc:
            raise VoxelError("CORRUPT_STATE", "The stored voxel operation receipt is invalid.", 409) from exc

    def receipt(self, project_id: str, origin: Literal["tool", "human"], request_id: str, kind: str, input: CreateInput | WriteInput) -> MutationOutput | None:
        with self._connect() as connection:
            return self._receipt(connection, project_id, origin, request_id, kind, payload_hash(kind, input), input)

    @staticmethod
    def _quota(connection: sqlite3.Connection, extra: int) -> None:
        used = int(connection.execute("""SELECT
            (SELECT COALESCE(SUM(length(CAST(document_json AS BLOB))+256),0) FROM world_revisions) +
            (SELECT COALESCE(SUM(COALESCE(length(blob),0)+192),0) FROM chunk_versions) +
            (SELECT COALESCE(SUM(length(CAST(outcome_json AS BLOB))+384),0) FROM operation_receipts)
        """).fetchone()[0])
        if used + extra > MAX_HISTORY_BYTES:
            raise VoxelError("HISTORY_QUOTA_EXCEEDED", "The voxel owner history budget is full. Existing worlds and snapshots remain readable.", 409)

    @staticmethod
    def _write_receipt(connection: sqlite3.Connection, project_id: str, origin: str, request_id: str, kind: str, hashed: str, output: MutationOutput, base_version: int | None) -> None:
        connection.execute("INSERT INTO operation_receipts VALUES (?,?,?,?,?,?,?,?,?,?)", (project_id, origin, request_id, kind, hashed, output.world_id, base_version, output.version, canonical(output.model_dump(mode="json")), now()))

    @staticmethod
    def _identity(project_id: str, request_id: str) -> None:
        if not project_id or not 1 <= len(request_id) <= 256:
            raise VoxelError("INVALID_REQUEST_ID", "A Project and a stable mutation identity are required.")

    def create(self, project_id: str, input: CreateInput, *, origin: Literal["tool", "human"], request_id: str, cancelled: Callable[[], bool] = never_cancelled) -> MutationOutput:
        self._identity(project_id, request_id)
        hashed = payload_hash("create", input)
        document = WorldDocument(size=input.size, title=input.title)
        encoded = self._metadata(document)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = self._receipt(connection, project_id, origin, request_id, "create", hashed, input)
            if previous is not None:
                return previous
            count = int(connection.execute("""SELECT COUNT(*) FROM worlds w JOIN world_revisions r ON
                r.world_id=w.id AND r.version=w.head_version WHERE w.project_id=? AND json_extract(r.document_json,'$.status')='active'""", (project_id,)).fetchone()[0])
            if count >= 128:
                raise VoxelError("WORLD_LIMIT", "A Project may have at most 128 active voxel worlds.", 409)
            world_id = "world_" + uuid4().hex
            snapshot = WorldSnapshot(world_id, project_id, 1, None, fingerprint(document, {}), document, {})
            output = MutationOutput(**self.summary(snapshot).model_dump(), changed=True, changed_chunk_count=0, changed_voxel_count=0, operation_kind="create")
            self._quota(connection, len(encoded.encode("utf-8")) + len(canonical(output.model_dump()).encode("utf-8")) + 1024)
            check_cancel(cancelled)
            created = now()
            connection.execute("INSERT INTO worlds VALUES (?,?,1,?)", (world_id, project_id, created))
            connection.execute("INSERT INTO world_revisions VALUES (?,1,NULL,'create',NULL,?,?,?)", (world_id, encoded, snapshot.content_hash, created))
            self._write_receipt(connection, project_id, origin, request_id, "create", hashed, output, None)
            check_cancel(cancelled)
            connection.commit()
            return output

    def _raw(self, connection: sqlite3.Connection, snapshot: WorldSnapshot, key: ChunkKey) -> bytes:
        record = snapshot.chunks.get(key)
        if record is None:
            return EMPTY_CHUNK
        row = connection.execute("SELECT blob FROM chunk_versions WHERE world_id=? AND layer_id=? AND cx=? AND cy=? AND cz=? AND version=?", (snapshot.world_id, *key, record.version)).fetchone()
        if row is None or row[0] is None:
            raise VoxelError("CORRUPT_STATE", "A voxel chunk payload is missing.", 409)
        blob = bytes(row[0])
        if len(blob) > CHUNK_BYTES + 64:
            raise VoxelError("CORRUPT_STATE", "A voxel chunk exceeds its encoded size limit.", 409)
        try:
            decoder = zlib.decompressobj()
            raw = decoder.decompress(blob, CHUNK_BYTES + 1)
        except zlib.error as exc:
            raise VoxelError("CORRUPT_STATE", "A voxel chunk cannot be decompressed.", 409) from exc
        if len(raw) != CHUNK_BYTES or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise VoxelError("CORRUPT_STATE", "A voxel chunk has an invalid decoded length or stream.", 409)
        if digest(raw) != record.raw_hash or CHUNK_BYTES - raw.count(0) != record.nonzero_count:
            raise VoxelError("CORRUPT_STATE", "A voxel chunk failed its content integrity check.", 409)
        allowed = {p.index for p in snapshot.document.palette}
        if not set(raw) <= allowed:
            raise VoxelError("CORRUPT_STATE", "A voxel chunk references an undefined palette index.", 409)
        _, cx, cy, cz = key
        size = snapshot.document.size
        if any((c + 1) * 16 > n for c, n in zip(key[1:], size)):
            for offset, value in enumerate(raw):
                if value and (cx * 16 + offset % 16 >= size[0] or cy * 16 + offset // 256 >= size[1] or cz * 16 + (offset // 16) % 16 >= size[2]):
                    raise VoxelError("CORRUPT_STATE", "A voxel chunk contains nonempty padding outside the world.", 409)
        return raw

    def read_chunk(self, snapshot: WorldSnapshot, key: ChunkKey) -> bytes:
        with self._connect() as connection:
            return self._raw(connection, snapshot, key)

    def _configured(self, connection: sqlite3.Connection, source: WorldSnapshot, input: ConfigureInput, cancelled: Callable[[], bool]) -> WorldDocument:
        data = source.document.model_dump(mode="json")
        op = input.operation
        if isinstance(op, Rename):
            data["title"] = op.title
        elif isinstance(op, PalettePut):
            if op.entry.index == 0:
                raise VoxelError("AIR_IS_FIXED", "Palette slot zero cannot be edited.")
            data["palette"] = [p.model_dump() for p in source.document.palette if p.index != op.entry.index] + [op.entry.model_dump()]
            data["palette"] = sorted(data["palette"], key=lambda p: p["index"])
        elif isinstance(op, PaletteRemove):
            if op.index == 0:
                raise VoxelError("AIR_IS_FIXED", "Palette slot zero cannot be removed.")
            if not any(p.index == op.index for p in source.document.palette):
                raise VoxelError("PALETTE_NOT_FOUND", "The palette index does not exist.", 404)
            for key in source.chunks:
                check_cancel(cancelled)
                if op.index in self._raw(connection, source, key):
                    raise VoxelError("PALETTE_IN_USE", "Replace voxels using this palette index before removing it.", 409)
            data["palette"] = [p.model_dump() for p in source.document.palette if p.index != op.index]
        elif isinstance(op, LayerPut):
            layers = list(source.document.layers)
            index = next((i for i, layer in enumerate(layers) if layer.id == op.layer.id), None)
            if index is None:
                # Reusing an old ID could reveal its historical chunks without a geometry operation.
                historical = connection.execute("SELECT 1 FROM chunk_versions WHERE world_id=? AND layer_id=? LIMIT 1", (source.world_id, op.layer.id)).fetchone()
                if historical is not None:
                    raise VoxelError("LAYER_ID_RETIRED", "Use a new ID for a newly added layer; restore history to recover a removed layer.", 409)
                layers.append(op.layer)
            else:
                layers[index] = op.layer
            data["layers"] = [layer.model_dump() for layer in layers]
        elif isinstance(op, LayerRemove):
            layer_exists(source.document, op.layer_id, writable=True)
            if len(source.document.layers) == 1:
                raise VoxelError("LAST_LAYER", "A voxel world must retain at least one layer.")
            data["layers"] = [layer.model_dump() for layer in source.document.layers if layer.id != op.layer_id]
        elif isinstance(op, LayerOrder):
            by_id = {layer.id: layer for layer in source.document.layers}
            if len(op.layer_ids) != len(by_id) or set(op.layer_ids) != set(by_id):
                raise VoxelError("INVALID_LAYER_ORDER", "Layer order must contain every current layer exactly once.")
            data["layers"] = [by_id[layer_id].model_dump() for layer_id in op.layer_ids]
        elif isinstance(op, RegionPut):
            data["regions"] = [r.model_dump() for r in source.document.regions if r.id != op.region.id] + [op.region.model_dump()]
        elif isinstance(op, RegionRemove):
            if not any(r.id == op.region_id for r in source.document.regions):
                raise VoxelError("REGION_NOT_FOUND", "The named region does not exist.", 404)
            data["regions"] = [r.model_dump() for r in source.document.regions if r.id != op.region_id]
        elif isinstance(op, MetadataSet):
            data["metadata"] = op.metadata.model_dump()
        document = WorldDocument.model_validate(data)
        self._metadata(document)
        return document

    def mutate(self, project_id: str, input: ApplyInput | ConfigureInput | UndoInput | WriteInput, *, kind: str, origin: Literal["tool", "human"], request_id: str, frozen_version: int | None = None, cancelled: Callable[[], bool] = never_cancelled) -> MutationOutput:
        self._identity(project_id, request_id)
        hashed = payload_hash(kind, input)
        with self._connect() as connection:
            previous = self._receipt(connection, project_id, origin, request_id, kind, hashed, input)
            if previous is not None:
                return previous
            if origin == "tool" and frozen_version != input.expected_version:
                raise VoxelError("STALE_VERSION", "The expected version differs from this invocation's frozen voxel resource.", 409)
            source = self._snapshot(connection, project_id, input.world_id)
            self._fence(source, input.expected_version, allow_deleted=isinstance(input, UndoInput))
            check_cancel(cancelled)
            document = source.document
            changes: dict[ChunkKey, bytes] = {}
            changed_voxels = 0
            restored_from: int | None = None
            if isinstance(input, ApplyInput):
                delta = apply_geometry(document, input.operation, lambda key: self._raw(connection, source, key), cancelled)
                changes, changed_voxels = delta.chunks, delta.changed_voxel_count
            elif isinstance(input, ConfigureInput):
                document = self._configured(connection, source, input, cancelled)
                active = {layer.id for layer in document.layers}
                for key in source.chunks:
                    if key[0] not in active:
                        changes[key] = EMPTY_CHUNK
                        changed_voxels += source.chunks[key].nonzero_count
            elif isinstance(input, UndoInput):
                if input.target_version > source.version:
                    raise VoxelError("INVALID_UNDO_TARGET", "Undo can only restore an existing earlier revision.")
                target = self._snapshot(connection, project_id, source.world_id, input.target_version)
                document, restored_from = target.document, target.version
                for key in source.chunks.keys() | target.chunks.keys():
                    check_cancel(cancelled)
                    a, b = source.chunks.get(key), target.chunks.get(key)
                    if (a.raw_hash if a else None) != (b.raw_hash if b else None):
                        before, after = self._raw(connection, source, key), self._raw(connection, target, key)
                        changes[key] = after
                        changed_voxels += sum(x != y for x, y in zip(before, after))
            elif kind == "delete":
                document = WorldDocument.model_validate({**source.document.model_dump(), "status": "deleted"})
            else:
                raise VoxelError("INVALID_OPERATION", "The voxel mutation type is unsupported.")
            encoded = self._metadata(document)
            changed = bool(changes) or encoded != self._metadata(source.document)
            version = source.version + 1 if changed else source.version
            index = dict(source.chunks)
            active_layers = {layer.id for layer in document.layers}
            index = {key: record for key, record in index.items() if key[0] in active_layers}
            encoded_chunks: list[tuple[ChunkKey, str, int, bytes | None]] = []
            for key, raw in changes.items():
                check_cancel(cancelled)
                raw_hash = digest(raw)
                nonzero = CHUNK_BYTES - raw.count(0)
                blob = zlib.compress(raw, level=1) if nonzero else None
                encoded_chunks.append((key, raw_hash, nonzero, blob))
                if nonzero and key[0] in active_layers:
                    index[key] = ChunkRecord(version, raw_hash, nonzero)
                else:
                    index.pop(key, None)
            if len(index) > MAX_LIVE_CHUNKS:
                raise VoxelError("CHUNK_LIMIT", "A world may have at most 8,192 nonempty layer chunks.", 409)
            result = WorldSnapshot(source.world_id, project_id, version, source.version if changed else source.parent_version,
                fingerprint(document, index) if changed else source.content_hash, document, index)
            output = MutationOutput(**self.summary(result).model_dump(), changed=changed, changed_chunk_count=len(changes), changed_voxel_count=changed_voxels, operation_kind=kind)
            connection.execute("BEGIN IMMEDIATE")
            previous = self._receipt(connection, project_id, origin, request_id, kind, hashed, input)
            if previous is not None:
                return previous
            current = self._snapshot(connection, project_id, source.world_id)
            self._fence(current, input.expected_version, allow_deleted=isinstance(input, UndoInput))
            if source.document.status == "deleted" and document.status == "active":
                active_count = int(connection.execute("""SELECT COUNT(*) FROM worlds w JOIN world_revisions r ON r.world_id=w.id AND r.version=w.head_version
                    WHERE w.project_id=? AND json_extract(r.document_json,'$.status')='active'""", (project_id,)).fetchone()[0])
                if active_count >= 128:
                    raise VoxelError("WORLD_LIMIT", "Restoring this world would exceed the Project's active-world limit.", 409)
            extra = len(canonical(output.model_dump()).encode("utf-8")) + 384
            if changed:
                extra += len(encoded.encode("utf-8")) + 256 + sum(len(blob or b"") + 192 for _, _, _, blob in encoded_chunks)
            self._quota(connection, extra)
            check_cancel(cancelled)
            if changed:
                connection.execute("INSERT INTO world_revisions VALUES (?,?,?,?,?,?,?,?)", (source.world_id, version, source.version, kind, restored_from, encoded, result.content_hash, now()))
                connection.executemany("INSERT INTO chunk_versions VALUES (?,?,?,?,?,?,?,?,?)", [(source.world_id, *key, version, hashed_raw, count, blob) for key, hashed_raw, count, blob in encoded_chunks])
                updated = connection.execute("UPDATE worlds SET head_version=? WHERE id=? AND project_id=? AND head_version=?", (version, source.world_id, project_id, source.version))
                if updated.rowcount != 1:
                    raise VoxelError("STALE_VERSION", "The voxel world changed concurrently; inspect before another edit.", 409)
            self._write_receipt(connection, project_id, origin, request_id, kind, hashed, output, source.version)
            check_cancel(cancelled)
            connection.commit()
            return output

    @staticmethod
    def _fence(snapshot: WorldSnapshot, expected: int, *, allow_deleted: bool = False) -> None:
        if snapshot.version != expected:
            raise VoxelError("STALE_VERSION", "The voxel world changed; inspect the current version before editing.", 409)
        if snapshot.document.status == "deleted" and not allow_deleted:
            raise VoxelError("WORLD_DELETED", "The voxel world is deleted; restore it before editing.", 409)

    def inspect(self, project_id: str, input: InspectInput, cancelled: Callable[[], bool] = never_cancelled) -> InspectOutput:
        with self._connect() as connection:
            snapshot = self._snapshot(connection, project_id, input.world_id, input.version)
            selected: int | None = None
            if input.layer_id is not None:
                layer_exists(snapshot.document, input.layer_id)
            if input.bounds is not None:
                validate_bounds(input.bounds, snapshot.document)
                canvas = Canvas(lambda key: self._raw(connection, snapshot, key), cancelled)
                selected = 0
                layers = [input.layer_id] if input.layer_id else [layer.id for layer in reversed(snapshot.document.layers)]
                for cell in positions(input.bounds):
                    canvas.tick()
                    selected += any(canvas.get(layer_id, cell) for layer_id in layers)
            start, stop = input.object_offset, input.object_offset + input.object_limit
            maximum = max(len(snapshot.document.layers), len(snapshot.document.palette), len(snapshot.document.regions))
            while True:
                output = InspectOutput(**self.summary(snapshot).model_dump(), layers=snapshot.document.layers[start:stop], palette=snapshot.document.palette[start:stop],
                    regions=snapshot.document.regions[start:stop], object_offset=start, next_object_offset=stop if stop < maximum else None,
                    truncated=stop < maximum, selected_nonzero_count=selected)
                if len(canonical(output.model_dump(mode="json")).encode("utf-8")) <= 12_000:
                    return output
                stop -= 1

    @staticmethod
    def _cursor(world_id: str, version: int, since: int | None, key: ChunkKey) -> str:
        raw = canonical([world_id, version, since, *key]).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii")

    @staticmethod
    def _decode_cursor(cursor: str | None, world_id: str, version: int, since: int | None) -> ChunkKey | None:
        if cursor is None:
            return None
        try:
            value = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
            if not isinstance(value, list) or len(value) != 7 or value[:3] != [world_id, version, since]:
                raise ValueError("cursor scope")
            if not isinstance(value[3], str) or any(type(n) is not int or not 0 <= n <= 15 for n in value[4:]):
                raise ValueError("cursor coordinate")
            return value[3], value[4], value[5], value[6]
        except (ValueError, TypeError, UnicodeError) as exc:
            raise VoxelError("INVALID_CURSOR", "The chunk cursor is invalid or belongs to another snapshot.") from exc

    def chunks(self, project_id: str, input: ChunkPageInput) -> ChunkPageOutput:
        with self._connect() as connection:
            target = self._snapshot(connection, project_id, input.world_id, input.version)
            after = self._decode_cursor(input.after, input.world_id, input.version, input.since_version)
            metadata_changed = False
            if input.since_version is not None:
                if input.since_version > input.version:
                    raise VoxelError("INVALID_VERSION_RANGE", "The starting version must not exceed the target version.")
                source = self._snapshot(connection, project_id, input.world_id, input.since_version)
                metadata_changed = self._metadata(source.document) != self._metadata(target.document)
                keys = [key for key in source.chunks.keys() | target.chunks.keys() if source.chunks.get(key) != target.chunks.get(key)]
            else:
                keys = list(target.chunks)
            keys = sorted(key for key in keys if after is None or key > after)
            selected = keys[:input.limit]
            result = [ChunkData(layer_id=key[0], coord=list(key[1:]), hash=target.chunks[key].raw_hash if key in target.chunks else digest(EMPTY_CHUNK),
                values=list(self._raw(connection, target, key)) if key in target.chunks else None) for key in selected]
            cursor = self._cursor(input.world_id, input.version, input.since_version, selected[-1]) if len(keys) > input.limit else None
            return ChunkPageOutput(world_id=input.world_id, version=input.version, since_version=input.since_version, chunks=result, next_after=cursor, metadata_changed=metadata_changed)

    def revisions(self, project_id: str, input: RevisionsInput) -> RevisionsOutput:
        with self._connect() as connection:
            self._snapshot(connection, project_id, input.world_id)
            rows = connection.execute("SELECT version,parent_version,operation_kind,restored_from_version,content_hash,created_at FROM world_revisions WHERE world_id=? AND version<? ORDER BY version DESC LIMIT ?", (input.world_id, input.before_version or 9_223_372_036_854_775_807, input.limit + 1)).fetchall()
            revisions = [RevisionSummary.model_validate(dict(row)) for row in rows[:input.limit]]
            return RevisionsOutput(world_id=input.world_id, revisions=revisions, next_before_version=revisions[-1].version if len(rows) > input.limit else None)

    def diff(self, project_id: str, input: DiffInput) -> DiffOutput:
        with self._connect() as connection:
            a = self._snapshot(connection, project_id, input.world_id, input.from_version)
            b = self._snapshot(connection, project_id, input.world_id, input.to_version)
            after = self._decode_cursor(input.after, input.world_id, input.to_version, input.from_version)
            keys = sorted(key for key in a.chunks.keys() | b.chunks.keys() if (a.chunks[key].raw_hash if key in a.chunks else None) != (b.chunks[key].raw_hash if key in b.chunks else None))
            remaining = [key for key in keys if after is None or key > after]
            selected = remaining[:input.limit]
            while True:
                chunks = [ChunkDifference(layer_id=key[0], coord=list(key[1:]), before_hash=a.chunks[key].raw_hash if key in a.chunks else None, after_hash=b.chunks[key].raw_hash if key in b.chunks else None) for key in selected]
                cursor = self._cursor(input.world_id, input.to_version, input.from_version, selected[-1]) if len(remaining) > len(selected) else None
                output = DiffOutput(world_id=input.world_id, from_version=input.from_version, to_version=input.to_version, metadata_changed=self._metadata(a.document) != self._metadata(b.document),
                    changed_chunk_count=len(keys), chunks=chunks, next_after=cursor, truncated=cursor is not None)
                if len(canonical(output.model_dump(mode="json")).encode("utf-8")) <= 12_000:
                    return output
                selected.pop()
