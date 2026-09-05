"""Owner-local SQLite revisions and exact receipts; no Core database access."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
import sqlite3
from uuid import uuid4

from dbfox_dlc_api import ProjectResourceDescriptor, ResourceScopeRef

from . import contracts as c
from .domain import PixelError, apply_operations, changes, check_rect, directory, frame_delta, metadata, require


def now():
    return datetime.now(UTC).isoformat()


def digest(value):
    return sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


class PixelStore:
    def __init__(self, data_path):
        directory_path = Path(data_path)
        directory_path.mkdir(parents=True, exist_ok=True)
        self.path = directory_path / "state.sqlite3"
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            require(version in (0, 1), "Unsupported Pixel storage schema.", "CORRUPT_STATE")
            if version == 0:
                require(not db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone(),
                        "Unrecognized Pixel storage cannot be initialized.", "CORRUPT_STATE")
                for statement in (
                    "CREATE TABLE documents(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,head INTEGER NOT NULL CHECK(head>0),status TEXT NOT NULL CHECK(status IN ('active','deleted')),created_at TEXT NOT NULL)",
                    "CREATE INDEX project_documents ON documents(project_id,status)",
                    "CREATE TABLE revisions(document_id TEXT NOT NULL REFERENCES documents(id),revision INTEGER NOT NULL,parent_revision INTEGER,body BLOB NOT NULL,content_hash TEXT NOT NULL,status TEXT NOT NULL,operation TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(document_id,revision))",
                    "CREATE TABLE receipts(project_id TEXT NOT NULL,actor TEXT NOT NULL,identity TEXT NOT NULL,action TEXT NOT NULL,input_hash TEXT NOT NULL,input_body BLOB NOT NULL,result_body BLOB,document_id TEXT NOT NULL,expected_version INTEGER NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(project_id,actor,identity))",
                    "CREATE TABLE object_identities(document_id TEXT NOT NULL REFERENCES documents(id),kind TEXT NOT NULL,object_id TEXT NOT NULL,created_revision INTEGER NOT NULL,PRIMARY KEY(document_id,kind,object_id))",
                ):
                    db.execute(statement)
                db.execute("PRAGMA user_version=1")
            require(db.execute("PRAGMA quick_check").fetchone()[0] == "ok", "Pixel storage integrity check failed.", "CORRUPT_STATE")
            # Known schema version alone is insufficient if a table was removed.
            db.execute("SELECT d.id,r.revision,p.identity,o.object_id FROM documents d LEFT JOIN revisions r ON r.document_id=d.id LEFT JOIN receipts p ON p.document_id=d.id LEFT JOIN object_identities o ON o.document_id=d.id LIMIT 0")
            db.commit()

    @contextmanager
    def _connect(self):
        db = None
        try:
            db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("PRAGMA journal_mode=WAL")
            yield db
        except sqlite3.Error as exc:
            code = "BUSY" if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower() else "CORRUPT_STATE"
            raise PixelError(code, "Pixel storage is busy." if code == "BUSY" else "Pixel storage is unavailable or inconsistent.") from exc
        finally:
            if db is not None:
                if db.in_transaction:
                    db.rollback()
                db.close()

    @staticmethod
    def _document_index(db, project_id, document_id):
        # One small authority check shared by full reads and lightweight polling.
        # Do not load/decode the document body on each head poll.
        row = db.execute("""SELECT d.*,r.content_hash,r.status AS revision_status,r.parent_revision,
            (SELECT MAX(revision) FROM revisions WHERE document_id=d.id) AS latest_revision,
            EXISTS(SELECT 1 FROM revisions WHERE document_id=d.id AND revision=d.head-1) AS parent_exists
            FROM documents d LEFT JOIN revisions r ON r.document_id=d.id AND r.revision=d.head
            WHERE d.id=? AND d.project_id=?""", (document_id, project_id)).fetchone()
        require(row is not None, "Pixel document does not exist in this Project.", "NOT_FOUND")
        require(type(row["head"]) is int and row["head"] >= 1 and row["head"] == row["latest_revision"]
                and row["status"] == row["revision_status"]
                and row["parent_revision"] == (row["head"] - 1 if row["head"] > 1 else None)
                and (row["head"] == 1 or row["parent_exists"])
                and isinstance(row["content_hash"], str) and len(row["content_hash"]) == 64
                and all(char in "0123456789abcdef" for char in row["content_hash"]),
                "Pixel head index or ancestry is inconsistent.", "CORRUPT_STATE")
        return row

    def _revision(self, db, project_id, document_id, revision=None):
        owner = self._document_index(db, project_id, document_id)
        target = owner["head"] if revision is None else revision
        shape = db.execute("SELECT length(body) AS size,typeof(body) AS storage_type FROM revisions WHERE document_id=? AND revision=?", (document_id, target)).fetchone()
        require(shape is not None, "Pixel revision does not exist.", "NOT_FOUND" if revision is not None else "CORRUPT_STATE")
        require(shape["storage_type"] == "blob" and shape["size"] <= c.MAX_DOCUMENT_BYTES,
                "Invalid stored Pixel document size.", "CORRUPT_STATE")
        row = db.execute("SELECT * FROM revisions WHERE document_id=? AND revision=?", (document_id, target)).fetchone()
        require(row is not None, "Pixel revision does not exist.", "NOT_FOUND" if revision is not None else "CORRUPT_STATE")
        try:
            body = row["body"]
            require(isinstance(body, bytes) and len(body) <= c.MAX_DOCUMENT_BYTES, "Invalid stored Pixel document size.", "CORRUPT_STATE")
            document = c.PixelDocument.model_validate_json(body)
            require(c.canonical(document).encode("utf-8") == body and digest(body) == row["content_hash"],
                    "Stored Pixel document hash does not match.", "CORRUPT_STATE")
            require(type(target) is int and target >= 1 and target <= owner["head"] and
                    row["parent_revision"] == (target - 1 if target > 1 else None), "Invalid revision ancestry.", "CORRUPT_STATE")
            require(target == 1 or db.execute("SELECT 1 FROM revisions WHERE document_id=? AND revision=?",
                    (document_id, target - 1)).fetchone() is not None, "Missing Pixel revision parent.", "CORRUPT_STATE")
            require(row["status"] in ("active", "deleted") and
                    (target != owner["head"] or row["status"] == owner["status"]), "Invalid revision status.", "CORRUPT_STATE")
            identities = {(item["kind"], item["object_id"]) for item in db.execute(
                "SELECT kind,object_id FROM object_identities WHERE document_id=? AND created_revision<=?", (document_id, target))}
            require(all((kind, item.id) in identities for kind, items in (("frame", document.frames), ("layer", document.layers), ("tag", document.tags)) for item in items),
                    "Pixel object birth records are inconsistent.", "CORRUPT_STATE")
            summary = c.DocumentSummary(project_id=project_id, document_id=document_id, revision=target,
                parent_revision=row["parent_revision"], content_hash=row["content_hash"], title=document.title,
                width=document.canvas.width, height=document.canvas.height, frame_count=len(document.frames),
                layer_count=len(document.layers), palette_count=len(document.palette), tag_count=len(document.tags), status=row["status"])
            return c.Revision(summary=summary, document=document)
        except (ValueError, TypeError) as exc:
            raise PixelError("CORRUPT_STATE", "Stored Pixel document is invalid.") from exc

    def get_revision(self, project_id, document_id, revision=None):
        with self._connect() as db:
            db.execute("BEGIN")
            return self._revision(db, project_id, document_id, revision)

    @staticmethod
    def _binding(project_id, actor, identity, action, payload, scope):
        require(isinstance(project_id, str) and 0 < len(project_id) <= 256 and actor in ("human", "agent") and
                isinstance(identity, str) and 0 < len(identity) <= 256, "Valid Project, actor and mutation identities are required.")
        if actor == "agent":
            require(scope is not None, "A frozen Pixel resource is required.", "AUTHORITY")
        else:
            require(scope is None, "Human authority comes from its Project operation.", "AUTHORITY")
        return c.canonical({"owner": c.OWNER, "project_id": project_id, "actor": actor, "identity": identity,
            "action": action, "input": payload.model_dump(mode="json"), "scope": scope.model_dump(mode="json") if scope else None}).encode("utf-8")

    def _receipt(self, db, project_id, actor, identity, binding, model):
        shape = db.execute("SELECT length(input_body) AS input_size,typeof(input_body) AS input_type,length(result_body) AS result_size,typeof(result_body) AS result_type FROM receipts WHERE project_id=? AND actor=? AND identity=?",
            (project_id, actor, identity)).fetchone()
        if shape is None:
            return None
        require(shape["input_type"] == "blob" and shape["input_size"] <= c.MAX_INPUT_BYTES + 4096 and
                (shape["result_type"] == "null" or (shape["result_type"] == "blob" and shape["result_size"] <= c.MAX_OUTPUT_BYTES)),
                "Invalid stored Pixel receipt size.", "CORRUPT_STATE")
        row = db.execute("SELECT * FROM receipts WHERE project_id=? AND actor=? AND identity=?", (project_id, actor, identity)).fetchone()
        if row is None:
            return None
        require(row["input_hash"] == digest(binding) and row["input_body"] == binding,
                "Mutation identity is already bound to different input.", "RECEIPT_MISMATCH")
        require(row["result_body"] is not None, "Pixel export outcome is unknown; do not repeat this export.", "EXPORT_UNKNOWN")
        try:
            require(len(row["result_body"]) <= c.MAX_OUTPUT_BYTES, "Invalid Pixel receipt size.", "CORRUPT_STATE")
            result = model.model_validate_json(row["result_body"])
            if model is c.MutationResult:
                require(result.document_id == row["document_id"] and result.project_id == project_id,
                        "Pixel receipt identity is inconsistent.", "CORRUPT_STATE")
                revision = self._revision(db, project_id, result.document_id, result.revision)
                summary = c.DocumentSummary.model_validate(result.model_dump(exclude={"changed", "changed_pixel_count", "changed_frame_ids", "changed_layer_ids"}))
                require(summary == revision.summary, "Pixel receipt differs from its immutable revision.", "CORRUPT_STATE")
            return result
        except ValueError as exc:
            raise PixelError("CORRUPT_STATE", "Pixel receipt is invalid.") from exc

    def reconcile(self, project_id, actor, identity, action, payload, scope=None):
        binding = self._binding(project_id, actor, identity, action, payload, scope)
        with self._connect() as db:
            db.execute("BEGIN")
            return self._receipt(db, project_id, actor, identity, binding, c.MutationResult)

    @staticmethod
    def _quota(db):
        total = sum(db.execute(query).fetchone()[0] for query in (
            "SELECT COALESCE(SUM(length(body)+length(operation)+512),0) FROM revisions",
            # A pending ActionRun reserves its full bounded result space before
            # external settlement; recording success never needs extra quota.
            "SELECT COALESCE(SUM(length(input_body)+COALESCE(length(result_body),16384)+512),0) FROM receipts",
            "SELECT COUNT(*)*512 FROM object_identities", "SELECT COUNT(*)*512 FROM documents"))
        require(total <= c.MAX_HISTORY_BYTES, "Pixel owner history quota is full; existing revisions remain readable.", "LIMIT")

    @staticmethod
    def _scope(scope, project_id, document_id, expected, library=False):
        if scope is None:
            return
        require(scope.kind == (c.LIBRARY_KIND if library else c.DOCUMENT_KIND) and
                scope.id == (project_id if library else document_id) and
                str(scope.version) == ("1" if library else str(expected)),
                "Pixel frozen resource does not match this write.", "CONFLICT")

    @staticmethod
    def _fence(revision, expected, action):
        require(revision.summary.revision == expected, "Pixel document changed; inspect before editing.", "CONFLICT")
        require(revision.summary.status == ("deleted" if action == "restore" else "active"),
                "Pixel document lifecycle does not allow this operation.", "CONFLICT")

    @staticmethod
    def _save_revision(db, document_id, version, document, status, action, actor):
        body = c.canonical(document).encode("utf-8")
        db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?,?)", (document_id, version,
            version - 1 if version > 1 else None, body, digest(body), status, action, actor, now()))

    @staticmethod
    def _save_receipt(db, project_id, actor, identity, action, binding, document_id, expected, result):
        encoded = c.canonical(result).encode("utf-8") if result is not None else None
        require(encoded is None or len(encoded) <= c.MAX_OUTPUT_BYTES, "Pixel result exceeds its bounded contract.", "LIMIT")
        db.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?)", (project_id, actor, identity, action,
            digest(binding), binding, encoded, document_id, expected, now()))

    def create(self, project_id, payload, identity, actor="human", scope=None, cancelled=lambda: False):
        binding = self._binding(project_id, actor, identity, "create", payload, scope)
        self._scope(scope, project_id, None, 0, library=True)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._receipt(db, project_id, actor, identity, binding, c.MutationResult)
            if previous is not None:
                return previous
            require(not cancelled(), "Pixel operation was cancelled.", "CANCELLED")
            require(payload.expected_version == 0, "Creation requires expected_version 0.")
            require(db.execute("SELECT COUNT(*) FROM documents WHERE project_id=? AND status='active'", (project_id,)).fetchone()[0] < 128,
                    "Project already has 128 active Pixel documents.", "LIMIT")
            palette = payload.palette or [c.PaletteEntry(name="Transparent", color="#00000000"),
                c.PaletteEntry(name="Ink", color="#181825FF"), c.PaletteEntry(name="White", color="#FFFFFFFF")]
            try:
                document = c.PixelDocument(schema_version=1, title=payload.title, canvas=c.Canvas(width=payload.width, height=payload.height),
                    palette=palette, layers=[c.Layer(id="layer_1", name="Layer 1", visible=True, locked=False)],
                    frames=[c.Frame(id="frame_1", duration_ms=100, cels=[c.Cel(layer_id="layer_1", pixels=[0] * (payload.width * payload.height))])], tags=[])
            except ValueError as exc:
                raise PixelError("INVALID", "Initial Pixel document violates palette or canvas invariants.") from exc
            document_id = "pixel_" + uuid4().hex
            db.execute("INSERT INTO documents VALUES (?,?,1,'active',?)", (document_id, project_id, now()))
            db.executemany("INSERT INTO object_identities VALUES (?,?,?,1)", [(document_id, "frame", "frame_1"), (document_id, "layer", "layer_1")])
            self._save_revision(db, document_id, 1, document, "active", "create", actor)
            result = c.MutationResult(**self._revision(db, project_id, document_id).summary.model_dump(), changed=True, **changes(None, document))
            self._save_receipt(db, project_id, actor, identity, "create", binding, document_id, 0, result)
            self._quota(db)
            require(not cancelled(), "Pixel operation was cancelled.", "CANCELLED")
            db.commit()
            return result

    def mutate(self, project_id, payload, identity, action="apply", actor="human", scope=None, cancelled=lambda: False):
        binding = self._binding(project_id, actor, identity, action, payload, scope)
        self._scope(scope, project_id, payload.document_id, payload.expected_version, library=action == "restore")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._receipt(db, project_id, actor, identity, binding, c.MutationResult)
            if previous is not None:
                return previous
            source = self._revision(db, project_id, payload.document_id)
            self._fence(source, payload.expected_version, action)
            require(not cancelled(), "Pixel operation was cancelled.", "CANCELLED")
            version = payload.expected_version + 1
            def born(kind, identity):
                require(not db.execute("SELECT 1 FROM object_identities WHERE document_id=? AND kind=? AND object_id=?",
                    (payload.document_id, kind, identity)).fetchone(), "Object identity was already used in this document.", "ID_REUSED")
                db.execute("INSERT INTO object_identities VALUES (?,?,?,?)", (payload.document_id, kind, identity, version))
            status = "deleted" if action == "delete" else "active"
            if action == "apply":
                operations = payload.operations if isinstance(payload, c.ApplyInput) else [payload.operation]
                document = apply_operations(source.document, operations, born, cancelled)
            elif action == "undo":
                require(payload.restore_revision <= payload.expected_version, "Undo revision must already exist.")
                restored = self._revision(db, project_id, payload.document_id, payload.restore_revision)
                require(restored.summary.status == "active", "Undo cannot restore a tombstone.")
                document = restored.document
            elif action in ("delete", "restore", "export"):
                document = source.document
                if action == "restore":
                    require(db.execute("SELECT COUNT(*) FROM documents WHERE project_id=? AND status='active'", (project_id,)).fetchone()[0] < 128,
                            "Project already has 128 active Pixel documents.", "LIMIT")
            else:
                raise PixelError("INVALID", "Unknown Pixel mutation.")
            changed = source.document != document or source.summary.status != status
            if changed:
                self._save_revision(db, payload.document_id, version, document, status, action, actor)
                cursor = db.execute("UPDATE documents SET head=?,status=? WHERE id=? AND project_id=? AND head=?",
                    (version, status, payload.document_id, project_id, payload.expected_version))
                require(cursor.rowcount == 1, "Pixel document changed concurrently.", "CONFLICT")
            else:
                # A create-then-delete batch leaves historical birth records at
                # the current revision even though content is unchanged.
                db.execute("UPDATE object_identities SET created_revision=? WHERE document_id=? AND created_revision=?",
                    (payload.expected_version, payload.document_id, version))
            result = c.MutationResult(**self._revision(db, project_id, payload.document_id).summary.model_dump(),
                changed=changed, **changes(source.document, document))
            self._save_receipt(db, project_id, actor, identity, action, binding, payload.document_id, payload.expected_version, result)
            self._quota(db)
            require(not cancelled(), "Pixel operation was cancelled.", "CANCELLED")
            db.commit()
            return result

    def list_documents(self, project_id, request):
        with self._connect() as db:
            db.execute("BEGIN")
            rows = db.execute("SELECT id FROM documents WHERE project_id=? AND (? OR status='active') ORDER BY created_at,id LIMIT ? OFFSET ?",
                (project_id, request.include_deleted, request.page_size + 1, request.page * request.page_size)).fetchall()
            return c.ListResult(documents=[self._revision(db, project_id, row["id"]).summary for row in rows[:request.page_size]], has_more=len(rows) > request.page_size)

    def get(self, project_id, request):
        revision = self.get_revision(project_id, request.document_id, request.revision)
        return c.MetadataResult(summary=revision.summary, document=metadata(revision.document))

    def head(self, project_id, request):
        # Polling transfers only the canonical head's small index fields. A
        # subsequent pinned frame/get read validates the full revision and hash.
        with self._connect() as db:
            row = self._document_index(db, project_id, request.document_id)
            try:
                return c.HeadResult(document_id=row["id"], revision=row["head"], content_hash=row["content_hash"], status=row["status"])
            except ValueError as exc:
                raise PixelError("CORRUPT_STATE", "Pixel head is invalid.") from exc

    def read_frame(self, project_id, request):
        revision = self.get_revision(project_id, request.document_id, request.revision)
        frame = next((frame for frame in revision.document.frames if frame.id == request.frame_id), None)
        require(frame is not None, "Pixel frame does not exist.", "NOT_FOUND")
        return c.FrameResult(document_id=request.document_id, revision=revision.summary.revision, content_hash=revision.summary.content_hash,
            canvas=revision.document.canvas, palette=revision.document.palette, frame=frame)

    def inspect(self, project_id, request):
        revision = self.get_revision(project_id, request.document_id, request.revision)
        items = directory(revision.document, request.kind)
        offset = request.page * request.page_size
        pixels, selection = None, None
        if request.rect is not None:
            frame = next((frame for frame in revision.document.frames if frame.id == request.frame_id), None)
            require(frame is not None, "Pixel frame does not exist.", "NOT_FOUND")
            cel = next((cel for cel in frame.cels if cel.layer_id == request.layer_id), None)
            require(cel is not None, "Pixel layer does not exist.", "NOT_FOUND")
            rect, width = request.rect, revision.document.canvas.width
            check_rect(rect, width, revision.document.canvas.height)
            pixels = [cel.pixels[(rect.y + y) * width + rect.x + x] for y in range(rect.height) for x in range(rect.width)]
            selection = {"frame_id": request.frame_id, "layer_id": request.layer_id, "rect": rect.model_dump()}
        result = c.PageResult(summary=revision.summary, kind=request.kind, page=request.page, page_size=request.page_size,
            total=len(items), has_more=offset + request.page_size < len(items), items=items[offset:offset + request.page_size], pixels=pixels, selection=selection)
        require(len(c.canonical(result).encode("utf-8")) <= c.MAX_OUTPUT_BYTES, "Pixel inspection exceeds output budget; request a smaller page.", "LIMIT")
        return result

    def revisions(self, project_id, request):
        with self._connect() as db:
            db.execute("BEGIN")
            head = self._revision(db, project_id, request.document_id).summary.revision
            rows = db.execute("SELECT revision FROM revisions WHERE document_id=? AND revision<? ORDER BY revision DESC LIMIT ?",
                (request.document_id, request.before_revision or head + 1, request.limit + 1)).fetchall()
            values = [self._revision(db, project_id, request.document_id, row["revision"]).summary for row in rows[:request.limit]]
            return c.RevisionsResult(revisions=values, next_before_revision=values[-1].revision if len(rows) > request.limit else None)

    def diff(self, project_id, request):
        before = self.get_revision(project_id, request.document_id, request.from_revision).document
        after = self.get_revision(project_id, request.document_id, request.to_revision).document
        left, right = directory(before, request.kind), directory(after, request.kind)
        key = "index" if request.kind == "palette" else "id"
        old, new = {item[key]: item for item in left}, {item[key]: item for item in right}
        items = []
        old_frames, new_frames = {f.id: f for f in before.frames}, {f.id: f for f in after.frames}
        for identity in sorted(old.keys() | new.keys()):
            a, b = old.get(identity), new.get(identity)
            position_changed = a is not None and b is not None and left.index(a) != right.index(b)
            deltas = frame_delta(old_frames.get(identity), new_frames.get(identity), after.canvas.width) if request.kind == "frames" else []
            # Full tag lists are compared even when the bounded preview matches.
            tag_changed = request.kind == "tags" and next((x for x in before.tags if x.id == identity), None) != next((x for x in after.tags if x.id == identity), None)
            if a != b or position_changed or deltas or tag_changed:
                item = {key: identity, "change": "added" if a is None else "deleted" if b is None else "modified",
                        "position_changed": position_changed}
                if deltas:
                    item.update(changed_pixel_count=sum(delta["changed_pixel_count"] for delta in deltas),
                                changed_cels=deltas, cel_count=len(deltas))
                items.append(item)
        offset = request.page * request.page_size
        result = c.DiffResult(document_id=request.document_id, from_revision=request.from_revision, to_revision=request.to_revision,
            kind=request.kind, page=request.page, page_size=request.page_size, total=len(items),
            has_more=offset + request.page_size < len(items), items=items[offset:offset + request.page_size])
        require(len(c.canonical(result).encode("utf-8")) <= c.MAX_OUTPUT_BYTES, "Pixel diff exceeds output budget; request a smaller page.", "LIMIT")
        return result

    def reserve_export(self, project_id, payload):
        binding = self._binding(project_id, "human", payload.mutation_id, "action_export", payload, None)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._receipt(db, project_id, "human", payload.mutation_id, binding, c.ExportResult)
            if previous is not None:
                return previous
            self._fence(self._revision(db, project_id, payload.document_id), payload.expected_version, "export")
            self._save_receipt(db, project_id, "human", payload.mutation_id, "action_export", binding, payload.document_id, payload.expected_version, None)
            self._quota(db)
            db.commit()
            return None

    def finish_export(self, project_id, payload, result):
        binding = self._binding(project_id, "human", payload.mutation_id, "action_export", payload, None)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT input_body,result_body FROM receipts WHERE project_id=? AND actor='human' AND identity=?",
                (project_id, payload.mutation_id)).fetchone()
            require(row is not None and row["input_body"] == binding and row["result_body"] is None,
                    "Pixel export reservation does not match.", "RECEIPT_MISMATCH")
            db.execute("UPDATE receipts SET result_body=? WHERE project_id=? AND actor='human' AND identity=?",
                (c.canonical(result).encode("utf-8"), project_id, payload.mutation_id))
            self._quota(db)
            db.commit()

    def list_resources(self, project_id):
        with self._connect() as db:
            db.execute("BEGIN")
            rows = db.execute("SELECT id FROM documents WHERE project_id=? AND status='active' ORDER BY id LIMIT 129", (project_id,)).fetchall()
            require(len(rows) <= 128, "Pixel Project catalog exceeds its durable budget.", "CORRUPT_STATE")
            values = [self._revision(db, project_id, row["id"]).summary for row in rows]
            return (ProjectResourceDescriptor(kind=c.LIBRARY_KIND, id=project_id, version="1", name="Pixel Library"),
                    *(ProjectResourceDescriptor(kind=c.DOCUMENT_KIND, id=value.document_id, version=str(value.revision), name=value.title) for value in values))

    def resolve_library(self, ref: ResourceScopeRef):
        require(ref.kind == c.LIBRARY_KIND and str(ref.version) == "1", "Invalid Pixel Library reference.", "AUTHORITY")
        return c.Library(project_id=ref.id)

    def resolve_document(self, ref: ResourceScopeRef):
        require(ref.kind == c.DOCUMENT_KIND and isinstance(ref.version, str) and ref.version.isascii() and ref.version.isdecimal()
                and str(int(ref.version)) == ref.version and int(ref.version) >= 1, "Invalid Pixel document revision reference.", "AUTHORITY")
        with self._connect() as db:
            owner = db.execute("SELECT project_id FROM documents WHERE id=?", (ref.id,)).fetchone()
            require(owner is not None, "Pixel document does not exist.", "NOT_FOUND")
            db.execute("BEGIN")
            return self._revision(db, owner["project_id"], ref.id, int(ref.version))
