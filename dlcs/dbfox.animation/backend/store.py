"""Owner-local SQLite revisions, atomic CAS and durable invocation receipts."""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from dbfox_dlc_api import ProjectResourceDescriptor, ResourceScopeRef
from .contracts import (Document, Summary, Revision, MutationResult, ListResult, PageResult, DiffResult,
    Library, SECTIONS, MAX_BYTES, LIBRARY_KIND, DOCUMENT_KIND, Target)
from .model import AnimationError, apply, differences


def canonical(value):
    return json.dumps(value.model_dump(mode="json") if hasattr(value, "model_dump") else value,
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return sha256(value.encode("utf-8")).hexdigest()


class AnimationStore:
    def __init__(self, root: Path):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "animation.sqlite3"
        with self.connect() as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
                raise AnimationError("SCHEMA_VERSION", "Animation data was created by an unsupported version.")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, head INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions(id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL, content_hash TEXT NOT NULL, document TEXT NOT NULL,
                    status TEXT NOT NULL, operation TEXT NOT NULL, PRIMARY KEY(id,version));
                CREATE TABLE IF NOT EXISTS entity_ids(id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    entity_id TEXT NOT NULL, PRIMARY KEY(id,entity_id));
                CREATE TABLE IF NOT EXISTS receipts(invocation TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
                    id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE, result TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS project_documents ON documents(project_id);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
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
    def check_cancel(cancelled):
        if cancelled and cancelled():
            raise AnimationError("CANCELLED", "Animation operation was cancelled before commit.")

    def _revision(self, connection, project_id, identity, version=None):
        row = connection.execute("SELECT d.project_id,d.head,r.* FROM documents d JOIN revisions r ON d.id=r.id "
            "WHERE d.id=? AND d.project_id=? AND r.version=COALESCE(?,d.head)", (identity, project_id, version)).fetchone()
        if row is None:
            raise AnimationError("NOT_FOUND", "Animation revision is unavailable in this Project.")
        try:
            if len(row["document"].encode("utf-8")) > MAX_BYTES or digest(row["document"]) != row["content_hash"]:
                raise ValueError("hash mismatch")
            document = Document.model_validate_json(row["document"])
            if canonical(document) != row["document"] or row["version"] < 1 or row["version"] > row["head"]:
                raise ValueError("invalid revision")
            summary = Summary(id=identity, project_id=project_id, title=document.title, version=row["version"],
                content_hash=row["content_hash"], status=row["status"], counts={section: len(getattr(document, section)) for section in SECTIONS})
            return Revision(animation=summary, document=document)
        except ValueError as exc:
            raise AnimationError("CORRUPT", "Animation revision failed integrity validation.") from exc

    def get(self, project_id, identity, version=None):
        with self.connect() as connection:
            return self._revision(connection, project_id, identity, version)

    @staticmethod
    def fence(revision, expected, frozen=None):
        if revision.animation.status != "active":
            raise AnimationError("DELETED", "Animation is deleted; historical exports remain readable.")
        if revision.animation.version != expected or (frozen is not None and frozen != expected):
            raise AnimationError("STALE", "Animation changed. Inspect again and reconsider this edit.")

    def require_live(self, project_id, identity, expected, frozen=None):
        self.fence(self.get(project_id, identity), expected, frozen)

    def _receipt(self, connection, project_id, invocation, request_hash):
        row = connection.execute("SELECT * FROM receipts WHERE invocation=?", (invocation,)).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise AnimationError("RECEIPT_MISMATCH", "Invocation ID was already used for a different request.")
        try:
            result = MutationResult.model_validate_json(row["result"])
            if row["id"] != result.animation.id or result.animation.project_id != project_id:
                raise ValueError("receipt identity mismatch")
            fixed = self._revision(connection, project_id, row["id"], result.animation.version)
            if fixed.animation != result.animation:
                raise ValueError("receipt revision mismatch")
            return result
        except ValueError as exc:
            raise AnimationError("CORRUPT", "Animation receipt failed integrity validation.") from exc

    @staticmethod
    def request_hash(project_id, action, payload):
        return digest(canonical({"project_id": project_id, "action": action, "input": payload.model_dump(mode="json")}))

    def reconcile(self, project_id, action, payload, invocation):
        with self.connect() as connection:
            return self._receipt(connection, project_id, invocation, self.request_hash(project_id, action, payload))

    @staticmethod
    def _save(connection, identity, version, document, status, payload):
        encoded = canonical(document)
        if len(encoded.encode("utf-8")) > MAX_BYTES:
            raise AnimationError("LIMIT", "Animation document exceeds 16 MiB.")
        connection.execute("INSERT INTO revisions VALUES(?,?,?,?,?,?)", (identity, version, digest(encoded), encoded, status, canonical(payload)))

    def create(self, project_id, payload, invocation, cancelled=None):
        if not project_id or not invocation:
            raise AnimationError("INVALID", "Project and invocation are required.")
        request_hash = self.request_hash(project_id, "create", payload)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            receipt = self._receipt(connection, project_id, invocation, request_hash)
            if receipt:
                return receipt
            self.check_cancel(cancelled)
            if connection.execute("SELECT COUNT(*) FROM documents WHERE project_id=?", (project_id,)).fetchone()[0] >= 1000:
                raise AnimationError("LIMIT", "Project supports at most 1000 Animation documents including history.")
            identity = uuid4().hex
            document = Document(title=payload.title)
            connection.execute("INSERT INTO documents VALUES(?,?,1)", (identity, project_id))
            self._save(connection, identity, 1, document, "active", payload)
            result = MutationResult(animation=self._revision(connection, project_id, identity).animation, changed=True)
            connection.execute("INSERT INTO receipts VALUES(?,?,?,?)", (invocation, request_hash, identity, canonical(result)))
            self.check_cancel(cancelled)
            connection.commit()
            return result

    def mutate(self, project_id, action, payload, invocation, frozen=None, cancelled=None, bound_targets=None):
        request_hash = self.request_hash(project_id, action, payload)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            receipt = self._receipt(connection, project_id, invocation, request_hash)
            if receipt:
                return receipt
            self.check_cancel(cancelled)
            identity = payload.animation_id
            source = self._revision(connection, project_id, identity)
            self.fence(source, payload.expected_version, frozen)
            status = "active"
            if action == "apply":
                document = apply(source.document, payload.operation)
            elif action == "undo":
                if payload.target_version > payload.expected_version:
                    raise AnimationError("INVALID", "Undo target must be an existing earlier revision.")
                document = self._revision(connection, project_id, identity, payload.target_version).document
            elif action == "delete":
                document, status = source.document, "deleted"
            elif action == "bind" and bound_targets is not None:
                data = source.document.model_dump(mode="json")
                data["targets"].extend(Target.model_validate(target).model_dump(mode="json") for target in bound_targets)
                data["targets"].sort(key=lambda target: target["id"])
                document = Document.model_validate(data)
            else:
                raise AnimationError("INVALID", "Unknown Animation operation.")
            changed = source.document != document or source.animation.status != status
            delta = differences(source.document, document)
            if changed:
                old_ids = {item.id for section in SECTIONS for item in getattr(source.document, section)}
                new_ids = {item.id for section in SECTIONS for item in getattr(document, section)}
                for entity_id in new_ids - old_ids:
                    try:
                        connection.execute("INSERT INTO entity_ids VALUES(?,?)", (identity, entity_id))
                    except sqlite3.IntegrityError as exc:
                        if action != "undo":
                            raise AnimationError("ID_REUSED", "Deleted entity IDs cannot be reused.") from exc
                version = payload.expected_version + 1
                self._save(connection, identity, version, document, status, payload)
                updated = connection.execute("UPDATE documents SET head=? WHERE id=? AND project_id=? AND head=?",
                    (version, identity, project_id, payload.expected_version))
                if updated.rowcount != 1:
                    raise AnimationError("STALE", "Animation changed concurrently.")
            result = MutationResult(animation=self._revision(connection, project_id, identity).animation,
                changed=changed, changed_ids=[item.id for item in delta[:100]], truncated=len(delta) > 100)
            connection.execute("INSERT INTO receipts VALUES(?,?,?,?)", (invocation, request_hash, identity, canonical(result)))
            self.check_cancel(cancelled)
            connection.commit()
            return result

    def list(self, project_id, request):
        with self.connect() as connection:
            connection.execute("BEGIN")
            ids = connection.execute("SELECT d.id FROM documents d JOIN revisions r ON d.id=r.id AND d.head=r.version "
                "WHERE d.project_id=? AND r.status='active' ORDER BY d.id", (project_id,)).fetchall()
            return ListResult(animations=[self._revision(connection, project_id, row[0]).animation for row in ids[request.offset:request.offset + request.limit]], total=len(ids))

    def page(self, project_id, request):
        revision = self.get(project_id, request.animation_id, request.version)
        if request.version is None and revision.animation.status != "active":
            raise AnimationError("DELETED", "Animation is deleted.")
        items = getattr(revision.document, request.section)
        if request.track_id:
            if request.section != "keyframes" or request.track_id not in {track.id for track in revision.document.tracks}:
                raise AnimationError("REFERENCE", "Keyframe filtering requires an existing track.")
            items = sorted((key for key in items if key.track_id == request.track_id), key=lambda key: (key.tick, key.id))
        page = items[request.offset:request.offset + request.limit]
        # Page count and bytes are independently bounded, including long Unicode names.
        while page and len(canonical([item.model_dump(mode="json") for item in page]).encode("utf-8")) > 120000:
            page.pop()
        end = request.offset + len(page)
        return PageResult(animation=revision.animation, timing=revision.document.timing, section=request.section,
            items=page, offset=request.offset, total=len(items), next_offset=end, has_more=end < len(items))

    def diff(self, project_id, request):
        delta = differences(self.get(project_id, request.animation_id, request.from_version).document,
                            self.get(project_id, request.animation_id, request.to_version).document)
        page = delta[request.offset:request.offset + request.limit]
        end = request.offset + len(page)
        return DiffResult(differences=page, total=len(delta), next_offset=end, has_more=end < len(delta))

    def list_resources(self, project_id):
        with self.connect() as connection:
            rows = connection.execute("SELECT d.id,d.head,r.document FROM documents d JOIN revisions r ON d.id=r.id AND d.head=r.version "
                "WHERE d.project_id=? AND r.status='active' ORDER BY d.id", (project_id,)).fetchall()
        return (ProjectResourceDescriptor(kind=LIBRARY_KIND, id=project_id, version=1, name="Animation Library"),
            *(ProjectResourceDescriptor(kind=DOCUMENT_KIND, id=row["id"], version=row["head"],
                name=Document.model_validate_json(row["document"]).title) for row in rows))

    def resolve_library(self, ref: ResourceScopeRef):
        if ref.kind != LIBRARY_KIND or ref.version != 1:
            raise AnimationError("REFERENCE", "Invalid frozen Animation Library.")
        return Library(project_id=ref.id)

    def resolve_document(self, ref: ResourceScopeRef):
        if ref.kind != DOCUMENT_KIND or type(ref.version) is not int or ref.version < 1:
            raise AnimationError("REFERENCE", "Animation requires an integer frozen version.")
        with self.connect() as connection:
            row = connection.execute("SELECT project_id FROM documents WHERE id=?", (ref.id,)).fetchone()
            if row is None:
                raise AnimationError("NOT_FOUND", "Animation does not exist.")
            return self._revision(connection, row[0], ref.id, ref.version)

    def delete_project(self, project_id):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM documents WHERE project_id=?", (project_id,))
            connection.commit()
