"""Owner SQLite facts: atomic revisions, receipts, immutable compute evidence."""
from __future__ import annotations

import base64
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import sqlite3
from uuid import uuid4

from dbfox_dlc_api import ProjectResourceDescriptor, ResourceScopeRef

from . import contracts as c
from .mutations import apply_operations, dedicated_operations, new_document


class ShaderError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def content_hash(document: c.Document, deleted: bool) -> str:
    return sha256(c.encoded({"document": document.model_dump(mode="json"), "deleted": deleted})).hexdigest()


def input_hash(action: str, data: c.Input, frozen_generation: int | None) -> str:
    return sha256(c.encoded({"action": action, "input": data.model_dump(mode="json", exclude_none=True), "frozen_generation": frozen_generation})).hexdigest()


def check_cancelled(cancelled: Callable[[], bool]) -> None:
    if cancelled():
        raise ShaderError("SHADER_CANCELLED", "Shader request was cancelled.")


def not_cancelled() -> bool:
    return False


class Store:
    def __init__(self, data_path: Path, *, history_limit: int = c.MAX_HISTORY) -> None:
        self.path = data_path / "state.sqlite3"
        self.history_limit = history_limit
        data_path.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ShaderError("SHADER_CORRUPT", "Unversioned Shader state cannot be adopted.")
                statements = (
                    "CREATE TABLE quota (id INTEGER PRIMARY KEY CHECK(id=1), payload_bytes INTEGER NOT NULL CHECK(payload_bytes>=0))",
                    "INSERT INTO quota VALUES (1,0)",
                    "CREATE TABLE studios (project TEXT PRIMARY KEY, generation INTEGER NOT NULL)",
                    "CREATE TABLE heads (id TEXT PRIMARY KEY, project TEXT NOT NULL, version INTEGER NOT NULL)",
                    "CREATE TABLE identities (id TEXT PRIMARY KEY, document_id TEXT NOT NULL)",
                    "CREATE TABLE revisions (id TEXT NOT NULL, version INTEGER NOT NULL, project TEXT NOT NULL, generation INTEGER NOT NULL, hash TEXT NOT NULL, deleted INTEGER NOT NULL CHECK(deleted IN (0,1)), payload BLOB NOT NULL, PRIMARY KEY(id,version), UNIQUE(project,generation))",
                    "CREATE INDEX revision_project ON revisions(project,id,generation)",
                    "CREATE TABLE textures (hash TEXT PRIMARY KEY, payload BLOB NOT NULL)",
                    "CREATE TABLE receipts (project TEXT NOT NULL, actor TEXT NOT NULL, request_id TEXT NOT NULL, input_hash TEXT NOT NULL, kind TEXT NOT NULL, hash TEXT NOT NULL, payload BLOB NOT NULL, PRIMARY KEY(project,actor,request_id))",
                    "CREATE TABLE reports (id TEXT PRIMARY KEY, project TEXT NOT NULL, document_id TEXT NOT NULL, version INTEGER NOT NULL, hash TEXT NOT NULL, payload BLOB NOT NULL, pixels BLOB NOT NULL)",
                    "CREATE INDEX report_document ON reports(project,document_id,version)",
                    "PRAGMA user_version=1",
                )
                for statement in statements:
                    db.execute(statement)
            elif version != 1:
                raise ShaderError("SHADER_SCHEMA_UNSUPPORTED", "Unsupported Shader state schema.")
            self.audit(db)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        except sqlite3.Error as exc:
            raise ShaderError("SHADER_STATE_UNAVAILABLE", "Shader state is unavailable or inconsistent.") from exc
        finally:
            db.close()

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            self.audit(db)
            yield db

    def audit(self, db: sqlite3.Connection) -> None:
        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ShaderError("SHADER_SCHEMA_UNSUPPORTED", "Unsupported Shader state schema.")
        broken = db.execute("SELECT 1 FROM heads h LEFT JOIN revisions r ON r.id=h.id AND r.version=h.version AND r.project=h.project WHERE r.id IS NULL OR h.version!=(SELECT count(*) FROM revisions x WHERE x.id=h.id) OR h.version!=(SELECT max(version) FROM revisions x WHERE x.id=h.id) LIMIT 1").fetchone()
        missing = db.execute("SELECT 1 FROM revisions r LEFT JOIN heads h ON h.id=r.id AND h.project=r.project LEFT JOIN studios s ON s.project=r.project WHERE h.id IS NULL OR s.project IS NULL LIMIT 1").fetchone()
        generation = db.execute("SELECT 1 FROM studios s WHERE s.generation!=(SELECT count(*) FROM revisions r WHERE r.project=s.project) OR s.generation!=(SELECT max(generation) FROM revisions r WHERE r.project=s.project) LIMIT 1").fetchone()
        if broken or missing or generation:
            raise ShaderError("SHADER_CORRUPT", "Shader head/history generations are inconsistent.")
        total = 0
        for table, maximum in (("revisions", c.MAX_DOCUMENT), ("textures", 1_048_576), ("receipts", c.MAX_RECEIPT), ("reports", c.MAX_REPORT)):
            if db.execute(f"SELECT 1 FROM {table} WHERE typeof(payload)!='blob' LIMIT 1").fetchone():
                raise ShaderError("SHADER_CORRUPT", "Shader payload storage type is invalid.")
            row = db.execute(f"SELECT coalesce(sum(length(payload)),0),coalesce(max(length(payload)),0),coalesce(min(length(payload)),1) FROM {table}").fetchone()
            if row[1] > maximum or row[2] < 1:
                raise ShaderError("SHADER_CORRUPT", "Stored Shader payload exceeds its contract.")
            total += row[0]
        row = db.execute("SELECT coalesce(sum(length(pixels)),0),coalesce(max(length(pixels)),0) FROM reports").fetchone()
        if row[1] > 262_144 or db.execute("SELECT 1 FROM reports WHERE typeof(pixels)!='blob' LIMIT 1").fetchone():
            raise ShaderError("SHADER_CORRUPT", "Stored preview exceeds its contract.")
        total += row[0]
        quota = db.execute("SELECT payload_bytes FROM quota WHERE id=1").fetchone()
        if quota is None or type(quota[0]) is not int or quota[0] != total or total > c.MAX_HISTORY:
            raise ShaderError("SHADER_CORRUPT", "Shader history accounting is inconsistent.")

    def charge(self, db: sqlite3.Connection, amount: int) -> None:
        total = db.execute("SELECT payload_bytes FROM quota WHERE id=1").fetchone()[0]
        if amount < 0 or total + amount > self.history_limit:
            raise ShaderError("SHADER_HISTORY_FULL", "Shader history payload quota is full; existing revisions remain readable.")
        db.execute("UPDATE quota SET payload_bytes=payload_bytes+? WHERE id=1", (amount,))

    @staticmethod
    def generation(db: sqlite3.Connection, project: str) -> int:
        row = db.execute("SELECT generation FROM studios WHERE project=?", (project,)).fetchone()
        if row is None:
            return 0
        value = row[0]
        if type(value) is not int or not 1 <= value <= 2**53-1:
            raise ShaderError("SHADER_CORRUPT", "Invalid studio generation.")
        return value

    def check_generation(self, db: sqlite3.Connection, project: str, generation: int | None, *, live: bool) -> int:
        current = self.generation(db, project)
        if generation is not None and (type(generation) is not int or generation < 0 or generation > current or (live and generation != current)):
            raise ShaderError("STALE_VERSION", "Shader studio generation changed; inspect current state before editing.")
        return current if generation is None else generation

    def list_resources(self, project_id: str) -> tuple[ProjectResourceDescriptor, ...]:
        with self.transaction() as db:
            generation = self.generation(db, project_id)
        return (ProjectResourceDescriptor(kind=c.STUDIO_KIND, id=project_id, version=generation, name="Shader Studio", is_default=True),)

    def resolve(self, ref: ResourceScopeRef) -> c.Studio:
        if ref.kind != c.STUDIO_KIND or type(ref.version) is not int:
            raise ShaderError("SHADER_SCOPE", "An exact Shader Studio generation is required.")
        with self.transaction() as db:
            self.check_generation(db, ref.id, ref.version, live=False)
        return c.Studio(project_id=ref.id, generation=ref.version)

    def read_revision(self, db: sqlite3.Connection, project: str, document_id: str, version: int | None = None, generation: int | None = None) -> c.Revision:
        frozen = self.check_generation(db, project, generation, live=False)
        query = "SELECT * FROM revisions WHERE project=? AND id=? AND generation<=?"
        params: list[str | int] = [project, document_id, frozen]
        if version is not None:
            query += " AND version=?"
            params.append(version)
        row = db.execute(query + " ORDER BY version DESC LIMIT 1", params).fetchone()
        if row is None:
            raise ShaderError("SHADER_NOT_FOUND", "Document revision is absent from this studio generation.")
        try:
            doc = c.Document.model_validate_json(row["payload"])
            revision = c.Revision(document=doc, version=row["version"], studio_generation=row["generation"], content_hash=row["hash"], deleted=bool(row["deleted"]))
            if doc.id != document_id or row["deleted"] not in (0, 1) or content_hash(doc, revision.deleted) != revision.content_hash:
                raise ValueError("Revision identity/hash mismatch")
            if c.encoded(doc.model_dump(mode="json")) != row["payload"]:
                raise ValueError("Revision is not canonical")
            ids = [doc.id, *[item.id for item in [*doc.stages, *doc.passes, *doc.uniforms, *doc.textures]]]
            count = db.execute("SELECT count(*) FROM identities WHERE document_id=? AND id IN (" + ",".join("?" for _ in ids) + ")", (doc.id, *ids)).fetchone()[0]
            if count != len(ids):
                raise ValueError("Object identity ledger mismatch")
            for texture in doc.textures:
                self.read_texture(db, texture)
            return revision
        except ValueError as exc:
            raise ShaderError("SHADER_CORRUPT", "Stored Shader revision failed validation.") from exc

    @staticmethod
    def read_texture(db: sqlite3.Connection, texture: c.Texture) -> bytes:
        row = db.execute("SELECT payload FROM textures WHERE hash=?", (texture.content_hash,)).fetchone()
        if row is None or not isinstance(row[0], bytes) or len(row[0]) != texture.width * texture.height * 4 or sha256(row[0]).hexdigest() != texture.content_hash:
            raise ShaderError("SHADER_CORRUPT", "Stored texture failed validation.")
        return row[0]

    def head(self, project: str, document_id: str) -> c.HeadResult:
        with self.transaction() as db:
            # Head polling reads the small immutable identity; no source/BLOB materialization.
            row = db.execute("SELECT r.id,r.version,r.hash,r.deleted,r.generation FROM heads h JOIN revisions r ON r.id=h.id AND r.version=h.version WHERE h.project=? AND h.id=? AND r.project=h.project", (project, document_id)).fetchone()
            if row is None:
                raise ShaderError("SHADER_NOT_FOUND", "Shader document does not exist.")
            return c.HeadResult(id=row["id"], version=row["version"], content_hash=row["hash"], deleted=bool(row["deleted"]))

    def get(self, project: str, document_id: str, version: int | None = None, generation: int | None = None) -> c.Revision:
        with self.transaction() as db:
            return self.read_revision(db, project, document_id, version, generation)

    def catalog(self, db: sqlite3.Connection, project: str, generation: int | None = None, *, offset: int = 0, limit: int = 50) -> tuple[list[c.Revision], int]:
        frozen = self.check_generation(db, project, generation, live=False)
        sql = "WITH latest AS (SELECT id,max(version) AS version FROM revisions WHERE project=? AND generation<=? GROUP BY id) SELECT r.id,r.version FROM revisions r JOIN latest l ON l.id=r.id AND l.version=r.version WHERE r.deleted=0"
        count = db.execute("SELECT count(*) FROM (" + sql + ")", (project, frozen)).fetchone()[0]
        rows = db.execute(sql + " ORDER BY r.id LIMIT ? OFFSET ?", (project, frozen, limit, offset)).fetchall()
        results = [self.read_revision(db, project, row["id"], row["version"], frozen) for row in rows]
        return results, count

    def receipt(self, db: sqlite3.Connection, project: str, actor: str, request_id: str, digest: str) -> c.MutationResult | c.ComputeOutcome | None:
        row = db.execute("SELECT * FROM receipts WHERE project=? AND actor=? AND request_id=?", (project, actor, request_id)).fetchone()
        if row is None:
            return None
        if row["input_hash"] != digest:
            raise ShaderError("SHADER_REQUEST_CONFLICT", "Request identity was already used with different input or frozen scope.")
        try:
            if sha256(row["payload"]).hexdigest() != row["hash"]:
                raise ValueError("Receipt hash mismatch")
            if row["kind"] == "mutation":
                return c.MutationResult.model_validate_json(row["payload"])
            if row["kind"] == "compute":
                return c.ComputeOutcome.model_validate_json(row["payload"])
            raise ValueError("Unknown receipt kind")
        except ValueError as exc:
            raise ShaderError("SHADER_CORRUPT", "Stored Shader receipt failed validation.") from exc

    def reconcile(self, project: str, actor: str, request_id: str, action: str, data: c.Input, generation: int | None) -> c.MutationResult | c.ComputeOutcome | None:
        with self.transaction() as db:
            self.check_generation(db, project, generation, live=False)
            return self.receipt(db, project, actor, request_id, input_hash(action, data, generation))

    def save_receipt(self, db: sqlite3.Connection, project: str, actor: str, request_id: str, digest: str, result: c.MutationResult | c.ComputeOutcome) -> None:
        payload = c.encoded(result.model_dump(mode="json", exclude_none=True))
        if len(payload) > c.MAX_RECEIPT:
            raise ShaderError("SHADER_LIMIT", "Shader receipt budget exceeded.")
        self.charge(db, len(payload))
        db.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?,?)", (project, actor, request_id, digest, "mutation" if isinstance(result, c.MutationResult) else "compute", sha256(payload).hexdigest(), payload))

    def mutate(self, project: str, actor: str, request_id: str, action: str, data: c.CreateInput | c.ApplyInput | c.UndoInput | c.VersionInput, *, generation: int | None = None, cancelled: Callable[[], bool] = not_cancelled) -> c.MutationResult:
        if actor not in {"human", "agent"} or not project or not request_id or len(request_id) > 256:
            raise ShaderError("SHADER_SCOPE", "Invalid mutation actor identity.")
        digest = input_hash(action, data, generation)
        with self.transaction(write=True) as db:
            prior = self.receipt(db, project, actor, request_id, digest)
            if prior is not None:
                if not isinstance(prior, c.MutationResult):
                    raise ShaderError("SHADER_CORRUPT", "Receipt kind mismatch.")
                return prior
            check_cancelled(cancelled)
            current_generation = self.check_generation(db, project, generation, live=True)
            refs: dict[str, str] = {}
            blobs: dict[str, bytes] = {}
            generated: list[str] = []
            old: c.Revision | None = None
            deleted = False
            try:
                if action == "create" and isinstance(data, c.CreateInput):
                    if data.expected_generation != current_generation:
                        raise ShaderError("STALE_VERSION", "Shader studio generation changed.")
                    if self.catalog(db, project, limit=0)[1] >= 128:
                        raise ShaderError("SHADER_LIMIT", "Studio already contains 128 active documents.")
                    document, refs = new_document(data.title)
                    generated = [document.id, *refs.values()]
                elif isinstance(data, c.VersionInput):
                    old = self.read_revision(db, project, data.document_id)
                    if old.version != data.expected_version:
                        raise ShaderError("STALE_VERSION", "Shader document changed; inspect before editing.")
                    document = old.document
                    deleted = old.deleted
                    if action == "undo" and isinstance(data, c.UndoInput):
                        target = self.read_revision(db, project, data.document_id, data.target_version)
                        document, deleted = target.document, target.deleted
                        if old.deleted and not deleted and self.catalog(db, project, limit=0)[1] >= 128:
                            raise ShaderError("SHADER_LIMIT", "Studio already contains 128 active documents.")
                    elif action == "delete":
                        deleted = True
                    elif action in {"apply", "uniform_set", "texture_bind", "pass_create"} and isinstance(data, (c.ApplyInput, c.UniformSetInput, c.TextureBindInput, c.PassCreateInput)):
                        if deleted:
                            raise ShaderError("SHADER_DELETED", "Restore a deleted document before editing.")
                        operations = data.operations if isinstance(data, c.ApplyInput) else dedicated_operations(data)
                        document, refs, blobs, generated = apply_operations(document, operations)
                    elif action != "export":
                        raise ValueError("Unsupported mutation")
                else:
                    raise ValueError("Mutation input mismatch")
                digest_content = content_hash(document, deleted)
                changed = old is None or old.content_hash != digest_content
                if action == "export":
                    changed = False
                version = (old.version if old else 0) + int(changed)
                next_generation = current_generation + int(changed)
                # Every generated id is reserved even when removed again in this batch.
                for identity in generated:
                    db.execute("INSERT INTO identities VALUES (?,?)", (identity, document.id))
                for texture_hash, raw in blobs.items():
                    if not db.execute("SELECT 1 FROM textures WHERE hash=?", (texture_hash,)).fetchone():
                        self.charge(db, len(raw))
                        db.execute("INSERT INTO textures VALUES (?,?)", (texture_hash, raw))
                for texture in document.textures:
                    self.read_texture(db, texture)
                if changed:
                    payload = c.encoded(document.model_dump(mode="json"))
                    self.charge(db, len(payload))
                    db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?,?)", (document.id, version, project, next_generation, digest_content, int(deleted), payload))
                    db.execute("INSERT INTO heads VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version", (document.id, project, version))
                    db.execute("INSERT INTO studios VALUES (?,?) ON CONFLICT(project) DO UPDATE SET generation=excluded.generation", (project, next_generation))
                old_items = {} if old is None else {item.id: item.model_dump() for item in [*old.document.stages, *old.document.passes, *old.document.uniforms, *old.document.textures]}
                new_items = {item.id: item.model_dump() for item in [*document.stages, *document.passes, *document.uniforms, *document.textures]}
                changed_ids = sorted(key for key in old_items.keys() | new_items.keys() if old_items.get(key) != new_items.get(key))
                if changed and (old is None or old.document.title != document.title or old.document.preview != document.preview or old.deleted != deleted):
                    changed_ids.append(document.id)
                result = c.MutationResult(document=c.Summary(id=document.id, title=document.title, version=version, content_hash=digest_content, deleted=deleted), studio_generation=next_generation, changed=changed, changed_ids=changed_ids[:64], truncated=len(changed_ids)>64, created_refs=refs)
                if len(c.encoded(result.model_dump(mode="json"))) > 8192:
                    raise ShaderError("SHADER_LIMIT", "Mutation response exceeds its observation budget.")
                check_cancelled(cancelled)
                self.save_receipt(db, project, actor, request_id, digest, result)
                return result
            except ShaderError:
                raise
            except ValueError as exc:
                raise ShaderError("SHADER_INVALID", str(exc)[:480]) from exc

    def compute_snapshot(self, project: str, data: c.VersionInput, generation: int) -> tuple[c.Revision, c.Snapshot]:
        with self.transaction() as db:
            self.check_generation(db, project, generation, live=True)
            revision = self.read_revision(db, project, data.document_id)
            if revision.version != data.expected_version:
                raise ShaderError("STALE_VERSION", "Shader source changed before compute.")
            if revision.deleted:
                raise ShaderError("SHADER_DELETED", "Deleted documents cannot run GPU work.")
            textures = {item.content_hash: item for item in revision.document.textures}
            snapshot = c.Snapshot(document=revision.document, textures=[c.TextureBytes(content_hash=digest, rgba_base64=base64.b64encode(self.read_texture(db, value)).decode("ascii")) for digest, value in textures.items()])
            return revision, snapshot

    def save_report(self, project: str, invocation_id: str, action: str, data: c.VersionInput, generation: int, report: c.Report, pixels: bytes, *, cancelled: Callable[[], bool]) -> c.ComputeOutcome:
        digest = input_hash(action, data, generation)
        with self.transaction(write=True) as db:
            prior = self.receipt(db, project, "agent", invocation_id, digest)
            if prior is not None:
                if not isinstance(prior, c.ComputeOutcome):
                    raise ShaderError("SHADER_CORRUPT", "Receipt kind mismatch.")
                return prior
            check_cancelled(cancelled)
            current = self.read_revision(db, project, data.document_id)
            if current.deleted or current.version != report.version or current.content_hash != report.content_hash or current.version != data.expected_version:
                raise ShaderError("STALE_VERSION", "Shader document changed during GPU computation.")
            if report.document_id != data.document_id or report.kind != action:
                raise ShaderError("SHADER_INVALID", "Compute report identity mismatch.")
            payload = c.encoded(report.model_dump(mode="json", exclude_none=True))
            if len(payload) > c.MAX_REPORT or len(pixels) > 262_144:
                raise ShaderError("SHADER_LIMIT", "Compute evidence budget exceeded.")
            if report.rendered:
                if not report.compiled or report.width != current.document.preview.width or report.height != current.document.preview.height or len(pixels) != report.width * report.height * 4 or sha256(pixels).hexdigest() != report.pixel_hash:
                    raise ShaderError("SHADER_INVALID", "Preview evidence does not match the document.")
            elif pixels or report.pixel_hash is not None:
                raise ShaderError("SHADER_INVALID", "Non-rendered report cannot contain pixels.")
            self.charge(db, len(payload) + len(pixels))
            db.execute("INSERT INTO reports VALUES (?,?,?,?,?,?,?)", (report.id, project, data.document_id, report.version, sha256(payload).hexdigest(), payload, pixels))
            diagnostics = [item.model_copy(update={"message": item.message[:256]}) for item in report.diagnostics[:20]]
            result = c.ComputeOutcome(document=current.summary(), report_id=report.id, compiled=report.compiled, rendered=report.rendered, diagnostics=diagnostics, diagnostic_count=len(report.diagnostics), truncated=len(report.diagnostics)>20 or any(len(item.message)>256 for item in report.diagnostics[:20]))
            # Count/code truncation must fit even when all messages are multibyte.
            while len(c.encoded(result.model_dump(mode="json", exclude_none=True))) > 8192 and result.diagnostics:
                result.diagnostics.pop()
                result.truncated = True
            check_cancelled(cancelled)
            self.save_receipt(db, project, "agent", invocation_id, digest, result)
            return result

    def read_report(self, db: sqlite3.Connection, project: str, report_id: str, generation: int | None = None) -> tuple[c.Report, bytes]:
        row = db.execute("SELECT * FROM reports WHERE project=? AND id=?", (project, report_id)).fetchone()
        if row is None:
            raise ShaderError("SHADER_NOT_FOUND", "Shader report does not exist in this studio.")
        try:
            if sha256(row["payload"]).hexdigest() != row["hash"]:
                raise ValueError("Report hash mismatch")
            report = c.Report.model_validate_json(row["payload"])
            revision = self.read_revision(db, project, report.document_id, report.version, generation)
            if report.id != report_id or report.document_id != row["document_id"] or report.version != row["version"] or report.content_hash != revision.content_hash:
                raise ValueError("Report locator mismatch")
            pixels: bytes = row["pixels"]
            if report.rendered:
                if not report.compiled or report.kind != "preview" or report.width is None or report.height is None or len(pixels) != report.width * report.height * 4 or sha256(pixels).hexdigest() != report.pixel_hash:
                    raise ValueError("Preview hash/layout mismatch")
            elif pixels or report.pixel_hash is not None:
                raise ValueError("Unexpected preview pixels")
            return report, pixels
        except ValueError as exc:
            raise ShaderError("SHADER_CORRUPT", "Stored Shader report failed validation.") from exc

    def report(self, project: str, report_id: str, generation: int | None = None) -> tuple[c.Report, bytes]:
        with self.transaction() as db:
            return self.read_report(db, project, report_id, generation)

    def make_report(self, revision: c.Revision, kind: str, result: c.ComputeResult, capabilities: c.Capabilities, elapsed_ms: int) -> tuple[c.Report, bytes]:
        from .mutations import decode_rgba
        pixels = b""
        pixel_hash: str | None = None
        if result.rendered and result.rgba_base64 is not None and result.width is not None and result.height is not None:
            raw = decode_rgba(result.rgba_base64, result.width, result.height)
            stride = result.width * 4
            pixels = b"".join(raw[offset:offset+stride] for offset in range(len(raw)-stride, -1, -stride))
            pixel_hash = sha256(pixels).hexdigest()
        report = c.Report(id=str(uuid4()), document_id=revision.document.id, version=revision.version, content_hash=revision.content_hash, kind=kind, compiled=result.compiled, rendered=result.rendered, diagnostics=result.diagnostics, logs=result.logs, log_truncated=result.log_truncated, capabilities=capabilities, elapsed_ms=elapsed_ms, width=result.width, height=result.height, pixel_hash=pixel_hash, pixel_format="rgba8-unorm" if pixels else None)
        return report, pixels
