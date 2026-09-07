"""SQLite transactions own Comic revisions, CAS and exact mutation receipts."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from dbfox_dlc_api import BaseModel, ProjectResourceDescriptor, ResourceScopeRef
from .contracts import (ComicProject, DiffInput, DiffResult, DOCUMENT_KIND, InspectInput, InspectResult,
    LIBRARY_KIND, Library, ListResult, MAX_BYTES, MutationResult, Operation, PageInput, Revision, Summary)


class ComicError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = "COMIC_" + code
        super().__init__(message)


def encoded(value) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value) -> str:
    return hashlib.sha256(encoded(value).encode("utf-8")).hexdigest()


def objects(document: ComicProject) -> dict[str, dict]:
    result = {"$document": {"title": document.title, "order": [p.id for p in document.pages]}}
    for page in document.pages:
        result[page.id] = {**page.model_dump(mode="json", exclude={"panels"}), "kind": "page", "order": [p.id for p in page.panels]}
        for panel in page.panels:
            result[panel.id] = {**panel.model_dump(mode="json", exclude={"elements"}), "kind": "panel", "page_id": page.id,
                                "order": [e.id for e in panel.elements]}
            for element in panel.elements:
                result[element.id] = {**element.model_dump(mode="json"), "panel_id": panel.id}
    return result


def apply_operation(document: ComicProject, operation: Operation) -> ComicProject:
    value = document.model_dump(mode="json")
    pages = {page["id"]: page for page in value["pages"]}
    panels = {panel["id"]: panel for page in value["pages"] for panel in page["panels"]}
    op = operation.model_dump(mode="json")
    kind = op.pop("kind")

    def require(table, identity):
        if identity not in table:
            raise ComicError("REFERENCE", "The exact object ID does not exist in this comic.")
        return table[identity]

    def reorder(items, order):
        mapping = {item["id"]: item for item in items}
        if len(order) != len(set(order)) or set(order) != set(mapping):
            raise ComicError("REFERENCE", "Reorder must name every child exactly once.")
        return [mapping[identity] for identity in order]

    if kind == "page_create":
        value["pages"].append(op["page"])
    elif kind == "panel_create":
        require(pages, op["page_id"])["panels"].extend(op["panels"])
    elif kind == "panel_layout":
        page = require(pages, op["page_id"])
        allowed = {p["id"] for p in page["panels"]}
        ids = [p["panel_id"] for p in op["placements"]]
        if len(ids) != len(set(ids)) or not set(ids) <= allowed:
            raise ComicError("REFERENCE", "Layout must contain unique panel IDs from the selected page.")
        for placement in op["placements"]:
            panels[placement["panel_id"]]["rect"] = placement["rect"]
    elif kind == "shot_set":
        require(panels, op["panel_id"])["shot"] = op["shot"]
    elif kind in ("character_place", "bubble_create", "caption_create", "note_create"):
        field = {"character_place": "character", "bubble_create": "bubble", "caption_create": "caption", "note_create": "note"}[kind]
        require(panels, op["panel_id"])["elements"].append(op[field])
    elif kind == "element_update":
        panel = require(panels, op["panel_id"])
        element = require({e["id"]: e for e in panel["elements"]}, op["element"]["id"])
        if element["kind"] != op["element"]["kind"]:
            raise ComicError("REFERENCE", "Changing an existing element type is not supported.")
        panel["elements"] = [op["element"] if e["id"] == element["id"] else e for e in panel["elements"]]
    elif kind == "panel_reorder":
        page = require(pages, op["page_id"])
        page["panels"] = reorder(page["panels"], op["panel_ids"])
    elif kind == "page_reorder":
        value["pages"] = reorder(value["pages"], op["page_ids"])
    elif kind in ("page_update", "panel_update"):
        key = "page_id" if kind == "page_update" else "panel_id"
        identity = op.pop(key)
        require(pages if key == "page_id" else panels, identity).update(op)
    elif kind == "object_delete":
        identity = op["object_id"]
        require(objects(document), identity)
        if identity in pages:
            value["pages"] = [p for p in value["pages"] if p["id"] != identity]
        elif identity in panels:
            for page in value["pages"]:
                page["panels"] = [p for p in page["panels"] if p["id"] != identity]
        else:
            for panel in panels.values():
                if any(e.get("speaker_id") == identity for e in panel["elements"]):
                    raise ComicError("REFERENCE", "Remove or unassign linked speech bubbles before deleting their character.")
                panel["elements"] = [e for e in panel["elements"] if e["id"] != identity]
    else:
        raise ComicError("INVALID", "Unsupported comic operation.")
    try:
        return ComicProject.model_validate(value)
    except ValueError as exc:
        raise ComicError("INVALID", "Operation violates comic bounds, IDs or references.") from exc


class ComicStore:
    def __init__(self, data_path: Path):
        data_path.mkdir(parents=True, exist_ok=True)
        self.path = data_path / "comic.sqlite3"
        with self.connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
                raise ComicError("SCHEMA", "This Comic database requires a newer DLC.")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS comics(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,head INTEGER NOT NULL,status TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS comic_project ON comics(project_id,status);
                CREATE TABLE IF NOT EXISTS revisions(comic_id TEXT NOT NULL REFERENCES comics(id),version INTEGER NOT NULL,
                    parent INTEGER,document TEXT NOT NULL,hash TEXT NOT NULL,status TEXT NOT NULL,producer TEXT NOT NULL,
                    PRIMARY KEY(comic_id,version));
                CREATE TABLE IF NOT EXISTS receipts(invocation TEXT PRIMARY KEY,request_hash TEXT NOT NULL,comic_id TEXT NOT NULL,
                    version INTEGER NOT NULL,result TEXT NOT NULL,FOREIGN KEY(comic_id,version) REFERENCES revisions(comic_id,version));
                CREATE TABLE IF NOT EXISTS object_ids(comic_id TEXT NOT NULL REFERENCES comics(id),id TEXT NOT NULL,PRIMARY KEY(comic_id,id));
                PRAGMA user_version=1;
                COMMIT;
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            if db.in_transaction:
                db.rollback()
            db.close()

    def _revision(self, db, project_id, comic_id, version=None) -> Revision:
        head = db.execute("SELECT * FROM comics WHERE id=? AND project_id=?", (comic_id, project_id)).fetchone()
        if head is None:
            raise ComicError("NOT_FOUND", "Comic does not exist in this Project.")
        rows = db.execute("SELECT version,parent,status FROM revisions WHERE comic_id=? ORDER BY version", (comic_id,)).fetchall()
        if not rows or head["head"] != len(rows) or any(row["version"] != i + 1 or row["parent"] != (i or None) for i, row in enumerate(rows)):
            raise ComicError("CORRUPT", "Comic revision chain is invalid.")
        if head["status"] != rows[-1]["status"] or any(row["status"] != "active" for row in rows[:-1]):
            raise ComicError("CORRUPT", "Comic lifecycle metadata is invalid.")
        row = db.execute("SELECT * FROM revisions WHERE comic_id=? AND version=?", (comic_id, head["head"] if version is None else version)).fetchone()
        if row is None:
            raise ComicError("NOT_FOUND", "Comic revision does not exist.")
        try:
            if len(row["document"].encode("utf-8")) > MAX_BYTES or row["status"] not in ("active", "deleted"):
                raise ValueError("invalid document")
            document = ComicProject.model_validate_json(row["document"])
            if fingerprint(document) != row["hash"]:
                raise ValueError("invalid hash")
            summary = Summary(id=comic_id, project_id=project_id, title=document.title, version=row["version"],
                content_hash=row["hash"], status=row["status"], page_count=len(document.pages),
                panel_count=sum(len(p.panels) for p in document.pages),
                element_count=sum(len(p.elements) for page in document.pages for p in page.panels))
            return Revision(comic=summary, parent_version=row["parent"], document=document)
        except (TypeError, ValueError) as exc:
            raise ComicError("CORRUPT", "Stored Comic content failed integrity validation.") from exc

    def get(self, project_id, comic_id, version=None):
        with self.connect() as db:
            db.execute("BEGIN")
            return self._revision(db, project_id, comic_id, version)

    @staticmethod
    def fence(revision, expected, frozen=None):
        if revision.comic.status != "active":
            raise ComicError("DELETED", "This comic was deleted.")
        if revision.comic.version != expected or (frozen is not None and frozen != expected):
            raise ComicError("STALE", "Comic changed. Inspect the current revision before editing.")

    @staticmethod
    def cancel(probe):
        if probe and probe():
            raise ComicError("CANCELLED", "Comic operation was cancelled before commit.")

    def _receipt(self, db, project_id, key, request_hash):
        row = db.execute("SELECT * FROM receipts WHERE invocation=?", (key,)).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise ComicError("RECEIPT_MISMATCH", "Request identity was already used for different input.")
        try:
            result = MutationResult.model_validate_json(row["result"])
            revision = self._revision(db, project_id, row["comic_id"], row["version"])
            producer = db.execute("SELECT producer FROM revisions WHERE comic_id=? AND version=?", (row["comic_id"], row["version"])).fetchone()[0]
            if result.comic != revision.comic or (result.changed and producer != key):
                raise ValueError("receipt producer mismatch")
            return result
        except ValueError as exc:
            raise ComicError("CORRUPT", "Stored Comic receipt is invalid.") from exc

    def reconcile(self, project_id, action, payload, key):
        with self.connect() as db:
            db.execute("BEGIN")
            return self._receipt(db, project_id, key, fingerprint([project_id, action, payload.model_dump(mode="json")]))

    def write(self, project_id: str, action: str, payload: BaseModel, key: str,
              frozen=None, cancelled: Callable[[], bool] | None = None) -> MutationResult:
        if not key:
            raise ComicError("INVALID", "Mutation requires a durable request identity.")
        request_hash = fingerprint([project_id, action, payload.model_dump(mode="json")])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.cancel(cancelled)
            prior = self._receipt(db, project_id, key, request_hash)
            if prior:
                return prior
            if action == "create":
                if db.execute("SELECT COUNT(*) FROM comics WHERE project_id=?", (project_id,)).fetchone()[0] >= 256:
                    raise ComicError("LIMIT", "Project reached its retained Comic capacity (256).")
                comic_id, version, status = "comic-" + uuid4().hex, 1, "active"
                document = ComicProject(title=payload.title)
                db.execute("INSERT INTO comics VALUES(?,?,?,?)", (comic_id, project_id, version, status))
                changed, prior_ids = True, set()
            else:
                comic_id = payload.comic_id
                current = self._revision(db, project_id, comic_id)
                if db.execute("SELECT COUNT(*) FROM receipts WHERE comic_id=?", (comic_id,)).fetchone()[0] >= 8192:
                    raise ComicError("LIMIT", "Comic reached its durable request receipt capacity (8192).")
                self.fence(current, payload.expected_version, frozen)
                status = "deleted" if action == "delete" else "active"
                if action == "apply":
                    document = apply_operation(current.document, payload.operation)
                elif action == "undo":
                    if payload.target_version > payload.expected_version:
                        raise ComicError("INVALID", "Undo target must not be newer than the inspected revision.")
                    document = self._revision(db, project_id, comic_id, payload.target_version).document
                elif action in ("delete", "export"):
                    document = current.document
                else:
                    raise ComicError("INVALID", "Unsupported mutation.")
                changed = document != current.document or status != current.comic.status
                version = current.comic.version + int(changed)
                prior_ids = set(objects(current.document))
            if changed:
                content = encoded(document)
                size = len(content.encode("utf-8"))
                history = db.execute("SELECT COALESCE(SUM(length(CAST(document AS BLOB))),0) FROM revisions WHERE comic_id=?", (comic_id,)).fetchone()[0]
                if size > MAX_BYTES or version > 1024 or history + size > 128 * 1024 * 1024:
                    raise ComicError("LIMIT", "Comic exceeds document or retained history capacity.")
                for identity in set(objects(document)) - prior_ids - {"$document"}:
                    try:
                        db.execute("INSERT INTO object_ids VALUES(?,?)", (comic_id, identity))
                    except sqlite3.IntegrityError as exc:
                        if action != "undo":
                            raise ComicError("ID_REUSED", "Deleted object IDs cannot be reused.") from exc
                db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,?,?)", (comic_id, version, version - 1 if version > 1 else None, content, fingerprint(document), status, key))
                db.execute("UPDATE comics SET head=?,status=? WHERE id=?", (version, status, comic_id))
            result = MutationResult(comic=self._revision(db, project_id, comic_id).comic, changed=changed)
            db.execute("INSERT INTO receipts VALUES(?,?,?,?,?)", (key, request_hash, comic_id, version, encoded(result)))
            self.cancel(cancelled)
            db.commit()
            return result

    def list(self, project_id, request: PageInput):
        with self.connect() as db:
            db.execute("BEGIN")
            ids = [row[0] for row in db.execute("SELECT id FROM comics WHERE project_id=? AND status='active' ORDER BY id", (project_id,))]
            selected = ids[request.offset:request.offset + request.limit]
            return ListResult(comics=[self._revision(db, project_id, identity).comic for identity in selected], total=len(ids),
                              offset=request.offset, next_offset=request.offset + len(selected))

    def inspect(self, project_id, request: InspectInput):
        revision = self.get(project_id, request.comic_id, request.version)
        if request.version is None and revision.comic.status != "active":
            raise ComicError("DELETED", "This comic was deleted.")
        pages = {p.id: p for p in revision.document.pages}
        panels = {p.id: p for page in revision.document.pages for p in page.panels}
        if request.section == "pages":
            values = [{**p.model_dump(mode="json", exclude={"panels"}), "panel_count": len(p.panels)} for p in pages.values()]
        elif request.section in ("panels", "page") and request.object_id in pages:
            page = pages[request.object_id]
            values = ([page.model_dump(mode="json")] if request.section == "page" else
                      [{**p.model_dump(mode="json", exclude={"elements"}), "element_count": len(p.elements)} for p in page.panels])
        elif request.section == "elements" and request.object_id in panels:
            values = [e.model_dump(mode="json") for e in panels[request.object_id].elements]
        else:
            raise ComicError("REFERENCE", "Inspection requires an exact page or panel ID.")
        selected = values[request.offset:request.offset + request.limit]
        end = request.offset + len(selected)
        return InspectResult(comic=revision.comic, items=selected, total=len(values), offset=request.offset,
                             next_offset=end, has_more=end < len(values))

    def diff(self, project_id, request: DiffInput):
        before = objects(self.get(project_id, request.comic_id, request.from_version).document)
        after = objects(self.get(project_id, request.comic_id, request.to_version).document)
        differences = []
        for identity in sorted(set(before) | set(after)):
            a, b = before.get(identity), after.get(identity)
            if a != b:
                differences.append({"id": identity, "change": "added" if a is None else "deleted" if b is None else "modified",
                    "fields": sorted(key for key in set(a or {}) | set(b or {}) if (a or {}).get(key) != (b or {}).get(key)),
                    "before_hash": fingerprint(a) if a else None, "after_hash": fingerprint(b) if b else None})
        selected = differences[request.offset:request.offset + request.limit]
        return DiffResult(comic_id=request.comic_id, from_version=request.from_version, to_version=request.to_version,
                          differences=selected, total=len(differences), offset=request.offset, next_offset=request.offset + len(selected))

    def resources(self, project_id):
        with self.connect() as db:
            db.execute("BEGIN")
            rows = db.execute("SELECT id,head FROM comics WHERE project_id=? AND status='active' ORDER BY id", (project_id,)).fetchall()
            summaries = [self._revision(db, project_id, row["id"]).comic for row in rows]
        return (ProjectResourceDescriptor(kind=LIBRARY_KIND, id=project_id, version=1, name="Comic Library"),
                *(ProjectResourceDescriptor(kind=DOCUMENT_KIND, id=s.id, version=s.version, name=s.title) for s in summaries))

    def resolve_library(self, ref: ResourceScopeRef):
        if ref.kind != LIBRARY_KIND or type(ref.version) is not int or ref.version != 1 or not ref.id:
            raise ComicError("REFERENCE", "Invalid Comic Library reference.")
        return Library(project_id=ref.id)

    def resolve(self, ref: ResourceScopeRef):
        if ref.kind != DOCUMENT_KIND or type(ref.version) is not int or ref.version < 1:
            raise ComicError("REFERENCE", "Comic requires an integer frozen revision.")
        with self.connect() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT project_id FROM comics WHERE id=?", (ref.id,)).fetchone()
            if row is None:
                raise ComicError("NOT_FOUND", "Comic resource does not exist.")
            return self._revision(db, row[0], ref.id, ref.version)

    def artifact_revision(self, summary: Summary, producer: str):
        with self.connect() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM receipts WHERE invocation=?", (producer,)).fetchone()
            if row is None or row["comic_id"] != summary.id or row["version"] != summary.version:
                raise ComicError("CORRUPT", "Artifact has no matching Comic producer receipt.")
            result = self._receipt(db, summary.project_id, producer, row["request_hash"])
            if result.comic != summary:
                raise ComicError("CORRUPT", "Artifact does not match its exact produced revision.")
            return self._revision(db, summary.project_id, summary.id, summary.version)
