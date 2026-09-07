"""Independent adversarial checks of installed Game; executor reports are fixtures.

No product store writes bypass its registered operations. SQLite reads only count
durable side effects. These tests do not claim actual Phaser simulation evidence.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from dbfox_dlc_api import Artifact, ArtifactRepresentationContext, ArtifactRepresentationError, ArtifactRepresentationRequest, DlcOperationContext, DlcOperationError, ResourceScopeRef, ToolKey
from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.runtime_composition import build_product_tool_registry
from engine.tools.runtime import ToolRuntime


class InstalledGame:
    def __init__(self, root):
        source = Path(__file__).resolve().parents[3] / "dlcs/dbfox.game"
        package = root / "package"
        package.mkdir()
        for name in ("backend", "frontend"):
            shutil.copytree(source / name, package / name, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(source / "manifest.template.json", package / "manifest.template.json")
        key = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Independent Game red team fixture key").digest())
        built = build_dlc_package_from_source(package, private_key=key)
        archive = root / "game.dbfox-dlc"
        archive.write_bytes(built.archive_bytes)
        self.digest = built.package_digest
        self.service = DlcPackageService(root / "dlcs")
        self.service.trust_publisher_from_file(archive, expected_package_digest=built.package_digest, expected_publisher_key_id=built.publisher_fingerprint)
        self.service.install_from_file(archive)
        self.service.set_desired_enabled("dbfox.game", True)
        self.reload()
        self.project = "independent-redteam"

    def reload(self):
        self.snapshot = ContributionCompiler(self.service.storage_root).compile(built_ins=BuiltinContributionSet())
        assert not self.snapshot.activation_failures
        self.registry = build_product_tool_registry(self.snapshot)
        self.runtime = ToolRuntime(self.registry)

    def op(self, name, data, project=True):
        spec = self.snapshot.get_operation("dbfox.game", name).spec
        return spec.handler(spec.input_model.model_validate(data), DlcOperationContext(
            dlc_id="dbfox.game", operation_name=name,
            project_id=self.project if project is True else project if isinstance(project, str) else None))

    def create(self, title="Independent", version=1):
        return self.op("games.create", {"title": title, "expected_library_version": version, "request_id": str(uuid4())}).game

    def invoke(self, name, data, ref, identity=None, cancel=None):
        resolver = next(r.resolver for r in self.snapshot.resource_resolvers if r.kind == ref.kind)
        identity = identity or str(uuid4())
        return self.runtime.invoke(tool_name=self.registry.provider_name_for_key(ToolKey("dbfox.game", name)),
            raw_input=data, request=None, idempotency_key=identity, invocation_id=identity,
            scope_refs=(ref,), resources={ref.canonical(): resolver(ref)}, cancellation_probe=cancel)

    @staticmethod
    def ref(game):
        return ResourceScopeRef(kind="dbfox.game.project", id=game.id, version=game.version)

    def attach(self, client=None, counter=1):
        result = self.op("playtest.attach", {"client_id": client or str(uuid4()), "registration_counter": counter,
            "package_digest": self.digest, "engine": "phaser-arcade-4.2.1", "available": True}, project=False)
        return result.model_dump(include={"epoch", "lease", "registration_counter"})

    def claim(self, lease):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = self.op("playtest.next", lease, project=False)
            if result.request is not None:
                return result.request.model_dump(mode="json", exclude_none=True)
            time.sleep(.005)
        pytest.fail("Installed executor did not receive a request")

    def complete(self, lease, request, report=None, **changes):
        proof = {k: request[k] for k in ("request_id", "invocation_id", "game_id", "version", "source_hash", "input_hash", "claim_id")}
        return self.op("playtest.complete", {**lease, **proof, "package_digest": self.digest,
            "report": report or self.report(request), **changes}, project=False)

    @staticmethod
    def report(request):
        data = request["input"]
        game = request["snapshot"]["document"]
        return {"engine": game["engine"], "seed": data["seed"], "ticks_requested": data["ticks"],
            "ticks_completed": data["ticks"], "scene_tick": data["ticks"], "scene_id": game["initial_scene_id"],
            "outcome": "exhausted", "reason": "Independent protocol fixture", "event_count": 0,
            "events_truncated": False, "events": [], "entities": [], "variables": {}}

    def counts(self):
        paths = list(self.service.storage_root.rglob("state.sqlite3"))
        assert len(paths) == 1
        with sqlite3.connect(paths[0]) as db:
            return {t: db.execute("SELECT count(*) FROM " + t).fetchone()[0] for t in ("revisions", "receipts", "reports")}


@pytest.fixture
def game(tmp_path):
    return InstalledGame(tmp_path)


def test_cross_project_and_wrong_frozen_game_cannot_modify(game):
    a = game.create()
    b = game.create("Second", 2)
    original = game.counts()
    for operation, payload in (("games.head", {"game_id": a.id}), ("games.apply", {
        "game_id": a.id, "expected_version": 1, "request_id": str(uuid4()),
        "operations": [{"kind": "game_rename", "title": "Unauthorized"}]})):
        with pytest.raises(DlcOperationError, match="does not exist in this project"):
            game.op(operation, payload, project="foreign-project")
    result = game.invoke("game_modify", {"game_id": b.id, "expected_version": 1,
        "operations": [{"kind": "game_rename", "title": "Wrong frozen resource"}]}, game.ref(a))
    assert result.status == "failed" and not result.artifact_drafts
    assert game.counts() == original


def test_batch_foreign_object_rolls_back_and_concurrent_public_edits_have_one_winner(game):
    a = game.create()
    b = game.create("Foreign object owner", 2)
    other_scene = game.op("games.get", {"game_id": b.id, "version": 1, "section": "summary"}).metadata["initial_scene_id"]
    before = game.counts()
    invalid = {"game_id": a.id, "expected_version": 1, "operations": [
        {"kind": "game_rename", "title": "Must roll back"},
        {"kind": "entity_create", "entities": [{"scene_id": {"id": other_scene}, "name": "Foreign scene entity"}]}]}
    failed = game.invoke("game_modify", invalid, game.ref(a))
    assert failed.status == "failed" and not failed.artifact_drafts
    assert game.counts() == before
    assert game.op("games.head", {"game_id": a.id}).game.title == a.title

    barrier = threading.Barrier(2)
    def edit(title):
        barrier.wait(timeout=2)
        try:
            return game.op("games.apply", {"game_id": a.id, "expected_version": 1, "request_id": str(uuid4()),
                "operations": [{"kind": "game_rename", "title": title}]}).game
        except DlcOperationError as exc:
            assert exc.code == "STALE_VERSION"
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ("Human A", "Human B")))
    winner = [r for r in results if r is not None]
    assert len(winner) == 1 and winner[0].version == 2
    assert game.op("games.head", {"game_id": a.id}).game == winner[0]
    after = game.counts()
    assert after["revisions"] == before["revisions"] + 1
    assert after["receipts"] == before["receipts"] + 1


@pytest.mark.parametrize("change", ["replace_executor", "human_edit", "cancel"])
def test_inflight_result_cannot_survive_authority_or_cancellation_change(game, change):
    made = game.create()
    original = game.counts()
    client = str(uuid4())
    lease = game.attach(client)
    cancelled = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(game.invoke, "playtest", {"game_id": made.id, "expected_version": 1, "ticks": 60},
            game.ref(made), cancel=cancelled.is_set)
        request = game.claim(lease)
        if change == "replace_executor":
            replacement = game.attach(client, 2)
            with pytest.raises(DlcOperationError, match="lease|active"):
                game.complete(lease, request)
            with pytest.raises(DlcOperationError, match="active request|proof"):
                game.complete(replacement, request)
        elif change == "human_edit":
            game.op("games.apply", {"game_id": made.id, "expected_version": 1, "request_id": str(uuid4()),
                "operations": [{"kind": "game_rename", "title": "Human edit while computing"}]})
            game.complete(lease, request)
        else:
            cancelled.set()
        result = future.result(3)
    assert result.status == "failed" and not result.artifact_drafts
    counts = game.counts()
    assert counts["reports"] == 0
    assert counts["revisions"] == original["revisions"] + (change == "human_edit")
    assert counts["receipts"] == original["receipts"] + (change == "human_edit")


@pytest.mark.parametrize("attack", ["wrong_input_hash", "foreign_entity", "missing_terminal_event"])
def test_report_claim_and_source_validation_fail_closed(game, attack):
    made = game.create()
    original = game.counts()
    lease = game.attach()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(game.invoke, "playtest", {"game_id": made.id, "expected_version": 1, "ticks": 2}, game.ref(made))
        request = game.claim(lease)
        report = game.report(request)
        if attack == "wrong_input_hash":
            with pytest.raises(DlcOperationError, match="proof"):
                game.complete(lease, request, input_hash="0" * 64)
            game.op("playtest.detach", lease, project=False)
        else:
            if attack == "foreign_entity":
                identity = str(uuid4())
                report["entities"] = [{"id": identity, "template_id": identity, "scene_id": report["scene_id"], "x": 0, "y": 0, "vx": 0, "vy": 0}]
            else:
                report["outcome"] = "won"
            game.complete(lease, request, report)
        result = future.result(3)
    assert result.status == "failed" and not result.artifact_drafts
    assert game.counts() == original


def test_report_receipt_replay_and_immutable_representation_after_reactivation(game):
    made = game.create()
    lease = game.attach()
    identity = str(uuid4())
    payload = {"game_id": made.id, "expected_version": 1, "ticks": 3, "seed": 7}
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(game.invoke, "playtest", payload, game.ref(made), identity)
        request = game.claim(lease)
        game.complete(lease, request)
        result = future.result(3)
    assert result.status == "success", result.error
    game.op("playtest.detach", lease, project=False)
    before = game.counts()
    replay = game.invoke("playtest", payload, game.ref(made), identity)
    assert replay.status == "success" and replay.output == result.output
    changed = game.invoke("playtest", {**payload, "seed": 8}, game.ref(made), identity)
    assert changed.status == "failed" and game.counts() == before
    draft = result.artifact_drafts[0]
    artifact = Artifact(id=str(uuid4()), run_id="independent-run", session_id="independent-session", turn_id="independent-turn",
        type=draft.type, schema_version=1, title=draft.title, payload=draft.payload, resource_refs=draft.resource_refs)

    def export(parameters=None):
        provider = game.snapshot.get_artifact_representation(artifact.type, "dbfox.game.playtest.v1").provider
        stream = provider.execute(artifact, ArtifactRepresentationRequest(operation="export", parameters=parameters or {}),
            ArtifactRepresentationContext(artifact_loader=lambda _: artifact))
        return b"".join(stream.chunks)

    raw = export()
    with pytest.raises(ArtifactRepresentationError, match="parameters or locator"):
        export({"version": 999, "game_id": str(uuid4())})
    game.op("games.delete", {"game_id": made.id, "expected_version": 1, "request_id": str(uuid4())})
    game.service.set_desired_enabled("dbfox.game", False)
    game.reload()
    assert not game.snapshot.get_operation("dbfox.game", "games.head")
    assert not game.snapshot.artifact_representations
    game.service.set_desired_enabled("dbfox.game", True)
    game.reload()
    assert export() == raw
    decoded = json.loads(raw)
    assert decoded["source"]["version"] == 1 and decoded["report"]["seed"] == 7
    assert game.counts()["reports"] == 1
