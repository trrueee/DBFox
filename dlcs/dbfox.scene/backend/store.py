"""SQLite is the only durable Scene authority; writes share one transaction path."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from dbfox_dlc_api import BaseModel, ProjectResourceDescriptor, ResourceScopeRef

from .contracts import (
    AssignMaterial, Camera, CreateCamera, CreateLight, CreateMaterial, CreateObjects,
    DeleteObjects, Difference, DiffInput, DiffResult, DuplicateObjects,
    InspectInput, Library, Light, ListResult, Mesh, MutationResult,
    Operation, PageInput, PageResult, ReparentObjects, Revision,
    SceneDocument, SceneSummary, TransformObjects, UpdateCamera, UpdateLight, UpdateMaterial, UpdateObject,
    UpdateSettings, LIBRARY_KIND, MAX_BATCH, MAX_DOCUMENT_BYTES, SCENE_KIND,
)


class SceneError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def canonical(model: BaseModel, *, exclude_unset: bool = False) -> str:
    return json.dumps(model.model_dump(mode="json", exclude_unset=exclude_unset), ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def differences(before: SceneDocument, after: SceneDocument) -> list[Difference]:
    result: list[Difference] = []
    for entity, old_items, new_items in (
        ("object", before.objects, after.objects),
        ("material", before.materials, after.materials),
    ):
        old = {item.id: item.model_dump(mode="json") for item in old_items}
        new = {item.id: item.model_dump(mode="json") for item in new_items}
        for key in sorted(old.keys() | new.keys()):
            if key not in old:
                result.append(Difference(id=key, entity=entity, change="added", fields=[]))
            elif key not in new:
                result.append(Difference(id=key, entity=entity, change="deleted", fields=[]))
            elif old[key] != new[key]:
                fields = sorted(name for name in old[key].keys() | new[key].keys()
                                if old[key].get(name) != new[key].get(name))
                result.append(Difference(id=key, entity=entity, change="modified", fields=fields))
    for field in ("settings", "title"):
        if getattr(before, field) != getattr(after, field):
            result.append(Difference(id=field, entity=field, change="modified", fields=[field]))
    return result


def _selected(document: SceneDocument, ids: list[str], subtree: bool = False) -> set[str]:
    selected = set(ids)
    nodes = {node.id: node for node in document.objects}
    if len(selected) != len(ids) or not selected <= nodes.keys():
        raise SceneError("SCENE_INVALID_REFERENCE", "Object selection is duplicate or missing.")
    if subtree:
        # At most 64 passes: document validation bounds hierarchy depth.
        for _ in range(64):
            additions = {node.id for node in document.objects if node.parent_id in selected} - selected
            if not additions:
                break
            selected.update(additions)
    if len(selected) > MAX_BATCH:
        raise SceneError("SCENE_LIMIT", "This operation exceeds 500 selected objects.")
    return selected


def apply_operation(document: SceneDocument, operation: Operation) -> SceneDocument:
    nodes = {item.id: item for item in document.objects}
    materials = {item.id: item for item in document.materials}
    settings = document.settings
    title = document.title
    if isinstance(operation, (CreateObjects, CreateLight, CreateCamera)):
        additions = (operation.objects if isinstance(operation, CreateObjects) else
                     [operation.light] if isinstance(operation, CreateLight) else [operation.camera])
        for node in additions:
            if node.id in nodes:
                raise SceneError("SCENE_INVALID_REFERENCE", "Object ID already exists.")
            nodes[node.id] = node
    elif isinstance(operation, TransformObjects):
        _selected(document, [item.object_id for item in operation.transforms])
        for change in operation.transforms:
            fields = change.model_dump(exclude_none=True, exclude={"object_id"})
            nodes[change.object_id] = nodes[change.object_id].model_copy(update=fields)
    elif isinstance(operation, DuplicateObjects):
        selected = _selected(document, operation.object_ids, operation.include_subtree)
        replacements = {key: uuid4().hex for key in sorted(selected)}
        for node in document.objects:
            if node.id not in selected:
                continue
            root = node.parent_id not in selected
            position = tuple(a + b for a, b in zip(node.position, operation.offset)) if root else node.position
            nodes[replacements[node.id]] = node.model_copy(update={
                "id": replacements[node.id], "name": (node.name[:115] + " Copy"),
                "parent_id": replacements.get(node.parent_id, node.parent_id) if node.parent_id else None,
                "position": position,
            })
    elif isinstance(operation, DeleteObjects):
        selected = _selected(document, operation.object_ids, operation.include_subtree)
        if any(node.parent_id in selected and node.id not in selected for node in document.objects):
            raise SceneError("SCENE_HAS_CHILDREN", "Select subtree deletion or reparent children first.")
        nodes = {key: node for key, node in nodes.items() if key not in selected}
        if settings.default_camera_id in selected:
            settings = settings.model_copy(update={"default_camera_id": None})
    elif isinstance(operation, ReparentObjects):
        selected = _selected(document, operation.object_ids)
        for key in selected:
            nodes[key] = nodes[key].model_copy(update={"parent_id": operation.parent_id})
    elif isinstance(operation, UpdateObject):
        _selected(document, [operation.object_id])
        fields = operation.model_dump(exclude_none=True, exclude={"kind", "object_id"})
        if not fields:
            raise SceneError("SCENE_INVALID", "Object update requires name or visibility.")
        nodes[operation.object_id] = nodes[operation.object_id].model_copy(update=fields)
    elif isinstance(operation, (UpdateLight, UpdateCamera)):
        is_light = isinstance(operation, UpdateLight)
        key = operation.light_id if is_light else operation.camera_id
        expected_type = Light if is_light else Camera
        if not isinstance(nodes.get(key), expected_type):
            raise SceneError("SCENE_INVALID_REFERENCE", "Light or camera does not exist in this scene.")
        fields = operation.model_dump(exclude_unset=True, exclude={"kind", "light_id", "camera_id", "clear_range"})
        if is_light and operation.clear_range:
            fields["range"] = None
        nodes[key] = nodes[key].model_copy(update=fields)
    elif isinstance(operation, (CreateMaterial, UpdateMaterial)):
        exists = operation.material.id in materials
        if exists != isinstance(operation, UpdateMaterial):
            raise SceneError("SCENE_INVALID_REFERENCE", "Material ID does not match the requested operation.")
        materials[operation.material.id] = operation.material
    elif isinstance(operation, AssignMaterial):
        selected = _selected(document, operation.object_ids)
        if operation.material_id is not None and operation.material_id not in materials:
            raise SceneError("SCENE_INVALID_REFERENCE", "Material does not exist.")
        for key in selected:
            if not isinstance(nodes[key], Mesh):
                raise SceneError("SCENE_INVALID_REFERENCE", "Materials can only be assigned to mesh objects.")
            nodes[key] = nodes[key].model_copy(update={"material_id": operation.material_id})
    elif isinstance(operation, UpdateSettings):
        settings = operation.settings
        title = operation.title if operation.title is not None else title
    else:
        raise SceneError("SCENE_INVALID", "Unsupported scene operation.")
    draft = document.model_copy(update={"title": title, "settings": settings,
                                       "objects": list(nodes.values()), "materials": list(materials.values())})
    try:
        return SceneDocument.model_validate(draft.model_dump(mode="json"))
    except ValueError as exc:
        raise SceneError("SCENE_INVALID", "Operation violates scene limits, references or hierarchy.") from exc


class SceneStore:
    def __init__(self, data_path: Path) -> None:
        data_path.mkdir(parents=True, exist_ok=True)
        self.path = data_path / "state.sqlite3"
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise SceneError("SCENE_SCHEMA_UNSUPPORTED", "Scene database requires a newer DLC.")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS scenes (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, head_version INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('active','deleted')), created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS scenes_project ON scenes(project_id,status);
                CREATE TABLE IF NOT EXISTS scene_revisions (
                    scene_id TEXT NOT NULL REFERENCES scenes(id), version INTEGER NOT NULL,
                    parent_version INTEGER, content_hash TEXT NOT NULL, document_json TEXT NOT NULL,
                    title TEXT NOT NULL, object_count INTEGER NOT NULL, material_count INTEGER NOT NULL,
                    status TEXT NOT NULL, operation_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(scene_id,version)
                );
                CREATE TABLE IF NOT EXISTS operation_receipts (
                    invocation_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL REFERENCES scenes(id), input_hash TEXT NOT NULL,
                    version INTEGER NOT NULL, result_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS entity_ids (
                    scene_id TEXT NOT NULL REFERENCES scenes(id), id TEXT NOT NULL,
                    PRIMARY KEY(scene_id,id)
                );
                PRAGMA user_version=1;
                COMMIT;
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        try:
            yield connection
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    @staticmethod
    def _query() -> str:
        return ("SELECT r.*,s.project_id,s.created_at AS scene_created_at,"
                "s.head_version AS scene_head_version,s.status AS scene_status,"
                "(SELECT MAX(v.version) FROM scene_revisions v WHERE v.scene_id=s.id) AS stored_head_version,"
                "h.status AS head_status,p.version AS existing_parent_version "
                "FROM scene_revisions r JOIN scenes s ON s.id=r.scene_id "
                "LEFT JOIN scene_revisions h ON h.scene_id=s.id AND h.version=s.head_version "
                "LEFT JOIN scene_revisions p ON p.scene_id=r.scene_id AND p.version=r.parent_version ")

    @staticmethod
    def _summary(row: sqlite3.Row) -> SceneSummary:
        return SceneSummary(id=row["scene_id"], project_id=row["project_id"], title=row["title"],
            version=row["version"], content_hash=row["content_hash"], status=row["status"],
            object_count=row["object_count"], material_count=row["material_count"],
            created_at=row["scene_created_at"], updated_at=row["created_at"])

    @classmethod
    def _revision_from_row(cls, row: sqlite3.Row) -> Revision:
        try:
            encoded = row["document_json"]
            if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > MAX_DOCUMENT_BYTES:
                raise ValueError("invalid stored document size")
            document = SceneDocument.model_validate_json(encoded)
            version, head = row["version"], row["scene_head_version"]
            if (type(version) is not int or type(head) is not int or not 1 <= version <= head or
                    head != row["stored_head_version"]):
                raise ValueError("invalid revision identity")
            parent = row["parent_version"]
            if (version == 1 and parent is not None) or (version > 1 and
                    (type(parent) is not int or parent != version - 1 or row["existing_parent_version"] != parent)):
                raise ValueError("invalid revision parent")
            if (row["status"] not in ("active", "deleted") or
                    row["scene_status"] not in ("active", "deleted") or
                    row["head_status"] != row["scene_status"] or
                    (version == head and row["status"] != row["scene_status"]) or
                    (row["status"] == "deleted" and version != head)):
                raise ValueError("invalid revision lifecycle")
            if (row["title"] != document.title or type(row["object_count"]) is not int or
                    row["object_count"] != len(document.objects) or type(row["material_count"]) is not int or
                    row["material_count"] != len(document.materials)):
                raise ValueError("stored summary differs from canonical document")
            if digest(canonical(document)) != row["content_hash"]:
                raise ValueError("hash mismatch")
            return Revision(scene=cls._summary(row), parent_version=parent, document=document)
        except (TypeError, ValueError) as exc:
            raise SceneError("SCENE_CORRUPT", "Stored scene failed integrity validation.") from exc

    def _revision(self, connection: sqlite3.Connection, project_id: str, scene_id: str,
                  version: int | None = None) -> Revision:
        where = "WHERE s.id=? AND s.project_id=? AND "
        values: tuple[str | int, ...] = (scene_id, project_id)
        if version is None:
            where += "r.version=s.head_version"
        else:
            where += "r.version=?"
            values += (version,)
        row = connection.execute(self._query() + where, values).fetchone()
        if row is None:
            scene = connection.execute("SELECT head_version FROM scenes WHERE id=? AND project_id=?",
                                       (scene_id, project_id)).fetchone()
            if scene is not None and (version is None or version == scene["head_version"]):
                raise SceneError("SCENE_CORRUPT", "Stored scene failed integrity validation.")
            raise SceneError("SCENE_NOT_FOUND", "Scene revision does not exist in this Project.")
        return self._revision_from_row(row)

    def get_revision(self, project_id: str, scene_id: str, version: int | None = None) -> Revision:
        with self._connect() as connection:
            return self._revision(connection, project_id, scene_id, version)

    def require_live(self, project_id: str, scene_id: str, expected: int,
                     frozen_version: int | str | None = None) -> Revision:
        current = self.get_revision(project_id, scene_id)
        self._fence(current, expected, frozen_version)
        return current

    @staticmethod
    def _fence(current: Revision, expected: int, frozen: int | str | None) -> None:
        if current.scene.status != "active":
            raise SceneError("SCENE_DELETED", "This scene has been deleted.")
        if current.scene.version != expected or (frozen is not None and frozen != expected):
            raise SceneError("SCENE_STALE", "Scene version changed. Inspect again before editing.")

    @staticmethod
    def _check_cancel(cancelled: Callable[[], bool] | None) -> None:
        if cancelled is not None and cancelled():
            raise SceneError("SCENE_CANCELLED", "Scene operation was cancelled before commit.")

    @staticmethod
    def _request_hash(project_id: str, action: str, payload: BaseModel) -> str:
        return digest(project_id + "\n" + action + "\n" + canonical(payload, exclude_unset=True))

    def _receipt(self, connection: sqlite3.Connection, invocation_id: str,
                 request_hash: str) -> MutationResult | None:
        row = connection.execute("SELECT * FROM operation_receipts WHERE invocation_id=?",
                                 (invocation_id,)).fetchone()
        if row is None:
            return None
        if row["input_hash"] != request_hash:
            raise SceneError("SCENE_RECEIPT_MISMATCH", "Invocation ID was already used for different input.")
        try:
            result = MutationResult.model_validate_json(row["result_json"])
            if (row["owner_id"] != "dbfox.scene" or result.scene.id != row["scene_id"] or
                    result.scene.project_id != row["project_id"] or result.scene.version != row["version"]):
                raise ValueError("receipt identity mismatch")
            revision = self._revision(connection, row["project_id"], row["scene_id"], row["version"])
            if revision.scene != result.scene:
                raise ValueError("receipt revision mismatch")
            return result
        except ValueError as exc:
            raise SceneError("SCENE_CORRUPT", "Stored operation receipt is invalid.") from exc

    def reconcile(self, project_id: str, action: str, payload: BaseModel,
                  invocation_id: str) -> MutationResult | None:
        with self._connect() as connection:
            return self._receipt(connection, invocation_id, self._request_hash(project_id, action, payload))

    @staticmethod
    def _save_receipt(connection: sqlite3.Connection, invocation_id: str, request_hash: str,
                      result: MutationResult) -> None:
        connection.execute("INSERT INTO operation_receipts VALUES (?,?,?,?,?,?,?)",
            (invocation_id, "dbfox.scene", result.scene.project_id, result.scene.id,
             request_hash, result.scene.version, canonical(result)))

    @staticmethod
    def _save_revision(connection: sqlite3.Connection, scene_id: str, version: int,
                       document: SceneDocument, operation: str, status: str) -> None:
        encoded = canonical(document)
        if len(encoded.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise SceneError("SCENE_LIMIT", "Scene document exceeds 8 MiB.")
        connection.execute("INSERT INTO scene_revisions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (scene_id, version, version - 1 if version > 1 else None, digest(encoded), encoded,
             document.title, len(document.objects), len(document.materials), status, operation, _now()))

    def create(self, project_id: str, payload: BaseModel, title: str, invocation_id: str,
               cancelled: Callable[[], bool] | None = None) -> MutationResult:
        if not project_id or not invocation_id:
            raise SceneError("SCENE_INVALID", "Project and invocation identity are required.")
        request_hash = self._request_hash(project_id, "create", payload)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._receipt(connection, invocation_id, request_hash)
            if existing:
                return existing
            self._check_cancel(cancelled)
            count = connection.execute("SELECT COUNT(*) FROM scenes WHERE project_id=? AND status='active'",
                                       (project_id,)).fetchone()[0]
            if count >= 1000:
                raise SceneError("SCENE_LIMIT", "Project exceeds 1000 active scenes.")
            scene_id = uuid4().hex
            document = SceneDocument(title=title)
            connection.execute("INSERT INTO scenes VALUES (?,?,1,'active',?)", (scene_id, project_id, _now()))
            self._save_revision(connection, scene_id, 1, document, canonical(payload, exclude_unset=True), "active")
            connection.executemany("INSERT INTO entity_ids VALUES (?,?)", [(scene_id, g.id) for g in document.geometries])
            result = MutationResult(scene=self._revision(connection, project_id, scene_id).scene, changed=True)
            self._save_receipt(connection, invocation_id, request_hash, result)
            self._check_cancel(cancelled)
            connection.commit()
            return result

    def mutate(self, project_id: str, scene_id: str, expected: int, action: str, payload: BaseModel,
               invocation_id: str, *, operation: Operation | None = None, target_version: int | None = None,
               frozen_version: int | str | None = None, cancelled: Callable[[], bool] | None = None) -> MutationResult:
        if not invocation_id:
            raise SceneError("SCENE_INVALID", "Invocation identity is required.")
        request_hash = self._request_hash(project_id, action, payload)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._receipt(connection, invocation_id, request_hash)
            if existing:
                return existing
            self._check_cancel(cancelled)
            source = self._revision(connection, project_id, scene_id)
            self._fence(source, expected, frozen_version)
            status = "active"
            if action == "apply" and operation is not None:
                document = apply_operation(source.document, operation)
            elif action == "undo" and target_version is not None:
                if target_version > expected:
                    raise SceneError("SCENE_INVALID", "Undo target must be an existing earlier revision.")
                document = self._revision(connection, project_id, scene_id, target_version).document
            elif action == "delete":
                document = source.document
                status = "deleted"
            else:
                raise SceneError("SCENE_INVALID", "Unknown scene mutation.")
            changed = document != source.document or status != source.scene.status
            delta = differences(source.document, document)
            if changed:
                old_ids = {item.id for item in [*source.document.objects, *source.document.materials]}
                for item in [*document.objects, *document.materials]:
                    if item.id in old_ids:
                        continue
                    try:
                        connection.execute("INSERT INTO entity_ids VALUES (?,?)", (scene_id, item.id))
                    except sqlite3.IntegrityError as exc:
                        if action != "undo":
                            raise SceneError("SCENE_ID_REUSED", "A deleted entity ID cannot be reused.") from exc
                version = expected + 1
                self._save_revision(connection, scene_id, version, document, canonical(payload, exclude_unset=True), status)
                cursor = connection.execute("UPDATE scenes SET head_version=?,status=? WHERE id=? AND project_id=? AND head_version=?",
                                            (version, status, scene_id, project_id, expected))
                if cursor.rowcount != 1:
                    raise SceneError("SCENE_STALE", "Scene changed concurrently.")
            result = MutationResult(scene=self._revision(connection, project_id, scene_id).scene, changed=changed,
                changed_ids=[item.id for item in delta[:100]], truncated=len(delta) > 100)
            self._save_receipt(connection, invocation_id, request_hash, result)
            self._check_cancel(cancelled)
            connection.commit()
            return result

    def list_scenes(self, project_id: str, request: PageInput) -> ListResult:
        with self._connect() as connection:
            connection.execute("BEGIN")
            total = connection.execute("SELECT COUNT(*) FROM scenes WHERE project_id=? AND status='active'", (project_id,)).fetchone()[0]
            rows = connection.execute(self._query() +
                "WHERE s.project_id=? AND s.status='active' AND r.version=s.head_version ORDER BY s.created_at,s.id LIMIT ? OFFSET ?",
                (project_id, request.limit, request.offset)).fetchall()
            return ListResult(scenes=[self._revision_from_row(row).scene for row in rows], total=total, offset=request.offset, limit=request.limit)

    def page(self, project_id: str, request: InspectInput) -> PageResult:
        revision = self.get_revision(project_id, request.scene_id, request.version)
        if request.version is None and revision.scene.status != "active":
            raise SceneError("SCENE_DELETED", "This scene has been deleted.")
        items = getattr(revision.document, request.section)
        values = {"scene": revision.scene, "settings": revision.document.settings,
                  "total": len(items), "offset": request.offset, "limit": request.limit,
                  request.section: items[request.offset:request.offset + request.limit]}
        return PageResult.model_validate(values)

    def diff(self, project_id: str, request: DiffInput) -> DiffResult:
        before = self.get_revision(project_id, request.scene_id, request.from_version)
        after = self.get_revision(project_id, request.scene_id, request.to_version)
        delta = differences(before.document, after.document)
        return DiffResult(scene_id=request.scene_id, from_version=request.from_version, to_version=request.to_version,
            differences=delta[request.offset:request.offset + request.limit], total=len(delta), offset=request.offset, limit=request.limit)

    def list_resources(self, project_id: str) -> tuple[ProjectResourceDescriptor, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT s.id,s.head_version,r.title FROM scenes s JOIN scene_revisions r ON "
                "s.id=r.scene_id AND s.head_version=r.version WHERE s.project_id=? AND s.status='active' ORDER BY s.id", (project_id,)).fetchall()
        return (ProjectResourceDescriptor(kind=LIBRARY_KIND, id=project_id, version=1, name="Scene Library"),
                *(ProjectResourceDescriptor(kind=SCENE_KIND, id=row["id"], version=row["head_version"], name=row["title"]) for row in rows))

    def resolve_library(self, ref: ResourceScopeRef) -> Library:
        if ref.kind != LIBRARY_KIND or ref.version != 1 or not ref.id:
            raise SceneError("SCENE_INVALID_REFERENCE", "Invalid frozen Scene Library reference.")
        return Library(project_id=ref.id)

    def resolve_scene(self, ref: ResourceScopeRef) -> Revision:
        if ref.kind != SCENE_KIND or type(ref.version) is not int or ref.version < 1:
            raise SceneError("SCENE_INVALID_REFERENCE", "Scene requires an integer frozen revision.")
        with self._connect() as connection:
            row = connection.execute("SELECT project_id FROM scenes WHERE id=?", (ref.id,)).fetchone()
            if row is None:
                raise SceneError("SCENE_NOT_FOUND", "Scene resource does not exist.")
            # Reconciliation must resolve the immutable input revision after a successful write.
            return self._revision(connection, row["project_id"], ref.id, ref.version)
