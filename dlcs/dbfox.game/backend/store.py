"""Owner SQLite facts, append-only revisions and exact actor-scoped receipts."""
from __future__ import annotations

import base64
import binascii
import hashlib
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from dbfox_dlc_api import ProjectResourceDescriptor, ResourceScopeRef
from pydantic import ValidationError

from . import contracts as c
from .mutations import apply_operations, new_game
from .validation import object_index

Actor = Literal["human", "agent"]
Guard = Callable[[], None]


class GameError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.status = code, status


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def text_field(row: sqlite3.Row, key: str) -> str:
    value: object = row[key]
    if type(value) is not str:
        raise GameError("STATE_CORRUPT", "Stored Game text is invalid", 500)
    return value


def int_field(row: sqlite3.Row, key: str) -> int:
    value: object = row[key]
    if type(value) is not int:
        raise GameError("STATE_CORRUPT", "Stored Game integer is invalid", 500)
    return value


def payload_field(row: sqlite3.Row, key: str) -> bytes:
    value: object = row[key]
    if type(value) is not bytes:
        raise GameError("STATE_CORRUPT", "Stored Game payload is invalid", 500)
    return value


def request_hash(action: str, request: c.Contract) -> str:
    return digest(c.encoded({"action": action, "input": request.data()}))


class Store:
    def __init__(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "state.sqlite3"
        self._lock = threading.RLock()
        with self.connection(write=True) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise GameError("STATE_CORRUPT", "Unversioned Game database is not empty", 500)
                statements = (
                    "CREATE TABLE projects(project_id TEXT PRIMARY KEY,version INTEGER NOT NULL)",
                    "CREATE TABLE games(project_id TEXT NOT NULL,game_id TEXT NOT NULL UNIQUE,head INTEGER NOT NULL,PRIMARY KEY(project_id,game_id))",
                    "CREATE TABLE revisions(project_id TEXT NOT NULL,game_id TEXT NOT NULL,version INTEGER NOT NULL,library_version INTEGER NOT NULL,content_hash TEXT NOT NULL,deleted INTEGER NOT NULL,payload BLOB NOT NULL,actor TEXT NOT NULL,request_key TEXT NOT NULL,operation TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(project_id,game_id,version),UNIQUE(project_id,library_version))",
                    "CREATE TABLE identities(project_id TEXT NOT NULL,game_id TEXT NOT NULL,object_id TEXT NOT NULL,kind TEXT NOT NULL,PRIMARY KEY(project_id,game_id,object_id))",
                    "CREATE TABLE receipts(project_id TEXT NOT NULL,actor TEXT NOT NULL,request_key TEXT NOT NULL,request_hash TEXT NOT NULL,payload_hash TEXT NOT NULL,payload BLOB NOT NULL,PRIMARY KEY(project_id,actor,request_key))",
                    "CREATE TABLE blobs(project_id TEXT NOT NULL,content_hash TEXT NOT NULL,payload BLOB NOT NULL,PRIMARY KEY(project_id,content_hash))",
                    "CREATE TABLE reports(project_id TEXT NOT NULL,game_id TEXT NOT NULL,report_id TEXT NOT NULL,version INTEGER NOT NULL,content_hash TEXT NOT NULL,payload_hash TEXT NOT NULL,payload BLOB NOT NULL,PRIMARY KEY(project_id,report_id))",
                    "CREATE TABLE action_receipts(project_id TEXT NOT NULL,request_key TEXT NOT NULL,request_hash TEXT NOT NULL,payload_hash TEXT NOT NULL,payload BLOB NOT NULL,PRIMARY KEY(project_id,request_key))",
                    "CREATE INDEX revision_library ON revisions(project_id,library_version,game_id)",
                )
                for statement in statements:
                    db.execute(statement)
                db.execute("PRAGMA user_version=1")
            elif version != 1:
                raise GameError("STATE_VERSION_UNSUPPORTED", "Game database schema is unsupported", 500)

    @contextmanager
    def connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        with self._lock:
            db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
            db.row_factory = sqlite3.Row
            try:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                yield db
                db.commit()
            except sqlite3.DatabaseError as exc:
                db.rollback()
                raise GameError("STATE_CORRUPT", "Game storage is unavailable or inconsistent", 500) from exc
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    def library(self, project_id: str, version: int | None = None) -> c.LibraryScope:
        with self.connection(write=True) as db:
            current = self._library(db, project_id)
            chosen = current if version is None else version
            if type(chosen) is not int or chosen < 1 or chosen > current:
                raise GameError("NOT_FOUND", "Game library version does not exist", 404)
            return c.LibraryScope(project_id=project_id, version=chosen)

    @staticmethod
    def _library(db: sqlite3.Connection, project_id: str) -> int:
        if not project_id or len(project_id) > 256:
            raise GameError("INVALID_PROJECT", "Game requires a valid Host project")
        row = db.execute("SELECT version FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            db.execute("INSERT INTO projects VALUES (?,1)", (project_id,))
            return 1
        version = int_field(row, "version")
        maximum = db.execute("SELECT MAX(library_version) AS maximum FROM revisions WHERE project_id=?", (project_id,)).fetchone()["maximum"]
        if type(version) is not int or version < 1 or (maximum is None and version != 1) or (maximum is not None and maximum != version):
            raise GameError("STATE_CORRUPT", "Game library head does not match revision history", 500)
        return version

    def list_games(self, project_id: str, version: int | None = None) -> tuple[c.LibraryScope, list[c.Summary]]:
        with self.connection(write=True) as db:
            current = self._library(db, project_id)
            chosen = current if version is None else version
            if type(chosen) is not int or not 1 <= chosen <= current:
                raise GameError("NOT_FOUND", "Game library version does not exist", 404)
            rows = db.execute("SELECT r.* FROM revisions r JOIN (SELECT game_id, MAX(version) AS version FROM revisions WHERE project_id=? AND library_version<=? GROUP BY game_id) h ON r.game_id=h.game_id AND r.version=h.version WHERE r.project_id=? ORDER BY r.game_id", (project_id, chosen, project_id)).fetchall()
            return c.LibraryScope(project_id=project_id, version=chosen), [self._decode(db, row).summary() for row in rows]

    def get(self, project_id: str, game_id: str, version: int | None = None) -> c.Revision:
        with self.connection() as db:
            return self._get(db, project_id, game_id, version)

    def resources(self, project_id: str) -> tuple[ProjectResourceDescriptor, ...]:
        library, games = self.list_games(project_id)
        return (ProjectResourceDescriptor(kind=c.LIBRARY, id=project_id, version=library.version, name="Game library"), *(ProjectResourceDescriptor(kind=c.RESOURCE, id=item.id, version=item.version, name=("Deleted · " if item.deleted else "") + item.title) for item in games))

    def resolve(self, ref: ResourceScopeRef) -> c.LibraryScope | c.Revision:
        if type(ref.version) is not int or ref.version < 1:
            raise GameError("INVALID_SCOPE", "Game Resource requires a fixed integer version")
        if ref.kind == c.LIBRARY:
            return self.library(ref.id, ref.version)
        if ref.kind != c.RESOURCE:
            raise GameError("INVALID_SCOPE", "Resource kind does not belong to Game")
        with self.connection() as db:
            row = db.execute("SELECT project_id FROM games WHERE game_id=?", (ref.id,)).fetchone()
            if row is None:
                raise GameError("NOT_FOUND", "Game Resource does not exist", 404)
            return self._get(db, text_field(row, "project_id"), ref.id, ref.version)

    def _get(self, db: sqlite3.Connection, project_id: str, game_id: str, version: int | None = None) -> c.Revision:
        if version is None:
            head = db.execute("SELECT head FROM games WHERE project_id=? AND game_id=?", (project_id, game_id)).fetchone()
            if head is None:
                raise GameError("NOT_FOUND", "Game does not exist in this project", 404)
            version = int_field(head, "head")
            maximum = db.execute("SELECT MAX(version) AS maximum FROM revisions WHERE project_id=? AND game_id=?", (project_id, game_id)).fetchone()["maximum"]
            if maximum != version:
                raise GameError("STATE_CORRUPT", "Game head does not match revision history", 500)
        row = db.execute("SELECT * FROM revisions WHERE project_id=? AND game_id=? AND version=?", (project_id, game_id, version)).fetchone()
        if row is None:
            raise GameError("NOT_FOUND", "Game revision does not exist", 404)
        return self._decode(db, row)

    def _decode(self, db: sqlite3.Connection, row: sqlite3.Row) -> c.Revision:
        raw = payload_field(row, "payload")
        if len(raw) > c.MAX_DOCUMENT or digest(raw) != text_field(row, "content_hash") or int_field(row, "deleted") not in (0, 1):
            raise GameError("STATE_CORRUPT", "Game revision payload failed integrity verification", 500)
        try:
            game = c.GameProject.model_validate_json(raw)
            revision = c.Revision(game=game, project_id=text_field(row, "project_id"), version=int_field(row, "version"), library_version=int_field(row, "library_version"), content_hash=text_field(row, "content_hash"), deleted=bool(int_field(row, "deleted")))
        except (ValidationError, ValueError, RecursionError) as exc:
            raise GameError("STATE_CORRUPT", "Game revision schema failed verification", 500) from exc
        if game.id != text_field(row, "game_id") or c.encoded(game.data()) != raw:
            raise GameError("STATE_CORRUPT", "Game revision identity or canonical encoding is inconsistent", 500)
        identities = {text_field(item, "object_id"): text_field(item, "kind") for item in db.execute("SELECT object_id,kind FROM identities WHERE project_id=? AND game_id=?", (revision.project_id, game.id))}
        for identity, kind in self._identities(game).items():
            if identities.get(identity) != kind:
                raise GameError("STATE_CORRUPT", "Game stable identity ledger is inconsistent", 500)
        for asset in game.assets:
            self._blob(db, revision.project_id, asset)
        return revision

    @staticmethod
    def _identities(game: c.GameProject) -> dict[str, str]:
        result = {game.id: "game"}
        for identity, item in object_index(game).items():
            result[identity] = "component:" + item.spec.kind if isinstance(item, c.Component) else type(item).__name__.lower()
        return result

    @staticmethod
    def _blob(db: sqlite3.Connection, project_id: str, asset: c.Asset) -> bytes:
        row = db.execute("SELECT payload FROM blobs WHERE project_id=? AND content_hash=?", (project_id, asset.content_hash)).fetchone()
        if row is None:
            raise GameError("STATE_CORRUPT", "Game asset bytes are missing", 500)
        raw = payload_field(row, "payload")
        if len(raw) != asset.width * asset.height * 4 or digest(raw) != asset.content_hash:
            raise GameError("STATE_CORRUPT", "Game asset bytes failed integrity verification", 500)
        return raw

    def asset_bytes(self, revision: c.Revision, asset_id: str) -> bytes:
        asset = next((item for item in revision.game.assets if item.id == asset_id), None)
        if asset is None:
            raise GameError("NOT_FOUND", "Asset does not belong to this fixed Game revision", 404)
        with self.connection() as db:
            return self._blob(db, revision.project_id, asset)

    def _receipt(self, db: sqlite3.Connection, project_id: str, actor: Actor, key: str, fingerprint: str) -> c.Mutation | None:
        if actor not in ("human", "agent") or not key or len(key) > 128:
            raise GameError("INVALID_IDENTITY", "Mutation requires a bounded actor request identity")
        if actor == "human" and db.execute("SELECT 1 FROM action_receipts WHERE project_id=? AND request_key=?", (project_id, key)).fetchone():
            raise GameError("REQUEST_MISMATCH", "Request identity already belongs to a Game action Run", 409)
        row = db.execute("SELECT request_hash,payload_hash,payload FROM receipts WHERE project_id=? AND actor=? AND request_key=?", (project_id, actor, key)).fetchone()
        if row is None:
            return None
        if text_field(row, "request_hash") != fingerprint:
            raise GameError("REQUEST_MISMATCH", "Request identity was already used with different input", 409)
        if digest(payload_field(row, "payload")) != text_field(row, "payload_hash"):
            raise GameError("STATE_CORRUPT", "Game receipt failed integrity verification", 500)
        try:
            result = c.Mutation.model_validate_json(payload_field(row, "payload"))
        except ValidationError as exc:
            raise GameError("STATE_CORRUPT", "Game receipt failed schema verification", 500) from exc
        if result.game.project_id != project_id:
            raise GameError("STATE_CORRUPT", "Game receipt project is inconsistent", 500)
        revision = self._get(db, project_id, result.game.id, result.game.version)
        if revision.summary() != result.game or revision.library_version > result.library_version:
            raise GameError("STATE_CORRUPT", "Game receipt does not match its historical revision", 500)
        if result.report is not None:
            report = self._report(db, project_id, result.game.id, result.game.version, result.report.id)
            if self._report_summary(result.report.id, report) != result.report:
                raise GameError("STATE_CORRUPT", "Game receipt and playtest report do not match", 500)
        return result

    def receipt(self, project_id: str, actor: Actor, key: str, action: str, request: c.Contract) -> c.Mutation | None:
        with self.connection() as db:
            return self._receipt(db, project_id, actor, key, request_hash(action, request))

    @staticmethod
    def _budget(db: sqlite3.Connection) -> None:
        total = 0
        for table in ("revisions", "receipts", "blobs", "reports"):
            row = db.execute("SELECT COALESCE(SUM(length(payload)),0) AS size FROM " + table).fetchone()
            total += int_field(row, "size")
        # Hashes and identity provenance also consume a bounded owner budget.
        total += int_field(db.execute("SELECT COUNT(*)*192 AS size FROM receipts").fetchone(), "size")
        total += int_field(db.execute("SELECT COUNT(*)*160 AS size FROM identities").fetchone(), "size")
        total += int_field(db.execute("SELECT COUNT(*)*32768 AS size FROM action_receipts").fetchone(), "size")
        if total > c.MAX_HISTORY:
            raise GameError("HISTORY_BUDGET", "Game history reached its 256 MiB payload budget; existing revisions remain readable", 409)

    def create(self, project_id: str, actor: Actor, key: str, request: c.CreateInput, guard: Guard = lambda: None) -> c.Mutation:
        with self.connection(write=True) as db:
            guard()
            fingerprint = request_hash("create", request)
            previous = self._receipt(db, project_id, actor, key, fingerprint)
            if previous is not None:
                return previous
            library_version = self._library(db, project_id)
            if library_version != request.expected_library_version:
                raise GameError("STALE_VERSION", "Game library changed; inspect it before creating", 409)
            rows = db.execute("SELECT r.deleted FROM games g JOIN revisions r ON g.project_id=r.project_id AND g.game_id=r.game_id AND g.head=r.version WHERE g.project_id=?", (project_id,)).fetchall()
            if len(rows) >= 128 or sum(not int_field(row, "deleted") for row in rows) >= 64:
                raise GameError("GAME_BUDGET", "Project supports 64 active Games and 128 retained Game identities", 409)
            game = new_game(request.title)
            guard()
            return self._save(db, project_id, actor, key, "create", fingerprint, game, None, False, {}, guard)

    def mutate(self, project_id: str, actor: Actor, key: str, action: Literal["apply", "undo", "delete", "upload"], request: c.VersionInput, guard: Guard = lambda: None) -> c.Mutation:
        with self.connection(write=True) as db:
            guard()
            fingerprint = request_hash(action, request)
            previous = self._receipt(db, project_id, actor, key, fingerprint)
            if previous is not None:
                return previous
            base = self._get(db, project_id, request.game_id)
            if base.version != request.expected_version:
                raise GameError("STALE_VERSION", "Game changed; inspect the current version before editing", 409)
            if base.deleted and action != "undo":
                raise GameError("GAME_DELETED", "Game is deleted; restore an earlier revision to edit", 409)
            game, deleted, aliases = base.game, base.deleted, {}
            if action == "apply" and isinstance(request, c.ApplyInput):
                applied = apply_operations(game, request.operations)
                game, aliases = applied.game, applied.created_refs
                existing = {text_field(row, "object_id") for row in db.execute("SELECT object_id FROM identities WHERE project_id=? AND game_id=?", (project_id, game.id))}
                if applied.allocated_ids & existing:
                    raise GameError("IDENTITY_COLLISION", "Generated Game object identity already exists", 409)
            elif action == "undo" and isinstance(request, c.UndoInput):
                target = self._get(db, project_id, request.game_id, request.target_version)
                if target.version > base.version:
                    raise GameError("INVALID_REVISION", "Undo target must be in this Game history")
                game, deleted = target.game, target.deleted
            elif action == "delete":
                deleted = True
            elif action == "upload" and isinstance(request, c.UploadInput):
                try:
                    raw = base64.b64decode(request.rgba_base64, validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise GameError("INVALID_ASSET", "Asset must contain canonical base64 RGBA bytes") from exc
                if len(raw) != request.width * request.height * 4 or base64.b64encode(raw).decode("ascii") != request.rgba_base64:
                    raise GameError("INVALID_ASSET", "Asset byte length or base64 encoding does not match its dimensions")
                game, asset = self._add_asset(db, project_id, game, request.name, request.width, request.height, raw)
                aliases = {"asset": asset.id}
            else:
                raise GameError("INVALID_OPERATION", "Game operation and typed input do not match")
            if base.deleted and not deleted:
                active = db.execute("SELECT COUNT(*) AS count FROM games g JOIN revisions r ON g.project_id=r.project_id AND g.game_id=r.game_id AND g.head=r.version WHERE g.project_id=? AND r.deleted=0", (project_id,)).fetchone()
                if int_field(active, "count") >= 64:
                    raise GameError("GAME_BUDGET", "Restore would exceed 64 active Games", 409)
            guard()
            return self._save(db, project_id, actor, key, action, fingerprint, game, base, deleted, aliases, guard)

    @staticmethod
    def _add_asset(db: sqlite3.Connection, project_id: str, game: c.GameProject, name: str, width: int, height: int, raw: bytes, source: c.Source | None = None) -> tuple[c.GameProject, c.Asset]:
        if len(raw) != width * height * 4:
            raise GameError("INVALID_ASSET", "Asset RGBA byte count does not match its dimensions")
        asset = c.Asset(id=str(uuid4()), name=name, width=width, height=height, content_hash=digest(raw), source=source)
        if db.execute("SELECT 1 FROM identities WHERE project_id=? AND game_id=? AND object_id=?", (project_id, game.id, asset.id)).fetchone():
            raise GameError("IDENTITY_COLLISION", "Generated asset identity already exists", 409)
        game = game.model_copy(deep=True)
        game.assets.append(asset)
        game = c.GameProject.model_validate(game.data())
        row = db.execute("SELECT payload FROM blobs WHERE project_id=? AND content_hash=?", (project_id, asset.content_hash)).fetchone()
        if row is None:
            db.execute("INSERT INTO blobs VALUES (?,?,?)", (project_id, asset.content_hash, raw))
        elif payload_field(row, "payload") != raw:
            raise GameError("STATE_CORRUPT", "Stored Game asset hash collision", 500)
        return game, asset

    def import_asset(self, project_id: str, key: str, request: c.ImportInput, raw: bytes, source: c.Source, guard: Guard) -> c.Mutation:
        with self.connection(write=True) as db:
            guard()
            fingerprint = request_hash("import", request)
            previous = self._receipt(db, project_id, "agent", key, fingerprint)
            if previous is not None:
                return previous
            base = self._get(db, project_id, request.game_id)
            if base.version != request.expected_version or base.deleted:
                raise GameError("STALE_VERSION", "Game changed before asset import commit", 409)
            if source.artifact_id != request.source_artifact_id or source.frame_id != request.frame_id or source.rect != request.rect:
                raise GameError("SOURCE_MISMATCH", "Imported asset provenance does not match its request")
            game, asset = self._add_asset(db, project_id, base.game, request.name, request.rect.width, request.rect.height, raw, source)
            return self._save(db, project_id, "agent", key, "import", fingerprint, game, base, False, {"asset": asset.id}, guard)

    def _save(self, db: sqlite3.Connection, project_id: str, actor: Actor, key: str, action: str, fingerprint: str, game: c.GameProject, base: c.Revision | None, deleted: bool, aliases: dict[str, str], guard: Guard) -> c.Mutation:
        library_version = self._library(db, project_id)
        raw = c.encoded(game.data())
        changed = action == "undo" or base is None or base.content_hash != digest(raw) or base.deleted != deleted
        version = 1 if base is None else base.version + int(changed)
        if changed:
            library_version += 1
            if library_version > 2**53-1 or version > 2**53-1:
                raise GameError("VERSION_BUDGET", "Game version counter exhausted", 409)
            current = self._identities(game)
            for identity, kind in current.items():
                row = db.execute("SELECT kind FROM identities WHERE project_id=? AND game_id=? AND object_id=?", (project_id, game.id, identity)).fetchone()
                if row is None:
                    db.execute("INSERT INTO identities VALUES (?,?,?,?)", (project_id, game.id, identity, kind))
                elif text_field(row, "kind") != kind:
                    raise GameError("STATE_CORRUPT", "Stable Game identity cannot change its kind", 500)
            db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?,?,?,?)", (project_id, game.id, version, library_version, digest(raw), int(deleted), raw, actor, key, action, datetime.now(timezone.utc).isoformat()))
            if base is None:
                db.execute("INSERT INTO games VALUES (?,?,?)", (project_id, game.id, version))
            elif db.execute("UPDATE games SET head=? WHERE project_id=? AND game_id=? AND head=?", (version, project_id, game.id, base.version)).rowcount != 1:
                raise GameError("STALE_VERSION", "Game changed before commit", 409)
            db.execute("UPDATE projects SET version=? WHERE project_id=?", (library_version, project_id))
        result_revision = c.Revision(game=game, project_id=project_id, version=version, library_version=library_version, content_hash=digest(raw), deleted=deleted)
        before = {} if base is None else {identity: item.data() for identity, item in object_index(base.game).items()}
        after = {identity: item.data() for identity, item in object_index(game).items()}
        changed_ids = sorted(identity for identity in before.keys() | after.keys() if before.get(identity) != after.get(identity))
        if base is None or base.deleted != deleted or base.game.title != game.title or base.game.initial_scene_id != game.initial_scene_id:
            changed_ids.insert(0, game.id)
        result = c.Mutation(game=result_revision.summary(), library_version=library_version, changed=changed, changed_ids=changed_ids[:64], truncated=len(changed_ids) > 64, created_refs=aliases)
        result_bytes = c.encoded(result.data())
        db.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?)", (project_id, actor, key, fingerprint, digest(result_bytes), result_bytes))
        self._budget(db)
        guard()
        return result

    def export(self, project_id: str, actor: Actor, key: str, request: c.VersionInput, guard: Guard = lambda: None) -> c.Mutation:
        with self.connection(write=True) as db:
            guard()
            fingerprint = request_hash("export", request)
            previous = self._receipt(db, project_id, actor, key, fingerprint)
            if previous is not None:
                return previous
            revision = self._get(db, project_id, request.game_id)
            if revision.version != request.expected_version:
                raise GameError("STALE_VERSION", "Game changed before export", 409)
            result = c.Mutation(game=revision.summary(), library_version=self._library(db, project_id), changed=False)
            raw = c.encoded(result.data())
            db.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?)", (project_id, actor, key, fingerprint, digest(raw), raw))
            self._budget(db)
            guard()
            return result

    @staticmethod
    def _report_summary(identity: str, report: c.SimulationReport) -> c.PlaytestSummary:
        return c.PlaytestSummary(id=identity, engine=report.engine, seed=report.seed, ticks_requested=report.ticks_requested, ticks_completed=report.ticks_completed, outcome=report.outcome, reason=report.reason, event_count=report.event_count, events_truncated=report.events_truncated, entity_count=len(report.entities))

    @staticmethod
    def validate_report(revision: c.Revision, request: c.PlaytestInput, report: c.SimulationReport) -> None:
        if report.seed != request.seed or report.ticks_requested != request.ticks or report.engine != revision.game.engine:
            raise GameError("REPORT_MISMATCH", "Playtest result does not match its frozen input", 409)
        scenes = {item.id for item in revision.game.scenes}
        entities = {item.id: item for item in revision.game.entities}
        if report.scene_id not in scenes or any(event.scene_id not in scenes for event in report.events):
            raise GameError("REPORT_MISMATCH", "Playtest scene does not belong to its source", 409)
        variables = {item.id: item for item in revision.game.variables}
        if set(report.variables) != set(variables):
            raise GameError("REPORT_MISMATCH", "Playtest variables do not match the source", 409)
        for identity, value in report.variables.items():
            c.check_value(variables[identity].value_type, value)
        for item in report.entities:
            source = entities.get(item.template_id)
            if source is None or item.id.split(":")[0] != item.template_id or source.scene_id != report.scene_id or item.scene_id != report.scene_id:
                raise GameError("REPORT_MISMATCH", "Runtime entity does not match its source template and scene", 409)
            health = next((part.spec for part in source.components if isinstance(part.spec, c.Health)), None)
            if (health is None) != (item.health is None) or (health is not None and item.health is not None and item.health > health.maximum):
                raise GameError("REPORT_MISMATCH", "Runtime health does not match its source component", 409)
        for event in report.events:
            if any(identity.split(":")[0] not in entities for identity in event.entity_ids):
                raise GameError("REPORT_MISMATCH", "Playtest event refers to a foreign template", 409)
        if report.outcome != "exhausted":
            expected_kind = "budget_exceeded" if report.outcome == "budget_exceeded" else "finish"
            if not report.events or report.events[-1].kind != expected_kind or report.events[-1].tick != report.ticks_completed:
                raise GameError("REPORT_MISMATCH", "Terminal event must survive event-log truncation", 409)

    def save_report(self, project_id: str, key: str, request: c.PlaytestInput, report: c.SimulationReport, guard: Guard) -> c.Mutation:
        with self.connection(write=True) as db:
            guard()
            fingerprint = request_hash("playtest", request)
            previous = self._receipt(db, project_id, "agent", key, fingerprint)
            if previous is not None:
                return previous
            revision = self._get(db, project_id, request.game_id)
            if revision.version != request.expected_version or revision.deleted:
                raise GameError("STALE_VERSION", "Game changed before playtest result commit", 409)
            self.validate_report(revision, request, report)
            identity = str(uuid4())
            raw = c.encoded(report.data())
            db.execute("INSERT INTO reports VALUES (?,?,?,?,?,?,?)", (project_id, revision.game.id, identity, revision.version, revision.content_hash, digest(raw), raw))
            result = c.Mutation(game=revision.summary(), library_version=self._library(db, project_id), changed=False, report=self._report_summary(identity, report))
            output = c.encoded(result.data())
            db.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?)", (project_id, "agent", key, fingerprint, digest(output), output))
            self._budget(db)
            guard()
            return result

    def _report(self, db: sqlite3.Connection, project_id: str, game_id: str, version: int, report_id: str) -> c.SimulationReport:
        revision = self._get(db, project_id, game_id, version)
        row = db.execute("SELECT * FROM reports WHERE project_id=? AND game_id=? AND version=? AND report_id=?", (project_id, game_id, version, report_id)).fetchone()
        if row is None:
            raise GameError("NOT_FOUND", "Game playtest report does not exist for this fixed revision", 404)
        raw = payload_field(row, "payload")
        if text_field(row, "content_hash") != revision.content_hash or digest(raw) != text_field(row, "payload_hash") or len(raw) > c.MAX_REPORT:
            raise GameError("STATE_CORRUPT", "Game playtest report failed integrity verification", 500)
        try:
            return c.SimulationReport.model_validate_json(raw)
        except ValueError as exc:
            raise GameError("STATE_CORRUPT", "Game playtest report schema is invalid", 500) from exc

    def report(self, project_id: str, game_id: str, version: int, report_id: str) -> c.SimulationReport:
        with self.connection() as db:
            return self._report(db, project_id, game_id, version, report_id)

    def reserve_action(self, project_id: str, key: str, action: str, request: c.VersionInput) -> c.ActionResult | None:
        with self.connection(write=True) as db:
            if db.execute("SELECT 1 FROM receipts WHERE project_id=? AND actor='human' AND request_key=?", (project_id, key)).fetchone():
                raise GameError("REQUEST_MISMATCH", "Request identity already belongs to a Game edit", 409)
            fingerprint = request_hash(action, request)
            row = db.execute("SELECT * FROM action_receipts WHERE project_id=? AND request_key=?", (project_id, key)).fetchone()
            if row is not None:
                if text_field(row, "request_hash") != fingerprint:
                    raise GameError("REQUEST_MISMATCH", "Game action identity was reused with different input", 409)
                raw = payload_field(row, "payload")
                if not raw:
                    raise GameError("ACTION_RESULT_UNKNOWN", "This Game action was already started; do not replay it", 409)
                if digest(raw) != text_field(row, "payload_hash"):
                    raise GameError("STATE_CORRUPT", "Game action receipt failed integrity verification", 500)
                try:
                    return c.ActionResult.model_validate_json(raw)
                except ValueError as exc:
                    raise GameError("STATE_CORRUPT", "Game action receipt schema is invalid", 500) from exc
            revision = self._get(db, project_id, request.game_id)
            if revision.version != request.expected_version:
                raise GameError("STALE_VERSION", "Game changed before action admission", 409)
            db.execute("INSERT INTO action_receipts VALUES (?,?,?,?,?)", (project_id, key, fingerprint, digest(b""), b""))
            self._budget(db)
            return None

    def finish_action(self, project_id: str, key: str, action: str, request: c.VersionInput, result: c.ActionResult) -> None:
        raw = c.encoded(result.data())
        if len(raw) > 32768:
            raise GameError("ACTION_BUDGET", "Game action result exceeds its reserved budget")
        with self.connection(write=True) as db:
            if db.execute("UPDATE action_receipts SET payload=?,payload_hash=? WHERE project_id=? AND request_key=? AND request_hash=? AND length(payload)=0", (raw, digest(raw), project_id, key, request_hash(action, request))).rowcount != 1:
                raise GameError("REQUEST_MISMATCH", "Game action reservation does not match", 409)

    def history(self, project_id: str, game_id: str, through_version: int, offset: int, limit: int) -> tuple[int, list[dict[str, c.JsonValue]]]:
        with self.connection() as db:
            self._get(db, project_id, game_id, through_version)
            rows = db.execute("SELECT version,content_hash,deleted,actor,operation,created_at FROM revisions WHERE project_id=? AND game_id=? AND version<=? ORDER BY version DESC LIMIT ? OFFSET ?", (project_id, game_id, through_version, limit, offset)).fetchall()
            return through_version, [{"version": int_field(row, "version"), "content_hash": text_field(row, "content_hash"), "deleted": bool(int_field(row, "deleted")), "actor": text_field(row, "actor"), "operation": text_field(row, "operation"), "created_at": text_field(row, "created_at")} for row in rows]
